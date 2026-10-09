"""Small PostgreSQL repository; file validation/storage stays in the HTTP backend."""
import hashlib
import json
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class ConflictError(ValueError):
    """An existing ID was submitted with different content or an owned photo."""


METADATA = {'client_registered_at', 'registered_line', 'registered_vehicle', 'vehicle_source',
            'found_date', 'date_quality', 'found_line', 'found_direction', 'found_location', 'received_at'}


def reviewed_fields(details):
    if set(details) != {'colors', 'objectType', 'material', 'description'}:
        raise ValueError('Expected colors, objectType, material and description')
    colors = details['colors']
    if not isinstance(colors, list) or any(not isinstance(c, str) or not c.strip() for c in colors):
        raise ValueError('Colors must be a list of nonempty strings')
    if not isinstance(details['description'], str) or len(details['description']) > 250:
        raise ValueError('Description must contain at most 250 characters')
    if any(details[k] is not None and (not isinstance(details[k], str) or not details[k].strip())
           for k in ('objectType', 'material')):
        raise ValueError('Unknown type/material must be null, not an empty value')
    return {**details, 'colors': list(dict.fromkeys(colors))}


def _review(conn, object_id, details, *, status='approved', extraction_id=None,
            reviewer_ref=None, review_seconds=None):
    fields = reviewed_fields(details)
    text = '. '.join(part for part in (fields['objectType'], ', '.join(fields['colors']),
                                      fields['material'], fields['description'].strip()) if part)
    return conn.execute('''INSERT INTO tmb.object_reviews
        (id, object_id, status, source, extraction_id, object_type, material,
         colors, description, search_text, reviewer_ref, review_seconds)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
        (str(uuid4()), object_id, status, 'extraction' if extraction_id else 'manual', extraction_id,
         fields['objectType'], fields['material'], fields['colors'], fields['description'],
         text if status == 'approved' else '', reviewer_ref, review_seconds)).fetchone()


class Repository:
    def __init__(self, dsn):
        self.dsn = dsn

    def connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def create_photo(self, *, storage_key, image_sha256, media_type, size_bytes, width, height,
                     position, original_filename=None, client_selected_at=None):
        """Stage verified file metadata before extraction; no object is created yet."""
        with self.connect() as conn:
            return conn.execute('''INSERT INTO tmb.photos
                (id,storage_key,image_sha256,media_type,size_bytes,width,height,position,
                 original_filename,client_selected_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *''', (str(uuid4()),storage_key,image_sha256,media_type,size_bytes,width,height,
                                position,original_filename,client_selected_at)).fetchone()

    def start_extraction(self, photo_id, *, model_name, model_digest=None,
                         prompt_version=None, preprocessing_version=None, cache_key=None,
                         input_config=None, source='operator'):
        with self.connect() as conn:
            row = conn.execute('''INSERT INTO tmb.extraction_runs
                (id,photo_id,input_image_sha256,model_name,model_digest,prompt_version,
                 preprocessing_version,cache_key,input_config,source)
                SELECT %s,id,image_sha256,%s,%s,%s,%s,%s,%s,%s FROM tmb.photos WHERE id=%s
                RETURNING *''', (str(uuid4()),model_name,model_digest,prompt_version,preprocessing_version,
                                cache_key,Jsonb(input_config or {}),source,photo_id)).fetchone()
            if row is None:
                raise KeyError(photo_id)
            return row

    def complete_extraction(self, extraction_id, *, raw_output, proposed_fields, quality,
                            sensitive_content, warnings=None, timings=None):
        with self.connect() as conn:
            row = conn.execute('''UPDATE tmb.extraction_runs SET status='succeeded',
                raw_output=%s,proposed_fields=%s,quality=%s,sensitive_content=%s,warnings=%s,
                timings=%s,completed_at=clock_timestamp() WHERE id=%s AND status='pending' RETURNING *''',
                (Jsonb(raw_output),Jsonb(proposed_fields),quality,sensitive_content,
                 Jsonb(warnings or []),Jsonb(timings or {}),extraction_id)).fetchone()
            if row is None:
                raise ConflictError('Extraction missing or already completed')
            return row

    def fail_extraction(self, extraction_id, error_message):
        with self.connect() as conn:
            row = conn.execute('''UPDATE tmb.extraction_runs SET status='failed',error_message=%s,
                completed_at=clock_timestamp() WHERE id=%s AND status='pending' RETURNING *''',
                (error_message,extraction_id)).fetchone()
            if row is None:
                raise ConflictError('Extraction missing or already completed')
            return row

    def register_object(self, object_id, *, photo_ids, details, reviewed, extraction_id=None, **metadata):
        """Atomically adopt staged photos and append the first approved review.

        Same normalized submission is idempotent even after later reviews/status changes.
        This contract accepts staged photo IDs, not data URLs from an HTTP request.
        """
        if reviewed is not True:
            raise ValueError('Explicit review confirmation is required')
        if not isinstance(photo_ids, list) or len(photo_ids) != len(set(photo_ids)):
            raise ValueError('photo_ids must be an ordered list of distinct IDs')
        if metadata.keys() - METADATA:
            raise ValueError('Unknown object metadata')
        fields = reviewed_fields(details)
        # Omitted and explicit null optional metadata have the same normalized meaning.
        metadata = {key: metadata.get(key) for key in sorted(METADATA)}
        metadata['date_quality'] = metadata['date_quality'] or 'unknown'
        with self.connect() as conn:
            # Consistent lock order avoids photo-adoption deadlocks across objects.
            photos = conn.execute('SELECT * FROM tmb.photos WHERE id = ANY(%s) ORDER BY id FOR UPDATE',
                                  (photo_ids,)).fetchall()
            by_id = {photo['id']:photo for photo in photos}
            if set(by_id) != set(photo_ids):
                raise ValueError('Unknown staged photo')
            if [by_id[id]['position'] for id in photo_ids] != list(range(1,len(photo_ids)+1)):
                raise ValueError('Photos must be supplied in their consecutive positions')
            submission = dict(details=fields, metadata=metadata, extraction_id=extraction_id,
                              photos=[by_id[id]['image_sha256'] for id in photo_ids])
            digest = hashlib.sha256(json.dumps(submission,sort_keys=True,ensure_ascii=False,
                                               default=str,separators=(',',':')).encode()).hexdigest()
            columns = ['id','original_details','submission_hash',*metadata]
            query = sql.SQL('INSERT INTO tmb.found_objects ({}) VALUES ({}) ON CONFLICT (id) DO NOTHING RETURNING id').format(
                sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder()*len(columns)))
            inserted = conn.execute(query,(object_id,Jsonb(fields),digest,*metadata.values())).fetchone()
            obj = conn.execute('SELECT * FROM tmb.found_objects WHERE id=%s FOR UPDATE',(object_id,)).fetchone()
            if not inserted:
                if obj['submission_hash'] != digest:
                    raise ConflictError('Object ID already exists with a different submission')
                return {**obj,'duplicate':True}
            if any(photo['object_id'] is not None for photo in photos):
                raise ConflictError('Photo already belongs to another object; stage a new reference')
            conn.execute('UPDATE tmb.photos SET object_id=%s WHERE id=ANY(%s)',(object_id,photo_ids))
            _review(conn,object_id,fields,extraction_id=extraction_id)
            return {**obj,'duplicate':False}

    def add_review(self, object_id, details, **options):
        with self.connect() as conn:
            return _review(conn,object_id,details,**options)

    def set_status(self, object_id, status):
        with self.connect() as conn:
            row = conn.execute('UPDATE tmb.found_objects SET status=%s WHERE id=%s RETURNING *',
                               (status,object_id)).fetchone()
            if row is None:
                raise KeyError(object_id)
            return row

    def get_object(self, object_id):
        with self.connect() as conn:
            # One snapshot for the object and its history, even under concurrent reviews.
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            obj = conn.execute('SELECT * FROM tmb.found_objects WHERE id=%s',(object_id,)).fetchone()
            if obj is None:
                return None
            obj['photos'] = conn.execute('SELECT * FROM tmb.photos WHERE object_id=%s ORDER BY position',(object_id,)).fetchall()
            obj['reviews'] = conn.execute('SELECT * FROM tmb.object_reviews WHERE object_id=%s ORDER BY revision',(object_id,)).fetchall()
            return obj

    def searchable_objects(self):
        """One consistent inventory snapshot for rebuilding the prototype BM25 index."""
        with self.connect() as conn:
            return conn.execute('SELECT * FROM tmb.searchable_objects ORDER BY id').fetchall()
