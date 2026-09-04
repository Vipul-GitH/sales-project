"""Initialize the database, then run the production HTTPS web server."""
import os
import time
from pathlib import Path

from database import connection, ensure_database
from scripts.init_db import backfill_audit, run_schema, seed


def initialize_database():
    last_error = None
    for attempt in range(30):
        try:
            ensure_database()
            with connection() as conn:
                run_schema(conn)
                seed(conn)
                backfill_audit(conn)
            return
        except Exception as error:
            last_error = error
            print(f"Database is not ready ({attempt + 1}/30): {error}", flush=True)
            time.sleep(2)
    raise SystemExit(f"Database did not become ready: {last_error}")


def run_server():
    cert_file = Path(os.getenv("TLS_CERT_FILE", "/app/certs/fullchain.pem"))
    key_file = Path(os.getenv("TLS_KEY_FILE", "/app/certs/privkey.pem"))
    missing = [str(path) for path in (cert_file, key_file) if not path.is_file()]
    if missing:
        raise SystemExit("Missing HTTPS files: " + ", ".join(missing))
    os.execvp("gunicorn", [
        "gunicorn",
        "--bind", "0.0.0.0:3020",
        "--workers", os.getenv("WEB_WORKERS", "2"),
        "--timeout", "60",
        "--access-logfile", "-",
        "--error-logfile", "-",
        "--certfile", str(cert_file),
        "--keyfile", str(key_file),
        "app:app",
    ])


if __name__ == "__main__":
    initialize_database()
    run_server()

