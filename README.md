# Porcentômetro — Taxon Completeness Analysis App

Web application for calculating and reporting data completeness of taxonomic records in the CTFB (Catálogo Taxonômico da Fauna do Brasil) Darwin Core Archive. Built in Python/Flask, it replicates the logic of the reference R script (`completeness_analysis.R`) and adds role-based access control and on-demand reporting via a browser interface.

---

## Table of Contents

1. [Overview](#overview)
2. [How It Works](#how-it-works)
3. [Completeness Rules (Porcentômetro)](#completeness-rules-porcentômetro)
4. [Outputs](#outputs)
5. [Installation](#installation)
6. [Running Locally](#running-locally)
7. [Deployment (Render / Railway)](#deployment-render--railway)
8. [User Management](#user-management)
9. [Data Sources](#data-sources)
10. [Project Structure](#project-structure)
11. [Dependency on the R Script](#dependency-on-the-r-script)
12. [Known Limitations](#known-limitations)

---

## Overview

Researchers responsible for specific taxonomic groups log in and request an analysis for their taxon (e.g., a phylum, class, order, or family). The app:

- Filters the main dataset to the requested taxon and all its subordinate groups.
- Calculates per-species data completeness following the official Porcentômetro rules.
- Aggregates results by family, order, class, subclass, and phylum.
- Associates each group with its responsible researcher.
- Delivers a ZIP with six XLSX tables and five PDF charts.

---

## How It Works

### 1. Data Loading (startup)

On startup the app downloads two Google Sheets as XLSX:

| Sheet | Content |
|---|---|
| `pesquisadores.xlsx` | Researcher login names and their assigned taxa (columns: `username`, `taxons`, `institution`) |
| `planilha_extendida.xlsx` | Full CTFB dataset — one row per taxon record, Darwin Core columns |

Both are cached in memory. A taxon hierarchy map is built from the main dataset (`phylum → class → order → family → genus`) and used for hierarchical authorization.

### 2. Authorization

Each user is assigned one or more taxa in `pesquisadores.xlsx`. When a user requests a taxon:

- If the taxon is directly in their allowed list → authorized.
- If the taxon is a **child** of an allowed taxon in the hierarchy → authorized.
- Admins bypass all restrictions.

### 3. Analysis Pipeline

When a taxon is submitted, `run_python_analysis()` executes:

```
1. Filter planilha_extendida for rows where any rank column matches the taxon
2. Keep only taxonrank IN ('ESPECIE', 'SUBESPECIE')
3. Compute per-species completeness (see rules below)
4. Aggregate by family / order / class / subclass / phylum
5. Join researcher names from pesquisadores.xlsx
6. Apply top_first() — move highest mean to top, mark with <<< MAX
7. Export XLSX tables (column order mirrors R script output)
8. Generate PDF charts (horizontal bars + min-max error bars)
9. ZIP everything and return to browser
```

---

## Completeness Rules (Porcentômetro)

Defined in `regras.txt` (Section 3–6) and implemented identically to `completeness_analysis.R`.

### 15 Evaluated Fields

| Column | Darwin Core field |
|---|---|
| `bibliographicreference` | AG |
| `country` | AH |
| `establishmentmeans` | AJ |
| `endemicbrazil` | AK |
| `environment` | AL |
| `locality` | AM |
| `epicontinentaldomain` | AN |
| `marinedomain` | AO |
| `lifeform` | AP |
| `habitat` | AQ |
| `vernacularname` | AR |
| `vernacularnamelanguage` | AS |
| `vernacularnamelocality` | AT |
| `animalhostnames` | AV |
| `vegetalhostnames` | AW |

### Fill Definition

A field is considered **filled** when it is not `NA` and not an empty/whitespace string.

### Ecological Exclusions (per species)

These rules adjust **both numerator and denominator** for each row:

| Condition | Excluded field | Effect |
|---|---|---|
| `environment == "epicontinental"` | `marinedomain` | Removed from applicable count; also removed from filled count if it was filled |
| `lifeform == "herbivoro"` | `animalhostnames` | Same |

This ensures completeness never exceeds 100% and that inapplicable fields do not penalise a species.

### Formula

```
completeness = (filled_count / total_applicable) × 100
```

Where `total_applicable = 15 − (ecological exclusions for that row)`.

---

## Outputs

All files are delivered as a single ZIP named `<taxon>_analysis_results.zip`.

### XLSX Tables (6 files)

Each table is sorted by taxonomic hierarchy and has the row with the highest `mean_complete` moved to the top, marked `<<< MAX` in the `max_flag` column.

| File | Group column | Context columns included |
|---|---|---|
| `completeness_by_family.xlsx` | family | phylum, class, order |
| `completeness_by_order.xlsx` | order | phylum, class |
| `completeness_by_class.xlsx` | class | phylum |
| `completeness_by_subclass.xlsx` | subclass | phylum, class |
| `completeness_by_phylum.xlsx` | phylum | — |
| `completeness_per_species.xlsx` | species | phylum, class, subclass, order, family |

**Columns in aggregated tables:**
`phylum · class · order · [level] · n_species · mean_complete · min_complete · max_complete · amplitude · pesquisador · max_flag`

**`pesquisador` fallback logic** (for each level):

```
family table  → looks up: family → order → class → phylum
order table   → looks up: order → class → phylum
class table   → looks up: class → phylum
subclass table→ looks up: subclass → class → phylum
phylum table  → looks up: phylum
species table → looks up: family → order → subclass → class → phylum
```

When resolved via a parent rank, the value is annotated (e.g., `"Joana Silva (via class)"`).

### PDF Charts (5 files)

One chart per taxonomic level. Each PDF contains a single horizontal bar chart showing:

- **Bar length** = mean completeness (%)
- **Error bars** = min to max range
- **Bar colour** = blue (default) / red (highest mean in the group)
- **Label** = mean % printed next to each bar
- **Y-axis** = group names, sorted by taxonomic hierarchy

| File | Level |
|---|---|
| `completeness_histograms_phylum.pdf` | Phylum |
| `completeness_histograms_class.pdf` | Class |
| `completeness_histograms_subclass.pdf` | Subclass |
| `completeness_histograms_order.pdf` | Order |
| `completeness_histograms_family.pdf` | Family |

---

## Installation

**Requirements:** Python 3.11+

```bash
git clone https://github.com/wboeger/completeness.git
cd completeness
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## Running Locally

```bash
source venv/bin/activate
python app.py
```

The app starts at `http://127.0.0.1:5000`.

**Default admin credentials:**
```
username: admin
password: adminpass
```

> Change the admin password immediately after first login by editing the database or creating a new admin user via the admin panel.

> On startup the app downloads the two Google Sheets. Ensure internet access is available or the app will start with no data and all analyses will fail.

---

## Deployment (Render / Railway)

The app is production-ready with Gunicorn and supports PostgreSQL via the `DATABASE_URL` environment variable.

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | SQLite (`instance/users.db`) |
| `SECRET_KEY` | Flask session secret | Random 24-byte key (regenerated on restart — use a fixed value in production) |

### Gunicorn start command

```
gunicorn app:app
```

> **Note:** the random `secret_key` in `app.py` means all sessions are invalidated on every restart. For production, set a stable `SECRET_KEY` environment variable:
> ```python
> app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
> ```

---

## User Management

Access the admin panel at `/admin` (admin login required).

### Add a user

1. Go to `/admin` → **Add User**.
2. Enter username, password, and optionally check **Admin**.
3. Open `pesquisadores.xlsx` (Google Sheet) and add a row:
   ```
   username | Taxon A; Taxon B, Taxon C | Institution name
   ```
   Taxa can be separated by `;` or `,`. The name in column 1 must exactly match the login username (case-insensitive).

### Authorization logic

A user can analyse any taxon that is:
- Listed directly in their `taxons` column, **or**
- A taxonomic child of a listed taxon (walks up the hierarchy automatically).

Example: a user assigned `Chordata` can analyse any class, order, family, genus, or species within Chordata.

---

## Data Sources

Both sources are Google Sheets published for export. URLs are hardcoded in `app.py` (lines 30–31). To point to different sheets, update those two constants:

```python
PESQUISADORES_SHEET_URL      = "https://docs.google.com/spreadsheets/d/<id>/export?format=xlsx"
PLANILHA_EXTENDIDA_SHEET_URL = "https://docs.google.com/spreadsheets/d/<id>/export?format=xlsx"
```

The sheets must be publicly accessible (Share → Anyone with the link → Viewer).

**Column name handling:** all column names in `planilha_extendida` are lowercased and stripped on load. The sheet does not need to use lowercase headers.

---

## Project Structure

```
completeness/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── runtime.txt             # Python version (3.11)
├── static/
│   └── style.css
├── templates/
│   ├── index.html          # Main dashboard
│   ├── login.html
│   ├── admin.html
│   └── add_user.html
├── data/                   # Local fallback data (not used in production)
│   ├── planilha_extendida.xlsx
│   ├── pesquisadores.xlsx
│   └── authors.xlsx
└── instance/
    └── users.db            # SQLite user database (auto-created)
```

Temporary analysis output is written to `temp_analysis_output/` and `temp_zips/` (auto-created, auto-deleted after each request).

---

## Dependency on the R Script

This app is a faithful Python port of `controle/Porcentometro/completeness_analysis.R`. The following behaviours are intentionally identical:

| Behaviour | R source | Python implementation |
|---|---|---|
| 15 MANUAL_COLS | Section 3 | `MANUAL_COLS` list in `run_python_analysis()` |
| Fill definition | Section 4 | `is_filled()` |
| Ecological exclusions (numerator + denominator) | Section 5 | `filled_count` adjustment block |
| Completeness formula | Section 6 | `completeness = filled_count / total_applicable * 100` |
| Species filter | Section 1 | `taxonrank isin ['ESPECIE', 'SUBESPECIE']` |
| Context columns per level | `by_family`, `by_order`, … | `HIERARCHY_CONTEXT` dict |
| Researcher fallback with `(via X)` label | Step 6 | `find_researcher()` |
| Max row first + `<<< MAX` flag | `top_first()` | `top_first()` |
| Taxonomic sort order | `arrange(phylum, class, …)` | `sort_values(context_cols + [level])` |

The main intentional differences are:
- Output format is **XLSX** (vs CSV in R).
- PDFs are one file per level (vs one file per phylum per level in R).
- The app analyses a **subset** of the full dataset filtered to the requested taxon; the R script processes the entire dataset.

---

## Known Limitations

- `SECRET_KEY` is regenerated on every restart — sessions are lost. Fix by setting a stable environment variable.
- Google Sheets download at startup has a 30-second timeout. If the sheets are unavailable, the app starts with no data.
- Very large taxa (e.g., full Animalia) may take significant time and memory to analyse.
- The `pesquisador` column in outputs shows the login **username**, not necessarily the researcher's full name (they are the same if the first column of `pesquisadores.xlsx` contains the full name).
