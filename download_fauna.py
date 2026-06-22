#!/usr/bin/env python3
"""Download the full Catalogo Taxonomico da Fauna do Brasil dataset.

Source: https://fauna.jbrj.gov.br/rest/mv_planilha_extendida (PostgREST endpoint).
The endpoint returns JSON and supports limit/offset pagination, so we fetch in
chunks to avoid holding the whole response in a single request.
"""

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request

URL = "https://fauna.jbrj.gov.br/rest/mv_planilha_extendida"
PAGE_SIZE = 5000
MAX_RETRIES = 4
TIMEOUT = 120


def fetch_page(offset, limit):
    """Fetch one page of rows starting at offset."""
    url = f"{URL}?limit={limit}&offset={offset}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            print(f"  retry {attempt} (offset {offset}): {exc} -> wait {wait}s",
                  file=sys.stderr)
            time.sleep(wait)


def download_all(page_size):
    """Yield every row, paginating until an empty page is returned."""
    offset = 0
    while True:
        rows = fetch_page(offset, page_size)
        if not rows:
            break
        print(f"  fetched {len(rows)} rows (offset {offset})", file=sys.stderr)
        yield from rows
        if len(rows) < page_size:
            break
        offset += page_size


def main():
    parser = argparse.ArgumentParser(description="Download fauna.jbrj.gov.br dataset")
    parser.add_argument("-o", "--output", default="mv_planilha_extendida",
                        help="Output basename (no extension). Default: %(default)s")
    parser.add_argument("-f", "--format", choices=["json", "csv", "both"],
                        default="csv", help="Output format. Default: %(default)s")
    parser.add_argument("-p", "--page-size", type=int, default=PAGE_SIZE,
                        help="Rows per request. Default: %(default)s")
    args = parser.parse_args()

    print("Downloading...", file=sys.stderr)
    records = list(download_all(args.page_size))
    print(f"Total rows: {len(records)}", file=sys.stderr)

    if not records:
        print("No data returned.", file=sys.stderr)
        sys.exit(1)

    if args.format in ("json", "both"):
        path = f"{args.output}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)
        print(f"Wrote {path}", file=sys.stderr)

    if args.format in ("csv", "both"):
        path = f"{args.output}.csv"
        # Union of keys across all rows preserves any field that appears late.
        fields = list(dict.fromkeys(k for r in records for k in r))
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
        print(f"Wrote {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
