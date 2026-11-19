import mysql.connector
from mysql.connector import Error, errorcode
from contextlib import contextmanager
from config import Config

def get_db_connection():
    """
    Establishes and returns a fresh connection to the MySQL database.
    Raises mysql.connector.Error on connection failure.
    """
    try:
        connection = mysql.connector.connect(**Config.get_db_config())
        return connection
    except Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            raise RuntimeError(
                f"MySQL Authentication Failed: Check username or password in config.py / .env. [User: {Config.DB_USER}]"
            ) from err
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            raise RuntimeError(
                f"Database '{Config.DB_NAME}' does not exist! Please run workbench_setup.sql in MySQL Workbench first."
            ) from err
        else:
            raise RuntimeError(
                f"MySQL Connection Error [{err.errno}]: {err.msg}. Ensure MySQL Server is running on port {Config.DB_PORT}."
            ) from err

@contextmanager
def get_db_cursor(commit=False, dictionary=True):
    """
    Context manager providing a database cursor with automatic cleanup and transaction management.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield cursor, conn
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def execute_query(query, params=None, fetch=None, commit=False):
    """
    Executes a SQL query with optional parameter binding.
    fetch: 'one' | 'all' | None
    commit: True for INSERT/UPDATE/DELETE
    Returns: dict (for 'one'), list of dicts (for 'all'), or lastrowid/rowcount.
    """
    with get_db_cursor(commit=commit, dictionary=True) as (cursor, conn):
        cursor.execute(query, params or ())
        if fetch == 'one':
            return cursor.fetchone()
        elif fetch == 'all':
            return cursor.fetchall()
        elif commit:
            return cursor.lastrowid or cursor.rowcount
        return None

def execute_procedure(proc_name, params=()):
    """
    Calls a MySQL Stored Procedure and retrieves all result rows from its result set(s).
    Returns a list of dict rows from the primary stored result.
    """
    with get_db_cursor(commit=True, dictionary=True) as (cursor, conn):
        cursor.callproc(proc_name, params)
        results = []
        for result in cursor.stored_results():
            results.extend(result.fetchall())
        return results

def check_db_health():
    """Verifies that the database is accessible and seeded."""
    try:
        with get_db_cursor(commit=False) as (cursor, _):
            cursor.execute("SELECT 1 AS ok")
            row = cursor.fetchone()
            return row and row.get('ok') == 1
    except Exception:
        return False

