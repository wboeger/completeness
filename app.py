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

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- Configuration ---
# Database configuration for production (e.g., Railway) or local development
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///users.db')
# Heroku/Railway use postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Google Sheets URLs ---
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

def download_gsheet(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"FATAL: Could not download Google Sheet from {url}. Error: {e}")
        return None

def load_data_on_startup():
    global TAXON_HIERARCHY, PESQUISADORES_DF, PLANILHA_DF
    
    pesquisadores_content = download_gsheet(PESQUISADORES_SHEET_URL)
    if pesquisadores_content:
        PESQUISADORES_DF = pd.read_excel(BytesIO(pesquisadores_content), header=None, names=['username', 'taxons', 'institution'])
        print(f"Loaded {len(PESQUISADORES_DF)} researchers from Google Sheet.")

    planilha_content = download_gsheet(PLANILHA_EXTENDIDA_SHEET_URL)
    if planilha_content:
        PLANILHA_DF = pd.read_excel(BytesIO(planilha_content))
        print(f"Loaded {len(PLANILHA_DF)} records from main data sheet.")
        
        taxonomic_ranks = ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'scientificname']
        df_taxons = PLANILHA_DF.dropna(subset=taxonomic_ranks[:-1]).copy()

        for rank_index in range(len(taxonomic_ranks) - 1):
            parent_rank = taxonomic_ranks[rank_index]
            child_rank = taxonomic_ranks[rank_index + 1]
            
            for _, row in df_taxons[[child_rank, parent_rank]].iterrows():
                child_name = str(row[child_rank]).strip().lower()
                parent_name = str(row[parent_rank]).strip().lower()
                if child_name and parent_name and child_name != 'nan' and parent_name != 'nan':
                    if child_name not in TAXON_HIERARCHY:
                        TAXON_HIERARCHY[child_name] = parent_name
        
        print(f"Built taxon hierarchy with {len(TAXON_HIERARCHY)} relationships.")

# --- Python-based Analysis Function ---
def run_python_analysis(taxon_filter, pesquisadores_df, planilha_df):
    try:
        # 1. Filter data based on the input taxon
        taxonomic_ranks = ['phylum', 'class', 'order', 'family', 'genus', 'scientificname']
        
        # Create a boolean mask for filtering
        mask = False
        for rank in taxonomic_ranks:
            # Ensure column exists and handle potential errors
            if rank in planilha_df.columns:
                mask |= (planilha_df[rank].str.lower() == taxon_filter.lower())
        
        filtered_data = planilha_df[mask].copy()

        if filtered_data.empty:
            print(f"No data found for taxon filter: {taxon_filter}")
            return None

        # 2. Filter for species-level records
        species_data = filtered_data[filtered_data['taxonrank'].isin(['ESPECIE', 'SUBESPECIE'])].copy()
        if species_data.empty:
            print(f"No species-level data found for taxon filter: {taxon_filter}")
            return None

        # 3. Calculate per-species completeness
        MANUAL_COLS = [
            "bibliographicreference", "country", "establishmentmeans", "endemicbrazil", 
            "environment", "locality", "epicontinentaldomain", "marinedomain", "lifeform", 
            "habitat", "vernacularname", "vernacularnamelanguage", "vernacularnamelocality", 
            "animalhostnames", "vegetalhostnames"
        ]
        manual_present = [col for col in MANUAL_COLS if col in species_data.columns]

        def is_filled(series):
            return series.notna() & (series.astype(str).str.strip() != '')

        filled_matrix = species_data[manual_present].apply(is_filled)
        
        remove_marine = species_data['environment'].str.lower().str.strip() == "epicontinental"
        remove_animal = species_data['lifeform'].str.lower().str.strip() == "herbivoro"

        species_data['filled_count'] = filled_matrix.sum(axis=1)
        species_data['total_applicable'] = len(manual_present)
        
        if 'marinedomain' in manual_present:
            species_data.loc[remove_marine, 'total_applicable'] -= 1
        if 'animalhostnames' in manual_present:
            species_data.loc[remove_animal, 'total_applicable'] -= 1

        species_data['completeness'] = (species_data['filled_count'] / species_data['total_applicable']) * 100

        # 4. Aggregate by taxonomic levels
        def most_common_val(x):
            x = x.dropna()[x != ""]
            if x.empty: return np.nan
            return x.mode().iloc[0]

        agg_funcs = {
            'n_species': ('scientificname', 'count'),
            'mean_complete': ('completeness', 'mean'),
            'min_complete': ('completeness', 'min'),
            'max_complete': ('completeness', 'max'),
        }

        def aggregate_by(level):
            hierarchy = ['phylum', 'class', 'order', 'family', 'genus']
            if level not in hierarchy: hierarchy.append(level)
            
            group_cols = [col for col in hierarchy if col in species_data.columns and col not in [level]]
            
            agg_dict = agg_funcs.copy()
            for col in group_cols:
                agg_dict[col] = (col, most_common_val)

            df = species_data.groupby(level).agg(**agg_dict).reset_index()
            df['amplitude'] = df['max_complete'] - df['min_complete']
            return df.round(2)

        by_family = aggregate_by('family')
        by_order = aggregate_by('order')
        by_class = aggregate_by('class')
        by_subclass = aggregate_by('subclass')
        by_phylum = aggregate_by('phylum')

        # 5. Add researcher names
        pesq_lookup = pesquisadores_df.dropna(subset=['taxons']).copy()
        pesq_lookup['taxons'] = pesq_lookup['taxons'].str.split('[;,]')
        pesq_lookup = pesq_lookup.explode('taxons')
        pesq_lookup['taxons'] = pesq_lookup['taxons'].str.strip()
        pesq_map = pesq_lookup.groupby('taxons')['username'].apply(lambda x: '; '.join(x.unique())).to_dict()

        def find_researcher(row, ranks):
            for rank in ranks:
                if rank in row and row[rank] in pesq_map:
                    return pesq_map[row[rank]]
            return np.nan
        
        by_family['pesquisador'] = by_family.apply(find_researcher, ranks=['family', 'order', 'class', 'phylum'], axis=1)
        by_order['pesquisador'] = by_order.apply(find_researcher, ranks=['order', 'class', 'phylum'], axis=1)
        by_class['pesquisador'] = by_class.apply(find_researcher, ranks=['class', 'phylum'], axis=1)
        by_subclass['pesquisador'] = by_subclass.apply(find_researcher, ranks=['subclass', 'class', 'phylum'], axis=1)
        by_phylum['pesquisador'] = by_phylum['phylum'].map(pesq_map)

        # 6. Save to CSV and Zip
        temp_dir = os.path.join(app.root_path, 'temp_analysis_output', taxon_filter.replace(" ", "_") + "_" + str(os.getpid()))
        os.makedirs(temp_dir, exist_ok=True)

        by_family.to_csv(os.path.join(temp_dir, "completeness_by_family.csv"), index=False)
        by_order.to_csv(os.path.join(temp_dir, "completeness_by_order.csv"), index=False)
        by_class.to_csv(os.path.join(temp_dir, "completeness_by_class.csv"), index=False)
        by_subclass.to_csv(os.path.join(temp_dir, "completeness_by_subclass.csv"), index=False)
        by_phylum.to_csv(os.path.join(temp_dir, "completeness_by_phylum.csv"), index=False)
        species_data.to_csv(os.path.join(temp_dir, "completeness_per_species.csv"), index=False)

        zip_filename = f"{taxon_filter.replace(' ', '_')}_analysis_results.zip"
        zip_filepath = os.path.join(app.root_path, 'temp_zips', zip_filename)
        os.makedirs(os.path.dirname(zip_filepath), exist_ok=True)
        
        shutil.make_archive(zip_filepath.replace('.zip', ''), 'zip', temp_dir)
        
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
    return render_template('index.html', username=user.username, allowed_taxa_count=len(session.get('allowed_taxa', [])), is_admin=user.is_admin)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            session['user_id'] = user.id
            if PESQUISADORES_DF is not None:
                user_data = PESQUISADORES_DF[PESQUISADORES_DF['username'].str.lower() == user.username.lower()]
                if not user_data.empty:
                    taxa_str = user_data.iloc[0]['taxons']
                    session['allowed_taxa'] = [t.strip().lower() for t in taxa_str.split(',')] if isinstance(taxa_str, str) else []
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
    user = User.query.get(session['user_id'])
    taxon_input = request.form['taxon'].strip()
    if not taxon_input:
        flash("Taxon cannot be empty.", 'warning')
        return redirect(url_for('index'))

    if not user.is_admin and not is_taxon_authorized(taxon_input, session.get('allowed_taxa', [])):
        flash(f"Taxon '{taxon_input}' is not allowed for analysis.", 'danger')
        return redirect(url_for('index'))

    # Call the new Python analysis function
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
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username already exists.', 'danger')
        else:
            new_user = User(username=request.form['username'], is_admin='is_admin' in request.form)
            new_user.set_password(request.form['password'])
            db.session.add(new_user)
            db.session.commit()
            flash(f"User {new_user.username} created successfully!", 'success')
            return redirect(url_for('admin_dashboard'))
    return render_template('add_user.html', username=User.query.get(session['user_id']).username, is_admin=True)

if __name__ == '__main__':
    app.run(debug=True)
