#!/bin/bash
# Diagnostic: plan of the source scan (manifest + fingerprint) and of the global CTAS.
ROWS=$1
P="psql -U postgres -h /var/run/postgresql -qAtX -d kaggle_challenge"
OUT=/results/r${ROWS}/diag
mkdir -p "$OUT"
$P > "$OUT/explain_scan.txt" 2>&1 <<'SQL'
SET max_parallel_workers_per_gather = 2;
SET work_mem = '64MB';
SET enable_sort = off;
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT x.raw_schema, x.raw_hash, x.chunk_no, count(*) AS n,
       COALESCE(sum(x.h1), 0) AS h1, COALESCE(sum(x.raw_id), 0) AS s, COALESCE(sum(x.h2), 0) AS h2
FROM (
    SELECT r.raw_schema::text AS raw_schema, r.raw_hash::text AS raw_hash,
           ((r.raw_id - 1) / 50000)::integer AS chunk_no,
           hashtext(r.ctid::text)::bigint AS h1, r.raw_id,
           (COALESCE(hashtext(r.raw_id::text)::bigint, 0) + COALESCE(hashtext(r.raw_hash::text)::bigint, 0)
            + COALESCE(hashtext(r.raw_ingested_at::text)::bigint, 0) + COALESCE(hashtext(r.raw_schema::text)::bigint, 0)
            + COALESCE(hashtext(r.raw_tab::text)::bigint, 0) + COALESCE(jsonb_hash(r.raw)::bigint, 0)) AS h2
    FROM public.raw_data AS r
    WHERE r.raw_schema IN ('group001')
) AS x
GROUP BY 1, 2, 3;
SET enable_sort = on;
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*), sum(jsonb_hash(raw)::bigint) FROM public.raw_data;
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*), sum(hashtext(ctid::text)::bigint) FROM public.raw_data;
EXPLAIN (ANALYZE, BUFFERS)
SELECT raw_schema::text, raw_hash::text, count(*) FROM public.raw_data WHERE raw_schema IN ('group001') GROUP BY 1, 2;
SQL
cat "$OUT/explain_scan.txt" | grep -E "Execution Time|Sort|Aggregate|Workers|Disk|temp|Seq Scan|Gather" | head -40
