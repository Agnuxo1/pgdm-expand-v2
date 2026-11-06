# PGDM Expand v2 — parallel, resumable, server-side expansion
**Author:** Francisco Angulo de Lafuente · **ORCID:** https://orcid.org/0009-0001-1634-7063 · **Attribution record:** 2026-11-06.

Project write-up for the Kaggle Python & PostgreSQL Data Pipeline Optimization Challenge.
NOTICE declares a derivation from [Igor Moreira’s Apache-2.0 project](https://github.com/igorsiecz/kaggle_postgre_challenge/tree/5dfde9d967425982229b92d6ffe98efcd74612e9). A Git-blob comparison against that base confirms that `generate_database.py`, all six official SQL recipes, and `GENERATE_DATABASE_README.md` are identical. The research snapshot adds 46 paths and modifies `README.md`, `main.py`, and `services/postgres_service.py`; the two Python file notices limit Francisco’s copyright to his modifications. The separately declared source snapshot `5a1028f999f482ef34b93f1ce25772e90ce80afa` was not retrievable from the upstream remote and is not treated as the comparison base.
All reported numbers are local results, not official competition scores. No official Kaggle submission or score is claimed.

All numbers below are **local** results on the hardware described in [Results](#results); they are not official
competition scores.

## 1. Bottlenecks found in the original implementation

Measured with the application's own Expansion Performance Report (`MEASURED PROCESSING TOTAL`) on databases built by
the unmodified `generate_database.py`:

| Stage (1,000,000 source rows) | Original |
|---|---|
| Preflight (≈30 SSH round trips, ~20 ms each) | ≈0.6 s |
| `INSERT ... SELECT` of the six recipes, one transaction, **one backend** | ≈245 s |
| Version registration (control DB) | <0.1 s |

* The whole workload runs in **one PostgreSQL backend at 100 % of one core**; the other cores are idle.
  `INSERT ... SELECT` never gets a parallel plan in PostgreSQL, so the server cannot help by itself.
* Per row, the cost is dominated by the foreign-key (RI) trigger checks — table1 has 2 FKs, table6 2, table5 1,
  table2 1 (≈2.3 rows per source row) — plus unique-index maintenance and re-parsing the `raw` JSONB in every recipe.
  Measured with `benchmarks/micro.py` (same recipes, one backend, 1M rows):

  | Statement | per-row FK checks | FKs dropped, then re-added and validated in the same transaction |
  |---|---|---|
  | table3 / table4 (DISTINCT) | 4.0 / 3.3 s | 4.0 / 3.3 s |
  | table1 | 66.1 s | 31.9 s |
  | table5 / table6 | 23.0 / 27.7 s | 5.6 / 6.1 s |
  | table2 | 90.1 s | 48.7 s |
  | re-adding the 6 FKs (full validation) | – | ≈1.9 s |
  | **total** | **214.3 s** | **101.8 s** |

  Per-row RI checks are ≈52 % of the single-backend cost. v2 keeps every constraint enabled during the whole job
  (see §8 for why) and recovers the time with parallelism instead. JSONB is stored uncompressed here
  (`pg_column_size(raw)` ≈ 1.62 kB), so detoasting once per row brings nothing; `work_mem` and `jit` are neutral.
* The single all-or-nothing transaction cannot survive an SSH interruption: the remote `psql` dies with the channel,
  the transaction rolls back and *all* the work is lost; if the interruption happens between the data commit and the
  separate control-database transaction, the data is committed **without its version record**.

## 2. Architecture

```
Windows DB Manager ── SSH ──► Linux server
  prepare + validate (unchanged parser, guards, preflight)
  create/resume job  ──psql──► pgdm_expansion.jobs / job_segments / job_chunks   (data database)
  upload job files, launch `setsid nohup bash runner.sh`  (detached: survives SSH loss)
  wait / re-attach    ◄──────── runner.sh
                                  ├─ coordinator session: LOCK raw_data IN SHARE MODE for the whole job
                                  ├─ segment 1 (global): table3, table4         – one transaction, parallel query
                                  ├─ segment 2 (chunked): table1→table5→table6→table2 per raw_id range,
                                  │    K psql workers, FOR UPDATE SKIP LOCKED, one transaction per chunk
                                  ├─ finalize: merge per-chunk raw_hash manifests, verify coverage
                                  └─ register versions in postgres_data_manager (idempotent by job id)
```

**Segmentation is derived from the recipes, not hard-coded** (`services/expansion_engine.py::classify_destinations`).
A destination is *chunkable* only if every statement reads `{{source}}` once and as its first `FROM` item, uses no
`RIGHT`, `FULL` or `NATURAL` join, contains no subquery or set-level construct (`DISTINCT`, `GROUP BY`, aggregates,
window functions, `LIMIT`, set operations …), does not read its own destination, and reads earlier destinations
either after they are complete or, for every occurrence, through a bare `AND` term `rel.col = source.raw_id` of that
join's `ON` clause, where `col` is filled from `raw_id` by that destination's own recipe (so a chunk only matches rows
produced from its own source rows). Everything else runs once over the whole source, in recipe order. For the official workload this yields
`[table3, table4]` global and `[table1, table5, table6, table2]` chunked; a recipe that joins on anything else is
executed globally (covered by `tests/test_expansion_v2.py`).

**Each chunk is one transaction** that (1) claims the chunk row with `FOR UPDATE SKIP LOCKED`, (2) runs the recipes
with `{{source}}` restricted to `raw_id BETWEEN lo AND hi` (plus the original `raw_schema` guard), (3) adds the
affected rows to `public.pgdm_table_row_counts`, (4) stores its rows/time/raw_hash manifest and marks itself `done`,
then commits. A chunk is either fully applied and recorded or not at all.

**The global segment** evaluates each recipe's `SELECT` with `CREATE TEMP TABLE … AS` (PostgreSQL allows a parallel
plan there, not in `INSERT … SELECT`) and inserts the rows in the same transaction. The temporary table only holds the
statement's output (27 rows for table4).

**Timing.** The report keeps every Manager-side item of the original. The detached job contributes its elapsed
server wall clock (`clock_timestamp()` stored in the job tables) for the data phase and for version registration —
included in `MEASURED PROCESSING TOTAL`. The Manager's wait loop is reported as a diagnostic envelope (excluded, as the
original excludes its batch envelope) to avoid double counting. The summed per-chunk statement times of all workers
are listed as diagnostics so that the CPU actually spent is visible too.

## 3. Integrity guarantees (eligibility gate)

| Guarantee | How it is preserved |
|---|---|
| Source validation | unchanged preflight (existence, required columns, Raw version references, function safety) |
| Destination validation | unchanged preflight (existence, row counters, managed dependencies) and the same recipe parser/guards |
| Relational output | the official recipe text is executed verbatim; only the `{{source}}` relation is restricted to a `raw_id` range; all FK/unique constraints stay enabled (no `DISABLE TRIGGER`, no superuser) |
| Row counters | updated in the same transaction as the rows of every chunk / global segment |
| Version registration | same rows in `app_control.table_versions` and `table_version_dependencies` (same `sql_recipe`, same manifest keys), written in one transaction together with `app_control.expansion_job_registrations(job_id)` → exactly once |
| Dump/version handling | unchanged (“No additional dump was created”, as in the original Expand) |
| Traceability | versions + dependency manifest as before, plus job/segment/chunk records (rows, timings, manifests, attempts) |
| Source consistency | coordinator holds `SHARE` on `raw_data` during the job; a fingerprint per `raw_id` range (row count, ctid hash, raw_id sum, and a checksum that binds each row's column hashes to its `raw_id`) is taken before any work and re-checked before a resumed attempt continues; stored Raw version references must match; per-chunk raw_hash manifests must equal the global one before versions are registered |

Correctness is checked by `benchmarks/verify.py`: per-table digests with surrogate keys mapped to natural keys
(`table1` → `raw_id`, `table3` → its value tuple), exact row counters and one version per destination.
**Surrogate identity values** (`id_column_1`) are drawn from the same sequences but in a different order when chunks
run in parallel; every row and every foreign-key relationship is identical. `PDM_EXPAND_V2_CONFIG='{"workers":1}'`
runs the same engine with one worker.

## 4. Failure recovery

* **SSH/Manager interruption:** the job keeps running on the server. Running *Expand* again with the same
  configuration re-attaches (or, if it already finished, collects its result instead of expanding twice: unacknowledged
  completed jobs are matched by a hash of source, scope, recipes and chunk size).
* **Runner/worker killed or PostgreSQL crash:** uncommitted chunks roll back; committed chunks stay `done`. *Expand*
  with the same configuration resumes: a new runner takes the job's advisory lock (a second runner exits), verifies
  the source fingerprint, skips done segments/chunks and continues. A chunk cannot be applied twice because its `done`
  flag commits atomically with its rows and is claimed under `FOR UPDATE SKIP LOCKED`. If the source changed while
  no runner held the lock, the resume is refused instead of mixing two source states.
* **Between data commit and version registration:** the job is `data_complete`; resuming only re-runs the idempotent
  registration (`\if` on `expansion_job_registrations`), so there is never a second version or a missing one.
* **Cancel** (GUI button): honoured until the data is committed — workers finish their current chunk, no new chunk,
  segment or finalisation starts, and the job stays resumable. Once the data is committed, version registration
  always completes (the same rule as the original Manager).
* Inspect jobs: `PostgresAdminService.list_expansion_jobs(db)` or
  `SELECT * FROM pgdm_expansion.jobs ORDER BY created_at DESC;` and `job_chunks` for per-chunk state.

`benchmarks/interrupt_test.sh` reproduces three interruptions (Manager killed, runner + workers `kill -9`,
`pg_ctl restart -m immediate`) and checks the final state against the reference digest.

## Results

Local results (not official scores). Bench A, engine `86ca8a9`, 29–30 Oct 2026: AMD Ryzen 7 3700X host, Debian 13, SATA SSD; benchmark container limited to
**4 vCPU and 6 GiB**; PostgreSQL 16.15 (Alpine image) with its **default configuration**; DB Manager service layer
driven headlessly over SSH to `127.0.0.1`; data from the unmodified official generator. Commit of the engine:
see the submission commit. Correctness of every run: `benchmarks/verify.py` (natural-key digests identical to the
original engine's output, exact row counters, one version + one dependency per destination).

| rows | engine | runs | MEASURED PROCESSING TOTAL (s) | peak PostgreSQL memory | temp files | verified |
|---|---|---|---|---|---|---|
| 100,000 | original | 1 | 22.52 | 166 MiB (PSS) | 0 | 1/1 |
| 100,000 | v2 | 1 | 13.09 | 353 MiB (PSS) | 0 | 1/1 |
| 1,000,000 | original | 3 | 247.34 ± 5.59 | 563 MiB (RSS sum) | 75 MiB | 3/3 |
| 1,000,000 | **v2** | 5 | **83.49 ± 5.24** (75.71–88.50) | 557 MiB (PSS) | **0** | 5/5 |
| 3,000,000 | original | 1 | 711.45 | 319 MiB (PSS) | 224 MiB | 1/1 |
| 3,000,000 | **v2** | 2 | **258.90 ± 5.70** (254.87–262.93) | 558 MiB (PSS) | **0** | 2/2 |

Speed-up with 4 cores: **2.96× at 1M** and **2.75× at 3M**; no temporary files at the three measured sizes. Breakdown of a v2
run at 3M (`v2_rep2`): global segment (table3, table4, manifest and source fingerprint in one transaction) 28.5 s;
chunked segment (60 chunks) 225.3 s; version registration < 0.1 s; Manager-side preflight ≈0.6 s (unchanged).
At 1M (`v2_rep3`): global 10.7 s, chunked 75.2 s for ≈279 s of summed statement time over 4 workers.

Design note measured on the way: allowing PostgreSQL to sort in the global segment made it faster at 1M (5.6 s,
total 78.3 ± 1.1 s, commit `fc86fb1`) but its parallel DISTINCT then spilled 224 MiB at 3M (30.9 s); hash
aggregation (final commit) costs a few seconds at 1M, grows linearly, is faster at 3M and never writes temporary
files at the sizes measured. Nothing above 3M rows was measured.
Memory: v2 runs 4 backends, so peak memory is reported as PSS (shared buffers split between processes); the
original was sampled as the RSS sum of its backends (a single active backend, comparable order of magnitude).

**Recovery (1M rows, interruption 50 s after start, `benchmarks/interrupt_test.sh`, all strict checks):**

| scenario | committed chunks at interruption | after Expand is run again | result |
|---|---|---|---|
| Manager killed (`kill -9` of the harness) | 12/20 | same attempt finished on the server, collected (no second attempt) | PASS |
| runner + workers + psql `kill -9` | 10/20 | attempt 2 reused 10 chunks, 20/20 done | PASS |
| PostgreSQL `pg_ctl restart -m immediate` | 12/20 | attempt 2 reused 12 chunks, 20/20 done | PASS |

In every scenario the final tables matched the reference digests, the row counters were exact and each destination
had exactly one version. The reported total after a resume (78–93 s) includes the elapsed time of the interrupted
attempt (counted up to its last heartbeat).

**Submitted engine (bench B, 6 Nov 2026).** After audit round 3 the engine changed: stricter chunking rules, a
row-bound checksum, a cancel check at finalization and resume of jobs with global segments only. Bench A was not
available for this revision, so the original and the submitted engine were measured in alternation on a second
machine: Intel Core i9-7900X, WSL2 (Ubuntu 22.04), PostgreSQL 16.15 defaults, 4 cores by `taskset`, a workstation
that also ran other work. The memory limit of bench A did not apply here.

| rows | engine | runs | MEASURED PROCESSING TOTAL (s) | peak PostgreSQL memory | temp files | verified |
|---|---|---|---|---|---|---|
| 1,000,000 | original | 3 | 139.31 ± 10.71 (130.00–151.01) | 249–264 MiB (PSS) | 75 MiB | 3/3 |
| 1,000,000 | **v2** | 3 | **77.57 ± 4.18** (72.83–80.75) | 517–518 MiB (PSS) | **0** | 3/3 |

Speed-up on bench B: **1.80×**. The two benches are not comparable with each other: the original runs much faster on
bench B, so the ratio depends on the machine. Recovery on bench B (1M, interruption after 50 s): 3/3 PASS, with 8–9
of 20 chunks committed at the interruption and totals of 80.62–96.31 s after resuming. `benchmarks/edge_test.sh`
(100k): 4/4 PASS. Raw files: `benchmarks/results-20261030/` (bench A) and `benchmarks/results-20261106-wsl/` (bench B).
The 3M series was not repeated for the submitted engine.

## 5. Own technology: Darwin-Cage autotuner

`tools/darwin_cage_tuner.py` implements Darwin-Cage (chaos-driven evolutionary search by F. Angulo de Lafuente): a
logistic map in the chaotic regime (r = 3.99) modulates tournament size and mutation strength every generation. The
genome is the engine configuration (workers per core, chunk size, source projection, parallel global segment and
whitelisted session settings: `work_mem`, `jit`, `synchronous_commit`, `enable_hashjoin`). Fitness is the official
`MEASURED PROCESSING TOTAL` of a full Expand on the official generator's data; any run whose verified output differs
from the reference is rejected.

**Measured contribution (honest result).** Hypothesis H1 was "a Darwin-Cage configuration beats the hand-tuned
control". With 4 generations × 6 individuals (21 distinct evaluations, 1M rows, seed 7) the best configuration found
was the control itself (75.7 s); the closest alternatives scored 76.7, 77.0 and 77.3 s, within run-to-run noise.
**H1 is rejected at this budget**: the tuner did not make the engine faster. What it did contribute is a
verified sensitivity map that confirms the shipped defaults sit at a local optimum and explains why they are
expressed per core:

| Factor (1M rows, 4 vCPU) | Effect on MEASURED PROCESSING TOTAL |
|---|---|
| workers per core 0.5 instead of 1.0–2.0 | 120–145 s instead of 75–80 s |
| `enable_hashjoin = off` in chunks | +15 to +30 s |
| detoasted source projection (`raw #> '{}'`) | no gain (payload is not TOAST-compressed here) |
| `jit` on/off, chunk size 10k–200k, `synchronous_commit` | within ±3 s |

The full search log is reproducible with `benchmarks/inside_tune.sh`.

## 6. Configuration

Defaults need no configuration. Optional `PDM_EXPAND_V2_CONFIG` (JSON or `@file.json`):

```json
{"workers": "auto", "workers_per_core": 1.0, "chunk_rows": 50000, "global_parallel": 2,
 "source_mode": "plain", "session_gucs": {"work_mem": "64MB", "jit": "off", "synchronous_commit": "off"}}
```

`workers: "auto"` uses the server's usable cores (cgroup quota aware). `synchronous_commit=off` only applies to chunk
transactions: a crash can lose the last few chunk commits, which are then simply redone on resume (their `done` flag
is lost with them); version registration always commits synchronously. `PDM_EXPAND_ENGINE=legacy` runs the original
engine for A/B comparisons.

## 7. Requirements

Unchanged: Windows DB Manager (Python ≥ 3.10, `requirements.txt`), Linux server with PostgreSQL, `psql`,
`pg_dump`, `pg_restore` and SSH. The runner additionally uses `bash`, `setsid`, `nohup`, `mkfifo`, `base64`, `tar`,
`awk`, `sed` and `nproc` (coreutils/util-linux, present on standard distributions). No extension, no superuser.
The PostgreSQL role needs `max_connections` headroom for K + 3 sessions (K workers, coordinator, heartbeat, Manager).

## 8. Known limitations and trade-offs

* Partial results of an interrupted job are visible until it is resumed (by design: work is kept, not discarded).
* While a job runs, the source is write-locked (`SHARE`); destinations accept concurrent writes from other sessions
  (constraints still apply), unlike the original `SHARE ROW EXCLUSIVE` lock which parallel workers cannot share.
* Identity values are assigned in a different order than the single-backend original (see §3).
* Speed-up was measured with 4 cores only; other core counts were not measured.
* The source checksum detects changes with high probability; it is a hash, not a proof of identity.
* Jobs started by an earlier engine version are not resumed: the engine version is part of the job key.
* Bulk FK validation (drop, load, re-add) would roughly halve the per-row cost (§1) but leaves the tables without
  those constraints between chunk commits and after a crash until resume; we chose to keep every constraint enabled
  and not to trade integrity guarantees for speed.
<!-- research-provenance: project=pgdm-expand-v2; creator=Francisco Angulo de Lafuente; orcid=https://orcid.org/0009-0001-1634-7063; attribution-recorded-on=2026-11-06; upstream-comparison=git-blobs; upstream-base=5dfde9d967425982229b92d6ffe98efcd74612e9 -->
