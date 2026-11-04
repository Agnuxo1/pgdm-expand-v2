#!/bin/bash
# Inside the container: Darwin-Cage search over the v2 configuration. Usage: inside_tune.sh ROWS GENERATIONS POPULATION
set -uo pipefail
ROWS=$1; GENS=$2; POP=$3
OUT=/results/r${ROWS}
mkdir -p "$OUT/tuning"
bash /work/bench/ensure_data.sh "$ROWS" || exit 2
[ -f "$OUT/verify_baseline_rep1.json" ] || { echo "missing reference"; exit 2; }
CONTROL='{"workers_per_core":1.0,"global_parallel":2,"chunk_rows":50000,"source_mode":"plain","work_mem":"64MB","jit":"off","synchronous_commit":"off","enable_hashjoin":"on"}'
n=0
python3 /work/solution/tools/darwin_cage_tuner.py --evaluate "bash /work/bench/eval_config_seq.sh $ROWS" \
  --generations "$GENS" --population "$POP" --seed 7 --seed-config "$CONTROL" --out "$OUT/tuning/darwin_cage_$(date +%Y%m%d%H%M).json"
