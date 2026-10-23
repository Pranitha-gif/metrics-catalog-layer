# metrics-catalog-layer

A simple base project: define business metrics **once** in YAML, then compile
them to SQL on demand. This is the core idea behind a semantic / metrics layer.

```
catalog/metrics.yaml ──► catalog.py (load + validate)
                              │
          metric request ──► compiler.py ──► SQL + params ──► SQLite (demo.db)
```

## Structure

```
metrics-catalog-layer/
├── catalog/metrics.yaml   # dimensions + simple/derived metrics
├── src/
│   ├── catalog.py         # YAML loader, validation, cycle detection
│   ├── compiler.py        # metrics + dimensions + filters -> SQL
│   ├── demo_db.py         # builds a demo `sales` table in SQLite
│   └── cli.py             # command line interface
└── tests/test_metrics.py
```

## Run

```bash
pip install -r requirements.txt

python -m src.cli --list
python -m src.cli -m revenue orders -b region
python -m src.cli -m revenue profit_margin_pct -b order_date:month --show-sql
python -m src.cli -m revenue -b category -f "region=North" --order-by revenue --limit 3
python -m src.cli -m revenue -b region -f "region in North,South"

python -m unittest discover -s tests -v
```

## Key ideas

- **Simple metrics**: one aggregation over one column (`sum`, `count`, `count_distinct`, `avg`, `min`, `max`).
- **Derived metrics**: expressions over other metrics, e.g. `{profit} / {revenue}`. References are expanded recursively and checked for unknown names and cycles.
- **Time grains**: `order_date:month` compiles to a month bucket (day, month, quarter, year).
- **Safe by design**: identifiers are validated, filter values are bound as parameters.

## Ideas to extend

- Point `table` at the Gold layer of your medallion pipeline or the star schema from `sales-analytics-mart`
- Add joins between models (entities and relationships)
- Add a warehouse dialect map (DuckDB, Postgres, BigQuery) for time grains
- Expose the compiler through a small REST API
- Add a metric-level access policy or certified/owner fields
