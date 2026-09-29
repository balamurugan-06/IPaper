"""
IPaper Summary Routes

Handles AI summary generation and summary retrieval/download.
"""

import os
import traceback
from datetime import datetime


from flask import (
    Blueprint,
    jsonify,
    redirect,
    request,
    send_from_directory,
    session
)





from app.services.database import (
    get_db_connection,
    release_db_connection
)
from app.services.summary_service import summarizer

summaries_bp = Blueprint(
    "summaries",
    __name__
)


@summaries_bp.route("/getSummary/<int:doc_id>")
def getSummary(doc_id):

    # ---------------------------------------------------------
    # 1. Authentication
    # ---------------------------------------------------------

    if 'user_id' not in session:
        return jsonify({
            "error": "Authentication required."
        }), 401

    conn = None
    cur = None

    try:

        user_id = session['user_id']

        # -----------------------------------------------------
        # 2. Verify document ownership
        # -----------------------------------------------------

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT fileid
            FROM files
            WHERE fileid = %s
              AND userid = %s
            """,
            (
                doc_id,
                user_id
            )
        )

        document = cur.fetchone()

        if not document:
            return jsonify({
                "error": "Document not found."
            }), 404

        # -----------------------------------------------------
        # 3. Get latest summary
        # -----------------------------------------------------

        cur.execute(
            """
            SELECT summary
            FROM summarygenerate
            WHERE docid = %s
            ORDER BY createdat DESC
            LIMIT 1
            """,
            (doc_id,)
        )

        row = cur.fetchone()

        if row:
            return jsonify({
                "summary": row[0]
            })

        return jsonify({
            "summary": None
        })

    except Exception as e:

        print(
            f"❌ Error retrieving summary: {e}"
        )

        traceback.print_exc()

        return jsonify({
            "error": "Unable to retrieve summary."
        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)


# =========================================================
# STEP 9E — PART 4A
# GET SUMMARY HISTORY
# =========================================================

@summaries_bp.route("/getSummaryHistory")
def getSummaryHistory():

    # ---------------------------------------------------------
    # 1. Authentication
    # ---------------------------------------------------------

    if 'user_id' not in session:
        return jsonify({
            "error": "Authentication required."
        }), 401

    conn = None
    cur = None

    try:

        user_id = session['user_id']

        # -----------------------------------------------------
        # 2. Get user's saved summaries
        # -----------------------------------------------------

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                sg.summaryid,
                sg.summarytemplateid,
                sg.modelname,
                sg.createdat,
                sg.docid,
                f.title,
                f.filename
            FROM summarygenerate sg

            INNER JOIN files f
                ON f.fileid = sg.docid

            WHERE f.userid = %s

            ORDER BY sg.createdat DESC

            LIMIT 20
            """,
            (user_id,)
        )

        rows = cur.fetchall()

        # -----------------------------------------------------
        # 3. Prepare response
        # -----------------------------------------------------

        history = []

        for row in rows:

            history.append({
                "summaryid": row[0],
                "summarytemplateid": row[1],
                "modelname": row[2],
                "createdat": (
                    row[3].isoformat()
                    if row[3]
                    else None
                ),
                "docid": row[4],
                "document_title": (
                    row[5]
                    or row[6]
                    or "Untitled Research Paper"
                ),
                "filename": row[6]
            })

        return jsonify({
            "success": True,
            "history": history
        })

    except Exception as e:

        print(
            f"❌ Error retrieving summary history: {e}"
        )

        traceback.print_exc()

        return jsonify({
            "success": False,
            "error": "Unable to retrieve summary history."
        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)

@summaries_bp.route('/download_summary/<int:docId>')
def download_summary(docId):

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
        # 2. Verify document ownership
        # -----------------------------------------------------

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT fileid
            FROM files
            WHERE fileid = %s
              AND userid = %s
            """,
            (
                docId,
                user_id
            )
        )

        document = cur.fetchone()

        if not document:

            return jsonify({
                "error": "Document not found."
            }), 404

    except Exception as e:

        print(
            f"❌ Error verifying summary download: {e}"
        )

        traceback.print_exc()

        return jsonify({
            "error": "Unable to access summary."
        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)

    # ---------------------------------------------------------
    # 3. Locate generated summary PDF
    # ---------------------------------------------------------

    summary_filename = (
        f"summary_{docId}.pdf"
    )

    summary_path = os.path.join(
        os.getenv(
            "UPLOAD_FOLDER",
            os.path.join(
                os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(
                            os.path.abspath(__file__)
                        )
                    )
                ),
                "uploads"
            )
        ),
        summary_filename
    )

    if not os.path.exists(summary_path):

        return jsonify({
            "error": "Summary PDF not found."
        }), 404

    # ---------------------------------------------------------
    # 4. Send summary PDF
    # ---------------------------------------------------------

    return send_from_directory(
        os.path.dirname(summary_path),
        summary_filename,
        as_attachment=True
    )

@summaries_bp.route("/generateSummary", methods=["POST"])
def generateSummary():

    # ---------------------------------------------------------
    # 1. Authentication
    # ---------------------------------------------------------

    if 'user_id' not in session:

        return jsonify({
            "error": "Authentication required."
        }), 401

    conn = None
    cur = None

    try:

        # -----------------------------------------------------
        # 2. Read request data
        # -----------------------------------------------------

        data = request.get_json(silent=True) or {}

        doc_name = data.get(
            "document_name"
        )

        doc_id_raw = data.get(
            "document_id"
        )

        template_prompt = data.get(
            "template_prompt",
            ""
        )

        summary_template_id = data.get(
            "summaryTemplate"
        )

        # -----------------------------------------------------
        # 3. Validate required values
        # -----------------------------------------------------

        if not doc_name:

            return jsonify({
                "error": "Document name is required."
            }), 400

        if doc_id_raw is None:

            return jsonify({
                "error": "Document ID is required."
            }), 400

        try:

            doc_id = int(doc_id_raw)

        except (TypeError, ValueError):

            return jsonify({
                "error": "Invalid document ID."
            }), 400

        

        # -----------------------------------------------------
        # 4. Verify document ownership
        # -----------------------------------------------------

        conn = get_db_connection()
        cur = conn.cursor()

                # -----------------------------------------------------
        # 4. Verify membership and template access
        # -----------------------------------------------------

        if summary_template_id is None:

            return jsonify({
                "error": "Summary template is required."
            }), 400

        try:

            summary_template_id = int(
                summary_template_id
            )

        except (TypeError, ValueError):

            return jsonify({
                "error": "Invalid summary template."
            }), 400

        # Get the user's current membership
        cur.execute(
            """
            SELECT membership
            FROM users
            WHERE userid = %s
            """,
            (
                session['user_id'],
            )
        )

        user_row = cur.fetchone()

        membership = 'Free'

        if user_row and user_row[0]:

            membership = user_row[0]

        if membership not in [
            'Free',
            'Professional',
            'Professional Plus'
        ]:

            membership = 'Free'

        # Verify that this template is available
        # for the user's membership level.
        cur.execute(
            """
            SELECT
                t.summarytemplateid,
                t.templatename,
                t.category,
                t.promptinstructions,
                a.minimum_plan
            FROM uploadsummarytemplates t
            INNER JOIN template_plan_access a
                ON a.summarytemplateid =
                   t.summarytemplateid
            WHERE
                t.summarytemplateid = %s
                AND
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
            LIMIT 1
            """,
            (
                summary_template_id,
                membership
            )
        )

        template_row = cur.fetchone()

        if not template_row:

            return jsonify({
                "error":
                    "This summary template is not "
                    "available for your membership plan."
            }), 403

        # -----------------------------------------------------
        # Use the prompt stored in the database.
        # Do NOT trust the prompt sent by the browser.
        # -----------------------------------------------------

        summary_template_id = template_row[0]

        template_name = template_row[1]

        template_category = template_row[2]

        template_prompt = template_row[3]

        minimum_plan = template_row[4]

        if not template_prompt:

            return jsonify({
                "error":
                    "The selected summary template "
                    "does not contain prompt instructions."
            }), 500

        print(
            f"Membership: {membership}"
        )

        print(
            f"Template: {template_name} "
            f"(ID: {summary_template_id})"
        )

        print(
            f"Required plan: {minimum_plan}"
        )

        cur.execute(
            """
            SELECT
                fileid,
                filename,
                attachment
            FROM files
            WHERE fileid = %s
              AND userid = %s
            """,
            (
                doc_id,
                session['user_id']
            )
        )

        document = cur.fetchone()

        if not document:

            return jsonify({
                "error": "Document not found."
            }), 404

        stored_file_id = document[0]
        stored_filename = document[1]
        attachment_path = document[2]

        # -----------------------------------------------------
        # 5. Determine actual document path
        # -----------------------------------------------------

        if attachment_path:

            doc_path = attachment_path

        else:

            doc_path = os.path.join(
                os.getenv(
                    "UPLOAD_FOLDER",
                    os.path.join(
                        os.path.dirname(
                            os.path.dirname(
                                os.path.dirname(
                                    os.path.abspath(__file__)
                                )
                            )
                        ),
                        "uploads"
                    )
                ),
                stored_filename
            )

        # -----------------------------------------------------
        # 6. Verify physical document exists
        # -----------------------------------------------------

        if not os.path.exists(doc_path):

            return jsonify({
                "error": "Document file not found."
            }), 404

        # -----------------------------------------------------
        # 7. Generate AI summary
        # -----------------------------------------------------

                # -----------------------------------------------------
        # 8. Generate AI summary
        # -----------------------------------------------------

        tem_prompt = template_prompt.strip()

        print(
            f"Generating summary "
            f"for document {stored_file_id}"
        )

        summary = summarizer(
            doc_path,
            tem_prompt,
            stored_file_id
        )

        if not summary:

            return jsonify({
                "error": "Summary generation returned no result."
            }), 500

        # -----------------------------------------------------
        # 8. Model information
        # -----------------------------------------------------

        model_name = "gpt-4o-mini"
        now = datetime.now()

        # -----------------------------------------------------
        # 9. Check existing summary
        # -----------------------------------------------------

        cur.execute(
            """
            SELECT summaryid
            FROM summarygenerate
            WHERE docid = %s
            LIMIT 1
            """,
            (stored_file_id,)
        )

        existing = cur.fetchone()

        # -----------------------------------------------------
        # 10. Update existing summary
        # -----------------------------------------------------

        if existing:

            cur.execute(
                """
                UPDATE summarygenerate
                SET
                    summarytemplateid = %s,
                    modelname = %s,
                    summary = %s,
                    createdat = %s
                WHERE docid = %s
                """,
                (
                    summary_template_id,
                    model_name,
                    summary,
                    now,
                    stored_file_id
                )
            )

        # -----------------------------------------------------
        # 11. Insert new summary
        # -----------------------------------------------------

        else:

            cur.execute(
                """
                INSERT INTO summarygenerate
                (
                    summarytemplateid,
                    modelname,
                    summary,
                    createdat,
                    docid
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    summary_template_id,
                    model_name,
                    summary,
                    now,
                    stored_file_id
                )
            )

        # -----------------------------------------------------
        # 12. Commit database transaction
        # -----------------------------------------------------

        conn.commit()

        print(
            f"✅ Summary generated "
            f"for document {stored_file_id}"
        )

        return jsonify({
            "summary": summary
        })

    except Exception as e:

        # -----------------------------------------------------
        # 13. Roll back database
        # -----------------------------------------------------

        if conn:

            try:
                conn.rollback()
            except Exception:
                pass

        print(
            f"❌ Summary generation failed: {e}"
        )

        traceback.print_exc()

        return jsonify({
            "error": "Summary generation failed. "
                     "Please try again."
        }), 500

    finally:

        # -----------------------------------------------------
        # 14. Close database resources
        # -----------------------------------------------------

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)

# =========================================================
# STEP 9E — PART 5A
# CLEAR SUMMARY HISTORY
# =========================================================

@summaries_bp.route("/clearSummaryHistory", methods=["DELETE"])
def clearSummaryHistory():

    # ---------------------------------------------------------
    # 1. Authentication
    # ---------------------------------------------------------

    if 'user_id' not in session:
        return jsonify({
            "success": False,
            "error": "Authentication required."
        }), 401

    conn = None
    cur = None

    try:

        user_id = session['user_id']

        # -----------------------------------------------------
        # 2. Delete only summaries belonging to this user
        # -----------------------------------------------------

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM summarygenerate
            WHERE docid IN (
                SELECT fileid
                FROM files
                WHERE userid = %s
            )
            """,
            (user_id,)
        )

        deleted_count = cur.rowcount

        conn.commit()

        return jsonify({
            "success": True,
            "deleted": deleted_count
        })

    except Exception as e:

        if conn:
            try:
                conn.rollback()
            except Exception:
                pass

        print(
            f"❌ Error clearing summary history: {e}"
        )

        traceback.print_exc()

        return jsonify({
            "success": False,
            "error": "Unable to clear summary history."
        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            release_db_connection(conn)