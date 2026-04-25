from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
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
        species_data = filtered_data[rank_mask & status_mask].copy()
        if species_data.empty:
            return None

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

        # --- Ecological exclusion vectors (regras.txt Section 5) ---
        if 'environment' in species_data.columns:
            remove_marine = species_data['environment'].str.lower().str.strip() == "epicontinental"
        else:
            remove_marine = pd.Series(False, index=species_data.index)

        if 'lifeform' in species_data.columns:
            remove_animal = species_data['lifeform'].str.lower().str.strip() == "herbivoro"
        else:
            remove_animal = pd.Series(False, index=species_data.index)

        # --- Adjust BOTH numerator and denominator (critical fix) ---
        # R: filled_count -= as.integer(remove_marine & filled_matrix[, marine_idx])
        filled_count = filled_matrix.sum(axis=1)
        if 'marinedomain' in manual_present:
            filled_count = filled_count - (remove_marine & filled_matrix['marinedomain']).astype(int)
        if 'animalhostnames' in manual_present:
            filled_count = filled_count - (remove_animal & filled_matrix['animalhostnames']).astype(int)

        species_data['filled_count'] = filled_count.values
        species_data['total_applicable'] = len(manual_present)
        if 'marinedomain' in manual_present:
            species_data.loc[remove_marine, 'total_applicable'] -= 1
        if 'animalhostnames' in manual_present:
            species_data.loc[remove_animal, 'total_applicable'] -= 1
        species_data['completeness'] = (species_data['filled_count'] / species_data['total_applicable']) * 100

        # --- Aggregation helpers ---
        def most_common_val(x):
            x = x.dropna()
            x = x[x.astype(str).str.strip() != '']
            return x.mode().iloc[0] if not x.empty else np.nan

        # Context (parent) columns per level — mirrors R script exactly
        HIERARCHY_CONTEXT = {
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
                'n_species':     ('taxonrank', 'count'),   # taxonrank always filled → equiv. to R's n()
                'mean_complete': ('completeness', 'mean'),
                'min_complete':  ('completeness', 'min'),
                'max_complete':  ('completeness', 'max'),
            })
            df = species_data.dropna(subset=[level]).groupby(level).agg(**agg_dict).reset_index()
            df['amplitude'] = df['max_complete'] - df['min_complete']
            sort_cols = [c for c in context_cols + [level] if c in df.columns]
            return df.sort_values(sort_cols).round(2)

        # Only aggregate ranks strictly finer than the input taxon's rank
        by_family   = aggregate_by('family')   if is_below_input_rank('family')   else pd.DataFrame()
        by_order    = aggregate_by('order')    if is_below_input_rank('order')    else pd.DataFrame()
        by_class    = aggregate_by('class')    if is_below_input_rank('class')    else pd.DataFrame()
        by_subclass = aggregate_by('subclass') if is_below_input_rank('subclass') else pd.DataFrame()
        by_phylum   = aggregate_by('phylum')   if is_below_input_rank('phylum')   else pd.DataFrame()

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
            'family':   ['phylum', 'class', 'order', 'family',   'n_species', 'mean_complete', 'min_complete', 'max_complete', 'amplitude', 'pesquisador', 'max_flag'],
            'order':    ['phylum', 'class', 'order',             'n_species', 'mean_complete', 'min_complete', 'max_complete', 'amplitude', 'pesquisador', 'max_flag'],
            'class':    ['phylum', 'class',                      'n_species', 'mean_complete', 'min_complete', 'max_complete', 'amplitude', 'pesquisador', 'max_flag'],
            'subclass': ['phylum', 'class', 'subclass',          'n_species', 'mean_complete', 'min_complete', 'max_complete', 'amplitude', 'pesquisador', 'max_flag'],
            'phylum':   ['phylum',                               'n_species', 'mean_complete', 'min_complete', 'max_complete', 'amplitude', 'pesquisador', 'max_flag'],
        }

        def reorder(df, level, sort_cols):
            df = top_first(df, sort_cols)
            cols = [c for c in COL_ORDER[level] if c in df.columns]
            return df[cols]

        by_family_out   = reorder(by_family,   'family',   ['phylum', 'class', 'order', 'family']) if not by_family.empty   else pd.DataFrame()
        by_order_out    = reorder(by_order,    'order',    ['phylum', 'class', 'order'])           if not by_order.empty    else pd.DataFrame()
        by_class_out    = reorder(by_class,    'class',    ['phylum', 'class'])                    if not by_class.empty    else pd.DataFrame()
        by_subclass_out = reorder(by_subclass, 'subclass', ['phylum', 'class', 'subclass'])        if not by_subclass.empty else pd.DataFrame()
        by_phylum_out   = reorder(by_phylum,   'phylum',   ['phylum'])                             if not by_phylum.empty   else pd.DataFrame()

        # --- Species export: selected columns + pesquisador with subclass fallback ---
        species_cols = ['taxonid', 'scientificname', 'phylum', 'class', 'subclass', 'order',
                        'family', 'taxonrank', 'completeness', 'filled_count', 'total_applicable']
        species_export = species_data[[c for c in species_cols if c in species_data.columns]].copy()
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
        return zip_filepath
    except Exception as e:
        print(f"An error occurred during Python analysis: {e}")
        import traceback
        traceback.print_exc()
        return None

# --- Flask Routes ---
_USING_POSTGRES = 'postgresql' in DATABASE_URL

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

    result_zip_path = run_python_analysis(taxon_input, PESQUISADORES_DF, PLANILHA_DF)

    if result_zip_path:
        return send_file(result_zip_path, as_attachment=True)
    else:
        flash(f"Analysis failed for '{taxon_input}'. Check server logs for details.", 'danger')
        return redirect(url_for('index'))

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        flash('Access denied: Administrators only.', 'danger')
        return redirect(url_for('index'))
    users = User.query.all()
    return render_template('admin.html', users=users,
                           username=User.query.get(session['user_id']).username,
                           is_admin=True, using_postgres=_USING_POSTGRES)

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

if __name__ == '__main__':
    app.run(debug=True)
