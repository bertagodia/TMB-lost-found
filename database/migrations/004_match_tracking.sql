SET LOCAL search_path = tmb, pg_catalog;

CREATE TABLE report_matches (
 object_id text NOT NULL REFERENCES found_objects(id),
 report_id text NOT NULL REFERENCES lost_reports(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 destination text CHECK (destination IS NULL OR btrim(destination) <> ''),
 sent_at timestamptz,
 returned_at timestamptz,
 PRIMARY KEY (object_id, report_id),
 CHECK ((destination IS NULL) = (sent_at IS NULL)),
 CHECK (returned_at IS NULL OR destination IS NOT NULL)
);

CREATE INDEX report_matches_report_idx ON report_matches(report_id);
