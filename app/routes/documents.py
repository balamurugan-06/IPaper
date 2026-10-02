"""
IPaper Document Routes

Handles:
- Document upload
- Document listing
- Category listing
- Document deletion
- Document download
"""

import os
import traceback

from flask import (
    Blueprint,
    request,
    redirect,
    flash,
    jsonify,
    session,
    send_file,
    current_app,
    send_from_directory
)

from werkzeug.utils import secure_filename

from app.services.database import (
    get_db_connection,
    release_db_connection
)


# ============================================================
# BLUEPRINT
# ============================================================

documents_bp = Blueprint(
    "documents",
    __name__
)


# ============================================================
# FILE CONFIGURATION
# ============================================================

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx"
}


def allowed_file(filename):
    """
    Check whether the uploaded file has an allowed extension.
    """

    return (
        "." in filename
        and filename.rsplit(
            ".",
            1
        )[1].lower() in ALLOWED_EXTENSIONS
    )


# ============================================================
# CATEGORY LIST
# ============================================================

@documents_bp.route(
    "/get_categories",
    methods=["GET"]
)
def get_categories():

    if "user_id" not in session:
        return jsonify([])


    conn = None
    cur = None


    try:

        conn = get_db_connection()
        cur = conn.cursor()


        cur.execute(
            """
            SELECT
                folderid,
                foldername
            FROM folders
            WHERE userid = %s
            ORDER BY folderid DESC
            """,
            (
                session["user_id"],
            )
        )


        rows = cur.fetchall()


        categories = [
            {
                "id": row[0],
                "name": row[1]
            }
            for row in rows
        ]


        return jsonify(categories)


    except Exception as e:

        print(
            f"❌ Error loading categories: {e}"
        )

        traceback.print_exc()


        return jsonify([])


    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)


# ============================================================
# DOCUMENT LIST
# ============================================================

@documents_bp.route(
    "/get-documents",
    methods=["GET"]
)
def get_documents():

    if "user_id" not in session:
        return jsonify([])


    category_filter = request.args.get(
        "category",
        "all"
    )


    conn = None
    cur = None


    try:

        conn = get_db_connection()
        cur = conn.cursor()


        # -----------------------------------------------------
        # All Documents
        # -----------------------------------------------------

        if category_filter == "all":

            cur.execute(
                """
                SELECT
                    f.fileid,
                    f.filename,
                    f.title,
                    f.folderid,
                    fo.foldername
                FROM files f

                LEFT JOIN folders fo
                    ON f.folderid = fo.folderid

                WHERE f.userid = %s
                  AND f.folderid IS NULL

                ORDER BY f.fileid DESC
                """,
                (
                    session["user_id"],
                )
            )


        # -----------------------------------------------------
        # Selected Category
        # -----------------------------------------------------

        else:

            # Make sure the category ID is numeric.

            try:

                category_id = int(
                    category_filter
                )

            except (TypeError, ValueError):

                return jsonify([])


            cur.execute(
                """
                SELECT
                    f.fileid,
                    f.filename,
                    f.title,
                    f.folderid,
                    fo.foldername
                FROM files f

                LEFT JOIN folders fo
                    ON f.folderid = fo.folderid

                WHERE f.userid = %s
                  AND f.folderid = %s

                ORDER BY f.fileid DESC
                """,
                (
                    session["user_id"],
                    category_id
                )
            )


        rows = cur.fetchall()


        documents = [
            {
                "id": row[0],
                "filename": row[1],
                "title": row[2],
                "category": row[3],
                "category_name": row[4]
            }
            for row in rows
        ]


        return jsonify(documents)


    except Exception as e:

        print(
            f"❌ Error in /get-documents: {e}"
        )

        traceback.print_exc()


        return jsonify({
            "error": "Unable to load documents."
        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)


# ============================================================
# DOCUMENT UPLOAD
# ============================================================

@documents_bp.route(
    "/upload-document",
    methods=["POST"]
)
def upload_document():

    # ---------------------------------------------------------
    # 1. Authentication
    # ---------------------------------------------------------

    if "user_id" not in session:
        return redirect("/login")


    conn = None
    cur = None


    try:

        # -----------------------------------------------------
        # 2. Read form data
        # -----------------------------------------------------

        files = request.files.getlist(
            "file"
        )

        folder_id_raw = request.form.get(
            "folder_id",
            ""
        ).strip()

        title = request.form.get(
            "title",
            ""
        ).strip()


        # -----------------------------------------------------
        # 3. Validate folder ID
        # -----------------------------------------------------

        folder_id = (
            int(folder_id_raw)
            if folder_id_raw.isdigit()
            else None
        )


        # -----------------------------------------------------
        # 4. Validate files
        # -----------------------------------------------------

        valid_files = [
            file
            for file in files
            if file and file.filename
        ]


        if not valid_files:

            flash(
                "Please select at least one document.",
                "error"
            )

            return redirect("/dashboard")


        # -----------------------------------------------------
        # 5. Validate title
        # -----------------------------------------------------

        if not title:

            flash(
                "Please enter a document title.",
                "error"
            )

            return redirect("/dashboard")


        # -----------------------------------------------------
        # 6. Database connection
        # -----------------------------------------------------

        conn = get_db_connection()
        cur = conn.cursor()


        # -----------------------------------------------------
        # 7. Process files
        # -----------------------------------------------------

        for file in valid_files:

            original_filename = file.filename


            # -------------------------------------------------
            # Validate extension
            # -------------------------------------------------

            if not allowed_file(
                original_filename
            ):

                raise ValueError(
                    f"Unsupported file type: "
                    f"{original_filename}"
                )


            # -------------------------------------------------
            # Secure filename
            # -------------------------------------------------

            filename = secure_filename(
                original_filename
            )


            if not filename:

                raise ValueError(
                    "Invalid file name."
                )


            # -------------------------------------------------
            # Read actual file into memory
            # -------------------------------------------------

            file_data = file.read()


            if not file_data:

                raise ValueError(
                    f"Uploaded file is empty: "
                    f"{filename}"
                )


            # -------------------------------------------------
            # Insert document + PDF bytes into PostgreSQL
            # -------------------------------------------------

            cur.execute(
                """
                INSERT INTO files
                (
                    userid,
                    folderid,
                    filename,
                    title,
                    attachment,
                    attachment_data
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    session["user_id"],
                    folder_id,
                    filename,
                    title,
                    None,
                    file_data
                )
            )


        # -----------------------------------------------------
        # 8. Commit
        # -----------------------------------------------------

        conn.commit()


        print(
            "✅ Document uploaded and stored "
            "in PostgreSQL."
        )


        flash(
            "Document uploaded successfully!",
            "success"
        )


    except Exception as e:

        if conn:

            try:
                conn.rollback()
            except Exception:
                pass


        print(
            f"❌ Upload failed: {e}"
        )

        traceback.print_exc()


        flash(
            "Upload failed. Please try again.",
            "error"
        )


    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)


    return redirect(
        "/dashboard"
    )


# ============================================================
# DOCUMENT DELETION
# ============================================================

@documents_bp.route(
    "/delete-document/<int:doc_id>",
    methods=["GET", "POST"]
)
def delete_document(doc_id):

    if "user_id" not in session:
        return redirect("/login")


    conn = None
    cur = None


    try:

        user_id = session["user_id"]


        conn = get_db_connection()
        cur = conn.cursor()


        # -----------------------------------------------------
        # Find document owned by current user
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


        if not row:

            flash(
                "Document not found.",
                "error"
            )

            return redirect(
                "/dashboard"
            )


        file_id = row[0]
        attachment = row[1]


        # -----------------------------------------------------
        # Delete database record
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


        if cur.rowcount != 1:

            conn.rollback()


            flash(
                "Document could not be deleted.",
                "error"
            )


            return redirect(
                "/dashboard"
            )


        conn.commit()


        # -----------------------------------------------------
        # Delete physical file
        # -----------------------------------------------------

        if attachment:

            try:

                if os.path.exists(
                    attachment
                ):

                    os.remove(
                        attachment
                    )

                    print(
                        f"🗑️ Deleted file: "
                        f"{attachment}"
                    )

            except Exception as file_error:

                print(
                    "⚠️ Database record deleted, "
                    f"but physical file could not "
                    f"be deleted: {file_error}"
                )


        flash(
            "Document deleted successfully!",
            "success"
        )


    except Exception as e:

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

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)


    return redirect(
        "/dashboard"
    )


# ============================================================
# DOCUMENT DOWNLOAD
# ============================================================

@documents_bp.route(
    "/download/<filename>"
)
def download_file(filename):

    if "user_id" not in session:
        return redirect("/login")


    conn = None
    cur = None


    try:

        user_id = session["user_id"]


        conn = get_db_connection()
        cur = conn.cursor()


        # -----------------------------------------------------
        # Verify ownership
        # -----------------------------------------------------

        cur.execute(
            """
            SELECT
                fileid,
                attachment,
                filename
            FROM files
            WHERE userid = %s
              AND filename = %s
            LIMIT 1
            """,
            (
                user_id,
                filename
            )
        )


        row = cur.fetchone()


        if not row:

            return jsonify({
                "error": "Document not found."
            }), 404


        attachment = row[1]
        stored_filename = row[2]


    except Exception as e:

        print(
            f"❌ Error verifying download: {e}"
        )

        traceback.print_exc()


        return jsonify({
            "error": "Unable to access document."
        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)


    # ---------------------------------------------------------
    # Send stored file
    # ---------------------------------------------------------

    if attachment and os.path.exists(
        attachment
    ):

        return send_from_directory(
            os.path.dirname(
                attachment
            ),
            os.path.basename(
                attachment
            ),
            as_attachment=True
        )


    # ---------------------------------------------------------
    # Fallback upload directory
    # ---------------------------------------------------------

    upload_folder = os.getenv(
        "UPLOAD_FOLDER",
        os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.abspath(
                        __file__
                    )
                )
            ),
            "..",
            "uploads"
        )
    )


    upload_folder = os.path.abspath(
        upload_folder
    )


    file_path = os.path.join(
        upload_folder,
        stored_filename
    )


    if os.path.exists(
        file_path
    ):

        return send_from_directory(
            upload_folder,
            stored_filename,
            as_attachment=True
        )


    return jsonify({
        "error": "Document file not found."
    }), 404

# =========================================================
# STEP 8E — INLINE PDF PREVIEW
# =========================================================

@documents_bp.route("/preview/<int:doc_id>")
def preview_file(doc_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = None
    cur = None

    try:

        user_id = session["user_id"]

        conn = get_db_connection()
        cur = conn.cursor()

        # -----------------------------------------------------
        # Verify document ownership
        # -----------------------------------------------------

        cur.execute(
            """
            SELECT
                fileid,
                attachment,
                filename
            FROM files
            WHERE userid = %s
              AND fileid = %s
            LIMIT 1
            """,
            (
                user_id,
                doc_id
            )
        )

        row = cur.fetchone()

        if not row:
            return jsonify({
                "error": "Document not found."
            }), 404

        file_id = row[0]
        attachment = row[1]
        stored_filename = row[2]

        # -----------------------------------------------------
        # Determine actual file path
        # -----------------------------------------------------

        if attachment:
            file_path = attachment
        else:
            file_path = os.path.join(
                current_app.config["UPLOAD_FOLDER"],
                stored_filename
            )

        # -----------------------------------------------------
        # Check file exists
        # -----------------------------------------------------

        if not os.path.exists(file_path):
            return jsonify({
                "error": "Document file not found."
            }), 404

        # -----------------------------------------------------
        # PDF preview only
        # -----------------------------------------------------

        if not stored_filename.lower().endswith(".pdf"):
            return jsonify({
                "error": "Only PDF documents can be previewed."
            }), 400

        # -----------------------------------------------------
        # Return PDF INLINE
        # -----------------------------------------------------

        return send_file(
            file_path,
            mimetype="application/pdf",
            as_attachment=False
        )

    except Exception as e:

        print(
            f"❌ Error previewing document: {e}"
        )

        traceback.print_exc()

        return jsonify({
            "error": "Unable to preview document."
        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)
