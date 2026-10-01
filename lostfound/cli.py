import argparse
import json
from pathlib import Path

from .config import DEMO_OBJECTS, DEMO_QUERIES, DEFAULT_INDEX, load_search_config
from .data.loader import load_objects
from .search import SearchEngine


def main():
    parser = argparse.ArgumentParser(description='Laboratorio de búsqueda de objetos perdidos')
    parser.add_argument('--data', type=Path, default=DEMO_OBJECTS)
    parser.add_argument('--config', type=Path, help='Configuración TOML para search/evaluate')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve', help='Formulario local de búsqueda textual')
    serve.add_argument('--port', type=int, default=8000)
    search = sub.add_parser('search')
    search.add_argument('description')
    search.add_argument('--date', default='')
    search.add_argument('--line', default='')
    search.add_argument('--direction', default='')
    search.add_argument('--date-approximate', action='store_true')
    search.add_argument('--mode', choices=['text', 'visual', 'hybrid'])
    search.add_argument('--index', type=Path, default=DEFAULT_INDEX)
    search.add_argument('--query-image', type=Path)
    search.add_argument('--image-only', action='store_true', help='Consulta visual usando solo la imagen')
    evaluation = sub.add_parser('evaluate')
    evaluation.add_argument('--queries', type=Path, default=DEMO_QUERIES)
    for command in (search, evaluation):
        command.add_argument('--policy', choices=['soft', 'strict'])
        command.add_argument('--window', type=int)
        command.add_argument('--k', type=int)
        command.add_argument('--min-score', type=float)
    index = sub.add_parser('index')
    index.add_argument('--output', type=Path, default=DEFAULT_INDEX)
    index.add_argument('--revision', default='main', help='Revisión o hash del modelo')
    args = parser.parse_args()
    try:
        if args.command in ('search', 'evaluate'):
            for key, value in load_search_config(args.config).items():
                if getattr(args, key, None) is None:
                    setattr(args, key, value)
            if args.command == 'evaluate' and args.mode != 'text':
                raise ValueError('El evaluador por lotes actual solo admite modalidad text')
        elif args.config:
            raise ValueError('--config solo se aplica a search y evaluate')
        objects = load_objects(args.data)
        engine = SearchEngine(objects)
        if args.command == 'serve':
            from .api.server import serve
            serve(engine, args.port)
            return
        if args.command == 'index':
            if not any(o.get('images') for o in objects):
                raise ValueError('El inventario no contiene imágenes. Añade fotografías antes de descargar el modelo.')
            from .imaging.siglip import SiglipEncoder
            from .indexing.builder import build_index
            result = build_index(objects, args.data, args.output, SiglipEncoder(revision=args.revision))
        elif args.command == 'evaluate':
            from .evaluation.runner import evaluate
            result = evaluate(engine, json.loads(args.queries.read_text()), args.policy,
                              args.window, args.k, args.min_score)
        else:
            scores = None
            if args.mode == 'text' and (args.query_image or args.image_only):
                raise ValueError('Selecciona --mode visual o hybrid para utilizar una imagen')
            if args.image_only and (not args.query_image or args.mode != 'visual'):
                raise ValueError('--image-only requiere --query-image y --mode visual')
            if args.mode != 'text':
                from .imaging.siglip import SiglipEncoder
                from .search.visual import visual_scores
                index = json.loads(args.index.read_text())
                encoder = SiglipEncoder(index['signature']['model'], index['signature']['revision'])
                scores = visual_scores(index, '' if args.image_only else args.description,
                                       encoder, args.query_image)
            result = engine.search(vars(args), args.policy, args.window, args.k,
                                   args.min_score, scores, args.mode)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f'Error: {exc}\n')
