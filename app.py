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
        PESQUISADORES_DF = pd.read_excel(BytesIO(pesquisadores_content), header=None, names=['username', 'taxons', 'institution'])
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

def generate_completeness_histograms(dataframe, category_column, value_column, title_prefix, output_path):
    """
    Generates histograms for completeness values (mean, min, max, amplitude) for each item in a category
    and saves them to a single PDF file.
    """
    if dataframe.empty:
        print(f"No data to generate histograms for {title_prefix}.")
        return

    with PdfPages(output_path) as pdf:
        # Plotting mean completeness
        fig, ax = plt.subplots(figsize=(10, 6))
        dataframe.set_index(category_column)['mean_complete'].plot(kind='bar', ax=ax, color='skyblue')
        ax.set_title(f'{title_prefix} - Média de Completude')
        ax.set_ylabel('Média de Completude (%)')
        ax.set_xlabel(category_column.capitalize())
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # Plotting amplitude
        fig, ax = plt.subplots(figsize=(10, 6))
        dataframe.set_index(category_column)['amplitude'].plot(kind='bar', ax=ax, color='lightcoral')
        ax.set_title(f'{title_prefix} - Amplitude de Completude')
        ax.set_ylabel('Amplitude (%)')
        ax.set_xlabel(category_column.capitalize())
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # Plotting min completeness
        fig, ax = plt.subplots(figsize=(10, 6))
        dataframe.set_index(category_column)['min_complete'].plot(kind='bar', ax=ax, color='lightgreen')
        ax.set_title(f'{title_prefix} - Completude Mínima')
        ax.set_ylabel('Completude Mínima (%)')
        ax.set_xlabel(category_column.capitalize())
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # Plotting max completeness
        fig, ax = plt.subplots(figsize=(10, 6))
        dataframe.set_index(category_column)['max_complete'].plot(kind='bar', ax=ax, color='gold')
        ax.set_title(f'{title_prefix} - Completude Máxima')
        ax.set_ylabel('Completude Máxima (%)')
        ax.set_xlabel(category_column.capitalize())
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

# --- Python-based Analysis Function (omitted for brevity, no changes needed) ---
def run_python_analysis(taxon_filter, pesquisadores_df, planilha_df):
    try:
        # ... (rest of the function is unchanged)
        taxonomic_ranks = ['phylum', 'class', 'order', 'family', 'genus', 'scientificname']
        mask = False
        for rank in taxonomic_ranks:
            if rank in planilha_df.columns:
                mask |= (planilha_df[rank].str.lower() == taxon_filter.lower())
        filtered_data = planilha_df[mask].copy()
        if filtered_data.empty: return None
        species_data = filtered_data[filtered_data['taxonrank'].isin(['ESPECIE', 'SUBESPECIE'])].copy()
        if species_data.empty: return None
        MANUAL_COLS = ["bibliographicreference", "country", "establishmentmeans", "endemicbrazil", "environment", "locality", "epicontinentaldomain", "marinedomain", "lifeform", "habitat", "vernacularname", "vernacularnamelanguage", "vernacularnamelocality", "animalhostnames", "vegetalhostnames"]
        manual_present = [col for col in MANUAL_COLS if col in species_data.columns]
        def is_filled(series): return series.notna() & (series.astype(str).str.strip() != '')
        filled_matrix = species_data[manual_present].apply(is_filled)
        remove_marine = species_data['environment'].str.lower().str.strip() == "epicontinental"
        remove_animal = species_data['lifeform'].str.lower().str.strip() == "herbivoro"
        species_data['filled_count'] = filled_matrix.sum(axis=1)
        species_data['total_applicable'] = len(manual_present)
        if 'marinedomain' in manual_present: species_data.loc[remove_marine, 'total_applicable'] -= 1
        if 'animalhostnames' in manual_present: species_data.loc[remove_animal, 'total_applicable'] -= 1
        species_data['completeness'] = (species_data['filled_count'] / species_data['total_applicable']) * 100
        def most_common_val(x):
            x = x.dropna()[x != ""]
            if x.empty: return np.nan
            return x.mode().iloc[0]
        agg_funcs = {'n_species': ('scientificname', 'count'), 'mean_complete': ('completeness', 'mean'), 'min_complete': ('completeness', 'min'), 'max_complete': ('completeness', 'max')}
        def aggregate_by(level):
            hierarchy = ['phylum', 'class', 'order', 'family', 'genus']
            if level not in hierarchy: hierarchy.append(level)
            group_cols = [col for col in hierarchy if col in species_data.columns and col not in [level]]
            agg_dict = agg_funcs.copy()
            for col in group_cols: agg_dict[col] = (col, most_common_val)
            df = species_data.groupby(level).agg(**agg_dict).reset_index()
            df['amplitude'] = df['max_complete'] - df['min_complete']
            return df.round(2)
        by_family = aggregate_by('family'); by_order = aggregate_by('order'); by_class = aggregate_by('class'); by_subclass = aggregate_by('subclass'); by_phylum = aggregate_by('phylum')
        pesq_lookup = pesquisadores_df.dropna(subset=['taxons']).copy()
        pesq_lookup['taxons'] = pesq_lookup['taxons'].str.split('[;,]')
        pesq_lookup = pesq_lookup.explode('taxons')
        pesq_lookup['taxons'] = pesq_lookup['taxons'].str.strip()
        pesq_map = pesq_lookup.groupby('taxons')['username'].apply(lambda x: '; '.join(x.unique())).to_dict()
        def find_researcher(row, ranks):
            for rank in ranks:
                if rank in row and row[rank] in pesq_map: return pesq_map[row[rank]]
            return np.nan
        by_family['pesquisador'] = by_family.apply(find_researcher, ranks=['family', 'order', 'class', 'phylum'], axis=1)
        by_order['pesquisador'] = by_order.apply(find_researcher, ranks=['order', 'class', 'phylum'], axis=1)
        by_class['pesquisador'] = by_class.apply(find_researcher, ranks=['class', 'phylum'], axis=1)
        by_subclass['pesquisador'] = by_subclass.apply(find_researcher, ranks=['subclass', 'class', 'phylum'], axis=1)
        by_phylum['pesquisador'] = by_phylum['phylum'].map(pesq_map)
        
        temp_dir = os.path.join(app.root_path, 'temp_analysis_output', taxon_filter.replace(" ", "_") + "_" + str(os.getpid()))
        os.makedirs(temp_dir, exist_ok=True)

        # List to store paths of all generated files (XLSX and PDF)
        generated_files = []

        # Save dataframes to XLSX
        by_family_path = os.path.join(temp_dir, "completeness_by_family.xlsx")
        by_family.to_excel(by_family_path, index=False)
        generated_files.append(by_family_path)

        by_order_path = os.path.join(temp_dir, "completeness_by_order.xlsx")
        by_order.to_excel(by_order_path, index=False)
        generated_files.append(by_order_path)

        by_class_path = os.path.join(temp_dir, "completeness_by_class.xlsx")
        by_class.to_excel(by_class_path, index=False)
        generated_files.append(by_class_path)

        by_subclass_path = os.path.join(temp_dir, "completeness_by_subclass.xlsx")
        by_subclass.to_excel(by_subclass_path, index=False)
        generated_files.append(by_subclass_path)

        by_phylum_path = os.path.join(temp_dir, "completeness_by_phylum.xlsx")
        by_phylum.to_excel(by_phylum_path, index=False)
        generated_files.append(by_phylum_path)

        species_data_path = os.path.join(temp_dir, "completeness_per_species.xlsx")
        species_data.to_excel(species_data_path, index=False)
        generated_files.append(species_data_path)

        # Generate and save histograms as PDFs
        pdf_family_path = os.path.join(temp_dir, "completeness_histograms_family.pdf")
        generate_completeness_histograms(by_family, 'family', 'amplitude', 'Completude por Família', pdf_family_path)
        generated_files.append(pdf_family_path)

        pdf_order_path = os.path.join(temp_dir, "completeness_histograms_order.pdf")
        generate_completeness_histograms(by_order, 'order', 'amplitude', 'Completude por Ordem', pdf_order_path)
        generated_files.append(pdf_order_path)

        pdf_class_path = os.path.join(temp_dir, "completeness_histograms_class.pdf")
        generate_completeness_histograms(by_class, 'class', 'amplitude', 'Completude por Classe', pdf_class_path)
        generated_files.append(pdf_class_path)

        pdf_subclass_path = os.path.join(temp_dir, "completeness_histograms_subclass.pdf")
        generate_completeness_histograms(by_subclass, 'subclass', 'amplitude', 'Completude por Subclasse', pdf_subclass_path)
        generated_files.append(pdf_subclass_path)

        pdf_phylum_path = os.path.join(temp_dir, "completeness_histograms_phylum.pdf")
        generate_completeness_histograms(by_phylum, 'phylum', 'amplitude', 'Completude por Filo', pdf_phylum_path)
        generated_files.append(pdf_phylum_path)

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
                user_data = PESQUISADORES_DF[PESQUISADORES_DF['username'].str.lower() == user.username.lower()]
                if not user_data.empty:
                    taxa_str = user_data.iloc[0]['taxons']
                    session['allowed_taxa'] = sorted([t.strip().lower() for t in taxa_str.split(',')] if isinstance(taxa_str, str) else [])
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
        flash(f"Taxon '{taxon_input}' is not allowed for analysis.', 'danger')
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
