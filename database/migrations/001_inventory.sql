-- ============================================================================
-- TMB LOST & FOUND SYSTEM — COMPLETE HARDENED DATABASE SCHEMA (BACKBONE v0.1)
-- Integrates Inventory (Phase 1) + Citizen Lost Reports & Contacts (Phase 2)
-- Target Engine: PostgreSQL 14+
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. EXTENSIONS & HELPER FUNCTIONS
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Automatically updates updated_at timestamp on row modification
CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Validates that a text[] array contains no duplicate elements and no empty/null values
CREATE OR REPLACE FUNCTION array_has_no_duplicates(arr TEXT[])
RETURNS BOOLEAN AS $$
BEGIN
    IF arr IS NULL OR array_length(arr, 1) IS NULL THEN
        RETURN TRUE;
    END IF;
    RETURN (
        SELECT COUNT(*) = COUNT(DISTINCT elem) AND COUNT(*) FILTER (WHERE elem IS NULL OR btrim(elem) = '') = 0
        FROM unnest(arr) AS elem
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ----------------------------------------------------------------------------
-- 2. TABLE: found_objects (Physical Inventory & Operational Context)
-- ----------------------------------------------------------------------------
CREATE TABLE found_objects (
    id                   TEXT PRIMARY KEY,
    status               TEXT NOT NULL DEFAULT 'registered',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    client_registered_at TIMESTAMPTZ,
    registered_line      TEXT,
    registered_vehicle   TEXT,
    vehicle_source       TEXT,
    found_date           DATE,
    date_quality         TEXT NOT NULL,
    found_line           TEXT,
    found_direction      TEXT,
    found_location       TEXT,
    received_at          TIMESTAMPTZ,
    original_details     JSONB NOT NULL DEFAULT '{}'::jsonb,
    submission_hash      TEXT NOT NULL,

    CONSTRAINT chk_found_objects_id_valid
        CHECK (btrim(id) <> '' AND char_length(id) <= 160),
    CONSTRAINT chk_found_objects_submission_hash_non_empty
        CHECK (btrim(submission_hash) <> ''),
    CONSTRAINT chk_found_objects_status
        CHECK (status IN ('registered', 'returned', 'archived')),
    CONSTRAINT chk_found_objects_vehicle_source
        CHECK (vehicle_source IS NULL OR vehicle_source IN ('manual', 'nfc')),
    CONSTRAINT chk_found_objects_date_quality
        CHECK (date_quality IN ('unknown', 'approximate', 'confirmed')),
   
    -- Business rule: found_date must be NULL if and only if date_quality is 'unknown'
    CONSTRAINT chk_found_objects_date_consistency CHECK (
        (date_quality = 'unknown' AND found_date IS NULL) OR
        (date_quality <> 'unknown' AND found_date IS NOT NULL)
    ),
    CONSTRAINT chk_found_objects_original_details_object
        CHECK (jsonb_typeof(original_details) = 'object')
);

CREATE INDEX ix_found_objects_status ON found_objects (status);
CREATE INDEX ix_found_objects_created_at ON found_objects (created_at DESC);
CREATE INDEX ix_found_objects_submission_hash ON found_objects (submission_hash);

CREATE TRIGGER trg_found_objects_updated_at
BEFORE UPDATE ON found_objects
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

-- ----------------------------------------------------------------------------
-- 3. TABLE: lost_reports (Citizen Loss Claims - Phase 2 Contract)
-- ----------------------------------------------------------------------------
CREATE TABLE lost_reports (
    id                   TEXT PRIMARY KEY,
    status               TEXT NOT NULL DEFAULT 'open',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    client_created_at    TIMESTAMPTZ,
    original_description TEXT NOT NULL,
    lost_date            DATE,
    date_approximate     BOOLEAN NOT NULL DEFAULT false,
    location_text        TEXT,
    line                 TEXT,
    direction            TEXT,
    object_type          TEXT,
    colors               TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
    submission_hash      TEXT NOT NULL,

    CONSTRAINT chk_lost_reports_id_valid
        CHECK (btrim(id) <> '' AND char_length(id) <= 160),
    CONSTRAINT chk_lost_reports_status
        CHECK (status IN ('open', 'closed', 'cancelled')),
    CONSTRAINT chk_lost_reports_description_non_empty
        CHECK (btrim(original_description) <> ''),
    CONSTRAINT chk_lost_reports_submission_hash_non_empty
        CHECK (btrim(submission_hash) <> ''),
    CONSTRAINT chk_lost_reports_colors_unique
        CHECK (array_has_no_duplicates(colors))
);

CREATE INDEX ix_lost_reports_status ON lost_reports (status);
CREATE INDEX ix_lost_reports_created_at ON lost_reports (created_at DESC);
CREATE INDEX ix_lost_reports_submission_hash ON lost_reports (submission_hash);

CREATE TRIGGER trg_lost_reports_updated_at
BEFORE UPDATE ON lost_reports
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

-- ----------------------------------------------------------------------------
-- 4. TABLE: report_contacts (GDPR-Isolated Citizen Contact Data)
-- ----------------------------------------------------------------------------
CREATE TABLE report_contacts (
    report_id   TEXT PRIMARY KEY REFERENCES lost_reports (id) ON DELETE RESTRICT,
    name        TEXT,
    email       TEXT,
    phone       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT chk_report_contacts_non_empty CHECK (
        COALESCE(btrim(name), '') <> '' OR
        COALESCE(btrim(email), '') <> '' OR
        COALESCE(btrim(phone), '') <> ''
    )
);

CREATE TRIGGER trg_report_contacts_updated_at
BEFORE UPDATE ON report_contacts
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

-- ----------------------------------------------------------------------------
-- 5. TABLE: photos (Filesystem References & Dual Ownership Support)
-- ----------------------------------------------------------------------------
CREATE TABLE photos (
    id                 TEXT PRIMARY KEY,
    object_id          TEXT REFERENCES found_objects (id) ON DELETE RESTRICT,
    report_id          TEXT REFERENCES lost_reports (id) ON DELETE RESTRICT,
    position           INTEGER NOT NULL,
    storage_key        TEXT NOT NULL UNIQUE,
    original_filename  TEXT,
    media_type         TEXT NOT NULL,
    image_sha256       TEXT NOT NULL,
    size_bytes         BIGINT NOT NULL,
    width              INTEGER NOT NULL,
    height             INTEGER NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    client_selected_at TIMESTAMPTZ,

    CONSTRAINT chk_photos_id_valid
        CHECK (btrim(id) <> ''),
    CONSTRAINT chk_photos_storage_key_valid
        CHECK (btrim(storage_key) <> ''),
    CONSTRAINT chk_photos_media_type_valid
        CHECK (btrim(media_type) <> ''),
    CONSTRAINT chk_photos_sha256_valid
        CHECK (btrim(image_sha256) <> ''),
    CONSTRAINT chk_photos_position_positive
        CHECK (position > 0),
    CONSTRAINT chk_photos_dimensions_positive
        CHECK (width > 0 AND height > 0 AND size_bytes > 0),
   
    -- A photo belongs to either a found object OR a lost report, never both.
    CONSTRAINT chk_photos_exclusive_owner CHECK (
        NOT (object_id IS NOT NULL AND report_id IS NOT NULL)
    )
);

-- Unique position per owner (position = 1 is the primary photo)
CREATE UNIQUE INDEX uq_photos_object_position
    ON photos (object_id, position)
    WHERE object_id IS NOT NULL;

CREATE UNIQUE INDEX uq_photos_report_position
    ON photos (report_id, position)
    WHERE report_id IS NOT NULL;

CREATE INDEX ix_photos_object_id ON photos (object_id);
CREATE INDEX ix_photos_report_id ON photos (report_id);
CREATE INDEX ix_photos_image_sha256 ON photos (image_sha256);

-- Prevent photo owner reassignment once attached
CREATE OR REPLACE FUNCTION prevent_photo_owner_reassignment()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.object_id IS NOT NULL AND NEW.object_id IS DISTINCT FROM OLD.object_id THEN
        RAISE EXCEPTION 'Photo % is already assigned to object % and cannot be reassigned.', OLD.id, OLD.object_id;
    END IF;
    IF OLD.report_id IS NOT NULL AND NEW.report_id IS DISTINCT FROM OLD.report_id THEN
        RAISE EXCEPTION 'Photo % is already assigned to report % and cannot be reassigned.', OLD.id, OLD.report_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_photos_prevent_reassignment
BEFORE UPDATE ON photos
FOR EACH ROW EXECUTE FUNCTION prevent_photo_owner_reassignment();

-- ----------------------------------------------------------------------------
-- 6. TABLE: extraction_runs (Local Ollama Vision Inference Audit Log)
-- ----------------------------------------------------------------------------
CREATE TABLE extraction_runs (
    id                    TEXT PRIMARY KEY,
    photo_id              TEXT NOT NULL REFERENCES photos (id) ON DELETE RESTRICT,
    cache_key             TEXT,
    source                TEXT NOT NULL,
    status                TEXT NOT NULL,
    model_name            TEXT,
    model_digest          TEXT,
    prompt_version        TEXT,
    preprocessing_version TEXT,
    input_image_sha256    TEXT NOT NULL,
    input_config          JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_output            JSONB,
    proposed_fields       JSONB,
    quality               TEXT,
    sensitive_content     BOOLEAN,
    warnings              JSONB NOT NULL DEFAULT '[]'::jsonb,
    timings               JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message         TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at          TIMESTAMPTZ,

    CONSTRAINT chk_extraction_runs_id_valid
        CHECK (btrim(id) <> ''),
    CONSTRAINT chk_extraction_runs_source
        CHECK (source IN ('operator', 'claimant')),
    CONSTRAINT chk_extraction_runs_status
        CHECK (status IN ('pending', 'succeeded', 'failed')),
    CONSTRAINT chk_extraction_runs_quality
        CHECK (quality IS NULL OR quality IN ('usable', 'insufficient', 'ambiguous')),
    CONSTRAINT chk_extraction_runs_json_types CHECK (
        jsonb_typeof(input_config) = 'object' AND
        jsonb_typeof(warnings) = 'array' AND
        jsonb_typeof(timings) = 'object'
    ),
    CONSTRAINT chk_extraction_runs_completed_metadata CHECK (
        status <> 'succeeded' OR (
            btrim(COALESCE(model_name, '')) <> '' AND
            btrim(COALESCE(model_digest, '')) <> '' AND
            btrim(COALESCE(prompt_version, '')) <> '' AND
            btrim(COALESCE(preprocessing_version, '')) <> '' AND
            completed_at IS NOT NULL
        )
    )
);

CREATE INDEX ix_extraction_runs_photo_id ON extraction_runs (photo_id);
CREATE INDEX ix_extraction_runs_cache_key ON extraction_runs (cache_key);

-- ----------------------------------------------------------------------------
-- 7. TABLE: object_reviews (Human-in-the-Loop Decisions Feeding Search)
-- ----------------------------------------------------------------------------
CREATE TABLE object_reviews (
    id             TEXT PRIMARY KEY,
    object_id      TEXT NOT NULL REFERENCES found_objects (id) ON DELETE RESTRICT,
    revision       INTEGER NOT NULL,
    status         TEXT NOT NULL,
    source         TEXT NOT NULL,
    extraction_id  TEXT REFERENCES extraction_runs (id) ON DELETE RESTRICT,
    object_type    TEXT,
    material       TEXT,
    colors         TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
    description    TEXT NOT NULL DEFAULT '',
    search_text    TEXT NOT NULL DEFAULT '',
    reviewed_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    reviewer_ref   TEXT,
    review_seconds NUMERIC,

    CONSTRAINT chk_object_reviews_id_valid
        CHECK (btrim(id) <> ''),
    CONSTRAINT chk_object_reviews_revision_positive
        CHECK (revision > 0),
    CONSTRAINT chk_object_reviews_status
        CHECK (status IN ('approved', 'rejected')),
    CONSTRAINT chk_object_reviews_source
        CHECK (source IN ('manual', 'extraction')),
    CONSTRAINT chk_object_reviews_review_seconds
        CHECK (review_seconds IS NULL OR review_seconds >= 0),
    CONSTRAINT chk_object_reviews_colors_unique
        CHECK (array_has_no_duplicates(colors)),
    CONSTRAINT chk_object_reviews_description_length
        CHECK (char_length(description) <= 250),
   
    CONSTRAINT uq_object_reviews_object_revision
        UNIQUE (object_id, revision),

    CONSTRAINT chk_object_reviews_extraction_origin CHECK (
        (source = 'extraction' AND extraction_id IS NOT NULL) OR
        (source = 'manual' AND extraction_id IS NULL)
    ),

    CONSTRAINT chk_object_reviews_approved_search_text CHECK (
        status <> 'approved' OR btrim(search_text) <> ''
    )
);

CREATE INDEX ix_object_reviews_object_revision_desc
    ON object_reviews (object_id, revision DESC);

-- Acceptance Test #8: Ensure extraction belongs to a photo of the same object
CREATE OR REPLACE FUNCTION enforce_review_extraction_integrity()
RETURNS TRIGGER AS $$
DECLARE
    v_photo_object_id TEXT;
    v_photo_sha256    TEXT;
    v_input_sha256    TEXT;
BEGIN
    IF NEW.source = 'extraction' AND NEW.extraction_id IS NOT NULL THEN
        SELECT p.object_id, p.image_sha256, er.input_image_sha256
          INTO v_photo_object_id, v_photo_sha256, v_input_sha256
          FROM extraction_runs er
          JOIN photos p ON p.id = er.photo_id
         WHERE er.id = NEW.extraction_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Extraction run % does not exist.', NEW.extraction_id;
        END IF;

        IF v_photo_object_id IS DISTINCT FROM NEW.object_id THEN
            RAISE EXCEPTION 'Integrity violation (Test #8): Extraction % belongs to photo of object %, not %.',
                NEW.extraction_id, COALESCE(v_photo_object_id, 'NULL/unassigned'), NEW.object_id;
        END IF;

        IF v_photo_sha256 IS DISTINCT FROM v_input_sha256 THEN
            RAISE EXCEPTION 'Integrity violation: Extraction input_image_sha256 does not match photo image_sha256.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_object_reviews_check_extraction
BEFORE INSERT OR UPDATE ON object_reviews
FOR EACH ROW EXECUTE FUNCTION enforce_review_extraction_integrity();

-- Automatically bump found_objects.updated_at when a new review is added
CREATE OR REPLACE FUNCTION touch_found_object_on_review()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE found_objects
       SET updated_at = clock_timestamp()
     WHERE id = NEW.object_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_object_reviews_touch_parent
AFTER INSERT OR UPDATE ON object_reviews
FOR EACH ROW EXECUTE FUNCTION touch_found_object_on_review();

-- ----------------------------------------------------------------------------
-- 8. VIEW: searchable_objects (BM25 Search Feed Contract for WP5)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW searchable_objects AS
WITH latest_reviews AS (
    SELECT DISTINCT ON (object_id)
        id AS review_id,
        object_id,
        revision,
        status AS review_status,
        search_text
    FROM object_reviews
    ORDER BY object_id, revision DESC
)
SELECT
    fo.id,
    lr.search_text AS description,
    fo.found_date,
    fo.date_quality,
    fo.found_line,
    fo.found_direction,
    lr.review_id,
    lr.revision
FROM found_objects fo
JOIN latest_reviews lr ON fo.id = lr.object_id
WHERE fo.status = 'registered'
  AND lr.review_status = 'approved';

COMMIT;