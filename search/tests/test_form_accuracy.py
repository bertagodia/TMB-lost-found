import argparse
import contextlib
import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from PIL import Image
    from search.accuracy import score, summarize, run
    from search.extraction import _prepare_image
    from search.form_extraction import Recognition, map_category, map_recognition, extract_form
except ImportError:
    Image = None


@unittest.skipIf(Image is None, 'Optional extraction dependencies are not installed')
class RecognitionTests(unittest.TestCase):
    def draft(self, **changes):
        values = dict(object_name='water bottle', visible_features=['Metal body', 'Black flip cap'],
                      colors=['silver', 'gray', 'orange', 'black'], material='metal',
                      quality='usable', sensitive_content=False)
        return Recognition.model_validate_json(json.dumps({**values, **changes}))

    def test_mapping_preserves_unknown_name_and_deduplicates_colors(self):
        fields, warnings = map_recognition(self.draft())
        self.assertEqual(fields['objectType'], 'Ampolla')
        self.assertEqual(fields['colors'], ['Gris', 'Taronja', 'Negre'])
        self.assertEqual(fields['material'], 'Metall')
        self.assertEqual(warnings, [])
        fields, warnings = map_recognition(self.draft(object_name='electric kettle'))
        self.assertEqual(fields['objectType'], 'Altres')
        self.assertTrue(fields['description'].startswith('electric kettle'))
        self.assertTrue(warnings)
        self.assertEqual(map_category('folding umbrella'), 'Paraigua')
        self.assertEqual(map_category('coin purse'), 'Cartera')
        self.assertEqual(map_category('bottle opener'), 'Altres')
        self.assertEqual(map_category('keyboard'), 'Altres')

    def test_unknowns_and_material_conflict_flagged_without_false_cap_conflict(self):
        fields, warnings = map_recognition(self.draft(material='textile'))
        self.assertIsNone(fields['material'])
        self.assertTrue(any('conflicts' in warning for warning in warnings))
        fields, warnings = map_recognition(self.draft(visible_features=['Plastic cap', 'Metal body']))
        self.assertEqual(fields['material'], 'Metall')
        self.assertFalse(warnings)
        fields, warnings = map_recognition(self.draft(object_name=None, material=None, colors=[]))
        self.assertIsNone(fields['objectType'])
        self.assertIsNone(fields['material'])
        self.assertEqual(len(warnings), 3)

    def test_generic_feature_headings_omitted(self):
        fields, warnings = map_recognition(self.draft(visible_features=['shape', 'closure', 'pattern']))
        self.assertEqual(fields['description'], 'water bottle')
        self.assertTrue(warnings)

    def test_unusable_and_sensitive_do_not_expose_recognized_name(self):
        for changes in ({'quality':'ambiguous'}, {'sensitive_content':True}):
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'image.png'
                Image.new('RGB',(20,20)).save(path)
                with patch('search.form_extraction.request_json',return_value=self.draft(**changes).model_dump_json()):
                    result=extract_form(path)
            self.assertIsNone(result['recognized_object'])
            self.assertEqual(result['fields'],dict(colors=[],objectType=None,material=None,description=''))

    def test_crop_uses_oriented_coordinates_and_original_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'image.png'
            image=Image.new('RGB',(100,50),'blue')
            image.paste('red',(0,0,50,50))
            image.save(path)
            _, original_hash=_prepare_image(path)
            encoded, crop_hash=_prepare_image(path,crop=[0,0,.5,1])
            self.assertEqual(original_hash,crop_hash)
            with Image.open(io.BytesIO(base64.b64decode(encoded))) as cropped:
                self.assertEqual(cropped.size,(50,50))
                self.assertGreater(cropped.getpixel((20,20))[0],240)
            for crop in ([0,0,0,1],[-.1,0,1,1],[0,0,1,2],[0,0,float('nan'),1]):
                with self.assertRaises(ValueError):
                    _prepare_image(path,crop=crop)
            exif=Image.Exif();exif[274]=6
            image.save(path,exif=exif)
            encoded,_=_prepare_image(path,crop=[0,0,1,.5])
            with Image.open(io.BytesIO(base64.b64decode(encoded))) as cropped:
                self.assertEqual(cropped.size,(50,50))
                self.assertGreater(cropped.getpixel((20,20))[0],240)


@unittest.skipIf(Image is None, 'Optional extraction dependencies are not installed')
class AccuracyTests(unittest.TestCase):
    def test_metrics_count_errors_and_optional_colors_honestly(self):
        case={'expected':dict(objectType='Ampolla',required_colors=['Gris','Taronja'],
                              allowed_colors=['Gris','Taronja','Negre'],name_pattern='bottle',material='Metall')}
        good={'recognized_object':'water bottle','fields':dict(objectType='Ampolla',colors=['Gris','Negre'],material='Metall')}
        scores=score(case,good)
        self.assertEqual(scores['color_hits'],1)
        self.assertEqual(scores['color_allowed_hits'],2)
        rows=[dict(model='test',variant='current',view='full',object_id='bottle',seconds=1,scores=scores),
              dict(model='test',variant='current',view='full',object_id='bottle',seconds=3,scores=score(case,{}),error='timeout')]
        summary=summarize(rows)[0]
        self.assertEqual(summary['category_accuracy'],.5)
        self.assertEqual(summary['color_recall'],.25)
        self.assertEqual(summary['errors'],1)
        self.assertEqual(summary['distinct_objects'],1)
        self.assertEqual(summary['unsupported_details_reviewed'],0)


    def test_runner_resumes_by_image_model_and_crop_without_sending_labels(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            photo=root/'photo.png'
            Image.new('RGB',(20,20),'orange').save(photo)
            case=dict(id='one',image='photo.png',image_sha256=hashlib.sha256(photo.read_bytes()).hexdigest(),
                      crop=[0,0,.5,1],expected=dict(objectType='Ampolla',required_colors=['Taronja'],name_pattern='bottle'))
            manifest=root/'manifest.json'
            manifest.write_text(json.dumps(dict(label_status='test',cases=[case])))
            args=argparse.Namespace(manifest=manifest,ids=None,images=root,personal=None,
                                   output=root/'report',reviews=None,models=['test'],variants=['current'],
                                   views=['full','crop'],timeout=5)
            result=dict(recognized_object='bottle',fields=dict(objectType='Ampolla',colors=['Taronja'],material=None))
            with patch('search.accuracy.model_digest',return_value='digest'), \
                 patch('search.accuracy.extract_form',return_value=result) as extract, \
                 contextlib.redirect_stdout(io.StringIO()):
                run(args)
                run(args)
                self.assertEqual(extract.call_count,2)
                self.assertEqual(extract.call_args_list[0].kwargs,dict(model='test',crop=None,timeout=5))
                self.assertEqual(extract.call_args_list[1].kwargs['crop'],[0,0,.5,1])
            report=json.loads((args.output/'report.json').read_text())
            self.assertEqual(len(report['rows']),2)
            self.assertNotEqual(report['rows'][0]['run_key'],report['rows'][1]['run_key'])
            case['image_sha256']='wrong'
            manifest.write_text(json.dumps(dict(label_status='test',cases=[case])))
            with patch('search.accuracy.model_digest') as model:
                with self.assertRaisesRegex(ValueError,'Source image changed'):
                    run(args)
                model.assert_not_called()


if __name__=='__main__':
    unittest.main()
