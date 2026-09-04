# Referral Sales Follow-up System — UI Prototype

Windows setup (one time only):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Open `https://your-domain.example:3020`. The application uses the local XAMPP
MySQL/MariaDB server and automatically creates the `referral_sales` database.

HTTPS uses `certs/fullchain.pem` and `certs/privkey.pem`. Before starting on a domain,
set `REFERRAL_PUBLIC_HOST` to the domain name. The launcher binds HTTPS on all
interfaces at port `3020`.

After initial setup, start both MySQL and the web application with one command:

```powershell
python main.py
```

Press `Ctrl+C` in the terminal to stop the web application. The launcher uses
the project's `.venv` automatically, even when `python` points to a system Python.

## Docker deployment (HTTPS on port 3020)

1. Clone the repository and copy `.env.example` to `.env`.
2. Replace both placeholder secrets in `.env` with strong random values.
3. Put the domain certificate at `certs/fullchain.pem` and private key at
   `certs/privkey.pem` on the server. Certificate files are intentionally not
   stored in Git.
4. Start the application:

```bash
docker compose up -d --build
```

The app is available at `https://your-domain.example:3020/login`. MariaDB data
and uploaded files are retained in Docker volumes.

The official logo is served unchanged from `static/images/bhasin-lab-logo.jpg`.

## Project structure

```text
Sales Project/
|-- main.py             # Single-command launcher
|-- app.py              # Flask routes and application
|-- database.py         # MySQL data-access helpers
|-- requirements.txt    # Python dependencies
|-- db/
|   `-- schema.sql      # Database schema
|-- scripts/            # One-time setup, migration, and admin utilities
|-- static/             # CSS, JavaScript, images, and uploads
|-- templates/          # Jinja HTML templates
`-- tests/              # Automated workflow tests
```

Run maintenance utilities from the project root as modules, for example:

```powershell
python -m scripts.init_db
```

Import the supplied phpMyAdmin users dump with:

```powershell
python -m scripts.import_users_sql "C:\Users\user\Downloads\users.sql"
```

Users sign in with their `name`. The login password is read directly from DOB
without slashes; for example, `10/04/2003` becomes `10042003`. No separate
password column is used. Project roles are limited to `Admin`, `Team Leader`,
and `Executive`.
