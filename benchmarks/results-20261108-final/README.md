# Final local paired validation — 2026-11-08

Author: Francisco Angulo de Lafuente · ORCID https://orcid.org/0009-0001-1634-7063.

The control is public b16f593c3eece730a868e5d1e490bd0f2ab8e06d; the measured candidate code is c95d7a1e0851f31773f61c2fc2e94147d99c27c2. PG16.15, AMD Ryzen 7 3700X host; Docker 4 vCPU/6 GiB. Exact software and role/constraint/WAL metadata are in runtime-metadata.json. No GPU is used.

Three reset/run/verify pairs per size, in AB, BA, AB order; tags are immutable. JSON retains the full Manager report, measured processing total, client wall time, sampled PostgreSQL/total PSS, temp_bytes delta and database-size delta. Verification includes natural and strict digests, exact counters, versions and dependencies. Identity allocation is normalized only for natural content comparison.

Cached official-generator volumes were reused without changing input values. The generator, six recipes and guide have Git blobs identical to upstream 5dfde9d; upstream-identity.json records this check. Every 3M natural digest matches the archived original reference. The exact original-generator parameters/seed are unchanged; regenerate from that source when reproducing.

The separate WSL pilot is labelled and is not pooled into confirmation statistics. Historical/exploratory numbers are not pooled either. evaluation.json records the exact preregistered decision, paired ratios, means/SDs, t intervals and resource checks. Raw data remain available even if the primary threshold is not reached. Local observations are not official competition scores.

For reproduction see ../README.md and ../../VALIDATION_20261108.md. SHA256SUMS covers the files in this directory, excluding itself.
