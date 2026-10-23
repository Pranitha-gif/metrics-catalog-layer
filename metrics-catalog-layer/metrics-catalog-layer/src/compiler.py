"""Compile a metric request (metrics + dimensions + filters) into SQL."""
import re
from dataclasses import dataclass, field

from .catalog import REF_PATTERN, VALID_GRAINS, Catalog

# SQLite expressions per time grain. Swap these out for another warehouse.
GRAIN_SQL = {
    "day": "date({col})",
    "month": "strftime('%Y-%m', {col})",
    "quarter": "strftime('%Y', {col}) || '-Q' || ((cast(strftime('%m', {col}) as integer) + 2) / 3)",
    "year": "strftime('%Y', {col})",
}

FILTER_OPS = {"=", "!=", ">", ">=", "<", "<=", "in"}


class CompileError(ValueError):
    """Raised when a metric request cannot be compiled."""


@dataclass
class Filter:
    dimension: str
    op: str
    value: object


@dataclass
class MetricQuery:
    metrics: list[str]
    dimensions: list[str] = field(default_factory=list)   # "region" or "order_date:month"
    filters: list[Filter] = field(default_factory=list)
    order_by: str | None = None                            # a metric or dimension name
    descending: bool = True
    limit: int | None = None


def metric_expression(catalog: Catalog, name: str) -> str:
    """Return the SQL expression for a metric (recursively expanding derived metrics)."""
    metric = catalog.metrics.get(name)
    if metric is None:
        raise CompileError(f"Unknown metric: {name}")

    if metric.is_derived:
        def replace(match):
            return f"({metric_expression(catalog, match.group(1))})"
        return REF_PATTERN.sub(replace, metric.expression)

    if metric.agg == "count_distinct":
        return f"COUNT(DISTINCT {metric.column})"
    return f"{metric.agg.upper()}({metric.column})"


def _dimension_expression(catalog: Catalog, spec: str):
    """'region' -> (sql, alias); 'order_date:month' -> (sql, alias)."""
    name, _, grain = spec.partition(":")
    dim = catalog.dimensions.get(name)
    if dim is None:
        raise CompileError(f"Unknown dimension: {name}")
    if dim.type == "time":
        grain = grain or "day"
        if grain not in VALID_GRAINS:
            raise CompileError(f"Invalid grain {grain!r}; choose from {sorted(VALID_GRAINS)}")
        return GRAIN_SQL[grain].format(col=dim.column), name
    if grain:
        raise CompileError(f"Dimension {name!r} is not a time dimension; grain not allowed")
    return dim.column, name


def compile_query(catalog: Catalog, query: MetricQuery):
    """Return (sql, params). Values are always bound as parameters, never inlined."""
    if not query.metrics:
        raise CompileError("At least one metric is required")

    select_parts, group_exprs, aliases = [], [], []
    for spec in query.dimensions:
        expr, alias = _dimension_expression(catalog, spec)
        select_parts.append(f"{expr} AS {alias}")
        group_exprs.append(expr)
        aliases.append(alias)

    for name in query.metrics:
        select_parts.append(f"{metric_expression(catalog, name)} AS {name}")
        aliases.append(name)

    sql = f"SELECT\n  " + ",\n  ".join(select_parts) + f"\nFROM {catalog.table}"

    params = []
    where_parts = []
    for f in query.filters:
        dim = catalog.dimensions.get(f.dimension)
        if dim is None:
            raise CompileError(f"Unknown filter dimension: {f.dimension}")
        if f.op not in FILTER_OPS:
            raise CompileError(f"Unsupported operator: {f.op}")
        if f.op == "in":
            values = list(f.value)
            where_parts.append(f"{dim.column} IN ({', '.join('?' * len(values))})")
            params.extend(values)
        else:
            where_parts.append(f"{dim.column} {f.op} ?")
            params.append(f.value)
    if where_parts:
        sql += "\nWHERE " + " AND ".join(where_parts)

    if group_exprs:
        sql += "\nGROUP BY " + ", ".join(str(i + 1) for i in range(len(group_exprs)))

    if query.order_by:
        if query.order_by not in aliases:
            raise CompileError(f"Cannot order by {query.order_by!r}; choose from {aliases}")
        sql += f"\nORDER BY {query.order_by} {'DESC' if query.descending else 'ASC'}"
    elif query.dimensions:
        sql += "\nORDER BY " + ", ".join(str(i + 1) for i in range(len(group_exprs)))

    if query.limit is not None:
        sql += f"\nLIMIT {int(query.limit)}"

    return sql, params


def parse_filter(text: str) -> Filter:
    """Parse 'region=North', 'revenue>=10', or 'region in North,South'."""
    m = re.fullmatch(r"\s*(\w+)\s*(>=|<=|!=|=|>|<|\s+in\s+)\s*(.+?)\s*", text)
    if not m:
        raise CompileError(f"Cannot parse filter: {text!r}")
    dim, op, value = m.group(1), m.group(2).strip(), m.group(3)
    if op == "in":
        return Filter(dim, "in", [v.strip() for v in value.split(",")])
    return Filter(dim, op, value)
