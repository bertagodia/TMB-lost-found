"""Interfaz para reemplazar el modelo sin cambiar indexación o búsqueda."""
from pathlib import Path
from typing import Protocol

from ..schemas import ImageQuality


class ImageTextEncoder(Protocol):
    model_id: str
    revision: str

    def text(self, text: str) -> list[float]: ...

    def image(self, path: str | Path) -> tuple[list[float], ImageQuality]: ...
