\set ON_ERROR_STOP 1
WITH inputs(raw) AS (
  VALUES (NULL::jsonb), ('null'::jsonb), ('{}'::jsonb), ('[]'::jsonb),
    ('[1,2]'::jsonb), ('true'::jsonb), ('"scalar"'::jsonb), ('123'::jsonb),
    ('{"values":null}'::jsonb), ('{"values":{}}'::jsonb),
    ('{"values":[]}'::jsonb), ('{"values":["a","b"]}'::jsonb),
    ('{"values":"scalar"}'::jsonb), ('{"values":42}'::jsonb),
    ('{"values":false}'::jsonb), ('{"values":{"key":null}}'::jsonb),
    ('{"values":{"key":"text"}}'::jsonb), ('{"values":{"key":12.50}}'::jsonb),
    ('{"values":{"key":true}}'::jsonb), ('{"values":{"key":{"a":1}}}'::jsonb),
    ('{"values":{"key":[1,2,null]}}'::jsonb)
), generated AS (
  SELECT jsonb_build_object('values', jsonb_build_object('key',
           CASE i % 4 WHEN 0 THEN to_jsonb(i) WHEN 1 THEN to_jsonb(i::text)
             WHEN 2 THEN 'null'::jsonb ELSE jsonb_build_array(i, i+1) END)) AS raw
  FROM generate_series(1,1000) i
), compared AS (
  SELECT raw, raw -> 'values' ->> 'key' AS old_value,
         raw #>> ARRAY['values','key'] AS new_value
  FROM (SELECT * FROM inputs UNION ALL SELECT * FROM generated) q
)
SELECT json_build_object('test','json_path_fusion','cases',count(*),
  'mismatches',count(*) FILTER (WHERE old_value IS DISTINCT FROM new_value))
FROM compared;

-- Witness for the CASE classifier defect. The patched classifier rejects it.
WITH s(raw_id) AS (VALUES (2)), m(id_column_3) AS (VALUES (1),(2)),
original AS (
 SELECT s.raw_id,m.id_column_3 FROM s JOIN m ON CASE WHEN s.raw_id=1
 THEN FALSE AND m.id_column_3=s.raw_id AND FALSE ELSE TRUE END
), unsafe AS (
 SELECT s.raw_id,m.id_column_3 FROM s JOIN
 (SELECT * FROM m WHERE id_column_3 BETWEEN 2 AND 2) m ON CASE WHEN s.raw_id=1
 THEN FALSE AND m.id_column_3=s.raw_id AND FALSE ELSE TRUE END
)
SELECT json_build_object('test','case_counterexample',
 'original_rows',(SELECT count(*) FROM original),'unsafe_rows',(SELECT count(*) FROM unsafe));

WITH input(raw) AS (VALUES ('{"values":{"f":"OLD","field":"NEW"}}'::jsonb))
SELECT json_build_object('test','key_cast_counterexample',
 'original',raw -> 'values' ->> 'field'::char(1),
 'unsafe',(raw #>> ARRAY['values','field'])::char(1)) FROM input;
