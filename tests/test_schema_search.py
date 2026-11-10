"""
Unit tests for schema auto-detection across 'curated', 'rdm' and 'historical',
the search_schemas plumbing, and the persisted-config migration.

Uses a FakeCursor so no Trino connection is needed.
"""

import re
import unittest

import generate_trino_diff
from generate_trino_diff import DEFAULT_SCHEMAS, fetch_columns, parse_schema_list
from trino_diff.backend.config_manager import DEFAULT_CONFIG, migrate_config


class FakeCursor:
    """Minimal cursor emulating the two information_schema query shapes used by
    fetch_columns: auto mode (table_schema IN (...)) and explicit schema mode."""

    def __init__(self, schema_rows):
        # schema_rows: {schema_name: [(column_name, data_type), ...]}
        self.schema_rows = schema_rows
        self.queries = []
        self._last_sql = ""

    def execute(self, sql):
        self.queries.append(sql)
        self._last_sql = sql

    def fetchall(self):
        sql = self._last_sql
        m = re.search(r"table_schema\s+IN\s*\(([^)]*)\)", sql, re.IGNORECASE)
        if m:
            schemas = [s.strip().strip("'") for s in m.group(1).split(",")]
            rows = []
            for sch in schemas:
                for col, dt in self.schema_rows.get(sch, []):
                    rows.append((sch, col, dt))
            return rows
        m = re.search(r"table_schema\s*=\s*'([^']+)'", sql, re.IGNORECASE)
        if m:
            sch = m.group(1)
            return [(col, dt) for col, dt in self.schema_rows.get(sch, [])]
        return []


class TestParseSchemaList(unittest.TestCase):
    def test_comma_string(self):
        self.assertEqual(
            parse_schema_list("curated, rdm , historical"),
            ["curated", "rdm", "historical"],
        )

    def test_list_input(self):
        self.assertEqual(parse_schema_list(["Curated", " RDM "]), ["curated", "rdm"])

    def test_empty_inputs(self):
        self.assertEqual(parse_schema_list(""), [])
        self.assertEqual(parse_schema_list(None), [])
        self.assertEqual(parse_schema_list(" , ,"), [])


class TestDefaultSchemas(unittest.TestCase):
    def test_contains_historical_not_typo(self):
        self.assertIn("historical", DEFAULT_SCHEMAS)
        self.assertNotIn("historial", DEFAULT_SCHEMAS)

    def test_config_default_contains_historical(self):
        self.assertIn("historical", parse_schema_list(DEFAULT_CONFIG["default_schemas"]))


class TestFetchColumnsAutoDetect(unittest.TestCase):
    def test_historical_only(self):
        cur = FakeCursor({"historical": [("id", "bigint"), ("name", "varchar")]})
        schema, cols = fetch_columns(cur, "postgres", "ref_archive")
        self.assertEqual(schema, "historical")
        self.assertEqual([c["name"] for c in cols], ["id", "name"])

    def test_independent_source_target_resolution(self):
        src_cur = FakeCursor({"curated": [("id", "bigint")]})
        tgt_cur = FakeCursor({"historical": [("id", "bigint")]})
        pg_schema, _ = fetch_columns(src_cur, "postgres", "t")
        ora_schema, _ = fetch_columns(tgt_cur, "oracle", "t")
        self.assertEqual(pg_schema, "curated")
        self.assertEqual(ora_schema, "historical")

    def test_precedence_and_found_schemas(self):
        cur = FakeCursor({
            "curated": [("id", "bigint")],
            "historical": [("id", "bigint")],
        })
        found = []
        schema, _ = fetch_columns(cur, "postgres", "t", found_schemas=found)
        self.assertEqual(schema, "curated")
        self.assertEqual(found, ["curated", "historical"])

    def test_missing_everywhere(self):
        cur = FakeCursor({})
        found = []
        schema, cols = fetch_columns(cur, "postgres", "nope", found_schemas=found)
        self.assertEqual(schema, DEFAULT_SCHEMAS[0])
        self.assertEqual(cols, [])
        self.assertEqual(found, [])

    def test_explicit_schema(self):
        cur = FakeCursor({"rdm": [("code", "varchar")]})
        schema, cols = fetch_columns(cur, "oracle", "ref_t24_sector", schema="rdm")
        self.assertEqual(schema, "rdm")
        self.assertEqual([c["name"] for c in cols], ["code"])

    def test_explicit_schema_no_rows(self):
        cur = FakeCursor({"historical": [("code", "varchar")]})
        schema, cols = fetch_columns(cur, "oracle", "t", schema="rdm")
        self.assertEqual(schema, "rdm")
        self.assertEqual(cols, [])

    def test_custom_search_schemas(self):
        cur = FakeCursor({"archive": [("id", "bigint")]})
        schema, cols = fetch_columns(cur, "postgres", "t", search_schemas=["curated", "archive"])
        self.assertEqual(schema, "archive")
        self.assertEqual(len(cols), 1)
        self.assertIn("'archive'", cur.queries[0])
        self.assertNotIn("'historical'", cur.queries[0])

    def test_auto_query_includes_historical(self):
        cur = FakeCursor({})
        fetch_columns(cur, "postgres", "t")
        self.assertIn("'historical'", cur.queries[0])

    def test_exclusion_filtering_still_applies(self):
        cur = FakeCursor({"historical": [
            ("id", "bigint"),
            ("extraction_timestamp", "timestamp"),
            ("name_key", "varchar"),
            ("amount", "decimal"),
        ]})
        schema, cols = fetch_columns(
            cur, "postgres", "t",
            exclude_cols=["extraction_timestamp"],
            exclude_suffix="key",
            id_columns=["id"],
        )
        names = [c["name"] for c in cols]
        self.assertEqual(schema, "historical")
        self.assertEqual(names, ["id", "amount"])


class TestMigrateConfig(unittest.TestCase):
    def test_legacy_default_upgraded(self):
        cfg, changed = migrate_config({"default_schemas": "curated, rdm"})
        self.assertTrue(changed)
        self.assertEqual(cfg["default_schemas"], DEFAULT_CONFIG["default_schemas"])

    def test_legacy_spacing_variants(self):
        for legacy in ("curated,rdm", " curated , rdm ", "CURATED, RDM"):
            cfg, changed = migrate_config({"default_schemas": legacy})
            self.assertTrue(changed, legacy)
            self.assertEqual(cfg["default_schemas"], DEFAULT_CONFIG["default_schemas"])

    def test_legacy_other_orders_and_duplicates_upgraded(self):
        for legacy in ("rdm, curated", "RDM,Curated", "rdm", "curated", "curated, rdm, curated", ["rdm", "curated"]):
            cfg, changed = migrate_config({"default_schemas": legacy})
            self.assertTrue(changed, legacy)
            self.assertEqual(cfg["default_schemas"], DEFAULT_CONFIG["default_schemas"])

    def test_empty_or_missing_upgraded(self):
        for raw in ({}, {"default_schemas": ""}, {"default_schemas": None}):
            cfg, changed = migrate_config(dict(raw))
            self.assertTrue(changed, raw)
            self.assertEqual(cfg["default_schemas"], DEFAULT_CONFIG["default_schemas"])

    def test_custom_value_preserved(self):
        cfg, changed = migrate_config({"default_schemas": "curated, custom_schema"})
        self.assertFalse(changed)
        self.assertEqual(cfg["default_schemas"], "curated, custom_schema")

    def test_new_default_not_flagged(self):
        cfg, changed = migrate_config({"default_schemas": "curated, rdm, historical"})
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
