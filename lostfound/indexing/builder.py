"""Construcción incremental de un índice de imágenes por objeto."""
import hashlib
from pathlib import Path

from ..data.image_store import image_path
from ..imaging.encoder import ImageTextEncoder
from .store import index_signature, load_index, save_index


def build_index(objects, manifest_path, destination, encoder: ImageTextEncoder):
    destination = Path(destination)
    old = load_index(destination) if destination.exists() else {}
    signature = index_signature(encoder)
    reusable = old.get('signature') == signature
    cached = {r['sha256']: r for r in old.get('images', [])} if reusable else {}
    records, errors = [], []
    for obj in objects:
        for relative in obj.get('images', []):
            try:
                path = image_path(manifest_path, relative)
                if path.stat().st_size > 20 * 1024 * 1024:
                    raise ValueError('Imagen superior a 20 MB')
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest in cached:
                    vector, quality = cached[digest]['vector'], cached[digest]['quality']
                else:
                    vector, quality = encoder.image(path)
                    cached[digest] = {'vector': vector, 'quality': quality}
                records.append({'object_id': obj['id'], 'path': relative,
                                'sha256': digest, 'vector': vector, 'quality': quality})
            except (ValueError, OSError) as exc:
                errors.append({'object_id': obj['id'], 'path': relative, 'error': str(exc)})
    result = {'signature': signature, 'images': records, 'errors': errors}
    save_index(destination, result)
    return {'indexed_images': len(records), 'errors': errors, 'signature': signature}
