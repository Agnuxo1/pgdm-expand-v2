#!/bin/bash
# Resume edge cases of the v2 engine on a job with global segments only (inside the container).
# Usage: edge_test.sh ROWS
# A: an interrupted global-only job resumes and adds no rows.
# B: a resume is refused after two source rows exchange their content.
# C: finalize.sql stops, without changing the job, when a cancel request is present.
# The source is restored at the end.  Use a small data volume: rows are physically rewritten.
set -uo pipefail
ROWS=$1
OUT=/results/r${ROWS}/edge
mkdir -p "$OUT"
bash /work/bench/ensure_data.sh "$ROWS" || exit 2
bash /work/bench/reset.sh >/dev/null || exit 4
P="psql -U postgres -h /var/run/postgresql -qAtX -d kaggle_challenge"
run() {
  python3 /work/bench/harness.py --app-dir /work/solution --tag "$1" --out "$OUT" \
    --recipes "/work/upstream/SQL files" --only 2 >"$OUT/$1.log" 2>&1
  python3 -c "import json;print(json.load(open('$OUT/$1.json'))['status'])"
}
reopen() {
  $P -c "UPDATE pgdm_expansion.jobs SET status='failed', acknowledged_at=NULL, finished_at=NULL"
}
counts() { $P -c "SELECT (SELECT count(*) FROM public.table3), (SELECT count(*) FROM public.table4)"; }
swap() {
  $P -c "WITH a AS (SELECT raw_id, raw FROM public.raw_data ORDER BY raw_id LIMIT 2)
         UPDATE public.raw_data r SET raw = (SELECT raw FROM a WHERE a.raw_id <> r.raw_id)
         WHERE r.raw_id IN (SELECT raw_id FROM a)"
}
FAILED=0
check() { echo "[edge] $1: $2"; [ "$2" = PASS ] || FAILED=1; }

[ "$(run first)" = ok ] || { echo "[edge] first run failed"; cat "$OUT/first.log"; exit 5; }
before=$(counts)
segments=$($P -c "SELECT count(*) FILTER (WHERE kind='global'), count(*) FROM pgdm_expansion.job_segments")
[ "$segments" = "1|1" ] && check global_only_plan PASS || check global_only_plan "FAIL $segments"

reopen
status=$(run resume)
[ "$status" = ok ] && [ "$(counts)" = "$before" ] && check A_global_only_resume PASS \
  || check A_global_only_resume "FAIL status=$status counts=$(counts) before=$before"

reopen
swap
status=$(run changed)
msg=$(python3 -c "import json;print(json.load(open('$OUT/changed.json')).get('error') or '')")
swap
[ "$status" = error ] && [ "$(counts)" = "$before" ] && check B_changed_source_refused PASS \
  || check B_changed_source_refused "FAIL status=$status"
echo "[edge] refusal: ${msg:0:200}"

finalize=$(find /tmp /var/tmp /home /root -name finalize.sql -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
if [ -n "$finalize" ]; then
  reopen
  $P -c "UPDATE pgdm_expansion.jobs SET cancel_requested = true"
  out=$($P -f "$finalize" 2>&1)
  state=$($P -c "SELECT status FROM pgdm_expansion.jobs")
  case "$out" in *PGDM_CANCELLED*) [ "$state" = failed ] && check C_finalize_cancel PASS || check C_finalize_cancel "FAIL state=$state";;
    *) check C_finalize_cancel "FAIL output=$out";; esac
else
  check C_finalize_cancel "FAIL finalize.sql not found"
fi
bash /work/bench/reset.sh >/dev/null
echo "[edge] FAILED=$FAILED"
exit $FAILED
