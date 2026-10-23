import sqlite3
import tempfile
import unittest
from pathlib import Path

from src import demo_db
from src.catalog import CatalogError, load_catalog
from src.compiler import (CompileError, Filter, MetricQuery, compile_query,
                          metric_expression, parse_filter)

ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_catalog(ROOT / "catalog" / "metrics.yaml")


class CompilerTests(unittest.TestCase):
    def test_simple_metric(self):
        self.assertEqual(metric_expression(CATALOG, "revenue"), "SUM(revenue)")
        self.assertEqual(metric_expression(CATALOG, "orders"), "COUNT(DISTINCT order_id)")

    def test_derived_metric_expands(self):
        expr = metric_expression(CATALOG, "avg_order_value")
        self.assertIn("SUM(revenue)", expr)
        self.assertIn("COUNT(DISTINCT order_id)", expr)

    def test_group_by_and_filter_are_parameterised(self):
        q = MetricQuery(["revenue"], ["region"], [Filter("region", "=", "North'; DROP TABLE sales;--")])
        sql, params = compile_query(CATALOG, q)
        self.assertIn("WHERE region = ?", sql)
        self.assertNotIn("DROP", sql)
        self.assertEqual(params, ["North'; DROP TABLE sales;--"])

    def test_time_grain(self):
        sql, _ = compile_query(CATALOG, MetricQuery(["revenue"], ["order_date:month"]))
        self.assertIn("strftime('%Y-%m', order_date)", sql)

    def test_unknown_names_rejected(self):
        with self.assertRaises(CompileError):
            compile_query(CATALOG, MetricQuery(["nope"]))
        with self.assertRaises(CompileError):
            compile_query(CATALOG, MetricQuery(["revenue"], ["nope"]))
        with self.assertRaises(CompileError):
            compile_query(CATALOG, MetricQuery(["revenue"], ["region:month"]))

    def test_parse_filter(self):
        self.assertEqual(parse_filter("region=North"), Filter("region", "=", "North"))
        self.assertEqual(parse_filter("region in North,South"), Filter("region", "in", ["North", "South"]))

    def test_end_to_end_matches_raw_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = demo_db.build(Path(tmp) / "t.db")
            conn = sqlite3.connect(db)
            sql, params = compile_query(CATALOG, MetricQuery(["revenue", "orders"]))
            revenue, orders = conn.execute(sql, params).fetchone()
            raw = conn.execute("SELECT SUM(revenue), COUNT(DISTINCT order_id) FROM sales").fetchone()
            self.assertEqual((revenue, orders), raw)


class CatalogValidationTests(unittest.TestCase):
    def _load(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(text)
        return load_catalog(f.name)

    def test_circular_reference_detected(self):
        with self.assertRaises(CatalogError):
            self._load("""
model: {name: m, table: t}
metrics:
  - {name: a, expression: "{b}"}
  - {name: b, expression: "{a}"}
""")

    def test_unknown_reference_detected(self):
        with self.assertRaises(CatalogError):
            self._load("""
model: {name: m, table: t}
metrics:
  - {name: a, expression: "{missing} + 1"}
""")

    def test_bad_agg_rejected(self):
        with self.assertRaises(CatalogError):
            self._load("""
model: {name: m, table: t}
metrics:
  - {name: a, agg: median, column: x}
""")


if __name__ == "__main__":
    unittest.main()
