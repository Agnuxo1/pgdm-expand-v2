# Recovery and small-workload regression — 2026-11-08

Author: Francisco Angulo de Lafuente · ORCID https://orcid.org/0009-0001-1634-7063.

Same frozen candidate code c95d7a1e0851f31773f61c2fc2e94147d99c27c2. Separate Intel Core i9-7900X workstation, Ubuntu 22.04 under WSL, PostgreSQL16.15, Python3.10.12; pinned to four CPU threads with 4 CPU-equivalent quota and 6 GiB. Qualitative failure evidence is not pooled with server timings.

At 1M source rows, interrupt after 40s: kill the Manager, kill runner/workers/psql, or restart PostgreSQL immediately. summary.jsonl records durable chunks, attempts, reused chunks, natural content, exact counters and exactly-once registrations/versions. All 3 scenarios passed; runner/PostgreSQL cases reused 8 chunks each. All final content matched the original reference.

The 100k smoke runs both original and candidate completely. Four edge checks passed: global-only plan, global-only resume without duplicates, source-change refusal, cancel at finalization. Job storage was private to that phase, as it is in the documented fresh Docker container; this avoids stale artifacts from previous local tests. edge-summary.txt is the extracted pass/fail summary, not an unedited raw log. Full local raw logs were preserved separately.

SHA256SUMS covers these files except itself. Reproduce with benchmarks/interrupt_test.sh and edge_test.sh using the documented Docker entry point. Worker synchronous_commit remains off: durable chunks are reused; in-flight/unflushed work may replay after a crash, atomically with its ledger.
