# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Attribution-Recorded-On: 2026-11-06
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Reuse: preserve applicable notices and cite the original author.

"""Canonical correctness digest of the six destination tables.

Two digests per table:
- natural: surrogate identity keys replaced by the natural key they point to
  (table1 -> raw_id through id_column_3; table3 -> its value tuple), so it is
  independent of the order in which identity values were drawn;
- strict: every column, including identity values.
Also checks the managed row counters and the registered versions.
"""
import argparse
import json
import subprocess
import sys

NATURAL = {
    "table3": """SELECT text_column_1, text_column_2, numeric_column_1, text_column_3, text_column_4
                 FROM public.table3""",
    "table4": "SELECT id_column_1, text_column_1, text_column_2 FROM public.table4",
    "table1": """SELECT t.id_column_3, t.id_column_2, t.text_column_1, t.datetime_column_1, t.text_column_2,
                        t.integer_column_1, t.integer_column_2, t.integer_column_3, t.text_column_3,
                        d.text_column_1 AS d1, d.text_column_2 AS d2, d.numeric_column_1 AS d3,
                        d.text_column_3 AS d4, d.text_column_4 AS d5,
                        t.id_column_5, t.integer_column_4, t.integer_column_5, t.id_column_6,
                        t.integer_column_6, t.integer_column_7
                 FROM public.table1 t LEFT JOIN public.table3 d ON d.id_column_1 = t.id_column_4""",
    "table5": """SELECT m.id_column_3 AS raw_id, c.numeric_column_1, c.numeric_column_2, c.integer_column_1,
                        c.integer_column_2, c.id_column_3
                 FROM public.table5 c JOIN public.table1 m ON m.id_column_1 = c.id_column_2""",
    "table6": """SELECT m.id_column_3 AS raw_id, c.id_column_3
                 FROM public.table6 c JOIN public.table1 m ON m.id_column_1 = c.id_column_2""",
    "table2": """SELECT m.id_column_3 AS raw_id, c.integer_column_1, c.integer_column_2, c.text_column_1,
                        c.integer_column_3, c.integer_column_4, c.integer_column_5, c.integer_column_6
                 FROM public.table2 c JOIN public.table1 m ON m.id_column_1 = c.id_column_2""",
}


def psql(sql, db):
    out = subprocess.run(
        ["psql", "-U", "postgres", "-h", "/var/run/postgresql", "-d", db, "-qAtX", "-c", sql],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


def digest(query, db):
    sql = (
        "SELECT count(*) || ':' || md5(COALESCE(string_agg(r::text, E'\\n' ORDER BY r::text), '')) "
        f"FROM ({query}) AS r"
    )
    return psql(sql, db)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="kaggle_challenge")
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect", default=None, help="JSON from a reference run to compare against")
    ap.add_argument("--expect-versions", type=int, default=1,
                    help="versions expected per destination since the last reset (0 = do not check)")
    args = ap.parse_args()
    result = {"natural": {}, "strict": {}, "counters_ok": {}, "versions": None}
    for table, query in NATURAL.items():
        result["natural"][table] = digest(query, args.db)
        result["strict"][table] = digest(f"SELECT * FROM public.{table}", args.db)
        actual = psql(f"SELECT count(*) FROM public.{table}", args.db)
        counter = psql(
            "SELECT row_count FROM public.pgdm_table_row_counts "
            f"WHERE schema_name='public' AND table_name='{table}'", args.db)
        result["counters_ok"][table] = (actual == counter)
    result["versions"] = psql(
        "SELECT json_agg(json_build_object('t', v.table_name, 'code', v.version_code, 'kind', v.operation_kind,"
        " 'deps', (SELECT count(*) FROM app_control.table_version_dependencies d WHERE d.table_version_id = v.id))"
        " ORDER BY v.table_name, v.version_code) FROM app_control.table_versions v"
        f" WHERE v.database_name = '{args.db}' AND v.operation_kind = 'cross_table_expand_v1'",
        "postgres_data_manager")
    ok = all(result["counters_ok"].values())
    versions = json.loads(result["versions"] or "[]")
    per_table = {}
    for item in versions:
        per_table.setdefault(item["t"], []).append(item)
    result["versions_ok"] = True
    if args.expect_versions:
        result["versions_ok"] = (
            sorted(per_table) == sorted(NATURAL)
            and all(len(items) == args.expect_versions for items in per_table.values())
            and all(item["deps"] == 1 for item in versions)
        )
    ok = ok and result["versions_ok"]
    if args.expect:
        ref = json.load(open(args.expect))
        result["natural_match"] = ref["natural"] == result["natural"]
        result["strict_match"] = ref["strict"] == result["strict"]
        ok = ok and result["natural_match"]
    result["ok"] = ok
    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=1)
    print(json.dumps(result))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
