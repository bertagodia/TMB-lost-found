import base64
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from PIL import Image
    from search.extraction import ImageAttributes, ExtractionError, _prepare_image, extract_image
    from search.pipeline import extract_batch, extract_version
except ImportError:
    Image = None

from search.storage import Inventory


@unittest.skipIf(Image is None, 'Optional extraction dependencies are not installed')
class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / 'object.png'
        Image.new('RGBA', (1400, 700), (255, 0, 0, 0)).save(self.image)

    def test_preprocessing_transparency_size_and_hash(self):
        encoded, digest = _prepare_image(self.image)
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as result:
            self.assertEqual(result.size, (1024, 512))
            self.assertEqual(result.mode, 'RGB')
            self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
            self.assertFalse(result.getexif())
        self.assertEqual(len(digest), 64)
        with Image.open(self.image) as original:
            self.assertEqual(original.size, (1400, 700))

    def test_bad_image_and_sensitive_draft(self):
        self.image.write_bytes(b'not an image')
        with self.assertRaises(ExtractionError):
            _prepare_image(self.image)
        attrs = ImageAttributes(category='mochila', colors=['negro'], material=None,
                                brand=None, distinctive_features=[], quality='usable',
                                sensitive_content=True, issues=[])
        self.assertEqual(attrs.to_search_text(), '')
        attrs.sensitive_content = False
        self.assertIn('mochila', attrs.to_search_text())
        attrs.quality = 'insufficient'
        self.assertEqual(attrs.to_search_text(), '')

    def test_unavailable_and_malformed_ollama(self):
        with patch('search.extraction.build_opener') as opener:
            opener.return_value.open.side_effect = OSError('offline')
            with self.assertRaisesRegex(ExtractionError, 'Ollama local'):
                extract_image(self.image, model='test')
        with patch('search.extraction.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'{}'
            with self.assertRaises(ExtractionError):
                extract_image(self.image, model='test')

    def test_batch_resume_and_model_change(self):
        inventory = Inventory(self.root / 'inventory.json')
        source = self.root / 'objects.json'
        source.write_text('[{"id":"one","description":"bag","image":"object.png"},'
                          '{"id":"two","description":"manual"}]')
        inventory.import_file(source)
        from search.pipeline import extraction_key
        def fake_extract(image_path, *, model, digest, timeout):
            key, _ = extraction_key(image_path, digest)
            return {'key': key, 'model_digest': digest, 'result': {'elapsed_seconds': 1}}
        with patch('search.pipeline.model_digest', return_value='digest-1'), \
             patch('search.pipeline.extract_version', side_effect=fake_extract) as call:
            first = extract_batch(inventory, model='local')
            self.assertEqual(first['extracted'], ['one'])
            self.assertIn('two', first['failed'])
            second = extract_batch(Inventory(inventory.path), model='local')
            self.assertEqual(second['cached'], ['one'])
            self.assertEqual(call.call_count, 1)
        with patch('search.pipeline.model_digest', return_value='digest-2'), \
             patch('search.pipeline.extract_version', side_effect=fake_extract):
            extract_batch(inventory, model='local')
        self.assertEqual(len(Inventory(inventory.path).get('one')['extractions']), 2)
        self.assertEqual(inventory.objects(), [])

    def test_model_change_during_inference_rejected(self):
        from search.pipeline import extraction_key
        _, image_hash = extraction_key(self.image, 'before')
        with patch('search.pipeline.extract_image') as extraction, \
             patch('search.pipeline.model_digest', return_value='after'):
            extraction.return_value.image_sha256 = image_hash
            with self.assertRaisesRegex(ValueError, 'changed'):
                extract_version(self.image, model='local', digest='before')

@unittest.skipIf(Image is None, 'Optional extraction dependencies are not installed')
class ModelDefaultsTests(unittest.TestCase):
    def test_qwen_default_and_explicit_model_override(self):
        import json
        from search.settings import DEFAULT_MODEL, DEFAULT_TIMEOUT
        attributes = dict(category='mochila', colors=['negro'], material=None, brand=None,
                          distinctive_features=['cordón frontal'], quality='usable',
                          sensitive_content=False, issues=[])
        payload = json.dumps({'done': True, 'done_reason': 'stop',
                              'message': {'content': json.dumps(attributes)}}).encode()
        for override in (None, 'gemma3:4b'):
            with self.subTest(model=override), \
                 patch('search.extraction._prepare_image', return_value=('image-base64', 'hash')), \
                 patch('search.extraction.build_opener') as opener:
                opener.return_value.open.return_value.__enter__.return_value.read.return_value = payload
                result = extract_image('unused.jpg', **({'model': override} if override else {}))
                request = opener.return_value.open.call_args.args[0]
                sent = json.loads(request.data)
                self.assertEqual(sent['model'], override or DEFAULT_MODEL)
                self.assertEqual(result.model, override or DEFAULT_MODEL)
                self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], DEFAULT_TIMEOUT)
                self.assertEqual(result.review_status, 'pending')
                self.assertIn('cordón frontal', result.draft_search_text)
                self.assertIn('properties', sent['format'])

    def test_cli_batch_uses_default_without_model_argument(self):
        from search.cli import main
        from search.settings import DEFAULT_MODEL, DEFAULT_TIMEOUT
        import contextlib
        with tempfile.TemporaryDirectory() as folder, patch('search.pipeline.extract_batch') as batch:
            batch.return_value = {'extracted': [], 'cached': [], 'failed': {}, 'keys': {}}
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(['--store', str(Path(folder) / 'inventory.json'), 'extract'])
            self.assertEqual(code, 0)
            self.assertEqual(batch.call_args.kwargs['model'], DEFAULT_MODEL)
            self.assertEqual(batch.call_args.kwargs['timeout'], DEFAULT_TIMEOUT)


if __name__ == '__main__':
    unittest.main()
