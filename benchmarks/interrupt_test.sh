#!/bin/bash
# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Attribution-Recorded-On: 2026-11-06
# Reuse: preserve upstream Apache-2.0 notices and cite the author of original changes.
# Recovery tests of the v2 engine (inside the container).
# Usage: interrupt_test.sh ROWS DELAY_SECONDS
# Scenarios: ssh_drop (Manager killed), runner_kill (kill -9 of runner, workers and psql),
#            pg_crash (pg_ctl restart -m immediate). After each, Expand is run again with the same
#            configuration and checked: natural digest = reference, exact counters, exactly one
#            version per destination, committed chunks reused.
set -uo pipefail
ROWS=$1; DELAY=$2
OUT=/results/r${ROWS}/recovery
mkdir -p "$OUT"
bash /work/bench/ensure_data.sh "$ROWS" || exit 2
REF=/results/r${ROWS}/verify_baseline_rep1.json
[ -f "$REF" ] || { echo "missing reference $REF"; exit 2; }
P="psql -U postgres -h /var/run/postgresql -qAtX"
summary="$OUT/summary.jsonl"
: > "$summary"

job_state() {
  $P -d kaggle_challenge -c "SELECT json_build_object('status', status, 'attempts', attempts,
     'chunks', (SELECT count(*) FROM pgdm_expansion.job_chunks c WHERE c.job_id = j.job_id),
     'done', (SELECT count(*) FROM pgdm_expansion.job_chunks c WHERE c.job_id = j.job_id AND c.status='done'),
     'segments_done', (SELECT count(*) FROM pgdm_expansion.job_segments g WHERE g.job_id = j.job_id AND g.status='done'))
     FROM pgdm_expansion.jobs j ORDER BY created_at DESC LIMIT 1" 2>/dev/null
}

run_scenario() {
  name=$1
  bash /work/bench/reset.sh >/dev/null 2>&1
  python3 /work/bench/harness.py --app-dir /work/solution --tag "${name}_first" --out "$OUT" \
     --recipes "/work/upstream/SQL files" > "$OUT/${name}_first.log" 2>&1 &
  HPID=$!
  sleep "$DELAY"
  case $name in
    ssh_drop)
      kill -9 $HPID 2>/dev/null ;;
    runner_kill)
      kill -9 $HPID 2>/dev/null
      pkill -9 -f 'bash runner.sh' ; pkill -9 -x psql ;;
    pg_crash)
      su postgres -c "pg_ctl -D /pgdata/data -m immediate restart -w -l /pgdata/server.log" >/dev/null 2>&1
      wait $HPID 2>/dev/null ;;
  esac
  wait $HPID 2>/dev/null
  sleep 2
  before=$(job_state)
  echo "[$name] after interruption: $before"
  python3 /work/bench/harness.py --app-dir /work/solution --tag "${name}_resume" --out "$OUT" \
     --recipes "/work/upstream/SQL files" > "$OUT/${name}_resume.log" 2>&1
  after=$(job_state)
  python3 /work/bench/verify.py --out "$OUT/verify_${name}.json" --expect "$REF" > /dev/null 2>&1
  versions=$($P -d postgres_data_manager -c "SELECT json_object_agg(table_name, n) FROM (SELECT table_name, count(*) n FROM app_control.table_versions WHERE database_name='kaggle_challenge' AND operation_kind='cross_table_expand_v1' GROUP BY 1) x")
  regs=$($P -d postgres_data_manager -c "SELECT count(*) FROM app_control.expansion_job_registrations")
  python3 - "$name" "$before" "$after" "$OUT/verify_${name}.json" "$versions" "$regs" "$OUT/${name}_resume.json" >> "$summary" <<'PY'
import json, sys
name, before, after, vfile, versions, regs, rfile = sys.argv[1:]
v = json.load(open(vfile))
try:
    r = json.load(open(rfile))
except Exception:
    r = {}
vers = json.loads(versions or "{}")
b = json.loads(before or "{}")
a = json.loads(after or "{}")
resumed = ((r.get("report") or {}).get("expansion_job") or {}).get("resumed_chunks")
ok = (bool(v.get("natural_match")) and bool(v.get("ok")) and bool(v.get("versions_ok"))
      and len(vers) == 6 and all(n == 1 for n in vers.values()) and regs.strip() == "1"
      and r.get("status") == "ok" and a.get("status") == "completed" and a.get("done") == a.get("chunks"))
if name in ("runner_kill", "pg_crash"):
    # committed work must be reused, not redone
    ok = ok and a.get("attempts", 0) >= 2 and resumed == b.get("done")
if name == "ssh_drop":
    # the server-side job must have survived the Manager: no second attempt
    ok = ok and a.get("attempts") == 1
print(json.dumps({"scenario": name, "pass": ok, "after_interruption": json.loads(before or "{}"),
                  "after_resume": json.loads(after or "{}"), "natural_match": v.get("natural_match"),
                  "counters_ok": v.get("counters_ok"), "versions_per_table": vers, "registrations": regs.strip(),
                  "resume_status": r.get("status"), "resume_error": r.get("error"),
                  "resume_measured_s": r.get("measured_processing_total_s"),
                  "resumed_chunks": ((r.get("report") or {}).get("expansion_job") or {}).get("resumed_chunks")}))
PY
  tail -1 "$summary"
}

for s in ssh_drop runner_kill pg_crash; do run_scenario $s; done
passed=$(grep -c '"pass": true' "$summary")
echo "[recovery] scenarios passed: $passed/3"
[ "$passed" = "3" ]
