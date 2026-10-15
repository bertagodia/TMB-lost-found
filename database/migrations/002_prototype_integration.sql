SET LOCAL search_path = tmb, pg_catalog;
CREATE TABLE http_submissions (
 object_id text PRIMARY KEY REFERENCES found_objects(id),
 request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$')
);
CREATE TABLE lost_reports (
 id text PRIMARY KEY CHECK (length(btrim(id)) BETWEEN 1 AND 160),
 status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','cancelled')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 client_created_at timestamptz,
 original_description text NOT NULL CHECK (length(btrim(original_description)) BETWEEN 1 AND 500),
 lost_date date, location_text text,
 object_type text,
 colors text[] NOT NULL DEFAULT '{}' CHECK (valid_colors(colors)),
 submission_hash text NOT NULL CHECK (submission_hash ~ '^[0-9a-f]{64}$')
);
CREATE TABLE report_contacts (
 report_id text PRIMARY KEY REFERENCES lost_reports(id),
 name text, email text, phone text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE photos ADD COLUMN report_id text REFERENCES lost_reports(id);
ALTER TABLE photos ADD CONSTRAINT photo_one_owner CHECK (object_id IS NULL OR report_id IS NULL);
ALTER TABLE photos ADD CONSTRAINT photo_report_position UNIQUE (report_id,position);
CREATE OR REPLACE FUNCTION protect_photo() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW) - 'object_id' - 'report_id') IS DISTINCT FROM (to_jsonb(OLD) - 'object_id' - 'report_id')
    OR (OLD.object_id IS NOT NULL AND NEW.object_id IS DISTINCT FROM OLD.object_id)
    OR (OLD.report_id IS NOT NULL AND NEW.report_id IS DISTINCT FROM OLD.report_id) THEN
   RAISE EXCEPTION 'Photo metadata and assigned owner are immutable' USING ERRCODE = '23514';
 END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION protect_photo_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.object_id IS NOT NULL OR OLD.report_id IS NOT NULL THEN
   RAISE EXCEPTION 'An attached photo is part of the original submission' USING ERRCODE = '23514';
 END IF;
 RETURN OLD;
END $$;
