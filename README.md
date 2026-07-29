# Asset Check-In

Internal inventory tracker: put a QR label on physical equipment, scan it with a
phone to log check-ins and status changes, manage everything from an admin
dashboard. FastAPI + SQLAlchemy backend, vanilla-JS frontend, SQLite for local
dev / PostgreSQL for production.

## Features

- Asset registry with departments, owners, class, cost, purchase date
- QR + Code128 barcode generation and printable labels
- Public (no-login) mobile check-in page per asset — name, note, status update
- Status lifecycle with full history (Purchased, Qualified, Maintenance, …)
- Activity feed of notes and status changes, with unread badge
- Excel import wizard (any .xlsx: pick sheet, header row, map columns) and export
- Inventory scan mode for barcode-gun stocktakes
- Admin/viewer roles, PBKDF2 password hashing, HMAC-signed session tokens

## Run locally

```bash
pip install -r requirements.txt
python run.py            # -> http://localhost:8000
```

No configuration needed: uses SQLite at `storage/checkin.db` and generates a
local signing key. First run seeds a default admin — email `admin@example.com`,
password `changeme123`. **Change it immediately** (or set the env vars below
before first start).

## Configuration (environment variables)

| Variable | Purpose | Default |
| --- | --- | --- |
| `CHECKIN_DATABASE_URL` | SQLAlchemy database URL | SQLite in `storage/` |
| `CHECKIN_SECRET` | Token-signing key — **required in production** | generated file (dev only) |
| `CHECKIN_ADMIN_EMAIL` / `CHECKIN_ADMIN_PASSWORD` | First-run admin seed | `admin@example.com` / `changeme123` |
| `PORT` | Port for `run.py` | `8000` |

See `.env.example`. PostgreSQL URL shape:

```
postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
```

## Deploying (Azure App Service + Azure Database for PostgreSQL)

1. Create an **Azure Database for PostgreSQL – Flexible Server**, plus a
   database (e.g. `checkin`). Allow App Service access (simplest: "Allow public
   access from Azure services" in Networking, or use a VNet).
2. Create an **App Service** (Linux, Python 3.11+). Deploy this repo via
   GitHub Actions / `az webapp up` / zip deploy.
3. In App Service → **Configuration → Application settings**, set:
   - `CHECKIN_DATABASE_URL` = the PostgreSQL URL above (keep `?sslmode=require`)
   - `CHECKIN_SECRET` = long random string (`python -c "import secrets; print(secrets.token_urlsafe(48))"`)
   - `CHECKIN_ADMIN_EMAIL` / `CHECKIN_ADMIN_PASSWORD` = your real first admin
4. Set the **startup command**:
   ```
   gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000
   ```
5. Open the site, sign in, then set **Settings → QR Settings → base URL** to
   your public URL (e.g. `https://yourapp.azurewebsites.net`) so printed QR
   codes point at the server.

Tables are created and the first admin is seeded automatically on startup.

## Project layout

```
run.py                  local dev entry point
app/
  main.py               FastAPI app, startup (create tables, migrate, seed)
  database.py           engine + session factory (SQLite or PostgreSQL)
  models.py             tables: Asset, CheckIn, StatusChange, Department, Setting, User
  security.py           password hashing + bearer tokens + role guards
  seed.py               first-run admin account
  routes_auth.py        /api/auth, /api/users
  routes_admin.py       /api/... assets, activity, import/export, QR/labels, settings
  routes_public.py      /c/{code} scan page + public check-in API (no login)
  qr.py, barcode_gen.py QR / Code128 PNG generation
  static/               index.html (admin SPA), checkin.html (mobile), style.css
storage/                local SQLite + dev signing key (gitignored)
```

## Notes

- The public check-in routes are intentionally unauthenticated — scanning a QR
  mirrors a badge tap. Opening the link logs nothing; only tapping "Check in" does.
- QR/barcode/label image routes are unauthenticated because `<img src>` can't
  send auth headers; they only lead to the already-public check-in page.
- Excel import is additive-only (re-importing a file creates duplicates).
