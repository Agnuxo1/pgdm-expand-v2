# PGDM Expand v2

![PGDM Expand v2 editorial cover. Illustrative, no experimental data.](docs/figures/cover.gif)

**Copyright © 2026 Francisco Angulo de Lafuente for original contributions and modifications only. Attribution record: 2026-11-06.**

**Research author:** [Francisco Angulo de Lafuente](https://orcid.org/0009-0001-1634-7063) for the original PGDM Expand v2 contributions · [Citation](CITATION.cff).

## Research scope

![Separate application control from data execution. DB Manager; Linux runner; Chunk worker A; Chunk worker B; Version ledger](docs/figures/architecture.gif)

*Separate application control from data execution.* [Static figure](docs/figures/architecture.png).

An engineering implementation for the [November Python & PostgreSQL Data Pipeline Optimization Challenge](https://www.kaggle.com/competitions/python-postgre-sql-data-pipeline-optimization-challenge). This project focuses on redesigning execution of the cross-table Expand operation and is distinct from the earlier QueryFoundry write-up. It builds on [Igor Moreira’s Apache-2.0 project](https://github.com/igorsiecz/kaggle_postgre_challenge/tree/5dfde9d967425982229b92d6ffe98efcd74612e9). A Git-blob comparison confirms that the database generator, six official SQL recipes, and their setup guide match that upstream revision. The research implementation adds new files and modifies three upstream files; see [NOTICE](NOTICE) and [LICENSE_SCOPE.md](LICENSE_SCOPE.md) for the exact boundaries. No official Kaggle submission or score is claimed for this repository.

## Measured evidence

![Measured processing time at one million rows. Original (n = 3): 247.34; Expand v2 (n = 5): 83.49](docs/figures/runtime.gif)

*Measured processing time at one million rows.* [Static figure](docs/figures/runtime.png).

On one million source rows, the original path recorded 247.34 ± 5.59 s (three runs) and v2 recorded 83.49 ± 5.24 s (five). The three-million-row v2 series recorded 258.90 ± 5.70 s (two runs). These are means and sample standard deviations from the local protocol on engine `86ca8a9`, not official scores. On a second machine the submitted engine recorded 77.57 ± 4.18 s against 139.31 ± 10.71 s for the original (three runs each); the two machines are not comparable. Output digests matched in the reported runs. See [experiment details](EXPAND_V2.md#results).

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

The derivative software remains under the existing Apache-2.0 terms and retains upstream notices. The independent figure renderer at tools/render_lab_figures.py is separately designated MIT under LICENSE.figures. See LICENSE_SCOPE.md for verified and unresolved file boundaries; no new license claim is made for benchmark results, figure outputs, or the cover.

## Bibliography and proposed checks

- [PostgreSQL, Parallel Plans](https://www.postgresql.org/docs/current/parallel-plans.html). Recheck the plan on each major PostgreSQL version.
- [PostgreSQL, Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html). Retest recovery at transaction boundaries and under competing locks.

**Attribution.** Cite [Francisco Angulo de Lafuente](https://orcid.org/0009-0001-1634-7063) using [CITATION.cff](CITATION.cff). Preserve upstream notices and consult LICENSE_SCOPE.md before reusing files outside the explicitly attributed code. The MIT notice below applies only to tools/render_lab_figures.py.

**Reuse notice for the original figure renderer file tools/render_lab_figures.py only:**

This project contains open-source material under the MIT License. When redistributing copies or substantial portions, retain the copyright and permission notices. If you build on this work, please cite the project and credit Francisco Angulo de Lafuente (ORCID: 0009-0001-1634-7063). Help advance scientific knowledge: we welcome reproducible results, corrections, and contributions.

<!-- research-provenance: project=pgdm-expand-v2; original-record=2026-11-04; creator=Francisco Angulo de Lafuente; orcid=https://orcid.org/0009-0001-1634-7063; attribution-recorded-on=2026-11-06; license-scope=LICENSE_SCOPE.md; upstream-comparison=git-blobs; upstream-base=5dfde9d967425982229b92d6ffe98efcd74612e9 -->
