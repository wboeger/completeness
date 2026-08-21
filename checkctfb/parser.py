"""Reads the DwC-A Taxon core table (tab-delimited) into typed rows."""

from __future__ import annotations

import csv
from collections import namedtuple
from pathlib import Path
from typing import Iterable, List, Mapping

TaxonRow = None  # populated by read_taxon_table / rows_from_records once the header is known

# DwC term "class" collides with the Python keyword; every other header
# field is already a valid identifier, so this is the only rename needed.
_FIELD_RENAMES = {"class": "taxonClass"}

# The Taxon core table's full DwC column set, in taxon.txt header order (see
# CONTEXT.md). Every rule in rules.py is written against these term names,
# so `rows_from_records` defaults to this set: a source record missing a
# column (e.g. an external dataset with no `kingdom`) still produces a row
# with that attribute set to "", matching how a blank taxon.txt cell reads,
# instead of raising AttributeError inside a rule.
CANONICAL_FIELDS = (
    "id", "taxonID", "acceptedNameUsageID", "parentNameUsageID", "scientificName",
    "acceptedNameUsage", "parentNameUsage", "namePublishedInYear", "higherClassification",
    "kingdom", "phylum", "class", "order", "superfamily", "family", "subfamily", "tribe",
    "subtribe", "genus", "subgenus", "specificEpithet", "infraspecificEpithet", "taxonRank",
    "scientificNameAuthorship", "taxonomicStatus", "nomenclaturalStatus", "modified",
    "language", "bibliographicCitation", "institutionCode", "institutionID",
)


def read_taxon_table(path: Path) -> List["TaxonRow"]:
    """Reads taxon.txt into a list of namedtuples, one per row.

    Field names come from the file's header, DwC term names renamed only
    where they collide with a Python keyword (see _FIELD_RENAMES). Missing
    trailing columns are padded to "" so tuple length always matches the
    header even if the server omits blank trailing fields.
    """
    global TaxonRow
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = [_FIELD_RENAMES.get(name, name) for name in next(reader)]
        TaxonRow = namedtuple("TaxonRow", header)
        width = len(header)
        rows = []
        for raw in reader:
            if len(raw) < width:
                raw = raw + [""] * (width - len(raw))
            elif len(raw) > width:
                raw = raw[:width]
            rows.append(TaxonRow(*raw))
        return rows


def rows_from_records(
    records: Iterable[Mapping[str, object]],
    fields: Iterable[str] = CANONICAL_FIELDS,
) -> List["TaxonRow"]:
    """Builds TaxonRow namedtuples from an in-memory dataset instead of
    taxon.txt — e.g. `dataframe.to_dict("records")` from a Taxon table
    already loaded elsewhere (see CONTEXT.md's decision on reuse). Each
    record is any DwC-term-keyed mapping (extra keys ignored); a record
    missing a `fields` key reads as "", same as a blank taxon.txt cell.
    None and NaN (`v != v`) both coerce to ""; every other value is
    stringified so the regex-based rules never choke on a non-str dtype.
    """
    global TaxonRow
    fields = list(fields)
    header = [_FIELD_RENAMES.get(name, name) for name in fields]
    TaxonRow = namedtuple("TaxonRow", header)
    rows = []
    for record in records:
        values = []
        for name in fields:
            value = record.get(name, "")
            if value is None or value != value:  # None or float NaN
                value = ""
            elif not isinstance(value, str):
                value = str(value)
            values.append(value)
        rows.append(TaxonRow(*values))
    return rows
