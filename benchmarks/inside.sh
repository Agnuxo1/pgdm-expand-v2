#!/bin/bash
# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Attribution-Recorded-On: 2026-11-06
# Reuse: preserve upstream Apache-2.0 notices and cite the author of original changes.
# Runs inside the container. Usage: inside.sh ROWS "VARIANTS" REPS
# VARIANT = name:app_dir[:KEY=VAL,KEY=VAL]  (the first rep of 'baseline' is the reference digest)
set -uo pipefail
ROWS=$1; VARIANTS=$2; REPS=$3
OUT=/results/r${ROWS}
mkdir -p "$OUT"
P="psql -U postgres -h /var/run/postgresql -qAtX"
bash /work/bench/ensure_data.sh "$ROWS" || exit 2
$P -d kaggle_challenge -c "SELECT 'raw_rows', count(*), pg_size_pretty(pg_total_relation_size('public.raw_data')) FROM public.raw_data"
FAILED=0
for rep in $(seq 1 "$REPS"); do
  for spec in $VARIANTS; do
    name=${spec%%:*}; rest=${spec#*:}; app=${rest%%:*}; envs=""
    [ "$rest" != "$app" ] && envs=${rest#*:}
    envargs=""; IFS=',' read -ra kv <<< "$envs"; for e in "${kv[@]}"; do [ -n "$e" ] && envargs="$envargs --env $e"; done
    bash /work/bench/reset.sh >/dev/null || { echo "[reset] FAILED"; exit 4; }
    tag="${name}_rep${rep}"
    echo "[run] $tag"
    python3 /work/bench/harness.py --app-dir "/work/$app" --tag "$tag" --out "$OUT" --recipes "/work/upstream/SQL files" $envargs || FAILED=1
    ref="$OUT/verify_baseline_rep1.json"; exp=""; [ -f "$ref" ] && exp="--expect $ref"
    python3 /work/bench/verify.py --out "$OUT/verify_${tag}.json" $exp > "$OUT/verify_${tag}.log" || FAILED=1
    python3 -c "import json;d=json.load(open('$OUT/verify_${tag}.json'));print('[verify]', '$tag', 'ok=',d['ok'],'natural=',d.get('natural_match'),'versions=',d['versions_ok'])"
  done
done
cp /pgdata/server.log "$OUT/server.log" 2>/dev/null || true
echo "[inside] FAILED=$FAILED"
exit $FAILED
