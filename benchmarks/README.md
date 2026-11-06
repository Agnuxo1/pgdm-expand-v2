# Benchmarks
**Author:** Francisco Angulo de Lafuente · **ORCID:** https://orcid.org/0009-0001-1634-7063 · **Attribution record:** 2026-11-06.

Reproducible local benchmark of the cross-table Expand, original engine vs PGDM Expand v2.

* `Dockerfile`, `entry.sh` — PostgreSQL 16 (default configuration) + OpenSSH + Python in one container. The DB
  Manager service layer is driven headlessly and connects over SSH to `127.0.0.1`, exactly like the GUI (SSH transit
  is excluded from `MEASURED PROCESSING TOTAL` in both engines). Credentials are random test values generated at
  container start and never printed.
* `harness.py` — reproduces the service calls of `main.py::_execute_cross_table_expansion_thread`
  (prepare → `execute_cross_table_expansion` → `register_cross_table_expansion_versions` → refresh) and computes
  `MEASURED PROCESSING TOTAL` with the same rule as `ExpansionTimingReportDialog.measured_total_seconds`.
  It also samples peak PSS of the PostgreSQL processes, `temp_bytes` and the database size delta.
* `verify.py` — per-table digests (natural keys and strict), exact row counters, one version + one dependency per
  destination. `ok` fails the run otherwise.
* `reset.sh` — returns `kaggle_challenge` to its freshly generated state between runs.
* `interrupt_test.sh` — three interruption scenarios with strict pass criteria.
* `edge_test.sh` — resume of a job with global segments only, refusal after a source change, cancel at finalize.
* `micro.py` — single-backend SQL micro-experiments used for the bottleneck analysis.
* `eval_config.sh`, `inside_tune.sh` — fitness function and driver of `tools/darwin_cage_tuner.py`.

```bash
benchmarks/prepare_workspace.sh /data/pgpipe-ws          # bench + upstream@5dfde9d + this repo
cd /data/pgpipe-ws
bash bench/run_bench.sh 1000000 "baseline:upstream v2:solution" 3            # timing, 3 repetitions
INSIDE=interrupt_test.sh bash bench/run_bench.sh 1000000 30 1                 # recovery scenarios
INSIDE=edge_test.sh bash bench/run_bench.sh 100000 0 1                        # resume edge cases
INSIDE=inside_tune.sh bash bench/run_bench.sh 1000000 4 6                     # Darwin-Cage (4 generations x 6)
```

Data is generated with the unmodified official `generate_database.py` (fixed seed) on first use of a size and kept
in the Docker volume `pgpipe-data-r<ROWS>`. Results land in `$PGPIPE_RESULTS` (default `~/pgpipe-results`).
The container is limited to 4 vCPU and 6 GiB (`run_bench.sh`); one container per data volume is enforced with a
lock inside the volume.
