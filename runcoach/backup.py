from __future__ import annotations

import sqlite3
from pathlib import Path


def backup_database(source: Path) -> Path:
    """Create a WAL-free SQLite backup at <source>.bak using the online backup API."""
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(source)
    dest = source.with_suffix(source.suffix + ".bak")
    src_conn = sqlite3.connect(source)
    dst_conn = sqlite3.connect(dest)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    return dest
