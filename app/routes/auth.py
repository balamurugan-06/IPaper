"""
IPaper Authentication Routes

Handles user registration, login, logout,
and password recovery.
"""

import re

from flask import (
     Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from app.services.database import (
    get_db_connection,
    release_db_connection
)


auth_bp = Blueprint(
    "auth",
    __name__
)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        name = request.form['name']
        email = request.form['email'].strip().lower()
        password = request.form['password']
        confirm_password = request.form['confirmPassword']
        gender = request.form['gender']
        age = request.form['age']
        profession = request.form['profession']

        if not all([
            name,
            email,
            password,
            confirm_password,
            gender,
            age,
            profession
        ]):
            flash("Please fill in all fields.", 'error')
            return render_template('register.html')

        if '@' not in email:
            flash("Email must contain '@'", 'error')
            return render_template('register.html')

        if len(password) < 8 or len(password) > 12:
            flash(
                "Password must be 8–12 characters long.",
                'error'
            )
            return render_template('register.html')

        pattern = (
            r'^(?=.*[a-z])'
            r'(?=.*[A-Z])'
            r'(?=.*\d)'
            r'(?=.*[!@#$%^&*()?/.>,<\'";:\[\]{}\\|])'
            r'.+$'
        )

        if not re.match(pattern, password):
            flash(
                "Password must contain a-z, A-Z, 0-9, "
                "and special symbols.",
                'error'
            )
            return render_template('register.html')

        if password != confirm_password:
            flash("Passwords do not match.", 'error')
            return render_template('register.html')

        conn = None
        cur = None

        try:

            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            if cur.fetchone():

                flash(
                    "Email already exists.",
                    'error'
                )

                return render_template(
                    'register.html'
                )

            hashed_password = generate_password_hash(
                password
            )

            cur.execute(
                """
                INSERT INTO users
                (
                    name,
                    email,
                    passwordhash,
                    gender,
                    age,
                    profession,
                    membership
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    name,
                    email,
                    hashed_password,
                    gender,
                    age,
                    profession,
                    'Free'
                )
            )

            conn.commit()

            flash(
                "Registered successfully! Please log in.",
                "success"
            )

            return redirect('/login')

        except Exception as e:

            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass

            flash(
                "Internal server error: " + str(e),
                'error'
            )

            return render_template(
                'register.html'
            )

        finally:

            if cur:
                cur.close()

            if conn:
                release_db_connection(conn)

    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form.get(
            'email',
            ''
        ).strip().lower()

        password = request.form.get(
            'password',
            ''
        )

        conn = None
        cur = None

        try:

            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute(
                """
                SELECT
                    userid,
                    name,
                    email,
                    passwordhash,
                    profession,
                    membership
                FROM users
                WHERE email = %s
                """,
                (email,)
            )

            row = cur.fetchone()

            if not row:

                flash(
                    "Email not registered.",
                    "error"
                )

                return render_template(
                    'login.html'
                )

            (
                userid,
                name,
                email_db,
                pw_hash,
                profession,
                membership
            ) = row

            if not check_password_hash(
                pw_hash,
                password
            ):

                flash(
                    "Incorrect password.",
                    "error"
                )

                return render_template(
                    'login.html'
                )

            session['user_id'] = userid
            session['user_name'] = name
            session['profession'] = profession
            session['membership'] = (
                membership or 'Free'
            )

            return redirect('/dashboard')

        except Exception as e:

            flash(
                f"Login failed: {e}",
                "error"
            )

            return render_template(
                'login.html'
            )

        finally:

            if cur:
                cur.close()

            if conn:
                release_db_connection(conn)

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():

    session.clear()

    flash(
        "You have been logged out successfully.",
        "success"
    )

    return redirect('/login')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():

    if request.method == 'POST':

        email = request.form['email'].strip()
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # -----------------------------------------------------
        # 1. Email validation
        # -----------------------------------------------------

        if '@' not in email:

            flash(
                "Invalid email format",
                "error"
            )

            return render_template(
                'forgot_password.html'
            )

        # -----------------------------------------------------
        # 2. Password validation
        # -----------------------------------------------------

        pattern = (
            r'^(?=.*[a-z])'
            r'(?=.*[A-Z])'
            r'(?=.*\d)'
            r'(?=.*[!@#$%^&*()?/.>,<\'";:\[\]{}\\|])'
            r'.+$'
        )

        if not re.match(
            pattern,
            new_password
        ):

            flash(
                "Password must contain a-z, A-Z, 0-9 "
                "and special symbols.",
                "error"
            )

            return render_template(
                'forgot_password.html'
            )

        if new_password != confirm_password:

            flash(
                "Passwords do not match.",
                "error"
            )

            return render_template(
                'forgot_password.html'
            )

        conn = None
        cur = None

        try:

            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            user = cur.fetchone()

            if not user:

                flash(
                    "Email is not registered.",
                    "error"
                )

                return render_template(
                    'forgot_password.html'
                )

            hashed_pw = generate_password_hash(
                new_password
            )

            cur.execute(
                """
                UPDATE users
                SET password = %s
                WHERE email = %s
                """,
                (
                    hashed_pw,
                    email
                )
            )

            conn.commit()

            flash(
                "Password has been reset successfully. "
                "Please log in.",
                "success"
            )

            return redirect('/login')

        except Exception as e:

            if conn:

                try:
                    conn.rollback()
                except Exception:
                    pass

            flash(
                f"Error: {str(e)}",
                "error"
            )

            return render_template(
                'forgot_password.html'
            )

        finally:

            if cur:
                cur.close()

            if conn:
                release_db_connection(conn)

    return render_template(
        'forgot_password.html'
    )