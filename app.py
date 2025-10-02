from flask import Flask, render_template, request, redirect, flash, session
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_session import Session
from flask import jsonify
from dotenv import load_dotenv
from flask import make_response
from flask import send_from_directory
from flask import Response
from flask_session import Session
import bcrypt
import os
import re


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config['UPLOAD_FOLDER'] = 'uploads'
Session(app)

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
# Admin credentials from environment (instead of hardcoded)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    
def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")

@app.route('/')
def index():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT type, path, caption FROM media")
        media_items = cur.fetchall()
        cur.close()
        conn.close()

        images = [item for item in media_items if item[0] == 'image']
        videos = [item for item in media_items if item[0] == 'video']
        
        return render_template('index.html', images=images, videos=videos)
    except Exception as e:
        return f"Error loading media: {e}"


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirmPassword']
        gender = request.form['gender']
        age = request.form['age']
        profession = request.form['profession']

        if not all([name, email, password, confirm_password, gender, age, profession]):
            flash("Please fill in all fields.", 'error')
            return render_template('register.html')

        if '@' not in email:
            flash("Email must contain '@'", 'error')
            return render_template('register.html')

        pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()?/.>,<\'";:\[\]{}\\|]).+$'
        if not re.match(pattern, password):
            flash("Password must contain a-z, A-Z, 0-9, and special symbols.", 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash("Passwords do not match.", 'error')
            return render_template('register.html')

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                flash("Email already exists.", 'error')
                cur.close()
                conn.close()
                return render_template('register.html')

            hashed_password = generate_password_hash(password)
            cur.execute("""
            INSERT INTO users (name, email, passwordhash, gender, age, profession, membership)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (name, email, hashed_password, gender, age, profession, 'Free'))

            conn.commit()
            cur.close()
            conn.close()

            flash("Registered successfully! Please log in.", "success")
            return redirect('/login')

        except Exception as e:
            flash("Internal server error: " + str(e), 'error')
            return render_template('register.html')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT userid, name, email, passwordhash, profession, membership
                FROM users
                WHERE email = %s
            """, (email,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if not row:
                flash("Email not registered.", "error")
                return render_template('login.html')

            userid, name, email_db, pw_hash, profession, membership = row
            if not check_password_hash(pw_hash, password):
                flash("Incorrect password.", "error")
                return render_template('login.html')

            session['user_id'] = userid
            session['user_name'] = name
            session['profession'] = profession
            session['membership'] = membership or 'Free'
            return redirect('/dashboard')
        except Exception as e:
            flash(f"Login failed: {e}", "error")
            return render_template('login.html')

    return render_template('login.html')

@app.route('/home')
def home():
    name = session.get('user_name', 'User')
    return render_template('home.html', name=name)

@app.route('/logout')
def logout():
    session.clear()  # Clear all session data
    flash("You have been logged out successfully.", "success")
    return redirect('/login')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # load user files
        cur.execute("""
            SELECT f.fileid, f.filename, f.folderid, fo.foldername
            FROM files f
            LEFT JOIN folders fo ON f.folderid = fo.folderid
            WHERE f.userid = %s
            ORDER BY f.fileid DESC
        """, (user_id,))
        files = cur.fetchall()
        documents = [{"id": r[0], "filename": r[1], "category": r[2], "category_name": r[3]} for r in files]

        # fetch membership from users (or subscriptions if you prefer)
        cur.execute("SELECT membership FROM users WHERE userid = %s", (user_id,))
        row = cur.fetchone()
        membership = row[0] if row and row[0] else 'Free'
        session['membership'] = membership

        cur.close()
        conn.close()

        return render_template('dashboard.html',
                               name=session.get('user_name'),
                               profession=session.get('profession'),
                               documents=documents,
                               latest_membership=membership)
    except Exception as e:
        return f"Dashboard error: {e}"



@app.route('/upload-document', methods=['POST'])
def upload_document():
    if 'user_id' not in session:
        return redirect('/login')

    # allow multiple files
    files = request.files.getlist('file')
    folder_id_raw = request.form.get('folder_id')  # optional
    folder_id = None
    try:
        if folder_id_raw:
            folder_id = int(folder_id_raw)
    except Exception:
        folder_id = None

    if not files or len(files) == 0 or files[0].filename == '':
        flash("No file selected", "error")
        return redirect('/dashboard')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                data = file.read()
                cur.execute("""
                    INSERT INTO files (userid, folderid, filename, attachment)
                    VALUES (%s, %s, %s, %s)
                """, (session['user_id'], folder_id, filename, psycopg2.Binary(data)))
        conn.commit()
        cur.close()
        conn.close()
        flash("Files uploaded", "success")
    except Exception as e:
        flash("Upload failed: " + str(e), "error")

    return redirect('/dashboard')
    

@app.route('/view-document/<int:doc_id>')
def view_document(doc_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT attachment, filename FROM files WHERE fileid = %s", (doc_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return "Not found", 404
        data, filename = row
        bytes_data = data.tobytes() if hasattr(data, 'tobytes') else data
        response = make_response(bytes_data)
        # infer content-type
        name_lower = (filename or '').lower()
        if name_lower.endswith('.pdf'):
            ctype = 'application/pdf'
        elif name_lower.endswith('.docx'):
            ctype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif name_lower.endswith('.doc'):
            ctype = 'application/msword'
        else:
            ctype = 'application/octet-stream'

        response.headers.set('Content-Type', ctype)
        response.headers.set('Content-Disposition', 'inline', filename=filename)
        return response
    except Exception as e:
        return f"Error displaying document: {e}", 500




@app.route('/delete-document/<int:doc_id>', methods=['GET', 'POST'])
def delete_document(doc_id):
    if 'user_id' not in session:
        return redirect('/login')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # ensure this belongs to user
        cur.execute("SELECT fileid FROM files WHERE fileid = %s AND userid = %s", (doc_id, session['user_id']))
        if cur.fetchone():
            cur.execute("DELETE FROM files WHERE fileid = %s AND userid = %s", (doc_id, session['user_id']))
            conn.commit()
            flash("Document deleted", "success")
        cur.close()
        conn.close()
    except Exception as e:
        flash("Delete failed: " + str(e), "error")
    return redirect('/dashboard')



@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip()
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # Email validation
        if '@' not in email:
            flash("Invalid email format", "error")
            return render_template('forgot_password.html')

        # Password validation
        pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()?\/.>,<\'";:\[\]{}\\|]).+$'
        if not re.match(pattern, new_password):
            flash("Password must contain a-z, A-Z, 0-9 and special symbols.", "error")
            return render_template('forgot_password.html')

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template('forgot_password.html')

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cur.fetchone()

            if not user:
                flash("Email is not registered.", "error")
                return render_template('forgot_password.html')

            hashed_pw = generate_password_hash(new_password)
            cur.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_pw, email))
            conn.commit()
            cur.close()
            conn.close()

            flash("Password has been reset successfully. Please log in.", "success")
            return redirect('/login')

        except Exception as e:
            flash(f"Error: {str(e)}", "error")
            return render_template('forgot_password.html')

    return render_template('forgot_password.html')


@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # Prefer DB-based admin if present
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT adminid, userid, username, passwordhash FROM admindatabase WHERE username = %s", (username,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                adminid, userid, uname, pw_hash = row
                if check_password_hash(pw_hash, password):
                    session['admin_logged_in'] = True
                    session['admin_userid'] = userid
                    return redirect('/admin')
                else:
                    flash("Invalid admin credentials", "error")
                    return render_template('admin_login.html')
            else:
                # fallback to env vars
                if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                    session['admin_logged_in'] = True
                    return redirect('/admin')
                else:
                    flash("Invalid admin credentials", "error")
                    return render_template('admin_login.html')
        except Exception as e:
            flash("Admin login failed: " + str(e), "error")
            return render_template('admin_login.html')
    return render_template('admin_login.html')
    

@app.route('/admin')
def admin():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    return render_template('admin.html')
    

@app.route('/admin/users')
def admin_users():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, email, gender, age, profession FROM users")
        users = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('admin_users.html', users=users)
    except Exception as e:
        flash(f"Error loading user data: {e}", "error")
        return render_template('admin_users.html', users=[])


@app.route('/admin/delete/<int:user_id>')
def delete_user(user_id):
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("User deleted successfully", "success")
    except Exception as e:
        flash(f"Failed to delete user: {e}", "error")
    return redirect('/admin')


@app.route('/membership')
def membership():
    if 'user_id' not in session:
        return redirect('/login')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT planid, code, name, pricecents, currency, features FROM plans ORDER BY planid")
        plans = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        plans = []
    return render_template('payment.html', plans=plans)





@app.route('/select_plan', methods=['POST'])
def select_plan():
    if 'user_id' not in session:
        return redirect('/login')
    plan_id = request.form.get('plan_id')
    if not plan_id:
        flash("No plan selected", "error")
        return redirect('/membership')
    session['selected_plan_id'] = int(plan_id)
    return redirect('/payment')



@app.route('/payment')
def payment_page():
    if 'user_id' not in session:
        return redirect('/login')
    plan_id = session.get('selected_plan_id')
    if not plan_id:
        return redirect('/membership')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT planid, code, name, pricecents, currency FROM plans WHERE planid = %s", (plan_id,))
        plan = cur.fetchone()
        cur.close()
        conn.close()
    except Exception:
        plan = None
    return render_template('payment.html', plan=plan)


@app.route('/payment_success', methods=['POST'])
def payment_success():
    if 'user_name' not in session:
        return redirect('/login')

    selected_plan = session.get('selected_plan')
    name = session.get('user_name')

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Get user ID
        cur.execute("SELECT id, email, profession FROM users WHERE name = %s", (name,))
        user_data = cur.fetchone()

        if not user_data:
            return "User not found"

        user_id, email, profession = user_data

        # Insert membership (no file upload)
        cur.execute("""
            INSERT INTO userdocuments (user_id, name, email, profession, membership)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, name, email, profession, selected_plan))

        conn.commit()
        cur.close()
        conn.close()
        session['membership'] = selected_plan

        return redirect('/dashboard')
    except Exception as e:
        return f"Error during payment: {e}"



@app.route('/payment_process', methods=['POST'])
def payment_process():
    if 'user_id' not in session:
        return redirect('/login')
    selected_plan_id = session.get('selected_plan_id')
    if not selected_plan_id:
        return redirect('/membership')

    # Card details (example; in production use a payment gateway)
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    card_number = request.form.get('card_number', '').replace(' ', '')
    card_expiry = request.form.get('card_expiry', '')  # expecting MM/YY or MM/YYYY
    card_cvv = request.form.get('card_cvv', '')

    if not all([first_name, last_name, card_number, card_expiry, card_cvv]):
        flash("All card fields required", "error")
        return redirect('/payment')

    # parse expiry
    try:
        parts = card_expiry.split('/')
        exp_month = int(parts[0])
        exp_year = int(parts[1]) if len(parts[1]) == 4 else 2000 + int(parts[1])
    except Exception:
        flash("Invalid expiry format", "error")
        return redirect('/payment')

    # get plan
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT planid, name, pricecents, currency FROM plans WHERE planid = %s", (selected_plan_id,))
        plan = cur.fetchone()
        if not plan:
            flash("Plan not found", "error")
            cur.close(); conn.close()
            return redirect('/membership')

        planid, plan_name, pricecents, currency = plan

        # Insert subscription
        now = datetime.utcnow()
        period_end = now + timedelta(days=30)
        cur.execute("""
            INSERT INTO subscriptions (userid, planid, status, currentperiodstart, currentperiodend)
            VALUES (%s, %s, %s, %s, %s) RETURNING subscriptionid
        """, (session['user_id'], planid, 'active', now, period_end))
        subscriptionid = cur.fetchone()[0]

        # Insert payment method (store last4 only, do NOT store raw card)
        last4 = card_number[-4:]
        provider = 'card'
        brand = request.form.get('card_brand') or 'Card'
        # Create a simple token placeholder (in prod you'd use Stripe/PayPal)
        token = bcrypt.hashpw((card_number + str(datetime.utcnow())).encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        cur.execute("""
            INSERT INTO paymentmethods (userid, provider, brand, last4, expmonth, expyear, providerpaymentmethodid)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING paymentmethodid
        """, (session['user_id'], provider, brand, last4, exp_month, exp_year, token))
        paymentmethodid = cur.fetchone()[0]

        # Insert a payment record
        cur.execute("""
            INSERT INTO payments (userid, subscriptionid, paymentmethodid, amountcents, currency, status, membershipsnapshot)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (session['user_id'], subscriptionid, paymentmethodid, pricecents, currency, 'succeeded', plan_name))

        # Optionally update users.membership for quick UI
        cur.execute("UPDATE users SET membership = %s WHERE userid = %s", (plan_name, session['user_id']))

        conn.commit()
        cur.close()
        conn.close()

        session['membership'] = plan_name
        flash("Payment successful. Membership activated.", "success")
        return redirect('/dashboard')
    except Exception as e:
        flash("Payment processing failed: " + str(e), "error")
        return redirect('/payment')


@app.route('/pay', methods=['POST'])
def pay():
    if 'user_name' not in session:
        return redirect('/login')

    membership_plan = session.get('selected_plan', 'Free')
    user_name = session['user_name']

    conn = get_db_connection()
    cur = conn.cursor()

    # Get user ID
    cur.execute("SELECT id FROM users WHERE name = %s", (user_name,))
    user_id = cur.fetchone()[0]

    # Check if entry already exists
    cur.execute("SELECT * FROM userdocuments WHERE user_id = %s", (user_id,))
    existing = cur.fetchone()

    if existing:
        cur.execute("UPDATE userdocuments SET membership = %s WHERE user_id = %s", (membership_plan, user_id))
    else:
        cur.execute("""
            INSERT INTO userdocuments (user_id, name, email, profession, membership)
            SELECT id, name, email, profession, %s FROM users WHERE id = %s
        """, (membership_plan, user_id))

    conn.commit()
    cur.close()
    conn.close()

    session['membership'] = membership_plan
    
    return redirect('/dashboard')

@app.context_processor
def inject_membership():
    return {'membership': session.get('membership', 'Free')}


@app.context_processor
def inject_membership():
    membership = session.get('membership')
    # If session doesn't have it but user is logged in, fetch latest from DB
    if not membership and 'user_name' in session:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT membership
                FROM userdocuments
                WHERE user_id = (SELECT id FROM users WHERE name = %s)
                ORDER BY id DESC
                LIMIT 1
            """, (session['user_name'],))
            row = cur.fetchone()
            cur.close()
            conn.close()
            membership = row[0] if row and row[0] else 'Free'
            session['membership'] = membership  # cache it
        except Exception:
            membership = 'Free'
    return {'membership': membership or 'Free'}


@app.route('/admin/templates')
def manage_templates():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT summarytemplateid, templatename, category, promptinstructions, createdby
            FROM uploadsummarytemplates
            ORDER BY summarytemplateid DESC
        """)
        templates = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('template_management.html', templates=templates)
    except Exception as e:
        return f"Error loading templates: {e}"



@app.route('/create_template', methods=['POST'])
def create_template():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    name = request.form.get('template_name')
    prompt = request.form.get('template_prompt')
    category = request.form.get('template_category') or None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO uploadsummarytemplates (templatename, promptinstructions, category, createdby)
            VALUES (%s, %s, %s, %s)
        """, (name, prompt, category, session.get('user_id')))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/admin/templates')
    except Exception as e:
        return f"Error creating template: {e}"



@app.route('/edit_template/<int:id>', methods=['POST'])
def edit_template(id):
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    name = request.form.get('edit_template_name')
    prompt = request.form.get('edit_template_prompt')
    category = request.form.get('edit_template_category') or None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE uploadsummarytemplates
            SET templatename = %s, promptinstructions = %s, category = %s
            WHERE summarytemplateid = %s
        """, (name, prompt, category, id))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/admin/templates')
    except Exception as e:
        return f"Error editing template: {e}"
        



@app.route('/delete_template/<int:id>', methods=['POST'])
def delete_template(id):
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM uploadsummarytemplates WHERE summarytemplateid = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/admin/templates')
    except Exception as e:
        return f"Error deleting template: {e}"



@app.route('/get-documents', methods=['GET'])
def get_documents():
    if 'user_id' not in session:
        return jsonify([])
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT f.fileid, f.filename, f.folderid, fo.foldername
            FROM files f
            LEFT JOIN folders fo ON f.folderid = fo.folderid
            WHERE f.userid = %s AND f.filename IS NOT NULL
            ORDER BY f.fileid DESC
        """, (session['user_id'],))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        docs = [
            {"id": r[0], "filename": r[1], "category": r[2], "category_name": r[3]}
            for r in rows if r[1]
        ]
        return jsonify(docs)
    except Exception as e:
        return jsonify([])


@app.route('/add_category', methods=['POST'])
def add_category():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"success": False, "error": "Invalid name"}), 400
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO folders (userid, foldername) VALUES (%s, %s) RETURNING folderid",
                    (session['user_id'], name))
        folderid = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True, "id": folderid, "name": name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/update-document-category', methods=['POST'])
def update_document_category():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    try:
        data = request.get_json()
        document_id = data.get('documentId')
        category = data.get('category')  # may be None or 'all' or folder id
        if not document_id:
            return jsonify({"success": False, "error": "Missing documentId"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        if category in [None, 'all', 'null', 'None']:
            cur.execute("UPDATE files SET folderid = NULL WHERE fileid = %s AND userid = %s", (document_id, session['user_id']))
        else:
            try:
                folderid = int(category)
                cur.execute("UPDATE files SET folderid = %s WHERE fileid = %s AND userid = %s", (folderid, document_id, session['user_id']))
            except Exception:
                return jsonify({"success": False, "error": "Invalid folder id"}), 400
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



@app.route('/get_categories', methods=['GET'])
def get_categories():
    if 'user_id' not in session:
        return jsonify([])
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT folderid, foldername FROM folders WHERE userid = %s ORDER BY folderid DESC",
                    (session['user_id'],))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        cats = [{"id": r[0], "name": r[1]} for r in rows]
        return jsonify(cats)
    except Exception as e:
        return jsonify([])
        

@app.route('/delete_category/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # only delete if owner
        cur.execute("UPDATE files SET folderid = NULL WHERE folderid = %s AND userid = %s", (category_id, session['user_id']))
        cur.execute("DELETE FROM folders WHERE folderid = %s AND userid = %s", (category_id, session['user_id']))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if 'user_id' not in session:
        return redirect('/login')
    if request.method == 'POST':
        name = request.form.get('name')
        profession = request.form.get('profession')
        feedback_type = request.form.get('feedback_type')
        feedback_text = request.form.get('feedback_text')
        rating = request.form.get('rating')
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO userfeedback (userid, name, profession, feedbacktype, comment, rating)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (session['user_id'], name, profession, feedback_type, feedback_text, rating))
            conn.commit()
            cur.close()
            conn.close()
            flash("Thanks for your feedback!", "success")
            return redirect('/dashboard')
        except Exception as e:
            flash("Feedback save failed: " + str(e), "error")
            return render_template('feedback.html')
    return render_template('feedback.html')


if __name__ == '__main__':
    app.run(debug=True)


















































