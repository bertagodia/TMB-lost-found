"""Resolución segura de rutas relativas al manifiesto."""
from pathlib import Path


def image_path(manifest_path, relative):
    root = Path(manifest_path).resolve().parent
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Las imágenes deben estar dentro del directorio del manifiesto')
    return path
