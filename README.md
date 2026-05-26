# odoo-exterior-web

A small SaaS web app on top of [`odoo-studio-extractor`](../odoo-studio-extractor).

Users sign up, register one or more Odoo instances, and use a read-only
**Odoo toolbox**: **Studio Audit** (reverse-engineer Studio customizations),
**Data Explorer** (browse live records and export CSV/JSON), and **Saved
Queries** (reusable export configurations) — all from a browser, without
installing anything inside Odoo.

This repository is the **MVP**. It is deliberately small:

- Django 5.x
- SQLite by default (Postgres-ready settings via env vars)
- Synchronous audit execution (structured for later move to Celery)
- Bootstrap 5 via CDN, no front-end build step
- Static assets served by **WhiteNoise** (works the same with `DEBUG=True`
  or `DEBUG=False`, no `collectstatic` required in development)

---

## Architecture

- **`accounts/`** — registration, login, logout (uses Django auth).
- **`instances/`** — `OdooInstance` model + CRUD + connection test.
  Passwords are **encrypted at rest** with Fernet (AES-128 in CBC + HMAC),
  using a key derived from `FIELD_ENCRYPTION_KEY` (or `SECRET_KEY` as a
  fallback for local dev).
- **`audits/`** — `AuditRun` model, a `services.py` layer that wraps the
  `odoo-studio-extractor` engine, and views to display + download the
  generated reports. `data_services.py` provides read-only live Odoo fetches
  for Data Explorer and Saved Queries.
- **`data_explorer/`** — browse live Odoo records using the latest completed
  audit as a field catalog; CSV/JSON export.
- **`saved_queries/`** — reusable Data Explorer configurations (settings
  only — no exported data or credentials).
- **Service layer** (`audits/services.py`) is the integration point with
  the extractor package. Replace its body with a Celery task later without
  touching the views.

---

## Requirements

- Python **3.11+**
- The [`odoo-studio-extractor`](../odoo-studio-extractor) package, installed
  in the same virtual environment.

---

## Setup

```bash
# 1. Clone both repos side by side
#    .../odoo-studio-extractor
#    .../odoo-exterior-web

cd odoo-exterior-web
python -m venv .venv
. .venv/Scripts/activate            # PowerShell on Windows
# source .venv/bin/activate         # Linux / macOS

# 2. Install the extractor (editable, from the sibling repo)
pip install -e ../odoo-studio-extractor

# 3. Install the web app dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env              # or `cp .env.example .env`
# then edit .env and set DJANGO_SECRET_KEY and FIELD_ENCRYPTION_KEY

# 5. Initialize the database
python manage.py migrate

# 6. (Optional) Create an admin user
python manage.py createsuperuser

# 7. Run the dev server
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and:

1. Register an account.
2. Add an Odoo instance (URL, database, username, password).
3. Click **Test connection**.
4. Click **Run audit**.
5. Open the audit detail page and download the Markdown / JSON report.

---

## Environment variables

See `.env.example`. The web app reads:

| Variable                  | Purpose                                          |
|---------------------------|--------------------------------------------------|
| `DJANGO_SECRET_KEY`       | Django cryptographic signing key                 |
| `DJANGO_DEBUG`            | `1` / `0` (default `0`)                          |
| `DJANGO_ALLOWED_HOSTS`    | Comma-separated host list                        |
| `FIELD_ENCRYPTION_KEY`    | Key used to encrypt Odoo passwords at rest. If unset, derived from `DJANGO_SECRET_KEY`. |
| `DB_ENGINE`               | e.g. `django.db.backends.postgresql` (optional)  |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | Postgres settings (optional) |

---

## Security notes

- Odoo credentials are stored in the `OdooInstance.encrypted_password` column
  as a Fernet token. Plain-text values never leave the request/response
  cycle.
- The underlying `OdooClient` from `odoo-studio-extractor` exposes
  **read-only** operations only (`search`, `read`, `search_read`, `count`).
  The web app cannot mutate the target Odoo database.
- Always use a **dedicated read-only Odoo user** for the credentials you
  store here — this is your second line of defense.
- Never commit `.env`.

---

## Roadmap

- Async audit execution via Celery + Redis.
- Per-user API keys.
- Team / organization sharing.
- Diff between two audits of the same instance.
- HTML report renderer.
