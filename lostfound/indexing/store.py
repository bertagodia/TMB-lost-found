"""Persistencia atómica y firma del índice visual."""
import json
from pathlib import Path

PREPROCESS_VERSION = 1


def index_signature(encoder):
    return {"model": encoder.model_id, "revision": encoder.revision,
            "preprocess_version": PREPROCESS_VERSION}


def load_index(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_index(path, index):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
