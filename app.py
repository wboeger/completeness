from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import pandas as pd
import subprocess
import json
import zipfile
import shutil
import datetime # For timestamping user creation

app = Flask(__name__)
app.secret_key = os.urandom(24) # Secret key for session management

# --- Configuration ---
# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Use relative paths based on the application's root directory
PESQUISADORES_EXCEL_PATH = os.path.join(app.root_path, "data", "pesquisadores.xlsx")
PLANILHA_EXTENDIDA_PATH = os.path.join(app.root_path, "data", "planilha_extendida.xlsx")
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

    def __repr__(self):
        return f'<User {self.username}>'

# --- Data Loading and Caching ---
TAXON_HIERARCHY = {}
PESQUISADORES_DF = None

def load_data_on_startup():
    """
    Loads the taxonomic hierarchy and researcher data into global variables
    to be used for authorization.
    """
    global TAXON_HIERARCHY, PESQUISADORES_DF
    try:
        # Load researcher data
        PESQUISADORES_DF = pd.read_excel(PESQUISADORES_EXCEL_PATH, header=None, names=['username', 'taxons', 'institution'])
        print(f"Loaded {len(PESQUISADORES_DF)} researchers.")

        # Load taxon hierarchy from the main data sheet
        df_taxons = pd.read_excel(PLANILHA_EXTENDIDA_PATH)
        taxonomic_ranks = ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'scientificname']
        
        # Drop rows where high-level ranks are missing
        df_taxons.dropna(subset=taxonomic_ranks[:-1], inplace=True)

        for rank_index in range(len(taxonomic_ranks) - 1):
            parent_rank = taxonomic_ranks[rank_index]
            child_rank = taxonomic_ranks[rank_index + 1]
            
            for _, row in df_taxons[[child_rank, parent_rank]].iterrows():
                child_name = str(row[child_rank]).strip().lower()
                parent_name = str(row[parent_rank]).strip().lower()
                if child_name and parent_name and child_name != 'nan' and parent_name != 'nan':
                    # Only add to hierarchy if the child doesn't already have a (potentially more specific) parent
                    if child_name not in TAXON_HIERARCHY:
                        TAXON_HIERARCHY[child_name] = parent_name
        
        print(f"Built taxon hierarchy with {len(TAXON_HIERARCHY)} relationships.")

    except FileNotFoundError as e:
        print(f"FATAL: Could not find data file: {e}. The application may not function correctly.")
    except Exception as e:
        print(f"FATAL: An error occurred during data loading: {e}")


# Load data when the application starts
with app.app_context():
    load_data_on_startup()
    db.create_all() # Create database tables if they don't exist

    # Create a default admin user if none exists
    if User.query.filter_by(username='admin').first() is None:
        admin_user = User(username='admin', is_admin=True)
        admin_user.set_password('adminpass') # Default admin password
        db.session.add(admin_user)
        db.session.commit()
        print("Default admin user 'admin' created with password 'adminpass'.")

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    # The number of allowed taxa is now user-specific
    allowed_taxa_count = len(session.get('allowed_taxa', []))
    return render_template('index.html', username=user.username, allowed_taxa_count=allowed_taxa_count, is_admin=user.is_admin)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            
            # --- New User-Specific Taxa Loading ---
            if PESQUISADORES_DF is not None:
                user_data = PESQUISADORES_DF[PESQUISADORES_DF['username'].str.lower() == username.lower()]
                if not user_data.empty:
                    taxa_str = user_data.iloc[0]['taxons']
                    if isinstance(taxa_str, str):
                        allowed_taxa = [t.strip().lower() for t in taxa_str.split(',')]
                        session['allowed_taxa'] = allowed_taxa
                    else:
                        session['allowed_taxa'] = []
                else:
                    session['allowed_taxa'] = []
            # --- End New Logic ---

            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'danger')
            return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('allowed_taxa', None) # Clear user-specific taxa on logout
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

def is_taxon_authorized(requested_taxon, user_allowed_taxa):
    """
    Checks if a user is authorized to analyze a given taxon.
    This includes checking for subordinate relationships.
    """
    if not user_allowed_taxa:
        return False

    current_taxon = requested_taxon.strip().lower()

    # 1. Direct match
    if current_taxon in user_allowed_taxa:
        return True

    # 2. Hierarchical (subordinate) match
    # Traverse up the hierarchy from the requested taxon
    while current_taxon in TAXON_HIERARCHY:
        parent_taxon = TAXON_HIERARCHY[current_taxon]
        if parent_taxon in user_allowed_taxa:
            return True
        if parent_taxon == current_taxon: # Avoid infinite loops
            break
        current_taxon = parent_taxon
        
    return False

@app.route('/analyze', methods=['POST'])
def analyze_taxon():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])

    taxon_input = request.form['taxon'].strip()
    if not taxon_input:
        flash("Taxon cannot be empty.", 'warning')
        return redirect(url_for('index'))

    # --- Authorization Check with Admin Override ---
    is_authorized = False
    if user.is_admin:
        is_authorized = True
    else:
        user_allowed_taxa = session.get('allowed_taxa', [])
        is_authorized = is_taxon_authorized(taxon_input, user_allowed_taxa)
    
    if not is_authorized:
        flash(f"Taxon '{taxon_input}' is not allowed for analysis.", 'danger')
        return redirect(url_for('index'))
    # --- End Authorization Check ---

    result_zip_path = run_analysis_script(taxon_input)

    if result_zip_path:
        return send_file(result_zip_path, as_attachment=True, download_name=f"{taxon_input.replace(' ', '_')}_analysis_results.zip")
    else:
        flash(f"Analysis failed for '{taxon_input}'. Check server logs.", 'danger')
        return redirect(url_for('index'))


@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user.is_admin:
        flash('Access denied: Administrators only.', 'danger')
        return redirect(url_for('index'))
    
    users = User.query.all()
    return render_template('admin.html', users=users, username=user.username, is_admin=user.is_admin)

@app.route('/admin/add_user', methods=['GET', 'POST'])
def add_user():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user.is_admin:
        flash('Access denied: Administrators only.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        is_admin = 'is_admin' in request.form

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
        else:
            new_user = User(username=username, is_admin=is_admin)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash(f'User {username} created successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
    
    return render_template('add_user.html', username=user.username, is_admin=user.is_admin)

def run_analysis_script(taxon):
    """
    Runs the completeness_analysis.R script for the given taxon and zips the results.
    Returns the path to the zip file or None if an error occurs.
    """
    r_script_path = os.path.join(app.root_path, 'completeness_analysis.R')
    
    # Create a temporary directory for this analysis run's output
    temp_output_dir = os.path.join(app.root_path, 'temp_analysis_output', taxon.replace(" ", "_") + "_" + str(os.getpid()))
    os.makedirs(temp_output_dir, exist_ok=True)

    # Create a 'data' subdirectory inside the temp_output_dir for the R script
    # to find the Excel files. Copy the Excel files there.
    temp_data_dir = os.path.join(temp_output_dir, 'data')
    os.makedirs(temp_data_dir, exist_ok=True)
    
    try:
        shutil.copy(PESQUISADORES_EXCEL_PATH, temp_data_dir)
        shutil.copy(PLANILHA_EXTENDIDA_PATH, temp_data_dir)
    except FileNotFoundError as e:
        print(f"Error copying data files: {e}")
        shutil.rmtree(temp_output_dir)
        return None
    except Exception as e:
        print(f"Unexpected error copying data files: {e}")
        shutil.rmtree(temp_output_dir)
        return None

    # Command to run the R script
    # Rscript <script_path> <output_directory> <taxon_filter>
    command = ["Rscript", r_script_path, temp_output_dir, taxon]

    try:
        print(f"Running R script for taxon: {taxon} with command: ", ' '.join(command))
        result = subprocess.run(command, check=True, capture_output=True, text=True, cwd=app.root_path)
        print(f"R script stdout for {taxon}:
{result.stdout}")
        if result.stderr:
            print(f"R script stderr for {taxon}:
{result.stderr}")

        # Zip the contents of the temporary output directory
        zip_filename = f"{taxon.replace(' ', '_')}_analysis_results.zip"
        zip_filepath = os.path.join(app.root_path, 'temp_zips', zip_filename)
        os.makedirs(os.path.dirname(zip_filepath), exist_ok=True)

        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(temp_output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Add file to zip, preserving directory structure relative to temp_output_dir
                    zipf.write(file_path, os.path.relpath(file_path, temp_output_dir))
        
        print(f"Analysis results for {taxon} zipped to {zip_filepath}")
        return zip_filepath

    except subprocess.CalledProcessError as e:
        print(f"Error running R script for {taxon}: {e}")
        print(f"R script stdout: {e.stdout}")
        print(f"R script stderr: {e.stderr}")
        return None
    except FileNotFoundError:
        print("Error: Rscript command not found. Is R installed and in PATH?")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during R script execution or zipping: {e}")
        return None
    finally:
        # Clean up the temporary output directory
        if os.path.exists(temp_output_dir):
            shutil.rmtree(temp_output_dir)
            print(f"Cleaned up temporary directory: {temp_output_dir}")


if __name__ == '__main__':
    app.run(debug=True)
