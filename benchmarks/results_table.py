# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Attribution-Recorded-On: 2026-11-06
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Reuse: preserve applicable notices and cite the original author.

"""Aggregate benchmark JSONs into a markdown table (run on the server).

Usage: python3 results_table.py <results_root> [--since EPOCH]
Rows: size x variant -> n, mean +/- sd, min, max of MEASURED PROCESSING TOTAL, peak PG memory, temp bytes,
and how many runs passed verify.py (ok + natural digest + versions).
"""
import glob
import json
import os
import statistics
import sys


def load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None


def main():
    root = sys.argv[1]
    since = float(sys.argv[sys.argv.index("--since") + 1]) if "--since" in sys.argv else 0
    rows = {}
    for size_dir in sorted(glob.glob(os.path.join(root, "r*"))):
        size = os.path.basename(size_dir)[1:]
        for path in glob.glob(os.path.join(size_dir, "*_rep*.json")):
            if os.path.basename(path).startswith("verify_") or os.path.getmtime(path) < since:
                continue
            run = load(path)
            if not run or "measured_processing_total_s" not in run:
                continue
            variant = run["tag"].rsplit("_rep", 1)[0]
            ver = load(os.path.join(size_dir, f"verify_{run['tag']}.json")) or {}
            passed = bool(ver.get("ok")) and ver.get("natural_match", True) is not False and run["status"] == "ok"
            rows.setdefault((int(size), variant), []).append(
                (run["measured_processing_total_s"],
                 run.get("peak_pg_pss_bytes") or run.get("peak_pg_rss_bytes") or 0,
                 "pss" if run.get("peak_pg_pss_bytes") else "rss",
                 run.get("temp_bytes_written") or 0, passed, os.path.getmtime(path)))
    print("| rows | engine | n | MEASURED PROCESSING TOTAL (s) mean ± sd | min–max | peak PG memory | temp files | verified |")
    print("|---|---|---|---|---|---|---|---|")
    for (size, variant), runs in sorted(rows.items()):
        times = [r[0] for r in runs]
        sd = statistics.stdev(times) if len(times) > 1 else 0.0
        mem = max(r[1] for r in runs) / 2 ** 20
        kind = runs[0][2].upper()
        temp = max(r[3] for r in runs) / 2 ** 20
        ok = sum(1 for r in runs if r[4])
        print(f"| {size:,} | {variant} | {len(runs)} | {statistics.mean(times):.2f} ± {sd:.2f} | "
              f"{min(times):.2f}–{max(times):.2f} | {mem:.0f} MiB ({kind}) | {temp:.0f} MiB | {ok}/{len(runs)} |")


if __name__ == "__main__":
    main()
