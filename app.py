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
            cur.execute("INSERT INTO users (name, email, password, gender, age, profession) VALUES (%s, %s, %s, %s, %s, %s)",
                        (name, email, hashed_password, gender, age, profession))
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
        email = request.form['email']
        password = request.form['password']

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            cur.close()
            conn.close()

            if not user:
                flash("Email is not registered.", 'error')
                return render_template('login.html')

            if not check_password_hash(user[3], password):
                flash("Type in the correct password.", 'error')
                return render_template('login.html')

            session['user_name'] = user[1]
            session['user_id'] = user[0] 
            session['profession'] = user[6]
            
            return redirect('/dashboard')


        except Exception as e:
            flash("Login failed: " + str(e), 'error')
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
    if 'user_name' not in session:
        return redirect('/login')

    name = session.get('user_name')
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Get user ID and profession
        cur.execute("SELECT id, profession FROM users WHERE name = %s", (name,))
        user = cur.fetchone()
        if not user:
            flash("User not found")
            return redirect('/login')

        user_id, profession = user
        session['profession'] = profession

        # Get latest membership
        cur.execute("""
            SELECT membership FROM userdocuments 
            WHERE user_id = %s AND membership IS NOT NULL
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        membership_record = cur.fetchone()
        latest_membership = membership_record[0] if membership_record and membership_record[0] else "Free"

        # Get user documents
        cur.execute("SELECT id, document FROM userdocuments WHERE user_id = %s AND document IS NOT NULL", (user_id,))
        documents = cur.fetchall()

        # Save membership in session
        session['membership'] = latest_membership

        cur.close()
        conn.close()

        print("DEBUG: latest_membership =", latest_membership)
        return render_template(
            'dashboard.html',
            name=name,
            profession=profession,
            documents=documents,
            latest_membership=latest_membership
        )
    except Exception as e:
        return f"Dashboard Error: {e}"


@app.route('/upload-document', methods=['POST'])
def upload_document():
    if 'user_name' not in session:
        return redirect('/login')

    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_data = file.read()

        conn = get_db_connection()
        cur = conn.cursor()

        # Get user info
        cur.execute("SELECT id, email, profession FROM users WHERE name = %s", (session['user_name'],))
        user = cur.fetchone()
        if not user:
            raise Exception("User not found")
        user_id, email, profession = user

        # Create large object (LOB)
        lo_oid = conn.lobject(0, 'wb').oid  # create new large object
        lo = conn.lobject(lo_oid, 'wb')
        lo.write(file_data)
        lo.close()

        # Store OID in the table
        cur.execute("""
            INSERT INTO userdocuments (user_id, name, email, profession, file_oid, document)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, session['user_name'], email, profession, lo_oid, filename))

        conn.commit()
        cur.close()
        conn.close()

    return redirect('/dashboard')




@app.route('/view-document/<int:doc_id>')
def view_document(doc_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT file_oid, document FROM userdocuments WHERE id = %s", (doc_id,))
        result = cur.fetchone()
        cur.close()
        conn.close()

        if not result or result[0] is None:
            return "Document not found", 404

        file_oid, filename = result

        conn = get_db_connection()
        lo = conn.lobject(file_oid, 'rb')
        file_data = lo.read()
        lo.close()
        conn.close()

        response = make_response(file_data)
        response.headers.set('Content-Type', 'application/pdf')
        response.headers.set('Content-Disposition', 'inline', filename=filename)
        return response

    except Exception as e:
        return f"Error displaying document: {e}", 500





@app.route('/delete-document/<int:doc_id>')
def delete_document(doc_id):
    if 'user_name' not in session:
        return redirect('/login')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT document FROM userdocuments WHERE id = %s", (doc_id,))
        result = cur.fetchone()
        if result:
            filename = result[0]
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(filepath):
                os.remove(filepath)

        cur.execute("DELETE FROM userdocuments WHERE id = %s", (doc_id,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        flash("Error deleting document: " + str(e), "error")

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
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect('/admin')
        else:
            error = 'Invalid username or password.'
            return render_template('admin_login.html')
    return render_template('admin_login.html')

@app.route('/admin')
def admin():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    return render_template('admin.html', users=[])  # Only show buttons, not users yet


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
    if 'user_name' not in session:
        return redirect('/login')
    return render_template("payment.html")





@app.route('/select_plan', methods=['POST'])
def select_plan():
    if 'user_name' not in session:
        return redirect('/login')

    plan = request.form.get('plan')
    if not plan:
        return "No plan selected", 400

    profession = session.get('profession', '')
    
    # Block Ultra from downgrading
    if profession == 'Ultra' and plan == 'Pro':
        flash("As a Ultra, you cannot subscribe to the Pro plan.", "error")
        return redirect('/membership')

    session['selected_plan'] = plan
    return redirect('/payment')




@app.route('/payment')
def payment():
    if 'user_id' not in session:
        return redirect('/login')
    if 'selected_plan' not in session:
        return redirect('/membership')  

    plan = session['selected_plan']
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
    selected_plan = request.form.get('selected_plan')
    if 'user_name' not in session or not selected_plan:
        return redirect('/login')

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Get user details
        cur.execute("SELECT id, email, profession FROM users WHERE name = %s", (session['user_name'],))
        user = cur.fetchone()
        user_id, email, profession = user

        # Only allow valid plan values
        if selected_plan not in ['Pro', 'Ultra']:
            return redirect('/membership')

        # Check for existing membership
        cur.execute("SELECT id FROM userdocuments WHERE user_id = %s", (user_id,))
        existing_doc = cur.fetchone()

        if existing_doc:
            cur.execute("""
                UPDATE userdocuments 
                SET membership = %s 
                WHERE user_id = %s
            """, (selected_plan, user_id))
        else:
            cur.execute("""
                INSERT INTO userdocuments (user_id, name, email, profession, membership)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, session['user_name'], email, profession, selected_plan))

        # ✅ Insert card details in SAME connection
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        card_number = request.form.get('card_number')
        card_expiry = request.form.get('card_expiry')
        card_cvv = request.form.get('card_cvv')

        if not all([first_name, last_name, card_number, card_expiry, card_cvv]):
            flash("All card fields are required", "error")
            return redirect('/membership')

        hashed_card_number = bcrypt.hashpw(card_number.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        hashed_card_expiry = bcrypt.hashpw(card_expiry.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        hashed_card_cvv = bcrypt.hashpw(card_cvv.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        cur.execute("""
            INSERT INTO CardDetails (user_id, first_name, last_name, card_number, card_expiry, card_cvv)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            first_name,
            last_name,
            hashed_card_number,
            hashed_card_expiry,
            hashed_card_cvv
        ))

        # ✅ Commit once after both inserts/updates
        conn.commit()

        # Close connection
        cur.close()
        conn.close()

        # Update session
        session['membership'] = selected_plan
        return render_template("payment_success.html", selected_plan=selected_plan)

    except Exception as e:
        return f"Payment processing failed: {e}"



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
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM UserTemplate ORDER BY id DESC")
        templates = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('template_management.html', templates=templates)
    except Exception as e:
        return f"Error loading templates: {e}"



@app.route('/create_template', methods=['POST'])
def create_template():
    name = request.form.get('template_name')
    prompt = request.form.get('template_prompt')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO UserTemplate (template_name, template_prompt) VALUES (%s, %s)", (name, prompt))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/admin/templates')
    except Exception as e:
        return f"Error creating template: {e}"


@app.route('/edit_template/<int:id>', methods=['POST'])
def edit_template(id):
    name = request.form.get('edit_template_name')
    prompt = request.form.get('edit_template_prompt')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE UserTemplate SET template_name = %s, template_prompt = %s WHERE id = %s", (name, prompt, id))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/admin/templates')
    except Exception as e:
        return f"Error editing template: {e}"



@app.route('/delete_template/<int:id>', methods=['POST'])
def delete_template(id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM UserTemplate WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/admin/templates')
    except Exception as e:
        return f"Error deleting template: {e}"

@app.route('/get-documents', methods=['GET'])
def get_documents():
    if 'user_name' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cur = conn.cursor()

    # Fetch user ID
    cur.execute("SELECT id FROM users WHERE name = %s", (session['user_name'],))
    user = cur.fetchone()
    if not user:
        cur.close()
        conn.close()
        return jsonify([])

    user_id = user[0]
    cur.execute("SELECT id, document FROM userdocuments WHERE user_id = %s", (user_id,))
    docs = [{"id": row[0], "filename": row[1]} for row in cur.fetchall()]

    cur.close()
    conn.close()
    return jsonify(docs)


# Add category
@app.route("/add_category", methods=["POST"])
def add_category():
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Not logged in"}), 401

    data = request.get_json()
    category_name = data.get("name")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO usercategories (user_id, name) VALUES (%s, %s) RETURNING id",
                (session["user_id"], category_name))
    category_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    return jsonify({"success": True, "id": category_id, "name": category_name})


@app.route("/update-document-category", methods=["POST"])
def update_document_category():
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Not logged in"}), 401

    try:
        data = request.get_json()
        document_id = data.get("documentId")
        category = data.get("category")  # can be None

        if not document_id:
            return jsonify({"success": False, "error": "Missing documentId"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        # Update document's category
        cur.execute("""
            UPDATE userdocuments
            SET category = %s
            WHERE id = %s AND user_id = %s
        """, (category, document_id, session["user_id"]))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if 'user_name' not in session:
        return redirect('/login')

    if request.method == 'POST':
        name = request.form.get("name")
        profession = request.form.get("profession")
        feedback_type = request.form.get("feedback_type")
        feedback_text = request.form.get("feedback_text")
        rating = request.form.get("rating")

        try:
            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute("SELECT id FROM users WHERE name = %s", (session['user_name'],))
            user = cur.fetchone()
            user_id = user[0] if user else None

            cur.execute("""
                INSERT INTO feedback (user_id, user_name, profession, feedback_type, feedback_text, rating)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, name, profession, feedback_type, feedback_text, rating))

            conn.commit()
            cur.close()
            conn.close()

            flash("✅ Thank you for your feedback!", "success")
            return redirect('/dashboard')

        except Exception as e:
            flash(f"Error saving feedback: {e}", "error")
            return render_template("feedback.html")

    return render_template("feedback.html")


if __name__ == '__main__':
    app.run(debug=True)


































