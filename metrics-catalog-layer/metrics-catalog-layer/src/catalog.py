"""Load and validate the YAML metrics catalog."""
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_AGGS = {"sum", "count", "count_distinct", "avg", "min", "max"}
VALID_GRAINS = {"day", "month", "quarter", "year"}
REF_PATTERN = re.compile(r"\{(\w+)\}")


class CatalogError(ValueError):
    """Raised when the catalog file is invalid."""


@dataclass
class Dimension:
    name: str
    column: str
    type: str = "categorical"


@dataclass
class Metric:
    name: str
    description: str = ""
    agg: str | None = None
    column: str | None = None
    expression: str | None = None
    format: str = "number"

    @property
    def is_derived(self) -> bool:
        return self.expression is not None


@dataclass
class Catalog:
    model_name: str
    table: str
    dimensions: dict[str, Dimension] = field(default_factory=dict)
    metrics: dict[str, Metric] = field(default_factory=dict)


def _ident(value: str, what: str) -> str:
    """Identifiers (tables/columns) must be plain names to keep generated SQL safe."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(value)):
        raise CatalogError(f"Invalid {what}: {value!r}")
    return value


def load_catalog(path) -> Catalog:
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict):
        raise CatalogError("Catalog must be a YAML mapping")

    model = raw.get("model") or {}
    catalog = Catalog(
        model_name=model.get("name", "model"),
        table=_ident(model.get("table", ""), "table name"),
    )

    for d in raw.get("dimensions", []):
        if d["name"] in catalog.dimensions:
            raise CatalogError(f"Duplicate dimension: {d['name']}")
        catalog.dimensions[d["name"]] = Dimension(
            name=_ident(d["name"], "dimension name"),
            column=_ident(d["column"], "dimension column"),
            type=d.get("type", "categorical"),
        )

    for m in raw.get("metrics", []):
        name = _ident(m["name"], "metric name")
        if name in catalog.metrics:
            raise CatalogError(f"Duplicate metric: {name}")
        metric = Metric(
            name=name,
            description=m.get("description", ""),
            agg=m.get("agg"),
            column=m.get("column"),
            expression=m.get("expression"),
            format=m.get("format", "number"),
        )
        if metric.is_derived:
            if metric.agg or metric.column:
                raise CatalogError(f"{name}: derived metric cannot also set agg/column")
        else:
            if metric.agg not in VALID_AGGS:
                raise CatalogError(f"{name}: agg must be one of {sorted(VALID_AGGS)}")
            _ident(metric.column or "", f"{name} column")
        catalog.metrics[name] = metric

    _validate_references(catalog)
    return catalog


def _validate_references(catalog: Catalog) -> None:
    """Derived metrics must reference existing metrics, with no cycles."""

    def visit(name: str, stack: tuple) -> None:
        if name in stack:
            raise CatalogError(f"Circular metric reference: {' -> '.join(stack + (name,))}")
        metric = catalog.metrics.get(name)
        if metric is None:
            raise CatalogError(f"Unknown metric referenced: {name}")
        if metric.is_derived:
            for ref in REF_PATTERN.findall(metric.expression):
                visit(ref, stack + (name,))

    for name in catalog.metrics:
        visit(name, ())
