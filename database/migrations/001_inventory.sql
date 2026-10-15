CREATE SCHEMA tmb;
SET LOCAL search_path = tmb, pg_catalog;

CREATE FUNCTION valid_colors(value text[]) RETURNS boolean
LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT coalesce(array_ndims(value), 1) = 1
   AND cardinality(value) = (SELECT count(DISTINCT c) FROM unnest(value) c)
   AND NOT EXISTS (SELECT FROM unnest(value) c WHERE c IS NULL OR btrim(c) = '')
$$;

CREATE TABLE found_objects (
 id text PRIMARY KEY CHECK (length(btrim(id)) BETWEEN 1 AND 160),
 status text NOT NULL DEFAULT 'registered' CHECK (status IN ('registered','returned','archived')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 client_registered_at timestamptz,
 registered_line text, registered_vehicle text,
 vehicle_source text CHECK (vehicle_source IN ('manual','nfc')),
 found_date date,
 date_quality text NOT NULL DEFAULT 'unknown' CHECK (date_quality IN ('unknown','approximate','confirmed')),
 found_line text CHECK (found_line IS NULL OR btrim(found_line) <> ''),
 found_direction text CHECK (found_direction IS NULL OR btrim(found_direction) <> ''),
 found_location text,
 received_at timestamptz,
 original_details jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(original_details) = 'object'),
 submission_hash text NOT NULL CHECK (submission_hash ~ '^[0-9a-f]{64}$'),
 CHECK ((found_date IS NULL) = (date_quality = 'unknown'))
);

CREATE TABLE photos (
 id text PRIMARY KEY CHECK (btrim(id) <> ''),
 object_id text REFERENCES found_objects(id),
 position integer NOT NULL CHECK (position > 0),
 storage_key text NOT NULL UNIQUE CHECK (btrim(storage_key) <> ''),
 original_filename text,
 media_type text NOT NULL CHECK (media_type IN ('image/jpeg','image/png','image/webp')),
 image_sha256 text NOT NULL CHECK (image_sha256 ~ '^[0-9a-f]{64}$'),
 size_bytes bigint NOT NULL CHECK (size_bytes > 0),
 width integer NOT NULL CHECK (width > 0),
 height integer NOT NULL CHECK (height > 0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 client_selected_at timestamptz,
 UNIQUE (object_id, position),
 UNIQUE (id, image_sha256)
);
CREATE INDEX photos_hash_idx ON photos(image_sha256);

CREATE TABLE extraction_runs (
 id text PRIMARY KEY CHECK (btrim(id) <> ''),
 photo_id text NOT NULL,
 input_image_sha256 text NOT NULL,
 FOREIGN KEY (photo_id, input_image_sha256) REFERENCES photos(id, image_sha256),
 cache_key text,
 source text NOT NULL DEFAULT 'operator' CHECK (source IN ('operator','claimant')),
 status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','succeeded','failed')),
 model_name text NOT NULL CHECK (btrim(model_name) <> ''),
 model_digest text,
 prompt_version text,
 preprocessing_version text,
 input_config jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(input_config) = 'object'),
 raw_output jsonb CHECK (jsonb_typeof(raw_output) = 'object'),
 proposed_fields jsonb CHECK (jsonb_typeof(proposed_fields) = 'object'),
 quality text CHECK (quality IN ('usable','insufficient','ambiguous')),
 sensitive_content boolean,
 warnings jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(warnings) = 'array'),
 timings jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(timings) = 'object'),
 error_message text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 completed_at timestamptz,
 CHECK ((status = 'pending') = (completed_at IS NULL)),
 CHECK (completed_at IS NULL OR completed_at >= created_at),
 CHECK (status <> 'failed' OR coalesce(length(btrim(error_message)),0) > 0),
 CHECK (status <> 'succeeded' OR (
   raw_output IS NOT NULL AND proposed_fields IS NOT NULL AND quality IS NOT NULL
   AND sensitive_content IS NOT NULL AND error_message IS NULL
   AND coalesce(length(btrim(model_digest)),0) > 0
   AND coalesce(length(btrim(prompt_version)),0) > 0
   AND coalesce(length(btrim(preprocessing_version)),0) > 0))
);
CREATE INDEX extraction_photo_idx ON extraction_runs(photo_id);
CREATE INDEX extraction_cache_idx ON extraction_runs(cache_key);

CREATE TABLE object_reviews (
 id text PRIMARY KEY CHECK (btrim(id) <> ''),
 object_id text NOT NULL REFERENCES found_objects(id),
 revision integer NOT NULL CHECK (revision > 0),
 status text NOT NULL CHECK (status IN ('approved','rejected')),
 source text NOT NULL CHECK (source IN ('manual','extraction')),
 extraction_id text REFERENCES extraction_runs(id),
 object_type text, material text,
 colors text[] NOT NULL DEFAULT '{}' CHECK (valid_colors(colors)),
 description text NOT NULL DEFAULT '' CHECK (length(description) <= 250),
 search_text text NOT NULL DEFAULT '',
 reviewed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 reviewer_ref text,
 review_seconds numeric CHECK (review_seconds >= 0 AND review_seconds <> 'NaN'::numeric
   AND review_seconds <> 'Infinity'::numeric),
 UNIQUE (object_id, revision),
 CHECK ((source = 'extraction') = (extraction_id IS NOT NULL)),
 CHECK (status <> 'approved' OR btrim(search_text) <> '')
);
CREATE INDEX review_extraction_idx ON object_reviews(extraction_id) WHERE extraction_id IS NOT NULL;

CREATE FUNCTION protect_object() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF ROW(NEW.id, NEW.original_details, NEW.submission_hash, NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id, OLD.original_details, OLD.submission_hash, OLD.created_at) THEN
   RAISE EXCEPTION 'Original submission is immutable' USING ERRCODE = '23514';
 END IF;
 NEW.updated_at := clock_timestamp();
 RETURN NEW;
END $$;
CREATE TRIGGER protect_object BEFORE UPDATE ON found_objects FOR EACH ROW EXECUTE FUNCTION protect_object();

CREATE FUNCTION protect_photo() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW) - 'object_id') IS DISTINCT FROM (to_jsonb(OLD) - 'object_id')
    OR (OLD.object_id IS NOT NULL AND NEW.object_id IS DISTINCT FROM OLD.object_id) THEN
   RAISE EXCEPTION 'Photo metadata and assigned owner are immutable' USING ERRCODE = '23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER protect_photo BEFORE UPDATE ON photos FOR EACH ROW EXECUTE FUNCTION protect_photo();

CREATE FUNCTION protect_extraction() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.status <> 'pending' OR ROW(NEW.id, NEW.photo_id, NEW.input_image_sha256,
      NEW.source, NEW.cache_key, NEW.input_config, NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id, OLD.photo_id, OLD.input_image_sha256,
      OLD.source, OLD.cache_key, OLD.input_config, OLD.created_at) THEN
   RAISE EXCEPTION 'Extraction provenance or completed result is immutable' USING ERRCODE = '23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER protect_extraction BEFORE UPDATE ON extraction_runs FOR EACH ROW EXECUTE FUNCTION protect_extraction();

CREATE FUNCTION append_review() RETURNS trigger LANGUAGE plpgsql
SET search_path = tmb, pg_catalog AS $$
DECLARE next_revision integer;
BEGIN
 -- Serialize review allocation, including writes from clients other than Python.
 PERFORM 1 FROM found_objects WHERE id = NEW.object_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Object not found' USING ERRCODE = '23503'; END IF;
 SELECT coalesce(max(revision),0) + 1 INTO next_revision FROM object_reviews WHERE object_id = NEW.object_id;
 IF NEW.revision IS NOT NULL AND NEW.revision <> next_revision THEN
   RAISE EXCEPTION 'Review revision must be the next version' USING ERRCODE = '23514';
 END IF;
 NEW.revision := next_revision;
 NEW.reviewed_at := clock_timestamp();
 IF NEW.extraction_id IS NOT NULL AND NOT EXISTS (
   SELECT FROM extraction_runs e JOIN photos p ON p.id = e.photo_id
   WHERE e.id = NEW.extraction_id AND p.object_id = NEW.object_id AND e.status = 'succeeded'
 ) THEN
   RAISE EXCEPTION 'Review extraction must be completed and belong to this object' USING ERRCODE = '23514';
 END IF;
 UPDATE found_objects SET updated_at = clock_timestamp() WHERE id = NEW.object_id;
 RETURN NEW;
END $$;
CREATE TRIGGER append_review BEFORE INSERT ON object_reviews FOR EACH ROW EXECUTE FUNCTION append_review();

CREATE FUNCTION forbid_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'History is append-only; archive objects or append a review' USING ERRCODE = '23514';
END $$;
CREATE TRIGGER immutable_review BEFORE UPDATE OR DELETE ON object_reviews FOR EACH ROW EXECUTE FUNCTION forbid_history_change();
CREATE TRIGGER keep_extraction BEFORE DELETE ON extraction_runs FOR EACH ROW EXECUTE FUNCTION forbid_history_change();
CREATE TRIGGER keep_object BEFORE DELETE ON found_objects FOR EACH ROW EXECUTE FUNCTION forbid_history_change();

CREATE VIEW searchable_objects AS
 SELECT o.id, r.search_text AS description, o.found_date, o.date_quality,
        o.found_line, o.found_direction, r.id AS review_id, r.revision
 FROM found_objects o
 JOIN LATERAL (
   SELECT * FROM object_reviews WHERE object_id = o.id ORDER BY revision DESC LIMIT 1
 ) r ON true
 WHERE o.status = 'registered' AND r.status = 'approved';

CREATE FUNCTION protect_photo_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.object_id IS NOT NULL THEN
   RAISE EXCEPTION 'An attached photo is part of the original submission' USING ERRCODE = '23514';
 END IF;
 RETURN OLD;
END $$;
CREATE TRIGGER keep_attached_photo BEFORE DELETE ON photos FOR EACH ROW EXECUTE FUNCTION protect_photo_delete();
