#!/bin/bash
# Wrapper that gives eval_config.sh an auto-incremented tag
ROWS=$1
N=$(( $(ls /results/r${ROWS}/tuning/*.harness.log 2>/dev/null | wc -l) + 1 ))
exec bash /work/bench/eval_config.sh "$ROWS" "dc_$(printf %03d $N)"
