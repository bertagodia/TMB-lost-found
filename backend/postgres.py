"""Local prototype: validated files, PostgreSQL inventory, reports and BM25 search."""
import base64
from datetime import date, datetime
import hashlib
import json
from uuid import uuid4
from pathlib import Path

ORIGINS = json.loads((Path(__file__).resolve().parent.parent/"client/origin-options.json").read_text())

from PIL import Image

from database.repository import Repository, ConflictError
from search import FoundObject, SearchEngine, SearchQuery
from search.form_extraction import FormFields, FORM_PROMPT_VERSION, OPTIONS
from search.extraction import PREPROCESS_VERSION, _prepare_image
from search.pipeline import model_digest
from .server import Application, decode_image
from .transit import finding, transit, calendar_date


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
    if 'colorOrderKnown' not in value:
        parsed.pop('colorOrderKnown', None)  # Preserve legacy retry hashes.
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
        found = finding(record['finding']) if 'finding' in record else None
        if found:
            metadata.update({k:v.isoformat() if isinstance(v,date) else v for k,v in found.items() if k!='found_transport'})
        extraction_id = text(record.get('extractionId'),160)
        request_data = dict(details=details,photos=hashes,metadata=metadata,extraction_id=extraction_id)
        if found is not None:
            request_data['found_transport'] = found['found_transport']
        origin = record.get('origin')
        route = None
        if origin is not None:
            if not isinstance(origin,dict) or origin.get('kind') not in ORIGINS:
                raise ValueError('Origen invàlid.')
            location = text(origin.get('location'),160)
            if location and location not in ORIGINS[origin['kind']]:
                raise ValueError('Ubicació d’origen desconeguda.')
            route = (origin['kind'],location,ORIGINS[origin['kind']].get(location))
            request_data['origin'] = route
        request_hash = hash_json(request_data)
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
                if found is not None:
                    conn.execute('UPDATE tmb.found_objects SET found_transport=%s WHERE id=%s',(found['found_transport'],object_id))
                    self.record_finding(conn,object_id,found)
                if route:
                    conn.execute('INSERT INTO tmb.object_routing(object_id,origin_kind,origin_location,assigned_destination,found_location) VALUES (%s,%s,%s,%s,%s)',(object_id,*route,route[1]))
                conn.execute('INSERT INTO tmb.http_submissions(object_id,request_hash) VALUES (%s,%s)',(object_id,request_hash))
            return dict(id=object_id,queued=False,status='stored-postgres',duplicate=False)
        finally:
            self.discard_staged(staged)

    @staticmethod
    def record_finding(conn, object_id, found):
        from psycopg.types.json import Jsonb
        snapshot = {k:v.isoformat() if isinstance(v,date) else v for k,v in found.items()}
        conn.execute('''INSERT INTO tmb.finding_reviews(object_id,review_id,metadata)
            SELECT %s,id,%s FROM tmb.object_reviews WHERE object_id=%s ORDER BY revision DESC LIMIT 1''',
            (object_id,Jsonb(snapshot),object_id))

    def inventory(self, payload):
        with self.repo.connect() as conn:
            rows = conn.execute('''SELECT o.id,o.status,o.created_at,o.registered_line,o.registered_vehicle,
                o.found_transport,o.found_line,o.found_date,o.date_quality,
                r.revision,r.status AS review_status,r.object_type,r.colors,r.color_order_known,r.material,r.description,
                p.id AS photo_id FROM tmb.found_objects o
                LEFT JOIN LATERAL (SELECT * FROM tmb.object_reviews WHERE object_id=o.id ORDER BY revision DESC LIMIT 1) r ON true
                LEFT JOIN tmb.photos p ON p.object_id=o.id AND p.position=1
                ORDER BY o.created_at DESC LIMIT 200''').fetchall()
        for row in rows:
            row['created_at'] = row['created_at'].isoformat()
            row['found_date'] = row['found_date'].isoformat() if row['found_date'] else None
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
            if 'finding' in payload:
                found = finding(payload['finding'])
                conn.execute('''UPDATE tmb.found_objects SET found_transport=%s,found_line=%s,found_date=%s,date_quality=%s WHERE id=%s''',
                    (found['found_transport'],found['found_line'],found['found_date'],found['date_quality'],object_id))
                self.record_finding(conn,object_id,found)
        return dict(id=object_id,revision=result['revision'])

    def status(self, payload):
        object_id = text(payload.get('id'),160,required=True)
        status = payload.get('status')
        if status not in ('registered','returned','archived'):
            raise ValueError('Estat invàlid.')
        with self.repo.connect() as conn:
            if not conn.execute('SELECT id FROM tmb.found_objects WHERE id=%s FOR UPDATE',(object_id,)).fetchone():
                raise ValueError('Objecte no trobat.')
            conn.execute('UPDATE tmb.found_objects SET status=%s WHERE id=%s',(status,object_id))
            if status != 'returned':
                conn.execute('UPDATE tmb.object_routing SET returned_at=NULL,revision=revision+1 WHERE object_id=%s',(object_id,))
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
        lost_date = calendar_date(payload.get('lostDate'))
        mode, line = transit(payload.get('transport'),payload.get('line'))
        approximate = payload.get('dateApproximate',False)
        if type(approximate) is not bool:
            raise ValueError('Precisió de data invàlida.')
        with self.repo.connect() as conn:
            rows = conn.execute('''SELECT s.*,o.found_transport,r.object_type,r.colors,r.color_order_known,r.material,r.description AS reviewed_description,p.id AS photo_id
                FROM tmb.searchable_objects s JOIN tmb.found_objects o ON o.id=s.id JOIN tmb.object_reviews r ON r.id=s.review_id
                LEFT JOIN tmb.photos p ON p.object_id=s.id AND p.position=1
                WHERE (%s::text IS NULL OR r.object_type=%s)''',
                (object_type,object_type)).fetchall()
        objects = [FoundObject(**{k:row[k] for k in ('id','description','found_date','date_quality','found_line','found_direction','colors','color_order_known','found_transport')}) for row in rows]
        query_text = ' '.join([description,object_type or ''])
        matches = SearchEngine(objects).search(SearchQuery(query_text[:2000],lost_date=lost_date,line=line,transport=mode,colors=tuple(colors),date_approximate=approximate),policy='ranked_strict',limit=20)
        lookup = {row['id']:row for row in rows}
        results = []
        for candidate in matches.candidates:
            row = lookup[candidate.object_id]
            results.append(dict(id=row['id'],objectType=row['object_type'],colors=row['colors'],material=row['material'],
                description=row['reviewed_description'],photo_url=f"/api/photos/{row['photo_id']}" if row['photo_id'] else None,
                colorOrderKnown=row['color_order_known'],foundLine=row['found_line'],foundTransport=row['found_transport'],
                foundDate=row['found_date'].isoformat() if row['found_date'] else None,dateQuality=row['date_quality'],
                score=round(candidate.rank_score,4),textScore=round(candidate.text_score,4),signals=list(candidate.signals)))
        return dict(candidates=results,inventory_count=len(rows))

    def lost_report(self, payload):
        report_id = text(payload.get('id'),160,required=True)
        incident = payload.get('incident') or {}
        contact = payload.get('contact') or {}
        if not isinstance(incident,dict) or not isinstance(contact,dict):
            raise ValueError('Declaració invàlida.')
        query = dict(description=text(payload.get('description'),500,required=True),
            filters=payload.get('filters') or {},lostDate=incident.get('lossDate') or None)
        if any(key in incident for key in ('transport','line','dateApproximate')):
            query.update(transport=incident.get('transport'),line=incident.get('line'),dateApproximate=incident.get('dateApproximate',False))
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
                    mode,line = transit(query.get('transport'),query.get('line'))
                    conn.execute('UPDATE tmb.lost_reports SET lost_transport=%s,lost_line=%s,date_approximate=%s WHERE id=%s',
                        (mode,line,query.get('dateApproximate',False),report_id))
                    if any(contacts.values()):
                        conn.execute('INSERT INTO tmb.report_contacts(report_id,name,email,phone) VALUES (%s,%s,%s,%s)',
                                     (report_id,contacts['name'],contacts['email'],contacts['phone']))
                    if staged:
                        conn.execute('UPDATE tmb.photos SET report_id=%s WHERE id=ANY(%s)',(report_id,staged))
            return dict(id=report_id,status='stored-postgres',**results)
        finally:
            self.discard_staged(staged)

    def matches(self, payload):
        """Operator-only local UI endpoint; never expose contacts through public search."""
        action = payload.get('action','list')
        if action not in ('list','link','unlink','location','return','reopen'):
            raise ValueError('Acció invàlida.')
        with self.repo.connect() as conn:
            if action != 'list':
                object_id = text(payload.get('recordId'),160,required=True)
                obj = conn.execute('SELECT status FROM tmb.found_objects WHERE id=%s FOR UPDATE',(object_id,)).fetchone()
                if not obj:
                    raise ValueError('Objecte no trobat.')
                if action in ('link','unlink'):
                    report_id = text(payload.get('reportId'),160,required=True)
                    if not conn.execute('SELECT id FROM tmb.lost_reports WHERE id=%s',(report_id,)).fetchone():
                        raise ValueError('Declaració no trobada.')
                    if action == 'link':
                        conn.execute('INSERT INTO tmb.object_matches(object_id,report_id) VALUES (%s,%s) ON CONFLICT DO NOTHING',(object_id,report_id))
                    else:
                        conn.execute('DELETE FROM tmb.object_matches WHERE object_id=%s AND report_id=%s',(object_id,report_id))
                else:
                    conn.execute('INSERT INTO tmb.object_routing(object_id) VALUES (%s) ON CONFLICT DO NOTHING',(object_id,))
                    route = conn.execute('SELECT * FROM tmb.object_routing WHERE object_id=%s FOR UPDATE',(object_id,)).fetchone()
                    if payload.get('revision') != route['revision']:
                        raise ConflictError('El seguiment ha canviat. Actualitza Match abans de tornar-ho a provar.')
                    if action == 'location':
                        location = text(payload.get('foundLocation'),160,required=True)
                        destination = text(payload.get('destination'),160)
                        if obj['status']=='returned' and destination != route['destination']:
                            raise ValueError('Reobre el seguiment abans de canviar la destinació.')
                        conn.execute("""UPDATE tmb.object_routing SET found_location=%s,
                            sent_at=CASE WHEN %s::text IS NULL THEN NULL WHEN destination IS DISTINCT FROM %s THEN clock_timestamp() ELSE sent_at END,
                            destination=%s,revision=revision+1 WHERE object_id=%s""",(location,destination,destination,destination,object_id))
                    else:
                        if obj['status']=='archived':
                            raise ValueError('Reactiva l’objecte des de l’inventari abans de continuar.')
                        if action=='return' and not route['destination']:
                            raise ValueError('Indica primer on s’ha enviat l’objecte.')
                        conn.execute("UPDATE tmb.object_routing SET returned_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END,revision=revision+1 WHERE object_id=%s",(action=='return',object_id))
                        conn.execute('UPDATE tmb.found_objects SET status=%s WHERE id=%s',('returned' if action=='return' else 'registered',object_id))
            objects = conn.execute("""SELECT o.*,r.object_type,r.description,
                t.origin_location,t.assigned_destination,t.found_location AS routing_location,t.destination,t.sent_at,t.returned_at,
                coalesce(t.revision,1) AS routing_revision,
                ARRAY(SELECT m.report_id FROM tmb.object_matches m WHERE m.object_id=o.id ORDER BY m.created_at,m.report_id) AS matches
                FROM tmb.found_objects o
                LEFT JOIN LATERAL (SELECT * FROM tmb.object_reviews WHERE object_id=o.id ORDER BY revision DESC LIMIT 1) r ON true
                LEFT JOIN tmb.object_routing t ON t.object_id=o.id ORDER BY o.created_at DESC""").fetchall()
            reports = conn.execute("""SELECT r.*,c.name,c.email,c.phone FROM tmb.lost_reports r
                LEFT JOIN tmb.report_contacts c ON c.report_id=r.id ORDER BY r.created_at DESC""").fetchall()
        def iso(value):
            return value.isoformat() if value else None
        return dict(records=[dict(id=o['id'],object=o['description'] or o['object_type'] or o['id'],type=o['object_type'],
            foundAt=iso(o['found_date']),receivedAt=iso(o['received_at'] or o['created_at']),
            foundLocation=o['routing_location'] or o['found_location'] or o['found_line'] or o['registered_line'] or '',
            assignedDestination=o['assigned_destination'],originLocation=o['origin_location'],
            destination=o['destination'] or '',sentAt=iso(o['sent_at']),
            returnedAt=iso(o['returned_at'] or o['updated_at']) if o['status']=='returned' else None,
            status=o['status'],revision=o['routing_revision'],matchedReportIds=o['matches']) for o in objects],
            reports=[dict(id=r['id'],object=r['original_description'],lostAt=iso(r['lost_date']),
                lostLocation=r['location_text'] or r['lost_line'],contact={k:r[k] for k in ('name','email','phone')}) for r in reports])

    def photo_bytes(self, photo_id):
        with self.repo.connect() as conn:
            photo = conn.execute('''SELECT p.storage_key FROM tmb.photos p
                JOIN tmb.searchable_objects s ON s.id=p.object_id WHERE p.id=%s''',(photo_id,)).fetchone()
        if not photo:
            raise FileNotFoundError('Fotografia no disponible.')
        encoded,_ = _prepare_image(self.data_dir/photo['storage_key'])
        return base64.b64decode(encoded)
