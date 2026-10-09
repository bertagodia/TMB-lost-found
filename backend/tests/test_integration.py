import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from pydantic import ValidationError
from backend.server import Application
from search.form_extraction import FormFields, Recognition, extract_form
from search.extraction import ExtractionError


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / 'image.png'
        Image.new('RGB', (24, 24), 'gray').save(self.image)
        self.photo = {'data': 'data:image/png;base64,' + base64.b64encode(self.image.read_bytes()).decode()}
        self.fields = dict(colors=['Gris', 'Negre'], objectType='Motxilla', material='Tèxtil',
                           description='backpack. Front cord')
        self.draft = dict(object_name='backpack', visible_features=['Front cord'],
                          colors=['gray', 'black'], material='textile',
                          quality='usable', sensitive_content=False)
        self.app = Application(self.root / 'store')
        self.record = dict(id='test-1', details=self.fields, photos=[self.photo, self.photo],
                           reviewed=True, vehicle={'line': 'H12', 'vehicle': '3421'},
                           capturedAt='2026-10-08T10:00:00Z', status='pending')

    def test_order_multi_colors_and_strict_choices(self):
        self.assertEqual(list(FormFields.model_fields), ['colors', 'objectType', 'material', 'description'])
        value = FormFields.model_validate_json(json.dumps(self.fields))
        self.assertEqual(value.model_dump(mode='json')['colors'], ['Gris', 'Negre'])
        with self.assertRaises(ValidationError):
            FormFields.model_validate_json(json.dumps({**self.fields, 'colors': ['invented']}))
        with self.assertRaises(ValidationError):
            FormFields.model_validate_json(json.dumps({**self.fields, 'description': 'x' * 251}))

    def test_real_contract_and_unusable_output_gate(self):
        with patch('search.form_extraction.request_json', return_value=json.dumps(self.draft)) as model:
            result = extract_form(self.image)
            self.assertEqual(result['fields'], self.fields)
            self.assertEqual(result['review_status'], 'pending')
            self.assertIn('WHOLE object', model.call_args.kwargs['prompt'])
            self.assertEqual(result['recognized_object'], 'backpack')
        with patch('search.form_extraction.request_json', return_value=json.dumps({**self.draft, 'sensitive_content': True})):
            self.assertEqual(extract_form(self.image)['fields'], dict(colors=[], objectType=None, material=None, description=''))
        with patch('search.form_extraction.request_json', return_value='{}'):
            with self.assertRaises(ExtractionError):
                extract_form(self.image)

    def test_cache_and_provenance(self):
        with patch('backend.server.model_digest', return_value='digest'), \
             patch('search.form_extraction.request_json', return_value=json.dumps(self.draft)) as model:
            first = self.app.extract({'photo': self.photo})
            second = self.app.extract({'photo': self.photo})
            self.assertFalse(first['cached'])
            self.assertTrue(second['cached'])
            self.assertEqual(model.call_count, 1)
        record = {**self.record, 'extractionId': first['id']}
        with self.assertRaisesRegex(ValueError, 'Confirma'):
            self.app.submit({**record, 'reviewed': False})
        self.assertFalse(self.app.submit(record)['queued'])
        self.assertTrue(self.app.submit(record)['duplicate'])
        saved = json.loads(next((self.root/'store/records').glob('*.json')).read_text())
        self.assertEqual(saved['details']['colors'], ['Gris', 'Negre'])
        self.assertEqual(saved['extractionId'], first['id'])
        with self.assertRaises(FileExistsError):
            self.app.submit({**record, 'details': {**self.fields, 'description': 'changed'}})

    def test_bad_image_does_not_create_record(self):
        with self.assertRaises((ValueError, ExtractionError)):
            self.app.submit({**self.record, 'photos': [{'data': 'data:image/png;base64,YmFk'}]})
        self.assertFalse((self.root/'store/records').exists())

    def test_busy_and_legacy_single_color(self):
        with self.app.extraction_lock:
            with self.assertRaises(BlockingIOError):
                self.app.extract({'photo': self.photo})
        details={**self.fields,'color':'Negre'}
        del details['colors']
        result=self.app.submit({**self.record,'details':details})
        self.assertEqual(result['status'],'received-local')


if __name__ == '__main__':
    unittest.main()
