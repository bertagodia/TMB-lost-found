import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lostfound.search import SearchEngine
from lostfound.data.loader import load_objects
from lostfound.api.server import make_handler


class WebTests(unittest.TestCase):
    def test_form_search_and_validation(self):
        with ThreadingHTTPServer(('127.0.0.1', 0), make_handler(SearchEngine(load_objects()))) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(base) as response:
                    self.assertIn('Buscar un objeto', response.read().decode())
                for path, mime, expected in (
                    ('/app.js', 'text/javascript', 'addEventListener'),
                    ('/styles.css', 'text/css', '.layout'),
                ):
                    with urlopen(base + path) as response:
                        self.assertIn(mime, response.headers['Content-Type'])
                        self.assertIn(expected, response.read().decode())
                request = Request(base + '/api/search', data=json.dumps({'description': 'Mochila roja'}).encode(),
                                  headers={'Content-Type': 'application/json'})
                with urlopen(request) as response:
                    self.assertTrue(json.load(response)['results'])
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base + '/api/search', data=b'{}'))
                self.assertEqual(error.exception.code, 400)
                error.exception.close()
            finally:
                server.shutdown()
                thread.join()
