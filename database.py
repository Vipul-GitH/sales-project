"""MySQL/MariaDB data layer for the referral-sales application."""
import os
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

DB_HOST = os.getenv("REFERRAL_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("REFERRAL_DB_PORT", "3306"))
DB_USER = os.getenv("REFERRAL_DB_USER", "root")
DB_PASSWORD = os.getenv("REFERRAL_DB_PASSWORD", "")
DB_NAME = os.getenv("REFERRAL_DB_NAME", "referral_sales")


def ensure_database():
    """Create the application database on the local XAMPP server if needed."""
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        charset="utf8mb4", autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()


@contextmanager
def connection():
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME, charset="utf8mb4",
        cursorclass=DictCursor, autocommit=False,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all(sql, params=()):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def fetch_one(sql, params=()):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.lastrowid
