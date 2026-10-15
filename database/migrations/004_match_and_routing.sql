-- WP3 additions are upgrades: never rewrite the checksummed 001 migration.
SET LOCAL search_path = tmb, pg_catalog;
ALTER TABLE lost_reports ADD COLUMN updated_at timestamptz NOT NULL DEFAULT clock_timestamp();
ALTER TABLE lost_reports ADD COLUMN direction text;
ALTER TABLE report_contacts ADD COLUMN updated_at timestamptz NOT NULL DEFAULT clock_timestamp();
ALTER TABLE report_contacts ADD CONSTRAINT contact_not_empty CHECK
 (coalesce(nullif(btrim(name),''),nullif(btrim(email),''),nullif(btrim(phone),'')) IS NOT NULL);
CREATE FUNCTION touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at := clock_timestamp(); RETURN NEW; END $$;
CREATE TRIGGER touch_report BEFORE UPDATE ON lost_reports FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER touch_contact BEFORE UPDATE ON report_contacts FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE INDEX lost_reports_created_idx ON lost_reports(created_at DESC);
CREATE INDEX lost_reports_status_idx ON lost_reports(status);
CREATE INDEX IF NOT EXISTS photos_hash_idx ON photos(image_sha256);
CREATE INDEX found_objects_created_idx ON found_objects(created_at DESC);
CREATE TABLE object_routing (
 object_id text PRIMARY KEY REFERENCES found_objects(id),
 origin_kind text CHECK (origin_kind IN ('station','depot')),
 origin_location text,
 assigned_destination text,
 found_location text,
 destination text,
 sent_at timestamptz,
 returned_at timestamptz,
 revision integer NOT NULL DEFAULT 1,
 CHECK ((destination IS NULL) = (sent_at IS NULL)),
 CHECK (returned_at IS NULL OR destination IS NOT NULL)
);
CREATE TABLE object_matches (
 object_id text NOT NULL REFERENCES found_objects(id),
 report_id text NOT NULL REFERENCES lost_reports(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(object_id,report_id)
);
CREATE INDEX object_matches_report_idx ON object_matches(report_id);
