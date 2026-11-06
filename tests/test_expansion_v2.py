# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Attribution-Recorded-On: 2026-11-06
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Reuse: preserve applicable notices and cite the original author.

import json
import subprocess
import unittest
from pathlib import Path

from services import expansion_engine as engine
from services.postgres_service import PostgresAdminService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECIPES = (
    ("01_table3.sql", "public.table3"),
    ("02_table4.sql", "public.table4"),
    ("03_table1.sql", "public.table1"),
    ("04_table5.sql", "public.table5"),
    ("05_table6.sql", "public.table6"),
    ("06_table2.sql", "public.table2"),
)


def prepared_official():
    destinations = [
        {
            "table_name": table_name,
            "version_title": "Synthetic expansion",
            "sql": (PROJECT_ROOT / "SQL files" / file_name).read_text(encoding="utf-8"),
        }
        for file_name, table_name in RECIPES
    ]
    prepared = PostgresAdminService._prepare_cross_table_expansion("public.raw_data", ["group001"], destinations)
    prepared["source_raw_id_unique"] = True
    return prepared


class ExpansionV2PlanTests(unittest.TestCase):
    def test_official_workload_segments(self):
        segments = engine.classify_destinations(PostgresAdminService, prepared_official())
        self.assertEqual(
            [(s["kind"], [i["destination"]["table_name"] for i in s["items"]]) for s in segments],
            [
                ("global", ["public.table3", "public.table4"]),
                ("chunked", ["public.table1", "public.table5", "public.table6", "public.table2"]),
            ],
        )

    def test_join_not_on_raw_id_is_not_chunked(self):
        prepared = prepared_official()
        destinations = [
            {"table_name": d["table_name"], "version_title": "x",
             "sql": (PROJECT_ROOT / "SQL files" / f).read_text(encoding="utf-8")}
            for f, d in zip([r[0] for r in RECIPES[:3]], prepared["destinations"][:3])
        ] + [{
            "table_name": "public.table5", "version_title": "x",
            "sql": "INSERT INTO public.table5 (numeric_column_1, id_column_2) SELECT 1, m.id_column_1 "
                   "FROM {{source}} AS s JOIN public.table1 AS m ON m.id_column_2 = 5",
        }]
        custom = PostgresAdminService._prepare_cross_table_expansion("public.raw_data", ["group001"], destinations)
        custom["source_raw_id_unique"] = True
        segments = engine.classify_destinations(PostgresAdminService, custom)
        self.assertEqual(segments[-1]["kind"], "global")
        self.assertIn("without a raw_id join", segments[-1]["items"][0]["reasons"][0])

    def classify_table5(self, sql):
        prepared = prepared_official()
        destinations = [
            {"table_name": d["table_name"], "version_title": "x",
             "sql": (PROJECT_ROOT / "SQL files" / f).read_text(encoding="utf-8")}
            for f, d in zip([r[0] for r in RECIPES[:3]], prepared["destinations"][:3])
        ] + [{"table_name": "public.table5", "version_title": "x", "sql": sql}]
        custom = PostgresAdminService._prepare_cross_table_expansion("public.raw_data", ["group001"], destinations)
        custom["source_raw_id_unique"] = True
        return engine.classify_destinations(PostgresAdminService, custom)[-1]["kind"]

    def test_join_forms_that_do_not_partition_run_globally(self):
        head = "INSERT INTO public.table5 (numeric_column_1, id_column_2) SELECT 1, m.id_column_1 "
        link = "m.id_column_3 = s.raw_id"
        for tail in (
            "FROM {{source}} AS s RIGHT JOIN public.table1 AS m ON " + link,
            "FROM {{source}} AS s RIGHT OUTER JOIN public.table1 AS m ON " + link,
            "FROM {{source}} AS s FULL JOIN public.table1 AS m ON " + link,
            "FROM public.table1 AS m LEFT JOIN {{source}} AS s ON " + link,
            "FROM {{source}} AS s JOIN public.table1 AS m ON TRUE WHERE m.id_column_3 = 5",
            "FROM {{source}} AS s JOIN public.table1 AS m ON NOT (" + link + ")",
            "FROM {{source}} AS s JOIN public.table1 AS m ON " + link + " JOIN public.table1 AS n ON TRUE",
        ):
            self.assertEqual(self.classify_table5(head + tail), "global", tail)

    def test_equality_outside_the_on_clause_is_not_a_link(self):
        sql = ("INSERT INTO public.table5 (numeric_column_1, id_column_2) "
               "SELECT (m.id_column_3 = s.raw_id)::int, m.id_column_1 "
               "FROM {{source}} AS s JOIN public.table1 AS m ON TRUE")
        self.assertEqual(self.classify_table5(sql), "global")

    def test_linked_inner_and_left_joins_stay_chunked(self):
        head = "INSERT INTO public.table5 (numeric_column_1, id_column_2) SELECT 1, m.id_column_1 "
        for tail in (
            "FROM {{source}} AS s JOIN public.table1 AS m ON m.id_column_3 = s.raw_id",
            "FROM {{source}} AS s LEFT JOIN public.table1 AS m ON s.raw_id = m.id_column_3 AND m.id_column_2 > 0",
        ):
            self.assertEqual(self.classify_table5(head + tail), "chunked", tail)

    def test_raw_id_of_another_alias_is_not_a_source_link(self):
        prepared = prepared_official()
        table1 = (PROJECT_ROOT / "SQL files" / "03_table1.sql").read_text(encoding="utf-8")
        self.assertIn("source_row.raw_id", table1)
        altered = table1.replace("source_row.raw_id", "alt.raw_id", 1).replace(
            "JOIN public.table3 AS dimension_row",
            "CROSS JOIN LATERAL (VALUES (source_row.raw_id + 1)) AS alt(raw_id) JOIN public.table3 AS dimension_row", 1)
        destination = [d for d in prepared["destinations"] if d["table_name"] == "public.table1"][0]
        columns = engine._raw_id_target_columns(
            PostgresAdminService, dict(destination, statement_templates=[
                t.replace("source_row.raw_id", "alt.raw_id", 1) for t in destination["statement_templates"]]), "{{source}}")
        self.assertEqual(columns, set())
        self.assertNotEqual(altered, table1)

    def test_every_statement_must_fill_the_link_column(self):
        prepared = prepared_official()
        destination = [d for d in prepared["destinations"] if d["table_name"] == "public.table1"][0]
        original = destination["statement_templates"]
        self.assertEqual(engine._raw_id_target_columns(PostgresAdminService, destination, "{{source}}"), {"id_column_3"})
        changed = original + [original[0].replace("source_row.raw_id", "source_row.raw_id + 1", 1)]
        self.assertEqual(engine._raw_id_target_columns(
            PostgresAdminService, dict(destination, statement_templates=changed), "{{source}}"), set())

    def test_each_statement_is_read_with_its_own_column_order(self):
        destination = {"statement_templates": [
            "INSERT INTO public.t (a, b) SELECT s.raw_id, 1 FROM {{source}} AS s",
            "INSERT INTO public.t (b, a) SELECT s.raw_id, 1 FROM {{source}} AS s",
        ]}
        self.assertEqual(engine._raw_id_target_columns(PostgresAdminService, destination, "{{source}}"), set())
        destination["statement_templates"][1] = "INSERT INTO public.t (b, a) SELECT 1, s.raw_id FROM {{source}} AS s"
        self.assertEqual(engine._raw_id_target_columns(PostgresAdminService, destination, "{{source}}"), {"a"})

    def test_content_hash_binds_values_to_their_row(self):
        sql = engine._content_hash_sql({"source_columns": [("raw_id", "bigint"), ("raw", "jsonb")]})
        self.assertIn("hashtextextended(concat_ws(':', r.", sql)
        self.assertNotIn(" + ", sql)

    def test_non_unique_raw_id_forces_global_execution(self):
        prepared = prepared_official()
        prepared["source_raw_id_unique"] = False
        segments = engine.classify_destinations(PostgresAdminService, prepared)
        self.assertEqual({s["kind"] for s in segments}, {"global"})

    def test_aggregates_force_global_execution(self):
        destinations = [{
            "table_name": "public.table4", "version_title": "x",
            "sql": "INSERT INTO public.table4 (id_column_1, text_column_1, text_column_2) "
                   "SELECT COUNT(*)::smallint, 'a', 'b' FROM {{source}} AS s",
        }]
        prepared = PostgresAdminService._prepare_cross_table_expansion("public.raw_data", ["group001"], destinations)
        segments = engine.classify_destinations(PostgresAdminService, prepared)
        self.assertEqual(segments[0]["kind"], "global")

    def test_templates_keep_official_recipe_text(self):
        prepared = prepared_official()
        for destination, (file_name, _table) in zip(prepared["destinations"], RECIPES):
            official = (PROJECT_ROOT / "SQL files" / file_name).read_text(encoding="utf-8").strip().rstrip(";").strip()
            self.assertEqual(destination["statement_templates"], [official])
            # The versioned recipe is still the full-source statement, unchanged.
            self.assertNotIn("pgdm.chunk_lo", destination["sql_recipe"])

    def test_split_insert_at_top_level_select(self):
        statement = prepared_official()["destinations"][0]["statements"][0]
        head, query = engine._split_insert(PostgresAdminService, statement)
        self.assertTrue(head.strip().upper().startswith("INSERT INTO PUBLIC.TABLE3"))
        self.assertTrue(query.strip().upper().startswith("SELECT DISTINCT"))
        self.assertEqual(head + query, statement)

    def test_gucs_are_whitelisted(self):
        with self.assertRaises(RuntimeError):
            engine.guc_sql({"session_replication_role": "replica"})
        with self.assertRaises(RuntimeError):
            engine.guc_sql({"work_mem": "1MB'; DROP TABLE x; --"})
        self.assertIn("SET LOCAL work_mem = '64MB';", engine.guc_sql({"work_mem": "64MB"}))

    def test_job_files_are_well_formed(self):
        prepared = prepared_official()
        segments = engine.classify_destinations(PostgresAdminService, prepared)
        files = engine.build_job_files(
            PostgresAdminService, prepared, segments, "00000000-0000-0000-0000-000000000001",
            engine.merge_config({}), "kaggle_challenge", "pdm", '"public"."pgdm_table_row_counts"',
            "-- registration", "postgres_data_manager",
        )
        self.assertIn("runner.sh", files)
        chunk_sql = files["segment_2.sql"]
        self.assertIn("FOR UPDATE SKIP LOCKED", chunk_sql)
        self.assertIn("LOCK TABLE \"public\".\"raw_data\" IN SHARE MODE", chunk_sql)
        self.assertEqual(chunk_sql.count("COMMIT;"), 1)
        # Every chunk marks itself done in the same transaction that inserts its rows.
        self.assertLess(chunk_sql.index("SET status = 'done'"), chunk_sql.index("COMMIT;"))
        result = subprocess.run(["bash", "-n"], input=files["runner.sh"].encode("utf-8"), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_spec_hash_is_stable_and_config_sensitive(self):
        prepared = prepared_official()
        a = engine.spec_hash(prepared, engine.merge_config({}))
        self.assertEqual(a, engine.spec_hash(prepared, engine.merge_config({})))
        self.assertNotEqual(a, engine.spec_hash(prepared, engine.merge_config({"chunk_rows": 1234})))

    def test_registration_is_idempotent_by_job_id(self):
        service = PostgresAdminService()
        prepared = prepared_official()
        sql = service._build_v2_registration_sql(
            prepared, [{"raw_schema": "group001", "version_code": "0000"}], "tester", "host",
            "kaggle_challenge", "00000000-0000-0000-0000-000000000001")
        self.assertIn("expansion_job_registrations", sql)
        self.assertIn("\\if :pgdm_registered", sql)
        self.assertEqual(sql.count("INSERT INTO \"app_control\".\"table_versions\""), 6)
        self.assertLess(sql.index("expansion_job_registrations (job_id"), sql.index("COMMIT;"))
        json.dumps(sql)


if __name__ == "__main__":
    unittest.main()
