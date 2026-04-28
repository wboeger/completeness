from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import time
import threading
import uuid
import pandas as pd
import subprocess
import json
import zipfile
import shutil
import datetime
import requests
from io import BytesIO
import numpy as np
import matplotlib
matplotlib.use('Agg') # Use the Agg backend for non-interactive plotting
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

app = Flask(__name__)
# SECRET_KEY must be stable across deployments so sessions survive restarts.
# Set the SECRET_KEY environment variable in Railway; falls back to a fixed
# dev key locally (not secure for production).
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# --- Configuration ---
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///users.db')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

PESQUISADORES_SHEET_URL = "https://docs.google.com/spreadsheets/d/1adWD1sksMqWhAaLmKC61mV8a3ZeuT-ou/export?format=xlsx"
PLANILHA_EXTENDIDA_SHEET_URL = "https://docs.google.com/spreadsheets/d/1zG0Ax_wKgg6UB9PgVXg29_qoZKDCE1Db/export?format=xlsx"
# --- End Configuration ---

# --- Database Model ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)   # NULL = must set password on first login
    is_admin = db.Column(db.Boolean, default=False)
    must_set_password = db.Column(db.Boolean, default=False)   # True for bulk-imported users
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.must_set_password = False

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

# --- Data Loading and Caching ---
TAXON_HIERARCHY = {}
PESQUISADORES_DF = None
PLANILHA_DF = None
DATA_LOADED_SUCCESSFULLY = False

def download_gsheet(url):
    try:
        response = requests.get(url, timeout=30) # Add a timeout
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"FATAL: Could not download Google Sheet from {url}. Error: {e}")
        return None

LOCAL_PESQUISADORES = os.path.join(os.path.dirname(__file__), 'data', 'pesquisadores.xlsx')
LOCAL_PLANILHA      = os.path.join(os.path.dirname(__file__), 'data', 'planilha_extendida.xlsx')

def load_data_on_startup():
    global TAXON_HIERARCHY, PESQUISADORES_DF, PLANILHA_DF, DATA_LOADED_SUCCESSFULLY

    # --- pesquisadores ---
    try:
        content = download_gsheet(PESQUISADORES_SHEET_URL)
        if content:
            PESQUISADORES_DF = pd.read_excel(BytesIO(content), header=0)
            print("Loaded pesquisadores from Google Sheet.")
        elif os.path.exists(LOCAL_PESQUISADORES):
            PESQUISADORES_DF = pd.read_excel(LOCAL_PESQUISADORES, header=0)
            print("Loaded pesquisadores from local file (Google Sheet unavailable).")
        if PESQUISADORES_DF is not None:
            PESQUISADORES_DF.columns = [c.lower().strip() for c in PESQUISADORES_DF.columns]
            print(f"  {len(PESQUISADORES_DF)} researchers loaded.")
    except Exception as e:
        print(f"ERROR loading pesquisadores: {e}")

    # --- planilha extendida ---
    try:
        content = download_gsheet(PLANILHA_EXTENDIDA_SHEET_URL)
        if content:
            PLANILHA_DF = pd.read_excel(BytesIO(content))
            print("Loaded planilha from Google Sheet.")
        elif os.path.exists(LOCAL_PLANILHA):
            PLANILHA_DF = pd.read_excel(LOCAL_PLANILHA)
            print("Loaded planilha from local file (Google Sheet unavailable).")
        if PLANILHA_DF is not None:
            PLANILHA_DF.columns = [col.lower().strip() for col in PLANILHA_DF.columns]
            print(f"  {len(PLANILHA_DF)} records loaded.")
    except Exception as e:
        print(f"ERROR loading planilha: {e}")

    # --- build taxon hierarchy ---
    if PLANILHA_DF is not None:
        try:
            taxonomic_ranks = ['phylum', 'class', 'order', 'family', 'genus', 'scientificname']
            valid_ranks = [r for r in taxonomic_ranks if r in PLANILHA_DF.columns]
            for i in range(len(valid_ranks) - 1):
                parent_rank = valid_ranks[i]
                child_rank  = valid_ranks[i + 1]
                pairs = PLANILHA_DF[[child_rank, parent_rank]].dropna()
                for child, parent in zip(pairs[child_rank].str.strip().str.lower(),
                                         pairs[parent_rank].str.strip().str.lower()):
                    if child and parent and child != 'nan' and parent != 'nan':
                        if child not in TAXON_HIERARCHY:
                            TAXON_HIERARCHY[child] = parent
            # Connect all phyla to 'animalia' so users responsible for
            # Animalia get access to every taxon in the catalogue
            if 'phylum' in PLANILHA_DF.columns:
                for phylum in PLANILHA_DF['phylum'].dropna().str.strip().str.lower().unique():
                    if phylum and phylum != 'nan' and phylum not in TAXON_HIERARCHY:
                        TAXON_HIERARCHY[phylum] = 'animalia'
            print(f"Built taxon hierarchy with {len(TAXON_HIERARCHY)} relationships.")
        except Exception as e:
            print(f"ERROR building taxon hierarchy: {e}")

    if PESQUISADORES_DF is not None and PLANILHA_DF is not None:
        DATA_LOADED_SUCCESSFULLY = True
        print("Data loading successful.")
    else:
        print("Data loading FAILED — check Google Sheet URLs and local fallback files.")

def run_db_migrations():
    """Add new columns to existing tables without dropping data.
    Each statement runs in its own connection+transaction so one failure
    does not roll back the others."""
    from sqlalchemy import text
    is_pg = 'postgresql' in str(db.engine.url)

    migrations = []
    if is_pg:
        migrations = [
            'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS must_set_password BOOLEAN DEFAULT FALSE',
            'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS created_at TIMESTAMP',
            # Make password_hash nullable (idempotent — no-op if already nullable)
            'ALTER TABLE "user" ALTER COLUMN password_hash DROP NOT NULL',
        ]
    else:
        migrations = [
            'ALTER TABLE "user" ADD COLUMN must_set_password BOOLEAN DEFAULT 0',
            'ALTER TABLE "user" ADD COLUMN created_at DATETIME',
        ]

    for stmt in migrations:
        try:
            with db.engine.connect() as conn:
                conn.execute(text(stmt))
                conn.commit()
        except Exception as _e:
            # Column already exists or other benign error — log and continue
            print(f"  Migration skipped ({_e})")

import re as _re

def _load_session_taxa(user):
    """Populate session['allowed_taxa'] from pesquisadores sheet for the given user."""
    if PESQUISADORES_DF is not None and 'login' in PESQUISADORES_DF.columns:
        row = PESQUISADORES_DF[PESQUISADORES_DF['login'].str.lower() == user.username.lower()]
        if not row.empty:
            taxa_str = row.iloc[0]['táxons']
            if isinstance(taxa_str, str):
                session['allowed_taxa'] = sorted(
                    t.strip().lower() for t in _re.split(r'[;,]', taxa_str) if t.strip()
                )
                return
    session['allowed_taxa'] = []

# ── GBIF gap analysis ──────────────────────────────────────────────────────────
GBIF_JOBS = {}   # job_id → dict with status/progress/result

def _gbif_gap_worker(job_id, taxon_name, planilha_df):
    def update(progress, pct=None):
        GBIF_JOBS[job_id]['progress'] = progress
        if pct is not None:
            GBIF_JOBS[job_id]['pct'] = pct

    try:
        GBIF_JOBS[job_id] = {'status': 'running', 'progress': 'Iniciando…', 'pct': 0,
                              'result_path': None, 'error': None}

        # ── Phase 1: resolve taxon name → GBIF usageKey ──
        update('Buscando táxon no GBIF…', 2)
        r = requests.get('https://api.gbif.org/v1/species/match',
                         params={'name': taxon_name, 'verbose': 'false'}, timeout=30)
        r.raise_for_status()
        match = r.json()
        taxon_key = match.get('usageKey')
        if not taxon_key:
            GBIF_JOBS[job_id].update(status='error',
                error=f'Táxon "{taxon_name}" não encontrado no GBIF (sem usageKey).')
            return
        gbif_rank = match.get('rank', '')
        update(f'Táxon encontrado: {match.get("canonicalName", taxon_name)} ({gbif_rank}, key={taxon_key})', 5)

        # ── Phase 2: collect speciesKey values via occurrence facets ──
        # basisOfRecord filter excludes FOSSIL_SPECIMEN at source so that species
        # with only fossil occurrences in Brazil never enter the key list.
        update('Coletando chaves de espécies via GBIF Occurrence Search (Brasil)…', 8)
        FACET_LIMIT = 50000
        NON_FOSSIL_BASIS = [
            'HUMAN_OBSERVATION', 'PRESERVED_SPECIMEN', 'LIVING_SPECIMEN',
            'MACHINE_OBSERVATION', 'MATERIAL_SAMPLE', 'OBSERVATION',
            'LITERATURE', 'OCCURRENCE',
        ]
        species_keys = []
        offset = 0
        while True:
            # Build params as list of tuples so multiple basisOfRecord values
            # are sent as repeated query parameters (requests requirement).
            params = [
                ('country',     'BR'),
                ('taxonKey',    taxon_key),
                ('facet',       'speciesKey'),
                ('facetLimit',  FACET_LIMIT),
                ('facetOffset', offset),
                ('limit',       0),
            ] + [('basisOfRecord', b) for b in NON_FOSSIL_BASIS]
            r = requests.get(
                'https://api.gbif.org/v1/occurrence/search',
                params=params, timeout=60
            )
            r.raise_for_status()
            data = r.json()
            facets = data.get('facets', [])
            if not facets or not facets[0].get('counts'):
                break
            counts = facets[0]['counts']
            species_keys.extend(int(c['name']) for c in counts)
            if len(counts) < FACET_LIMIT:
                break
            offset += FACET_LIMIT
            time.sleep(0.3)

        n_keys = len(species_keys)
        update(f'{n_keys} chaves de espécies encontradas no GBIF. Resolvendo nomes…', 15)

        # ── Phase 3: resolve each speciesKey → canonical name (parallelised) ──
        resolved = [None] * n_keys
        lock = threading.Lock()
        counter = [0]

        def resolve_one(idx, key):
            try:
                rr = requests.get(f'https://api.gbif.org/v1/species/{key}', timeout=30)
                if rr.ok:
                    sp = rr.json()
                    # Skip fossil / extinct taxa (do not return early — counter must increment below)
                    if sp.get('extinct') is not True:
                        name = sp.get('canonicalName', '')
                        if name and len(name.split()) >= 2:
                            resolved[idx] = {
                                'species_key':   key,
                                'canonical_name': name,
                                'gbif_family':   sp.get('family', ''),
                                'gbif_order':    sp.get('order', ''),
                                'gbif_class':    sp.get('class', ''),
                                'gbif_phylum':   sp.get('phylum', ''),
                            }
            except Exception:
                pass
            with lock:
                counter[0] += 1
                done = counter[0]
            if done % 200 == 0 or done == n_keys:
                pct = 15 + int(done / max(n_keys, 1) * 70)
                update(f'Resolvendo nomes: {done}/{n_keys}…', pct)

        # Use up to 20 parallel threads (GBIF allows ~20 req/s)
        MAX_WORKERS = 20
        threads = []
        for idx, key in enumerate(species_keys):
            t = threading.Thread(target=resolve_one, args=(idx, key), daemon=True)
            threads.append(t)
            t.start()
            if len(threads) >= MAX_WORKERS:
                threads[0].join()
                threads.pop(0)
        for t in threads:
            t.join()

        gbif_df = pd.DataFrame([r for r in resolved if r is not None])
        if gbif_df.empty:
            GBIF_JOBS[job_id].update(status='error',
                error='Nenhuma espécie válida retornada pelo GBIF.')
            return

        # ── Phase 4: compare with CTFB (accepted names + synonyms) ──
        update('Comparando com CTFB…', 88)
        df = planilha_df.copy()
        has_status = 'taxonomicstatus' in df.columns
        sp_mask = df['taxonrank'].str.upper().str.strip() == 'ESPECIE'
        has_binomial = df.get('genus', pd.Series(dtype=str)).notna() & \
                       df.get('specificepithet', pd.Series(dtype=str)).notna()

        def make_binomials(mask):
            sub = df[mask & has_binomial]
            return set(
                (sub['genus'].str.strip() + ' ' + sub['specificepithet'].str.strip())
                .str.lower()
            )

        # Accepted names
        if has_status:
            ctfb_accepted = make_binomials(
                sp_mask & (df['taxonomicstatus'].str.upper().str.strip() == 'NOME_ACEITO'))
        else:
            ctfb_accepted = make_binomials(sp_mask)

        # Synonyms: any other status (SINONIMO, NOME_DUVIDOSO, etc.)
        if has_status:
            ctfb_synonyms = make_binomials(
                sp_mask & (df['taxonomicstatus'].str.upper().str.strip() != 'NOME_ACEITO')
            ) - ctfb_accepted
        else:
            ctfb_synonyms = set()

        gbif_df['gbif_binomial'] = gbif_df['canonical_name'].str.lower().str.strip()

        in_ctfb     = gbif_df[gbif_df['gbif_binomial'].isin(ctfb_accepted)].copy()
        as_synonym  = gbif_df[
            ~gbif_df['gbif_binomial'].isin(ctfb_accepted) &
             gbif_df['gbif_binomial'].isin(ctfb_synonyms)
        ].copy()
        not_in_ctfb = gbif_df[
            ~gbif_df['gbif_binomial'].isin(ctfb_accepted) &
            ~gbif_df['gbif_binomial'].isin(ctfb_synonyms)
        ].copy()

        sort_cols = ['gbif_phylum', 'gbif_class', 'gbif_order', 'gbif_family', 'canonical_name']
        not_in_ctfb = not_in_ctfb.sort_values(sort_cols)
        as_synonym  = as_synonym.sort_values(sort_cols)

        # Summary by family (only truly absent species)
        summary = (not_in_ctfb
                   .groupby(['gbif_phylum', 'gbif_class', 'gbif_order', 'gbif_family'])
                   .agg(ausentes_ctfb=('canonical_name', 'count'))
                   .reset_index())
        gbif_fam = (gbif_df.groupby('gbif_family')
                            .agg(total_gbif=('canonical_name', 'count'))
                            .reset_index())
        syn_fam  = (as_synonym.groupby('gbif_family')
                               .agg(sinonimos_ctfb=('canonical_name', 'count'))
                               .reset_index())
        summary = (summary
                   .merge(gbif_fam, on='gbif_family', how='left')
                   .merge(syn_fam,  on='gbif_family', how='left'))
        summary['sinonimos_ctfb'] = summary['sinonimos_ctfb'].fillna(0).astype(int)
        summary['pct_ausente'] = (summary['ausentes_ctfb'] / summary['total_gbif'] * 100).round(1)
        summary = summary.sort_values('ausentes_ctfb', ascending=False)

        _rename = {
            'gbif_phylum': 'phylum_gbif', 'gbif_class': 'classe_gbif',
            'gbif_order': 'ordem_gbif',   'gbif_family': 'familia_gbif',
            'canonical_name': 'nome_cientifico', 'species_key': 'gbif_species_key',
        }
        _export_cols = ['gbif_phylum', 'gbif_class', 'gbif_order', 'gbif_family',
                        'canonical_name', 'species_key']

        # ── Save XLSX ──
        update('Gerando arquivo XLSX…', 95)
        result_path = os.path.join('/tmp', f'gbif_gap_{job_id}.xlsx')
        with pd.ExcelWriter(result_path, engine='openpyxl') as writer:
            not_in_ctfb[_export_cols].rename(columns=_rename).to_excel(
                writer, sheet_name='Ausentes_no_CTFB', index=False)

            as_synonym[_export_cols].rename(columns=_rename).to_excel(
                writer, sheet_name='Sinonimos_no_CTFB', index=False)

            summary.rename(columns={
                'gbif_phylum': 'phylum', 'gbif_class': 'classe',
                'gbif_order': 'ordem',  'gbif_family': 'familia',
            }).to_excel(writer, sheet_name='Resumo_por_Familia', index=False)

            in_ctfb[_export_cols].rename(columns=_rename).to_excel(
                writer, sheet_name='Presentes_no_CTFB', index=False)

        GBIF_JOBS[job_id].update(
            status='done', pct=100,
            progress='Concluído.',
            result_path=result_path,
            taxon_name=taxon_name,
            n_gbif=len(gbif_df),
            n_missing=len(not_in_ctfb),
            n_synonym=len(as_synonym),
            n_present=len(in_ctfb),
            n_ctfb=len(ctfb_accepted),
        )

    except Exception as e:
        GBIF_JOBS[job_id].update(status='error', error=str(e))

def generate_completeness_chart(dataframe, category_column, title_label, sort_cols, output_path):
    """
    Horizontal bar chart with min-max error bars and max bar highlighted,
    matching R's plot_completeness() output.
    """
    if dataframe.empty:
        return

    plot_data = dataframe.copy()
    valid_sort = [c for c in sort_cols if c in plot_data.columns]
    plot_data = plot_data.sort_values(valid_sort) if valid_sort else plot_data.sort_values('mean_complete')

    max_val = plot_data['mean_complete'].max()
    colors = ['firebrick' if v == max_val else 'steelblue' for v in plot_data['mean_complete']]
    n = len(plot_data)
    height = max(4, n * 0.4 + 2)

    fig, ax = plt.subplots(figsize=(10, height))
    y_pos = list(range(n))

    ax.barh(y_pos, plot_data['mean_complete'].values, color=colors, alpha=0.8, height=0.7)

    for i, (_, row) in enumerate(plot_data.iterrows()):
        lo = max(0.0, row['mean_complete'] - row['min_complete'])
        hi = max(0.0, row['max_complete'] - row['mean_complete'])
        ax.errorbar(row['mean_complete'], i, xerr=[[lo], [hi]],
                    fmt='none', color='dimgray', capsize=3, linewidth=0.6)
        ax.text(min(row['max_complete'] + 1.0, 119), i,
                f"{row['mean_complete']:.1f}%", va='center', ha='left', fontsize=7, color='dimgray')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(plot_data[category_column].astype(str).tolist(), fontsize=7)
    ax.set_xlim(0, 120)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xlabel('Completude (%)')
    fig.suptitle(f'Completude de Dados por {title_label}', fontweight='bold', fontsize=12)
    ax.set_title('Média (barra) com amplitude min-max (barras de erro)', fontsize=9, color='gray')
    ax.grid(axis='x', alpha=0.3, linewidth=0.5)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()

    with PdfPages(output_path) as pdf:
        pdf.savefig(fig)
    plt.close(fig)

def run_python_analysis(taxon_filter, pesquisadores_df, planilha_df):
    try:
        # Full taxonomic rank hierarchy (coarser → finer)
        RANK_HIERARCHY = [
            'phylum', 'superclass', 'class', 'subclass', 'infraclass',
            'superorder', 'order', 'suborder', 'infraorder',
            'superfamily', 'family', 'subfamily', 'tribe', 'subtribe',
            'genus', 'subgenus',
        ]

        # --- Filter rows matching the requested taxon across all rank columns ---
        mask = pd.Series(False, index=planilha_df.index)
        for rank in RANK_HIERARCHY:
            if rank in planilha_df.columns:
                mask |= (planilha_df[rank].str.lower() == taxon_filter.lower())
        filtered_data = planilha_df[mask].copy()
        if filtered_data.empty:
            return None

        # Determine which rank the input taxon belongs to
        taxon_rank_col = None
        for col in RANK_HIERARCHY:
            if col in filtered_data.columns:
                if (filtered_data[col].str.lower() == taxon_filter.lower()).any():
                    taxon_rank_col = col
                    break
        taxon_rank_idx = RANK_HIERARCHY.index(taxon_rank_col) if taxon_rank_col else -1

        def is_below_input_rank(level):
            """True only if level is strictly finer than the input taxon's rank."""
            if taxon_rank_idx < 0 or level not in RANK_HIERARCHY:
                return True
            return RANK_HIERARCHY.index(level) > taxon_rank_idx

        rank_mask   = filtered_data['taxonrank'].isin(['ESPECIE', 'SUBESPECIE'])
        status_mask = filtered_data['taxonomicstatus'].str.upper().str.strip() == 'NOME_ACEITO' \
                      if 'taxonomicstatus' in filtered_data.columns \
                      else pd.Series(True, index=filtered_data.index)
        accepted = filtered_data[rank_mask & status_mask].copy()
        if accepted.empty:
            return None

        # If a species has accepted subspecies, drop the species-level row and
        # use only its subspecies as the units of analysis.
        if 'genus' in accepted.columns and 'specificepithet' in accepted.columns:
            accepted['_binomial'] = (
                accepted['genus'].fillna('').str.strip() + ' ' +
                accepted['specificepithet'].fillna('').str.strip()
            ).str.lower()
            subsp_binomials = set(
                accepted.loc[accepted['taxonrank'] == 'SUBESPECIE', '_binomial']
            )
            # Keep row if it is a subspecies OR if its binomial has no subspecies
            species_data = accepted[
                (accepted['taxonrank'] == 'SUBESPECIE') |
                (~accepted['_binomial'].isin(subsp_binomials))
            ].copy()
            species_data.drop(columns=['_binomial'], inplace=True)
        else:
            species_data = accepted.copy()

        if species_data.empty:
            return None

        # Deduplicate by canonical epithet key:
        # 1. Rows with the same epithet key AND the same namepublishedinyear are merged
        #    column-by-column; distinct non-empty values are joined with '|'.
        # 2. Among rows with the same epithet key but different years, keep only the
        #    oldest namepublishedinyear (NaN years are treated as last).
        # Key = genus + subgenus + specificepithet + infraspecificepithet (non-empty parts).
        _epi_cols = [c for c in ['genus', 'subgenus', 'specificepithet', 'infraspecificepithet']
                     if c in species_data.columns]
        if _epi_cols and 'namepublishedinyear' in species_data.columns:
            species_data['_epi_key'] = species_data[_epi_cols].fillna('').apply(
                lambda r: ' '.join(p for p in r if str(p).strip()), axis=1
            ).str.lower().str.strip()
            species_data['_year_sort'] = pd.to_numeric(
                species_data['namepublishedinyear'], errors='coerce'
            )

            def _join_unique(vals_iter):
                """Join distinct non-empty string values with '|'."""
                unique_vals = list(dict.fromkeys(
                    v for v in (str(x).strip() for x in vals_iter)
                    if v and v.lower() != 'nan'
                ))
                return '|'.join(unique_vals) if unique_vals else np.nan

            def _merge_group(grp):
                """Merge one group of rows into a single row.
                vernacularname entries are annotated with (language, locality) when present."""
                merged = {}
                # Vernacular name: embed language and locality into each name entry
                vn_present  = 'vernacularname'         in grp.columns
                vl_present  = 'vernacularnamelanguage' in grp.columns
                vloc_present = 'vernacularnamelocality' in grp.columns
                if vn_present:
                    entries = []
                    for _, row in grp.iterrows():
                        name = str(row.get('vernacularname', '') or '').strip()
                        if not name or name.lower() == 'nan':
                            continue
                        lang = (str(row.get('vernacularnamelanguage', '') or '').strip()
                                if vl_present else '')
                        loc  = (str(row.get('vernacularnamelocality',  '') or '').strip()
                                if vloc_present else '')
                        extras = ', '.join(p for p in [lang, loc]
                                          if p and p.lower() != 'nan')
                        entries.append(f'{name} ({extras})' if extras else name)
                    merged['vernacularname'] = (
                        '|'.join(list(dict.fromkeys(entries))) if entries else np.nan
                    )
                # All other columns: join distinct values
                for col in grp.columns:
                    if col == 'vernacularname':
                        continue
                    merged[col] = _join_unique(grp[col])
                return pd.Series(merged)

            # Build a stable group key (NaN year → sentinel string)
            _year_str = species_data['_year_sort'].apply(
                lambda x: str(int(x)) if pd.notna(x) else '__nan__'
            )
            species_data['_group_key'] = species_data['_epi_key'] + '||' + _year_str

            _counts = species_data.groupby('_group_key', sort=False).size()
            _multi  = set(_counts[_counts > 1].index)
            _single_mask = ~species_data['_group_key'].isin(_multi)

            singles  = species_data[_single_mask].copy()
            multiples = species_data[~_single_mask].copy()

            if not multiples.empty:
                merged_rows = (
                    multiples
                    .groupby('_group_key', sort=False)
                    .apply(_merge_group, include_groups=False)
                    .reset_index(level=0, drop=True)
                    .reset_index(drop=True)
                )
                # Restore the group key so we can drop it later
                merged_rows['_group_key'] = (
                    multiples.groupby('_group_key', sort=False)['_group_key'].first().values
                )
                species_data = pd.concat([singles, merged_rows], ignore_index=True)
            else:
                species_data = singles

            species_data.drop(columns=['_group_key'], inplace=True)
            species_data['_year_sort'] = pd.to_numeric(
                species_data['_year_sort'], errors='coerce'
            )
            species_data = (
                species_data
                .sort_values('_year_sort', ascending=True, na_position='last')
                .drop_duplicates(subset='_epi_key', keep='first')
            )
            species_data.drop(columns=['_epi_key', '_year_sort'], inplace=True)

        # Deduplicate: keep only the first row per taxonid
        if 'taxonid' in species_data.columns:
            species_data = species_data.drop_duplicates(subset='taxonid', keep='first')

        # --- 15 manual fields (regras.txt Section 3) ---
        MANUAL_COLS = [
            "bibliographicreference", "country", "establishmentmeans", "endemicbrazil",
            "environment", "locality", "epicontinentaldomain", "marinedomain",
            "lifeform", "habitat", "vernacularname", "vernacularnamelanguage",
            "vernacularnamelocality", "animalhostnames", "vegetalhostnames",
        ]
        manual_present = [col for col in MANUAL_COLS if col in species_data.columns]

        def is_filled(series):
            return series.notna() & (series.astype(str).str.strip() != '')

        filled_matrix = species_data[manual_present].apply(is_filled)

        # --- Ecological exclusion vectors (regras.txt) ---
        env_lower = pd.Series('', index=species_data.index)
        if 'environment' in species_data.columns:
            env_lower = species_data['environment'].fillna('').str.lower().str.strip()

        is_epicontinental = env_lower == "epicontinental"
        is_marine         = env_lower == "marinho"
        is_vazio          = env_lower == "vazio"
        is_null_env       = env_lower == ""

        lifeform_lower = pd.Series('', index=species_data.index)
        if 'lifeform' in species_data.columns:
            lifeform_lower = species_data['lifeform'].fillna('').str.lower().str.strip()

        # Use str.contains to handle compound values like "herbivoro;vida livre individual"
        is_parasite   = lifeform_lower.str.contains(r'endoparasito|ectoparasito', regex=True, na=False)
        is_vida_livre = lifeform_lower.str.contains('vida livre individual', na=False) & ~is_parasite
        is_herbivore  = lifeform_lower.str.contains('herbivoro', na=False) & ~is_parasite & ~is_vida_livre
        is_empty_lf   = lifeform_lower == ''
        # "other" lifeforms: anything not matching above categories → both host cols apply
        is_other_lf   = ~is_parasite & ~is_vida_livre & ~is_herbivore & ~is_empty_lf

        # --- Adjust numerator and denominator ---
        filled_count = filled_matrix.sum(axis=1).copy().astype(float)
        species_data['total_applicable'] = float(len(manual_present))

        # Rule: environment = "vazio" → treat environment as not filled (subtract from numerator)
        if 'environment' in manual_present:
            filled_count -= (is_vazio & filled_matrix['environment']).astype(float)

        # Rule: endemicbrazil = "SIM" → exclude 'country' from denominator
        endemic_sim = pd.Series(False, index=species_data.index)
        if 'endemicbrazil' in species_data.columns:
            endemic_sim = species_data['endemicbrazil'].fillna('').str.strip().str.upper() == 'SIM'
        if 'country' in manual_present:
            filled_count -= (endemic_sim & filled_matrix['country']).astype(float)
            species_data.loc[endemic_sim, 'total_applicable'] -= 1.0

        # Domain rule: always keep exactly ONE domain column per species.
        # epicontinental → exclude marinedomain
        # marinho        → exclude epicontinentaldomain
        # vazio or null  → exclude whichever domain is NOT filled (prefer to keep the filled one)
        epi_in    = 'epicontinentaldomain' in manual_present
        marine_in = 'marinedomain' in manual_present
        if epi_in and marine_in:
            # epicontinental: exclude marinedomain
            filled_count -= (is_epicontinental & filled_matrix['marinedomain']).astype(float)
            species_data.loc[is_epicontinental, 'total_applicable'] -= 1.0
            # marinho: exclude epicontinentaldomain
            filled_count -= (is_marine & filled_matrix['epicontinentaldomain']).astype(float)
            species_data.loc[is_marine, 'total_applicable'] -= 1.0
            # vazio or null env: exclude the domain that is NOT filled; if both or neither, exclude marinedomain
            ambiguous = is_vazio | is_null_env
            epi_filled    = filled_matrix['epicontinentaldomain']
            marine_filled = filled_matrix['marinedomain']
            # keep epicontinentaldomain → exclude marinedomain (when epi filled and marine not, or neither)
            keep_epi = ambiguous & (epi_filled | ~marine_filled)
            # keep marinedomain → exclude epicontinentaldomain (only when marine filled and epi not)
            keep_marine = ambiguous & marine_filled & ~epi_filled
            filled_count -= (keep_epi & marine_filled).astype(float)
            species_data.loc[keep_epi, 'total_applicable'] -= 1.0
            filled_count -= (keep_marine & epi_filled).astype(float)
            species_data.loc[keep_marine, 'total_applicable'] -= 1.0
        elif epi_in and not marine_in:
            # only epicontinentaldomain present: marinho species exclude it
            filled_count -= (is_marine & filled_matrix['epicontinentaldomain']).astype(float)
            species_data.loc[is_marine, 'total_applicable'] -= 1.0
        elif marine_in and not epi_in:
            # only marinedomain present: epicontinental species exclude it
            filled_count -= (is_epicontinental & filled_matrix['marinedomain']).astype(float)
            species_data.loc[is_epicontinental, 'total_applicable'] -= 1.0

        # Host column rules (regras.txt Section 4 — Trophic Rules):
        #   empty lifeform   → exclude both host columns
        #   vida livre       → exclude both host columns
        #   herbivore        → exclude animalhostnames only (vegetalhostnames counts)
        #   parasite         → 1 combined slot (animal OR vegetal)
        #   other lifeforms  → both host columns count normally
        animal_in = 'animalhostnames' in manual_present
        vegetal_in = 'vegetalhostnames' in manual_present
        if animal_in or vegetal_in:
            # Strip both columns from everyone first
            if animal_in:
                filled_count -= filled_matrix['animalhostnames'].astype(float)
            if vegetal_in:
                filled_count -= filled_matrix['vegetalhostnames'].astype(float)
            species_data['total_applicable'] -= float(int(animal_in) + int(vegetal_in))

            # Other lifeforms: add both back
            if animal_in:
                species_data.loc[is_other_lf, 'total_applicable'] += 1.0
                filled_count += is_other_lf.astype(float) * filled_matrix['animalhostnames'].astype(float)
            if vegetal_in:
                species_data.loc[is_other_lf, 'total_applicable'] += 1.0
                filled_count += is_other_lf.astype(float) * filled_matrix['vegetalhostnames'].astype(float)

            # Herbivores: add back vegetalhostnames only
            if vegetal_in:
                species_data.loc[is_herbivore, 'total_applicable'] += 1.0
                filled_count += is_herbivore.astype(float) * filled_matrix['vegetalhostnames'].astype(float)

            # Parasites: 1 combined slot
            if animal_in and vegetal_in:
                host_filled = (filled_matrix['animalhostnames'] | filled_matrix['vegetalhostnames']).astype(float)
            elif animal_in:
                host_filled = filled_matrix['animalhostnames'].astype(float)
            else:
                host_filled = filled_matrix['vegetalhostnames'].astype(float)
            species_data.loc[is_parasite, 'total_applicable'] += 1.0
            filled_count += is_parasite.astype(float) * host_filled

        species_data['filled_count'] = filled_count.values
        species_data['completeness'] = (species_data['filled_count'] / species_data['total_applicable']) * 100

        # --- Aggregation helpers ---
        def most_common_val(x):
            x = x.dropna()
            x = x[x.astype(str).str.strip() != '']
            return x.mode().iloc[0] if not x.empty else np.nan

        # Context (parent) columns per level — mirrors R script exactly
        HIERARCHY_CONTEXT = {
            'genus':    ['phylum', 'class', 'order', 'family'],
            'family':   ['phylum', 'class', 'order'],
            'order':    ['phylum', 'class'],
            'class':    ['phylum'],
            'subclass': ['phylum', 'class'],
            'phylum':   [],
        }

        def aggregate_by(level):
            if level not in species_data.columns:
                return pd.DataFrame()
            context_cols = [c for c in HIERARCHY_CONTEXT.get(level, []) if c in species_data.columns]
            agg_dict = {}
            for col in context_cols:
                agg_dict[col] = (col, most_common_val)
            agg_dict.update({
                'n_spp_ctfb':    ('taxonrank', 'count'),   # species/subspecies units after subspecies rule
                'mean_complete': ('completeness', 'mean'),
                'min_complete':  ('completeness', 'min'),
                'max_complete':  ('completeness', 'max'),
            })
            df = species_data.dropna(subset=[level]).groupby(level).agg(**agg_dict).reset_index()
            df['amplitude'] = df['max_complete'] - df['min_complete']
            df.insert(0, 'taxon_analisado', taxon_filter)
            sort_cols = [c for c in context_cols + [level] if c in df.columns]
            return df.sort_values(sort_cols).round(2)

        # Only aggregate ranks strictly finer than the input taxon's rank
        by_family   = aggregate_by('family')   if is_below_input_rank('family')   else pd.DataFrame()
        by_order    = aggregate_by('order')    if is_below_input_rank('order')    else pd.DataFrame()
        by_class    = aggregate_by('class')    if is_below_input_rank('class')    else pd.DataFrame()
        by_subclass = aggregate_by('subclass') if is_below_input_rank('subclass') else pd.DataFrame()
        by_phylum   = aggregate_by('phylum')   if is_below_input_rank('phylum')   else pd.DataFrame()
        # When the input taxon is a family, also aggregate by genus
        by_genus    = aggregate_by('genus')    if taxon_rank_col == 'family'       else pd.DataFrame()

        # --- Researcher lookup ---
        # pesq_map: Táxons value → nome_completo (full name, not login username)
        pesq_lookup = pesquisadores_df.dropna(subset=['táxons']).copy()
        pesq_lookup['táxons'] = pesq_lookup['táxons'].astype(str).str.split(r'[;,]', regex=True)
        pesq_lookup = pesq_lookup.explode('táxons')
        pesq_lookup['táxons'] = pesq_lookup['táxons'].str.strip()
        pesq_lookup = pesq_lookup[pesq_lookup['táxons'] != '']
        pesq_map = (pesq_lookup.groupby('táxons')['nome_completo']
                               .apply(lambda x: '; '.join(x.dropna().unique()))
                               .to_dict())

        def find_researcher(row, search_ranks):
            """Return nome_completo of the closest researcher going up the hierarchy.
            Tries search_ranks[0] (same level) first, then each superior rank in
            order. Annotates with '(via X)' when resolved above the first rank."""
            for i, rank in enumerate(search_ranks):
                val = row.get(rank, np.nan)
                if pd.notna(val) and str(val).strip() and str(val) in pesq_map:
                    name = pesq_map[str(val)]
                    return name if i == 0 else f"{name} (via {rank})"
            return np.nan

        # Full cascade up the hierarchy — closest responsible researcher wins
        if not by_genus.empty:
            by_genus['pesquisador']    = by_genus.apply(find_researcher,    search_ranks=['genus', 'family', 'order', 'class', 'phylum'], axis=1)
        if not by_family.empty:
            by_family['pesquisador']   = by_family.apply(find_researcher,   search_ranks=['family', 'order', 'class', 'phylum'], axis=1)
        if not by_order.empty:
            by_order['pesquisador']    = by_order.apply(find_researcher,    search_ranks=['order', 'class', 'phylum'], axis=1)
        if not by_class.empty:
            by_class['pesquisador']    = by_class.apply(find_researcher,    search_ranks=['class', 'phylum'], axis=1)
        if not by_subclass.empty:
            by_subclass['pesquisador'] = by_subclass.apply(find_researcher, search_ranks=['subclass', 'class', 'phylum'], axis=1)
        if not by_phylum.empty:
            by_phylum['pesquisador']   = by_phylum['phylum'].map(pesq_map)

        # --- top_first: put max mean_complete row first, mark with <<< MAX ---
        def top_first(df, sort_cols):
            if df.empty:
                return df
            max_idx = df['mean_complete'].idxmax()
            max_row = df.loc[[max_idx]].copy()
            max_row['max_flag'] = '<<< MAX'
            rest = df.drop(max_idx).copy()
            rest['max_flag'] = ''
            valid = [c for c in sort_cols if c in rest.columns]
            return pd.concat([max_row, rest.sort_values(valid) if valid else rest], ignore_index=True)

        # Column ordering aligned with R script output
        COL_ORDER = {
            'genus':    ['taxon_analisado', 'phylum', 'class', 'order', 'family', 'genus', 'n_spp_ctfb', 'mean_complete', 'min_complete', 'max_complete', 'amplitude', 'pesquisador', 'max_flag'],
            'family':   ['taxon_analisado', 'phylum', 'class', 'order', 'family',          'n_spp_ctfb', 'mean_complete', 'min_complete', 'max_complete', 'amplitude', 'pesquisador', 'max_flag'],
            'order':    ['taxon_analisado', 'phylum', 'class', 'order',                    'n_spp_ctfb', 'mean_complete', 'min_complete', 'max_complete', 'amplitude', 'pesquisador', 'max_flag'],
            'class':    ['taxon_analisado', 'phylum', 'class',                             'n_spp_ctfb', 'mean_complete', 'min_complete', 'max_complete', 'amplitude', 'pesquisador', 'max_flag'],
            'subclass': ['taxon_analisado', 'phylum', 'class', 'subclass',                 'n_spp_ctfb', 'mean_complete', 'min_complete', 'max_complete', 'amplitude', 'pesquisador', 'max_flag'],
            'phylum':   ['taxon_analisado', 'phylum',                                      'n_spp_ctfb', 'mean_complete', 'min_complete', 'max_complete', 'amplitude', 'pesquisador', 'max_flag'],
        }

        def reorder(df, level, sort_cols):
            df = top_first(df, sort_cols)
            cols = [c for c in COL_ORDER[level] if c in df.columns]
            return df[cols]

        by_genus_out    = reorder(by_genus,    'genus',    ['family', 'genus'])                    if not by_genus.empty    else pd.DataFrame()
        by_family_out   = reorder(by_family,   'family',   ['phylum', 'class', 'order', 'family']) if not by_family.empty   else pd.DataFrame()
        by_order_out    = reorder(by_order,    'order',    ['phylum', 'class', 'order'])           if not by_order.empty    else pd.DataFrame()
        by_class_out    = reorder(by_class,    'class',    ['phylum', 'class'])                    if not by_class.empty    else pd.DataFrame()
        by_subclass_out = reorder(by_subclass, 'subclass', ['phylum', 'class', 'subclass'])        if not by_subclass.empty else pd.DataFrame()
        by_phylum_out   = reorder(by_phylum,   'phylum',   ['phylum'])                             if not by_phylum.empty   else pd.DataFrame()

        # --- Species export: selected columns + pesquisador with subclass fallback ---
        species_cols = ['taxonid', 'scientificname', 'phylum', 'class', 'subclass', 'order',
                        'family', 'taxonrank', 'completeness', 'filled_count', 'total_applicable']
        species_export = species_data[[c for c in species_cols if c in species_data.columns]].copy()
        species_export.insert(0, 'taxon_analisado', taxon_filter)
        # Species: climb hierarchy from family upward until a responsible researcher is found
        species_export['pesquisador'] = species_export.apply(
            find_researcher, search_ranks=['family', 'order', 'class', 'phylum'], axis=1
        )
        sort_sp = [c for c in ['phylum', 'class', 'subclass', 'order', 'family', 'scientificname']
                   if c in species_export.columns]
        if sort_sp:
            species_export = species_export.sort_values(sort_sp)
        species_export['completeness'] = species_export['completeness'].round(2)

        # --- Write files ---
        temp_dir = os.path.join(app.root_path, 'temp_analysis_output',
                                taxon_filter.replace(" ", "_") + "_" + str(os.getpid()))
        os.makedirs(temp_dir, exist_ok=True)
        generated_files = []

        for fname, df in [
            ("completeness_by_genus.xlsx",    by_genus_out),
            ("completeness_by_family.xlsx",   by_family_out),
            ("completeness_by_order.xlsx",    by_order_out),
            ("completeness_by_class.xlsx",    by_class_out),
            ("completeness_by_subclass.xlsx", by_subclass_out),
            ("completeness_by_phylum.xlsx",   by_phylum_out),
            ("completeness_per_species.xlsx", species_export),
        ]:
            if df.empty:
                continue
            path = os.path.join(temp_dir, fname)
            df.to_excel(path, index=False)
            generated_files.append(path)

        for fname, df, col, label, sort_cols in [
            ("completeness_histograms_genus.pdf",    by_genus,    'genus',    'Gênero',    ['family', 'genus']),
            ("completeness_histograms_family.pdf",   by_family,   'family',   'Família',   ['phylum', 'class', 'order', 'family']),
            ("completeness_histograms_order.pdf",    by_order,    'order',    'Ordem',     ['phylum', 'class', 'order']),
            ("completeness_histograms_class.pdf",    by_class,    'class',    'Classe',    ['phylum', 'class']),
            ("completeness_histograms_subclass.pdf", by_subclass, 'subclass', 'Subclasse', ['phylum', 'class', 'subclass']),
            ("completeness_histograms_phylum.pdf",   by_phylum,   'phylum',   'Filo',      ['phylum']),
        ]:
            if df.empty:
                continue
            path = os.path.join(temp_dir, fname)
            generate_completeness_chart(df, col, label, sort_cols, path)
            if os.path.exists(path):
                generated_files.append(path)

        zip_filename = f"{taxon_filter.replace(' ', '_')}_analysis_results.zip"
        zip_filepath = os.path.join(app.root_path, 'temp_zips', zip_filename)
        os.makedirs(os.path.dirname(zip_filepath), exist_ok=True)
        with zipfile.ZipFile(zip_filepath, 'w') as zf:
            for file_path in generated_files:
                zf.write(file_path, os.path.basename(file_path))

        shutil.rmtree(temp_dir)

        summary = {
            'taxon':        taxon_filter,
            'n_spp_ctfb':   int(len(species_data)),
            'n_species':    int((species_data['taxonrank'] == 'ESPECIE').sum()),
            'n_subsp':      int((species_data['taxonrank'] == 'SUBESPECIE').sum()),
            'mean_complete': round(float(species_data['completeness'].mean()), 1),
            'n_families':   int(species_data['family'].nunique())   if 'family'  in species_data.columns else 0,
            'n_orders':     int(species_data['order'].nunique())    if 'order'   in species_data.columns else 0,
            'n_classes':    int(species_data['class'].nunique())    if 'class'   in species_data.columns else 0,
        }
        return zip_filepath, summary
    except Exception as e:
        print(f"An error occurred during Python analysis: {e}")
        import traceback
        traceback.print_exc()
        return None, None

# --- Flask Routes ---
_USING_POSTGRES = 'postgresql' in DATABASE_URL
ANALYSIS_RESULTS = {}   # result_id → {zip_path, summary}

with app.app_context():
    load_data_on_startup()
    if _USING_POSTGRES:
        print(f"[DB] Connected to PostgreSQL — data will persist across deployments.")
    else:
        print(f"[DB] WARNING: Using SQLite ({DATABASE_URL}) — data WILL be lost on redeploy! "
              "Set DATABASE_URL in Railway environment variables.")
    db.create_all()
    print("[DB] Tables created/verified.")
    run_db_migrations()
    print("[DB] Migrations complete.")
    if User.query.filter_by(username='admin').first() is None:
        admin = User(username='admin', is_admin=True)
        admin.set_password('adminpass')
        db.session.add(admin)
        db.session.commit()
        print("Default admin user 'admin' created.")

    # Seed users from users_backup.csv (only inserts users that don't exist yet)
    _seed_csv = os.path.join(os.path.dirname(__file__), 'users_backup.csv')
    if os.path.exists(_seed_csv):
        import csv as _csv
        _seeded = 0
        with open(_seed_csv, newline='', encoding='utf-8') as _f:
            for _row in _csv.DictReader(_f):
                _uname = (_row.get('username') or '').strip()
                if not _uname:
                    continue
                if User.query.filter_by(username=_uname).first() is None:
                    _u = User(
                        username=_uname,
                        is_admin=str(_row.get('is_admin', '0')).strip() in ('1', 'True', 'true'),
                        must_set_password=str(_row.get('must_set_password', '0')).strip() in ('1', 'True', 'true'),
                        password_hash=_row.get('password_hash') or None,
                    )
                    db.session.add(_u)
                    _seeded += 1
        if _seeded:
            db.session.commit()
            print(f"[DB] Seeded {_seeded} user(s) from users_backup.csv.")

@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    return render_template('index.html', 
                           username=user.username, 
                           is_admin=user.is_admin,
                           data_loaded=DATA_LOADED_SUCCESSFULLY,
                           allowed_taxa_list=session.get('allowed_taxa', []))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user is None:
            flash('Credenciais inválidas.', 'danger')
        elif user.must_set_password or not user.password_hash:
            # First-time login: send to password setup
            session['pending_user_id'] = user.id
            return redirect(url_for('set_password'))
        elif user.check_password(password):
            session['user_id'] = user.id
            _load_session_taxa(user)
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Credenciais inválidas.', 'danger')
    return render_template('login.html')

@app.route('/set_password', methods=['GET', 'POST'])
def set_password():
    if 'pending_user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['pending_user_id'])
    if not user:
        session.pop('pending_user_id', None)
        return redirect(url_for('login'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')
        if len(password) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
        elif password != confirm:
            flash('As senhas não coincidem.', 'danger')
        else:
            user.set_password(password)
            db.session.commit()
            session.pop('pending_user_id', None)
            session['user_id'] = user.id
            _load_session_taxa(user)
            flash('Senha definida com sucesso! Bem-vindo(a).', 'success')
            return redirect(url_for('index'))
    return render_template('set_password.html', username=user.username)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

def is_taxon_authorized(requested_taxon, user_allowed_taxa):
    if not user_allowed_taxa: return False
    current_taxon = requested_taxon.strip().lower()
    if current_taxon in user_allowed_taxa: return True
    while current_taxon in TAXON_HIERARCHY:
        parent_taxon = TAXON_HIERARCHY[current_taxon]
        if parent_taxon in user_allowed_taxa: return True
        if parent_taxon == current_taxon: break
        current_taxon = parent_taxon
    return False

@app.route('/analyze', methods=['POST'])
def analyze_taxon():
    if 'user_id' not in session: return redirect(url_for('login'))
    if not DATA_LOADED_SUCCESSFULLY:
        flash("Error: Application data is not loaded. Please restart the application service.", 'danger')
        return redirect(url_for('index'))

    user = User.query.get(session['user_id'])
    taxon_input = request.form['taxon'].strip()
    if not taxon_input:
        flash("Taxon cannot be empty.", 'warning')
        return redirect(url_for('index'))

    if not user.is_admin and not is_taxon_authorized(taxon_input, session.get('allowed_taxa', [])):
        flash(f"Taxon '{taxon_input}' is not allowed for analysis.", 'danger')
        return redirect(url_for('index'))

    result_zip_path, summary = run_python_analysis(taxon_input, PESQUISADORES_DF, PLANILHA_DF)

    if result_zip_path and summary:
        result_id = uuid.uuid4().hex
        ANALYSIS_RESULTS[result_id] = {'zip_path': result_zip_path, 'summary': summary}
        return redirect(url_for('analysis_result', result_id=result_id))
    else:
        flash(f"Analysis failed for '{taxon_input}'. Check server logs for details.", 'danger')
        return redirect(url_for('index'))

@app.route('/result/<result_id>')
def analysis_result(result_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    entry = ANALYSIS_RESULTS.get(result_id)
    if not entry:
        flash('Resultado não encontrado ou expirado.', 'danger')
        return redirect(url_for('index'))
    user = User.query.get(session['user_id'])
    return render_template('analysis_result.html',
                           summary=entry['summary'],
                           result_id=result_id,
                           username=user.username,
                           is_admin=user.is_admin)

@app.route('/result/<result_id>/download')
def analysis_download(result_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    entry = ANALYSIS_RESULTS.get(result_id)
    if not entry or not os.path.exists(entry['zip_path']):
        flash('Arquivo não disponível.', 'danger')
        return redirect(url_for('index'))
    return send_file(entry['zip_path'], as_attachment=True)

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        flash('Access denied: Administrators only.', 'danger')
        return redirect(url_for('index'))
    users = User.query.all()
    return render_template('admin.html', users=users,
                           username=User.query.get(session['user_id']).username,
                           is_admin=True, using_postgres=_USING_POSTGRES)

@app.route('/admin/upload_data', methods=['POST'])
def upload_data():
    """Admin: upload pesquisadores.xlsx and/or planilha_extendida.xlsx directly."""
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('index'))

    os.makedirs(os.path.join(app.root_path, 'data'), exist_ok=True)
    uploaded = []
    errors   = []

    for field, filename in [('pesquisadores',     'pesquisadores.xlsx'),
                             ('planilha_extendida','planilha_extendida.xlsx')]:
        f = request.files.get(field)
        if f and f.filename:
            dest = os.path.join(app.root_path, 'data', filename)
            try:
                f.save(dest)
                uploaded.append(filename)
            except Exception as e:
                errors.append(f'{filename}: {e}')

    if uploaded:
        load_data_on_startup()
        flash(f'Arquivo(s) carregado(s): {", ".join(uploaded)}. Dados recarregados.', 'success')
    if errors:
        flash(f'Erro ao salvar: {"; ".join(errors)}', 'danger')
    if not uploaded and not errors:
        flash('Nenhum arquivo enviado.', 'info')

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/reload_data', methods=['POST'])
def reload_data():
    """Admin: retry loading data from Google Drive."""
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('index'))
    load_data_on_startup()
    if DATA_LOADED_SUCCESSFULLY:
        flash('Dados recarregados com sucesso.', 'success')
    else:
        flash('Falha ao recarregar — verifique a conectividade com o Google Drive e os arquivos locais.', 'danger')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/export_users')
def export_users():
    """Download a CSV of all users so admins can restore after a SQLite wipe."""
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('index'))
    import csv, io
    users = User.query.all()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['username', 'is_admin', 'must_set_password', 'password_hash', 'created_at'])
    for u in users:
        w.writerow([u.username, int(u.is_admin), int(u.must_set_password or 0),
                    u.password_hash or '', u.created_at or ''])
    out.seek(0)
    from flask import Response
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=users_backup.csv'})

@app.route('/admin/add_user', methods=['GET', 'POST'])
def add_user():
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        flash('Access denied: Administrators only.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash('Username and password are required.', 'danger')
            return redirect(url_for('add_user'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
        else:
            try:
                new_user = User(username=username, is_admin='is_admin' in request.form)
                new_user.set_password(password)
                db.session.add(new_user)
                db.session.commit()
                flash(f"User '{new_user.username}' created successfully!", 'success')
                return redirect(url_for('admin_dashboard'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error creating user: {e}", 'danger')
                print(f"Error creating user: {e}")
    
    current_user = User.query.get(session['user_id'])
    return render_template('add_user.html', username=current_user.username, is_admin=current_user.is_admin)

@app.route('/admin/import_users_csv', methods=['GET', 'POST'])
def import_users_csv():
    """Restore users from a CSV previously exported by /admin/export_users."""
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        import csv, io
        file = request.files.get('csv_file')
        if not file:
            flash('Nenhum arquivo enviado.', 'danger')
            return redirect(url_for('import_users_csv'))
        content = file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))
        created = skipped = errors = 0
        for row in reader:
            username = row.get('username', '').strip()
            if not username:
                continue
            if User.query.filter_by(username=username).first():
                skipped += 1
                continue
            try:
                u = User(
                    username=username,
                    is_admin=bool(int(row.get('is_admin', 0))),
                    must_set_password=bool(int(row.get('must_set_password', 0))),
                    password_hash=row.get('password_hash') or None,
                )
                db.session.add(u)
                db.session.commit()
                created += 1
            except Exception as e:
                db.session.rollback()
                errors += 1
                print(f"CSV import error for {username}: {e}")
        flash(f'Importação CSV: {created} criados, {skipped} já existiam, {errors} erros.', 'info')
        return redirect(url_for('admin_dashboard'))
    current_user = User.query.get(session['user_id'])
    return render_template('import_users_csv.html', username=current_user.username, is_admin=True)

@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    """Admin action: clear a user's password so they must set a new one on next login."""
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('index'))
    target = User.query.get_or_404(user_id)
    if target.username == 'admin' and target.id == session['user_id']:
        flash('Você não pode redefinir sua própria senha por aqui.', 'danger')
        return redirect(url_for('admin_dashboard'))
    target.password_hash = None
    target.must_set_password = True
    db.session.commit()
    flash(f'Senha de "{target.username}" redefinida. O usuário deverá criar uma nova senha no próximo acesso.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/bulk_add_users', methods=['GET', 'POST'])
def bulk_add_users():
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        flash('Acesso negado: somente administradores.', 'danger')
        return redirect(url_for('index'))

    results = []
    if request.method == 'POST':
        logins_text = request.form.get('logins', '')
        logins = [l.strip() for l in logins_text.splitlines() if l.strip()]
        created = skipped = not_found = errors = 0

        for login_name in logins:
            # Already exists?
            if User.query.filter_by(username=login_name).first():
                results.append((login_name, 'warning', 'Já existe — ignorado'))
                skipped += 1
                continue

            # Verify in pesquisadores sheet
            taxa_info = '(sem táxons na planilha)'
            if PESQUISADORES_DF is not None and 'login' in PESQUISADORES_DF.columns:
                row = PESQUISADORES_DF[PESQUISADORES_DF['login'].str.lower() == login_name.lower()]
                if row.empty:
                    results.append((login_name, 'danger', 'Não encontrado em pesquisadores.xlsx — ignorado'))
                    not_found += 1
                    continue
                taxa_val = row.iloc[0].get('táxons', '')
                if isinstance(taxa_val, str) and taxa_val.strip():
                    taxa_info = taxa_val.strip()

            try:
                new_user = User(username=login_name, must_set_password=True, is_admin=False)
                db.session.add(new_user)
                db.session.commit()
                results.append((login_name, 'success', f'Criado — definirá senha no 1º acesso | Táxons: {taxa_info}'))
                created += 1
            except Exception as e:
                db.session.rollback()
                results.append((login_name, 'danger', f'Erro: {e}'))
                errors += 1

        flash(f'Concluído: {created} criados, {skipped} já existiam, {not_found} não encontrados, {errors} erros.', 'info')

    current_user = User.query.get(session['user_id'])
    return render_template('bulk_add_users.html',
                           results=results,
                           username=current_user.username,
                           is_admin=True)

@app.route('/gbif_gap', methods=['GET', 'POST'])
def gbif_gap():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        taxon_name = request.form.get('taxon', '').strip()
        if not taxon_name:
            flash('Informe um táxon.', 'danger')
            return redirect(url_for('gbif_gap'))
        # Authorization: same rule as the main analysis
        allowed = session.get('allowed_taxa', [])
        if not user.is_admin and not is_taxon_authorized(taxon_name, allowed):
            flash(f'Táxon "{taxon_name}" não está autorizado para este usuário.', 'danger')
            return redirect(url_for('gbif_gap'))
        if PLANILHA_DF is None:
            flash('Dados CTFB não carregados — tente novamente mais tarde.', 'danger')
            return redirect(url_for('gbif_gap'))
        job_id = uuid.uuid4().hex
        t = threading.Thread(target=_gbif_gap_worker,
                             args=(job_id, taxon_name, PLANILHA_DF.copy()),
                             daemon=True)
        t.start()
        return redirect(url_for('gbif_gap_status', job_id=job_id))
    return render_template('gbif_gap.html',
                           username=user.username, is_admin=user.is_admin,
                           allowed_taxa=session.get('allowed_taxa', []),
                           data_loaded=DATA_LOADED_SUCCESSFULLY)

@app.route('/gbif_gap/status/<job_id>')
def gbif_gap_status(job_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    job = GBIF_JOBS.get(job_id)
    if job is None:
        flash('Job não encontrado.', 'danger')
        return redirect(url_for('gbif_gap'))
    return render_template('gbif_gap_status.html',
                           job=job, job_id=job_id,
                           username=user.username, is_admin=user.is_admin)

@app.route('/gbif_gap/download/<job_id>')
def gbif_gap_download(job_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    job = GBIF_JOBS.get(job_id)
    if not job or job['status'] != 'done' or not job.get('result_path'):
        flash('Resultado não disponível.', 'danger')
        return redirect(url_for('gbif_gap'))
    taxon_safe = job['taxon_name'].replace(' ', '_').replace('/', '-')
    return send_file(job['result_path'], as_attachment=True,
                     download_name=f'gbif_gap_{taxon_safe}.xlsx')

@app.route('/gbif_gap/poll/<job_id>')
def gbif_gap_poll(job_id):
    """JSON endpoint polled by the status page."""
    from flask import jsonify
    job = GBIF_JOBS.get(job_id, {'status': 'not_found'})
    return jsonify({k: v for k, v in job.items() if k != 'result_path'})

if __name__ == '__main__':
    app.run(debug=True)
