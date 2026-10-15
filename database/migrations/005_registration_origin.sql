ALTER TABLE tmb.found_objects
    ADD COLUMN origin_kind text,
    ADD COLUMN origin_location text,
    ADD COLUMN origin_destination text,
    ADD CONSTRAINT chk_found_objects_origin
        CHECK (
            (origin_kind IS NULL AND origin_location IS NULL AND origin_destination IS NULL)
            OR
            (origin_kind IS NOT NULL AND origin_kind IN ('station', 'depot')
             AND origin_location IS NOT NULL AND btrim(origin_location) <> ''
             AND char_length(origin_location) <= 120
             AND origin_destination IS NOT NULL AND btrim(origin_destination) <> ''
             AND char_length(origin_destination) <= 120)
        );

-- Populate the new main-branch columns from origins already saved by the prototype.
UPDATE tmb.found_objects o SET origin_kind=r.origin_kind,
 origin_location=r.origin_location,origin_destination=r.assigned_destination
 FROM tmb.object_routing r WHERE r.object_id=o.id AND r.origin_location IS NOT NULL;
