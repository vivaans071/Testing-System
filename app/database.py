"""Database setup for Azure SQL (SQL Server).

Connection resolution order:
1. CHECKIN_DATABASE_URL  - a full SQLAlchemy URL, if you want to set it directly.
2. The five AZURE_SQL_* variables Azure exposes, assembled into a URL here so
   you can paste them straight from the portal without hand-building a string:
       AZURE_SQL_SERVER    e.g. myserver.database.windows.net
       AZURE_SQL_DATABASE  e.g. inventorymanagementdashboard-database
       AZURE_SQL_USER      the server admin login
       AZURE_SQL_PASSWORD  the admin password
       AZURE_SQL_PORT      usually 1433
3. Local SQLite fallback (storage/checkin.db) if none of the above are set, so
   the app still runs on a laptop with no database configured.
"""
import os
import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "storage")
os.makedirs(DATA_DIR, exist_ok=True)


def _build_url() -> str:
    direct = os.environ.get("CHECKIN_DATABASE_URL")
    if direct:
        return direct

    server = os.environ.get("AZURE_SQL_SERVER")
    database = os.environ.get("AZURE_SQL_DATABASE")
    user = os.environ.get("AZURE_SQL_USER")
    password = os.environ.get("AZURE_SQL_PASSWORD")
    port = os.environ.get("AZURE_SQL_PORT", "1433")
    if server and database and user and password:
        # ODBC connection string, URL-encoded so special characters in the
        # password (e.g. $, @, /) don't corrupt the SQLAlchemy URL - a very
        # common cause of "login failed" that isn't actually a bad password.
        odbc = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={server},{port};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password};"
            "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
        )
        return "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(odbc)

    # Fallback so the app still starts locally without a database configured.
    return f"sqlite:///{os.path.join(DATA_DIR, 'checkin.db')}"


DATABASE_URL = _build_url()

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,   # replace connections the server has silently dropped
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
