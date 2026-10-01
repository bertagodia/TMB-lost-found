import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lostfound.cli import main
from lostfound.config import load_search_config


class ConfigTests(unittest.TestCase):
    def test_cli_overrides_toml(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'experiment.toml'
            config.write_text('[search]\npolicy = "strict"\nk = 1\n')
            output = io.StringIO()
            with patch('sys.argv', ['lostfound', '--config', str(config), 'search',
                                    'mochila negra', '--policy', 'soft']), contextlib.redirect_stdout(output):
                main()
            response = json.loads(output.getvalue())
            self.assertEqual(response['policy'], 'soft')
            self.assertEqual(len(response['results']), 1)

    def test_reject_unknown_keys_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'experiment.toml'
            for content in ('[search]\nwindows = 2', '[search]\nk = -1', '[search]\nmin_score = nan'):
                config.write_text(content)
                with self.assertRaises(ValueError):
                    load_search_config(config)
