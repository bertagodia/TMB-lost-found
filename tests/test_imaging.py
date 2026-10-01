import importlib.util
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow no instalado')
class ImageTests(unittest.TestCase):
    def test_orientation_metadata_quality_and_corrupt_file(self):
        from PIL import Image
        from lostfound.imaging.preprocessing import prepare_image
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'image.jpg'
            source = Image.new('RGB', (40, 80), 'red')
            exif = Image.Exif()
            exif[274] = 6
            exif[315] = 'Private name'
            source.save(path, exif=exif)
            image, report = prepare_image(path)
            self.assertEqual(image.size, (80, 40))
            self.assertFalse(image.getexif())
            self.assertTrue(report['warnings'])
            path.write_bytes(b'invalid file')
            with self.assertRaises(ValueError):
                prepare_image(path)
