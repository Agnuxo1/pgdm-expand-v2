#!/bin/bash
# Benchmark job entry point (server-ia queue, cpu lane).
# Usage: run_bench.sh ROWS "VARIANTS" REPS [PROFILE]; env INSIDE=<script> selects the in-container driver.
# Safety: one container per data volume at a time (flock), and the container is stopped
# if this job is cancelled (docker run --rm alone does not stop it when the CLI dies).
set -uo pipefail
ROWS=$1; VARIANTS=$2; REPS=$3; PROFILE=${4:-}
HERE=$(cd "$(dirname "$0")/.." && pwd)
IMG=pgpipe-bench:pg16
DOCKER=${DOCKER:-docker}
$DOCKER build -q -t $IMG "$HERE/bench" >/dev/null || { echo "image build failed"; exit 3; }
VOL=pgpipe-data-r${ROWS}
RES=${PGPIPE_RESULTS:-$HOME/pgpipe-results}
LOCKDIR=${PGPIPE_LOCKS:-$HOME/pgpipe-locks}
mkdir -p "$RES" "$HERE/results" "$LOCKDIR"
NAME=pgpipe-$(date +%s)-$$
cleanup() { $DOCKER stop -t 30 "$NAME" >/dev/null 2>&1 || true; }
trap 'cleanup; exit 143' TERM INT HUP
exec 9> "$LOCKDIR/$VOL.lock"
if ! flock -w 7200 9; then echo "volume $VOL busy"; exit 75; fi
$DOCKER run --rm --name "$NAME" --cpus 4 --memory 6g --shm-size 1g --cap-add SYS_PTRACE \
  -e PG_PROFILE="$PROFILE" -v $VOL:/pgdata -v "$HERE":/work:ro -v "$RES":/results \
  $IMG bash /work/bench/${INSIDE:-inside.sh} "$ROWS" "$VARIANTS" "$REPS" ${EXTRA:-} &
CPID=$!
wait $CPID
rc=$?
$DOCKER run --rm --entrypoint sh -v "$RES":/r $IMG -c "chown -R $(id -u):$(id -g) /r" >/dev/null 2>&1 || true
cp -r "$RES"/. "$HERE/results"/ 2>/dev/null || true
exit $rc
