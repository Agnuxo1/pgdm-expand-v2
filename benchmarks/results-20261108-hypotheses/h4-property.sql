\set ON_ERROR_STOP 1
WITH inputs(raw,field_0) AS (
 SELECT jsonb_build_object('values', jsonb_build_object(
 'field_0',CASE i%4 WHEN 0 THEN to_jsonb(i) WHEN 1 THEN to_jsonb(i::text) WHEN 2 THEN 'null'::jsonb ELSE jsonb_build_array(i) END,
 'field_1',jsonb_build_object('a',i),'field_2',jsonb_build_array(i,'x'),'field_3',true)), 'EXTERNAL'::text
 FROM generate_series(1,1000) i
 UNION ALL SELECT raw,'EXTERNAL' FROM (VALUES (NULL::jsonb),('null'::jsonb),('{}'::jsonb),('[]'::jsonb),
 ('{"values":null}'::jsonb),('{"values":[]}'::jsonb),('{"values":"scalar"}'::jsonb)) p(raw)
), old AS (SELECT s.raw -> 'values' ->> 'field_0' AS f0, s.raw -> 'values' ->> 'field_1' AS f1, s.raw -> 'values' ->> 'field_2' AS f2, s.raw -> 'values' ->> 'field_3' AS f3, s.raw -> 'values' ->> 'field_0' AS f4, s.raw -> 'values' ->> 'field_1' AS f5, s.raw -> 'values' ->> 'field_2' AS f6, s.raw -> 'values' ->> 'field_3' AS f7, field_0 AS external_name FROM inputs AS s), new AS (SELECT pgdm_values_89445ea08b."pgdm_values_89445ea08b_0" AS f0, pgdm_values_89445ea08b."pgdm_values_89445ea08b_1" AS f1, pgdm_values_89445ea08b."pgdm_values_89445ea08b_2" AS f2, pgdm_values_89445ea08b."pgdm_values_89445ea08b_3" AS f3, pgdm_values_89445ea08b."pgdm_values_89445ea08b_0" AS f4, pgdm_values_89445ea08b."pgdm_values_89445ea08b_1" AS f5, pgdm_values_89445ea08b."pgdm_values_89445ea08b_2" AS f6, pgdm_values_89445ea08b."pgdm_values_89445ea08b_3" AS f7, field_0 AS external_name FROM inputs AS s
CROSS JOIN LATERAL (SELECT pgdm_values_89445ea08b_record."field_0" AS "pgdm_values_89445ea08b_0", pgdm_values_89445ea08b_record."field_1" AS "pgdm_values_89445ea08b_1", pgdm_values_89445ea08b_record."field_2" AS "pgdm_values_89445ea08b_2", pgdm_values_89445ea08b_record."field_3" AS "pgdm_values_89445ea08b_3" FROM jsonb_to_record(CASE WHEN jsonb_typeof(s.raw -> 'values') = 'object' THEN s.raw -> 'values' ELSE NULL END) AS pgdm_values_89445ea08b_record ("field_0" text, "field_1" text, "field_2" text, "field_3" text)) AS pgdm_values_89445ea08b
), diff AS ((SELECT * FROM old EXCEPT ALL SELECT * FROM new)
 UNION ALL (SELECT * FROM new EXCEPT ALL SELECT * FROM old))
SELECT json_build_object('test','H4_record_projection','old_rows',(SELECT count(*) FROM old),
 'new_rows',(SELECT count(*) FROM new),'differences',(SELECT count(*) FROM diff));