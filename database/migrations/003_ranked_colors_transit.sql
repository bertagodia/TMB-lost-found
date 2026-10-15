SET LOCAL search_path = tmb, pg_catalog;
-- Older records keep unknown order; alphabetical selection order is not coverage.
ALTER TABLE object_reviews ADD COLUMN color_order_known boolean NOT NULL DEFAULT false;
ALTER TABLE found_objects ADD COLUMN found_transport text CHECK (found_transport IN ('bus','metro'));
ALTER TABLE lost_reports ADD COLUMN lost_transport text CHECK (lost_transport IN ('bus','metro'));
ALTER TABLE lost_reports ADD COLUMN lost_line text;
ALTER TABLE lost_reports ADD COLUMN date_approximate boolean NOT NULL DEFAULT false;
-- Audit corrections independently of the immutable original attribute submission.
CREATE TABLE finding_reviews (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 object_id text NOT NULL REFERENCES found_objects(id),
 review_id text NOT NULL REFERENCES object_reviews(id),
 metadata jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER immutable_finding_review BEFORE UPDATE OR DELETE ON finding_reviews
 FOR EACH ROW EXECUTE FUNCTION forbid_history_change();
