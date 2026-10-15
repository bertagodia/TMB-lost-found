"""Real browser smoke test. Requires Playwright and Chromium or BROWSER_CHANNEL=chrome."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from uuid import uuid4

import httpx
from PIL import Image
from playwright.sync_api import sync_playwright, expect
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from database.migrate import migrate
from database.repository import Repository


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = os.environ.get('TEST_DATABASE_URL')
        if not cls.admin:
            raise RuntimeError('Set TEST_DATABASE_URL to a local PostgreSQL role with CREATEDB')
        cls.name = 'tmb_test_' + uuid4().hex
        with psycopg.connect(cls.admin, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.name)))
        cls.addClassCleanup(cls.drop_database)
        cls.dsn = make_conninfo(cls.admin, dbname=cls.name)
        migrate(cls.dsn)
        cls.repo = Repository(cls.dsn)

    @classmethod
    def drop_database(cls):
        with psycopg.connect(cls.admin, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(cls.name)))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root/'photo.png'
        Image.new('RGB', (24, 24), 'gray').save(self.image)
        with socket.socket() as handle:
            handle.bind(('127.0.0.1', 0))
            self.port = handle.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        self.process = None
        self.addCleanup(self.stop_server)
        self.start_server()

    def start_server(self):
        self.process = subprocess.Popen([sys.executable, '-m', 'backend.server', '--port', str(self.port),
            '--data-dir', str(self.root/'files')], env={**os.environ, 'DATABASE_URL': self.dsn},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 15
        with httpx.Client(timeout=0.5, trust_env=False) as client:
            while time.monotonic() < deadline:
                try:
                    if client.get(self.url+'/api/health').status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                if self.process.poll() is not None:
                    self.fail('The API process exited before becoming ready')
                time.sleep(0.1)
        self.fail('The API did not become ready within 15 seconds')

    def stop_server(self):
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=10)
            self.process = None

    def test_both_forms_survive_backend_outage_and_restart(self):
        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True, channel=os.environ.get('BROWSER_CHANNEL') or None)
            try:
                page = browser.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('**/api/extract', lambda route: route.fulfill(status=502,
                    content_type='application/json', body='{"error":"Simulated offline Ollama"}'))
                page.goto(self.url)
                page.fill('#manualLine', 'H12')
                page.fill('#manualVehicle', '3421')
                page.click('#manualVehicleButton')
                page.click('#nextButton')
                for position in (0, 1):
                    with page.expect_file_chooser() as chooser:
                        page.click(f'.photo-button[data-photo="{position}"]')
                    chooser.value.set_files(self.image)
                    expect(page.locator(f'#photoStatus{position}')).to_contain_text('Revisada')
                page.click('#nextButton')
                expect(page.locator('#extractionStatus')).to_contain_text('No s’ha pogut')
                page.check('#color input[value="Gris"]')
                page.select_option('#objectType', 'Motxilla')
                page.select_option('#material', 'Tèxtil')
                page.fill('#description', 'Motxilla de prova')
                page.check('#fieldsReviewed')
                page.click('#nextButton')
                self.stop_server()
                page.click('#nextButton')
                page.wait_for_function("JSON.parse(localStorage.getItem('tmb-lost-found-queue')||'[]').length===1")
                expect(page.locator('#toast')).to_contain_text('pendent')
                self.assertEqual(self.repo.list_records('objects')['total'], 0)
                operator_id = page.evaluate("JSON.parse(localStorage.getItem('tmb-lost-found-queue'))[0].id")
                self.start_server()
                page.reload()
                page.wait_for_function("JSON.parse(localStorage.getItem('tmb-lost-found-queue')||'[]').length===0")
                self.assertIsNotNone(self.repo.get_object(operator_id))

                page.click('#citizenTab')
                page.fill('#citizenDescription', 'Motxilla grisa de prova')
                page.fill('#citizenName', 'Browser Test')
                page.fill('#citizenEmail', 'browser@example.invalid')
                page.locator('#citizenPhoto').set_input_files(self.image)
                expect(page.locator('#citizenPhotoPreview')).to_be_visible()
                page.click('.citizen-submit')
                expect(page.locator('#citizenConfirmation')).to_contain_text('guardada a la base de dades local')
                self.assertEqual(self.repo.list_records('reports')['total'], 1)

                self.stop_server()
                page.fill('#citizenDescription', 'Claus de prova pendents')
                page.fill('#citizenName', 'Offline Test')
                page.fill('#citizenEmail', 'offline@example.invalid')
                page.click('.citizen-submit')
                expect(page.locator('#citizenConfirmation')).to_contain_text('pendent d’enviament')
                expect(page.locator('.citizen-submit')).to_be_enabled()
                citizen_id = page.evaluate("JSON.parse(localStorage.getItem('tmb-lost-found-citizen-reports')).find(r=>r.status==='pending').id")
                self.assertEqual(self.repo.list_records('reports')['total'], 1)
                self.start_server()
                page.reload()
                page.wait_for_function("JSON.parse(localStorage.getItem('tmb-lost-found-citizen-reports')).every(r=>r.status==='sent')")
                self.assertIsNotNone(self.repo.get_report(citizen_id))
                self.assertEqual(self.repo.get_contact(citizen_id)['email'], 'offline@example.invalid')
                self.assertEqual(self.repo.list_records('objects')['total'], 1)
                self.assertEqual(self.repo.list_records('reports')['total'], 2)
                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
