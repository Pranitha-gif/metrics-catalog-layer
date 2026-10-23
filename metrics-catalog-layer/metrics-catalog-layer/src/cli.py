"""Command line interface for the metrics catalog layer.

Examples:
  python -m src.cli --list
  python -m src.cli -m revenue orders -b region
  python -m src.cli -m revenue profit_margin_pct -b order_date:month --show-sql
  python -m src.cli -m revenue -b category -f "region=North" --order-by revenue --limit 3
"""
import argparse
import sqlite3
from pathlib import Path

from . import demo_db
from .catalog import load_catalog
from .compiler import CompileError, MetricQuery, compile_query, parse_filter

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "catalog" / "metrics.yaml"


def print_table(columns, rows):
    str_rows = [[("" if v is None else f"{v:,.2f}" if isinstance(v, float) else str(v)) for v in r]
                for r in rows]
    widths = [max(len(c), *(len(r[i]) for r in str_rows)) if str_rows else len(c)
              for i, c in enumerate(columns)]
    print(" | ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in str_rows:
        print(" | ".join(v.ljust(w) for v, w in zip(r, widths)))


def main(argv=None):
    p = argparse.ArgumentParser(description="Query the metrics catalog")
    p.add_argument("-m", "--metrics", nargs="+", help="metric names")
    p.add_argument("-b", "--by", nargs="*", default=[], help="dimensions, e.g. region order_date:month")
    p.add_argument("-f", "--filter", action="append", default=[], help='e.g. "region=North"')
    p.add_argument("--order-by", help="metric or dimension to sort by")
    p.add_argument("--asc", action="store_true", help="sort ascending (default descending)")
    p.add_argument("--limit", type=int)
    p.add_argument("--show-sql", action="store_true", help="print the compiled SQL")
    p.add_argument("--list", action="store_true", help="list available metrics and dimensions")
    args = p.parse_args(argv)

    catalog = load_catalog(CATALOG_PATH)

    if args.list:
        print("Metrics:")
        for m in catalog.metrics.values():
            kind = "derived" if m.is_derived else m.agg
            print(f"  {m.name:<22} [{kind}] {m.description}")
        print("\nDimensions:")
        for d in catalog.dimensions.values():
            print(f"  {d.name:<22} ({d.type})")
        return 0

    if not args.metrics:
        p.error("--metrics is required (or use --list)")

    if not demo_db.DB_PATH.exists():
        demo_db.build()

    try:
        query = MetricQuery(
            metrics=args.metrics,
            dimensions=args.by,
            filters=[parse_filter(f) for f in args.filter],
            order_by=args.order_by,
            descending=not args.asc,
            limit=args.limit,
        )
        sql, params = compile_query(catalog, query)
    except CompileError as e:
        p.error(str(e))

    if args.show_sql:
        print(sql)
        print(f"-- params: {params}\n")

    conn = sqlite3.connect(demo_db.DB_PATH)
    cur = conn.execute(sql, params)
    print_table([c[0] for c in cur.description], cur.fetchall())
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
