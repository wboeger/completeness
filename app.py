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
# Default to a SQLite file inside the data/ directory. On Railway this folder is a
# mounted persistent volume (/app/data), so the database survives redeploys without
# needing a separate Postgres service. Override with DATABASE_URL for Postgres.
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'users.db')
os.makedirs(os.path.dirname(_DEFAULT_DB_PATH), exist_ok=True)
DATABASE_URL = os.environ.get('DATABASE_URL', f'sqlite:///{_DEFAULT_DB_PATH}')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Allow session cookies to be sent inside cross-origin iframes (e.g. Google Sites).
# SameSite=None requires Secure=True (HTTPS), which is always true on Railway.
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True
db = SQLAlchemy(app)

@app.after_request
def allow_google_sites_framing(response):
    # Allow Google Sites to embed this app in an iframe.
    response.headers['Content-Security-Policy'] = (
        "frame-ancestors 'self' https://sites.google.com https://*.googleusercontent.com"
    )
    # Remove any X-Frame-Options header that would block framing.
    response.headers.remove('X-Frame-Options')
    return response

PESQUISADORES_SHEET_URL = "https://docs.google.com/spreadsheets/d/1adWD1sksMqWhAaLmKC61mV8a3ZeuT-ou/export?format=xlsx"
PLANILHA_EXTENDIDA_SHEET_URL = "https://drive.usercontent.google.com/download?id=10mvn7MjatBzXqfG5Uyg9wbK1lnYGBbtW&export=download&confirm=t"
INVASIVE_LIST_URL = "https://drive.google.com/uc?export=download&id=1_KHngk2dHKir5Phsndpp_eN_bydBYM3s"
IPT_SOURCE_URL = "https://ipt.jbrj.gov.br/jbrj/archive.do?r=catalogo_taxonomico_da_fauna_do_brasil&v=1.50"
IPT_COMBINED_SHEET_URL = os.environ.get('IPT_COMBINED_SHEET_URL', '')
DATA_DATES_FILE = os.path.join(os.path.dirname(__file__), 'data', 'data_dates.json')
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
IPT_DF = None
DATA_LOADED_SUCCESSFULLY = False

IPT_UPDATE_JOB = {'status': 'idle', 'message': '', 'last_update': None}

def download_file(url, dest_path):
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False

def process_ipt_archive():
    global IPT_UPDATE_JOB, IPT_DF
    IPT_UPDATE_JOB['status'] = 'running'
    IPT_UPDATE_JOB['message'] = 'Iniciando download do IPT...'
    
    data_dir = os.path.join(app.root_path, 'data')
    ipt_dir = os.path.join(data_dir, 'ipt_tmp')
    os.makedirs(ipt_dir, exist_ok=True)
    zip_path = os.path.join(ipt_dir, 'dwca.zip')
    
    try:
        if not download_file(IPT_SOURCE_URL, zip_path):
            raise Exception("Falha no download do arquivo ZIP do IPT.")
            
        IPT_UPDATE_JOB['message'] = 'Extraindo arquivos...'
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(ipt_dir)
            
        taxon_file = os.path.join(ipt_dir, 'taxon.txt')
        dist_file = os.path.join(ipt_dir, 'distribution.txt')
        vern_file = os.path.join(ipt_dir, 'vernacularname.txt')
        
        if not os.path.exists(taxon_file):
            raise Exception("Arquivo taxon.txt não encontrado no arquivo ZIP.")
            
        IPT_UPDATE_JOB['message'] = 'Processando tabelas (pode demorar alguns minutos)...'
        
        # Process Taxon
        taxon_df = pd.read_csv(taxon_file, sep='\t', low_memory=False)
        
        # Process Distribution
        dist_agg = pd.DataFrame(columns=['id', 'distribution'])
        if os.path.exists(dist_file):
            dist_df = pd.read_csv(dist_file, sep='\t', low_memory=False)
            dist_agg = dist_df.groupby('id')['locality'].apply(lambda x: '; '.join(filter(None, x.astype(str).unique()))).reset_index()
            dist_agg.rename(columns={'locality': 'distribution'}, inplace=True)
            
        # Process Vernacular
        vern_agg = pd.DataFrame(columns=['id', 'common_names'])
        if os.path.exists(vern_file):
            vern_df = pd.read_csv(vern_file, sep='\t', low_memory=False)
            vern_agg = vern_df.groupby('id')['vernacularName'].apply(lambda x: '; '.join(filter(None, x.astype(str).unique()))).reset_index()
            vern_agg.rename(columns={'vernacularName': 'common_names'}, inplace=True)
            
        IPT_UPDATE_JOB['message'] = 'Mesclando dados...'
        merged = taxon_df.merge(dist_agg, on='id', how='left').merge(vern_agg, on='id', how='left')
        merged.columns = [c.lower().strip() for c in merged.columns]
        
        output_csv = os.path.join(data_dir, 'ipt_combined.csv')
        merged.to_csv(output_csv, index=False)
        
        IPT_DF = merged
        IPT_UPDATE_JOB['status'] = 'success'
        IPT_UPDATE_JOB['message'] = f'IPT atualizado com sucesso! {len(merged)} registros processados.'
        IPT_UPDATE_JOB['last_update'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Clean up tmp dir
        shutil.rmtree(ipt_dir)
        
    except Exception as e:
        IPT_UPDATE_JOB['status'] = 'error'
        IPT_UPDATE_JOB['message'] = f'Erro: {str(e)}'
        print(f"IPT Processing Error: {e}")

def _gdrive_direct_url(url):
    """Convert any Google Drive share/uc URL to usercontent direct download URL."""
    import re
    m = re.search(r'[?&/](?:id=|d/)([A-Za-z0-9_-]{10,})', url)
    if m:
        return f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t"
    return url

def download_gsheet(url):
    try:
        dl_url = _gdrive_direct_url(url) if 'drive.google.com' in url else url
        session = requests.Session()
        response = session.get(dl_url, timeout=300)
        response.raise_for_status()
        # Detect HTML response — means file not public or URL wrong
        if response.content[:100].lower().lstrip().startswith(b'<!doctype') or \
           response.content[:100].lower().lstrip().startswith(b'<html'):
            print(f"ERROR: Google Drive returned HTML for {dl_url}. "
                  f"File may not be publicly shared or URL is invalid.")
            return None
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not download from {url}. Error: {e}")
        return None

# --- JBRJ Fauna do Brasil PostgREST API ---
FAUNA_API_URL = os.environ.get(
    'FAUNA_API_URL',
    'https://fauna.jbrj.gov.br/rest/mv_planilha_extendida'
)
FAUNA_PAGE_SIZE = int(os.environ.get('FAUNA_PAGE_SIZE', '5000'))

def download_fauna_csv(dest_path):
    """Download the full Catalogo Taxonomico da Fauna do Brasil dataset from the
    JBRJ PostgREST API and write it to dest_path as 'planilha_extendida.csv'.

    Paginates with limit/offset, streams each page straight to a temporary file
    and atomically replaces dest_path on success, so an existing cached file is
    preserved if the download fails midway. Returns True on success.
    """
    import csv as _csv
    tmp_path = dest_path + '.tmp'
    offset = 0
    total = 0
    writer = None
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        sess = requests.Session()
        with open(tmp_path, 'w', encoding='utf-8', newline='') as fh:
            while True:
                url = f'{FAUNA_API_URL}?limit={FAUNA_PAGE_SIZE}&offset={offset}'
                resp = sess.get(url, timeout=300,
                                headers={'Accept': 'application/json'})
                resp.raise_for_status()
                rows = resp.json()
                if not rows:
                    break
                if writer is None:
                    writer = _csv.DictWriter(fh, fieldnames=list(rows[0].keys()),
                                             extrasaction='ignore')
                    writer.writeheader()
                writer.writerows(rows)
                total += len(rows)
                if len(rows) < FAUNA_PAGE_SIZE:
                    break
                offset += FAUNA_PAGE_SIZE
        if total == 0:
            os.remove(tmp_path)
            print("ERROR: Fauna API returned no rows.")
            return False
        os.replace(tmp_path, dest_path)
        print(f"Downloaded {total} rows from Fauna API -> {dest_path}")
        return True
    except Exception as e:
        print(f"ERROR downloading from Fauna API: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False

# --- JBRJ researcher contribution report (daily pesquisadores refresh) ---
PESQUISADORES_API_URL = os.environ.get(
    'PESQUISADORES_API_URL',
    'https://fauna.jbrj.gov.br/rest/mv_relatorio_contribuicao_usuarios'
)

def _build_taxons(*fields):
    """Merge comma-separated taxon strings (filo/classe/familia) into one
    deduplicated, semicolon-separated string, preserving first-seen order."""
    seen = []
    for f in fields:
        if not isinstance(f, str):
            continue
        for t in f.split(','):
            t = t.strip()
            if t and t not in seen:
                seen.append(t)
    return ';'.join(seen)

def fetch_pesquisadores_api():
    """Download the researcher list from the JBRJ contribution-report PostgREST
    endpoint. Returns a DataFrame (login, nome_completo, email, táxons) or None
    on failure, in which case the caller keeps the existing sheet."""
    try:
        sess = requests.Session()
        rows = []
        offset, page = 0, 5000
        while True:
            url = (f'{PESQUISADORES_API_URL}?limit={page}&offset={offset}'
                   '&select=login,nome_completo,email,'
                   'filos_alterados,classes_alteradas,familias_alteradas')
            resp = sess.get(url, timeout=120, headers={'Accept': 'application/json'})
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page:
                break
            offset += page
        if not rows:
            print("ERROR: pesquisadores API returned no rows.")
            return None
        recs = [{
            'login':         (r.get('login') or '').strip(),
            'nome_completo': (r.get('nome_completo') or '').strip(),
            'email':         (r.get('email') or '').strip(),
            'táxons':        _build_taxons(r.get('filos_alterados'),
                                           r.get('classes_alteradas'),
                                           r.get('familias_alteradas')),
        } for r in rows]
        df = pd.DataFrame(recs)
        df = df[df['login'] != ''].reset_index(drop=True)
        print(f"Fetched {len(df)} researchers from JBRJ contribution API.")
        return df
    except Exception as e:
        print(f"ERROR downloading pesquisadores from API: {e}")
        return None

def merge_pesquisadores(base_df, api_df):
    """Merge mode. The API supplies login/nome_completo/táxons/email; the base
    sheet supplies institution and is the fallback for blank API táxons and for
    users absent from the API. Returns a DataFrame keyed by login."""
    if api_df is None or api_df.empty:
        return base_df

    def _get(row, col):
        if row is not None and col in row and pd.notna(row.get(col)):
            return str(row.get(col)).strip()
        return ''

    base_by_login = {}
    if base_df is not None and 'login' in base_df.columns:
        for _, br in base_df.iterrows():
            lg = str(br.get('login', '')).strip().lower()
            if lg:
                base_by_login[lg] = br

    out, used = [], set()
    for _, ar in api_df.iterrows():
        lg = ar['login'].strip().lower()
        used.add(lg)
        b = base_by_login.get(lg)
        out.append({
            'login':         ar['login'],
            'nome_completo': ar['nome_completo'] or _get(b, 'nome_completo'),
            'táxons':        ar['táxons'] or _get(b, 'táxons'),
            'institution':   _get(b, 'institution'),
            'email':         ar['email'] or _get(b, 'email'),
        })
    # users present only in the base sheet — keep them untouched
    sheet_only = 0
    for lg, b in base_by_login.items():
        if lg in used:
            continue
        sheet_only += 1
        out.append({
            'login':         _get(b, 'login'),
            'nome_completo': _get(b, 'nome_completo'),
            'táxons':        _get(b, 'táxons'),
            'institution':   _get(b, 'institution'),
            'email':         _get(b, 'email'),
        })
    merged = pd.DataFrame(out)
    print(f"Merged pesquisadores: {len(used)} from API + {sheet_only} sheet-only "
          f"= {len(merged)} total.")
    return merged

LOCAL_PESQUISADORES = os.path.join(os.path.dirname(__file__), 'data', 'pesquisadores.xlsx')
LOCAL_PLANILHA      = os.path.join(os.path.dirname(__file__), 'data', 'planilha_extendida.csv')
LOCAL_IPT_COMBINED  = os.path.join(os.path.dirname(__file__), 'data', 'ipt_combined.csv')
LOCAL_INVASIVE      = os.path.join(os.path.dirname(__file__), 'data', 'invasive_list.tsv')

INVASIVE_DF = None

def load_data_on_startup():
    global TAXON_HIERARCHY, PESQUISADORES_DF, PLANILHA_DF, IPT_DF, INVASIVE_DF, DATA_LOADED_SUCCESSFULLY

    print("--- Starting Data Load ---")
    # --- pesquisadores (base sheet for institution + daily JBRJ API merge) ---
    try:
        import unicodedata as _ud
        base_df = None
        content = download_gsheet(PESQUISADORES_SHEET_URL)
        if content:
            base_df = pd.read_excel(BytesIO(content), header=0)
            print("Loaded pesquisadores base sheet from Google Sheet.")
        elif os.path.exists(LOCAL_PESQUISADORES):
            base_df = pd.read_excel(LOCAL_PESQUISADORES, header=0)
            print("Loaded pesquisadores base sheet from local cache (Google Sheet unavailable).")
        if base_df is not None:
            # NFC-normalize so decomposed accents (from Google Sheets) match source literals
            base_df.columns = [_ud.normalize('NFC', c).lower().strip() for c in base_df.columns]

        api_df = fetch_pesquisadores_api()
        if api_df is not None:
            PESQUISADORES_DF = merge_pesquisadores(base_df, api_df)
            # Cache the merged result for offline fallback and stamp the refresh date.
            try:
                os.makedirs(os.path.dirname(LOCAL_PESQUISADORES), exist_ok=True)
                PESQUISADORES_DF.to_excel(LOCAL_PESQUISADORES, index=False)
            except Exception as _e:
                print(f"  (could not cache merged pesquisadores: {_e})")
            try:
                _d = load_data_dates()
                _d['pesquisadores'] = datetime.date.today().isoformat()
                save_data_dates(_d)
            except Exception as _e:
                print(f"  (could not update pesquisadores date: {_e})")
        else:
            # API unavailable — fall back to the base sheet / local cache unchanged.
            PESQUISADORES_DF = base_df

        if PESQUISADORES_DF is not None:
            print(f"  {len(PESQUISADORES_DF)} researchers loaded. columns={list(PESQUISADORES_DF.columns)}")
    except Exception as e:
        print(f"ERROR loading pesquisadores: {e}")

    # --- planilha extendida (from JBRJ Fauna API) ---
    try:
        ok = download_fauna_csv(LOCAL_PLANILHA)
        if ok and os.path.exists(LOCAL_PLANILHA):
            PLANILHA_DF = pd.read_csv(LOCAL_PLANILHA, low_memory=False)
            print("Loaded planilha from Fauna API.")
            # Record refresh date for the UI.
            try:
                _d = load_data_dates()
                _d['planilha_extendida'] = datetime.date.today().isoformat()
                save_data_dates(_d)
            except Exception as _e:
                print(f"  (could not update planilha date: {_e})")
        elif os.path.exists(LOCAL_PLANILHA):
            PLANILHA_DF = pd.read_csv(LOCAL_PLANILHA, low_memory=False)
            print("Loaded planilha from local cache (Fauna API unavailable).")
            
        if PLANILHA_DF is not None:
            PLANILHA_DF.columns = [col.lower().strip() for col in PLANILHA_DF.columns]
            # Normalize to uppercase; GDrive file uses English DwC values
            if 'taxonrank' in PLANILHA_DF.columns:
                _raw_ranks = PLANILHA_DF['taxonrank'].str.upper().str.strip().value_counts().to_dict()
                print(f"  taxonrank raw values: {_raw_ranks}")
                PLANILHA_DF['taxonrank'] = PLANILHA_DF['taxonrank'].str.upper().str.strip()
            if 'taxonomicstatus' in PLANILHA_DF.columns:
                _raw_statuses = PLANILHA_DF['taxonomicstatus'].str.upper().str.strip().value_counts().to_dict()
                print(f"  taxonomicstatus raw values: {_raw_statuses}")
                PLANILHA_DF['taxonomicstatus'] = PLANILHA_DF['taxonomicstatus'].str.upper().str.strip().replace({
                    'HOMOTYPICSYNONYM':   'SYNONYM',
                    'HETEROTYPICSYNONYM': 'SYNONYM',
                })
            if 'establishmentmeans' in PLANILHA_DF.columns:
                PLANILHA_DF['establishmentmeans'] = PLANILHA_DF['establishmentmeans'].str.upper().str.strip().replace({
                    'NATIVE':       'NATIVA',
                    'EXOTIC':       'EXOTICA',
                    'CRYPTOGENIC':  'CRIPTOGENICA',
                })
            print(f"  {len(PLANILHA_DF)} records loaded.")
    except Exception as e:
        print(f"ERROR loading planilha: {e}")

    # --- invasive list ---
    try:
        content = download_gsheet(INVASIVE_LIST_URL)
        if content:
            INVASIVE_DF = pd.read_csv(BytesIO(content), sep='\t')
            os.makedirs(os.path.dirname(LOCAL_INVASIVE), exist_ok=True)
            with open(LOCAL_INVASIVE, 'wb') as f:
                f.write(content)
            print("Loaded invasive list from Google Drive.")
        elif os.path.exists(LOCAL_INVASIVE):
            INVASIVE_DF = pd.read_csv(LOCAL_INVASIVE, sep='\t')
            print("Loaded invasive list from local file.")
        
        if INVASIVE_DF is not None:
            print(f"  {len(INVASIVE_DF)} invasive species loaded.")
    except Exception as e:
        print(f"ERROR loading invasive list: {e}")

    # --- IPT combined (optional) ---
    try:
        if os.path.exists(LOCAL_IPT_COMBINED):
            IPT_DF = pd.read_csv(LOCAL_IPT_COMBINED, low_memory=False)
            print(f"Loaded IPT data from local file. {len(IPT_DF)} records.")
        elif IPT_COMBINED_SHEET_URL:
            # Attempt to download from GDrive if configured
            resp = requests.get(IPT_COMBINED_SHEET_URL, timeout=60)
            if resp.status_code == 200:
                IPT_DF = pd.read_csv(BytesIO(resp.content), low_memory=False)
                print("Loaded IPT data from Google Drive link.")
    except Exception as e:
        print(f"ERROR loading IPT data: {e}")

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

def get_user_taxa(user):
    """Return the lowercase taxa list authorised for a user, read from the in-memory
    pesquisadores table. Computed per request rather than stored in the session cookie,
    because a researcher may be assigned many taxa (phylum + class + dozens of families)
    which would overflow the 4 KB browser cookie limit and silently drop the session."""
    if user is not None and PESQUISADORES_DF is not None and 'login' in PESQUISADORES_DF.columns:
        row = PESQUISADORES_DF[PESQUISADORES_DF['login'].str.lower() == user.username.lower()]
        if not row.empty and 'táxons' in PESQUISADORES_DF.columns:
            taxa_str = row.iloc[0]['táxons']
            if isinstance(taxa_str, str):
                return sorted(
                    t.strip().lower() for t in _re.split(r'[;,]', taxa_str) if t.strip()
                )
    return []

def current_allowed_taxa():
    """Authorised taxa for the currently logged-in user (empty if not logged in)."""
    uid = session.get('user_id')
    if not uid:
        return []
    return get_user_taxa(User.query.get(uid))

# ── GBIF gap analysis ──────────────────────────────────────────────────────────
GBIF_JOBS = {}   # job_id → dict with status/progress/result
INVASIVE_JOBS = {} # job_id → dict with status/progress/result

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
        sp_mask = df['taxonrank'].str.upper().str.strip() == 'SPECIES'
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
                sp_mask & (df['taxonomicstatus'].str.upper().str.strip() == 'ACCEPTED'))
        else:
            ctfb_accepted = make_binomials(sp_mask)

        # Synonyms: any other status (SYNONYM, NOME_DUVIDOSO, etc.)
        if has_status:
            ctfb_synonyms = make_binomials(
                sp_mask & (df['taxonomicstatus'].str.upper().str.strip() != 'ACCEPTED')
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

        # ── Create ZIP (including manuals) ──
        zip_path = os.path.join('/tmp', f'gbif_gap_{job_id}.zip')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(result_path, f'gbif_gap_{taxon_name.replace(" ", "_")}.xlsx')
            # Include manuals if they exist
            if os.path.exists('manual_pt.pdf'):
                zf.write('manual_pt.pdf', 'manual_pt.pdf')
            if os.path.exists('manual_en.pdf'):
                zf.write('manual_en.pdf', 'manual_en.pdf')

        GBIF_JOBS[job_id].update(
            status='done', pct=100,
            progress='Concluído.',
            result_path=zip_path,
            taxon_name=taxon_name,
            n_gbif=len(gbif_df),
            n_missing=len(not_in_ctfb),
            n_synonym=len(as_synonym),
            n_present=len(in_ctfb),
            n_ctfb=len(ctfb_accepted),
        )

    except Exception as e:
        GBIF_JOBS[job_id].update(status='error', error=str(e))

def _invasive_gap_worker(job_id, taxon_name, planilha_df):
    def update(progress, pct=None):
        INVASIVE_JOBS[job_id]['progress'] = progress
        if pct is not None:
            INVASIVE_JOBS[job_id]['pct'] = pct

    try:
        INVASIVE_JOBS[job_id] = {'status': 'running', 'progress': 'Iniciando…', 'pct': 0,
                                 'result_path': None, 'error': None}

        # ── Phase 1: download and filter invasive species list ──
        update('Baixando lista de espécies invasoras…', 5)
        response = requests.get(INVASIVE_LIST_URL, timeout=60)
        response.raise_for_status()
        
        from io import BytesIO
        # We know from earlier that it's a TSV (even with .xlsx extension in the Drive link)
        invasive_df = pd.read_csv(BytesIO(response.content), sep='\t')
        
        if invasive_df.empty:
            INVASIVE_JOBS[job_id].update(status='error', error='Lista de espécies invasoras vazia.')
            return

        # Filtering invasive species by taxon_name if provided
        # The invasive list only has binomials, so we use the CTFB as a "taxonomic universe"
        # to identify which species in the invasive list belong to the requested taxon.
        
        # ── Phase 2: compare with CTFB (also filtered by taxon) ──
        df_full = planilha_df.copy()
        
        # Filter CTFB by taxon_name to get the "Universe" of relevant species
        RANK_HIERARCHY = [
            'phylum', 'superclass', 'class', 'subclass', 'infraclass',
            'superorder', 'order', 'suborder', 'infraorder',
            'superfamily', 'family', 'subfamily', 'tribe', 'subtribe',
            'genus', 'subgenus',
        ]
        
        if taxon_name and taxon_name.lower() != 'animalia':
            mask_universe = pd.Series(False, index=df_full.index)
            for rank in RANK_HIERARCHY:
                if rank in df_full.columns:
                    mask_universe |= (df_full[rank].astype(str).str.lower().str.strip() == taxon_name.lower())
            df_filtered = df_full[mask_universe].copy()
        else:
            df_filtered = df_full.copy()

        if df_filtered.empty:
            INVASIVE_JOBS[job_id].update(status='error', 
                error=f'O táxon "{taxon_name}" não contém espécies no CTFB.')
            return

        # Identify all binomials (accepted and synonyms) in CTFB for this taxon
        # to filter the invasive list.
        def get_all_binomials(dataframe):
            sp_m = dataframe['taxonrank'].str.upper().str.strip() == 'SPECIES'
            has_bin = dataframe.get('genus', pd.Series(dtype=str)).notna() & \
                      dataframe.get('specificepithet', pd.Series(dtype=str)).notna()
            sub = dataframe[sp_m & has_bin]
            return set(
                (sub['genus'].str.strip() + ' ' + sub['specificepithet'].str.strip())
                .str.lower()
            )

        taxon_universe_binomials = get_all_binomials(df_filtered)
        
        # Now filter the invasive list by this universe
        invasive_df['binomial'] = invasive_df['scientificName'].str.strip().str.lower()
        invasive_df = invasive_df[invasive_df['binomial'].isin(taxon_universe_binomials)].copy()
        
        # Deduplicate to ensure each species is counted and listed only once
        invasive_df = invasive_df.drop_duplicates(subset='binomial', keep='first')

        if invasive_df.empty:
            INVASIVE_JOBS[job_id].update(status='error', 
                error=f'Nenhuma espécie da lista de invasoras pertence ao táxon "{taxon_name}" (baseado no CTFB).')
            return

        update(f'Lista filtrada pelo universo "{taxon_name}" ({len(invasive_df)} registros). Comparando...', 20)

        # Now proceed with the standard comparison using the filtered CTFB subset
        has_status = 'taxonomicstatus' in df_filtered.columns
        sp_mask = df_filtered['taxonrank'].str.upper().str.strip() == 'SPECIES'
        has_binomial = df_filtered.get('genus', pd.Series(dtype=str)).notna() & \
                       df_filtered.get('specificepithet', pd.Series(dtype=str)).notna()

        def make_binomials(mask):
            sub = df_filtered[mask & has_binomial]
            return set(
                (sub['genus'].str.strip() + ' ' + sub['specificepithet'].str.strip())
                .str.lower()
            )

        # Accepted names
        if has_status:
            ctfb_accepted = make_binomials(
                sp_mask & (df_filtered['taxonomicstatus'].str.upper().str.strip() == 'ACCEPTED'))
        else:
            ctfb_accepted = make_binomials(sp_mask)

        # Synonyms
        if has_status:
            ctfb_synonyms = make_binomials(
                sp_mask & (df_filtered['taxonomicstatus'].str.upper().str.strip() != 'ACCEPTED')
            ) - ctfb_accepted
        else:
            ctfb_synonyms = set()

        invasive_df['canonical_name'] = invasive_df['scientificName'].str.strip()
        invasive_df['binomial'] = invasive_df['canonical_name'].str.lower()

        in_ctfb     = invasive_df[invasive_df['binomial'].isin(ctfb_accepted)].copy()
        as_synonym  = invasive_df[
            ~invasive_df['binomial'].isin(ctfb_accepted) &
             invasive_df['binomial'].isin(ctfb_synonyms)
        ].copy()
        not_in_ctfb = invasive_df[
            ~invasive_df['binomial'].isin(ctfb_accepted) &
            ~invasive_df['binomial'].isin(ctfb_synonyms)
        ].copy()

        # ── Phase 3: Save XLSX ──
        update('Gerando arquivo XLSX…', 85)
        result_path = os.path.join('/tmp', f'invasive_gap_{job_id}.xlsx')
        
        _export_cols = ['scientificName', 'kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'specificEpithet', 'datasetName']
        export_cols = [c for c in _export_cols if c in invasive_df.columns]

        with pd.ExcelWriter(result_path, engine='openpyxl') as writer:
            not_in_ctfb[export_cols].to_excel(writer, sheet_name='Ausentes_no_CTFB', index=False)
            as_synonym[export_cols].to_excel(writer, sheet_name='Sinonimos_no_CTFB', index=False)
            in_ctfb[export_cols].to_excel(writer, sheet_name='Presentes_no_CTFB', index=False)

        # ── Create ZIP (including manuals) ──
        zip_path = os.path.join('/tmp', f'invasive_gap_{job_id}.zip')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(result_path, f'invasive_gap_{job_id[:8]}.xlsx')
            if os.path.exists('manual_pt.pdf'):
                zf.write('manual_pt.pdf', 'manual_pt.pdf')
            if os.path.exists('manual_en.pdf'):
                zf.write('manual_en.pdf', 'manual_en.pdf')

        INVASIVE_JOBS[job_id].update(
            status='done', pct=100,
            progress='Concluído.',
            result_path=zip_path,
            taxon_name=taxon_name,
            n_total=len(invasive_df),
            n_missing=len(not_in_ctfb),
            n_synonym=len(as_synonym),
            n_present=len(in_ctfb),
            n_ctfb=len(ctfb_accepted),
        )

    except Exception as e:
        INVASIVE_JOBS[job_id].update(status='error', error=str(e))

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

def run_python_analysis(taxon_filter, pesquisadores_df, planilha_df, category=None):
    import sys as _sys
    def _dbg(msg):
        print(msg, file=_sys.stderr, flush=True)
    try:
        # Full taxonomic rank hierarchy (coarser → finer)
        RANK_HIERARCHY = [
            'phylum', 'superclass', 'class', 'subclass', 'infraclass',
            'superorder', 'order', 'suborder', 'infraorder',
            'superfamily', 'family', 'subfamily', 'tribe', 'subtribe',
            'genus', 'subgenus',
        ]

        # Optional category: restrict the match to a single rank column when the
        # user explicitly chose one; otherwise search the whole hierarchy.
        category = (category or '').strip().lower() or None
        if category and category not in planilha_df.columns:
            _dbg(f"[analysis] '{taxon_filter}': requested category '{category}' not a known rank column; ignoring")
            category = None
        ranks_to_search = [category] if category else RANK_HIERARCHY

        _rank_cols = [r for r in RANK_HIERARCHY if r in planilha_df.columns]
        _dbg(f"[analysis] '{taxon_filter}' start (category={category}). planilha cols={list(planilha_df.columns[:10])} rank_cols_found={_rank_cols}")
        # --- Filter rows matching the requested taxon ---
        mask = pd.Series(False, index=planilha_df.index)
        for rank in ranks_to_search:
            if rank in planilha_df.columns:
                mask |= (planilha_df[rank].str.lower() == taxon_filter.lower())
        filtered_data = planilha_df[mask].copy()
        _dbg(f"[analysis] '{taxon_filter}': {len(filtered_data)} rows matched rank filter")
        if filtered_data.empty:
            scope = f"category '{category}'" if category else f"rank cols {_rank_cols}"
            diag = f"no rows matched '{taxon_filter}' in {scope}"
            _dbg(f"[analysis] {diag}")
            return None, None, diag

        # Determine which rank the input taxon belongs to (honour the chosen
        # category first, then fall back to scanning the hierarchy).
        taxon_rank_col = None
        for col in ([category] if category else []) + RANK_HIERARCHY:
            if col in filtered_data.columns:
                if (filtered_data[col].str.lower() == taxon_filter.lower()).any():
                    taxon_rank_col = col
                    break
        taxon_rank_idx = RANK_HIERARCHY.index(taxon_rank_col) if taxon_rank_col else -1
        _dbg(f"[analysis] '{taxon_filter}': rank_col={taxon_rank_col}")

        def is_below_input_rank(level):
            """True only if level is strictly finer than the input taxon's rank."""
            if taxon_rank_idx < 0 or level not in RANK_HIERARCHY:
                return True
            return RANK_HIERARCHY.index(level) > taxon_rank_idx

        _taxonrank_norm = filtered_data['taxonrank'].str.upper().str.strip()
        rank_mask   = _taxonrank_norm.isin(['SPECIES', 'SUBSPECIES'])
        status_mask = filtered_data['taxonomicstatus'].str.upper().str.strip() == 'ACCEPTED' \
                      if 'taxonomicstatus' in filtered_data.columns \
                      else pd.Series(True, index=filtered_data.index)
        _rank_vals = _taxonrank_norm.value_counts().to_dict()
        _status_vals = filtered_data['taxonomicstatus'].str.upper().str.strip().value_counts().to_dict() if 'taxonomicstatus' in filtered_data.columns else {}
        _dbg(f"[analysis] '{taxon_filter}': rank_mask={rank_mask.sum()} status_mask={status_mask.sum()} combined={(rank_mask & status_mask).sum()} taxonrank_vals={_rank_vals} status_vals={_status_vals}")
        accepted = filtered_data[rank_mask & status_mask].copy()
        if accepted.empty:
            diag = f"found {len(filtered_data)} rows but 0 accepted species/subspecies. taxonrank_vals={_rank_vals} status_vals={_status_vals}"
            _dbg(f"[analysis] '{taxon_filter}': {diag}")
            return None, None, diag

        # If a species has accepted subspecies, drop the species-level row and
        # use only its subspecies as the units of analysis.
        if 'genus' in accepted.columns and 'specificepithet' in accepted.columns:
            accepted['_binomial'] = (
                accepted['genus'].fillna('').str.strip() + ' ' +
                accepted['specificepithet'].fillna('').str.strip()
            ).str.lower()
            _accepted_rank = accepted['taxonrank'].str.upper().str.strip()
            subsp_binomials = set(
                accepted.loc[_accepted_rank == 'SUBSPECIES', '_binomial']
            )
            # Keep row if it is a subspecies OR if its binomial has no subspecies
            species_data = accepted[
                (_accepted_rank == 'SUBSPECIES') |
                (~accepted['_binomial'].isin(subsp_binomials))
            ].copy()
            species_data.drop(columns=['_binomial'], inplace=True)
        else:
            species_data = accepted.copy()

        if species_data.empty:
            return None, None, "species_data empty after subspecies dedup"

        # Deduplicate by canonical epithet key:
        # 1. Rows with the same epithet key AND the same namepublishedinyear are merged
        #    column-by-column; distinct non-empty values are joined with '|'.
        # 2. Among rows with the same epithet key but different years, keep only the
        #    oldest namepublishedinyear (NaN years are treated as last).
        # Key = genus + subgenus + specificepithet + infraspecificepithet (non-empty parts).
        _epi_cols = [c for c in ['genus', 'subgenus', 'specificepithet', 'infraspecificepithet']
                     if c in species_data.columns]
        if 'specificepithet' in _epi_cols and 'namepublishedinyear' in species_data.columns:
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
                        parts = [p for p in [name, lang, loc]
                                 if p and p.lower() != 'nan']
                        entries.append('(' + ', '.join(parts) + ')' if len(parts) > 1 else name)
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

        # --- Manual fields (regras.txt Section 3) ---
        # The first 15 follow ecological/trophic exclusion rules below; the last 4
        # (controlledbibliography, countrycode, voucher, typology) are plain
        # completeness fields — always applicable, no special rules.
        MANUAL_COLS = [
            "bibliographicreference", "country", "establishmentmeans", "endemicbrazil",
            "environment", "locationid", "epicontinentaldomain", "marinedomain",
            "lifeform", "habitat", "vernacularname", "vernacularnamelanguage",
            "vernacularnamelocality", "animalhostnames", "vegetalhostnames",
            "controlledbibliography", "countrycode", "voucher", "typology",
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

        # Bibliography rule: bibliographicReference and controlledBibliography form
        # a single slot — if either is filled the slot counts as filled. Collapse the
        # two columns into one (1 applicable slot, filled when either is present).
        bib_in  = 'bibliographicreference' in manual_present
        ctrl_in = 'controlledbibliography' in manual_present
        if bib_in and ctrl_in:
            filled_count -= filled_matrix['bibliographicreference'].astype(float)
            filled_count -= filled_matrix['controlledbibliography'].astype(float)
            species_data['total_applicable'] -= 1.0   # two columns → one slot
            bib_filled = (filled_matrix['bibliographicreference'] |
                          filled_matrix['controlledbibliography']).astype(float)
            filled_count += bib_filled

        species_data['filled_count'] = filled_count.values
        species_data['completeness'] = (species_data['filled_count'] / species_data['total_applicable']) * 100

        # --- Per-column applicability mask (for missing-fields CSV) ---
        applicable_mask = pd.DataFrame(True, index=species_data.index, columns=manual_present)
        effective_filled = filled_matrix.copy()

        # environment "vazio" → applicable but counts as not filled
        if 'environment' in manual_present:
            effective_filled.loc[is_vazio, 'environment'] = False

        # endemicbrazil = SIM → country not applicable
        if 'country' in manual_present:
            applicable_mask.loc[endemic_sim, 'country'] = False

        # Domain applicability
        if epi_in and marine_in:
            applicable_mask.loc[is_epicontinental, 'marinedomain'] = False
            applicable_mask.loc[is_marine, 'epicontinentaldomain'] = False
            _ambig = is_vazio | is_null_env
            _ke = _ambig & (filled_matrix['epicontinentaldomain'] | ~filled_matrix['marinedomain'])
            _km = _ambig & filled_matrix['marinedomain'] & ~filled_matrix['epicontinentaldomain']
            applicable_mask.loc[_ke, 'marinedomain'] = False
            applicable_mask.loc[_km, 'epicontinentaldomain'] = False
        elif epi_in and not marine_in:
            applicable_mask.loc[is_marine, 'epicontinentaldomain'] = False
        elif marine_in and not epi_in:
            applicable_mask.loc[is_epicontinental, 'marinedomain'] = False

        # Host applicability
        if animal_in:
            applicable_mask.loc[is_empty_lf | is_vida_livre | is_herbivore | is_parasite, 'animalhostnames'] = False
        if vegetal_in:
            applicable_mask.loc[is_empty_lf | is_vida_livre | is_parasite, 'vegetalhostnames'] = False

        # Bibliography slot: represent on bibliographicReference (filled when either
        # bibliographicReference OR controlledBibliography is present); fold the
        # controlledBibliography column out of the per-field report.
        if bib_in and ctrl_in:
            effective_filled.loc[:, 'bibliographicreference'] = (
                filled_matrix['bibliographicreference'] | filled_matrix['controlledbibliography']
            )
            applicable_mask.loc[:, 'controlledbibliography'] = False

        unfilled_mask = applicable_mask & ~effective_filled

        # Output headers use the original Darwin Core term names (camelCase),
        # matching the source CSV columns rather than Portuguese labels.
        _FIELD_DWC = {
            'bibliographicreference':  'bibliographicReference',
            'country':                 'country',
            'establishmentmeans':      'establishmentMeans',
            'endemicbrazil':           'endemicBrazil',
            'environment':             'environment',
            'locationid':              'locationID',
            'epicontinentaldomain':    'epicontinentalDomain',
            'marinedomain':            'marineDomain',
            'lifeform':                'lifeForm',
            'habitat':                 'habitat',
            'vernacularname':          'vernacularName',
            'vernacularnamelanguage':  'vernacularNameLanguage',
            'vernacularnamelocality':  'vernacularNameLocality',
            'animalhostnames':         'animalHostNames',
            'vegetalhostnames':        'vegetalHostNames',
            'controlledbibliography':  'controlledBibliography',
            'countrycode':             'countryCode',
            'voucher':                 'voucher',
            'typology':                'typology',
        }
        # Darwin Core casing for the identifier columns carried into the export.
        _ID_DWC = {
            'taxonid':        'taxonID',
            'family':         'family',
            'genus':          'genus',
            'scientificname': 'scientificName',
            'taxonrank':      'taxonRank',
        }

        _id_cols = [c for c in ['taxonid', 'family', 'genus', 'scientificname', 'taxonrank']
                    if c in species_data.columns]
        missing_fields_df = species_data[_id_cols].copy()
        missing_fields_df.insert(0, 'taxon_analisado', taxon_filter)

        for _col in manual_present:
            missing_fields_df[_FIELD_DWC.get(_col, _col)] = unfilled_mask[_col].map({True: 'faltante', False: ''})

        # controlledBibliography is folded into the bibliographicReference slot — drop
        # its (always-empty) per-field column from the report.
        if bib_in and ctrl_in:
            missing_fields_df.drop(columns=['controlledBibliography'], inplace=True, errors='ignore')

        # Combined host slot for parasites
        if (animal_in or vegetal_in) and is_parasite.any():
            if animal_in and vegetal_in:
                _host_eff = effective_filled['animalhostnames'] | effective_filled['vegetalhostnames']
            elif animal_in:
                _host_eff = effective_filled['animalhostnames']
            else:
                _host_eff = effective_filled['vegetalhostnames']
            missing_fields_df['parasiteHostNames'] = (is_parasite & ~_host_eff).map({True: 'faltante', False: ''})

        _field_cols = [c for c in missing_fields_df.columns if c not in _id_cols and c != 'taxon_analisado']
        missing_fields_df = missing_fields_df[missing_fields_df[_field_cols].eq('faltante').any(axis=1)]
        _sort_miss = [c for c in ['family', 'genus', 'scientificname'] if c in missing_fields_df.columns]
        if _sort_miss:
            missing_fields_df = missing_fields_df.sort_values(_sort_miss)
        # Rename identifier columns to Darwin Core casing for the output file.
        missing_fields_df = missing_fields_df.rename(columns=_ID_DWC)

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
        if pesquisadores_df is not None and 'táxons' in pesquisadores_df.columns and 'nome_completo' in pesquisadores_df.columns:
            pesq_lookup = pesquisadores_df.dropna(subset=['táxons']).copy()
            pesq_lookup['táxons'] = pesq_lookup['táxons'].astype(str).str.split(r'[;,]', regex=True)
            pesq_lookup = pesq_lookup.explode('táxons')
            pesq_lookup['táxons'] = pesq_lookup['táxons'].str.strip()
            pesq_lookup = pesq_lookup[pesq_lookup['táxons'] != '']
            pesq_map = (pesq_lookup.groupby('táxons')['nome_completo']
                                   .apply(lambda x: '; '.join(x.dropna().unique()))
                                   .to_dict())
        else:
            pesq_map = {}

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
        # Darwin Core casing for identifier/rank columns in the export.
        species_export = species_export.rename(columns={
            'taxonid':        'taxonID',
            'scientificname': 'scientificName',
            'taxonrank':      'taxonRank',
        })

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

        if not missing_fields_df.empty:
            miss_path = os.path.join(temp_dir, "campos_faltantes_por_especie.xlsx")
            missing_fields_df.to_excel(miss_path, index=False)
            generated_files.append(miss_path)

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
            # Include manuals
            if os.path.exists('manual_pt.pdf'):
                zf.write('manual_pt.pdf', 'manual_pt.pdf')
            if os.path.exists('manual_en.pdf'):
                zf.write('manual_en.pdf', 'manual_en.pdf')

        shutil.rmtree(temp_dir)

        summary = {
            'taxon':        taxon_filter,
            'n_spp_ctfb':   int(len(species_data)),
            'n_species':    int((species_data['taxonrank'].str.upper().str.strip() == 'SPECIES').sum()),
            'n_subsp':      int((species_data['taxonrank'].str.upper().str.strip() == 'SUBSPECIES').sum()),
            'mean_complete': round(float(species_data['completeness'].mean()), 1),
            'n_families':   int(species_data['family'].nunique())   if 'family'  in species_data.columns else 0,
            'n_orders':     int(species_data['order'].nunique())    if 'order'   in species_data.columns else 0,
            'n_classes':    int(species_data['class'].nunique())    if 'class'   in species_data.columns else 0,
        }
        return zip_filepath, summary, None
    except Exception as e:
        import sys as _sys, traceback as _tb
        _tb.print_exc(file=_sys.stderr)
        return None, None, f"exception: {e}"

# --- Language helpers ---
def tmpl(name):
    """Return template filename based on current session language."""
    if session.get('lang') == 'en':
        return f'{name}_en.html'
    return f'{name}.html'

# --- Data Dates helpers ---
def load_data_dates():
    try:
        with open(DATA_DATES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'planilha_extendida': '', 'pesquisadores': '', 'nota': ''}

def save_data_dates(dates: dict):
    os.makedirs(os.path.dirname(DATA_DATES_FILE), exist_ok=True)
    with open(DATA_DATES_FILE, 'w', encoding='utf-8') as f:
        json.dump(dates, f, ensure_ascii=False, indent=2)

# --- Daily data refresh scheduler ---
def refresh_all_data():
    """Re-download datasets (planilha from the Fauna API) and reload into memory.
    Invoked by the scheduler daily at 03:00 America/Sao_Paulo."""
    print("[SCHED] Daily data refresh starting...")
    try:
        with app.app_context():
            load_data_on_startup()
        print("[SCHED] Daily data refresh complete.")
    except Exception as e:
        print(f"[SCHED] Daily refresh FAILED: {e}")

def start_scheduler():
    if os.environ.get('ENABLE_SCHEDULER', '1') not in ('1', 'true', 'True'):
        print("[SCHED] Scheduler disabled via ENABLE_SCHEDULER.")
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from zoneinfo import ZoneInfo
        sched = BackgroundScheduler(timezone=ZoneInfo('America/Sao_Paulo'))
        sched.add_job(refresh_all_data, 'cron', hour=3, minute=0,
                      id='daily_data_refresh', replace_existing=True)
        sched.start()
        print("[SCHED] Scheduler started — daily refresh at 03:00 America/Sao_Paulo.")
    except Exception as e:
        print(f"[SCHED] Could not start scheduler: {e}")

# --- Flask Routes ---
_USING_POSTGRES = 'postgresql' in DATABASE_URL
# SQLite stored inside the data/ volume mount persists across redeploys too.
_DB_PERSISTENT = _USING_POSTGRES or os.path.dirname(_DEFAULT_DB_PATH) in DATABASE_URL
ANALYSIS_RESULTS = {}   # result_id → {zip_path, summary}
ANALYSIS_JOBS = {}      # job_id → {status, progress, pct, taxon_name, result_id, error}

def _analysis_worker(job_id, taxon_input, category, pesq_df, plan_df):
    """Run the Data Completeness analysis in a background thread so large taxa
    (e.g. Hexapoda) do not block the request and trip the worker timeout."""
    try:
        ANALYSIS_JOBS[job_id].update(progress='Processando dados…', pct=15)
        zip_path, summary, diag = run_python_analysis(
            taxon_input, pesq_df, plan_df, category=category)
        if zip_path and summary:
            result_id = uuid.uuid4().hex
            ANALYSIS_RESULTS[result_id] = {'zip_path': zip_path, 'summary': summary}
            ANALYSIS_JOBS[job_id].update(status='done', pct=100,
                                         progress='Concluído', result_id=result_id)
        else:
            ANALYSIS_JOBS[job_id].update(status='error',
                                         error=diag or 'Falha na análise.')
    except Exception as e:
        import traceback
        traceback.print_exc()
        ANALYSIS_JOBS[job_id].update(status='error', error=str(e))

with app.app_context():
    load_data_on_startup()
    if _USING_POSTGRES:
        print(f"[DB] Connected to PostgreSQL — data will persist across deployments.")
    elif _DB_PERSISTENT:
        print(f"[DB] Using SQLite on persistent volume ({DATABASE_URL}) — data persists across redeploys.")
    else:
        print(f"[DB] WARNING: Using SQLite ({DATABASE_URL}) — data WILL be lost on redeploy! "
              "Set DATABASE_URL or mount a volume at the data/ directory.")
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

# Start the daily 03:00 America/Sao_Paulo data refresh (single gunicorn worker).
start_scheduler()

@app.route('/lang/<code>')
def set_lang(code):
    if code in ('pt', 'en'):
        session['lang'] = code
    return redirect(request.referrer or url_for('index'))


@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    return render_template(tmpl('index'),
                           username=user.username,
                           is_admin=user.is_admin,
                           data_loaded=DATA_LOADED_SUCCESSFULLY,
                           allowed_taxa_list=current_allowed_taxa(),
                           data_dates=load_data_dates())

@app.route('/manual')
def manual():
    """Serve the user manual PDF matching the current session language."""
    fname = 'manual_en.pdf' if session.get('lang') == 'en' else 'manual_pt.pdf'
    path = os.path.join(os.path.dirname(__file__), fname)
    if not os.path.exists(path):
        # Fall back to the other language if one PDF is missing.
        alt = 'manual_pt.pdf' if fname == 'manual_en.pdf' else 'manual_en.pdf'
        path = os.path.join(os.path.dirname(__file__), alt)
        if not os.path.exists(path):
            return ('Manual not available.', 404)
    return send_file(path, mimetype='application/pdf')

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
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Credenciais inválidas.', 'danger')
    return render_template(tmpl('login'), data_dates=load_data_dates())

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
            flash('Senha definida com sucesso! Bem-vindo(a).', 'success')
            return redirect(url_for('index'))
    return render_template(tmpl('set_password'), username=user.username)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    """Self-service: a logged-in user changes their own password."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        current  = request.form.get('current', '')
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')
        if not user.check_password(current):
            flash('Senha atual incorreta.', 'danger')
        elif len(password) < 6:
            flash('A nova senha deve ter pelo menos 6 caracteres.', 'danger')
        elif password != confirm:
            flash('As senhas não coincidem.', 'danger')
        else:
            user.set_password(password)
            db.session.commit()
            flash('Senha alterada com sucesso.', 'success')
            return redirect(url_for('index'))
    return render_template(tmpl('change_password'),
                           username=user.username, is_admin=user.is_admin)

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

    taxon_input = request.form.get('taxon', '').strip()
    category = request.form.get('category', '').strip()
    if not taxon_input:
        flash("Taxon cannot be empty.", 'warning')
        return redirect(url_for('index'))

    # Run in the background so large taxa don't trip the request/worker timeout.
    job_id = uuid.uuid4().hex
    ANALYSIS_JOBS[job_id] = {'status': 'running', 'progress': 'Iniciando…',
                             'pct': 0, 'taxon_name': taxon_input}
    t = threading.Thread(target=_analysis_worker,
                         args=(job_id, taxon_input, category,
                               PESQUISADORES_DF, PLANILHA_DF.copy()),
                         daemon=True)
    t.start()
    return redirect(url_for('analysis_status', job_id=job_id))

@app.route('/analysis/status/<job_id>')
def analysis_status(job_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    job = ANALYSIS_JOBS.get(job_id)
    if job is None:
        flash('Análise não encontrada ou expirada.', 'danger')
        return redirect(url_for('index'))
    # Once finished, hand off to the existing result page.
    if job.get('status') == 'done' and job.get('result_id'):
        return redirect(url_for('analysis_result', result_id=job['result_id']))
    return render_template(tmpl('analysis_status'),
                           job=job, job_id=job_id,
                           username=user.username, is_admin=user.is_admin)

@app.route('/analysis/poll/<job_id>')
def analysis_poll(job_id):
    """JSON endpoint polled by the analysis status page."""
    from flask import jsonify
    job = ANALYSIS_JOBS.get(job_id, {'status': 'not_found'})
    return jsonify(job)

@app.route('/result/<result_id>')
def analysis_result(result_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    entry = ANALYSIS_RESULTS.get(result_id)
    if not entry:
        flash('Resultado não encontrado ou expirado.', 'danger')
        return redirect(url_for('index'))
    user = User.query.get(session['user_id'])
    return render_template(tmpl('analysis_result'),
                           summary=entry['summary'],
                           result_id=result_id,
                           username=user.username,
                           is_admin=user.is_admin,
                           data_dates=load_data_dates())

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
    return render_template(tmpl('admin'), users=users,
                           username=User.query.get(session['user_id']).username,
                           is_admin=True, using_postgres=_USING_POSTGRES,
                           db_persistent=_DB_PERSISTENT,
                           data_dates=load_data_dates())

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
                             ('planilha_extendida','planilha_extendida.csv')]:
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
    return render_template(tmpl('add_user'), username=current_user.username, is_admin=current_user.is_admin)

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
    return render_template(tmpl('import_users_csv'), username=current_user.username, is_admin=True)

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

@app.route('/admin/set_user_password/<int:user_id>', methods=['POST'])
def admin_set_user_password(user_id):
    """Admin action: set a specific new password for a user directly (no first-access flow)."""
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('index'))
    target = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password', '')
    if len(new_password) < 6:
        flash(f'A senha de "{target.username}" deve ter pelo menos 6 caracteres.', 'danger')
        return redirect(url_for('admin_dashboard'))
    target.set_password(new_password)   # also clears must_set_password
    db.session.commit()
    flash(f'Senha de "{target.username}" definida com sucesso.', 'success')
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
    return render_template(tmpl('bulk_add_users'),
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
        allowed = current_allowed_taxa()
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
    return render_template(tmpl('gbif_gap'),
                           username=user.username, is_admin=user.is_admin,
                           allowed_taxa=current_allowed_taxa(),
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
    return render_template(tmpl('gbif_gap_status'),
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
                     download_name=f'gbif_gap_{taxon_safe}.zip')

@app.route('/gbif_gap/poll/<job_id>')
def gbif_gap_poll(job_id):
    """JSON endpoint polled by the status page."""
    from flask import jsonify
    job = GBIF_JOBS.get(job_id, {'status': 'not_found'})
    return jsonify({k: v for k, v in job.items() if k != 'result_path'})

@app.route('/invasive_gap', methods=['GET', 'POST'])
def invasive_gap():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        taxon_name = request.form.get('taxon', '').strip()
        if not taxon_name:
            flash('Informe um táxon.', 'danger')
            return redirect(url_for('invasive_gap'))
        # Authorization: same rule as the main analysis
        allowed = current_allowed_taxa()
        if not user.is_admin and not is_taxon_authorized(taxon_name, allowed):
            flash(f'Táxon "{taxon_name}" não está autorizado para este usuário.', 'danger')
            return redirect(url_for('invasive_gap'))
        if PLANILHA_DF is None:
            flash('Dados CTFB não carregados — tente novamente mais tarde.', 'danger')
            return redirect(url_for('invasive_gap'))
        job_id = uuid.uuid4().hex
        t = threading.Thread(target=_invasive_gap_worker,
                             args=(job_id, taxon_name, PLANILHA_DF.copy()),
                             daemon=True)
        t.start()
        return redirect(url_for('invasive_gap_status', job_id=job_id))
    # Reuse gbif_gap template or create a new one
    return render_template(tmpl('invasive_gap'),
                           username=user.username, is_admin=user.is_admin,
                           data_loaded=DATA_LOADED_SUCCESSFULLY)

@app.route('/invasive_gap/status/<job_id>')
def invasive_gap_status(job_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    job = INVASIVE_JOBS.get(job_id)
    if job is None:
        flash('Job não encontrado.', 'danger')
        return redirect(url_for('invasive_gap'))
    return render_template(tmpl('invasive_gap_status'),
                           job=job, job_id=job_id,
                           username=user.username, is_admin=user.is_admin)

@app.route('/invasive_gap/download/<job_id>')
def invasive_gap_download(job_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    job = INVASIVE_JOBS.get(job_id)
    if not job or job['status'] != 'done' or not job.get('result_path'):
        flash('Resultado não disponível.', 'danger')
        return redirect(url_for('invasive_gap'))
    return send_file(job['result_path'], as_attachment=True,
                     download_name=f'invasive_gap_{job_id[:8]}.zip')

@app.route('/invasive_gap/poll/<job_id>')
def invasive_gap_poll(job_id):
    from flask import jsonify
    job = INVASIVE_JOBS.get(job_id, {'status': 'not_found'})
    return jsonify({k: v for k, v in job.items() if k != 'result_path'})

@app.route('/admin/update_ipt', methods=['POST'])
def admin_update_ipt():
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        return {"status": "error", "message": "Acesso negado"}, 403
    
    if IPT_UPDATE_JOB['status'] == 'running':
        flash('Uma atualização do IPT já está em andamento.', 'warning')
    else:
        thread = threading.Thread(target=process_ipt_archive)
        thread.start()
        flash('Atualização do IPT iniciada em segundo plano. Isso pode levar alguns minutos.', 'info')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/ipt_status')
def admin_ipt_status():
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        return {"status": "error", "message": "Acesso negado"}, 403
    from flask import jsonify
    return jsonify(IPT_UPDATE_JOB)

@app.route('/admin/download_ipt_combined')
def download_ipt_combined():
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('index'))
    if not os.path.exists(LOCAL_IPT_COMBINED):
        flash('Arquivo IPT combinado ainda não gerado.', 'warning')
        return redirect(url_for('admin_dashboard'))
    return send_file(LOCAL_IPT_COMBINED, as_attachment=True, download_name='ipt_combined.csv')

if __name__ == '__main__':
    app.run(debug=True)
