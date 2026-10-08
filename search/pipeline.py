"""Optional extraction integration; imported only by photo commands."""
import hashlib
import json
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from .settings import DEFAULT_MODEL, DEFAULT_TIMEOUT
from .extraction import extract_image, PROMPT_VERSION, PREPROCESS_VERSION, MAX_BYTES


def model_digest(model):
    request = Request('http://127.0.0.1:11434/api/tags')
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=10) as response:
            payload = json.loads(response.read(1_000_001))
        names = {model, model + ':latest'}
        for entry in payload['models']:
            if entry.get('name') in names or entry.get('model') in names:
                if entry.get('digest'):
                    return entry['digest']
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError('Cannot resolve local Ollama model digest; check the service') from exc
    raise ValueError(f'Local Ollama model not found: {model}')


def extraction_key(image_path, digest):
    with Path(image_path).open('rb') as handle:
        raw = handle.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('Image must contain 1 byte to 20 MiB')
    image_hash = hashlib.sha256(raw).hexdigest()
    identity = [image_hash, digest, PROMPT_VERSION, PREPROCESS_VERSION]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest(), image_hash


def extract_version(image_path, *, model, digest, source='operator', timeout=DEFAULT_TIMEOUT):
    key, image_hash = extraction_key(image_path, digest)
    result = extract_image(image_path, model=model, source=source, timeout=timeout)
    if result.image_sha256 != image_hash or model_digest(model) != digest:
        raise ValueError('Image or model changed during extraction; retry')
    return {'key': key, 'model_digest': digest, 'result': result.model_dump()}


def extract_batch(inventory, *, model=DEFAULT_MODEL, object_ids=None, timeout=DEFAULT_TIMEOUT):
    digest = model_digest(model)
    report = {'extracted': [], 'cached': [], 'failed': {}, 'keys': {}}
    for object_id in object_ids if object_ids is not None else inventory.data['objects']:
        record = inventory.get(object_id)
        try:
            if not record['image_path']:
                raise ValueError('No image; enter a manual review description')
            key, _ = extraction_key(record['image_path'], digest)
            if any(entry['key'] == key for entry in record['extractions']):
                report['cached'].append(object_id)
                report['keys'][object_id] = key
                continue
            extraction = extract_version(record['image_path'], model=model,
                                         digest=digest, timeout=timeout)
            record['extractions'].append(extraction)
            inventory.save()  # Checkpoint each image so an interrupted batch can resume.
            report['extracted'].append(object_id)
            report['keys'][object_id] = extraction['key']
        except (ValueError, OSError, RuntimeError) as exc:
            report['failed'][object_id] = str(exc)
    return report
