import os
import sqlite3
from pathlib import Path
from typing import Optional

# agentic/ is one level below root, so parent.parent is project root
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "ujjwal_rail.db"


def get_db_path() -> str:
    env_path = os.getenv("DATABASE_PATH")
    if env_path:
        p = Path(env_path)
        if not p.is_absolute():
            p = BASE_DIR / p
        return str(p)
    return str(DEFAULT_DB_PATH)


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Returns a SQLite connection with 30s busy timeout, Row factory, and WAL mode."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
    except Exception:
        pass
    return conn


def create_in_memory_db() -> sqlite3.Connection:
    """Connects to the persistent Ujjwal Rail database or in-memory fallback."""
    db_file = get_db_path()
    if os.path.exists(db_file):
        return get_connection(db_file)
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
