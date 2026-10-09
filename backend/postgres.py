"""Local prototype: validated files, PostgreSQL inventory, reports and BM25 search."""
import base64
from datetime import date, datetime
import hashlib
import json
from uuid import uuid4

from PIL import Image

from database.repository import Repository, ConflictError
from search import FoundObject, SearchEngine, SearchQuery
from search.form_extraction import FormFields, FORM_PROMPT_VERSION, OPTIONS
from search.extraction import PREPROCESS_VERSION, _prepare_image
from search.pipeline import model_digest
from .server import Application, decode_image


def text(value, limit, *, required=False):
    if value is None and not required:
        return None
    if not isinstance(value,str) or len(value)>limit or (required and not value.strip()):
        raise ValueError('Camp de text invàlid o massa llarg.')
    return value.strip() or None


def timestamp(value):
    if value is None:
        return None
    stamp = datetime.fromisoformat(text(value,80,required=True))
    if stamp.tzinfo is None:
        raise ValueError('La data ha d’incloure zona horària.')
    return stamp.isoformat()


def hash_json(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def fields(value):
    if not isinstance(value,dict):
        raise ValueError('Falten els camps revisats.')
    value = dict(value)
    if 'colors' not in value:
        value['colors'] = [value['color']] if value.get('color') else []
    value.pop('color',None)
    parsed = FormFields.model_validate_json(json.dumps(value)).model_dump(mode='json')
    if not parsed['colors'] or not parsed['objectType'] or not parsed['material']:
        raise ValueError('Revisa colors, tipus i material.')
    return parsed


class PostgresApplication(Application):
    def __init__(self, data_dir, dsn, model):
        super().__init__(data_dir,model)
        self.repo = Repository(dsn)
        (self.data_dir/'photos').mkdir(parents=True,exist_ok=True)

    def stage(self, photo, position):
        raw = decode_image(photo)
        key = f'photos/{uuid4().hex}'
        path = self.data_dir/key
        try:
            path.write_bytes(raw)
            _prepare_image(path)  # Decode and enforce image/size limits, including MPO.
            with Image.open(path) as image:
                width,height = image.size
                media = {'JPEG':'image/jpeg','MPO':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}[image.format]
            return self.repo.create_photo(storage_key=key,image_sha256=hashlib.sha256(raw).hexdigest(),
                media_type=media,size_bytes=len(raw),width=width,height=height,position=position,
                original_filename=text(photo.get('name'),255) if isinstance(photo,dict) else None,
                client_selected_at=timestamp(photo.get('capturedAt')) if isinstance(photo,dict) else None)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def discard_staged(self, ids):
        if not ids:
            return
        with self.repo.connect() as conn:
            removed = conn.execute('''DELETE FROM tmb.photos p WHERE p.id=ANY(%s)
                AND p.object_id IS NULL AND p.report_id IS NULL
                AND NOT EXISTS (SELECT FROM tmb.extraction_runs e WHERE e.photo_id=p.id)
                RETURNING storage_key''',(ids,)).fetchall()
        for photo in removed:
            (self.data_dir/photo['storage_key']).unlink(missing_ok=True)

    def extract(self, payload):
        # The inherited cache stores only model output, never ownership of DB photos.
        photo = self.stage(payload['photo'],1)
        run = None
        try:
            digest = model_digest(self.model)
            cache_key = hashlib.sha256(json.dumps([photo['image_sha256'],digest,FORM_PROMPT_VERSION,PREPROCESS_VERSION]).encode()).hexdigest()
            run = self.repo.start_extraction(photo['id'],model_name=self.model,model_digest=digest,
                prompt_version=FORM_PROMPT_VERSION,preprocessing_version=PREPROCESS_VERSION,cache_key=cache_key)
            result = super().extract(payload)
            if result['model_digest'] != digest:
                raise ValueError('El model ha canviat; torna a extreure la foto.')
            self.repo.complete_extraction(run['id'],raw_output=result['raw_draft'],
                proposed_fields=result['fields'],quality=result['quality'],sensitive_content=result['sensitive_content'],
                warnings=result.get('warnings'),timings=result.get('timings'))
            return {**result,'id':run['id'],'cache_key':result['id']}
        except Exception as exc:
            if run is None:
                run = self.repo.start_extraction(photo['id'],model_name=self.model)
            self.repo.fail_extraction(run['id'],str(exc)[:1000])
            raise

    def submit(self, record):
        object_id = text(record.get('id'),160,required=True)
        if record.get('reviewed') is not True:
            raise ValueError('Confirma la revisió abans de desar.')
        details = fields(record.get('details'))
        photos = record.get('photos')
        if not isinstance(photos,list) or not 1<=len(photos)<=2:
            raise ValueError('Cal enviar una o dues fotografies.')
        hashes = [hashlib.sha256(decode_image(p)).hexdigest() for p in photos]
        vehicle = record.get('vehicle') or {}
        if not isinstance(vehicle,dict):
            raise ValueError('Vehicle invàlid.')
        metadata = dict(client_registered_at=timestamp(record.get('capturedAt')),
            registered_line=text(vehicle.get('line'),100),registered_vehicle=text(vehicle.get('vehicle'),100),
            vehicle_source=vehicle.get('source'))
        if metadata['vehicle_source'] not in (None,'manual','nfc'):
            raise ValueError('Origen del vehicle invàlid.')
        extraction_id = text(record.get('extractionId'),160)
        request_hash = hash_json(dict(details=details,photos=hashes,metadata=metadata,extraction_id=extraction_id))
        staged = []
        try:
            with self.repo.connect() as conn:
                # Per-ID lock across server processes, including an ID that does not exist yet.
                conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(object_id,))
                previous = conn.execute('SELECT request_hash FROM tmb.http_submissions WHERE object_id=%s',(object_id,)).fetchone()
                if previous:
                    if previous['request_hash'] != request_hash:
                        raise ConflictError('Aquest ID ja té un contingut diferent.')
                    return dict(id=object_id,queued=False,status='stored-postgres',duplicate=True)
                linked = None
                if extraction_id:
                    linked = conn.execute('''SELECT e.*,p.object_id,p.report_id FROM tmb.extraction_runs e
                        JOIN tmb.photos p ON p.id=e.photo_id WHERE e.id=%s''',(extraction_id,)).fetchone()
                    if not linked or linked['status']!='succeeded' or linked['input_image_sha256']!=hashes[0]:
                        raise ValueError('L’extracció no correspon a la foto principal. Reextreu-la o continua manualment.')
                for index, photo in enumerate(photos):
                    if index==0 and linked and linked['object_id'] is None and linked['report_id'] is None:
                        staged.append(linked['photo_id'])
                    else:
                        staged.append(self.stage(photo,index+1)['id'])
                # Reusing an extraction's bytes for a different object gets its own attempt.
                attempt_id = extraction_id
                if linked and staged[0]!=linked['photo_id']:
                    clone = self.repo.start_extraction(staged[0],model_name=linked['model_name'],
                        model_digest=linked['model_digest'],prompt_version=linked['prompt_version'],
                        preprocessing_version=linked['preprocessing_version'],cache_key=linked['cache_key'],input_config=linked['input_config'])
                    self.repo.complete_extraction(clone['id'],raw_output=linked['raw_output'],proposed_fields=linked['proposed_fields'],
                        quality=linked['quality'],sensitive_content=linked['sensitive_content'],warnings=linked['warnings'],timings=linked['timings'])
                    attempt_id = clone['id']
                self.repo.register_object(object_id,photo_ids=staged,details=details,reviewed=True,
                    extraction_id=attempt_id,connection=conn,**metadata)
                conn.execute('INSERT INTO tmb.http_submissions(object_id,request_hash) VALUES (%s,%s)',(object_id,request_hash))
            return dict(id=object_id,queued=False,status='stored-postgres',duplicate=False)
        finally:
            self.discard_staged(staged)

    def inventory(self, payload):
        with self.repo.connect() as conn:
            rows = conn.execute('''SELECT o.id,o.status,o.created_at,o.registered_line,o.registered_vehicle,
                r.revision,r.status AS review_status,r.object_type,r.colors,r.material,r.description,
                p.id AS photo_id FROM tmb.found_objects o
                LEFT JOIN LATERAL (SELECT * FROM tmb.object_reviews WHERE object_id=o.id ORDER BY revision DESC LIMIT 1) r ON true
                LEFT JOIN tmb.photos p ON p.object_id=o.id AND p.position=1
                ORDER BY o.created_at DESC LIMIT 200''').fetchall()
        for row in rows:
            row['created_at'] = row['created_at'].isoformat()
        return dict(objects=rows)

    def review(self, payload):
        object_id = text(payload.get('id'),160,required=True)
        if payload.get('reviewed') is not True:
            raise ValueError('Confirma la revisió.')
        # Optimistic check prevents silently overwriting another operator's correction.
        with self.repo.connect() as conn:
            obj = conn.execute('SELECT id FROM tmb.found_objects WHERE id=%s FOR UPDATE',(object_id,)).fetchone()
            current = conn.execute('SELECT max(revision) AS revision FROM tmb.object_reviews WHERE object_id=%s',(object_id,)).fetchone()
            if not obj:
                raise ValueError('Objecte no trobat.')
            if payload.get('revision') != current['revision']:
                raise ConflictError('Hi ha una revisió més nova. Actualitza l’inventari.')
            from database.repository import _review
            result = _review(conn,object_id,fields(payload.get('details')),status=payload.get('status','approved'))
        return dict(id=object_id,revision=result['revision'])

    def status(self, payload):
        self.repo.set_status(text(payload.get('id'),160,required=True),payload.get('status'))
        return dict(id=payload['id'],status=payload['status'])

    def search(self, payload):
        description = text(payload.get('description'),500,required=True)
        filters = payload.get('filters') or {}
        if not isinstance(filters,dict):
            raise ValueError('Filtres invàlids.')
        object_type = filters.get('objectType') or None
        colors = filters.get('colors') or []
        if object_type is not None and object_type not in OPTIONS['objectTypes']:
            raise ValueError('Tipus invàlid.')
        if not isinstance(colors,list) or any(c not in OPTIONS['colors'] for c in colors):
            raise ValueError('Colors invàlids.')
        lost_date = payload.get('lostDate') or None
        if lost_date:
            lost_date = date.fromisoformat(text(lost_date,10,required=True))
        with self.repo.connect() as conn:
            rows = conn.execute('''SELECT s.*,r.object_type,r.colors,r.material,r.description AS reviewed_description,p.id AS photo_id
                FROM tmb.searchable_objects s JOIN tmb.object_reviews r ON r.id=s.review_id
                LEFT JOIN tmb.photos p ON p.object_id=s.id AND p.position=1
                WHERE (%s::text IS NULL OR r.object_type=%s) AND (%s::text[]='{}' OR r.colors @> %s::text[])''',
                (object_type,object_type,colors,colors)).fetchall()
        objects = [FoundObject(**{k:row[k] for k in ('id','description','found_date','date_quality','found_line','found_direction')}) for row in rows]
        query_text = ' '.join([description,object_type or '',*colors])
        matches = SearchEngine(objects).search(SearchQuery(query_text[:2000],lost_date=lost_date),limit=20)
        lookup = {row['id']:row for row in rows}
        results = []
        for candidate in matches.candidates:
            row = lookup[candidate.object_id]
            results.append(dict(id=row['id'],objectType=row['object_type'],colors=row['colors'],material=row['material'],
                description=row['reviewed_description'],photo_url=f"/api/photos/{row['photo_id']}" if row['photo_id'] else None,
                score=round(candidate.text_score,4),signals=list(candidate.signals)))
        return dict(candidates=results,inventory_count=len(rows))

    def lost_report(self, payload):
        report_id = text(payload.get('id'),160,required=True)
        incident = payload.get('incident') or {}
        contact = payload.get('contact') or {}
        if not isinstance(incident,dict) or not isinstance(contact,dict):
            raise ValueError('Declaració invàlida.')
        query = dict(description=text(payload.get('description'),500,required=True),
            filters=payload.get('filters') or {},lostDate=incident.get('lossDate') or None)
        results = self.search(query)  # Validate before storing; query only contains search data.
        contacts = {k:text(contact.get(k),limit) for k,limit in [('name',120),('email',254),('phone',40)]}
        location = text(incident.get('location'),100)
        created = timestamp(payload.get('createdAt'))
        photo = payload.get('referencePhoto')
        image_hash = hashlib.sha256(decode_image(photo)).hexdigest() if photo else None
        digest = hash_json(dict(query=query,contacts=contacts,location=location,created=created,image=image_hash))
        staged = []
        try:
            with self.repo.connect() as conn:
                conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,1))',(report_id,))
                previous = conn.execute('SELECT submission_hash FROM tmb.lost_reports WHERE id=%s',(report_id,)).fetchone()
                if previous:
                    if previous['submission_hash'] != digest:
                        raise ConflictError('La declaració ja existeix amb un contingut diferent.')
                else:
                    if photo:
                        staged.append(self.stage(photo,1)['id'])
                    conn.execute('''INSERT INTO tmb.lost_reports(id,client_created_at,original_description,lost_date,
                        location_text,object_type,colors,submission_hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (report_id,created,query['description'],query['lostDate'],location,
                         query['filters'].get('objectType') or None,query['filters'].get('colors') or [],digest))
                    if any(contacts.values()):
                        conn.execute('INSERT INTO tmb.report_contacts(report_id,name,email,phone) VALUES (%s,%s,%s,%s)',
                                     (report_id,contacts['name'],contacts['email'],contacts['phone']))
                    if staged:
                        conn.execute('UPDATE tmb.photos SET report_id=%s WHERE id=ANY(%s)',(report_id,staged))
            return dict(id=report_id,status='stored-postgres',**results)
        finally:
            self.discard_staged(staged)

    def photo_bytes(self, photo_id):
        with self.repo.connect() as conn:
            photo = conn.execute('''SELECT p.storage_key FROM tmb.photos p
                JOIN tmb.searchable_objects s ON s.id=p.object_id WHERE p.id=%s''',(photo_id,)).fetchone()
        if not photo:
            raise FileNotFoundError('Fotografia no disponible.')
        encoded,_ = _prepare_image(self.data_dir/photo['storage_key'])
        return base64.b64decode(encoded)
