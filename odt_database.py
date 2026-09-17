"""Read/write connection for the existing ODT lead-management database."""
import os
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

ODT_DB_HOST = os.getenv("ODT_MYSQL_HOST", "10.1.1.67")
ODT_DB_PORT = int(os.getenv("ODT_MYSQL_PORT", "3306"))
ODT_DB_USER = os.getenv("ODT_MYSQL_USER", "root")
ODT_DB_PASSWORD = os.getenv("ODT_MYSQL_PASSWORD", "")
ODT_DB_NAME = os.getenv("ODT_MYSQL_DB", "lead_management")


@contextmanager
def odt_connection():
    if not ODT_DB_PASSWORD:
        raise RuntimeError("ODT_MYSQL_PASSWORD is not configured.")
    conn = pymysql.connect(
        host=ODT_DB_HOST, port=ODT_DB_PORT, user=ODT_DB_USER,
        password=ODT_DB_PASSWORD, database=ODT_DB_NAME,
        charset="utf8mb4", cursorclass=DictCursor, autocommit=False,
        connect_timeout=8, read_timeout=15, write_timeout=15,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
