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

## Final 1M/3M paired confirmation

The frozen candidate core is `c95d7a1e0851f31773f61c2fc2e94147d99c27c2`. Its final documentation/evidence commit preserves that measured core. Control `b16f593c3eece730a868e5d1e490bd0f2ab8e06d` has the same tree as the earlier approved `346dc0b`. Do not use the optimized HEAD as its own control.

On Linux with Docker and Git, run from the final repository commit, choosing a new workspace and results directory. Use LF shell-script line endings (`git config core.autocrlf false` before checkout):

```bash
bash benchmarks/prepare_workspace.sh /data/pgpipe-final
mkdir -p /data/pgpipe-final/control
git archive b16f593c3eece730a868e5d1e490bd0f2ab8e06d | tar -x -C /data/pgpipe-final/control
cd /data/pgpipe-final
export PGPIPE_RESULTS=/data/pgpipe-final-confirmation
INSIDE=confirm.sh bash bench/run_bench.sh 1000000 unused 3
INSIDE=confirm.sh bash bench/run_bench.sh 3000000 unused 3
python3 bench/evaluate_confirmation.py "$PGPIPE_RESULTS" \
  --reference-3m solution/benchmarks/results-20261030/r3000000/verify_baseline_rep1.json \
  --out "$PGPIPE_RESULTS/evaluation.json"
```

`confirm_candidate.py` resets before each run, keeps AB/BA/AB order, verifies immediately, and refuses to overwrite tags. The control directory contains the prior approved engine, not the original upstream single-backend path. The archived original 3M digest independently anchors all six confirmation outputs. The full official generator, deterministic seed and recipes are unchanged. Cached official-generator volumes were reused without changing input values; a new size is generated on first use. Repeated pairs are warm-cache observations rather than cold-cache latency claims.

The recorded runtime is PostgreSQL 16.15 / Python 3.14.10 / paramiko 4.0.0 / pandas 3.0.3 / psutil 7.2.2. Exact role/constraint/WAL checks are in [runtime metadata](results-20261108-final/runtime-metadata.json). The Dockerfile uses the rolling `postgres:16-alpine` tag: record or pin the image digest and package versions when reproducing; later patch/dependency versions can change timings. All six validated foreign keys and their triggers stay enabled. `--cpus 4 --memory 6g` is an execution limit, not a claim of a dedicated or idle host.

The [local prospective protocol](results-20261108-final/protocol-20261108.md) sets the acceptance thresholds before confirmation. It is a local record, not a third-party preregistration. The [final measurements](results-20261108-final/README.md), [separate recovery evidence](results-20261108-recovery/README.md) and [negative/ablation evidence](results-20261108-hypotheses/README.md) retain their environments. Do not pool WSL pilot/micro or historical timings with the server confirmation.

For fault injection use a distinct results directory and the existing commands above with `INSIDE=interrupt_test.sh` (1M, 40 seconds) and `INSIDE=edge_test.sh` (100k). Random test credentials are container-local. A detached runner survives Manager loss; runner/PostgreSQL failures reuse durably committed chunks. With worker `synchronous_commit=off`, recently acknowledged but unflushed chunks may replay; chunk data and its ledger are atomic. Version registration commits synchronously.

To regenerate the report and figure from the retained evidence, run from the repository root (for example `cd /data/pgpipe-final/solution` after the commands above; Python and Matplotlib for the plot):

```bash
python3 tools/write_validation_report.py benchmarks/results-20261108-final/evaluation.json \
  --recovery benchmarks/results-20261108-recovery/summary.jsonl \
  --code-commit c95d7a1e0851f31773f61c2fc2e94147d99c27c2 --out VALIDATION_20261108.md
python3 tools/plot_final_validation.py benchmarks/results-20261108-final/evaluation.json --out docs/figures
```

The unit suite is `python -m unittest discover -s tests -q` with project dependencies installed. On Windows, put Git Bash on PATH for generated-shell syntax checks. Each evidence directory includes SHA256SUMS. Timing uses MEASURED PROCESSING TOTAL and records client wall time separately. The [final report](../VALIDATION_20261108.md) states uncertainty and scaling limits.
