\set ON_ERROR_STOP 1
SET default_transaction_read_only=on;
SET max_parallel_workers_per_gather=0;
SET jit=off;

SELECT 'PGDM_MICRO h3 1';
EXPLAIN (ANALYZE, FORMAT JSON, TIMING OFF) SELECT SUM(octet_length(to_jsonb(q)::text)) FROM (SELECT
    source_row.raw_id,
    position_data.position_number,
    ROUND(
        NULLIF(BTRIM(position_data.weight_text), '')::numeric * 1000
    )::integer,
    UPPER(BTRIM(position_data.type_text)),
    NULL::integer,
    NULL::integer,
    NULL::integer,
    CASE
        WHEN NULLIF(BTRIM(position_data.gap_text), '')::numeric > 0
        THEN ROUND(
            NULLIF(BTRIM(position_data.gap_text), '')::numeric * 1000
        )::integer
        ELSE NULL::integer
    END
FROM (SELECT raw_id,raw FROM public.raw_data WHERE raw_id BETWEEN 1 AND 50000) AS source_row
CROSS JOIN LATERAL (
    VALUES
        (1::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_2']), (source_row.raw #>> ARRAY['values', 'text_column_4']), (source_row.raw #>> ARRAY['values', 'numeric_column_3']), (source_row.raw #>> ARRAY['values', 'numeric_column_4'])),
        (2::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_3']), (source_row.raw #>> ARRAY['values', 'text_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_6'])),
        (3::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_4']), (source_row.raw #>> ARRAY['values', 'text_column_6']), (source_row.raw #>> ARRAY['values', 'numeric_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_8'])),
        (4::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_5']), (source_row.raw #>> ARRAY['values', 'text_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_10'])),
        (5::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_6']), (source_row.raw #>> ARRAY['values', 'text_column_8']), (source_row.raw #>> ARRAY['values', 'numeric_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_12'])),
        (6::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_7']), (source_row.raw #>> ARRAY['values', 'text_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_14'])),
        (7::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_8']), (source_row.raw #>> ARRAY['values', 'text_column_10']), (source_row.raw #>> ARRAY['values', 'numeric_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_16'])),
        (8::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_9']), (source_row.raw #>> ARRAY['values', 'text_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_18'])),
        (9::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_10']), (source_row.raw #>> ARRAY['values', 'text_column_12']), (source_row.raw #>> ARRAY['values', 'numeric_column_19']), (source_row.raw #>> ARRAY['values', 'numeric_column_20'])),
        (10::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_11']), (source_row.raw #>> ARRAY['values', 'text_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_21']), (source_row.raw #>> ARRAY['values', 'numeric_column_22'])),
        (11::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_12']), (source_row.raw #>> ARRAY['values', 'text_column_14']), (source_row.raw #>> ARRAY['values', 'numeric_column_23']), (source_row.raw #>> ARRAY['values', 'numeric_column_24'])),
        (12::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_13']), (source_row.raw #>> ARRAY['values', 'text_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_25']), (source_row.raw #>> ARRAY['values', 'numeric_column_26'])),
        (13::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_14']), (source_row.raw #>> ARRAY['values', 'text_column_16']), (source_row.raw #>> ARRAY['values', 'numeric_column_27']), (source_row.raw #>> ARRAY['values', 'numeric_column_28'])),
        (14::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_15']), (source_row.raw #>> ARRAY['values', 'text_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_29']), (source_row.raw #>> ARRAY['values', 'numeric_column_30']))
) AS position_data(position_number, declared_number_text, type_text, weight_text, gap_text)

WHERE NULLIF(BTRIM(position_data.declared_number_text), '')::smallint
        = position_data.position_number
  AND NULLIF(BTRIM(position_data.weight_text), '')::numeric >= 0
  AND UPPER(BTRIM(position_data.type_text)) IN ('X', 'Y', 'Z')) q;
SELECT 'PGDM_MICRO h5 1';
EXPLAIN (ANALYZE, FORMAT JSON, TIMING OFF) SELECT SUM(octet_length(to_jsonb(q)::text)) FROM (SELECT
    source_row.raw_id,
    position_data.position_number,
    ROUND(
        NULLIF(BTRIM(position_data.weight_text), '')::numeric * 1000
    )::integer,
    UPPER(BTRIM(position_data.type_text)),
    NULL::integer,
    NULL::integer,
    NULL::integer,
    CASE
        WHEN NULLIF(BTRIM(position_data.gap_text), '')::numeric > 0
        THEN ROUND(
            NULLIF(BTRIM(position_data.gap_text), '')::numeric * 1000
        )::integer
        ELSE NULL::integer
    END
FROM (SELECT raw_id,raw FROM public.raw_data WHERE raw_id BETWEEN 1 AND 50000) AS source_row
CROSS JOIN LATERAL (
SELECT 1::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_2']), (source_row.raw #>> ARRAY['values', 'text_column_4']), (source_row.raw #>> ARRAY['values', 'numeric_column_3']), (source_row.raw #>> ARRAY['values', 'numeric_column_4'])
UNION ALL
SELECT 2::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_3']), (source_row.raw #>> ARRAY['values', 'text_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_6'])
UNION ALL
SELECT 3::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_4']), (source_row.raw #>> ARRAY['values', 'text_column_6']), (source_row.raw #>> ARRAY['values', 'numeric_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_8'])
UNION ALL
SELECT 4::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_5']), (source_row.raw #>> ARRAY['values', 'text_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_10'])
UNION ALL
SELECT 5::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_6']), (source_row.raw #>> ARRAY['values', 'text_column_8']), (source_row.raw #>> ARRAY['values', 'numeric_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_12'])
UNION ALL
SELECT 6::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_7']), (source_row.raw #>> ARRAY['values', 'text_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_14'])
UNION ALL
SELECT 7::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_8']), (source_row.raw #>> ARRAY['values', 'text_column_10']), (source_row.raw #>> ARRAY['values', 'numeric_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_16'])
UNION ALL
SELECT 8::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_9']), (source_row.raw #>> ARRAY['values', 'text_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_18'])
UNION ALL
SELECT 9::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_10']), (source_row.raw #>> ARRAY['values', 'text_column_12']), (source_row.raw #>> ARRAY['values', 'numeric_column_19']), (source_row.raw #>> ARRAY['values', 'numeric_column_20'])
UNION ALL
SELECT 10::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_11']), (source_row.raw #>> ARRAY['values', 'text_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_21']), (source_row.raw #>> ARRAY['values', 'numeric_column_22'])
UNION ALL
SELECT 11::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_12']), (source_row.raw #>> ARRAY['values', 'text_column_14']), (source_row.raw #>> ARRAY['values', 'numeric_column_23']), (source_row.raw #>> ARRAY['values', 'numeric_column_24'])
UNION ALL
SELECT 12::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_13']), (source_row.raw #>> ARRAY['values', 'text_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_25']), (source_row.raw #>> ARRAY['values', 'numeric_column_26'])
UNION ALL
SELECT 13::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_14']), (source_row.raw #>> ARRAY['values', 'text_column_16']), (source_row.raw #>> ARRAY['values', 'numeric_column_27']), (source_row.raw #>> ARRAY['values', 'numeric_column_28'])
UNION ALL
SELECT 14::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_15']), (source_row.raw #>> ARRAY['values', 'text_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_29']), (source_row.raw #>> ARRAY['values', 'numeric_column_30'])
) AS position_data(position_number, declared_number_text, type_text, weight_text, gap_text)

WHERE NULLIF(BTRIM(position_data.declared_number_text), '')::smallint
        = position_data.position_number
  AND NULLIF(BTRIM(position_data.weight_text), '')::numeric >= 0
  AND UPPER(BTRIM(position_data.type_text)) IN ('X', 'Y', 'Z')) q;
SELECT 'PGDM_MICRO h5 2';
EXPLAIN (ANALYZE, FORMAT JSON, TIMING OFF) SELECT SUM(octet_length(to_jsonb(q)::text)) FROM (SELECT
    source_row.raw_id,
    position_data.position_number,
    ROUND(
        NULLIF(BTRIM(position_data.weight_text), '')::numeric * 1000
    )::integer,
    UPPER(BTRIM(position_data.type_text)),
    NULL::integer,
    NULL::integer,
    NULL::integer,
    CASE
        WHEN NULLIF(BTRIM(position_data.gap_text), '')::numeric > 0
        THEN ROUND(
            NULLIF(BTRIM(position_data.gap_text), '')::numeric * 1000
        )::integer
        ELSE NULL::integer
    END
FROM (SELECT raw_id,raw FROM public.raw_data WHERE raw_id BETWEEN 1 AND 50000) AS source_row
CROSS JOIN LATERAL (
SELECT 1::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_2']), (source_row.raw #>> ARRAY['values', 'text_column_4']), (source_row.raw #>> ARRAY['values', 'numeric_column_3']), (source_row.raw #>> ARRAY['values', 'numeric_column_4'])
UNION ALL
SELECT 2::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_3']), (source_row.raw #>> ARRAY['values', 'text_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_6'])
UNION ALL
SELECT 3::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_4']), (source_row.raw #>> ARRAY['values', 'text_column_6']), (source_row.raw #>> ARRAY['values', 'numeric_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_8'])
UNION ALL
SELECT 4::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_5']), (source_row.raw #>> ARRAY['values', 'text_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_10'])
UNION ALL
SELECT 5::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_6']), (source_row.raw #>> ARRAY['values', 'text_column_8']), (source_row.raw #>> ARRAY['values', 'numeric_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_12'])
UNION ALL
SELECT 6::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_7']), (source_row.raw #>> ARRAY['values', 'text_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_14'])
UNION ALL
SELECT 7::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_8']), (source_row.raw #>> ARRAY['values', 'text_column_10']), (source_row.raw #>> ARRAY['values', 'numeric_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_16'])
UNION ALL
SELECT 8::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_9']), (source_row.raw #>> ARRAY['values', 'text_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_18'])
UNION ALL
SELECT 9::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_10']), (source_row.raw #>> ARRAY['values', 'text_column_12']), (source_row.raw #>> ARRAY['values', 'numeric_column_19']), (source_row.raw #>> ARRAY['values', 'numeric_column_20'])
UNION ALL
SELECT 10::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_11']), (source_row.raw #>> ARRAY['values', 'text_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_21']), (source_row.raw #>> ARRAY['values', 'numeric_column_22'])
UNION ALL
SELECT 11::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_12']), (source_row.raw #>> ARRAY['values', 'text_column_14']), (source_row.raw #>> ARRAY['values', 'numeric_column_23']), (source_row.raw #>> ARRAY['values', 'numeric_column_24'])
UNION ALL
SELECT 12::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_13']), (source_row.raw #>> ARRAY['values', 'text_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_25']), (source_row.raw #>> ARRAY['values', 'numeric_column_26'])
UNION ALL
SELECT 13::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_14']), (source_row.raw #>> ARRAY['values', 'text_column_16']), (source_row.raw #>> ARRAY['values', 'numeric_column_27']), (source_row.raw #>> ARRAY['values', 'numeric_column_28'])
UNION ALL
SELECT 14::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_15']), (source_row.raw #>> ARRAY['values', 'text_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_29']), (source_row.raw #>> ARRAY['values', 'numeric_column_30'])
) AS position_data(position_number, declared_number_text, type_text, weight_text, gap_text)

WHERE NULLIF(BTRIM(position_data.declared_number_text), '')::smallint
        = position_data.position_number
  AND NULLIF(BTRIM(position_data.weight_text), '')::numeric >= 0
  AND UPPER(BTRIM(position_data.type_text)) IN ('X', 'Y', 'Z')) q;
SELECT 'PGDM_MICRO h3 2';
EXPLAIN (ANALYZE, FORMAT JSON, TIMING OFF) SELECT SUM(octet_length(to_jsonb(q)::text)) FROM (SELECT
    source_row.raw_id,
    position_data.position_number,
    ROUND(
        NULLIF(BTRIM(position_data.weight_text), '')::numeric * 1000
    )::integer,
    UPPER(BTRIM(position_data.type_text)),
    NULL::integer,
    NULL::integer,
    NULL::integer,
    CASE
        WHEN NULLIF(BTRIM(position_data.gap_text), '')::numeric > 0
        THEN ROUND(
            NULLIF(BTRIM(position_data.gap_text), '')::numeric * 1000
        )::integer
        ELSE NULL::integer
    END
FROM (SELECT raw_id,raw FROM public.raw_data WHERE raw_id BETWEEN 1 AND 50000) AS source_row
CROSS JOIN LATERAL (
    VALUES
        (1::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_2']), (source_row.raw #>> ARRAY['values', 'text_column_4']), (source_row.raw #>> ARRAY['values', 'numeric_column_3']), (source_row.raw #>> ARRAY['values', 'numeric_column_4'])),
        (2::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_3']), (source_row.raw #>> ARRAY['values', 'text_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_6'])),
        (3::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_4']), (source_row.raw #>> ARRAY['values', 'text_column_6']), (source_row.raw #>> ARRAY['values', 'numeric_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_8'])),
        (4::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_5']), (source_row.raw #>> ARRAY['values', 'text_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_10'])),
        (5::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_6']), (source_row.raw #>> ARRAY['values', 'text_column_8']), (source_row.raw #>> ARRAY['values', 'numeric_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_12'])),
        (6::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_7']), (source_row.raw #>> ARRAY['values', 'text_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_14'])),
        (7::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_8']), (source_row.raw #>> ARRAY['values', 'text_column_10']), (source_row.raw #>> ARRAY['values', 'numeric_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_16'])),
        (8::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_9']), (source_row.raw #>> ARRAY['values', 'text_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_18'])),
        (9::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_10']), (source_row.raw #>> ARRAY['values', 'text_column_12']), (source_row.raw #>> ARRAY['values', 'numeric_column_19']), (source_row.raw #>> ARRAY['values', 'numeric_column_20'])),
        (10::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_11']), (source_row.raw #>> ARRAY['values', 'text_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_21']), (source_row.raw #>> ARRAY['values', 'numeric_column_22'])),
        (11::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_12']), (source_row.raw #>> ARRAY['values', 'text_column_14']), (source_row.raw #>> ARRAY['values', 'numeric_column_23']), (source_row.raw #>> ARRAY['values', 'numeric_column_24'])),
        (12::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_13']), (source_row.raw #>> ARRAY['values', 'text_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_25']), (source_row.raw #>> ARRAY['values', 'numeric_column_26'])),
        (13::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_14']), (source_row.raw #>> ARRAY['values', 'text_column_16']), (source_row.raw #>> ARRAY['values', 'numeric_column_27']), (source_row.raw #>> ARRAY['values', 'numeric_column_28'])),
        (14::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_15']), (source_row.raw #>> ARRAY['values', 'text_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_29']), (source_row.raw #>> ARRAY['values', 'numeric_column_30']))
) AS position_data(position_number, declared_number_text, type_text, weight_text, gap_text)

WHERE NULLIF(BTRIM(position_data.declared_number_text), '')::smallint
        = position_data.position_number
  AND NULLIF(BTRIM(position_data.weight_text), '')::numeric >= 0
  AND UPPER(BTRIM(position_data.type_text)) IN ('X', 'Y', 'Z')) q;
SELECT 'PGDM_MICRO h3 3';
EXPLAIN (ANALYZE, FORMAT JSON, TIMING OFF) SELECT SUM(octet_length(to_jsonb(q)::text)) FROM (SELECT
    source_row.raw_id,
    position_data.position_number,
    ROUND(
        NULLIF(BTRIM(position_data.weight_text), '')::numeric * 1000
    )::integer,
    UPPER(BTRIM(position_data.type_text)),
    NULL::integer,
    NULL::integer,
    NULL::integer,
    CASE
        WHEN NULLIF(BTRIM(position_data.gap_text), '')::numeric > 0
        THEN ROUND(
            NULLIF(BTRIM(position_data.gap_text), '')::numeric * 1000
        )::integer
        ELSE NULL::integer
    END
FROM (SELECT raw_id,raw FROM public.raw_data WHERE raw_id BETWEEN 1 AND 50000) AS source_row
CROSS JOIN LATERAL (
    VALUES
        (1::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_2']), (source_row.raw #>> ARRAY['values', 'text_column_4']), (source_row.raw #>> ARRAY['values', 'numeric_column_3']), (source_row.raw #>> ARRAY['values', 'numeric_column_4'])),
        (2::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_3']), (source_row.raw #>> ARRAY['values', 'text_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_6'])),
        (3::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_4']), (source_row.raw #>> ARRAY['values', 'text_column_6']), (source_row.raw #>> ARRAY['values', 'numeric_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_8'])),
        (4::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_5']), (source_row.raw #>> ARRAY['values', 'text_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_10'])),
        (5::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_6']), (source_row.raw #>> ARRAY['values', 'text_column_8']), (source_row.raw #>> ARRAY['values', 'numeric_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_12'])),
        (6::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_7']), (source_row.raw #>> ARRAY['values', 'text_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_14'])),
        (7::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_8']), (source_row.raw #>> ARRAY['values', 'text_column_10']), (source_row.raw #>> ARRAY['values', 'numeric_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_16'])),
        (8::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_9']), (source_row.raw #>> ARRAY['values', 'text_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_18'])),
        (9::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_10']), (source_row.raw #>> ARRAY['values', 'text_column_12']), (source_row.raw #>> ARRAY['values', 'numeric_column_19']), (source_row.raw #>> ARRAY['values', 'numeric_column_20'])),
        (10::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_11']), (source_row.raw #>> ARRAY['values', 'text_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_21']), (source_row.raw #>> ARRAY['values', 'numeric_column_22'])),
        (11::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_12']), (source_row.raw #>> ARRAY['values', 'text_column_14']), (source_row.raw #>> ARRAY['values', 'numeric_column_23']), (source_row.raw #>> ARRAY['values', 'numeric_column_24'])),
        (12::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_13']), (source_row.raw #>> ARRAY['values', 'text_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_25']), (source_row.raw #>> ARRAY['values', 'numeric_column_26'])),
        (13::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_14']), (source_row.raw #>> ARRAY['values', 'text_column_16']), (source_row.raw #>> ARRAY['values', 'numeric_column_27']), (source_row.raw #>> ARRAY['values', 'numeric_column_28'])),
        (14::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_15']), (source_row.raw #>> ARRAY['values', 'text_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_29']), (source_row.raw #>> ARRAY['values', 'numeric_column_30']))
) AS position_data(position_number, declared_number_text, type_text, weight_text, gap_text)

WHERE NULLIF(BTRIM(position_data.declared_number_text), '')::smallint
        = position_data.position_number
  AND NULLIF(BTRIM(position_data.weight_text), '')::numeric >= 0
  AND UPPER(BTRIM(position_data.type_text)) IN ('X', 'Y', 'Z')) q;
SELECT 'PGDM_MICRO h5 3';
EXPLAIN (ANALYZE, FORMAT JSON, TIMING OFF) SELECT SUM(octet_length(to_jsonb(q)::text)) FROM (SELECT
    source_row.raw_id,
    position_data.position_number,
    ROUND(
        NULLIF(BTRIM(position_data.weight_text), '')::numeric * 1000
    )::integer,
    UPPER(BTRIM(position_data.type_text)),
    NULL::integer,
    NULL::integer,
    NULL::integer,
    CASE
        WHEN NULLIF(BTRIM(position_data.gap_text), '')::numeric > 0
        THEN ROUND(
            NULLIF(BTRIM(position_data.gap_text), '')::numeric * 1000
        )::integer
        ELSE NULL::integer
    END
FROM (SELECT raw_id,raw FROM public.raw_data WHERE raw_id BETWEEN 1 AND 50000) AS source_row
CROSS JOIN LATERAL (
SELECT 1::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_2']), (source_row.raw #>> ARRAY['values', 'text_column_4']), (source_row.raw #>> ARRAY['values', 'numeric_column_3']), (source_row.raw #>> ARRAY['values', 'numeric_column_4'])
UNION ALL
SELECT 2::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_3']), (source_row.raw #>> ARRAY['values', 'text_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_5']), (source_row.raw #>> ARRAY['values', 'numeric_column_6'])
UNION ALL
SELECT 3::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_4']), (source_row.raw #>> ARRAY['values', 'text_column_6']), (source_row.raw #>> ARRAY['values', 'numeric_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_8'])
UNION ALL
SELECT 4::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_5']), (source_row.raw #>> ARRAY['values', 'text_column_7']), (source_row.raw #>> ARRAY['values', 'numeric_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_10'])
UNION ALL
SELECT 5::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_6']), (source_row.raw #>> ARRAY['values', 'text_column_8']), (source_row.raw #>> ARRAY['values', 'numeric_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_12'])
UNION ALL
SELECT 6::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_7']), (source_row.raw #>> ARRAY['values', 'text_column_9']), (source_row.raw #>> ARRAY['values', 'numeric_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_14'])
UNION ALL
SELECT 7::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_8']), (source_row.raw #>> ARRAY['values', 'text_column_10']), (source_row.raw #>> ARRAY['values', 'numeric_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_16'])
UNION ALL
SELECT 8::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_9']), (source_row.raw #>> ARRAY['values', 'text_column_11']), (source_row.raw #>> ARRAY['values', 'numeric_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_18'])
UNION ALL
SELECT 9::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_10']), (source_row.raw #>> ARRAY['values', 'text_column_12']), (source_row.raw #>> ARRAY['values', 'numeric_column_19']), (source_row.raw #>> ARRAY['values', 'numeric_column_20'])
UNION ALL
SELECT 10::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_11']), (source_row.raw #>> ARRAY['values', 'text_column_13']), (source_row.raw #>> ARRAY['values', 'numeric_column_21']), (source_row.raw #>> ARRAY['values', 'numeric_column_22'])
UNION ALL
SELECT 11::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_12']), (source_row.raw #>> ARRAY['values', 'text_column_14']), (source_row.raw #>> ARRAY['values', 'numeric_column_23']), (source_row.raw #>> ARRAY['values', 'numeric_column_24'])
UNION ALL
SELECT 12::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_13']), (source_row.raw #>> ARRAY['values', 'text_column_15']), (source_row.raw #>> ARRAY['values', 'numeric_column_25']), (source_row.raw #>> ARRAY['values', 'numeric_column_26'])
UNION ALL
SELECT 13::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_14']), (source_row.raw #>> ARRAY['values', 'text_column_16']), (source_row.raw #>> ARRAY['values', 'numeric_column_27']), (source_row.raw #>> ARRAY['values', 'numeric_column_28'])
UNION ALL
SELECT 14::smallint, (source_row.raw #>> ARRAY['values', 'integer_column_15']), (source_row.raw #>> ARRAY['values', 'text_column_17']), (source_row.raw #>> ARRAY['values', 'numeric_column_29']), (source_row.raw #>> ARRAY['values', 'numeric_column_30'])
) AS position_data(position_number, declared_number_text, type_text, weight_text, gap_text)

WHERE NULLIF(BTRIM(position_data.declared_number_text), '')::smallint
        = position_data.position_number
  AND NULLIF(BTRIM(position_data.weight_text), '')::numeric >= 0
  AND UPPER(BTRIM(position_data.type_text)) IN ('X', 'Y', 'Z')) q;