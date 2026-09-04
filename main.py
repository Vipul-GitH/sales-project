"""Single-command launcher for the Referral Sales application.

Run from the project directory with: python main.py
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
MYSQL_ROOT = Path(r"C:\xampp\mysql")
MYSQL_EXE = MYSQL_ROOT / "bin" / "mysqld.exe"
MYSQL_CONFIG = MYSQL_ROOT / "bin" / "my.ini"
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306
WEB_PORT = 3020
CERT_FILE = PROJECT_ROOT / "certs" / "fullchain.pem"
KEY_FILE = PROJECT_ROOT / "certs" / "privkey.pem"
PUBLIC_HOST = os.getenv("REFERRAL_PUBLIC_HOST", "127.0.0.1")


def port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def use_project_virtualenv() -> None:
    """Re-run under the project's environment when started with `python main.py`."""
    if not VENV_PYTHON.exists():
        raise SystemExit(
            "Project environment is missing. Create it once with:\n"
            "  py -m venv .venv\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        )

    if Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        completed = subprocess.run([str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])
        raise SystemExit(completed.returncode)


def start_mysql() -> None:
    if port_is_open(MYSQL_HOST, MYSQL_PORT):
        print(f"MySQL is already running on port {MYSQL_PORT}.")
        return

    missing = [path for path in (MYSQL_EXE, MYSQL_CONFIG) if not path.exists()]
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise SystemExit(f"Required database files are missing:\n{formatted}")

    print("Starting portable MySQL...")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            str(MYSQL_EXE),
            f"--defaults-file={MYSQL_CONFIG}",
        ],
        cwd=MYSQL_ROOT,
        creationflags=creation_flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if port_is_open(MYSQL_HOST, MYSQL_PORT):
            print("MySQL is ready.")
            return
        time.sleep(0.5)
    raise SystemExit("MySQL did not become ready within 30 seconds.")


def main() -> None:
    os.chdir(PROJECT_ROOT)
    use_project_virtualenv()
    start_mysql()

    from database import ensure_database
    from scripts.init_db import backfill_audit, run_schema, seed

    ensure_database()
    from database import connection
    with connection() as conn:
        run_schema(conn)
        seed(conn)
        backfill_audit(conn)

    missing_tls = [path for path in (CERT_FILE, KEY_FILE) if not path.is_file()]
    if missing_tls:
        formatted = "\n".join(f"  - {path}" for path in missing_tls)
        raise SystemExit(f"Required HTTPS certificate files are missing:\n{formatted}")

    if port_is_open(MYSQL_HOST, WEB_PORT):
        raise SystemExit(
            f"Port {WEB_PORT} is already in use. The app may already be running at "
            f"https://{PUBLIC_HOST}:{WEB_PORT}/login"
        )

    from app import app

    print(f"Opening Referral Sales at https://{PUBLIC_HOST}:{WEB_PORT}/login")
    print(f"TLS certificate: {CERT_FILE}")
    print("Press Ctrl+C to stop the web application.")
    app.run(debug=False, host="0.0.0.0", port=WEB_PORT, use_reloader=False,
            ssl_context=(str(CERT_FILE), str(KEY_FILE)))


if __name__ == "__main__":
    main()
