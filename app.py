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
app.secret_key = os.urandom(24)

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
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
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

def load_data_on_startup():
    global TAXON_HIERARCHY, PESQUISADORES_DF, PLANILHA_DF, DATA_LOADED_SUCCESSFULLY
    
    pesquisadores_content = download_gsheet(PESQUISADORES_SHEET_URL)
    if pesquisadores_content:
        PESQUISADORES_DF = pd.read_excel(BytesIO(pesquisadores_content), header=0)
        PESQUISADORES_DF.columns = [c.lower().strip() for c in PESQUISADORES_DF.columns]
        print(f"Loaded {len(PESQUISADORES_DF)} researchers from Google Sheet.")

    planilha_content = download_gsheet(PLANILHA_EXTENDIDA_SHEET_URL)
    if planilha_content:
        PLANILHA_DF = pd.read_excel(BytesIO(planilha_content))
        print(f"Loaded {len(PLANILHA_DF)} records from main data sheet.")
        PLANILHA_DF.columns = [col.lower().strip() for col in PLANILHA_DF.columns]
        
        taxonomic_ranks = ['phylum', 'class', 'order', 'family', 'genus', 'scientificname']
        valid_ranks = [rank for rank in taxonomic_ranks if rank in PLANILHA_DF.columns]
        df_taxons = PLANILHA_DF.dropna(subset=valid_ranks[:-1]).copy()

        for rank_index in range(len(valid_ranks) - 1):
            parent_rank = valid_ranks[rank_index]
            child_rank = valid_ranks[rank_index + 1]
            
            for _, row in df_taxons[[child_rank, parent_rank]].iterrows():
                child_name = str(row[child_rank]).strip().lower()
                parent_name = str(row[parent_rank]).strip().lower()
                if child_name and parent_name and child_name != 'nan' and parent_name != 'nan':
                    if child_name not in TAXON_HIERARCHY:
                        TAXON_HIERARCHY[child_name] = parent_name
        
        print(f"Built taxon hierarchy with {len(TAXON_HIERARCHY)} relationships.")

    if PESQUISADORES_DF is not None and PLANILHA_DF is not None:
        DATA_LOADED_SUCCESSFULLY = True
        print("Data loading successful.")
    else:
        print("Data loading failed.")

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
        # --- Filter rows matching the requested taxon across all rank columns ---
        taxonomic_ranks = ['phylum', 'class', 'order', 'family', 'genus', 'scientificname']
        mask = pd.Series(False, index=planilha_df.index)
        for rank in taxonomic_ranks:
            if rank in planilha_df.columns:
                mask |= (planilha_df[rank].str.lower() == taxon_filter.lower())
        filtered_data = planilha_df[mask].copy()
        if filtered_data.empty:
            return None

        species_data = filtered_data[filtered_data['taxonrank'].isin(['ESPECIE', 'SUBESPECIE'])].copy()
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

        by_family   = aggregate_by('family')
        by_order    = aggregate_by('order')
        by_class    = aggregate_by('class')
        by_subclass = aggregate_by('subclass')
        by_phylum   = aggregate_by('phylum')

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

        def find_researcher(row, parent_ranks):
            """Return nome_completo of the researcher responsible for the
            immediately superior taxonomic category (parent_ranks[0]), with
            cascade fallback to higher ranks if not found."""
            for i, rank in enumerate(parent_ranks):
                val = row.get(rank, np.nan)
                if pd.notna(val) and str(val).strip() and str(val) in pesq_map:
                    name = pesq_map[str(val)]
                    return name if i == 0 else f"{name} (via {rank})"
            return np.nan

        # Lookup: same level first, then immediately superior, then cascade up
        by_family['pesquisador']   = by_family.apply(find_researcher,   parent_ranks=['family', 'order', 'class', 'phylum'], axis=1)
        by_order['pesquisador']    = by_order.apply(find_researcher,    parent_ranks=['order', 'class', 'phylum'], axis=1)
        by_class['pesquisador']    = by_class.apply(find_researcher,    parent_ranks=['class', 'phylum'], axis=1)
        by_subclass['pesquisador'] = by_subclass.apply(find_researcher, parent_ranks=['subclass', 'class', 'phylum'], axis=1)
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

        by_family_out   = reorder(by_family,   'family',   ['phylum', 'class', 'order', 'family'])
        by_order_out    = reorder(by_order,    'order',    ['phylum', 'class', 'order'])
        by_class_out    = reorder(by_class,    'class',    ['phylum', 'class'])
        by_subclass_out = reorder(by_subclass, 'subclass', ['phylum', 'class', 'subclass'])
        by_phylum_out   = reorder(by_phylum,   'phylum',   ['phylum'])

        # --- Species export: selected columns + pesquisador with subclass fallback ---
        species_cols = ['taxonid', 'scientificname', 'phylum', 'class', 'subclass', 'order',
                        'family', 'taxonrank', 'completeness', 'filled_count', 'total_applicable']
        species_export = species_data[[c for c in species_cols if c in species_data.columns]].copy()
        # Species: same level (family) first, then immediately superior (order), then cascade
        species_export['pesquisador'] = species_export.apply(
            find_researcher, parent_ranks=['family', 'order', 'subclass', 'class', 'phylum'], axis=1
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
with app.app_context():
    load_data_on_startup()
    db.create_all()
    if User.query.filter_by(username='admin').first() is None:
        db.session.add(User(username='admin', is_admin=True, password_hash=generate_password_hash('adminpass')))
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
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            session['user_id'] = user.id
            if PESQUISADORES_DF is not None:
                user_data = PESQUISADORES_DF[PESQUISADORES_DF['login'].str.lower() == user.username.lower()]
                if not user_data.empty:
                    taxa_str = user_data.iloc[0]['táxons']
                    import re as _re
                    session['allowed_taxa'] = sorted([t.strip().lower() for t in _re.split(r'[;,]', taxa_str)] if isinstance(taxa_str, str) else [])
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('login.html')

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
    return render_template('admin.html', users=users, username=User.query.get(session['user_id']).username, is_admin=True)

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

if __name__ == '__main__':
    app.run(debug=True)
