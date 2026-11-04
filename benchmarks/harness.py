# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Reuse: preserve applicable notices and cite the original author.

"""Headless driver for the DB Manager cross-table Expand operation.

Reproduces the service calls made by main.py::_execute_cross_table_expansion_thread
(prepare -> execute_cross_table_expansion -> register_cross_table_expansion_versions
-> refresh) against the app code found in --app-dir, connecting through SSH exactly
as the GUI does. MEASURED PROCESSING TOTAL is computed with the same rule as
ui/dialogs.py::ExpansionTimingReportDialog.measured_total_seconds.

It also samples resource usage: peak RSS of all PostgreSQL backends plus this
process, temp_bytes from pg_stat_database and the data-database size delta.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil

RECIPES = (
    ("01_table3.sql", "public.table3"),
    ("02_table4.sql", "public.table4"),
    ("03_table1.sql", "public.table1"),
    ("04_table5.sql", "public.table5"),
    ("05_table6.sql", "public.table6"),
    ("06_table2.sql", "public.table2"),
)


def measured_total_seconds(report: dict) -> float:
    return sum(
        max(float(item.get("seconds") or 0.0), 0.0)
        for item in (report.get("items") or [])
        if item.get("include_in_total", True)
    )


def psql_scalar(sql: str, db: str = "postgres") -> str:
    out = subprocess.run(
        ["psql", "-U", "postgres", "-h", "/var/run/postgresql", "-d", db, "-qAtX", "-c", sql],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


class PeakSampler(threading.Thread):
    def __init__(self, interval=0.5):
        super().__init__(daemon=True)
        self.interval = interval
        self.peak_pg_rss = 0
        self.peak_total_rss = 0
        self._stop = threading.Event()

    def run(self):
        me = os.getpid()
        while not self._stop.is_set():
            pg = 0
            total = 0
            for proc in psutil.process_iter(["name", "pid"]):
                try:
                    # PSS: shared pages (shared_buffers) are split among the processes
                    # mapping them instead of being counted once per backend.
                    rss = proc.memory_full_info().pss
                except Exception:
                    continue
                if proc.info["name"] and proc.info["name"].startswith("postgres"):
                    pg += rss
                    total += rss
                elif proc.info["pid"] == me or (proc.info["name"] or "").startswith(("psql", "sshd")):
                    total += rss
            self.peak_pg_rss = max(self.peak_pg_rss, pg)
            self.peak_total_rss = max(self.peak_total_rss, total)
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-dir", required=True)
    ap.add_argument("--db", default="kaggle_challenge")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", default="/results")
    ap.add_argument("--recipes", default=None, help="Directory with the six official SQL files")
    ap.add_argument("--env", action="append", default=[], help="KEY=VALUE passed to the app (tuning)")
    args = ap.parse_args()

    for item in args.env:
        key, _, value = item.partition("=")
        os.environ[key] = value
    app_dir = Path(args.app_dir).resolve()
    sys.path.insert(0, str(app_dir))
    os.chdir(app_dir)
    from services.postgres_service import PostgresAdminService  # noqa: E402

    recipe_dir = Path(args.recipes) if args.recipes else app_dir / "SQL files"
    destinations = [
        {
            "table_name": table_name,
            "version_title": "Benchmark expansion",
            "sql": (recipe_dir / file_name).read_text(encoding="utf-8"),
        }
        for file_name, table_name in RECIPES
    ]

    service = PostgresAdminService()
    service.connect(
        "127.0.0.1", 22, "pdm", os.environ["BENCH_SSH_PASS"], 5432,
        "pdm", os.environ["BENCH_PG_PASS"],
    )
    source = "public.raw_data"
    raw_schemas = service.list_table_raw_schemas(args.db, source)
    raw_schemas = service.resolve_raw_schema_interval(raw_schemas, raw_schemas[0], raw_schemas[-1])

    temp_before = int(psql_scalar(
        f"SELECT COALESCE(temp_bytes,0) FROM pg_stat_database WHERE datname='{args.db}'"))
    size_before = int(psql_scalar(f"SELECT pg_database_size('{args.db}')"))
    sampler = PeakSampler()
    sampler.start()
    wall_started = time.perf_counter()
    status = "ok"
    error = None
    report = service.create_cross_table_expansion_timing_report(
        args.db, source, raw_schemas, [d["table_name"] for d in destinations])
    try:
        with service.expansion_timing_scope(report, "prepare", "Ensure control database metadata"):
            service.ensure_admin_schema()
        import inspect
        kwargs = {}
        if "requested_by" in inspect.signature(service.execute_cross_table_expansion).parameters:
            kwargs = {"requested_by": "benchmark", "workstation_name": socket.gethostname()}
        result = service.execute_cross_table_expansion(
            database_name=args.db,
            source_full_table_name=source,
            raw_schemas=raw_schemas,
            destinations=destinations,
            timing_report=report,
            **kwargs,
        )
        registered = service.register_cross_table_expansion_versions(
            expansion_result=result,
            requested_by="benchmark",
            workstation_name=socket.gethostname(),
            timing_report=report,
        )
        with service.expansion_timing_scope(report, "refresh", "Invalidate destination filter caches"):
            pass  # local SQLite facet cache of the GUI; not present headless
        with service.expansion_timing_scope(report, "refresh", "Reload database table catalog"):
            service.list_tables(args.db)
        with service.expansion_timing_scope(report, "refresh", "Rebuild table navigation controls"):
            pass  # Tk widgets; not present headless
        with service.expansion_timing_scope(report, "refresh", "Build completion summary"):
            summary = ", ".join(f"{i['table_name']}={i['version_code']}" for i in registered)
        report["completed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception as exc:  # recorded, never hidden
        status = "error"
        error = f"{type(exc).__name__}: {exc}"
        summary = ""
    wall = time.perf_counter() - wall_started
    sampler.stop()
    sampler.join()
    service.close()
    temp_after = int(psql_scalar(
        f"SELECT COALESCE(temp_bytes,0) FROM pg_stat_database WHERE datname='{args.db}'"))
    size_after = int(psql_scalar(f"SELECT pg_database_size('{args.db}')"))

    out = {
        "tag": args.tag,
        "status": status,
        "error": error,
        "measured_processing_total_s": measured_total_seconds(report),
        "client_wall_s": wall,
        "peak_pg_pss_bytes": sampler.peak_pg_rss,
        "peak_total_pss_bytes": sampler.peak_total_rss,
        "temp_bytes_written": temp_after - temp_before,
        "db_size_delta_bytes": size_after - size_before,
        "versions": summary,
        "report": report,
    }
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / f"{args.tag}.json").write_text(json.dumps(out, indent=1, default=str))
    try:
        sys.path.insert(0, str(app_dir))
        from ui.dialogs import ExpansionTimingReportDialog  # needs customtkinter; optional
        text = ExpansionTimingReportDialog.build_report_text(report)
    except Exception:
        text = "\n".join(
            f"{i['stage']:8} {i['seconds']:10.3f} {'*' if i.get('include_in_total', True) else ' '} {i['name']}"
            for i in report.get("items") or []
        ) + f"\nMEASURED PROCESSING TOTAL: {measured_total_seconds(report):.3f} s\n"
    (Path(args.out) / f"{args.tag}.txt").write_text(text)
    print(json.dumps({k: v for k, v in out.items() if k != "report"}))
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
