# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Porcentômetro is a single-file Flask web app for the CTFB (Catálogo Taxonômico da Fauna do Brasil).
Researchers log in, request a taxon, and the app runs one of several analyses over the full fauna
dataset and returns a ZIP of XLSX tables + PDF charts. It is a faithful Python port of an R script
(`completeness_analysis.R`, not in this repo) for the core "Data Completeness" analysis; behavioural
parity with the R logic is intentional and documented in README.md's "Dependency on the R Script"
section — don't change the completeness formula, fill definition, or ecological exclusion rules
without checking that section first.

Almost all application logic lives in **`app.py`** (~2900 lines, monolithic — no blueprints/packages).
Read the relevant function there rather than assuming a typical Flask project layout.

## Running / developing

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py                       # dev server at http://127.0.0.1:5000, debug=True
```

Production: `gunicorn app:app --worker-class gthread --workers 1 --threads 4 --timeout 600 --graceful-timeout 30` (see `Procfile`).
**Must stay single-worker** — analysis jobs, the in-memory data cache, and the APScheduler daily
refresh all live in one process's memory and are not shared across workers.

There is no test suite, linter, or build step configured in this repo.

Default admin login: `admin` / `adminpass` (seeded on first startup if the `user` table is empty).

### Startup data load

On every app start (`with app.app_context(): load_data_on_startup()` near the bottom of `app.py`),
the app downloads/refreshes several datasets over the network into module-level globals
(`PESQUISADORES_DF`, `PLANILHA_DF`, `INVASIVE_DF`, `IPT_DF`, `TAXON_HIERARCHY`). If network access is
unavailable, it falls back to cached files under `data/` (gitignored) and `DATA_LOADED_SUCCESSFULLY`
stays `False`, causing `/analyze` and friends to refuse requests. An APScheduler job
(`start_scheduler()`) re-runs the same load daily at 03:00 America/Sao_Paulo. When testing locally
without network access, expect empty results and check the startup log for `ERROR loading ...` lines.

## Architecture

### Data sources (all fetched live, cached locally under `data/`)

| Global | Source | Loader |
|---|---|---|
| `PESQUISADORES_DF` | Google Sheet (researcher → taxa assignments) merged with a live JBRJ API pull | `fetch_pesquisadores_api()` + `merge_pesquisadores()` |
| `PLANILHA_DF` | JBRJ Fauna API (`fauna.jbrj.gov.br/rest/mv_planilha_extendida`), paginated | `download_fauna_csv()` |
| `INVASIVE_DF` | Google Drive TSV of invasive species | inline in `load_data_on_startup()` |
| `IPT_DF` | Optional IPT Darwin Core Archive combine, admin-triggered | `process_ipt_archive()` |
| `TAXON_HIERARCHY` | Built in-process from `PLANILHA_DF` (`child_lowercase → parent_lowercase`) | `load_data_on_startup()` |

`COLUMN_MAPPINGS.md` documents English→Portuguese value translations (e.g. `taxonrank`,
`taxonomicstatus`, `establishmentMeans`) applied when normalizing `PLANILHA_DF` after download — update
it (and the corresponding `.replace({...})` calls in `load_data_on_startup()`) if the upstream API adds
new enum values; the startup log prints raw unmapped values for this purpose.

`download_fauna.py` is a standalone CLI for manually dumping the same Fauna API dataset to
JSON/CSV — not imported by `app.py`, just a debugging/offline tool.

### Authorization model

Each researcher has a `taxons` list (from `pesquisadores.xlsx`). A user may analyse a taxon if it's
directly in their list, or a descendant of one via `TAXON_HIERARCHY` (walked in
`is_taxon_authorized()` / `get_user_taxa()` / `current_allowed_taxa()`). All phyla are wired to
`animalia` so an `Animalia`-level researcher can reach everything. Admins bypass this entirely.

### Background job pattern (repeated per analysis type)

Every analysis follows the same shape because results can take minutes for large taxa (e.g.
Hexapoda) and must not trip the gunicorn request timeout:

1. Route handler (e.g. `analyze_taxon`) validates input, creates a `job_id`, stores an entry in a
   module-level dict (`ANALYSIS_JOBS`, `GBIF_JOBS`, `INVASIVE_JOBS`, `AUTHORS_JOBS`, `CONTRIB_JOBS`),
   and spawns a `daemon=True` `threading.Thread` running a `_..._worker(job_id, ...)` function.
2. The worker mutates its job dict entry in place (`status`, `progress`, `pct`, then `result_id` or
   `error`) as it works.
3. `.../status/<job_id>` renders a polling page; `.../poll/<job_id>` is the JSON endpoint it polls;
   `.../download/<job_id>` (or `/result/<id>/download` for the main analysis) streams the finished
   file via `send_file`.

When adding a new long-running analysis, copy this pattern (job dict + worker thread + status/poll/
download routes) rather than inventing a new one. Job/result dicts are in-memory only — they don't
survive a restart and aren't shared across workers, consistent with the single-worker gunicorn config.

### The analysis types

- **Data Completeness** (`/analyze`, `run_python_analysis()`) — the core Porcentômetro analysis
  described in README.md. Computes per-species field completeness across 15 Darwin Core columns with
  ecological exclusions, aggregates by family/order/class/subclass/phylum, and renders both XLSX
  tables and PDF bar charts (`generate_completeness_chart()`).
- **GBIF Gap** (`/gbif_gap`, `_gbif_gap_worker()`) — cross-references taxa against GBIF.
- **Invasive Gap** (`/invasive_gap`, `_invasive_gap_worker()`) — cross-references against `INVASIVE_DF`.
- **Autores de taxa** (`/authors`, `_authors_worker()`) — lists `scientificNameAuthorship` values and
  edit-recency stats for a taxon subtree.
- **Contributors** (`/contrib`, `_contrib_worker()` + `load_contrib_report()`) — lists JBRJ editors who
  touched a taxon subtree; `load_contrib_report()` has retry + PostgREST-fallback logic because the
  underlying CSV export endpoint is unreliable — preserve that resilience if you touch it.

### Internationalization

No i18n framework — every template has a hand-maintained `_en` sibling (e.g. `index.html` /
`index_en.html`). `tmpl(name)` picks the right one based on `session['lang']`, set via
`/lang/<code>` (`pt` or `en`). **When editing any template's content or behavior, update both
language variants together** — they are expected to stay in structural sync.

### Database

Flask-SQLAlchemy with a single `User` model (`app.py`). Defaults to SQLite at `data/users.db`
(persistent volume in production on Railway); set `DATABASE_URL` for Postgres (`postgres://` is
rewritten to `postgresql://` for SQLAlchemy compatibility). Schema changes must go through
`run_db_migrations()` as additive, idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`-style
statements (dialect-specific: separate migration lists for Postgres vs SQLite) — there is no
Alembic/migration framework, so never assume a column exists without adding a migration for it.
`users_backup.csv` is seeded into the `user` table on startup for any username not already present.

### Config / environment variables

`DATABASE_URL`, `SECRET_KEY` (falls back to a fixed dev key — **must** be set in production or
sessions reset on every deploy), `ENABLE_SCHEDULER` (default on), `IPT_COMBINED_SHEET_URL`. Sheet/API
source URLs (`PESQUISADORES_SHEET_URL`, `PLANILHA_EXTENDIDA_SHEET_URL`, `INVASIVE_LIST_URL`,
`IPT_SOURCE_URL`) are hardcoded near the top of `app.py`, not env-driven.

### Output lifecycle

Analysis outputs are written under `temp_analysis_output/` and zipped into `temp_zips/` (both
gitignored, auto-created/cleaned per request) and served via `send_file`; results are kept in the
`ANALYSIS_RESULTS` / equivalent in-memory dicts keyed by a `result_id` UUID, not persisted to disk
long-term or to the database.

## Other files

- `generate_manuals.py` — standalone ReportLab script that regenerates `manual_en.pdf` /
  `manual_pt.pdf` (served at `/manual`). Run manually (`python generate_manuals.py`) after changing
  app behavior that the manual documents; it is not run automatically.
- `COLUMN_MAPPINGS.md` — source of truth for upstream-API value translations; see above.
- `README.md` — user/deployment-facing documentation, including the full completeness formula and
  the R-script parity table. Treat it as authoritative for the *rules*, and this file as authoritative
  for *where things live in the code*.
