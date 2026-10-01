from flask import Flask, render_template, request, redirect, flash, session, jsonify, make_response, send_from_directory, send_file, Response, url_for
from config import DevelopmentConfig
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

from flask import url_for
import uuid
from datetime import datetime, timedelta
import traceback
from summarizer import summarizer
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.services.database import (
    get_db_connection,
    release_db_connection,
    reset_db_pool
)

from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import threading
from flask_compress import Compress
from app.routes.documents import documents_bp
from app.routes.summaries import summaries_bp
from app.routes.auth import auth_bp

load_dotenv()
_executor = ThreadPoolExecutor(max_workers=4)


app = Flask(__name__)
app.config.from_object(DevelopmentConfig)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
UPLOAD_FOLDER = app.config["UPLOAD_FOLDER"]
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
Session(app)
Compress(app) # enable gzip/brotli compression for responses
app.register_blueprint(documents_bp)
app.register_blueprint(summaries_bp)
app.register_blueprint(auth_bp)

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
# Admin credentials from environment (instead of hardcoded)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")







def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    
def _insert_file_record(
    user_id,
    folder_id,
    filename,
    title,
    attachment_path,
    conn=None,
    cur=None
):
    """
    Insert an uploaded document into the files table.

    If a connection/cursor is supplied, the caller
    controls the transaction.
    """

    own_connection = False


    # ---------------------------------------------------------
    # Create connection only when one wasn't supplied
    # ---------------------------------------------------------

    if conn is None:

        conn = get_db_connection()

        cur = conn.cursor()

        own_connection = True


    elif cur is None:

        cur = conn.cursor()


    try:

        cur.execute(
            """
            INSERT INTO files
            (
                userid,
                folderid,
                filename,
                title,
                attachment
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                user_id,
                folder_id,
                filename,
                title,
                attachment_path
            )
        )


        # Only commit when this function created
        # its own connection.

        if own_connection:

            conn.commit()


    except Exception:

        if own_connection:

            conn.rollback()

        raise


    finally:

        if own_connection:

            if cur:

                cur.close()


            if conn:

                release_db_connection(conn)

@lru_cache(maxsize=50)
def get_summary_templates_cached():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT summarytemplateid, templatename, promptinstructions, category FROM uploadsummarytemplates")
    rows = cur.fetchall()
    cur.close()
    release_db_connection(conn)
    return rows




@app.route('/')
def index():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Fetch media
        try:
            cur.execute("SELECT type, path, caption FROM media ORDER BY id")
        except psycopg2.OperationalError as e:
            print(f"⚠️ Query failed ({e}), resetting pool and retrying once...")
            reset_db_pool()
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT type, path, caption FROM media ORDER BY id")
        
        rows = cur.fetchall()
        images = [row for row in rows if row[0] == 'image']
        videos = [row for row in rows if row[0] == 'video' and not row[1].startswith('/static')]
        videos = videos[::-1]

        # Fetch feedbacks
        cur.execute("""
            SELECT name, profession, rating, comment, feedbacktype
            FROM userfeedback
            WHERE rating >= 3
            ORDER BY CreatedAt DESC
            LIMIT 3
        """)
        feedbacks = cur.fetchall()
        cur.close()
        release_db_connection(conn)
        
        print(f"📸 Images: {len(images)}, 🎥 Videos: {len(videos)}, 💬 Feedbacks: {len(feedbacks)}")

        return render_template('index.html', images=images, videos=videos, feedbacks=feedbacks)
        
    except Exception as e:
        print(f"❌ Error loading index: {e}")
        return render_template('index.html', images=[], videos=[], feedbacks=[])
    finally:
        if cur:
            cur.close()
        if conn:
            release_db_connection(conn)




@app.route('/home')
def home():
    name = session.get('user_name', 'User')
    return render_template('home.html', name=name)



@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # --- 🔹 Auto-reset membership if expired ---
        cur.execute("""
            SELECT enddate 
            FROM payments
            WHERE userid = %s
            ORDER BY enddate DESC
            LIMIT 1
        """, (user_id,))
        row = cur.fetchone()

        if row and row[0]:
            from datetime import datetime
            if row[0] < datetime.now():
                # Expired — reset to Free plan
                cur.execute("UPDATE users SET membership = 'Free' WHERE userid = %s", (user_id,))
                conn.commit()
                session['membership'] = 'Free'

        # --- 🔹 Load user files ---
        cur.execute("""
            SELECT f.fileid, f.filename, f.folderid, fo.foldername
            FROM files f
            LEFT JOIN folders fo ON f.folderid = fo.folderid
            WHERE f.userid = %s
            ORDER BY f.fileid DESC
        """, (user_id,))
        files = cur.fetchall()
        documents = [
            {"id": r[0], "filename": r[1], "category": r[2], "category_name": r[3]}
            for r in files
        ]

        # --- 🔹 Fetch user membership (after possible reset) ---
        cur.execute("SELECT membership FROM users WHERE userid = %s", (user_id,))
        row = cur.fetchone()
        membership = row[0] if row and row[0] else 'Free'
        session['membership'] = membership

        cur.close()
        release_db_connection(conn)


        return render_template(
            'dashboard.html',
            name=session.get('user_name'),
            profession=session.get('profession'),
            documents=documents,
            latest_membership=membership
        )

    except Exception as e:
        return f"Dashboard error: {e}"


    

@app.route('/view-document/<int:doc_id>')
def view_document(doc_id):
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT attachment, filename, userid FROM files WHERE fileid = %s", (doc_id,))
    row = cur.fetchone()
    cur.close()
    release_db_connection(conn)


    if not row:
        return "File not found", 404

    file_path, filename, owner_userid = row

    if owner_userid != session['user_id']:
        return "Unauthorized", 403

    if not os.path.exists(file_path):
        # 👇 Try resolving relative uploads path if stored relative
        alt_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(file_path))
        if os.path.exists(alt_path):
            file_path = alt_path
        else:
            return f"File not found on disk: {file_path}", 404

    # 👇 Explicit MIME type fixes “blank tab” issue
    return send_file(file_path, mimetype='application/pdf', as_attachment=False)




@app.route('/delete-document/<int:doc_id>', methods=['GET', 'POST'])
def delete_document(doc_id):

    # ---------------------------------------------------------
    # 1. Authentication
    # ---------------------------------------------------------

    if 'user_id' not in session:
        return redirect('/login')


    conn = None
    cur = None


    try:

        user_id = session['user_id']


        # -----------------------------------------------------
        # 2. Open database connection
        # -----------------------------------------------------

        conn = get_db_connection()
        cur = conn.cursor()


        # -----------------------------------------------------
        # 3. Find document belonging to current user
        # -----------------------------------------------------

        cur.execute(
            """
            SELECT
                fileid,
                attachment,
                filename,
                title
            FROM files
            WHERE fileid = %s
              AND userid = %s
            """,
            (
                doc_id,
                user_id
            )
        )


        row = cur.fetchone()


        # -----------------------------------------------------
        # 4. Document not found / not owned by user
        # -----------------------------------------------------

        if not row:

            flash(
                "Document not found.",
                "error"
            )

            return redirect('/dashboard')


        file_id = row[0]
        attachment = row[1]
        filename = row[2]
        title = row[3]


        # -----------------------------------------------------
        # 5. Delete database record
        # -----------------------------------------------------

        cur.execute(
            """
            DELETE FROM files
            WHERE fileid = %s
              AND userid = %s
            """,
            (
                file_id,
                user_id
            )
        )


        # -----------------------------------------------------
        # 6. Verify a row was actually deleted
        # -----------------------------------------------------

        if cur.rowcount != 1:

            conn.rollback()

            flash(
                "Document could not be deleted.",
                "error"
            )

            return redirect('/dashboard')


        # -----------------------------------------------------
        # 7. Commit database deletion
        # -----------------------------------------------------

        conn.commit()


        # -----------------------------------------------------
        # 8. Delete physical file
        # -----------------------------------------------------

        if attachment:

            try:

                if os.path.exists(attachment):

                    os.remove(attachment)

                    print(
                        f"🗑️ Deleted file: {attachment}"
                    )

                else:

                    print(
                        f"ℹ️ File already missing: "
                        f"{attachment}"
                    )

            except Exception as file_error:

                # The DB record has already been removed.
                # Log the filesystem problem for cleanup.

                print(
                    "⚠️ Database record deleted, "
                    f"but physical file could not be "
                    f"deleted: {file_error}"
                )


        # -----------------------------------------------------
        # 9. Success message
        # -----------------------------------------------------

        flash(
            "Document deleted successfully!",
            "success"
        )


    except Exception as e:

        # -----------------------------------------------------
        # 10. Roll back database transaction
        # -----------------------------------------------------

        if conn:

            try:

                conn.rollback()

            except Exception:

                pass


        print(
            f"❌ Delete failed: {e}"
        )

        traceback.print_exc()


        flash(
            "Delete failed. Please try again.",
            "error"
        )


    finally:

        # -----------------------------------------------------
        # 11. Close database resources
        # -----------------------------------------------------

        if cur:

            cur.close()


        if conn:

            release_db_connection(conn)


    return redirect('/dashboard')




@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = cur = None

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT adminid, username, passwordhash
                FROM admindatabase
                WHERE username = %s
            """, (username,))
            row = cur.fetchone()

            if row:
                adminid, uname, pw_hash = row
                if pw_hash and check_password_hash(pw_hash, password):
                    session['admin_logged_in'] = True
                    session['admin_id'] = adminid
                    session['admin_username'] = uname
                    flash("Welcome, Admin!", "success")
                    return redirect('/admin')
                else:
                    flash("❌ Incorrect password.", "error")
            else:
                flash("⚠️ Admin not found.", "error")

        except Exception as e:
            print("ERROR:", e)
            flash(f"Admin login failed: {e}", "error")
        finally:
            if cur:
                cur.close()
            if conn:
                release_db_connection(conn)


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
        cur.execute("SELECT userid, name, email, gender, age, profession FROM users")
        users = cur.fetchall()
        cur.close()
        release_db_connection(conn)

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
        cur.execute("DELETE FROM users WHERE userid = %s", (user_id,))
        conn.commit()
        cur.close()
        release_db_connection(conn)

        flash("User deleted successfully", "success")
    except Exception as e:
        flash(f"Failed to delete user: {e}", "error")
    return redirect('/admin')

@app.route('/admin/media', methods=['GET'])
def admin_media():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, type, path, caption FROM media ORDER BY id')
    images = cur.fetchall()
    cur.close()
    release_db_connection(conn)
    return render_template('admin_media.html', images=images)


@app.route('/admin/media/update', methods=['POST'])
def update_media():
    id_ = request.form.get('id')
    path = request.form.get('path', '').strip()
    caption = request.form.get('caption', '').strip()

    if not id_:
        flash("Image ID is required.", "error")
        return redirect('/admin/media')

    # Build dynamic update only for fields provided
    fields = []
    values = []

    if path:
        fields.append("path = %s")
        values.append(path)
    if caption:
        fields.append("caption = %s")
        values.append(caption)

    if not fields:
        flash("Nothing to update. Provide a new path or caption.", "info")
        return redirect('/admin/media')

    values.append(id_)  # WHERE id = %s

    query = f"UPDATE media SET {', '.join(fields)} WHERE id = %s"

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, tuple(values))
    conn.commit()
    cur.close()
    release_db_connection(conn)


    flash("Image updated successfully.", "success")
    return redirect('/admin/media')


@app.route('/admin/media/upload', methods=['POST'])
def upload_media():
    if not session.get('admin_logged_in'):
        flash("Please log in as admin", "error")
        return redirect('/admin-login')
    
    media_id = request.form.get('id', '').strip()
    media_type = request.form.get('type', 'image').strip()
    file = request.files.get('file')
    
    if not file or file.filename == '':
        flash("No file selected", "error")
        return redirect('/admin/media')
    
    # Validate file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'webm', 'mov'}
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in allowed_extensions:
        flash("Invalid file type", "error")
        return redirect('/admin/media')
    
    conn = None
    cur = None
    
    try:
        from datetime import datetime
        
        # Create unique filename
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        name, extension = os.path.splitext(filename)
        unique_filename = f"{name}_{timestamp}{extension}"
        
        # 🔹 Use same persistent storage as uploads (parallel folder)
        MEDIA_FOLDER = "/tmp/uploads/media"
        os.makedirs(MEDIA_FOLDER, exist_ok=True)
        
        # Save to persistent disk
        file_path = os.path.join(MEDIA_FOLDER, unique_filename)
        file.save(file_path)
        print(f"✅ File saved to: {file_path}")
        
        # Verify file exists
        if not os.path.exists(file_path):
            flash("File save failed", "error")
            return redirect('/admin/media')
        
        # Store web-accessible path
        web_path = f"/media/{unique_filename}"
        print(f"✅ Web path: {web_path}")
        
        # Update database
        conn = get_db_connection()
        cur = conn.cursor()
        
        if media_id:
            cur.execute("UPDATE media SET path = %s WHERE id = %s", (web_path, media_id))
            if cur.rowcount == 0:
                cur.execute("INSERT INTO media (type, path) VALUES (%s, %s)", (media_type, web_path))
        else:
            cur.execute("INSERT INTO media (type, path) VALUES (%s, %s)", (media_type, web_path))
        
        conn.commit()
        flash(f"✅ {media_type.capitalize()} uploaded successfully!", "success")
        
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        print(traceback.format_exc())
        
        if conn:
            try:
                conn.rollback()
            except:
                pass
        
        flash(f"Upload failed: {str(e)}", "error")
        
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            try:
                release_db_connection(conn)
            except:
                pass
    
    return redirect('/admin/media')

@app.route('/media/<filename>')
def serve_media(filename):
    """Serve media files from persistent disk - PUBLIC ACCESS"""
    MEDIA_FOLDER = "/tmp/uploads/media"
    try:
        return send_from_directory(MEDIA_FOLDER, filename)
    except Exception as e:
        print(f"❌ Error serving media {filename}: {e}")
        return "Media not found", 404
    
@app.route('/static/media/<path:filename>')
def legacy_static_media(filename):
    """Compatibility shim: serve old /static/media/... links from the persistent folder."""
    MEDIA_FOLDER = "/tmp/uploads/media"
    try:
        return send_from_directory(MEDIA_FOLDER, filename)
    except Exception as e:
        print(f"❌ Error serving legacy static media {filename}: {e}")
        return "Media not found", 404
        

@app.route('/membership')
def membership():
    if 'user_id' not in session:
        return redirect('/login')

    conn = None
    cur = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                planid,
                code,
                name,
                pricecents,
                currency,
                features
            FROM plans
            ORDER BY planid
        """)

        plans = cur.fetchall()

        cur.execute("""
            SELECT membership
            FROM users
            WHERE userid = %s
        """, (session['user_id'],))

        row = cur.fetchone()

        current_membership = (
            row[0]
            if row and row[0]
            else 'Free'
        )

        return render_template(
            'payment.html',
            plans=plans,
            current_membership=current_membership
        )

    except Exception as e:
        print("Error loading membership plans:", e)

        return render_template(
            'payment.html',
            plans=[],
            current_membership='Free'
        )

    finally:
        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)





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

@app.route('/payment_success')
def payment_success():

    if 'user_id' not in session:
        return redirect('/login')

    transaction_id = session.get(
        'last_transaction_id'
    )

    if not transaction_id:
        return redirect('/dashboard')

    conn = None
    cur = None

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                paymentid,
                planname,
                amount,
                currency,
                payment_method,
                transaction_id,
                payer_name,
                startdate,
                enddate,
                status
            FROM payments
            WHERE userid = %s
              AND transaction_id = %s
              AND status = 'success'
            LIMIT 1
        """, (
            session['user_id'],
            transaction_id
        ))

        payment = cur.fetchone()

        if not payment:
            return redirect('/dashboard')


        payment_id = payment[0]
        plan_name = payment[1]
        amount = payment[2]
        currency = payment[3]
        payment_method = payment[4]
        transaction_id = payment[5]
        payer_name = payment[6]
        start_date = payment[7]
        end_date = payment[8]
        status = payment[9]


        if currency == 'INR':

            amount_display = (
                f"₹{float(amount):,.2f}"
            )

        elif currency == 'USD':

            amount_display = (
                f"${float(amount):,.2f}"
            )

        else:

            amount_display = (
                f"{currency} "
                f"{float(amount):,.2f}"
            )


        payment_date = (
            start_date.strftime(
                "%d/%m/%Y"
            )
            if start_date
            else "N/A"
        )


        valid_until = (
            end_date.strftime(
                "%d/%m/%Y"
            )
            if end_date
            else "N/A"
        )


        return render_template(
            'payment_success.html',

            selected_plan=plan_name,

            amount=amount_display,

            currency=currency,

            payment_method=payment_method,

            transaction_id=transaction_id,

            payer_name=payer_name,

            payment_date=payment_date,

            valid_until=valid_until,

            payment_id=payment_id,

            status=status
        )


    except Exception as e:

        print(
            "Error loading payment success:",
            e
        )

        traceback.print_exc()

        return redirect('/dashboard')


    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)

@app.route('/payment_process', methods=['POST'])
def payment_process():
    # Ensure user is logged in
    if 'user_id' not in session:
        flash("Please log in to continue.", "error")
        return redirect('/login')

    selected_plan = request.form.get('selected_plan')
    if not selected_plan:
        flash("Please select a plan.", "error")
        return redirect('/membership')

    # Collect form data
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    card_number = request.form.get('card_number', '').replace(' ', '').strip()
    card_expiry = request.form.get('card_expiry', '').strip()
    card_cvv = request.form.get('card_cvv', '').strip()

    # Basic validation
    if not all([first_name, last_name, card_number, card_expiry, card_cvv]):
        flash("All payment fields are required.", "error")
        return redirect('/membership')

    # Parse expiry (MM/YY)
    try:
        mm, yy = card_expiry.split('/')
        exp_month = int(mm)
        exp_year = int(yy) if len(yy) == 4 else 2000 + int(yy)
    except Exception:
        flash("Invalid expiry date format. Use MM/YY.", "error")
        return redirect('/membership')

    # Determine plan pricing
    if selected_plan == 'Professional':
        amount = 9.99
    elif selected_plan == 'Professional Plus':
        amount = 19.99
    else:
        amount = 0.00

    # Hash sensitive details
    hashed_card_number = generate_password_hash(card_number)
    hashed_expiry = generate_password_hash(card_expiry)
    hashed_cvv = generate_password_hash(card_cvv)

    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Insert payment record
        cur.execute("""
            INSERT INTO Payments (userid, planname, amount, currency, cardnumber, cardexpiry, cardcvv, status, startdate, enddate)
            VALUES (%s, %s, %s, 'USD', %s, %s, %s, 'success', NOW(), NOW() + interval '30 days')
        """, (
            user_id, selected_plan, amount,
            hashed_card_number, hashed_expiry, hashed_cvv
        ))

        # Update user's membership
        cur.execute("UPDATE Users SET membership = %s WHERE userid = %s", (selected_plan, user_id))

        conn.commit()
        cur.close()
        release_db_connection(conn)


        session['last_payment_plan'] = selected_plan
        flash("Payment successful!", "success")
        return redirect(url_for('payment_success'))

    except Exception as e:
        print("Payment Error:", e)
        flash(f"Payment failed: {str(e)}", "error")
        return redirect('/membership')





@app.route('/payment')
def payment_page():

    if 'user_id' not in session:
        return redirect('/login')

    plan_id = session.get('selected_plan_id')

    if not plan_id:
        return redirect('/membership')

    conn = None
    cur = None

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        # ---------------------------------------------------------
        # Get the selected plan
        # ---------------------------------------------------------

        cur.execute("""
            SELECT
                planid,
                code,
                name
            FROM plans
            WHERE planid = %s
              AND active = TRUE
        """, (plan_id,))

        plan_row = cur.fetchone()

        if not plan_row:
            return redirect('/membership')

        db_plan_id = plan_row[0]
        plan_code = plan_row[1]
        plan_name = plan_row[2]


        # ---------------------------------------------------------
        # Get USD price
        # ---------------------------------------------------------

        cur.execute("""
            SELECT amountcents
            FROM plan_prices
            WHERE planid = %s
              AND currency = 'USD'
              AND active = TRUE
            LIMIT 1
        """, (db_plan_id,))

        usd_row = cur.fetchone()

        usd_price = (
            usd_row[0]
            if usd_row
            else None
        )


        # ---------------------------------------------------------
        # Get INR price
        # ---------------------------------------------------------

        cur.execute("""
            SELECT amountcents
            FROM plan_prices
            WHERE planid = %s
              AND currency = 'INR'
              AND active = TRUE
            LIMIT 1
        """, (db_plan_id,))

        inr_row = cur.fetchone()

        inr_price = (
            inr_row[0]
            if inr_row
            else None
        )


        # ---------------------------------------------------------
        # Make sure at least one price exists
        # ---------------------------------------------------------

        if usd_price is None and inr_price is None:

            print(
                f"No active prices found for plan {db_plan_id}"
            )

            return redirect('/membership')


        # ---------------------------------------------------------
        # Remember selected payment currency
        # ---------------------------------------------------------

        selected_currency = session.get(
            'payment_currency',
            'USD'
        )


        if selected_currency not in ['INR', 'USD']:

            selected_currency = 'USD'

            session['payment_currency'] = 'USD'


        # ---------------------------------------------------------
        # If selected currency is unavailable,
        # fall back to the other available currency.
        # ---------------------------------------------------------

        if (
            selected_currency == 'INR'
            and inr_price is None
        ):

            selected_currency = 'USD'

            session['payment_currency'] = 'USD'


        elif (
            selected_currency == 'USD'
            and usd_price is None
        ):

            selected_currency = 'INR'

            session['payment_currency'] = 'INR'


        # ---------------------------------------------------------
        # Prepare plan data for checkout template
        # ---------------------------------------------------------

        plan = {

            'planid': db_plan_id,

            'code': plan_code,

            'name': plan_name,

            'inr_price': inr_price,

            'usd_price': usd_price

        }


        return render_template(
            'payment_checkout.html',
            plan=plan,
            selected_currency=selected_currency
        )


    except Exception as e:

        print(
            "Error loading checkout:",
            e
        )

        return redirect('/membership')


    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)



@app.route('/pay', methods=['POST'])
def pay():
    if 'user_id' not in session:
        return redirect('/login')

    membership_plan = session.get('selected_plan', 'Free')
    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE users
            SET membership = %s
            WHERE userid = %s
        """, (membership_plan, user_id))

        conn.commit()

        cur.close()
        release_db_connection(conn)

        session['membership'] = membership_plan

        return redirect('/dashboard')

    except Exception as e:
        print("Membership update error:", e)

        try:
            cur.close()
            release_db_connection(conn)
        except Exception:
            pass

        flash("Unable to update membership.", "error")
        return redirect('/membership')

@app.context_processor
def inject_membership():
    membership = 'Free'

    if 'user_id' in session:
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute("""
                SELECT membership
                FROM users
                WHERE userid = %s
            """, (session['user_id'],))

            row = cur.fetchone()

            cur.close()
            release_db_connection(conn)

            if row and row[0]:
                membership = row[0]

            session['membership'] = membership

        except Exception as e:
            print("Error loading membership:", e)

    return {
        'membership': membership
    }


@app.route('/admin/templates')
def manage_templates():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    try:
        templates = get_summary_templates_cached()
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
        release_db_connection(conn)


        # Invalidate template cache
        get_summary_templates_cached.cache_clear()
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
        release_db_connection(conn)


        # Invalidate template cache
        get_summary_templates_cached.cache_clear()
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
        release_db_connection(conn)


        # Invalidate template cache
        get_summary_templates_cached.cache_clear()
        return redirect('/admin/templates')
    except Exception as e:
        return f"Error deleting template: {e}"




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
        release_db_connection(conn)

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
        release_db_connection(conn)

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



        

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
        release_db_connection(conn)

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
            release_db_connection(conn)

            flash("Thanks for your feedback!", "success")
            return redirect('/dashboard')
        except Exception as e:
            flash("Feedback save failed: " + str(e), "error")
            return render_template('feedback.html')
    return render_template('feedback.html')

@app.route('/get_templates')
def get_templates():

    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    conn = None
    cur = None

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        # -------------------------------------------------
        # 1. Get the user's current membership
        # -------------------------------------------------

        cur.execute("""
            SELECT membership
            FROM users
            WHERE userid = %s
        """, (session['user_id'],))

        user_row = cur.fetchone()

        membership = 'Free'

        if user_row and user_row[0]:
            membership = user_row[0]

        # -------------------------------------------------
        # 2. Normalize membership
        # -------------------------------------------------

        if membership not in [
            'Free',
            'Professional',
            'Professional Plus'
        ]:
            membership = 'Free'

        # -------------------------------------------------
        # 3. Determine membership level
        #
        # Free = 1
        # Professional = 2
        # Professional Plus = 3
        # -------------------------------------------------

        cur.execute("""
            SELECT
                t.summarytemplateid,
                t.templatename,
                t.category,
                t.promptinstructions
            FROM uploadsummarytemplates t
            INNER JOIN template_plan_access a
                ON a.summarytemplateid = t.summarytemplateid
            WHERE
                CASE %s
                    WHEN 'Free' THEN 1
                    WHEN 'Professional' THEN 2
                    WHEN 'Professional Plus' THEN 3
                END
                >=
                CASE a.minimum_plan
                    WHEN 'Free' THEN 1
                    WHEN 'Professional' THEN 2
                    WHEN 'Professional Plus' THEN 3
                END
            ORDER BY t.summarytemplateid
        """, (membership,))

        rows = cur.fetchall()

        templates = []

        for row in rows:

            templates.append({
                'id': row[0],
                'name': row[1],
                'category': row[2],
                'prompt': row[3]
            })

        return jsonify({
            'success': True,
            'membership': membership,
            'templates': templates,
            'template_count': len(templates)
        })

    except Exception as e:

        print(
            "Error in /get_templates:",
            e
        )

        return jsonify({
            'success': False,
            'error': 'Unable to load templates'
        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)

@app.route('/debug-files')
def debug_files():
    try:
        files = os.listdir(app.config['UPLOAD_FOLDER'])
        # Show DB entries too for cross-check
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT fileid, filename, attachment, userid FROM files ORDER BY fileid DESC LIMIT 50")
        rows = cur.fetchall()
        cur.close()
        release_db_connection(conn)


        html = "<h3>Files on disk:</h3><pre>{}</pre>".format("\n".join(files))
        html += "<h3>Latest DB file rows:</h3><pre>{}</pre>".format("\n".join(str(r) for r in rows))
        return html
    except Exception as e:
        return f"Error inspecting uploads: {e}", 500





# ============================================================
# GET LATEST SUMMARY
# ============================================================


# ============================================================
# DOWNLOAD GENERATED SUMMARY PDF
# ============================================================


@app.route('/forum')
def forum():
    if 'user_id' not in session:
        return redirect('/login')

    return render_template(
        'forum.html',
        current_user_id=session['user_id']
    )

@app.route('/forum/posts', methods=['GET'])
def get_forum_posts():
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                fp.postid,
                fp.userid,
                u.name,
                fp.title,
                fp.content,
                fp.category,
                fp.views,
                fp.createdat,
                fp.updatedat
            FROM forum_posts fp
            INNER JOIN users u
                ON fp.userid = u.userid
            WHERE fp.status = 'active'
            ORDER BY fp.createdat DESC
        """)

        rows = cur.fetchall()

        cur.close()
        release_db_connection(conn)

        posts = []

        for row in rows:
            posts.append({
                'postid': row[0],
                'userid': row[1],
                'username': row[2],
                'title': row[3],
                'content': row[4],
                'category': row[5],
                'views': row[6],
                'createdat': row[7].isoformat() if row[7] else None,
                'updatedat': row[8].isoformat() if row[8] else None
            })

        return jsonify({
            'success': True,
            'posts': posts
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/forum/posts/<int:post_id>', methods=['GET'])
def get_forum_post(post_id):
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                fp.postid,
                fp.userid,
                u.name,
                fp.title,
                fp.content,
                fp.category,
                fp.views,
                fp.createdat,
                fp.updatedat
            FROM forum_posts fp
            INNER JOIN users u
                ON fp.userid = u.userid
            WHERE fp.postid = %s
              AND fp.status = 'active'
        """, (post_id,))

        row = cur.fetchone()

        cur.close()
        release_db_connection(conn)

        if not row:
            return jsonify({
                'success': False,
                'error': 'Discussion not found'
            }), 404

        post = {
            'postid': row[0],
            'userid': row[1],
            'username': row[2],
            'title': row[3],
            'content': row[4],
            'category': row[5],
            'views': row[6],
            'createdat': row[7].isoformat() if row[7] else None,
            'updatedat': row[8].isoformat() if row[8] else None
        }

        return jsonify({
            'success': True,
            'post': post
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    
@app.route('/forum/posts', methods=['POST'])
def create_forum_post():
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    try:
        data = request.get_json()

        title = (data.get('title') or '').strip()
        content = (data.get('content') or '').strip()
        category = (data.get('category') or 'General Discussion').strip()

        # Validate title
        if not title:
            return jsonify({
                'success': False,
                'error': 'Post title is required'
            }), 400

        if len(title) > 200:
            return jsonify({
                'success': False,
                'error': 'Post title cannot exceed 200 characters'
            }), 400

        # Validate content
        if not content:
            return jsonify({
                'success': False,
                'error': 'Post content is required'
            }), 400

        # Validate category
        allowed_categories = [
            'Research Methods',
            'Data Science',
            'Artificial Intelligence',
            'Machine Learning',
            'Academic Writing',
            'Statistics',
            'Technology',
            'General Discussion'
        ]

        if category not in allowed_categories:
            category = 'General Discussion'

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO forum_posts (
                userid,
                title,
                content,
                category
            )
            VALUES (%s, %s, %s, %s)
            RETURNING postid, createdat
        """, (
            session['user_id'],
            title,
            content,
            category
        ))

        row = cur.fetchone()

        conn.commit()

        cur.close()
        release_db_connection(conn)

        return jsonify({
            'success': True,
            'message': 'Discussion created successfully',
            'post': {
                'postid': row[0],
                'title': title,
                'content': content,
                'category': category,
                'views': 0,
                'createdat': row[1].isoformat() if row[1] else None
            }
        }), 201

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/forum/posts/<int:post_id>/comments', methods=['GET'])
def get_forum_comments(post_id):
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                fc.commentid,
                fc.postid,
                fc.userid,
                u.name,
                fc.parent_comment_id,
                fc.content,
                fc.createdat,
                fc.updatedat
            FROM forum_comments fc
            INNER JOIN users u
                ON fc.userid = u.userid
            WHERE fc.postid = %s
              AND fc.status = 'active'
            ORDER BY fc.createdat ASC
        """, (post_id,))

        rows = cur.fetchall()

        cur.close()
        release_db_connection(conn)

        comments = []

        for row in rows:
            comments.append({
                'commentid': row[0],
                'postid': row[1],
                'userid': row[2],
                'username': row[3],
                'parent_comment_id': row[4],
                'content': row[5],
                'createdat': row[6].isoformat() if row[6] else None,
                'updatedat': row[7].isoformat() if row[7] else None
            })

        return jsonify({
            'success': True,
            'comments': comments
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/forum/posts/<int:post_id>/comments', methods=['POST'])
def create_forum_comment(post_id):
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    try:
        data = request.get_json() or {}

        content = (data.get('content') or '').strip()
        parent_comment_id = data.get('parent_comment_id')

        if not content:
            return jsonify({
                'success': False,
                'error': 'Comment content is required'
            }), 400

        if len(content) > 5000:
            return jsonify({
                'success': False,
                'error': 'Comment cannot exceed 5000 characters'
            }), 400

        conn = get_db_connection()
        cur = conn.cursor()

        # Confirm that the discussion exists
        cur.execute("""
            SELECT postid
            FROM forum_posts
            WHERE postid = %s
              AND status = 'active'
        """, (post_id,))

        post_row = cur.fetchone()

        if not post_row:
            cur.close()
            release_db_connection(conn)

            return jsonify({
                'success': False,
                'error': 'Discussion not found'
            }), 404

        # If this is a reply, verify the parent comment
        if parent_comment_id is not None:
            cur.execute("""
                SELECT commentid
                FROM forum_comments
                WHERE commentid = %s
                  AND postid = %s
                  AND status = 'active'
            """, (parent_comment_id, post_id))

            parent_row = cur.fetchone()

            if not parent_row:
                cur.close()
                release_db_connection(conn)

                return jsonify({
                    'success': False,
                    'error': 'Parent comment not found'
                }), 404

        cur.execute("""
            INSERT INTO forum_comments (
                postid,
                userid,
                parent_comment_id,
                content
            )
            VALUES (%s, %s, %s, %s)
            RETURNING commentid, createdat
        """, (
            post_id,
            session['user_id'],
            parent_comment_id,
            content
        ))

        row = cur.fetchone()

        conn.commit()

        cur.close()
        release_db_connection(conn)

        return jsonify({
            'success': True,
            'message': 'Comment added successfully',
            'comment': {
                'commentid': row[0],
                'postid': post_id,
                'userid': session['user_id'],
                'parent_comment_id': parent_comment_id,
                'content': content,
                'createdat': row[1].isoformat() if row[1] else None
            }
        }), 201

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/forum/summaries', methods=['GET'])
def get_forum_summaries():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT forumid, documenttitle, summarycontent, views, sharedat
            FROM forum
            ORDER BY sharedat DESC
        """)
        rows = cur.fetchall()
        cur.close()
        release_db_connection(conn)
        
        summaries = [{
            'forumid': r[0],
            'documenttitle': r[1],
            'summarycontent': r[2],
            'views': r[3],
            'sharedat': r[4].isoformat() if r[4] else None
        } for r in rows]
        
        return jsonify({'success': True, 'summaries': summaries})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/forum/share', methods=['POST'])
def share_to_forum():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    try:
        data = request.get_json()
        doc_id = data.get('doc_id')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get document title
        cur.execute("SELECT title, filename FROM files WHERE fileid = %s AND userid = %s", 
                   (doc_id, session['user_id']))
        file_row = cur.fetchone()
        if not file_row:
            cur.close()
            release_db_connection(conn)
            return jsonify({'success': False, 'error': 'Document not found'}), 404
        
        doc_title = file_row[0] or file_row[1] or 'Untitled Document'
        
        # Get latest summary
        cur.execute("SELECT summary FROM summarygenerate WHERE docid = %s ORDER BY createdat DESC LIMIT 1", 
                   (doc_id,))
        summary_row = cur.fetchone()
        if not summary_row:
            cur.close()
            release_db_connection(conn)
            return jsonify({'success': False, 'error': 'No summary found'}), 404
        
        # Check if already shared
        cur.execute("SELECT forumid FROM forum WHERE docid = %s AND userid = %s", 
                   (doc_id, session['user_id']))
        existing = cur.fetchone()
        
        if existing:
            cur.execute("""
                UPDATE forum SET summarycontent = %s, documenttitle = %s, sharedat = CURRENT_TIMESTAMP
                WHERE forumid = %s
            """, (summary_row[0], doc_title, existing[0]))
        else:
            cur.execute("""
                INSERT INTO forum (userid, docid, documenttitle, summarycontent)
                VALUES (%s, %s, %s, %s)
            """, (session['user_id'], doc_id, doc_title, summary_row[0]))
        
        conn.commit()
        cur.close()
        release_db_connection(conn)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/forum/posts/<int:post_id>/view', methods=['POST'])
def increment_forum_post_view(post_id):
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE forum_posts
            SET views = views + 1
            WHERE postid = %s
              AND status = 'active'
            RETURNING views
        """, (post_id,))

        row = cur.fetchone()

        if not row:
            cur.close()
            release_db_connection(conn)

            return jsonify({
                'success': False,
                'error': 'Discussion not found'
            }), 404

        conn.commit()

        new_views = row[0]

        cur.close()
        release_db_connection(conn)

        return jsonify({
            'success': True,
            'views': new_views
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/forum/posts/<int:post_id>', methods=['PUT'])
def update_forum_post(post_id):
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    try:
        data = request.get_json() or {}

        title = (data.get('title') or '').strip()
        content = (data.get('content') or '').strip()
        category = (data.get('category') or 'General Discussion').strip()

        if not title:
            return jsonify({
                'success': False,
                'error': 'Post title is required'
            }), 400

        if len(title) > 200:
            return jsonify({
                'success': False,
                'error': 'Post title cannot exceed 200 characters'
            }), 400

        if not content:
            return jsonify({
                'success': False,
                'error': 'Post content is required'
            }), 400

        allowed_categories = [
            'Research Methods',
            'Data Science',
            'Artificial Intelligence',
            'Machine Learning',
            'Academic Writing',
            'Statistics',
            'Technology',
            'General Discussion'
        ]

        if category not in allowed_categories:
            category = 'General Discussion'

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE forum_posts
            SET
                title = %s,
                content = %s,
                category = %s,
                updatedat = CURRENT_TIMESTAMP
            WHERE postid = %s
              AND userid = %s
              AND status = 'active'
            RETURNING
                postid,
                title,
                content,
                category,
                views,
                createdat,
                updatedat
        """, (
            title,
            content,
            category,
            post_id,
            session['user_id']
        ))

        row = cur.fetchone()

        if not row:
            cur.close()
            release_db_connection(conn)

            return jsonify({
                'success': False,
                'error': 'Discussion not found or you are not allowed to edit it'
            }), 404

        conn.commit()

        cur.close()
        release_db_connection(conn)

        return jsonify({
            'success': True,
            'message': 'Discussion updated successfully',
            'post': {
                'postid': row[0],
                'title': row[1],
                'content': row[2],
                'category': row[3],
                'views': row[4],
                'createdat': row[5].isoformat() if row[5] else None,
                'updatedat': row[6].isoformat() if row[6] else None
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/forum/posts/<int:post_id>', methods=['DELETE'])
def delete_forum_post(post_id):
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE forum_posts
            SET
                status = 'deleted',
                updatedat = CURRENT_TIMESTAMP
            WHERE postid = %s
              AND userid = %s
              AND status = 'active'
            RETURNING postid
        """, (
            post_id,
            session['user_id']
        ))

        row = cur.fetchone()

        if not row:
            cur.close()
            release_db_connection(conn)

            return jsonify({
                'success': False,
                'error': 'Discussion not found or you are not allowed to delete it'
            }), 404

        conn.commit()

        cur.close()
        release_db_connection(conn)

        return jsonify({
            'success': True,
            'message': 'Discussion deleted successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ---------------------------------------------------------
# Razorpay Configuration
# ---------------------------------------------------------

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

razorpay_client = None

if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    razorpay_client = razorpay.Client(
        auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
    )

# ---------------------------------------------------------
# Create Razorpay Order
# ---------------------------------------------------------

@app.route('/create_razorpay_order', methods=['POST'])
def create_razorpay_order():

    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    if not razorpay_client:
        return jsonify({
            'success': False,
            'error': 'Payment gateway is not configured'
        }), 500

    plan_id = session.get('selected_plan_id')

    if not plan_id:
        return jsonify({
            'success': False,
            'error': 'No plan selected'
        }), 400

    # ---------------------------------------------------------
    # Get currency selected on checkout
    # ---------------------------------------------------------

    currency = session.get(
        'payment_currency',
        'USD'
    )

    if currency not in ['INR', 'USD']:
        return jsonify({
            'success': False,
            'error': 'Invalid payment currency'
        }), 400

    conn = None
    cur = None

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        # -----------------------------------------------------
        # Get plan + currency-specific price
        # -----------------------------------------------------

        cur.execute("""
            SELECT
                p.planid,
                p.code,
                p.name,
                pp.currency,
                pp.amountcents
            FROM plans p
            INNER JOIN plan_prices pp
                ON pp.planid = p.planid
            WHERE p.planid = %s
              AND p.active = TRUE
              AND pp.currency = %s
              AND pp.active = TRUE
            LIMIT 1
        """, (
            plan_id,
            currency
        ))

        row = cur.fetchone()

        if not row:

            return jsonify({
                'success': False,
                'error': 'Price is not available for the selected currency'
            }), 400

        db_plan_id = row[0]
        plan_code = row[1]
        plan_name = row[2]
        db_currency = row[3]
        amount_cents = row[4]


        # -----------------------------------------------------
        # Validate price
        # -----------------------------------------------------

        if amount_cents <= 0:

            return jsonify({
                'success': False,
                'error': 'This plan does not require payment'
            }), 400


        # -----------------------------------------------------
        # Create unique receipt
        # -----------------------------------------------------

        receipt = (
            f"ipaper_{session['user_id']}_"
            f"{db_plan_id}_{currency.lower()}"
        )


        # -----------------------------------------------------
        # Razorpay order data
        # -----------------------------------------------------

        order_data = {

            'amount': amount_cents,

            'currency': db_currency,

            'receipt': receipt,

            'notes': {

                'userid':
                    str(session['user_id']),

                'planid':
                    str(db_plan_id),

                'plancode':
                    plan_code,

                'planname':
                    plan_name,

                'currency':
                    db_currency

            }

        }


        # -----------------------------------------------------
        # Create Razorpay order
        # -----------------------------------------------------

        order = razorpay_client.order.create(
            data=order_data
        )


        # -----------------------------------------------------
        # Store pending payment information in session
        #
        # This lets the verification step compare the
        # Razorpay response with the order we actually created.
        # -----------------------------------------------------

        session['pending_payment'] = {

            'order_id':
                order['id'],

            'plan_id':
                db_plan_id,

            'currency':
                db_currency,

            'amount_cents':
                amount_cents

        }


        return jsonify({

            'success': True,

            'order': {

                'id':
                    order['id'],

                'amount':
                    amount_cents,

                'currency':
                    db_currency,

                'plan_id':
                    db_plan_id,

                'plan_name':
                    plan_name,

                'key_id':
                    RAZORPAY_KEY_ID

            }

        })


    except Exception as e:

        print(
            "Razorpay order creation error:",
            e
        )

        return jsonify({

            'success': False,

            'error':
                'Unable to create payment order'

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)

# ---------------------------------------------------------
# Verify Razorpay Payment
# ---------------------------------------------------------

@app.route('/verify_razorpay_payment', methods=['POST'])
def verify_razorpay_payment():

    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    if not razorpay_client:
        return jsonify({
            'success': False,
            'error': 'Payment gateway is not configured'
        }), 500

    data = request.get_json(silent=True) or {}

    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_signature = data.get('razorpay_signature')

    if not all([
        razorpay_payment_id,
        razorpay_order_id,
        razorpay_signature
    ]):
        return jsonify({
            'success': False,
            'error': 'Incomplete payment information'
        }), 400

    try:

        # ---------------------------------------------------------
        # 1. Verify Razorpay signature
        # ---------------------------------------------------------

        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })


        # ---------------------------------------------------------
        # 2. Get pending payment created by our server
        # ---------------------------------------------------------

        pending_payment = session.get('pending_payment')

        if not pending_payment:
            return jsonify({
                'success': False,
                'error': 'Payment session not found'
            }), 400


        expected_order_id = pending_payment.get(
            'order_id'
        )

        expected_plan_id = pending_payment.get(
            'plan_id'
        )

        expected_currency = pending_payment.get(
            'currency'
        )

        expected_amount_cents = pending_payment.get(
            'amount_cents'
        )


        # ---------------------------------------------------------
        # 3. Confirm returned Razorpay order belongs to
        #    the order created by our server
        # ---------------------------------------------------------

        if razorpay_order_id != expected_order_id:

            return jsonify({
                'success': False,
                'error': 'Razorpay order does not match the payment session'
            }), 400


        # ---------------------------------------------------------
        # 4. Get selected plan
        # ---------------------------------------------------------

        plan_id = session.get(
            'selected_plan_id'
        )

        if not plan_id:
            return jsonify({
                'success': False,
                'error': 'Selected plan not found'
            }), 400


        if int(plan_id) != int(expected_plan_id):

            return jsonify({
                'success': False,
                'error': 'Selected plan does not match the payment order'
            }), 400


        conn = None
        cur = None

        try:

            conn = get_db_connection()
            cur = conn.cursor()


            # -----------------------------------------------------
            # 5. Get plan information
            # -----------------------------------------------------

            cur.execute("""
                SELECT
                    planid,
                    code,
                    name
                FROM plans
                WHERE planid = %s
                  AND active = TRUE
            """, (
                plan_id,
            ))

            plan_row = cur.fetchone()


            if not plan_row:

                return jsonify({
                    'success': False,
                    'error': 'Selected plan not found'
                }), 404


            db_plan_id = plan_row[0]
            plan_code = plan_row[1]
            plan_name = plan_row[2]


            # -----------------------------------------------------
            # 6. Get price from plan_prices
            # -----------------------------------------------------

            cur.execute("""
                SELECT
                    amountcents,
                    currency
                FROM plan_prices
                WHERE planid = %s
                  AND currency = %s
                  AND active = TRUE
                LIMIT 1
            """, (
                db_plan_id,
                expected_currency
            ))

            price_row = cur.fetchone()


            if not price_row:

                return jsonify({
                    'success': False,
                    'error': 'Payment price not found'
                }), 400


            amount_cents = price_row[0]
            currency = price_row[1]


            # -----------------------------------------------------
            # 7. Verify our pending session price
            #    matches the database price
            # -----------------------------------------------------

            if int(expected_amount_cents) != int(amount_cents):

                return jsonify({
                    'success': False,
                    'error': 'Payment amount does not match the database price'
                }), 400


            # -----------------------------------------------------
            # 8. Fetch Razorpay order
            # -----------------------------------------------------

            order = razorpay_client.order.fetch(
                razorpay_order_id
            )


            # -----------------------------------------------------
            # 9. Verify Razorpay order amount
            # -----------------------------------------------------

            if int(order.get('amount', 0)) != int(amount_cents):

                return jsonify({
                    'success': False,
                    'error': 'Payment amount does not match the selected plan'
                }), 400


            # -----------------------------------------------------
            # 10. Verify Razorpay currency
            # -----------------------------------------------------

            if order.get('currency') != currency:

                return jsonify({
                    'success': False,
                    'error': 'Payment currency does not match the selected plan'
                }), 400


            # -----------------------------------------------------
            # 11. Verify Razorpay order status
            # -----------------------------------------------------

            if order.get('status') != 'paid':

                return jsonify({
                    'success': False,
                    'error': 'Razorpay order has not been paid'
                }), 400


            # -----------------------------------------------------
            # 12. Fetch the actual Razorpay payment
            # -----------------------------------------------------

            payment = razorpay_client.payment.fetch(
                razorpay_payment_id
            )


            # -----------------------------------------------------
            # 13. Confirm payment belongs to our order
            # -----------------------------------------------------

            if payment.get('order_id') != razorpay_order_id:

                return jsonify({
                    'success': False,
                    'error': 'Payment does not belong to the Razorpay order'
                }), 400


            # -----------------------------------------------------
            # 14. Verify payment amount
            # -----------------------------------------------------

            if int(payment.get('amount', 0)) != int(amount_cents):

                return jsonify({
                    'success': False,
                    'error': 'Payment amount verification failed'
                }), 400


            # -----------------------------------------------------
            # 15. Verify payment currency
            # -----------------------------------------------------

            if payment.get('currency') != currency:

                return jsonify({
                    'success': False,
                    'error': 'Payment currency verification failed'
                }), 400


            # -----------------------------------------------------
            # 16. Verify payment is captured
            # -----------------------------------------------------

            if payment.get('status') != 'captured':

                return jsonify({
                    'success': False,
                    'error': 'Payment has not been captured'
                }), 400


            # -----------------------------------------------------
            # 17. Prevent duplicate payment records
            # -----------------------------------------------------

            cur.execute("""
                SELECT
                    paymentid,
                    planname,
                    amount,
                    currency
                FROM payments
                WHERE razorpay_payment_id = %s
                LIMIT 1
            """, (
                razorpay_payment_id,
            ))

            existing_payment = cur.fetchone()


            if existing_payment:

                session['last_payment_plan'] = (
                    existing_payment[1]
                )

                session['last_payment_amount'] = (
                    float(existing_payment[2])
                )

                session['last_payment_currency'] = (
                    existing_payment[3]
                )

                session['membership'] = (
                    existing_payment[1]
                )

                session.pop(
                    'pending_payment',
                    None
                )

                return jsonify({
                    'success': True,
                    'message': 'Payment already processed',
                    'redirect': url_for(
                        'payment_success'
                    )
                })


            # -----------------------------------------------------
            # 18. Convert cents/paise to display amount
            # -----------------------------------------------------

            amount = amount_cents / 100


            # -----------------------------------------------------
            # 19. Save successful payment
            # -----------------------------------------------------

            cur.execute("""
                INSERT INTO payments (
                    userid,
                    planname,
                    amount,
                    currency,
                    status,
                    startdate,
                    enddate,
                    razorpay_order_id,
                    razorpay_payment_id,
                    razorpay_signature
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW(),
                    NOW() + INTERVAL '30 days',
                    %s,
                    %s,
                    %s
                )
            """, (
                session['user_id'],
                plan_name,
                amount,
                currency,
                'success',
                razorpay_order_id,
                razorpay_payment_id,
                razorpay_signature
            ))


            # -----------------------------------------------------
            # 20. Update user's membership
            # -----------------------------------------------------

            cur.execute("""
                UPDATE users
                SET membership = %s
                WHERE userid = %s
            """, (
                plan_name,
                session['user_id']
            ))


            # -----------------------------------------------------
            # 21. Commit transaction
            # -----------------------------------------------------

            conn.commit()


            # -----------------------------------------------------
            # 22. Store success-page information
            # -----------------------------------------------------

            session['last_payment_plan'] = plan_name

            session['last_payment_amount'] = amount

            session['last_payment_currency'] = currency
            
            session['last_payment_id'] = razorpay_payment_id

            session['membership'] = plan_name


            # -----------------------------------------------------
            # 23. Remove pending payment
            # -----------------------------------------------------

            session.pop(
                'pending_payment',
                None
            )


            return jsonify({
                'success': True,
                'redirect': url_for(
                    'payment_success'
                )
            })


        finally:

            if cur:
                cur.close()

            if conn:
                release_db_connection(conn)


    except Exception as e:

        print(
            "Razorpay payment verification error:",
            e
        )

        return jsonify({
            'success': False,
            'error': 'Payment verification failed'
        }), 400

@app.route('/set_payment_currency', methods=['POST'])
def set_payment_currency():

    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Not logged in'
        }), 401

    data = request.get_json(silent=True) or {}

    currency = data.get('currency')

    if currency not in ['INR', 'USD']:
        return jsonify({
            'success': False,
            'error': 'Invalid payment currency'
        }), 400

    plan_id = session.get('selected_plan_id')

    if not plan_id:
        return jsonify({
            'success': False,
            'error': 'No plan selected'
        }), 400

    conn = None
    cur = None

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT priceid
            FROM plan_prices
            WHERE planid = %s
              AND currency = %s
              AND active = TRUE
            LIMIT 1
        """, (
            plan_id,
            currency
        ))

        price_row = cur.fetchone()

        if not price_row:

            return jsonify({
                'success': False,
                'error': 'Selected currency is not available for this plan'
            }), 400

        session['payment_currency'] = currency

        return jsonify({
            'success': True,
            'currency': currency
        })

    except Exception as e:

        print(
            "Payment currency selection error:",
            e
        )

        return jsonify({
            'success': False,
            'error': 'Unable to select payment currency'
        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)

# ---------------------------------------------------------
# Demo Payment
# ---------------------------------------------------------

# ---------------------------------------------------------
# Realistic Demo Payment
# ---------------------------------------------------------

@app.route('/demo_payment_process', methods=['POST'])
def demo_payment_process():

    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Authentication required.'
        }), 401

    data = request.get_json(silent=True) or {}

    currency = str(
        data.get('currency', '')
    ).strip().upper()

    payment_method = str(
        data.get('payment_method', '')
    ).strip()

    payer_name = str(
        data.get('payer_name', '')
    ).strip()

    card_number = str(
        data.get('card_number', '')
    ).replace(' ', '').strip()

    card_expiry = str(
        data.get('card_expiry', '')
    ).strip()

    card_cvv = str(
        data.get('card_cvv', '')
    ).strip()

    upi_id = str(
        data.get('upi_id', '')
    ).strip()

    bank_name = str(
        data.get('bank_name', '')
    ).strip()


    # -----------------------------------------------------
    # Validate currency
    # -----------------------------------------------------

    if currency not in ['INR', 'USD']:

        return jsonify({
            'success': False,
            'error': 'Invalid payment currency.'
        }), 400


    # -----------------------------------------------------
    # Validate payment method
    # -----------------------------------------------------

    allowed_methods = [
        'UPI',
        'Card',
        'Net Banking'
    ]

    if payment_method not in allowed_methods:

        return jsonify({
            'success': False,
            'error': 'Invalid payment method.'
        }), 400


    # -----------------------------------------------------
    # Get selected plan
    # -----------------------------------------------------

    plan_id = session.get(
        'selected_plan_id'
    )

    if not plan_id:

        return jsonify({
            'success': False,
            'error': 'No payment plan selected.'
        }), 400


    if not payer_name:

        return jsonify({
            'success': False,
            'error': 'Please enter the name on the payment.'
        }), 400


    # -----------------------------------------------------
    # Payment-method validation
    # -----------------------------------------------------

    card_last4 = None
    masked_card = None

    if payment_method == 'Card':

        if not card_number:

            return jsonify({
                'success': False,
                'error': 'Card number is required.'
            }), 400

        if not card_number.isdigit():

            return jsonify({
                'success': False,
                'error': 'Invalid card number.'
            }), 400

        if len(card_number) not in [15, 16]:

            return jsonify({
                'success': False,
                'error': 'Invalid card number.'
            }), 400

        if not card_expiry:

            return jsonify({
                'success': False,
                'error': 'Card expiry date is required.'
            }), 400

        try:

            month, year = card_expiry.split('/')

            month = int(month)
            year = int(year)

            if month < 1 or month > 12:

                raise ValueError()

            if year < 100:

                year += 2000

        except Exception:

            return jsonify({
                'success': False,
                'error': 'Invalid expiry date. Use MM/YY.'
            }), 400

        if len(card_cvv) not in [3, 4] or not card_cvv.isdigit():

            return jsonify({
                'success': False,
                'error': 'Invalid CVV.'
            }), 400

        card_last4 = card_number[-4:]

        masked_card = (
            '**** **** **** ' +
            card_last4
        )


    elif payment_method == 'UPI':

        if not upi_id:

            return jsonify({
                'success': False,
                'error': 'UPI ID is required.'
            }), 400

        if '@' not in upi_id or len(upi_id) < 5:

            return jsonify({
                'success': False,
                'error': 'Please enter a valid UPI ID.'
            }), 400


    elif payment_method == 'Net Banking':

        if not bank_name:

            return jsonify({
                'success': False,
                'error': 'Please select your bank.'
            }), 400


    conn = None
    cur = None

    try:

        conn = get_db_connection()
        cur = conn.cursor()


        # -------------------------------------------------
        # Get plan price from database
        # -------------------------------------------------

        cur.execute("""
            SELECT
                p.planid,
                p.code,
                p.name,
                pp.currency,
                pp.amountcents
            FROM plans p
            INNER JOIN plan_prices pp
                ON pp.planid = p.planid
            WHERE
                p.planid = %s
                AND pp.currency = %s
                AND p.active = TRUE
                AND pp.active = TRUE
            LIMIT 1
        """, (
            plan_id,
            currency
        ))

        plan_row = cur.fetchone()

        if not plan_row:

            return jsonify({
                'success': False,
                'error':
                    'Selected plan price is not available.'
            }), 404


        db_plan_id = plan_row[0]
        plan_code = plan_row[1]
        plan_name = plan_row[2]
        db_currency = plan_row[3]
        amount_cents = plan_row[4]

        amount = amount_cents / 100


        # -------------------------------------------------
        # Generate transaction reference
        # -------------------------------------------------

        transaction_id = (
            'IPAY-' +
            uuid.uuid4().hex[:12].upper()
        )


        # -------------------------------------------------
        # Payment display information
        # -------------------------------------------------

        if payment_method == 'Card':

            payment_display = 'Card'

        elif payment_method == 'UPI':

            payment_display = 'UPI'

        else:

            payment_display = 'Net Banking'


        # -------------------------------------------------
        # Save simulated payment
        #
        # No raw card number or CVV is stored.
        # -------------------------------------------------

        cur.execute("""
            INSERT INTO payments (
                userid,
                planname,
                amount,
                currency,
                cardnumber,
                cardexpiry,
                cardcvv,
                status,
                startdate,
                enddate,
                payment_method,
                transaction_id,
                card_last4,
                payer_name
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                NULL,
                NULL,
                %s,
                NOW(),
                NOW() + INTERVAL '30 days',
                %s,
                %s,
                %s,
                %s
            )
            RETURNING paymentid
        """, (
            session['user_id'],
            plan_name,
            amount,
            db_currency,
            masked_card,
            'success',
            payment_display,
            transaction_id,
            card_last4,
            payer_name
        ))

        payment_id = cur.fetchone()[0]


        # -------------------------------------------------
        # Activate membership
        # -------------------------------------------------

        cur.execute("""
            UPDATE users
            SET membership = %s
            WHERE userid = %s
        """, (
            plan_name,
            session['user_id']
        ))


        conn.commit()


        # -------------------------------------------------
        # Store successful payment in session
        # -------------------------------------------------

        session['last_payment_plan'] = plan_name
        session['last_payment_amount'] = amount
        session['last_payment_currency'] = db_currency
        session['last_payment_method'] = payment_display
        session['last_transaction_id'] = transaction_id


        return jsonify({

            'success': True,

            'payment': {

                'payment_id': payment_id,

                'transaction_id':
                    transaction_id,

                'plan_name':
                    plan_name,

                'amount':
                    amount,

                'currency':
                    db_currency,

                'payment_method':
                    payment_display
            },

            'redirect':
                url_for('payment_success')
        })


    except Exception as e:

        if conn:

            conn.rollback()

        print(
            "Demo payment error:",
            e
        )

        traceback.print_exc()

        return jsonify({
            'success': False,
            'error':
                'Payment could not be completed.'
        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)

if __name__ == '__main__':
    app.run(debug=True)




















