"""
IPaper Database Service

Centralized PostgreSQL connection-pool management.
"""


import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")

DB_MIN_CONN = 1

DB_MAX_CONN = int(
    os.getenv("DB_MAX_CONN", "20")
)


# ============================================================
# DATABASE CONNECTION POOL
# ============================================================

db_pool = None


def create_db_pool():
    """
    Create the PostgreSQL connection pool.
    """

    global db_pool

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is not configured."
        )

    try:

        db_pool = pool.SimpleConnectionPool(
            DB_MIN_CONN,
            DB_MAX_CONN,
            DATABASE_URL,
            sslmode="require"
        )

        print(
            "✅ Database connection pool created."
        )

        return db_pool

    except Exception as e:

        print(
            f"❌ Failed to create database pool: {e}"
        )

        raise


# ============================================================
# INITIALIZE DATABASE POOL
# ============================================================

create_db_pool()


# ============================================================
# GET DATABASE CONNECTION
# ============================================================

def get_db_connection():

    """
    Get a connection from the PostgreSQL pool.

    If getting a connection fails, recreate the pool
    and try once more.
    """

    global db_pool

    try:

        return db_pool.getconn()

    except Exception as e:

        print(
            f"⚠️ DB pool getconn failed: {e}"
        )

        reset_db_pool()

        return db_pool.getconn()


# ============================================================
# RELEASE DATABASE CONNECTION
# ============================================================

def release_db_connection(conn):

    """
    Return a connection to the PostgreSQL pool.
    """

    global db_pool

    if not db_pool or not conn:
        return

    try:

        db_pool.putconn(conn)

    except Exception as e:

        print(
            f"⚠️ Failed to return "
            f"connection to pool: {e}"
        )


# ============================================================
# RESET DATABASE POOL
# ============================================================

def reset_db_pool():

    """
    Recreate the PostgreSQL connection pool.
    """

    global db_pool

    try:

        print(
            "🔁 Resetting DB pool..."
        )

        if db_pool:

            try:

                db_pool.closeall()

            except Exception:

                pass

        db_pool = pool.SimpleConnectionPool(
            DB_MIN_CONN,
            DB_MAX_CONN,
            DATABASE_URL,
            sslmode="require"
        )

        print(
            "✅ DB pool reset"
        )

    except Exception as e:

        print(
            f"❌ Failed to reset DB pool: {e}"
        )

        raise