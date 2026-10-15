-- Complements the unchanged 001 template. The migration runner owns the transaction.
ALTER TABLE public.found_objects ALTER COLUMN date_quality SET DEFAULT 'unknown';
ALTER TABLE public.extraction_runs ALTER COLUMN status SET DEFAULT 'pending';
ALTER TABLE public.extraction_runs ALTER COLUMN source SET DEFAULT 'operator';

ALTER TABLE public.found_objects ADD CONSTRAINT found_context_nonempty CHECK (
    (found_line IS NULL OR btrim(found_line) <> '') AND
    (found_direction IS NULL OR btrim(found_direction) <> '')
);
ALTER TABLE public.photos ADD CONSTRAINT photos_sha256 CHECK (image_sha256 ~ '^[0-9a-f]{64}$');
ALTER TABLE public.photos ADD CONSTRAINT photos_id_hash UNIQUE (id, image_sha256);
ALTER TABLE public.extraction_runs ADD CONSTRAINT extraction_photo_hash
    FOREIGN KEY (photo_id, input_image_sha256) REFERENCES public.photos(id, image_sha256);
ALTER TABLE public.extraction_runs ADD CONSTRAINT extraction_completion CHECK (
    (status = 'pending' AND completed_at IS NULL) OR
    (status = 'succeeded' AND completed_at IS NOT NULL AND
     raw_output IS NOT NULL AND proposed_fields IS NOT NULL AND
     jsonb_typeof(proposed_fields) = 'object' AND quality IS NOT NULL AND sensitive_content IS NOT NULL) OR
    (status = 'failed' AND completed_at IS NOT NULL AND btrim(COALESCE(error_message, '')) <> '')
);

CREATE FUNCTION public.reject_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'History is append-only; create a new revision or attempt'
        USING ERRCODE = '23514';
END;
$$;
CREATE TRIGGER immutable_reviews BEFORE UPDATE OR DELETE ON public.object_reviews
    FOR EACH ROW EXECUTE FUNCTION public.reject_history_change();
CREATE TRIGGER retain_extractions BEFORE DELETE ON public.extraction_runs
    FOR EACH ROW EXECUTE FUNCTION public.reject_history_change();

CREATE FUNCTION public.guard_extraction_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status <> 'pending' OR NEW.status NOT IN ('succeeded', 'failed') OR
       (to_jsonb(NEW) - ARRAY['status','raw_output','proposed_fields','quality','sensitive_content',
         'warnings','timings','error_message','completed_at']) IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['status','raw_output','proposed_fields','quality','sensitive_content',
         'warnings','timings','error_message','completed_at']) THEN
        RAISE EXCEPTION 'Extraction identity and completed attempts are immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER immutable_extractions BEFORE UPDATE ON public.extraction_runs
    FOR EACH ROW EXECUTE FUNCTION public.guard_extraction_update();

CREATE FUNCTION public.guard_original_submission() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (to_jsonb(NEW) - ARRAY['status','updated_at']) IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['status','updated_at']) THEN
        RAISE EXCEPTION 'Original submission is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER immutable_object_submission BEFORE UPDATE ON public.found_objects
    FOR EACH ROW EXECUTE FUNCTION public.guard_original_submission();
CREATE TRIGGER immutable_report_submission BEFORE UPDATE ON public.lost_reports
    FOR EACH ROW EXECUTE FUNCTION public.guard_original_submission();

CREATE FUNCTION public.guard_photo_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.object_id IS NOT NULL OR OLD.report_id IS NOT NULL OR
           EXISTS (SELECT FROM public.extraction_runs WHERE photo_id = OLD.id) THEN
            RAISE EXCEPTION 'Attached or audited photos cannot be deleted' USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    END IF;
    IF (to_jsonb(NEW) - ARRAY['object_id','report_id']) IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['object_id','report_id']) OR
       (OLD.object_id IS NOT NULL AND NEW.object_id IS DISTINCT FROM OLD.object_id) OR
       (OLD.report_id IS NOT NULL AND NEW.report_id IS DISTINCT FROM OLD.report_id) THEN
        RAISE EXCEPTION 'Photo metadata and ownership are immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
-- Replace the template guard to give constraint violations a consistent SQLSTATE.
DROP TRIGGER trg_photos_prevent_reassignment ON public.photos;
CREATE TRIGGER immutable_photos BEFORE UPDATE OR DELETE ON public.photos
    FOR EACH ROW EXECUTE FUNCTION public.guard_photo_change();

CREATE FUNCTION public.allocate_review_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM public.found_objects WHERE id = NEW.object_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown object' USING ERRCODE = '23503';
    END IF;
    SELECT COALESCE(MAX(revision), 0) + 1 INTO NEW.revision
        FROM public.object_reviews WHERE object_id = NEW.object_id;
    RETURN NEW;
END;
$$;
CREATE TRIGGER allocate_review_revision BEFORE INSERT ON public.object_reviews
    FOR EACH ROW EXECUTE FUNCTION public.allocate_review_revision();

CREATE OR REPLACE FUNCTION public.enforce_review_extraction_integrity()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.extraction_id IS NOT NULL AND NOT EXISTS (
        SELECT FROM public.extraction_runs er JOIN public.photos p ON p.id = er.photo_id
        WHERE er.id = NEW.extraction_id AND er.status = 'succeeded'
          AND p.object_id = NEW.object_id AND p.position = 1
          AND p.image_sha256 = er.input_image_sha256
    ) THEN
        RAISE EXCEPTION 'Review requires a successful extraction of this object primary photo'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
