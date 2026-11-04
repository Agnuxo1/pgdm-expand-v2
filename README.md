# PGDM Expand v2

![PGDM Expand v2 editorial cover. Illustrative, no experimental data.](docs/figures/cover.gif)

**Research author:** [Francisco Angulo de Lafuente](https://orcid.org/0009-0001-1634-7063) · [Citation](CITATION.cff).

## Research scope

![Separate application control from data execution. DB Manager; Linux runner; Chunk worker A; Chunk worker B; Version ledger](docs/figures/architecture.gif)

*Separate application control from data execution.* [Static figure](docs/figures/architecture.png).

An engineering implementation for the [November Python & PostgreSQL Data Pipeline Optimization Challenge](https://www.kaggle.com/competitions/python-postgre-sql-data-pipeline-optimization-challenge). It is distinct from the earlier QueryFoundry writeup. This snapshot contains original work over the organizer's Apache-2.0 project; see [NOTICE](NOTICE) for the exact source lineage. No official Kaggle submission or score is claimed for this repository.

## Measured evidence

![Measured processing time at one million rows. Original (n = 3): 247.34; Expand v2 (n = 5): 83.49](docs/figures/runtime.gif)

*Measured processing time at one million rows.* [Static figure](docs/figures/runtime.png).

On one million source rows, the original path recorded 247.34 ± 5.59 s (three runs) and v2 recorded 83.49 ± 5.24 s (five). The three-million-row v2 series recorded 258.90 ± 5.70 s (two runs). These are means and sample standard deviations from the local protocol, not official scores. Output digests matched in the reported runs. See [experiment details](EXPAND_V2.md#results).

## Recovery and integrity

![Recovery follows the last durable checkpoint. Freeze source; Commit chunk; Persist ledger; Interrupted worker; Verify final state](docs/figures/recovery.gif)

*Recovery follows the last durable checkpoint.* [Static figure](docs/figures/recovery.png).

The design records completed chunks and preserves source and result checks. Recovery from an interrupted run is tested separately from timing. See [failure recovery](EXPAND_V2.md#4-failure-recovery) and [integrity guarantees](EXPAND_V2.md#3-integrity-guarantees-eligibility-gate).

## Reproduce

![Reproduce on a fixed input. Official generator; Fixed-seed data; Run protocol; Verify digests](docs/figures/reproduce.gif)

*Reproduce on a fixed input.* [Static figure](docs/figures/reproduce.png).

Run the unit tests with Python and the project dependencies. For the historical end-to-end benchmark use the unchanged generator, the Windows Manager and a Linux PostgreSQL instance, following the [benchmark guide](benchmarks/README.md). Keep credentials and generated databases outside Git.

## License and citation

![Release provenance. Upstream Apache-2.0; Original modifications; Separate MIT renderer; CITATION.cff](docs/figures/rights.gif)

*Release provenance.* [Static figure](docs/figures/rights.png).

The code derived from the organizer and its modifications retain [Apache-2.0](LICENSE). The new figure renderer is [MIT](LICENSE.figures). Cite Francisco Angulo de Lafuente and the upstream project; preserve both sets of notices.

## Bibliography and proposed checks

- [PostgreSQL, Parallel Plans](https://www.postgresql.org/docs/current/parallel-plans.html). Recheck the plan on each major PostgreSQL version.
- [PostgreSQL, Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html). Retest recovery at transaction boundaries and under competing locks.

**Attribution.** Cite [Francisco Angulo de Lafuente](https://orcid.org/0009-0001-1634-7063) using [CITATION.cff](CITATION.cff). The upstream and derivative software is Apache-2.0. The independent figure renderer is MIT-licensed. Preserve applicable copyright and permission notices and do not present this work as your own. [License](LICENSE) · [Figure methods and provenance](docs/figures/README.md).

<!-- research-provenance: project=pgdm-expand-v2; edition=2026-11-04; creator=Francisco Angulo de Lafuente; orcid=https://orcid.org/0009-0001-1634-7063; figure-renderer-license=MIT -->
