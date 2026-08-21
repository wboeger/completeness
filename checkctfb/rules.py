"""Anomaly-detection rules for the CTFB Taxon core table.

Each rule is a plain function: (rows) -> Iterator[Anomaly]. Registered in
ALL_RULES. Adding a category means adding a function + a registry entry —
see CONTEXT.md for why this is hardcoded rather than config-driven.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Iterable, Iterator, List

from .parser import TaxonRow


class Severity(str, Enum):
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Anomaly:
    taxon_id: str
    category: str
    severity: Severity
    field: str
    value: str
    detail: str


# --- shared patterns / vocabularies, all derived from a live audit of the
# dataset (2026-08) — see CONTEXT.md ---------------------------------------

_CAPITALIZED_WORD = re.compile(r"^[A-Z][a-zà-ÿ]*$")
_LOWERCASE_EPITHET = re.compile(r"^[a-zà-ÿ][a-zà-ÿ'’-]*$")
_WHITESPACE_ISSUE = re.compile(r"^\s|\s$|\s{2,}")
_PLAIN_YEAR = re.compile(r"^\d{4}$")
_BRACKETED_YEAR = re.compile(r"^\[(\d{4})\]$")
_MIN_YEAR = 1750
_MAX_YEAR = date.today().year + 1

VALID_TAXONOMIC_STATUS = {"accepted", "synonym"}

VALID_NOMENCLATURAL_STATUS = {
    "",
    "CHANGED_COMBINATION",
    "HOMONYM_JUNIOR",
    "JUNIOR_SYNONYM_CHANGED_COMBINATION",
    "JUNIOR_SYNONYM_ORIGINAL_COMBINATION",
    "ORIGINAL_COMBINATION",
    "PARTIM",
    "REPLACEMENT_NAME",
    "SUPPRESSED_NAME",
    "UNPLACED_TAXON",
    "VARIANT_SPELLING",
}

VALID_TAXON_RANK = {
    "class", "family", "genus", "infraclass", "infraorder", "order",
    "parvorder", "phylum", "species", "subclass", "subfamily", "subgenus",
    "suborder", "subspecies", "subtribe", "superclass", "superfamily",
    "superorder", "tribe",
}

# Name-bearing fields checked for whitespace problems.
_NAME_FIELDS = (
    "scientificName", "kingdom", "phylum", "taxonClass", "order", "superfamily",
    "family", "subfamily", "tribe", "subtribe", "genus", "subgenus",
    "specificEpithet", "infraspecificEpithet",
)


def check_malformed_binomial(rows: Iterable[TaxonRow]) -> Iterator[Anomaly]:
    """Genus must be Capitalized; specific/infraspecific epithets lowercase."""
    for row in rows:
        if row.genus and not _CAPITALIZED_WORD.match(row.genus):
            yield Anomaly(
                row.taxonID, "malformed_binomial", Severity.WARNING,
                "genus", row.genus,
                "genus must start with a capital letter, rest lowercase",
            )
        for field_name, value in (
            ("specificEpithet", row.specificEpithet),
            ("infraspecificEpithet", row.infraspecificEpithet),
        ):
            if value and not _LOWERCASE_EPITHET.match(value):
                yield Anomaly(
                    row.taxonID, "malformed_binomial", Severity.WARNING,
                    field_name, value,
                    f"{field_name} must be lowercase letters only (ICZN)",
                )


def check_extra_whitespace(rows: Iterable[TaxonRow]) -> Iterator[Anomaly]:
    """Leading/trailing or doubled internal whitespace in name fields."""
    for row in rows:
        for field_name in _NAME_FIELDS:
            value = getattr(row, field_name)
            if value and _WHITESPACE_ISSUE.search(value):
                yield Anomaly(
                    row.taxonID, "extra_whitespace", Severity.WARNING,
                    field_name, value,
                    "leading/trailing or doubled internal whitespace",
                )


def check_date(rows: Iterable[TaxonRow]) -> Iterator[Anomaly]:
    """namePublishedInYear: plain 4-digit year, bracketed uncertain year, or malformed."""
    for row in rows:
        value = row.namePublishedInYear
        if not value:
            continue

        plain = _PLAIN_YEAR.match(value)
        bracketed = _BRACKETED_YEAR.match(value)

        if plain:
            year = int(value)
            if _MIN_YEAR <= year <= _MAX_YEAR:
                continue
            yield Anomaly(
                row.taxonID, "malformed_date", Severity.ERROR,
                "namePublishedInYear", value,
                f"year outside plausible range {_MIN_YEAR}-{_MAX_YEAR}",
            )
        elif bracketed:
            year = int(bracketed.group(1))
            if _MIN_YEAR <= year <= _MAX_YEAR:
                yield Anomaly(
                    row.taxonID, "uncertain_date", Severity.WARNING,
                    "namePublishedInYear", value,
                    "bracketed year: nomenclatural convention for inferred/uncertain date",
                )
            else:
                yield Anomaly(
                    row.taxonID, "malformed_date", Severity.ERROR,
                    "namePublishedInYear", value,
                    f"bracketed year outside plausible range {_MIN_YEAR}-{_MAX_YEAR}",
                )
        else:
            yield Anomaly(
                row.taxonID, "malformed_date", Severity.ERROR,
                "namePublishedInYear", value,
                "not a 4-digit year or a [4-digit] uncertain year",
            )


def check_duplicate_taxon_id(rows: List[TaxonRow]) -> Iterator[Anomaly]:
    counts = Counter(row.taxonID for row in rows)
    for row in rows:
        if counts[row.taxonID] > 1:
            yield Anomaly(
                row.taxonID, "duplicate_taxon_id", Severity.ERROR,
                "taxonID", row.taxonID,
                f"taxonID appears {counts[row.taxonID]} times in the table",
            )


def check_orphan_reference(rows: List[TaxonRow]) -> Iterator[Anomaly]:
    known_ids = {row.taxonID for row in rows}
    for row in rows:
        for field_name in ("parentNameUsageID", "acceptedNameUsageID"):
            value = getattr(row, field_name)
            if value and value not in known_ids:
                yield Anomaly(
                    row.taxonID, "orphan_reference", Severity.ERROR,
                    field_name, value,
                    f"{field_name} does not match any taxonID in the table",
                )


def check_taxonomic_status(rows: Iterable[TaxonRow]) -> Iterator[Anomaly]:
    for row in rows:
        if row.taxonomicStatus not in VALID_TAXONOMIC_STATUS:
            yield Anomaly(
                row.taxonID, "invalid_taxonomic_status", Severity.ERROR,
                "taxonomicStatus", row.taxonomicStatus,
                f"expected one of {sorted(VALID_TAXONOMIC_STATUS)}",
            )


def check_nomenclatural_status(rows: Iterable[TaxonRow]) -> Iterator[Anomaly]:
    for row in rows:
        if row.nomenclaturalStatus not in VALID_NOMENCLATURAL_STATUS:
            yield Anomaly(
                row.taxonID, "invalid_nomenclatural_status", Severity.ERROR,
                "nomenclaturalStatus", row.nomenclaturalStatus,
                f"expected empty or one of {sorted(VALID_NOMENCLATURAL_STATUS - {''})}",
            )


def check_taxon_rank(rows: Iterable[TaxonRow]) -> Iterator[Anomaly]:
    for row in rows:
        if row.taxonRank not in VALID_TAXON_RANK:
            yield Anomaly(
                row.taxonID, "invalid_taxon_rank", Severity.ERROR,
                "taxonRank", row.taxonRank,
                f"expected one of {sorted(VALID_TAXON_RANK)}",
            )


# Registry: name -> rule function. `checkctfb check --category NAME` filters
# against these keys.
ALL_RULES = {
    "malformed_binomial": check_malformed_binomial,
    "extra_whitespace": check_extra_whitespace,
    "date": check_date,  # produces both malformed_date and uncertain_date
    "duplicate_taxon_id": check_duplicate_taxon_id,
    "orphan_reference": check_orphan_reference,
    "invalid_taxonomic_status": check_taxonomic_status,
    "invalid_nomenclatural_status": check_nomenclatural_status,
    "invalid_taxon_rank": check_taxon_rank,
}


def run_rules(rows: List[TaxonRow], categories: Iterable[str] | None = None) -> List[Anomaly]:
    """Runs the requested rule categories (default: all) over rows."""
    selected = categories or ALL_RULES.keys()
    unknown = set(selected) - ALL_RULES.keys()
    if unknown:
        raise ValueError(f"Unknown rule categories: {sorted(unknown)}")
    anomalies: List[Anomaly] = []
    for name in selected:
        anomalies.extend(ALL_RULES[name](rows))
    return anomalies
