#!/bin/bash
# Restores kaggle_challenge to its freshly generated state: empty destinations with restarted
# identities, counters at 0, no expansion versions and no job artefacts of the solution.
set -euo pipefail
DB=${1:-kaggle_challenge}
P="psql -U postgres -h /var/run/postgresql -qAtX -v ON_ERROR_STOP=1"
$P -d "$DB" -c "TRUNCATE public.table2, public.table5, public.table6, public.table1, public.table3, public.table4 RESTART IDENTITY CASCADE;"
$P -d "$DB" -c "CREATE TABLE IF NOT EXISTS public.pgdm_table_row_counts (schema_name text NOT NULL, table_name text NOT NULL, row_count bigint NOT NULL CHECK (row_count >= 0), initialized_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(), last_reconciled_at timestamptz, PRIMARY KEY (schema_name, table_name)); ALTER TABLE public.pgdm_table_row_counts OWNER TO pdm;" >/dev/null
$P -d "$DB" -c "UPDATE public.pgdm_table_row_counts SET row_count = 0 WHERE schema_name='public' AND table_name IN ('table1','table2','table3','table4','table5','table6');"
$P -d "$DB" -c "DROP SCHEMA IF EXISTS pgdm_expansion CASCADE;"
$P -d postgres_data_manager -c "DO \$\$BEGIN
  IF to_regclass('app_control.table_versions') IS NOT NULL THEN
    DELETE FROM app_control.table_versions WHERE database_name='$DB' AND operation_kind='cross_table_expand_v1';
  END IF;
  IF to_regclass('app_control.expansion_job_registrations') IS NOT NULL THEN
    DELETE FROM app_control.expansion_job_registrations WHERE database_name='$DB';
  END IF;
END\$\$;"

$P -d "$DB" -c "VACUUM (ANALYZE) public.table1, public.table2, public.table3, public.table4, public.table5, public.table6"
$P -d "$DB" -c "CHECKPOINT"
