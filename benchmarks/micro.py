# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Reuse: preserve applicable notices and cite the original author.

"""Micro-experiments on the six official recipes, run with psql in one transaction.

Each mode changes ONE mechanism so its effect can be isolated:
  source  : plain | detoast   ({{source}} relation used)
  fk      : row | bulk        (per-row RI triggers vs drop + re-add validated FK)
  gucs    : extra SET LOCAL settings (work_mem, jit, ...)
Prints per-statement wall times (psql \\timing) and verifies against verify.py.
"""
import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

RECIPES = (
    ("01_table3.sql", "table3"), ("02_table4.sql", "table4"), ("03_table1.sql", "table1"),
    ("04_table5.sql", "table5"), ("05_table6.sql", "table6"), ("06_table2.sql", "table2"),
)
SOURCES = {
    "plain": "(SELECT * FROM public.raw_data WHERE raw_schema IN ('group001'))",
    "detoast": ("(SELECT raw_id, raw_hash, raw_ingested_at, raw_schema, raw_tab, "
                "(raw || '{}'::jsonb) AS raw FROM public.raw_data "
                "WHERE raw_schema IN ('group001') OFFSET 0)"),
}
CHILD_FKS = ("table1", "table2", "table5", "table6")


def psql(sql, db="kaggle_challenge", timing=False):
    cmd = ["psql", "-U", "postgres", "-h", "/var/run/postgresql", "-d", db, "-X", "-v", "ON_ERROR_STOP=1", "-q", "-At"]
    if timing:
        sql = "\\timing on\n" + sql
    out = subprocess.run(cmd, input=sql, check=True, capture_output=True, text=True)
    return out.stdout


def fk_defs():
    rows = psql(
        "SELECT conrelid::regclass::text || '|' || conname || '|' || pg_get_constraintdef(oid) "
        "FROM pg_constraint WHERE contype='f' AND conrelid::regclass::text IN "
        "('table1','table2','table5','table6') ORDER BY 1", timing=False)
    out = []
    for line in rows.splitlines():
        line = line.strip()
        parts = [p.strip() for p in line.split("|", 2)]
        if len(parts) == 3 and parts[2].startswith("FOREIGN KEY"):
            out.append(parts)
    return out


def build(mode):
    src = SOURCES[mode["source"]]
    parts = ["BEGIN ISOLATION LEVEL REPEATABLE READ;", "SET LOCAL client_min_messages = warning;"]
    for guc in mode.get("gucs", []):
        parts.append(f"SET LOCAL {guc};")
    fks = fk_defs() if mode["fk"] == "bulk" else []
    for table, name, _ in fks:
        parts.append(f"ALTER TABLE public.{table} DROP CONSTRAINT {name};")
    recipe_dir = Path("/work/upstream/SQL files")
    for file_name, table in RECIPES:
        stmt = (recipe_dir / file_name).read_text().strip().rstrip(";").replace("{{source}}", src)
        parts.append(f"SELECT 'STMT {table}';")
        parts.append(stmt + ";")
        parts.append(
            f"UPDATE public.pgdm_table_row_counts SET row_count = (SELECT count(*) FROM public.{table}) "
            f"WHERE schema_name='public' AND table_name='{table}';")
    for table, name, definition in fks:
        parts.append(f"SELECT 'FK {table}.{name}';")
        parts.append(f"ALTER TABLE public.{table} ADD CONSTRAINT {name} {definition};")
    parts.append("SELECT 'COMMIT';")
    parts.append("COMMIT;")
    return "\n".join(parts)


def parse_times(output):
    label = None
    rows = []
    for line in output.splitlines():
        line = line.strip()
        m = re.match(r"Time: ([0-9.]+) ms", line)
        if m:
            if label:
                rows.append((label, float(m.group(1)) / 1000.0))
            continue
        if line.startswith(("STMT ", "FK ", "COMMIT")):
            label = line
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", required=True, help="JSON list of modes")
    ap.add_argument("--out", required=True)
    ap.add_argument("--reps", type=int, default=1)
    args = ap.parse_args()
    modes = json.loads(args.modes)
    results = []
    for rep in range(1, args.reps + 1):
        for mode in modes:
            subprocess.run(["bash", "/work/bench/reset.sh"], check=True, capture_output=True)
            sql = build(mode)
            t0 = time.perf_counter()
            output = psql(sql, timing=True)
            wall = time.perf_counter() - t0
            times = parse_times(output)
            ver = subprocess.run(
                ["python3", "/work/bench/verify.py", "--out", f"/tmp/v_{mode['name']}.json",
                 "--expect", os.path.join(os.path.dirname(args.out), "verify_baseline_rep1.json")],
                capture_output=True, text=True)
            vres = json.loads(ver.stdout or "{}")
            row = {"mode": mode["name"], "rep": rep, "wall_s": wall,
                   "steps": times, "natural_match": vres.get("natural_match"),
                   "strict_match": vres.get("strict_match")}
            print(json.dumps(row))
            results.append(row)
    Path(args.out).write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
