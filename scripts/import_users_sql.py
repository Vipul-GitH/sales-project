"""Replace project users with users from the supplied phpMyAdmin SQL dump."""

from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path

from database import connection


DEFAULT_SOURCE = Path(r"C:\Users\user\Downloads\users.sql")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"


def parse_users(source: Path) -> list[list[str]]:
    sql = source.read_text(encoding="utf-8-sig")
    marker = "INSERT INTO " + chr(96) + "users" + chr(96)
    statements = re.findall(re.escape(marker) + r".*?VALUES\s*(.*?);", sql, re.DOTALL)
    if not statements:
        raise ValueError("The SQL dump does not contain a users INSERT statement.")

    rows = []
    for values in statements:
        tuples = re.findall(r"\((.*?)\)(?:,|\s*$)", values, re.DOTALL)
        rows.extend(
            next(csv.reader(io.StringIO(item), delimiter=",", quotechar="'", escapechar="\\", skipinitialspace=True))
            for item in tuples
        )
    if not rows or any(len(row) not in {11, 12} for row in rows):
        raise ValueError("The users SQL rows do not match the supported 11/12-column formats.")
    return rows


def clean(value: str) -> str | None:
    value = value.strip()
    return None if value.upper() == "NULL" else value


def project_role(source_role: str, name: str) -> tuple[str, int]:
    normalized = source_role.strip().lower()
    if name.strip().lower() in {"dr vishu bhasin", "dr vipul bhasin"}:
        return "Admin", 1
    if normalized in {"administrator", "admin"}:
        return "Admin", 1
    if normalized in {"asset_manager", "team leader", "team_leader"}:
        return "Team Leader", 2
    return "Executive", 3


def import_users(source: Path) -> tuple[int, int]:
    rows = parse_users(source)
    user_schema = SCHEMA_PATH.read_text(encoding="utf-8").split(";", 1)[0].strip()
    prepared = []
    for row in rows:
        if len(row) == 12:
            user_id, name, _old_password, contact, departments, source_role, _old_role_id, status, _updated, dob, designation, department_id = row
        else:
            user_id, name, _old_password, contact, departments, source_role, status, _updated, dob, designation, department_id = row
        dob_value = clean(dob)
        role, role_id = project_role(source_role, name)
        prepared.append(
            (
                int(user_id), name.strip(), contact.strip(),
                clean(departments), role, role_id, status.strip(), dob_value,
                clean(designation), int(department_id) if clean(department_id) else None,
            )
        )

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            try:
                cur.execute("DROP TABLE IF EXISTS users")
                cur.execute(user_schema)
                cur.executemany(
                    """INSERT INTO users
                       (id,name,contact,departments,role,role_id,status,dob,designation,department_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    prepared,
                )
            finally:
                cur.execute("SET FOREIGN_KEY_CHECKS=1")
    return len(prepared), 0


if __name__ == "__main__":
    source_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_SOURCE
    imported, _ = import_users(source_path)
    print(f"Imported {imported} users from {source_path}")
    print("Login passwords are derived directly from DOB (DDMMYYYY).")
