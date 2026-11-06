#!/bin/bash
# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Attribution-Recorded-On: 2026-11-06
# Reuse: preserve upstream Apache-2.0 notices and cite the author of original changes.
# Evaluates one v2 configuration (PDM_EXPAND_V2_CONFIG): reset, Expand, verification.
# Prints one JSON line for tools/darwin_cage_tuner.py. Usage inside the container: eval_config.sh ROWS TAG
set -uo pipefail
ROWS=$1; TAG=$2
OUT=/results/r${ROWS}/tuning
mkdir -p "$OUT"
bash /work/bench/reset.sh >/dev/null 2>&1
python3 /work/bench/harness.py --app-dir /work/solution --tag "$TAG" --out "$OUT" \
  --recipes "/work/upstream/SQL files" --env "PDM_EXPAND_V2_CONFIG=$PDM_EXPAND_V2_CONFIG" > "$OUT/$TAG.harness.log" 2>&1
python3 /work/bench/verify.py --out "$OUT/verify_$TAG.json" --expect "/results/r${ROWS}/verify_baseline_rep1.json" > /dev/null 2>&1
python3 - "$OUT/$TAG.json" "$OUT/verify_$TAG.json" <<'PY'
import json, sys
try:
    h = json.load(open(sys.argv[1]))
except Exception as exc:
    print(json.dumps({"valid": False, "error": f"no harness result: {exc}"})); sys.exit(0)
try:
    v = json.load(open(sys.argv[2]))
except Exception:
    v = {}
print(json.dumps({"measured_processing_total_s": h.get("measured_processing_total_s"),
                  "valid": h.get("status") == "ok" and bool(v.get("ok")) and bool(v.get("natural_match")),
                  "peak_pg_pss_bytes": h.get("peak_pg_rss_bytes"), "temp_bytes_written": h.get("temp_bytes_written"),
                  "status": h.get("status"), "error": h.get("error")}))
PY
