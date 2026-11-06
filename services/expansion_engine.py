# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Attribution-Recorded-On: 2026-11-06
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Reuse: preserve applicable notices and cite the original author.

"""PGDM Expand v2: resumable, parallel, server-side cross-table expansion.

The Windows DB Manager still prepares and validates every recipe exactly as
before (same parser, same guards, same preflight).  What changes is how the
validated INSERT ... SELECT statements are executed on the Linux server:

* The work runs as a detached job on the server (``setsid nohup bash
  runner.sh``).  An SSH interruption no longer aborts the transaction: the job
  keeps running and the Manager re-attaches to it.
* Destinations are split into ordered segments.  Statements whose result over
  the whole source equals the union of their results over disjoint ``raw_id``
  ranges (row-wise statements, see ``classify_destinations``) run chunk by
  chunk on K parallel ``psql`` workers.  Statements that need the whole source
  (``DISTINCT``, aggregates, windows, ...) run once, in a single transaction.
* Every chunk is ONE transaction that inserts its rows, updates the managed
  row counters and marks the chunk done in ``pgdm_expansion.job_chunks``.  A
  chunk is therefore either completely applied and recorded or not at all, so
  a resumed job never duplicates rows and never loses committed work.
* The raw_hash dependency manifest is accumulated per chunk inside the same
  transaction and merged at the end; while the job runs a coordinator session
  holds ``LOCK raw_data IN SHARE MODE`` so the source cannot change under it.
* Version registration in the control database is idempotent: it records the
  job id in ``app_control.expansion_job_registrations`` in the same
  transaction as the versions, so it happens exactly once even if the job is
  resumed after a crash between "data complete" and "versions registered".

Timing: the runner records clock_timestamp() for every phase in the job
tables; the Manager reports the elapsed server wall time of each phase
(included in MEASURED PROCESSING TOTAL) and, for transparency, the summed
per-statement time of all chunks (diagnostic only, excluded from totals).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import shlex
import tarfile
import uuid

ENGINE_SCHEMA = "pgdm_expansion"
ENGINE_VERSION = 3

# Words that make a statement depend on rows other than the current source
# row; such statements are executed once over the complete source.
_SET_WORDS = {
    "distinct", "group", "having", "over", "window", "limit", "offset",
    "union", "intersect", "except", "fetch", "tablesample",
}
_AGGREGATES = {
    "count", "sum", "avg", "min", "max", "array_agg", "string_agg", "json_agg",
    "jsonb_agg", "json_object_agg", "jsonb_object_agg", "bool_and", "bool_or",
    "every", "bit_and", "bit_or", "bit_xor", "stddev", "stddev_pop",
    "stddev_samp", "variance", "var_pop", "var_samp", "corr", "covar_pop",
    "covar_samp", "regr_avgx", "regr_avgy", "regr_count", "regr_intercept",
    "regr_r2", "regr_slope", "regr_sxx", "regr_sxy", "regr_syy", "mode",
    "percentile_cont", "percentile_disc", "rank", "dense_rank", "row_number",
    "ntile", "lag", "lead", "first_value", "last_value", "nth_value",
    "cume_dist", "percent_rank", "xmlagg", "range_agg", "range_intersect_agg",
    "any_value",
}

DEFAULT_CONFIG = {
    # Hand-tuned control; tools/darwin_cage_tuner.py searches around it (see README).
    "workers": "auto",
    "workers_per_core": 1.0,
    "global_parallel": 2,
    "chunk_rows": 50000,
    "source_mode": "plain",
    "session_gucs": {
        "jit": "off",
        "work_mem": "64MB",
        "synchronous_commit": "off",
    },
    "global_gucs": {
        "jit": "off",
        "work_mem": "64MB",
    },
}


def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def sql_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def merge_config(overrides: dict | None) -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)
        else:
            config[key] = value
    if str(config["workers"]).lower() != "auto":
        config["workers"] = max(1, int(config["workers"]))
    else:
        config["workers"] = "auto"
    config["workers_per_core"] = float(config.get("workers_per_core") or 1.0)
    config["global_parallel"] = max(0, int(config.get("global_parallel") or 0))
    if config.get("source_mode") not in ("plain", "detoast"):
        raise RuntimeError(f"Unsupported source_mode: {config.get('source_mode')!r}")
    config["chunk_rows"] = max(1000, int(config["chunk_rows"]))
    return config


_GUC_NAME = re.compile(r"^[a-z_][a-z0-9_.]*$")
_GUC_VALUE = re.compile(r"^[A-Za-z0-9_.:+\- ]{1,64}$")
_ALLOWED_GUCS = {
    "jit", "work_mem", "synchronous_commit", "enable_hashjoin",
    "enable_mergejoin", "enable_nestloop", "enable_seqscan", "random_page_cost",
    "max_parallel_workers_per_gather", "parallel_setup_cost", "enable_sort",
    "parallel_tuple_cost", "min_parallel_table_scan_size", "hash_mem_multiplier",
    "temp_buffers", "commit_delay", "commit_siblings",
}


def guc_sql(gucs: dict) -> str:
    lines = []
    for name, value in sorted((gucs or {}).items()):
        if name not in _ALLOWED_GUCS or not _GUC_NAME.match(name) or not _GUC_VALUE.match(str(value)):
            raise RuntimeError(f"Unsupported expansion tuning parameter: {name}={value!r}")
        lines.append(f"SET LOCAL {name} = {sql_literal(value)};")
    return "\n".join(lines)


def classify_destinations(service_cls, prepared: dict) -> list[dict]:
    """Split the destinations into ordered execution segments.

    A destination is chunkable when every statement:
      * reads the source exactly once and contains none of the set-level
        constructs in _SET_WORDS / _AGGREGATES (row-wise over the source);
      * keeps the source as the first FROM item and uses no RIGHT, FULL or
        NATURAL join, so each output row depends on one source row and
        restricting the source partitions the result exactly;
      * does not read its own destination;
      * reads earlier destinations only if they were completed in an earlier
        segment, or if they are chunked in the same segment AND the statement
        joins every occurrence through a bare ``AND`` term of its ON clause,
        ``<relation>.<column> = <source alias>.raw_id``, where that column is filled from ``raw_id`` by that destination's
        recipe (so a chunk only ever matches rows produced from its own
        source rows).
    Everything else runs once, globally, in recipe order.
    """
    placeholder = service_cls.CROSS_TABLE_SOURCE_PLACEHOLDER
    destinations = prepared["destinations"]
    raw_id_columns = {}
    info = []
    for destination in destinations:
        key = (destination["schema_name"], destination["pure_table_name"])
        templates = destination["statement_templates"]
        reasons = []
        for template in templates:
            masked = service_cls._mask_sql_literals_and_comments(template)
            if masked.count(placeholder) != 1:
                reasons.append("reads the source more than once")
            tokens = service_cls._tokenize_managed_sql(template.replace(placeholder, "__pgdm_src__"))
            words = {value for kind, value, _depth in tokens if kind == "word"}
            hits = sorted((words & _SET_WORDS) | (words & _AGGREGATES))
            if hits:
                reasons.append("set-level construct: " + ", ".join(hits))
            selects = sum(1 for kind, value, _depth in tokens if kind == "word" and value == "select")
            if selects != 1:
                reasons.append("contains a subquery")
            reasons.extend(_row_preservation_problems(masked, placeholder))
        if key in {tuple(r) for r in destination.get("read_relations") or []}:
            reasons.append("reads its own destination")
        columns = _raw_id_target_columns(service_cls, destination, placeholder)
        raw_id_columns[key] = columns
        info.append({"destination": destination, "key": key, "reasons": reasons})

    segments = []
    completed = set()
    current = None
    for item in info:
        destination = item["destination"]
        reasons = list(item["reasons"])
        if not reasons and not prepared.get("source_raw_id_unique", False):
            reasons.append("source raw_id is not guaranteed unique")
        if not reasons and current and current["kind"] == "chunked":
            in_segment = {d["key"] for d in current["items"]}
            for relation in destination.get("read_relations") or []:
                relation = tuple(relation)
                if relation in completed:
                    continue
                if relation in in_segment and _joins_on_raw_id(
                    service_cls, destination, relation, raw_id_columns.get(relation) or set(), placeholder
                ) and not _has_word(service_cls, destination, "or"):
                    continue
                reasons.append(f"reads {relation[0]}.{relation[1]} without a raw_id join")
        elif not reasons:
            # Starts a new chunked segment: everything in the current global
            # segment will be committed before it runs.
            ready = set(completed)
            if current is not None:
                ready.update(d["key"] for d in current["items"])
            for relation in destination.get("read_relations") or []:
                if tuple(relation) not in ready:
                    reasons.append(f"reads {relation[0]}.{relation[1]} before it is complete")
        kind = "global" if reasons else "chunked"
        if current is None or current["kind"] != kind:
            if current is not None:
                completed.update(d["key"] for d in current["items"])
            current = {"kind": kind, "items": []}
            segments.append(current)
        current["items"].append({"key": item["key"], "destination": destination, "reasons": reasons})
    return segments


def _top_level_from_end(masked: str) -> int:
    """Index just after the FROM keyword of the top-level SELECT, or -1."""
    match = re.search(r"\bselect\b", masked, flags=re.I)
    if not match:
        return -1
    depth = 0
    for found in re.finditer(r"[()]|\bfrom\b", masked[match.end():], flags=re.I):
        token = found.group(0)
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
        elif depth == 0:
            return match.end() + found.end()
    return -1


def _row_preservation_problems(masked: str, placeholder: str) -> list[str]:
    """Reasons why restricting the source would not partition the statement's result."""
    problems = []
    start = _top_level_from_end(masked)
    if start < 0 or not masked[start:].lstrip().startswith(placeholder):
        problems.append("the source is not the first FROM item")
    if re.search(r"\b(?:right|full)\s+(?:outer\s+)?join\b|\bnatural\b", masked, flags=re.I):
        problems.append("join type does not preserve source rows")
    return problems


def _on_clause_terms(masked: str, start: int) -> list[str]:
    """Top-level AND terms of the first ON clause at or after ``start``."""
    depth = 0
    term_start = -1
    end = len(masked)
    terms = []
    for found in re.finditer(r"[();]|\b(?:on|and|join|where)\b", masked[start:], flags=re.I):
        token = found.group(0).lower()
        position = start + found.start()
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
        elif depth != 0:
            continue
        elif term_start < 0:
            if token == "on":
                term_start = start + found.end()
            elif token in {"join", "where", ";"}:
                return []
        elif token == "and":
            terms.append(masked[term_start:position])
            term_start = start + found.end()
        elif token in {"join", "where", ";", "on"}:
            end = position
            break
    if term_start < 0:
        return []
    terms.append(masked[term_start:end])
    return [re.sub(r"\s+(?:inner|left|cross)(?:\s+outer)?\s*$", "", term, flags=re.I).strip() for term in terms]


def _has_word(service_cls, destination, word: str) -> bool:
    for template in destination["statement_templates"]:
        for kind, value, _depth in service_cls._tokenize_managed_sql(template):
            if kind == "word" and value == word:
                return True
    return False


def _raw_id_target_columns(service_cls, destination, placeholder) -> set:
    """Columns of the destination that every statement of its recipe fills with <source>.raw_id,
    using the alias of the source itself."""
    result = None
    columns = list(destination.get("destination_columns") or [])
    for template in destination["statement_templates"]:
        masked = service_cls._mask_sql_literals_and_comments(template)
        source_alias = re.search(re.escape(placeholder) + r"\s+(?:as\s+)?([a-z_][a-z0-9_]*)", masked, flags=re.I)
        select_list = _top_level_select_list(service_cls, template)
        if not source_alias or not select_list or len(select_list) != len(columns):
            return set()
        pattern = re.escape(source_alias.group(1)) + r"\.raw_id"
        filled = {column for column, expression in zip(columns, select_list)
                  if re.fullmatch(pattern, expression.strip(), flags=re.I)}
        result = filled if result is None else result & filled
    return result or set()


def _top_level_select_list(service_cls, template: str) -> list[str]:
    masked = service_cls._mask_sql_literals_and_comments(template)
    match = re.search(r"\bselect\b", masked, flags=re.I)
    if not match:
        return []
    depth = 0
    start = match.end()
    parts = []
    current_start = start
    index = start
    lowered = masked.lower()
    while index < len(masked):
        char = masked[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and char == ",":
            parts.append(template[current_start:index])
            current_start = index + 1
        elif depth == 0 and lowered.startswith("from", index) and re.match(r"\bfrom\b", lowered[index:]) \
                and (index == 0 or not (lowered[index - 1].isalnum() or lowered[index - 1] == "_")):
            parts.append(template[current_start:index])
            return [p.strip() for p in parts]
        index += 1
    return []


def _joins_on_raw_id(service_cls, destination, relation, target_columns, placeholder) -> bool:
    if not target_columns:
        return False
    schema_name, table_name = relation
    for template in destination["statement_templates"]:
        masked = service_cls._mask_sql_literals_and_comments(template)
        source_alias = re.search(
            re.escape(placeholder) + r"\s+(?:as\s+)?([a-z_][a-z0-9_]*)", masked, flags=re.I)
        offset = _top_level_from_end(masked)
        occurrences = list(re.finditer(
            r"(?:\b" + re.escape(schema_name) + r"\.)?\b" + re.escape(table_name)
            + r"\s+(?:as\s+)?([a-z_][a-z0-9_]*)", masked[offset:], flags=re.I))
        if not source_alias or not occurrences:
            return False
        s_alias = source_alias.group(1)
        for occurrence in occurrences:
            r_alias = occurrence.group(1)
            terms = _on_clause_terms(masked, offset + occurrence.end())
            linked = any(
                re.fullmatch(rf"{r_alias}\.{column}\s*=\s*{s_alias}\.raw_id", term, flags=re.I)
                or re.fullmatch(rf"{s_alias}\.raw_id\s*=\s*{r_alias}\.{column}", term, flags=re.I)
                for column in target_columns for term in terms
            )
            if not linked:
                return False
    return True


def spec_hash(prepared: dict, config: dict) -> str:
    payload = {
        "engine": ENGINE_VERSION,
        "source": [prepared["source_schema_name"], prepared["source_table_name"]],
        "raw_schemas": prepared["raw_schemas"],
        "destinations": [
            [d["table_name"], d["statement_templates"]] for d in prepared["destinations"]
        ],
        "chunk_rows": config["chunk_rows"],
        "source_mode": config.get("source_mode", "plain"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


_UPGRADE_COLUMNS = (
    ("jobs", "attempt_started_at", "timestamptz"),
    ("jobs", "acknowledged_at", "timestamptz"),
    ("jobs", "workers_used", "integer"),
    ("jobs", "source_versions", "jsonb"),
    ("jobs", "chunk_min", "bigint"),
    ("jobs", "chunk_width", "bigint"),
    ("jobs", "fingerprinted", "boolean NOT NULL DEFAULT false"),
    ("jobs", "fp_all", "text"),
    ("job_segments", "attempt", "integer"),
    ("job_chunks", "attempt", "integer"),
    ("job_chunks", "fp0", "text"),
    ("job_attempts", "heartbeat_at", "timestamptz"),
)
_ATTEMPTS_DDL = (
    f"CREATE TABLE {ENGINE_SCHEMA}.job_attempts (job_id uuid NOT NULL REFERENCES {ENGINE_SCHEMA}.jobs (job_id) "
    "ON DELETE CASCADE, attempt_no integer NOT NULL, started_at timestamptz NOT NULL DEFAULT clock_timestamp(), "
    "heartbeat_at timestamptz, ended_at timestamptz, outcome text, workers integer, PRIMARY KEY (job_id, attempt_no))"
)


def engine_ddl_guarded_sql() -> str:
    """Create the job tables only when they are missing.  Checked in the catalog first:
    CREATE ... IF NOT EXISTS / ALTER ... IF NOT EXISTS still take strong table locks and
    would conflict with the workers of a job that is running while the Manager re-attaches."""
    statements = "\n".join(
        f"        EXECUTE {sql_literal(statement.strip())};"
        for statement in engine_ddl_sql().split(";\n")
        if statement.strip().rstrip(";")
    )
    migrations = [
        f"    IF to_regclass('{ENGINE_SCHEMA}.job_attempts') IS NULL THEN\n"
        f"        EXECUTE {sql_literal(_ATTEMPTS_DDL)};\n"
        "    END IF;"
    ]
    for table, column, definition in _UPGRADE_COLUMNS:
        migrations.append(
            f"    IF NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = to_regclass('{ENGINE_SCHEMA}.{table}') "
            f"AND attname = '{column}' AND NOT attisdropped) THEN\n"
            f"        EXECUTE 'ALTER TABLE {ENGINE_SCHEMA}.{table} ADD COLUMN {column} {definition}';\n"
            "    END IF;")
    migrations = "\n".join(migrations)
    return f"""
DO $pgdm_v2_ddl$
BEGIN
    IF to_regclass('{ENGINE_SCHEMA}.job_chunks') IS NULL THEN
{statements}
    END IF;
    -- Upgrade job tables created by an older version (only touches what is missing).
{migrations}
END
$pgdm_v2_ddl$;""".strip()


def engine_ddl_sql() -> str:
    s = sql_ident(ENGINE_SCHEMA)
    return f"""
CREATE SCHEMA IF NOT EXISTS {s};
CREATE TABLE IF NOT EXISTS {s}.jobs (
    job_id uuid PRIMARY KEY,
    spec_hash text NOT NULL,
    source_table text NOT NULL,
    raw_schemas text[] NOT NULL,
    destinations text[] NOT NULL,
    status text NOT NULL CHECK (status IN
        ('created','running','data_complete','completed','failed','cancelled')),
    config jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    data_completed_at timestamptz,
    finished_at timestamptz,
    cancel_requested boolean NOT NULL DEFAULT false,
    attempts integer NOT NULL DEFAULT 0,
    manifest jsonb,
    versions jsonb,
    last_error text,
    attempt_started_at timestamptz,
    acknowledged_at timestamptz,
    workers_used integer,
    source_versions jsonb,
    chunk_min bigint,
    chunk_width bigint,
    fingerprinted boolean NOT NULL DEFAULT false,
    fp_all text
);
CREATE TABLE IF NOT EXISTS {s}.job_attempts (
    job_id uuid NOT NULL REFERENCES {s}.jobs (job_id) ON DELETE CASCADE,
    attempt_no integer NOT NULL,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    heartbeat_at timestamptz,
    ended_at timestamptz,
    outcome text,
    workers integer,
    PRIMARY KEY (job_id, attempt_no)
);
CREATE INDEX IF NOT EXISTS jobs_open_idx ON {s}.jobs (spec_hash)
    WHERE status NOT IN ('completed','cancelled');
CREATE TABLE IF NOT EXISTS {s}.job_segments (
    job_id uuid NOT NULL REFERENCES {s}.jobs (job_id) ON DELETE CASCADE,
    segment_no integer NOT NULL,
    kind text NOT NULL CHECK (kind IN ('global','chunked')),
    destinations text[] NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done')),
    rows jsonb,
    manifest jsonb,
    attempt integer,
    started_at timestamptz,
    finished_at timestamptz,
    PRIMARY KEY (job_id, segment_no)
);
CREATE TABLE IF NOT EXISTS {s}.job_chunks (
    job_id uuid NOT NULL,
    segment_no integer NOT NULL,
    chunk_no integer NOT NULL,
    lo bigint NOT NULL,
    hi bigint NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done')),
    rows jsonb,
    statement_seconds jsonb,
    manifest jsonb,
    worker integer,
    attempt integer,
    fp0 text,
    started_at timestamptz,
    finished_at timestamptz,
    PRIMARY KEY (job_id, segment_no, chunk_no),
    FOREIGN KEY (job_id, segment_no) REFERENCES {s}.job_segments (job_id, segment_no) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS job_chunks_pending_idx ON {s}.job_chunks (job_id, segment_no, chunk_no)
    WHERE status = 'pending';
""".strip()


def control_ddl_sql(control_schema_ident: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {control_schema_ident}.expansion_job_registrations (
    job_id uuid PRIMARY KEY,
    database_name text NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    versions jsonb NOT NULL
);
""".strip()


def _content_hash_sql(prepared: dict) -> str:
    """Per-row content checksum: jsonb_hash() of jsonb columns (binary, no text
    serialisation) and hashtext() of every other column, combined in column order with the
    row's raw_id, so moving a value between rows or columns changes it.  Summed per range."""
    parts = []
    for name, data_type in prepared.get("source_columns") or []:
        column = "r." + sql_ident(name)
        if str(data_type).lower() == "jsonb":
            parts.append(f"COALESCE(jsonb_hash({column})::bigint, 0)")
        else:
            parts.append(f"COALESCE(hashtext({column}::text)::bigint, 0)")
    if not parts:
        return "0"
    return f"hashtextextended(concat_ws(':', r.{sql_ident('raw_id')}, {', '.join(parts)}), 0)"


def _source_scan_sql(prepared: dict, job: str) -> str:
    """One pass over the source: raw_hash manifest and per-raw_id-range fingerprint (row count,
    ctid hash, raw_id sum, content checksum).  Rows are reduced to a few numbers before
    grouping, so the aggregation never sorts or spills the payload."""
    s = sql_ident(ENGINE_SCHEMA)
    source, scope = _source_scope_sql(prepared)
    # The planner cannot estimate the number of (raw_hash, range) groups and would sort the
    # full-width rows (spilling the payload to disk); hash aggregation is forced for this
    # statement only: partial hash aggregates per parallel worker, a few hundred groups at most.
    return f"""
SET LOCAL enable_sort = off;
CREATE TEMP TABLE pgdm_v2_scan ON COMMIT DROP AS
SELECT x.raw_schema, x.raw_hash, x.chunk_no, count(*) AS n,
       COALESCE(sum(x.h1), 0) AS h1, COALESCE(sum(x.raw_id), 0) AS s, COALESCE(sum(x.h2), 0) AS h2
FROM (
    SELECT r.{sql_ident('raw_schema')}::text AS raw_schema, r.{sql_ident('raw_hash')}::text AS raw_hash,
           ((r.raw_id - j.chunk_min) / j.chunk_width)::integer AS chunk_no,
           hashtext(r.ctid::text)::bigint AS h1, r.raw_id, ({_content_hash_sql(prepared)}) AS h2
    FROM {source} AS r, (SELECT chunk_min, chunk_width FROM {s}.jobs WHERE job_id = {job}) AS j
    WHERE r.{sql_ident('raw_schema')} IN ({scope})
) AS x
GROUP BY 1, 2, 3;
SET LOCAL enable_sort = on;
CREATE TEMP TABLE pgdm_v2_fp ON COMMIT DROP AS
SELECT chunk_no, sum(n)::text || ':' || sum(h1)::text || ':' || sum(s)::text || ':' || sum(h2)::text AS fp
FROM pg_temp.pgdm_v2_scan GROUP BY chunk_no;""".strip()


_FP_ALL_SQL = "(SELECT string_agg(chunk_no::text || '=' || fp, ',' ORDER BY chunk_no) FROM pg_temp.pgdm_v2_fp)"


def _source_scope_sql(prepared: dict) -> tuple[str, str]:
    source = f"{sql_ident(prepared['source_schema_name'])}.{sql_ident(prepared['source_table_name'])}"
    scope = ", ".join(sql_literal(v) for v in prepared["raw_schemas"])
    return source, scope


def _source_projection(prepared: dict, mode: str) -> tuple[str, str]:
    """Projection of the source relation.  'detoast' replaces the jsonb column raw by
    raw #> '{}' (the identity for every jsonb value) behind an OFFSET 0 barrier, so a
    compressed/TOASTed payload is decompressed once per row instead of once per
    raw -> ... access in the recipe.  Same columns, same order, same values."""
    columns = list(prepared.get("source_columns") or [])
    names = [name for name, _type in columns]
    if mode != "detoast" or ("raw", "jsonb") not in [(n, str(t).lower()) for n, t in columns]:
        return "*", ""
    projection = ", ".join(
        "raw #> '{}'::text[] AS raw" if name == "raw" else sql_ident(name) for name in names
    )
    return projection, "\n    OFFSET 0"


def chunk_source_sql(prepared: dict, mode: str = "plain") -> str:
    source, scope = _source_scope_sql(prepared)
    projection, barrier = _source_projection(prepared, mode)
    return (
        f"(\n    SELECT {projection}\n"
        f"    FROM {source}\n"
        f"    WHERE {sql_ident('raw_schema')} IN ({scope})\n"
        "      AND raw_id BETWEEN current_setting('pgdm.chunk_lo')::bigint\n"
        f"                     AND current_setting('pgdm.chunk_hi')::bigint{barrier}\n)"
    )


def full_source_sql(prepared: dict, mode: str = "plain") -> str:
    source, scope = _source_scope_sql(prepared)
    projection, barrier = _source_projection(prepared, mode)
    return (f"(\n    SELECT {projection}\n    FROM {source}\n"
            f"    WHERE {sql_ident('raw_schema')} IN ({scope}){barrier}\n)")


def _counted_insert(statement: str, label: str) -> str:
    """Run one INSERT and add its row count / duration to pg_temp accumulators."""
    tag = "$pgdm_v2$"
    suffix = 0
    while tag in statement:
        suffix += 1
        tag = f"$pgdm_v2_{suffix}$"
    return f"""
DO {tag}
DECLARE
    pgdm_rows bigint;
    pgdm_started timestamptz := clock_timestamp();
BEGIN
    {statement}
    ;
    GET DIAGNOSTICS pgdm_rows = ROW_COUNT;
    INSERT INTO pg_temp.pgdm_v2_rows VALUES ({sql_literal(label)}, pgdm_rows,
        EXTRACT(EPOCH FROM clock_timestamp() - pgdm_started));
END
{tag};""".strip()


def _global_gucs(config: dict) -> dict:
    gucs = dict(config.get("global_gucs") or {})
    # Global segments hold set-level recipes (DISTINCT, aggregates) over the whole source with
    # few groups: hash aggregation avoids sorting (and spilling) every source row.
    gucs.setdefault("enable_sort", "off")
    if int(config.get("global_parallel") or 0) > 0:
        gucs.setdefault("max_parallel_workers_per_gather", str(int(config["global_parallel"])))
    return gucs


def _split_insert(service_cls, statement: str) -> tuple[str, str]:
    """Split 'INSERT INTO t (cols) SELECT ...' at its top-level SELECT."""
    masked = service_cls._mask_sql_literals_and_comments(statement)
    depth = 0
    for match in re.finditer(r"[()]|\bselect\b", masked, flags=re.I):
        token = match.group(0)
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
        elif depth == 0:
            return statement[:match.start()], statement[match.start():]
    raise RuntimeError("Could not locate the SELECT of an expansion statement.")


def _parallel_insert(service_cls, statement: str, destination: dict, index: int) -> str:
    """Evaluate the recipe query with PostgreSQL parallel query (CREATE TABLE AS allows a
    parallel plan, INSERT ... SELECT does not), then insert its rows in one statement.
    Same rows, same assignment casts; the temporary table holds only the query output."""
    head, query = _split_insert(service_cls, statement)
    columns = len(destination.get("destination_columns") or [])
    names = ", ".join(f"pgdm_c{i}" for i in range(1, columns + 1))
    temp = f"pgdm_v2_g{index}"
    label = sql_literal(destination["table_name"])
    return f"""
SELECT clock_timestamp() AS pgdm_t0 \\gset
CREATE TEMP TABLE {temp} ({names}) ON COMMIT DROP AS
{query};
{head} SELECT {names} FROM pg_temp.{temp};
INSERT INTO pg_temp.pgdm_v2_rows VALUES ({label}, :ROW_COUNT,
    EXTRACT(EPOCH FROM clock_timestamp() - :'pgdm_t0'::timestamptz));""".strip()


def _global_scan_block(prepared: dict, job: str, first: bool) -> str:
    """Manifest of a global segment.  The first segment also records the source fingerprint
    (job_chunks.fp0) from the same scan, in the same transaction and snapshot as its rows."""
    s = sql_ident(ENGINE_SCHEMA)
    if not first:
        return (f"CREATE TEMP TABLE pgdm_v2_manifest ON COMMIT DROP AS\n"
                f"SELECT ({_manifest_sql(prepared, full_source_sql(prepared))}) AS manifest;")
    return f"""{_source_scan_sql(prepared, job)}
CREATE TEMP TABLE pgdm_v2_manifest ON COMMIT DROP AS
SELECT COALESCE(jsonb_agg(jsonb_build_object('raw_schema', raw_schema, 'raw_hash', raw_hash, 'row_count', n)),
                '[]'::jsonb) AS manifest
FROM (SELECT raw_schema, raw_hash, sum(n)::bigint AS n FROM pg_temp.pgdm_v2_scan GROUP BY 1, 2) AS m;
DO $pgdm_v2_fp$
BEGIN
    IF EXISTS (SELECT 1 FROM {s}.job_chunks WHERE job_id = {job})
       AND EXISTS (SELECT 1 FROM pg_temp.pgdm_v2_fp f WHERE NOT EXISTS (
               SELECT 1 FROM {s}.job_chunks c WHERE c.job_id = {job} AND c.chunk_no = f.chunk_no)) THEN
        RAISE EXCEPTION 'Source rows outside the planned raw_id ranges: the source changed since the job was created.';
    END IF;
END
$pgdm_v2_fp$;
UPDATE {s}.job_chunks AS c
SET fp0 = COALESCE((SELECT f.fp FROM pg_temp.pgdm_v2_fp AS f WHERE f.chunk_no = c.chunk_no), '0:0:0:0')
WHERE c.job_id = {job};
UPDATE {s}.jobs SET fingerprinted = true, fp_all = {_FP_ALL_SQL} WHERE job_id = {job};"""


def _counter_update_sql(counter_table: str, destinations: list[dict]) -> str:
    parts = []
    for destination in destinations:
        label = destination["table_name"]
        parts.append(f"""
UPDATE {counter_table} AS c
SET row_count = c.row_count + r.n, updated_at = clock_timestamp()
FROM (SELECT COALESCE(SUM(n), 0) AS n FROM pg_temp.pgdm_v2_rows WHERE label = {sql_literal(label)}) AS r
WHERE c.schema_name = {sql_literal(destination['schema_name'])}
  AND c.table_name = {sql_literal(destination['pure_table_name'])};
DO $pgdm_v2_counter$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM {counter_table}
                   WHERE schema_name = {sql_literal(destination['schema_name'])}
                     AND table_name = {sql_literal(destination['pure_table_name'])}) THEN
        RAISE EXCEPTION 'Contador ausente para %.% durante insercao.',
            {sql_literal(destination['schema_name'])}, {sql_literal(destination['pure_table_name'])};
    END IF;
END
$pgdm_v2_counter$;""".strip())
    return "\n".join(parts)


def _manifest_sql(prepared: dict, source_relation: str) -> str:
    return f"""
SELECT COALESCE(jsonb_agg(jsonb_build_object('raw_schema', raw_schema, 'raw_hash', raw_hash,
                                             'row_count', row_count)), '[]'::jsonb)
FROM (
    SELECT raw_schema::text AS raw_schema, raw_hash::text AS raw_hash, COUNT(*)::bigint AS row_count
    FROM {source_relation} AS pgdm_src
    GROUP BY 1, 2
) AS m""".strip()


def build_job_files(service_cls, prepared: dict, segments: list[dict], job_id: str, config: dict,
                    database_name: str, sql_username: str, counter_table: str,
                    registration_sql: str, control_db: str) -> dict:
    """Return {file name: content} for the server-side runner."""
    placeholder = service_cls.CROSS_TABLE_SOURCE_PLACEHOLDER
    s = sql_ident(ENGINE_SCHEMA)
    job = sql_literal(job_id)
    source, scope = _source_scope_sql(prepared)
    files = {}
    preamble = (
        "\\set ON_ERROR_STOP 1\n"
        "CREATE TEMP TABLE IF NOT EXISTS pgdm_v2_rows (label text, n bigint, seconds double precision);\n"
        "TRUNCATE pg_temp.pgdm_v2_rows;\n"
    )
    for number, segment in enumerate(segments, start=1):
        destinations = [item["destination"] for item in segment["items"]]
        if segment["kind"] == "global":
            body = []
            for destination in destinations:
                for template in destination["statement_templates"]:
                    statement = template.replace(placeholder, full_source_sql(prepared, config.get('source_mode', 'plain')))
                    if int(config.get("global_parallel") or 0) > 0:
                        body.append(_parallel_insert(service_cls, statement, destination, len(body) + 1))
                    else:
                        body.append(_counted_insert(statement, destination["table_name"]))
            files[f"segment_{number}.sql"] = preamble + f"""
BEGIN ISOLATION LEVEL REPEATABLE READ;
SET LOCAL client_min_messages = warning;
{guc_sql(_global_gucs(config))}
SELECT (status = 'done') AS pgdm_done FROM {s}.job_segments
 WHERE job_id = {job} AND segment_no = {number} FOR UPDATE \\gset
\\if :pgdm_done
ROLLBACK;
\\echo PGDM_SEGMENT_ALREADY_DONE
\\quit
\\endif
UPDATE {s}.job_segments SET started_at = clock_timestamp()
 WHERE job_id = {job} AND segment_no = {number};
{chr(10).join(body)}
{_counter_update_sql(counter_table, destinations)}
{_global_scan_block(prepared, job, number == 1)}
UPDATE {s}.job_segments SET status = 'done', finished_at = clock_timestamp(), attempt = :pgdm_attempt,
       rows = (SELECT jsonb_object_agg(label, n) FROM (SELECT label, SUM(n) AS n FROM pg_temp.pgdm_v2_rows GROUP BY label) x),
       manifest = (SELECT manifest FROM pg_temp.pgdm_v2_manifest)
 WHERE job_id = {job} AND segment_no = {number};
COMMIT;
\\echo PGDM_SEGMENT_DONE
"""
        else:
            body = []
            for destination in destinations:
                for index, template in enumerate(destination["statement_templates"], start=1):
                    body.append(_counted_insert(
                        template.replace(placeholder, chunk_source_sql(prepared, config.get('source_mode', 'plain'))),
                        destination["table_name"]))
            files[f"segment_{number}.sql"] = preamble + f"""
BEGIN;
SET LOCAL client_min_messages = warning;
{guc_sql(config.get('session_gucs'))}
SELECT COALESCE(c.chunk_no, -1) AS pgdm_chunk,
       set_config('pgdm.chunk_lo', COALESCE(c.lo, 0)::text, true) AS pgdm_lo,
       set_config('pgdm.chunk_hi', COALESCE(c.hi, -1)::text, true) AS pgdm_hi,
       (SELECT cancel_requested FROM {s}.jobs WHERE job_id = {job}) AS pgdm_cancel
FROM (SELECT 1) AS one
LEFT JOIN LATERAL (
    SELECT chunk_no, lo, hi FROM {s}.job_chunks
    WHERE job_id = {job} AND segment_no = {number} AND status = 'pending'
    ORDER BY chunk_no LIMIT 1 FOR UPDATE SKIP LOCKED
) AS c ON true \\gset
SELECT (:pgdm_chunk < 0 OR :'pgdm_cancel' = 't') AS pgdm_stop \\gset
\\if :pgdm_stop
ROLLBACK;
\\echo PGDM_NO_CHUNK
\\quit
\\endif
LOCK TABLE {source} IN SHARE MODE;
UPDATE {s}.job_chunks SET started_at = clock_timestamp(), worker = :pgdm_worker, attempt = :pgdm_attempt
 WHERE job_id = {job} AND segment_no = {number} AND chunk_no = :pgdm_chunk;
{chr(10).join(body)}
{_counter_update_sql(counter_table, destinations)}
UPDATE {s}.job_chunks SET status = 'done', finished_at = clock_timestamp(),
       rows = (SELECT jsonb_object_agg(label, n) FROM (SELECT label, SUM(n) AS n FROM pg_temp.pgdm_v2_rows GROUP BY label) x),
       statement_seconds = (SELECT jsonb_object_agg(label, s) FROM (SELECT label, SUM(seconds) AS s FROM pg_temp.pgdm_v2_rows GROUP BY label) y),
       manifest = ({_manifest_sql(prepared, chunk_source_sql(prepared))})
 WHERE job_id = {job} AND segment_no = {number} AND chunk_no = :pgdm_chunk;
COMMIT;
\\echo PGDM_CHUNK_DONE :pgdm_chunk
"""
            files[f"segment_{number}_close.sql"] = f"""
\\set ON_ERROR_STOP 1
BEGIN;
SELECT count(*) = 0 AS pgdm_complete FROM {s}.job_chunks
 WHERE job_id = {job} AND segment_no = {number} AND status <> 'done' \\gset
\\if :pgdm_complete
UPDATE {s}.job_segments AS g
SET status = 'done',
    started_at = (SELECT min(started_at) FROM {s}.job_chunks WHERE job_id = {job} AND segment_no = {number}),
    finished_at = (SELECT max(finished_at) FROM {s}.job_chunks WHERE job_id = {job} AND segment_no = {number}),
    rows = (SELECT jsonb_object_agg(k, v) FROM (
              SELECT e.key AS k, SUM(e.value::bigint) AS v
              FROM {s}.job_chunks c, jsonb_each_text(c.rows) e
              WHERE c.job_id = {job} AND c.segment_no = {number} GROUP BY e.key) t)
WHERE g.job_id = {job} AND g.segment_no = {number} AND g.status <> 'done';
COMMIT;
\\echo PGDM_SEGMENT_DONE
\\else
ROLLBACK;
\\echo PGDM_SEGMENT_INCOMPLETE
\\endif
"""
    # Finalisation: merge manifests, verify coverage, mark data_complete and emit the manifest.
    files["finalize.sql"] = f"""
\\set ON_ERROR_STOP 1
BEGIN;
-- Row lock: a cancel either lands before this check, or waits and finds the data committed.
SELECT cancel_requested AS pgdm_cancel FROM {s}.jobs WHERE job_id = {job} FOR UPDATE \\gset
\\if :pgdm_cancel
ROLLBACK;
\\echo PGDM_CANCELLED
\\quit
\\endif
SELECT count(*) = 0 AS pgdm_ready FROM {s}.job_segments
 WHERE job_id = {job} AND status <> 'done' \\gset
\\if :pgdm_ready
\\else
ROLLBACK;
\\echo PGDM_NOT_READY
\\quit
\\endif
WITH chunk_manifest AS (
    SELECT c.segment_no, e->>'raw_schema' AS raw_schema, e->>'raw_hash' AS raw_hash,
           SUM((e->>'row_count')::bigint) AS row_count
    FROM {s}.job_chunks c, jsonb_array_elements(c.manifest) e
    WHERE c.job_id = {job}
    GROUP BY 1, 2, 3
), global_manifest AS (
    SELECT g.segment_no, e->>'raw_schema' AS raw_schema, e->>'raw_hash' AS raw_hash,
           (e->>'row_count')::bigint AS row_count
    FROM {s}.job_segments g, jsonb_array_elements(g.manifest) e
    WHERE g.job_id = {job} AND g.kind = 'global'
), per_segment AS (
    SELECT * FROM chunk_manifest UNION ALL SELECT * FROM global_manifest
), reference AS (
    SELECT raw_schema, raw_hash, row_count FROM per_segment
    WHERE segment_no = (SELECT min(segment_no) FROM per_segment)
), mismatch AS (
    SELECT seg.segment_no FROM (SELECT DISTINCT segment_no FROM per_segment) AS seg
    WHERE EXISTS (
        (SELECT raw_schema, raw_hash, row_count FROM per_segment p WHERE p.segment_no = seg.segment_no
         EXCEPT SELECT raw_schema, raw_hash, row_count FROM reference)
        UNION ALL
        (SELECT raw_schema, raw_hash, row_count FROM reference
         EXCEPT SELECT raw_schema, raw_hash, row_count FROM per_segment p WHERE p.segment_no = seg.segment_no))
)
SELECT count(*) = 0 AS pgdm_consistent FROM mismatch \\gset
\\if :pgdm_consistent
\\else
ROLLBACK;
\\echo PGDM_MANIFEST_MISMATCH
\\quit
\\endif
UPDATE {s}.jobs SET manifest = (
    WITH m AS (
        SELECT e->>'raw_schema' AS raw_schema, e->>'raw_hash' AS raw_hash, SUM((e->>'row_count')::bigint) AS row_count
        FROM {s}.job_chunks c, jsonb_array_elements(c.manifest) e
        WHERE c.job_id = {job} AND c.segment_no = (SELECT min(segment_no) FROM {s}.job_segments WHERE job_id = {job} AND kind = 'chunked')
        GROUP BY 1, 2
        UNION ALL
        SELECT e->>'raw_schema', e->>'raw_hash', (e->>'row_count')::bigint
        FROM {s}.job_segments g, jsonb_array_elements(g.manifest) e
        WHERE g.job_id = {job} AND NOT EXISTS (SELECT 1 FROM {s}.job_segments x WHERE x.job_id = {job} AND x.kind = 'chunked')
          AND g.segment_no = (SELECT min(segment_no) FROM {s}.job_segments WHERE job_id = {job})
    )
    SELECT jsonb_build_object(
        'raw_schemas', to_jsonb(ARRAY[{scope}]::text[]),
        'expected_row_count', COALESCE((SELECT SUM(row_count) FROM m), 0),
        'expected_distinct_raw_hash_count', (SELECT COUNT(DISTINCT raw_hash) FROM m),
        'raw_hash_manifest', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'raw_schema', raw_schema, 'raw_hash', raw_hash, 'row_count', row_count)
              ORDER BY raw_schema, raw_hash NULLS FIRST) FROM m), '[]'::jsonb),
        'source_columns', COALESCE((
            SELECT jsonb_agg(jsonb_build_object('name', a.attname,
                   'type', pg_catalog.format_type(a.atttypid, a.atttypmod)) ORDER BY a.attnum)
            FROM pg_attribute a JOIN pg_class r ON r.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = r.relnamespace
            WHERE n.nspname = {sql_literal(prepared['source_schema_name'])}
              AND r.relname = {sql_literal(prepared['source_table_name'])}
              AND r.relkind IN ('r','p') AND a.attnum > 0 AND NOT a.attisdropped), '[]'::jsonb)
    )),
    status = CASE WHEN status = 'completed' THEN status ELSE 'data_complete' END,
    data_completed_at = COALESCE(data_completed_at, clock_timestamp())
WHERE job_id = {job};
COMMIT;
SELECT 'PGDM_MANIFEST ' || manifest::text FROM {s}.jobs WHERE job_id = {job};
"""
    files["register.sql"] = registration_sql
    files["mark_completed.sql"] = f"""
\\set ON_ERROR_STOP 1
UPDATE {s}.jobs SET status = 'completed', versions = :'pgdm_versions'::jsonb,
       finished_at = COALESCE(finished_at, clock_timestamp())
 WHERE job_id = {job};
"""
    # Source fingerprint per raw_id range (row count, ctid hash, raw_id sum, content checksum):
    # any INSERT, UPDATE or DELETE of a source row changes it.  Normally recorded by the first
    # (global) segment from its own full scan; computed here only when there is no global first
    # segment, and always re-checked before a resumed attempt continues.
    first_global = bool(segments) and segments[0]["kind"] == "global"
    files["fingerprint.sql"] = f"""
\\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ;
SET LOCAL max_parallel_workers_per_gather = {int(config.get('global_parallel') or 0)};
SET LOCAL work_mem = '64MB';
SELECT fingerprinted AS pgdm_have,
       {'EXISTS (SELECT 1 FROM ' + s + '.job_segments g WHERE g.job_id = ' + job + " AND g.segment_no = 1 AND g.status = 'pending')" if first_global else 'false'} AS pgdm_deferred
FROM {s}.jobs WHERE job_id = {job} FOR UPDATE \\gset
\\if :pgdm_have
{_source_scan_sql(prepared, job)}
SELECT (fp_all IS DISTINCT FROM {_FP_ALL_SQL})::integer AS pgdm_changed
FROM {s}.jobs WHERE job_id = {job} \\gset
COMMIT;
\\echo PGDM_FP_CHANGED :pgdm_changed
\\elif :pgdm_deferred
COMMIT;
\\echo PGDM_FP_CHANGED 0
\\else
{_source_scan_sql(prepared, job)}
SELECT count(*) AS pgdm_outside FROM pg_temp.pgdm_v2_fp f
WHERE EXISTS (SELECT 1 FROM {s}.job_chunks c WHERE c.job_id = {job})
  AND NOT EXISTS (SELECT 1 FROM {s}.job_chunks c WHERE c.job_id = {job} AND c.chunk_no = f.chunk_no) \\gset
UPDATE {s}.job_chunks AS c
SET fp0 = COALESCE((SELECT f.fp FROM pg_temp.pgdm_v2_fp AS f WHERE f.chunk_no = c.chunk_no), '0:0:0:0')
WHERE c.job_id = {job};
UPDATE {s}.jobs SET fingerprinted = true, fp_all = {_FP_ALL_SQL} WHERE job_id = {job};
COMMIT;
\\echo PGDM_FP_CHANGED :pgdm_outside
\\endif
"""
    files["coordinator.sql"] = f"""
\\set ON_ERROR_STOP 1
SET application_name = 'pgdm_v2_coordinator';
SELECT pg_try_advisory_lock(hashtextextended({job}, 0)) AS pgdm_owner \\gset
\\if :pgdm_owner
\\else
\\echo PGDM_BUSY
\\quit
\\endif
SET application_name = {sql_literal('pgdm_v2_coord_' + job_id)};
BEGIN;
LOCK TABLE {source} IN SHARE MODE;
\\echo PGDM_SOURCE_LOCKED
"""
    files["attempt_start.sql"] = f"""
\\set ON_ERROR_STOP 1
BEGIN;
SELECT attempts + 1 AS pgdm_attempt FROM {s}.jobs WHERE job_id = {job} FOR UPDATE \\gset
INSERT INTO {s}.job_attempts (job_id, attempt_no, workers) VALUES ({job}, :pgdm_attempt, :pgdm_workers);
UPDATE {s}.jobs SET
    status = CASE WHEN status IN ('data_complete', 'completed') THEN status ELSE 'running' END,
    started_at = COALESCE(started_at, clock_timestamp()),
    attempt_started_at = clock_timestamp(),
    finished_at = CASE WHEN status = 'completed' THEN finished_at ELSE NULL END,
    attempts = :pgdm_attempt, last_error = NULL, workers_used = :pgdm_workers
WHERE job_id = {job};
COMMIT;
\\echo PGDM_ATTEMPT :pgdm_attempt
"""
    files["attempt_end.sql"] = f"""
UPDATE {s}.job_attempts SET ended_at = clock_timestamp(), outcome = :'pgdm_outcome'
 WHERE job_id = {job} AND attempt_no = :pgdm_attempt;
"""
    files["mark_failed.sql"] = f"""
UPDATE {s}.jobs SET status = CASE WHEN status IN ('completed','data_complete') THEN status ELSE 'failed' END,
       last_error = :'pgdm_error'
 WHERE job_id = {job} AND status <> 'completed';
"""
    psql = f"psql -h localhost -U {shlex.quote(sql_username)} -X -qAt"
    seg_lines = []
    for number, segment in enumerate(segments, start=1):
        if segment["kind"] == "global":
            seg_lines.append(f"run_global {number}")
        else:
            seg_lines.append(f"run_chunked {number} $WORKERS")
    files["runner.sh"] = f"""#!/bin/bash
# PGDM Expand v2 server-side runner for job {job_id}. Safe to re-run (resume).
# Liveness and ownership: the coordinator session holds the job's advisory lock for the
# whole run; the Manager reads status from the job tables, not from files.
set -u
cd "$(dirname "$0")"
DB={shlex.quote(database_name)}
CONTROL_DB={shlex.quote(control_db)}
PSQL="{psql}"
JOB={shlex.quote(job_id)}
# Workers: explicit number, or 'auto' = usable CPU cores of this server (cgroup quota aware) x workers_per_core.
CORES=$(nproc 2>/dev/null || echo 1)
if [ -r /sys/fs/cgroup/cpu.max ]; then read -r q per < /sys/fs/cgroup/cpu.max; if [ "$q" != "max" ]; then CORES=$(( (q + per - 1) / per )); fi; fi
WORKERS={shlex.quote(str(config['workers']))}
if [ "$WORKERS" = "auto" ]; then WORKERS=$(awk -v c="$CORES" -v f={float(config.get('workers_per_core') or 1.0)} 'BEGIN{{w=int(c*f+0.5); if(w<1)w=1; if(w>32)w=32; print w}}'); fi
ATTEMPT=0
log() {{ echo "[$(date +%H:%M:%S.%N)] $*" >> runner.log; }}
end_attempt() {{ [ "$ATTEMPT" -gt 0 ] && $PSQL -d "$DB" -v pgdm_attempt=$ATTEMPT -v pgdm_outcome="$1" -f attempt_end.sql >/dev/null 2>&1; }}
fail() {{
  log "FAILED: $*"
  $PSQL -d "$DB" -v pgdm_error="$*" -f mark_failed.sql >/dev/null 2>&1
  end_attempt failed
  exit 1
}}
cancelled() {{
  [ "$($PSQL -d "$DB" -c "SELECT cancel_requested FROM {ENGINE_SCHEMA}.jobs WHERE job_id = '$JOB'")" = "t" ]
}}
stop_cancelled() {{
  log "cancelled at: $1"
  $PSQL -d "$DB" -c "UPDATE {ENGINE_SCHEMA}.jobs SET status = CASE WHEN status IN ('completed','data_complete') THEN status ELSE 'failed' END, last_error = 'cancelled by user at $1 (resumable)' WHERE job_id = '$JOB' AND status <> 'completed'" >/dev/null
  end_attempt cancelled
  exit 0
}}
# Coordinator: advisory lock (single runner per job) + SHARE lock on the source.
rm -f coord.fifo; mkfifo coord.fifo
$PSQL -d "$DB" < coord.fifo > coord.out 2> coord.err &
COORD=$!
exec 3> coord.fifo
cat coordinator.sql >&3
for i in $(seq 1 1200); do grep -q -e PGDM_SOURCE_LOCKED -e PGDM_BUSY coord.out 2>/dev/null && break; kill -0 $COORD 2>/dev/null || break; sleep 0.05; done
if grep -q PGDM_BUSY coord.out 2>/dev/null; then log "another runner owns this job; exiting"; exit 0; fi
grep -q PGDM_SOURCE_LOCKED coord.out 2>/dev/null || fail "could not lock source: $(cat coord.err)"
out=$($PSQL -d "$DB" -v pgdm_workers=$WORKERS -f attempt_start.sql 2>attempt.err) || fail "cannot start attempt: $(cat attempt.err)"
ATTEMPT=$(printf '%s\\n' "$out" | sed -n 's/^PGDM_ATTEMPT //p' | tail -1)
[ -n "$ATTEMPT" ] || {{ ATTEMPT=0; fail "no attempt number"; }}
log "attempt $ATTEMPT: source locked; workers=$WORKERS cores=$CORES"
( exec 3>&-; while sleep 2; do kill -0 $$ 2>/dev/null || exit 0
    $PSQL -d "$DB" -c "UPDATE {ENGINE_SCHEMA}.job_attempts SET heartbeat_at = clock_timestamp() WHERE job_id = '$JOB' AND attempt_no = $ATTEMPT" >/dev/null 2>&1
  done ) &
HEARTBEAT=$!
trap 'kill $HEARTBEAT 2>/dev/null' EXIT
cancelled && stop_cancelled "start"
out=$($PSQL -d "$DB" -f fingerprint.sql 2>fingerprint.err) || fail "source fingerprint: $(cat fingerprint.err)"
changed=$(printf '%s\\n' "$out" | sed -n 's/^PGDM_FP_CHANGED //p' | tail -1)
[ "$changed" = "0" ] || fail "source rows changed since this job started ($changed raw_id range(s) differ); the job cannot be resumed safely"
log "source fingerprint verified"
run_global() {{
  cancelled && stop_cancelled "segment $1"
  out=$($PSQL -d "$DB" -v pgdm_attempt=$ATTEMPT -f segment_$1.sql 2>segment_$1.err) || fail "segment $1: $(tail -c 2000 segment_$1.err)"
  log "segment $1 global: $out"
}}
run_chunked() {{
  seg=$1; workers=$2
  pids=()
  for w in $(seq 1 "$workers"); do
    (
      exec 3>&-
      while :; do
        out=$($PSQL -d "$DB" -v pgdm_worker=$w -v pgdm_attempt=$ATTEMPT -f segment_$seg.sql 2>>worker_$w.err) || {{ echo "worker $w error" >> worker_$w.err; exit 1; }}
        case "$out" in *PGDM_NO_CHUNK*) exit 0;; esac
      done
    ) &
    pids+=($!)
  done
  rc=0
  for p in "${{pids[@]}}"; do wait "$p" || rc=1; done
  [ $rc -eq 0 ] || fail "segment $seg worker failed: $(tail -c 2000 worker_*.err)"
  cancelled && stop_cancelled "segment $seg"
  out=$($PSQL -d "$DB" -f segment_${{seg}}_close.sql 2>segment_${{seg}}_close.err) || fail "segment $seg close: $(cat segment_${{seg}}_close.err)"
  case "$out" in *PGDM_SEGMENT_DONE*) ;; *) fail "segment $seg incomplete";; esac
  log "segment $seg chunked done"
}}
{chr(10).join(seg_lines)}
cancelled && stop_cancelled "finalize"
out=$($PSQL -d "$DB" -f finalize.sql 2>finalize.err) || fail "finalize: $(cat finalize.err) $out"
case "$out" in *PGDM_CANCELLED*) stop_cancelled "finalize";; esac
manifest=$(printf '%s\\n' "$out" | sed -n 's/^PGDM_MANIFEST //p' | tail -1)
[ -n "$manifest" ] || fail "finalize returned no manifest: $out"
# Release the source lock but keep the coordinator session (and its advisory lock) until the end.
echo "COMMIT;" >&3
log "data complete; source unlocked"
# As in the original Manager: once the data is committed, versioning always completes.
reg=$($PSQL -d "$CONTROL_DB" -v pgdm_manifest="$manifest" -f register.sql 2>register.err) || fail "version registration: $(cat register.err)"
versions=$(printf '%s\\n' "$reg" | sed -n 's/^PGDM_VERSIONS //p' | tail -1)
[ -n "$versions" ] || fail "registration returned no versions: $reg"
$PSQL -d "$DB" -v pgdm_versions="$versions" -f mark_completed.sql >/dev/null 2>mark.err || fail "mark completed: $(cat mark.err)"
end_attempt completed
log "completed"
kill $HEARTBEAT 2>/dev/null
exec 3>&-; wait $COORD 2>/dev/null; rm -f coord.fifo
"""
    return files


def pack_files(files: dict) -> str:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o700 if name.endswith(".sh") else 0o600
            archive.addfile(info, io.BytesIO(data))
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def new_job_id() -> str:
    return str(uuid.uuid4())
