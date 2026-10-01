"""Rutas del laboratorio y configuración explícita de experimentos."""
from pathlib import Path
import sysconfig
import tomllib

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT if (ROOT / 'web/index.html').is_file() else Path(sysconfig.get_path('data')) / 'share/tmb-lost-found'
WEB_DIR = RESOURCES / 'web'
DEMO_OBJECTS = RESOURCES / 'data/demo/objects.json'
DEMO_QUERIES = RESOURCES / 'data/demo/queries.json'
DEFAULT_INDEX = Path('artifacts/visual-index.json')
SEARCH_DEFAULTS = {'policy': 'soft', 'window': 2, 'k': 3, 'min_score': 0.0, 'mode': 'text'}


def load_search_config(path=None):
    settings = dict(SEARCH_DEFAULTS)
    if path is None:
        return settings
    with Path(path).open('rb') as handle:
        document = tomllib.load(handle)
    if set(document) - {'search'}:
        raise ValueError('La configuración solo admite la sección [search]')
    values = document.get('search', {})
    if not isinstance(values, dict) or set(values) - set(settings):
        raise ValueError('Configuración de búsqueda desconocida')
    settings.update(values)
    if settings['policy'] not in ('soft', 'strict') or settings['mode'] not in ('text', 'visual', 'hybrid'):
        raise ValueError('Modalidad o política de configuración desconocida')
    if type(settings['window']) is not int or not 0 <= settings['window'] <= 365:
        raise ValueError('window debe ser un entero entre 0 y 365')
    if type(settings['k']) is not int or not 1 <= settings['k'] <= 100:
        raise ValueError('k debe ser un entero entre 1 y 100')
    if type(settings['min_score']) not in (int, float) or not -1 <= settings['min_score'] <= 1:
        raise ValueError('min_score debe ser un número entre -1 y 1')
    return settings
