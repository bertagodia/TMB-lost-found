"""Versioned local prototype storage. One writer at a time; no database required."""
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile

from .models import FoundObject

SCHEMA_VERSION = 1


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.tmp-', delete=False) as handle:
            temporary = handle.name
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def found_object(record, description):
    metadata = dict(record['metadata'])
    if metadata.get('found_date') is not None:
        metadata['found_date'] = date.fromisoformat(metadata['found_date'])
    return FoundObject(id=record['id'], description=description, **metadata)


class Inventory:
    def __init__(self, path):
        self.path = Path(path)
        self.data = (json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists()
                     else {'schema_version': SCHEMA_VERSION, 'objects': {}})
        if self.data.get('schema_version') != SCHEMA_VERSION:
            raise ValueError('Unsupported inventory schema version')
        if not isinstance(self.data.get('objects'), dict):
            raise ValueError('Inventory objects must be a mapping')

    def save(self):
        write_json(self.path, self.data)

    def get(self, object_id):
        if object_id not in self.data['objects']:
            raise ValueError(f'Unknown object: {object_id}')
        return self.data['objects'][object_id]

    def add_object(self, object_id, *, description='', image_path=None, metadata=None):
        """Add an unreviewed local object without overwriting an existing record."""
        if object_id in self.data['objects']:
            raise ValueError(f'Duplicate object ID: {object_id}')
        record = {
            'id': object_id, 'original_description': description,
            'image_path': str(Path(image_path).resolve()) if image_path else None,
            'metadata': {**{'found_date': None, 'found_line': None,
                            'found_direction': None, 'date_quality': 'unknown'},
                         **(metadata or {})},
            'import_source': 'local-programmatic', 'imported_at': utc_now(),
            'extractions': [], 'reviews': [],
        }
        found_object(record, description)
        self.data['objects'][object_id] = record
        self.save()
        return record

    def import_file(self, path):
        path = Path(path).resolve()
        rows = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(rows, list):
            raise ValueError('Import must be a JSON array')
        additions = {}
        for row in rows:
            object_id = row['id']
            if object_id in additions or object_id in self.data['objects']:
                raise ValueError(f'Duplicate object ID: {object_id}; import does not overwrite')
            record = {
                'id': object_id, 'original_description': row.get('description', ''),
                'image_path': str((path.parent / row['image']).resolve()) if row.get('image') else None,
                'metadata': {key: row.get(key, default) for key, default in (
                    ('found_date', None), ('found_line', None), ('found_direction', None),
                    ('date_quality', 'unknown'))},
                'import_source': str(path), 'imported_at': utc_now(),
                'extractions': [], 'reviews': [],
            }
            found_object(record, record['original_description'])
            additions[object_id] = record
        self.data['objects'].update(additions)
        self.save()
        return len(additions)

    def review(self, object_id, *, text, status, reviewer, source, extraction_key=None,
               elapsed_seconds=None):
        record = self.get(object_id)
        if status not in {'approved', 'rejected'} or source not in {'manual', 'extraction'}:
            raise ValueError('Invalid review status or source')
        if not reviewer.strip() or (status == 'approved' and not text.strip()):
            raise ValueError('Reviewer and approved text must be nonempty')
        if source == 'extraction' and not any(x['key'] == extraction_key for x in record['extractions']):
            raise ValueError('An extraction review must reference an existing extraction key')
        if elapsed_seconds is not None and (not math.isfinite(elapsed_seconds) or elapsed_seconds < 0):
            raise ValueError('Review duration must be finite and nonnegative')
        record['reviews'].append({
            'status': status, 'text': text.strip(), 'reviewer': reviewer.strip(),
            'source': source, 'extraction_key': extraction_key, 'created_at': utc_now(),
            'elapsed_seconds': elapsed_seconds,
        })
        self.save()

    def objects(self, variant='reviewed'):
        if variant not in {'manual', 'reviewed', 'extraction'}:
            raise ValueError('Unknown inventory text variant')
        result = []
        for record in self.data['objects'].values():
            if variant == 'manual':
                text = record['original_description']
            else:
                reviews = record['reviews']
                if variant == 'extraction':
                    reviews = [r for r in reviews if r['source'] == 'extraction']
                if not reviews or reviews[-1]['status'] != 'approved':
                    continue
                # A later rejection removes the object from every reviewed index.
                if record['reviews'][-1]['status'] == 'rejected':
                    continue
                text = reviews[-1]['text']
            result.append(found_object(record, text))
        return result
