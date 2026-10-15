-- Synthetic metadata only: these storage keys do NOT refer to real image files.
-- Reserved IDs beginning demo-wp3-. Run in a development database only.
INSERT INTO tmb.found_objects(id,registered_line,registered_vehicle,vehicle_source,original_details,submission_hash)
VALUES ('demo-wp3-bottle','TEST','001','manual',
 '{"colors":["Gris","Taronja","Negre"],"objectType":"Ampolla","material":"Metall","description":"Demo bottle"}',repeat('1',64)),
 ('demo-wp3-keys','TEST','002','manual',
 '{"colors":["Gris"],"objectType":"Claus","material":"Metall","description":"Demo keys"}',repeat('2',64))
ON CONFLICT (id) DO NOTHING;

INSERT INTO tmb.photos(id,object_id,position,storage_key,media_type,image_sha256,size_bytes,width,height)
VALUES ('demo-wp3-photo-1','demo-wp3-bottle',1,'demo/not-a-real-file/bottle-front.jpg','image/jpeg',repeat('a',64),100,20,30),
 ('demo-wp3-photo-2','demo-wp3-bottle',2,'demo/not-a-real-file/bottle-back.jpg','image/jpeg',repeat('b',64),100,20,30),
 ('demo-wp3-photo-3','demo-wp3-keys',1,'demo/not-a-real-file/keys.jpg','image/jpeg',repeat('c',64),100,20,30)
ON CONFLICT (id) DO NOTHING;

INSERT INTO tmb.extraction_runs(id,photo_id,input_image_sha256,status,model_name,model_digest,
 prompt_version,preprocessing_version,raw_output,proposed_fields,quality,sensitive_content,completed_at)
VALUES ('demo-wp3-extraction-1','demo-wp3-photo-1',repeat('a',64),'succeeded','fixture-not-ollama','fixture',
 'fixture-v1','fixture-v1','{"object_name":"bottle"}',
 '{"colors":["Gris","Taronja","Negre"],"objectType":"Ampolla","material":"Metall","description":"Demo bottle"}',
 'usable',false,clock_timestamp())
ON CONFLICT (id) DO NOTHING;

INSERT INTO tmb.extraction_runs(id,photo_id,input_image_sha256,status,model_name,error_message,completed_at)
VALUES ('demo-wp3-extraction-2','demo-wp3-photo-3',repeat('c',64),'failed','fixture-not-ollama',
 'Synthetic example: model unavailable',clock_timestamp())
ON CONFLICT (id) DO NOTHING;

-- Avoid re-running the append trigger for an already seeded review.
INSERT INTO tmb.object_reviews(id,object_id,status,source,extraction_id,object_type,material,colors,description,search_text)
SELECT 'demo-wp3-review-1','demo-wp3-bottle','approved','extraction','demo-wp3-extraction-1',
 'Ampolla','Metall',ARRAY['Gris','Taronja','Negre'],'Demo bottle','Ampolla. Gris, Taronja, Negre. Metall. Demo bottle'
WHERE NOT EXISTS (SELECT FROM tmb.object_reviews WHERE id='demo-wp3-review-1');

INSERT INTO tmb.object_reviews(id,object_id,status,source,object_type,material,colors,description,search_text)
SELECT 'demo-wp3-review-2','demo-wp3-keys','approved','manual',
 'Claus','Metall',ARRAY['Gris'],'Demo keys','Claus. Gris. Metall. Demo keys'
WHERE NOT EXISTS (SELECT FROM tmb.object_reviews WHERE id='demo-wp3-review-2');
