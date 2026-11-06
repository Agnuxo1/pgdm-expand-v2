# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Attribution-Recorded-On: 2026-11-06
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Reuse: preserve applicable notices and cite the original author.

"""DB Manager side of PGDM Expand v2 (see services/expansion_engine.py).

Mixed into PostgresAdminService.  Every remote step goes through
run_remote_command inside an expansion_timing_scope, so it is measured exactly
like the legacy path; the detached server job is measured by its own
clock_timestamp() records.
"""
from __future__ import annotations

import json
import os
import shlex
import time

from services import expansion_engine as engine


class ExpansionV2Mixin:
    EXPANSION_V2_ENV = "PDM_EXPAND_ENGINE"
    EXPANSION_V2_CONFIG_ENV = "PDM_EXPAND_V2_CONFIG"

    # ------------------------------------------------------------------ config
    def expansion_v2_enabled(self) -> bool:
        return str(os.environ.get(self.EXPANSION_V2_ENV, "v2")).strip().lower() != "legacy"

    def expansion_v2_config(self, overrides: dict | None = None) -> dict:
        env_value = os.environ.get(self.EXPANSION_V2_CONFIG_ENV)
        merged = {}
        if env_value:
            if env_value.startswith("@"):
                with open(env_value[1:], encoding="utf-8") as handle:
                    env_value = handle.read()
            merged.update(json.loads(env_value))
        merged.update(overrides or {})
        return engine.merge_config(merged)

    def _expansion_job_dir(self, job_id: str) -> str:
        return f"{self.remote_storage_root}/expansion_jobs/{job_id}"

    def _psql_command(self, database_name: str, extra: str = "") -> str:
        return (
            f"psql -h localhost -U {shlex.quote(self.sql_username)} "
            f"-d {shlex.quote(database_name)} -X -qAt -v ON_ERROR_STOP=1 {extra}"
        )

    # ------------------------------------------------------ version SQL (server)
    def _build_v2_registration_sql(self, prepared, source_versions, requested_by,
                                   workstation_name, database_name, job_id) -> str:
        from services import postgres_service as ps

        raw_schemas = list(prepared["raw_schemas"])
        source_schema_name = prepared["source_schema_name"]
        source_table_name = prepared["source_table_name"]
        source_full_table_name = f"{source_schema_name}.{source_table_name}"
        job = ps.sql_literal(job_id)
        registrations = f"{ps.CONTROL_SCHEMA_IDENT}.expansion_job_registrations"
        parts = [
            "\\set ON_ERROR_STOP 1",
            "SET client_min_messages = warning;",
            engine.control_ddl_sql(ps.CONTROL_SCHEMA_IDENT),
            f"SELECT EXISTS (SELECT 1 FROM {registrations} WHERE job_id = {job}) AS pgdm_registered \\gset",
            "\\if :pgdm_registered",
            f"SELECT 'PGDM_VERSIONS ' || versions::text FROM {registrations} WHERE job_id = {job};",
            "\\else",
            "BEGIN;",
        ]
        lock_keys = sorted(
            f"{ps.CONTROL_SCHEMA}.table_versions:{database_name}:{d['schema_name']}:{d['pure_table_name']}"
            for d in prepared["destinations"]
        )
        for lock_key in lock_keys:
            parts.append(f"SELECT pg_advisory_xact_lock(hashtextextended({ps.sql_literal(lock_key)}, 0));")
        version_vars = []
        for index, destination in enumerate(prepared["destinations"], start=1):
            schema_name = destination["schema_name"]
            table_name = destination["pure_table_name"]
            full_table_name = destination["table_name"]
            extra = {
                "source_versions": source_versions,
                "raw_schemas": raw_schemas,
                "destination_columns": self._dedupe_non_empty_strings(destination.get("destination_columns")),
                "destination_read_relations": [
                    {"schema_name": str(s).strip(), "table_name": str(t).strip()}
                    for s, t in (destination.get("read_relations") or [])
                    if str(s).strip() and str(t).strip()
                ],
            }
            dependency_sql = (
                "(:'pgdm_manifest'::jsonb || "
                + ps.sql_literal(json.dumps(extra, ensure_ascii=False, sort_keys=True))
                + "::jsonb)"
            )
            version_notes = (
                f"Versioned expansion from {source_full_table_name}. "
                "Exact raw_schema scope: " + ", ".join(raw_schemas)
                + ". No additional dump was created."
                + f" Executed by PGDM Expand v2 job {job_id}."
            )
            history = self._build_server_version_history_expression(
                "next_version.version_code", destination["version_title"], requested_by,
                workstation_name, destination["sql_recipe"], version_notes,
            )
            var = f"pgdm_v_{index}"
            version_vars.append(var)
            parts.append(f"""
WITH next_version_number AS (
    SELECT COALESCE(MAX(version_code::integer) + 1, 0) AS value
    FROM {ps.CONTROL_TABLE_VERSIONS}
    WHERE database_name = {ps.sql_literal(database_name)}
      AND schema_name = {ps.sql_literal(schema_name)}
      AND table_name = {ps.sql_literal(table_name)}
),
next_version AS (
    SELECT CASE WHEN value < 10000 THEN lpad(value::text, 4, '0') ELSE value::text END AS version_code
    FROM next_version_number
),
inserted_version AS (
    INSERT INTO {ps.CONTROL_TABLE_VERSIONS} (
        database_name, schema_name, table_name, version_code, version_title, created_by,
        workstation_name, sql_recipe, restored_from_version, version_history_log,
        version_history_format, raw_dump_path, raw_hash, raw_ingested_at, raw_schema, operation_kind
    )
    SELECT {ps.sql_literal(database_name)}, {ps.sql_literal(schema_name)}, {ps.sql_literal(table_name)},
        next_version.version_code, {ps.sql_literal(destination['version_title'])},
        {ps.sql_literal(requested_by)}, {ps.sql_literal(workstation_name)},
        {ps.sql_literal(destination['sql_recipe'])}, NULL, {history},
        {ps.sql_literal(self.VERSION_HISTORY_FORMAT_ENTRY)}, NULL, NULL, NULL, NULL,
        {ps.sql_literal(self.CROSS_TABLE_EXPANSION_OPERATION_KIND)}
    FROM next_version
    RETURNING id, version_code
),
inserted_dependency AS (
    INSERT INTO {ps.CONTROL_TABLE_VERSION_DEPENDENCIES} (
        table_version_id, dependency_kind, source_database_name, source_schema_name,
        source_table_name, dependency_payload
    )
    SELECT inserted_version.id, {ps.sql_literal(self.CROSS_TABLE_EXPANSION_DEPENDENCY_KIND)},
        {ps.sql_literal(database_name)}, {ps.sql_literal(source_schema_name)},
        {ps.sql_literal(source_table_name)}, {dependency_sql}
    FROM inserted_version
    RETURNING table_version_id
)
SELECT json_build_object(
    'table_name', {ps.sql_literal(full_table_name)},
    'version_code', inserted_version.version_code,
    'dependency_count', (SELECT COUNT(*) FROM inserted_dependency)
)::text AS {var}
FROM inserted_version \\gset""".strip())
        array_sql = "jsonb_build_array(" + ", ".join(f":'{v}'::jsonb" for v in version_vars) + ")"
        parts.extend([
            f"INSERT INTO {registrations} (job_id, database_name, versions) "
            f"VALUES ({job}, {ps.sql_literal(database_name)}, {array_sql});",
            "COMMIT;",
            f"SELECT 'PGDM_VERSIONS ' || versions::text FROM {registrations} WHERE job_id = {job};",
            "\\endif",
        ])
        return "\n".join(parts) + "\n"

    def _source_raw_id_is_unique(self, database_name, prepared) -> bool:
        """Chunking by raw_id requires raw_id to identify one source row (PK or unique index)."""
        from services import postgres_service as ps

        source = f"{ps.sql_ident(prepared['source_schema_name'])}.{ps.sql_ident(prepared['source_table_name'])}"
        sql = (
            "SELECT EXISTS (SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
            "AND a.attnum = i.indkey[0] WHERE i.indrelid = " + ps.sql_literal(source) + "::regclass "
            "AND i.indisunique AND i.indnatts = 1 AND i.indpred IS NULL AND a.attname = 'raw_id')"
        )
        output = self.run_remote_command(self._psql_command(database_name, "-c " + shlex.quote(sql)))
        return output.strip().splitlines()[-1].strip() in {"t", "true"}

    # ------------------------------------------------------------ job creation
    def _create_or_resume_expansion_job(self, database_name, prepared, segments, config, source_versions,
                                        cancel_event=None):
        from services import postgres_service as ps

        s = ps.sql_ident(engine.ENGINE_SCHEMA)
        digest = engine.spec_hash(prepared, config)
        job_id = engine.new_job_id()
        source = f"{ps.sql_ident(prepared['source_schema_name'])}.{ps.sql_ident(prepared['source_table_name'])}"
        scope_array = "ARRAY[" + ", ".join(ps.sql_literal(v) for v in prepared["raw_schemas"]) + "]::text[]"
        segment_rows = []
        for number, segment in enumerate(segments, start=1):
            names = "ARRAY[" + ", ".join(ps.sql_literal(i["destination"]["table_name"]) for i in segment["items"]) + "]::text[]"
            segment_rows.append(f"(pgdm_job, {number}, {ps.sql_literal(segment['kind'])}, {names})")
        chunked_numbers = [n for n, seg in enumerate(segments, start=1) if seg["kind"] == "chunked"]
        chunk_inserts = "\n".join(f"""
    INSERT INTO {s}.job_chunks (job_id, segment_no, chunk_no, lo, hi)
    SELECT pgdm_job, {number}, g - 1,
           pgdm_min + (g - 1) * pgdm_width,
           LEAST(pgdm_max, pgdm_min + g * pgdm_width - 1)
    FROM generate_series(1, GREATEST(1, CEIL((pgdm_max - pgdm_min + 1)::numeric / pgdm_width)::int)) AS g
    WHERE pgdm_min IS NOT NULL;""" for number in chunked_numbers)
        config_json = ps.sql_literal(json.dumps(config, sort_keys=True))
        versions_json = ps.sql_literal(json.dumps(source_versions, sort_keys=True))
        destinations_array = "ARRAY[" + ", ".join(ps.sql_literal(d["table_name"]) for d in prepared["destinations"]) + "]::text[]"
        sql = f"""
BEGIN;
SET LOCAL client_min_messages = warning;
SELECT pg_advisory_xact_lock(hashtextextended('pgdm_v2_job_create', 0));
{engine.engine_ddl_guarded_sql()}
DO $pgdm_v2_create$
DECLARE
    pgdm_job uuid;
    pgdm_min bigint;
    pgdm_max bigint;
    pgdm_rows double precision;
    pgdm_width bigint;
    missing_schemas text;
BEGIN
    SELECT job_id INTO pgdm_job FROM {s}.jobs
    WHERE spec_hash = {ps.sql_literal(digest)}
      AND (status NOT IN ('completed', 'cancelled') OR (status = 'completed' AND acknowledged_at IS NULL))
    ORDER BY created_at DESC LIMIT 1;
    IF pgdm_job IS NOT NULL THEN
        IF (SELECT source_versions FROM {s}.jobs WHERE job_id = pgdm_job) IS DISTINCT FROM {versions_json}::jsonb
           AND (SELECT status FROM {s}.jobs WHERE job_id = pgdm_job) <> 'completed' THEN
            RAISE EXCEPTION 'The Raw version references of the source changed since unfinished expansion job % started; it cannot be resumed.', pgdm_job;
        END IF;
        -- A new request (re)starts the job: an old cancel request must not stop it.
        UPDATE {s}.jobs SET cancel_requested = false WHERE job_id = pgdm_job AND status <> 'completed';
        RAISE NOTICE 'PGDM_RESUME %', pgdm_job;
        PERFORM set_config('pgdm.job', pgdm_job::text, true);
        PERFORM set_config('pgdm.resumed', 'true', true);
        RETURN;
    END IF;
    SELECT string_agg(expected, ', ' ORDER BY expected) INTO missing_schemas
    FROM unnest({scope_array}) AS expected
    WHERE NOT EXISTS (SELECT 1 FROM {source} WHERE raw_schema = expected);
    IF missing_schemas IS NOT NULL THEN
        RAISE EXCEPTION 'raw_schema has no source rows: %.', missing_schemas;
    END IF;
    pgdm_job := {ps.sql_literal(job_id)}::uuid;
    SELECT min(raw_id), max(raw_id) INTO pgdm_min, pgdm_max FROM {source}
    WHERE raw_schema = ANY ({scope_array});
    SELECT GREATEST(reltuples, 1) INTO pgdm_rows FROM pg_class WHERE oid = {ps.sql_literal(source)}::regclass;
    IF pgdm_rows IS NULL OR pgdm_rows <= 1 THEN
        pgdm_rows := GREATEST(COALESCE(pgdm_max - pgdm_min + 1, 1), 1);
    END IF;
    pgdm_width := GREATEST(1, CEIL({int(config['chunk_rows'])} * GREATEST(COALESCE(pgdm_max - pgdm_min + 1, 1), 1) / pgdm_rows)::bigint);
    INSERT INTO {s}.jobs (job_id, spec_hash, source_table, raw_schemas, destinations, status, config,
                          source_versions, chunk_min, chunk_width)
    VALUES (pgdm_job, {ps.sql_literal(digest)}, {ps.sql_literal(prepared['source_schema_name'] + '.' + prepared['source_table_name'])},
            {scope_array}, {destinations_array}, 'created', {config_json}::jsonb,
            {versions_json}::jsonb, COALESCE(pgdm_min, 0), pgdm_width);
    INSERT INTO {s}.job_segments (job_id, segment_no, kind, destinations) VALUES
    {', '.join(segment_rows)};
{chunk_inserts}
    PERFORM set_config('pgdm.job', pgdm_job::text, true);
    PERFORM set_config('pgdm.resumed', 'false', true);
END
$pgdm_v2_create$;
SELECT json_build_object(
    'job_id', current_setting('pgdm.job'),
    'resumed', current_setting('pgdm.resumed')::boolean,
    'status', (SELECT status FROM {s}.jobs WHERE job_id = current_setting('pgdm.job')::uuid),
    'chunks', (SELECT count(*) FROM {s}.job_chunks WHERE job_id = current_setting('pgdm.job')::uuid),
    'chunks_done', (SELECT count(*) FROM {s}.job_chunks WHERE job_id = current_setting('pgdm.job')::uuid AND status = 'done'),
    'attempts', (SELECT attempts FROM {s}.jobs WHERE job_id = current_setting('pgdm.job')::uuid)
)::text;
COMMIT;
"""
        output = self.run_remote_command(self._psql_command(database_name, "-f -"), stdin_text=sql,
                                         cancel_event=cancel_event)
        for line in output.splitlines()[::-1]:
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        raise RuntimeError("Could not create the expansion job.")

    # --------------------------------------------------------------- execution
    def execute_cross_table_expansion_v2(self, database_name, prepared, source_versions, requested_by,
                                         workstation_name, timing_report, cancel_event=None,
                                         progress_callback=None, post_commit_callback=None,
                                         engine_config=None) -> dict:
        from services import postgres_service as ps

        with self.expansion_timing_scope(timing_report, "prepare", "Plan parallel resumable expansion job"):
            config = self.expansion_v2_config(engine_config)
            prepared["source_raw_id_unique"] = self._source_raw_id_is_unique(database_name, prepared)
            segments = engine.classify_destinations(type(self), prepared)
        with self.expansion_timing_scope(timing_report, "execute", "Create or resume expansion job"):
            job = self._create_or_resume_expansion_job(database_name, prepared, segments, config,
                                                       self._canonical_source_version_references(source_versions),
                                                       cancel_event)
        job_id = job["job_id"]
        if job.get("resumed"):
            self._notify_progress(progress_callback, "execute", 5,
                                  f"Resuming job {job_id}: {job['chunks_done']}/{job['chunks']} chunks already committed.")
        with self.expansion_timing_scope(timing_report, "prepare", "Build server-side job files"):
            registration_sql = self._build_v2_registration_sql(
                prepared, source_versions, requested_by, workstation_name, database_name, job_id)
            files = engine.build_job_files(
                type(self), prepared, segments, job_id, config, database_name, self.sql_username,
                ps.DATA_TABLE_ROW_COUNTS, registration_sql, ps.CONTROL_DB)
            payload = engine.pack_files(files)
        job_dir = f"{self._expansion_job_dir(job_id)}/launch-{int(time.time() * 1000)}"
        if job.get("status") == "completed":
            # Finished in the background after the Manager lost its connection:
            # collect it instead of expanding the same data twice.
            state = "completed"
        else:
            with self.expansion_timing_scope(timing_report, "execute", "Upload job files and launch detached runner"):
                self.run_remote_command(
                    f"mkdir -p {shlex.quote(job_dir)} && base64 -d | tar -xz -C {shlex.quote(job_dir)} && "
                    f"cd {shlex.quote(job_dir)} && "
                    "(setsid nohup bash runner.sh > runner.out 2>&1 < /dev/null &) && echo launched",
                    stdin_text=payload, cancel_event=cancel_event)
            state = self.wait_for_expansion_job(database_name, job_id, timing_report, cancel_event=cancel_event,
                                                progress_callback=progress_callback,
                                                launched_after_attempt=int(job.get("attempts") or 0))
        if post_commit_callback:
            post_commit_callback()
        result = self._collect_expansion_job_result(database_name, prepared, source_versions, job_id,
                                                    timing_report, state)
        with self.expansion_timing_scope(timing_report, "refresh", "Acknowledge completed expansion job"):
            self.run_remote_command(self._psql_command(database_name, "-c " + shlex.quote(
                f"UPDATE {ps.sql_ident(engine.ENGINE_SCHEMA)}.jobs SET acknowledged_at = clock_timestamp() "
                f"WHERE job_id = '{job_id}'")))
        return result

    def wait_for_expansion_job(self, database_name, job_id, timing_report=None, cancel_event=None,
                               progress_callback=None, poll_seconds: float = 1.0,
                               launched_after_attempt: int = 0) -> str:
        """Block until the detached runner finishes.  Status comes from the job tables and
        liveness from the coordinator's advisory lock (held for the whole run).  Excluded
        from totals: the job's own clock_timestamp() records are reported instead."""
        from services import postgres_service as ps

        s = ps.sql_ident(engine.ENGINE_SCHEMA)
        job = ps.sql_literal(job_id)
        probe = f"""
SELECT 'PGDM_WAIT ' || j.status || ':' || j.attempts || ' '
    || CASE WHEN EXISTS (
           SELECT 1 FROM pg_stat_activity a
           WHERE a.application_name = {ps.sql_literal('pgdm_v2_coord_' + job_id)}
       ) THEN 'alive' ELSE 'idle' END || ' '
    || (SELECT count(*) FILTER (WHERE status = 'done') || '/' || count(*) FROM {s}.job_chunks c WHERE c.job_id = j.job_id)
FROM {s}.jobs j WHERE j.job_id = {job};"""
        wait_sql = f"SELECT pg_sleep({max(0.05, float(poll_seconds))});"
        cancel_sent = False
        idle_polls = 0
        started = time.monotonic()
        with self.expansion_timing_scope(timing_report, "execute", "Wait for server-side job (envelope)",
                                         record_local_cpu=False, remote_include_in_total=False):
            while True:
                if cancel_event is not None and cancel_event.is_set() and not cancel_sent:
                    self.run_remote_command(self._psql_command(
                        database_name,
                        "-c " + shlex.quote(f"UPDATE {s}.jobs SET cancel_requested = true WHERE job_id = {job}")))
                    cancel_sent = True
                output = self.run_remote_command(
                    self._psql_command(database_name, "-c " + shlex.quote(wait_sql) + " -c " + shlex.quote(probe)))
                status, attempts, alive, progress = "", 0, "idle", ""
                for line in output.splitlines():
                    if line.startswith("PGDM_WAIT "):
                        parts = line.split()
                        status, _, attempt_text = parts[1].partition(":")
                        attempts = int(attempt_text or 0)
                        alive, progress = parts[2], parts[3] if len(parts) > 3 else ""
                if progress and progress_callback:
                    done, _, total = progress.partition("/")
                    try:
                        pct = 10 + 85 * int(done) / max(int(total), 1)
                    except ValueError:
                        pct = 10
                    self._notify_progress(progress_callback, "execute", pct, f"Chunks committed: {progress}")
                if status == "completed":
                    return "completed"
                # A 'failed' status left by an earlier attempt does not count until the
                # runner launched now has started its own attempt.
                if status == "failed" and attempts > launched_after_attempt and alive != "alive":
                    return "failed"
                if alive == "alive":
                    idle_polls = 0
                    continue
                idle_polls += 1
                # No runner holds the job lock: give a freshly launched runner time to start.
                if idle_polls >= 5 and time.monotonic() - started > 15:
                    return "died"

    def _collect_expansion_job_result(self, database_name, prepared, source_versions, job_id, timing_report,
                                      state) -> dict:
        from services import postgres_service as ps

        s = ps.sql_ident(engine.ENGINE_SCHEMA)
        job = ps.sql_literal(job_id)
        sql = f"""
SELECT json_build_object(
  'status', j.status, 'last_error', j.last_error, 'attempts', j.attempts, 'versions', j.versions,
  'manifest', j.manifest, 'config', j.config, 'workers_used', j.workers_used,
  'attempt_wall', EXTRACT(EPOCH FROM j.finished_at - j.attempt_started_at),
  'earlier_attempts_wall', (SELECT COALESCE(SUM(EXTRACT(EPOCH FROM COALESCE(a.ended_at, a.heartbeat_at, GREATEST(
            (SELECT max(c.finished_at) FROM {s}.job_chunks c WHERE c.job_id = j.job_id AND c.attempt = a.attempt_no),
            (SELECT max(g.finished_at) FROM {s}.job_segments g WHERE g.job_id = j.job_id AND g.attempt = a.attempt_no)),
            a.started_at) - a.started_at)), 0)
        FROM {s}.job_attempts a WHERE a.job_id = j.job_id AND a.attempt_no < j.attempts),
  'data_wall', EXTRACT(EPOCH FROM j.data_completed_at - j.attempt_started_at),
  'version_wall', EXTRACT(EPOCH FROM j.finished_at - j.data_completed_at),
  'segments', (SELECT json_agg(json_build_object('n', g.segment_no, 'kind', g.kind, 'destinations', g.destinations,
                'rows', g.rows, 'seconds', EXTRACT(EPOCH FROM g.finished_at - g.started_at),
                'chunks', (SELECT count(*) FROM {s}.job_chunks c WHERE c.job_id = g.job_id AND c.segment_no = g.segment_no))
                ORDER BY g.segment_no) FROM {s}.job_segments g WHERE g.job_id = j.job_id),
  'statement_seconds', (SELECT json_object_agg(k, v) FROM (
        SELECT e.key AS k, SUM(e.value::double precision) AS v
        FROM {s}.job_chunks c, jsonb_each_text(c.statement_seconds) e WHERE c.job_id = j.job_id GROUP BY e.key) t),
  'resumed_chunks', (SELECT count(*) FROM {s}.job_chunks c WHERE c.job_id = j.job_id AND c.status = 'done'
                     AND c.finished_at < j.attempt_started_at)
)::text FROM {s}.jobs j WHERE j.job_id = {job};
"""
        with self.expansion_timing_scope(timing_report, "execute", "Read job telemetry"):
            output = self.run_remote_command(self._psql_command(database_name, "-c " + shlex.quote(sql)))
        info = json.loads(output.strip().splitlines()[-1])
        if state != "completed" or info["status"] != "completed":
            tail = ""
            try:
                tail = self.run_remote_command(
                    f"tail -n 20 {shlex.quote(self._expansion_job_dir(job_id))}/runner.log")
            except Exception:
                pass
            if state == "cancelled":
                raise ps.OperationCancelledError(
                    f"Expansion job {job_id} cancelled; committed chunks are kept and the job can be resumed.")
            raise RuntimeError(
                f"Expansion job {job_id} ended with status {info['status']}: {info.get('last_error') or ''}\n{tail}\n"
                "Committed chunks are kept; run Expand again with the same configuration to resume.")
        workers = int(info.get("workers_used") or 1)
        attempt_wall = float(info.get("attempt_wall") or 0.0)
        data_wall = float(info.get("data_wall") or 0.0)
        version_wall = float(info.get("version_wall") or 0.0)
        earlier_wall = float(info.get("earlier_attempts_wall") or 0.0)
        if earlier_wall > 0:
            self._append_expansion_timing(
                timing_report, "execute",
                f"Earlier interrupted attempts of this job ({int(info.get('attempts') or 1) - 1})",
                earlier_wall, "postgresql_backend_wall",
                details=("Elapsed server time of previous attempts up to their last committed work; "
                         "their committed chunks were reused, so this work is part of the result."))
        self._append_expansion_timing(
            timing_report, "execute",
            f"Server-side expansion job: data phase (all segments, {workers} worker(s))",
            data_wall, "postgresql_backend_wall",
            details=("Elapsed clock_timestamp() of the detached job from runner start to data commit and "
                     "manifest merge; parallel work is counted as elapsed time, SSH transport excluded."))
        self._append_expansion_timing(
            timing_report, "version", "Server-side version registration and job completion",
            version_wall, "postgresql_backend_wall",
            details="Elapsed clock_timestamp() from data commit to job completion (control database).")
        for segment in info.get("segments") or []:
            self._append_expansion_timing(
                timing_report, "execute",
                f"Segment {segment['n']} ({segment['kind']}, {segment['chunks']} chunk(s)): "
                + ", ".join(segment["destinations"]),
                float(segment.get("seconds") or 0.0), "postgresql_backend_wall",
                details="Diagnostic breakdown of the data phase above.", include_in_total=False)
        for name, seconds in sorted((info.get("statement_seconds") or {}).items()):
            self._append_expansion_timing(
                timing_report, "execute", f"Summed per-chunk statement time for {name}",
                float(seconds), "postgresql_backend_cpu_sum",
                details="Sum over chunks and workers (diagnostic; overlaps in parallel).",
                include_in_total=False)
        destination_rows = {}
        for segment in info.get("segments") or []:
            for name, rows in (segment.get("rows") or {}).items():
                destination_rows[name] = destination_rows.get(name, 0) + int(rows)
        timing_report["destination_rows"] = [
            {"table_name": d["table_name"], "rows": int(destination_rows.get(d["table_name"], 0))}
            for d in prepared["destinations"]
        ]
        timing_report["total_rows_inserted"] = sum(i["rows"] for i in timing_report["destination_rows"])
        manifest = info.get("manifest") or {}
        timing_report["source_rows"] = int(manifest.get("expected_row_count") or 0)
        timing_report["expansion_job"] = {
            "job_id": job_id, "attempts": info.get("attempts"), "resumed_chunks": info.get("resumed_chunks"),
            "workers_used": workers,
            "config": info.get("config"),
        }
        versions = list(info.get("versions") or [])
        return {
            "engine": "v2",
            "job_id": job_id,
            "source_database_name": database_name,
            "source_schema_name": prepared["source_schema_name"],
            "source_table_name": prepared["source_table_name"],
            "raw_schemas": list(prepared["raw_schemas"]),
            "source_versions": source_versions,
            "dependency_manifest": manifest,
            "destinations": prepared["destinations"],
            "timing_report": timing_report,
            "registered_versions": versions,
        }

    # ------------------------------------------------------------ inspection
    def list_expansion_jobs(self, database_name: str, limit: int = 20) -> list[dict]:
        from services import postgres_service as ps

        s = ps.sql_ident(engine.ENGINE_SCHEMA)
        sql = f"""
SELECT COALESCE(json_agg(x ORDER BY x.created_at DESC), '[]'::json)::text FROM (
  SELECT j.job_id, j.status, j.created_at, j.attempts, j.destinations, j.last_error,
         (SELECT count(*) FROM {s}.job_chunks c WHERE c.job_id = j.job_id) AS chunks,
         (SELECT count(*) FROM {s}.job_chunks c WHERE c.job_id = j.job_id AND c.status = 'done') AS chunks_done
  FROM {s}.jobs j ORDER BY j.created_at DESC LIMIT {int(limit)}) x;
"""
        output = self.run_remote_command(
            f"{self._psql_command(database_name)} -c {shlex.quote(sql)} 2>/dev/null || echo '[]'")
        return json.loads(output.strip().splitlines()[-1] or "[]")
