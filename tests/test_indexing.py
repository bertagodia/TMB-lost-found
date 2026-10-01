import json
from pathlib import Path
import tempfile
import unittest

from lostfound.indexing.store import PREPROCESS_VERSION
from lostfound.indexing.builder import build_index
from lostfound.data.image_store import image_path
from lostfound.search.visual import visual_scores


class FakeEncoder:
    model_id = 'test-encoder'
    revision = 'test-revision'

    def __init__(self):
        self.calls = 0

    def image(self, path):
        self.calls += 1
        return [1.0, 0.0], {'warnings': []}

    def text(self, text):
        return [1.0, 0.0]


class IndexTests(unittest.TestCase):
    def test_cache_invalidation_multiple_photos_and_removed_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'photo.png').write_bytes(b'fixture, fake encoder only')
            objects = [{'id': 'a', 'images': ['photo.png', 'photo.png']}]
            encoder = FakeEncoder()
            path = root / 'index.json'
            build_index(objects, root / 'objects.json', path, encoder)
            build_index(objects, root / 'objects.json', path, encoder)
            self.assertEqual(encoder.calls, 1)
            index = json.loads(path.read_text())
            self.assertEqual(visual_scores(index, 'bag', encoder), {'a': 1.0})
            (root / 'photo.png').write_bytes(b'changed')
            build_index(objects, root / 'objects.json', path, encoder)
            self.assertEqual(encoder.calls, 2)
            build_index([], root / 'objects.json', path, encoder)
            self.assertEqual(json.loads(path.read_text())['images'], [])

    def test_reject_path_escape(self):
        with self.assertRaises(ValueError):
            image_path('/tmp/example/objects.json', '../outside.jpg')

    def test_reject_incompatible_model(self):
        index = {'signature': {'model': 'other', 'revision': 'x',
                               'preprocess_version': PREPROCESS_VERSION}, 'images': []}
        with self.assertRaises(ValueError):
            visual_scores(index, 'bag', FakeEncoder())
