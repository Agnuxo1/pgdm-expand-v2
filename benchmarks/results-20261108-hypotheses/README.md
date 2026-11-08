# Hypothesis screens and standalone ablation

Author: Francisco Angulo de Lafuente · ORCID https://orcid.org/0009-0001-1634-7063.

These data are separate from the final confirmation. The 1M server screens compare the approved control, range-bounded joins (H1), JSON fusion alone (H3) and the combination. Bounded joins were slower and remain disabled. The complete standalone H3 evaluation includes three new paired repetitions at 1M and 3M: its point ratios were 1.057 and 1.009, below the fixed 1.10 target. It is an ablation, not final H5 evidence.

The H4 record-projection and H5 VALUES-compilation screens use a separate WSL PostgreSQL 16.15 CPU workstation. Their SQL, JSON EXPLAIN output, exact bag comparisons and summaries are retained. H4 returned equal 1007-row bags but a 0.944 geometric extraction ratio, so it was rejected and removed. H5 returned equal 2320-row bags on 1000 inputs; its 50k extraction-only geometric ratio was 1.825. The H5 model deliberately omits the parent lookup/surrogate identity solely to isolate transformation cost. It is not MEASURED PROCESSING TOTAL. The separate complete-operation WSL pilot found only 1.016 H5/H3 speed-up and is retained in the final archive.

The locally recorded prospective protocol is in ../results-20261108-final/protocol-20261108.md. No exploratory, micro, historical or WSL timing is pooled with the final server confirmation. The original source generator and six recipe files remain unchanged. SHA256SUMS covers this directory excluding itself.

`postgres_properties.sql` reproduces the JSON path fusion check (21 explicit plus 1000 generated cases) and the CASE/key-cast counterexamples in PostgreSQL; it is test input, rather than a saved output log. Run it with `psql -X -f postgres_properties.sql` on a disposable PostgreSQL 16 database. Expected JSON fusion mismatches: zero; the intentionally unsafe CASE/key-cast forms demonstrate why the compiler rejects those forms.
