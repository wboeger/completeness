"""Formats anomaly findings: console summary + CSV artifact."""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path
from typing import List, TextIO

from .parser import TaxonRow
from .rules import Anomaly, Severity

CSV_FIELDS = (
    "phylum", "class", "order", "family", "taxon_id", "taxon_name", "category",
    "severity", "field", "value", "detail",
)


def write_csv(anomalies: List[Anomaly], path: Path, rows: List[TaxonRow]) -> None:
    """Writes the anomaly report, grouped by phylum, then class, order, family.

    Higher-classification columns and `taxon_name` (scientificName) are
    looked up per taxon_id from `rows` rather than carried on Anomaly
    itself, so rule functions stay unaware of report layout. Rows are
    sorted (blank classification first) so an unclassified taxon's
    anomalies still cluster together.
    """
    by_id = {row.taxonID: row for row in rows}

    def classification(a: Anomaly):
        row = by_id.get(a.taxon_id)
        if row is None:
            return ("", "", "", "", "")
        return (row.phylum, row.taxonClass, row.order, row.family, row.scientificName)

    def sort_key(a: Anomaly):
        phylum, taxon_class, order, family, _name = classification(a)
        return (phylum, taxon_class, order, family, a.taxon_id, a.category)

    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_FIELDS)
        for a in sorted(anomalies, key=sort_key):
            phylum, taxon_class, order, family, name = classification(a)
            writer.writerow(
                [phylum, taxon_class, order, family, a.taxon_id, name, a.category,
                 a.severity.value, a.field, a.value, a.detail]
            )


def print_summary(anomalies: List[Anomaly], total_rows: int, out: TextIO = sys.stdout) -> None:
    counts = Counter((a.category, a.severity) for a in anomalies)
    errors = sum(1 for a in anomalies if a.severity is Severity.ERROR)
    warnings = sum(1 for a in anomalies if a.severity is Severity.WARNING)

    print(f"Checked {total_rows} Taxon rows.", file=out)
    if not anomalies:
        print("No anomalies found.", file=out)
        return

    print(f"{len(anomalies)} anomalies found ({errors} ERROR, {warnings} WARNING):", file=out)
    for (category, severity), count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  [{severity.value:7s}] {category:30s} {count}", file=out)
