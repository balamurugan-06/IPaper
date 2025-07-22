from flask import Flask, render_template, request, redirect, flash, session
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from flask_session import Session
from dotenv import load_dotenv
import os
import re

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Admin credentials from environment (instead of hardcoded)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

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
            return redirect('/home')

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


