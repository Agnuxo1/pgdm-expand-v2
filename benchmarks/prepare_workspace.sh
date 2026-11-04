#!/bin/bash
# Lays out a benchmark workspace:  <ws>/bench (these scripts), <ws>/upstream (official
# baseline at commit 5dfde9d) and <ws>/solution (this repository at HEAD).
# Usage: benchmarks/prepare_workspace.sh <workspace-dir>
set -euo pipefail
WS=$1
REPO=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$WS"
rm -rf "$WS/bench" && cp -r "$REPO/benchmarks" "$WS/bench"
[ -d "$WS/upstream/.git" ] || git clone -q https://github.com/igorsiecz/kaggle_postgre_challenge.git "$WS/upstream"
git -C "$WS/upstream" checkout -q 5dfde9d
rm -rf "$WS/solution" && mkdir -p "$WS/solution"
git -C "$REPO" archive --format=tar HEAD | tar -x -C "$WS/solution"
echo "Workspace ready. Example:"
echo "  bash $WS/bench/run_bench.sh 1000000 'baseline:upstream v2:solution' 3"
