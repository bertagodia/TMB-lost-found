"""Preparación local de imágenes. No escribe copias ni conserva EXIF en la salida."""
from pathlib import Path
import warnings

from .quality import assess_quality


def prepare_image(path):
    from PIL import Image, ImageOps, UnidentifiedImageError
    path = Path(path)
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('Imagen superior al límite experimental de 20 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValueError('Solo se admiten JPEG, PNG y WEBP')
                if source.width * source.height > 20_000_000:
                    raise ValueError('Imagen superior a 20 megapíxeles')
                source.load()
                oriented = ImageOps.exif_transpose(source)
                rgba = oriented.convert('RGBA')
                background = Image.new('RGBA', rgba.size, 'white')
                converted = Image.alpha_composite(background, rgba).convert('RGB')
                # A new image deliberately omits source metadata.
                clean = Image.new('RGB', converted.size)
                clean.paste(converted)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError('Imagen dañada, ilegible o excesivamente grande') from exc
    return clean, assess_quality(clean)
