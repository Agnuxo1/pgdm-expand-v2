#!/bin/bash
# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Attribution-Recorded-On: 2026-11-06
# Reuse: preserve upstream Apache-2.0 notices and cite the author of original changes.
# Inside the container: single-backend SQL micro-experiments. Usage: inside_micro.sh ROWS MODES_JSON REPS TAG
set -uo pipefail
ROWS=$1; MODES=$2; REPS=$3; TAG=$4
OUT=/results/r${ROWS}
mkdir -p "$OUT"
bash /work/bench/ensure_data.sh "$ROWS" || exit 2
if [ ! -f "$OUT/verify_baseline_rep1.json" ]; then
  bash /work/bench/reset.sh >/dev/null 2>&1
  python3 /work/bench/harness.py --app-dir /work/upstream --tag baseline_ref --out "$OUT" --recipes "/work/upstream/SQL files"
  python3 /work/bench/verify.py --out "$OUT/verify_baseline_rep1.json" >/dev/null
fi
psql -U postgres -h /var/run/postgresql -qAtX -d kaggle_challenge -c "SELECT pg_column_size(raw), octet_length(raw::text) FROM public.raw_data LIMIT 3; SELECT avg(pg_column_size(raw))::int, avg(octet_length(raw::text))::int FROM public.raw_data;"
python3 /work/bench/micro.py --modes "$MODES" --reps "$REPS" --out "$OUT/micro_${TAG}.json"
