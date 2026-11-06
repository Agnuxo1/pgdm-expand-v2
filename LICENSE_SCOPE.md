# License and attribution scope

- Project: PGDM Expand v2
- Author of the identified original contributions and modifications: Francisco Angulo de Lafuente
- ORCID: https://orcid.org/0009-0001-1634-7063
- Attribution record: 2026-11-06
- Repository: https://github.com/Agnuxo1/pgdm-expand-v2
- Reviewed research snapshot: `3b81aedc45bcff28500f99fdbcd4d024cbe44f86` (single root commit by the user-confirmed Agnuxo1 account)

## Verified upstream comparison

The upstream remote is [igorsiecz/kaggle_postgre_challenge](https://github.com/igorsiecz/kaggle_postgre_challenge), compared at commit `5dfde9d967425982229b92d6ffe98efcd74612e9`. The tree comparison with the research snapshot shows 46 added paths and three modified upstream paths: `README.md`, `main.py`, and `services/postgres_service.py`; no upstream paths were deleted.

The following have Git blobs identical to the verified base: `generate_database.py`, `GENERATE_DATABASE_README.md`, and all six files in `SQL files/`. The project source snapshot also preserves the upstream Apache-2.0 license and other unchanged upstream files. The separately declared source snapshot `5a1028f999f482ef34b93f1ce25772e90ce80afa` was not found among the upstream remote's advertised refs; no equivalence to it is asserted. The alternate URL spelling `kaggle_postgresql_challenge` returned Repository not found.

## Current per-file attribution

- Apache-2.0 original project software: `services/expansion_engine.py`, `services/expansion_v2.py`, `benchmarks/*`, `tests/test_expansion_v2.py`, and `tools/darwin_cage_tuner.py`. The benchmark directory contains newly added project code, scripts, configuration, and documentation.
- Apache-2.0 modifications only: `main.py` and `services/postgres_service.py`. Their headers limit Francisco’s copyright to PGDM Expand v2 modifications and preserve the upstream file authorship and license.
- MIT: `tools/render_lab_figures.py` only, under `LICENSE.figures`. The reuse notice in `README.md` and `docs/figures/README.md` is limited to this renderer.
- Upstream, not attributed to Francisco: `generate_database.py`, `GENERATE_DATABASE_README.md`, the six official SQL recipes, and other unchanged upstream files. No Francisco copyright or SPDX header is applied to these files.
- `README.md` is a mixed derivative document. Its visible credit covers original contributions and modifications only.

## Existing license declarations and unresolved material

The root Apache-2.0 license, root `CITATION.cff`, CodeMeta record, and some project-level license declarations were present in the reviewed snapshot. This note records current per-file attribution intent; it does not retroactively revoke or settle the interpretation of any existing grant. Preserve the upstream Apache notices.

No new license claim is made here for benchmark result values, reports, figure specifications, cover artwork, generated PNG/GIF files, or other material whose rights are not established. The cover source is not recorded. The renderer’s MIT license does not automatically license its output. See the figure provenance records for the original figure date and the 2026-11-06 attribution record.

Direct opens of the Kaggle overview and rules pages returned no readable lines. The official overview search index exposes the requirements for an unchanged generator/fixed seed, a public Git repository, an exact commit before the deadline, no committed secrets, and independent reproducibility; the full rules text and deadline status remain unconfirmed. The repository was already public, and its README makes no official submission or score claim. This audit did not change repository visibility or modify the generator, setup guide, or SQL recipes.
