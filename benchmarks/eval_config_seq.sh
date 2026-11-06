#!/bin/bash
# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Attribution-Recorded-On: 2026-11-06
# Reuse: preserve upstream Apache-2.0 notices and cite the author of original changes.
# Wrapper that gives eval_config.sh an auto-incremented tag
ROWS=$1
N=$(( $(ls /results/r${ROWS}/tuning/*.harness.log 2>/dev/null | wc -l) + 1 ))
exec bash /work/bench/eval_config.sh "$ROWS" "dc_$(printf %03d $N)"
