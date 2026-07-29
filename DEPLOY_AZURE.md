# Deploying to Azure (SQL Server build)

## 1. Push to GitHub
The .gitignore already excludes the local database and secret key. Push the repo.

## 2. App Service → Deployment Center
Connect this GitHub repo. Azure builds from requirements.txt.

## 3. App Service → Settings → Environment variables
Add these. The five AZURE_SQL_* values come straight from your database:

    AZURE_SQL_SERVER      <your-server>.database.windows.net
    AZURE_SQL_DATABASE    <your-database-name>
    AZURE_SQL_USER        <admin login>
    AZURE_SQL_PASSWORD    <admin password>
    AZURE_SQL_PORT        1433

    CHECKIN_SECRET        <a long random string; run:  python -c "import secrets;print(secrets.token_urlsafe(48))">
    CHECKIN_ADMIN_PASSWORD  <the admin-gate password; defaults to admin1234 if unset>

(You do NOT need CHECKIN_DATABASE_URL — the app assembles it from the AZURE_SQL_* values.
 If you'd rather set it directly, it overrides them.)

## 4. Startup command
See startup.txt.

## 5. ODBC driver
Azure App Service for Linux includes the Microsoft ODBC Driver 18 for SQL Server,
which pyodbc needs. If a local run can't find it, install "ODBC Driver 18 for SQL Server".

## 6. First boot
The app connects, creates all its tables automatically, and seeds the 9 departments.
Open the site, then Settings → set the Base URL to your azurewebsites.net domain so
printed QR codes point at the right place.

## 7. Easy Auth (company login)
Enable App Service Authentication (Easy Auth) pointed at your Entra tenant. Once on,
the app reads each user's email from the header Azure injects and logs it on check-ins
and status changes. Until then everyone shows as "unknown" — nothing else breaks.
