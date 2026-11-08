# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
"""Write a concise report from retained evaluation and recovery evidence."""
from pathlib import Path
import argparse
import json

ap=argparse.ArgumentParser()
ap.add_argument('evaluation',type=Path)
ap.add_argument('--recovery',type=Path,required=True)
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--code-commit',required=True)
args=ap.parse_args()
d=json.loads(args.evaluation.read_text())
recovery=[json.loads(line) for line in args.recovery.read_text().splitlines() if line.strip()]
assert len(recovery)==3 and all(r['pass'] for r in recovery)
assert d['archived_original_3m_reference_match']
rows=[]
resource=[]
individual=[]
for size in d['sizes']:
    a=size['arms']['control']; b=size['arms']['candidate']
    ci=size['geometric_speedup_t95_ci']
    rows.append(f"| {size['rows']:,} | {a['mean_s']:.2f} ± {a['sd_s']:.2f} | {b['mean_s']:.2f} ± {b['sd_s']:.2f} | {size['geometric_speedup']:.3f}× [{ci[0]:.3f}, {ci[1]:.3f}] |")
    resource.append(f"| {size['rows']:,} | {a['max_pg_pss_bytes']/2**20:.2f} | {b['max_pg_pss_bytes']/2**20:.2f} | {a['max_total_pss_bytes']/2**20:.2f} / {b['max_total_pss_bytes']/2**20:.2f} | {a['max_temp_bytes']:,} / {b['max_temp_bytes']:,} |")
    for i,(x,y) in enumerate(zip(a['times_s'],b['times_s']),1):
        individual.append(f"| {size['rows']:,} | {i} | {x:.6f} | {y:.6f} | {x/y:.6f} |")
fault_rows=[]
for r in recovery:
    fault_rows.append(f"| {r['scenario']} | {r['after_interruption']['done']}/{r['after_interruption']['chunks']} | {r['after_resume']['attempts']} | {r['resumed_chunks']} | PASS |")
strict='passed' if d['accepted_per_preregistered_performance_criteria'] else 'not reached'
text=f"""# PGDM Expand — validation of the final query compiler

**Author:** Francisco Angulo de Lafuente · [ORCID](https://orcid.org/0009-0001-1634-7063). Original modifications are Apache-2.0; upstream notices remain in NOTICE.

## Verified results

The candidate combines constant JSON path fusion and guarded compilation of homogeneous lateral VALUES into UNION ALL SELECT branches. It retains the original six recipe files, generator and seed, all foreign keys, source/destination validation, row counters and exactly-once version registration. It uses the existing detached server runner and atomic per-chunk ledger.

Local paired results on an AMD Ryzen 7 3700X host, PostgreSQL 16, Docker limited to 4 vCPU and 6 GiB. The control is the approved public engine `b16f593c3eece730a868e5d1e490bd0f2ab8e06d`; the tested candidate code is `{args.code_commit}`. These observations describe this environment; the organizers determine the competition score on their standardized infrastructure.

| Source rows | Control seconds, mean ± sample SD | Candidate seconds, mean ± sample SD | Paired geometric speed-up [t 95% CI] |
|---|---:|---:|---:|
{chr(10).join(rows)}

![Paired processing time and sampled memory](docs/figures/validation-20261108.png)

Each size has three fresh reset/run/verify pairs, in AB, BA, AB order. Exploratory runs and measurements on the separate WSL recovery workstation are not pooled into these statistics. All twelve retained runs have correct natural-key content, exact counters and one version/dependency per destination. All six 3M outputs also match the archived original-engine content digest.

The ratio is `exp(mean(log(control_seconds / candidate_seconds)))`. Intervals use Student t with two degrees of freedom on the log ratios; three pairs give limited precision and assume approximately normal log ratios. Raw JSON, per-run verification and the evaluation are in [the result archive](benchmarks/results-20261108-final/README.md).

## Resources

| Source rows | Maximum control PostgreSQL PSS, MiB | Maximum candidate PostgreSQL PSS, MiB | Maximum total PSS, control / candidate MiB | Recorded temp_bytes delta, control / candidate |
|---|---:|---:|---:|---:|
{chr(10).join(resource)}

PSS is sampled proportional set size, rather than a sum that repeatedly counts PostgreSQL shared pages. Total PSS includes the Manager process, psql and sshd. `temp_bytes` is the recorded pg_stat_database counter delta; it is not a claim that no temporary relation exists. The engine still creates small global result, manifest and checkpoint relations. It does not materialize a second copy of the JSONB source. Per-run database-size deltas remain in the raw files.

## Why these transformations

1. A constant nonnumeric `raw -> 'object_key' ->> 'field_key'` is fused into a path extraction. Escaped or concatenated key literals, numeric keys and postfix key casts/COLLATE/AT keep the original expression. PostgreSQL equivalence checks cover 1021 NULL/scalar/array/object cases with zero differences.
2. The official lateral VALUES constructor evaluates fourteen possible positions per source row. Compiling its homogeneous rows into SELECT branches exposes predicates before projection. The compiler requires typed smallint constants, plain JSON text expressions, a complete output alias list, a chunked row-wise segment and JSONB metadata. Other forms keep the original constructor. No branch inspects known raw_id values or precomputed outputs.

A separate extraction microbenchmark found 1.825× geometric speed-up over path fusion alone (three pairs); both plans returned 116,058 rows from 50,000 inputs. A smaller exact bag comparison produced 2320 rows in both arms with zero differences. This micro result motivated the full study; it is not a full-operation speed-up. The original recipe text remains the versioned recipe; the compiler changes execution SQL.

Three scoped fresh-context Elephant/Goldfish reviews found concrete parser/identity defects during development; they were corrected and checked with executable cases. The final compiler review found no remaining actionable issue in its stated scope. The parent unit suite passes 35 tests. Reviews are supporting checks, not proofs of arbitrary SQL equivalence.

## Recovery and consistency

At one million rows, a separate Intel Core i9-7900X/WSL PostgreSQL 16 workstation exercised the same frozen candidate code, with interruption after 40 seconds. This is qualitative recovery evidence, separate from the server performance series.

| Scenario | Committed chunks after interruption | Attempts after completion | Reused chunks reported by resumed client | Outcome |
|---|---:|---:|---:|---|
{chr(10).join(fault_rows)}

Manager loss leaves the server running (one attempt); runner or PostgreSQL loss resumes the durable ledger (two attempts). All three end with the original relational content, exact counters, one registration and one version per destination. At 100k, four additional checks pass: global-only planning, global-only reattachment without duplicate rows, source-change refusal, and cancellation at finalization. See [recovery evidence](benchmarks/results-20261108-recovery/README.md).

## Reproduce

Use the unmodified official generator and the documented Windows Manager/Linux PostgreSQL over SSH architecture. The headless harness executes the same service workflow and the same MEASURED PROCESSING TOTAL inclusion rule. Full commands, control checkout, parameters and fault injection are in [benchmarks/README.md](benchmarks/README.md). The exact submission commit belongs in the submitted Kaggle Writeup; a local archive or draft does not constitute that submission.

## Individual confirmation runs

| Source rows | Pair | Control seconds | Candidate seconds | Ratio |
|---|---:|---:|---:|---:|
{chr(10).join(individual)}

## Observations and retained negative results

- The preregistered strong-improvement criterion (at least 1.10× at one size, no material regression at the other, and resource/correctness checks) was **{strict}**. The machine-readable evaluation retains every component of that decision.
- Range-bounded joins preserved content but were slower at 1M (123.67 vs 99.29 seconds in the first screen; 111.94 vs 99.02 in the second). They remain off by default; the table6 plan accounted for the regression.
- JSON fusion alone improved the 1M confirmation by 5.4%; its 3M ratio was 1.009× with a wide interval. Its standalone study did not meet the 1.10× strong-improvement target.
- A record-projection prototype passed 1007-row equivalence but its extraction ratio was 0.944×; it was rejected and removed from the delivered engine.
- Measurements stop at 3M rows and four CPU equivalents. The 300M target remains an unmeasured scaling target. No official rank or winning probability is inferred.
- Identity allocation order can vary with parallelism. Verification replaces surrogate foreign keys with natural keys while checking every remaining field, counters and version dependencies.
- Worker sessions retain the measured `synchronous_commit=off` setting. In-flight or not-yet-flushed work can replay after a crash; data and its chunk ledger remain atomic. Applications requiring acknowledgement durability for each chunk can set it to on and remeasure.
- The classifier/compiler is conservative and tested on the official workload plus adversarial cases; it is not a complete SQL parser. Compare custom recipes against legacy execution and disable an optional rewrite when its syntax is outside the supported form. Finish an interrupted job with its original code/configuration before upgrading engine protocol versions.
- Initial CRLF and foreground-WSL interruption attempts produced no performance result and are recorded as infrastructure incidents; none were relabelled as successful runs.

## References

- [Official challenge rules and evaluation](https://www.kaggle.com/competitions/python-postgre-sql-data-pipeline-optimization-challenge).
- [PostgreSQL 16 JSON operators and record conversion](https://www.postgresql.org/docs/16/functions-json.html).
- [PostgreSQL 16 table expressions and lateral subqueries](https://www.postgresql.org/docs/16/queries-table-expressions.html).
- [PostgreSQL 16 combining queries](https://www.postgresql.org/docs/16/queries-union.html).
- [PostgreSQL 16 WAL settings](https://www.postgresql.org/docs/16/runtime-config-wal.html).
"""
args.out.write_text(text,encoding='utf-8')
print(json.dumps({'report':str(args.out),'primary_criterion':strict}))
