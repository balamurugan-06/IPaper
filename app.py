from flask import Flask, render_template, request, redirect, flash, session
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_session import Session
from dotenv import load_dotenv
from flask import make_response
from flask import send_from_directory
from flask import Response
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
        cur.execute("SELECT id, profession FROM users WHERE name = %s", (name,))
        user = cur.fetchone()
        user_id, profession = user[0], user[1]

        cur.execute("SELECT id, document FROM UserDocuments WHERE user_id = %s", (user_id,))
        documents = cur.fetchall()
        cur.close()
        conn.close()

        return render_template('dashboard.html', name=name, profession=profession, documents=documents)
    except Exception as e:
        return f"Dashboard Error: {e}"

@app.route('/upload-document', methods=['POST'])
def upload_document():
    if 'user_name' not in session:
        return redirect('/login')

    file = request.files['file']
    if file and allowed_file(file.filename):
        file_data = file.read()
        filename = secure_filename(file.filename)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, email, profession FROM users WHERE name = %s", (session['user_name'],))
        user = cur.fetchone()
        user_id, email, profession = user

        cur.execute("""
            INSERT INTO UserDocuments (user_id, name, email, profession, document, file_data)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, session['user_name'], email, profession, filename, psycopg2.Binary(file_data)))
        conn.commit()
        cur.close()
        conn.close()

    return redirect('/dashboard')



@app.route('/view-document/<int:doc_id>')
def view_document(doc_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT file_data, document FROM UserDocuments WHERE id = %s", (doc_id,))
        result = cur.fetchone()
        cur.close()
        conn.close()

        if result:
            file_data, filename = result
            # Convert memoryview to bytes
            pdf_bytes = bytes(file_data)

            response = make_response(pdf_bytes)
            response.headers.set('Content-Type', 'application/pdf')
            response.headers.set('Content-Disposition', 'inline', filename=filename)
            return response
        else:
            return "Document not found", 404

    except Exception as e:
        return f"Error displaying document: {e}", 500




@app.route('/delete-document/<int:doc_id>')
def delete_document(doc_id):
    if 'user_name' not in session:
        return redirect('/login')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT document FROM UserDocuments WHERE id = %s", (doc_id,))
        result = cur.fetchone()
        if result:
            filename = result[0]
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(filepath):
                os.remove(filepath)

        cur.execute("DELETE FROM UserDocuments WHERE id = %s", (doc_id,))
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
            flash("Invalid admin credentials", "error")
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

if __name__ == '__main__':
    app.run(debug=True)


