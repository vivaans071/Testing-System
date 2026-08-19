import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from .database import Base, engine, SessionLocal
from .routes_admin import router as admin_router
from .routes_auth import router as auth_router
from .routes_public import router as public_router
from .seed import (seed_departments, seed_locations, seed_classes,
                   normalize_flat_locations)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _drop_legacy_location_unique():
    """Locations.name used to be globally unique. Sub-locations made that wrong:
    Acoustic and Metrology may each have a "104". Drop the old unique index on
    databases created before the change - uniqueness is now enforced per-parent
    in routes_admin instead.

    SQLite bakes UNIQUE into the table definition, so it can't be dropped
    without rebuilding the table; those databases are left alone (the app-level
    check still applies, and a fresh SQLite file gets the new schema anyway).
    """
    insp = inspect(engine)
    if "locations" not in insp.get_table_names():
        return
    if engine.dialect.name != "mssql":
        return
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("""
            SELECT i.name FROM sys.indexes i
            JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            WHERE i.object_id = OBJECT_ID('locations')
              AND i.is_unique = 1 AND i.is_primary_key = 0 AND c.name = 'name'
        """).fetchall()
        for (index_name,) in rows:
            conn.exec_driver_sql(f"DROP INDEX [{index_name}] ON [locations]")


def _ensure_schema():
    """Add columns introduced after the DB was first created. SQLAlchemy's
    create_all() only creates missing tables, never alters existing ones, so
    new columns on an existing table need a lightweight migration like this."""
    insp = inspect(engine)
    tables = insp.get_table_names()
    # Column type names differ between SQLite and SQL Server. On a fresh Azure
    # database there are no pre-existing tables, so create_all() builds
    # everything and this migration is a no-op. It only runs (and only needs the
    # right dialect types) when upgrading a database that predates these columns.
    is_mssql = engine.dialect.name == "mssql"
    STR = "NVARCHAR(255)" if is_mssql else "VARCHAR"
    BOOL = "BIT DEFAULT 0" if is_mssql else "BOOLEAN DEFAULT 0"
    INT = "INT" if is_mssql else "INTEGER"
    DT = "DATETIME2" if is_mssql else "DATETIME"
    DATE = "DATE"
    if "assets" in tables:
        cols = [c["name"] for c in insp.get_columns("assets")]
        with engine.begin() as conn:
            if "asset_class" not in cols:
                conn.execute(text(f"ALTER TABLE assets ADD asset_class {STR}"
                                  if is_mssql else "ALTER TABLE assets ADD COLUMN asset_class VARCHAR"))
            if "equipment_type" not in cols:
                conn.execute(text(f"ALTER TABLE assets ADD equipment_type {STR}"
                                  if is_mssql else "ALTER TABLE assets ADD COLUMN equipment_type VARCHAR"))
            if "checked_out" not in cols:
                add = "ALTER TABLE assets ADD " if is_mssql else "ALTER TABLE assets ADD COLUMN "
                conn.execute(text(f"{add}checked_out {BOOL}"))
                conn.execute(text(f"{add}holder_department_id {INT}"))
                conn.execute(text(f"{add}holder_person {STR}"))
                conn.execute(text(f"{add}checked_out_at {DT}"))
                conn.execute(text(f"{add}due_back {DATE}"))
    if "departments" in tables:
        cols = [c["name"] for c in insp.get_columns("departments")]
        if "code" not in cols:
            with engine.begin() as conn:
                add = "ALTER TABLE departments ADD " if is_mssql else "ALTER TABLE departments ADD COLUMN "
                conn.execute(text(f"{add}code {'NVARCHAR(8)' if is_mssql else 'VARCHAR(8)'}"))


def _init_db():
    """Create every table, migrate, and seed - safe under multiple workers.

    Root cause this guards against: with 2 Gunicorn workers, both run startup at
    once. If one worker creates a table and the other then tries to create the
    SAME table, SQL Server raises "already an object named ...". If that error
    aborts the whole create step, the REMAINING tables (assets, reminders, ...)
    never get created - which is exactly what produced /api/assets -> 500 and a
    blank page. So we create tables ONE AT A TIME and ignore only the harmless
    "already exists" race, guaranteeing every table ends up created regardless
    of worker timing.
    """
    from sqlalchemy.exc import ProgrammingError, OperationalError, IntegrityError

    def _harmless(err) -> bool:
        s = str(err).lower()
        return "already an object named" in s or "already exists" in s

    # Create each table on its own so a race on one can't stop the others.
    for table in Base.metadata.sorted_tables:
        try:
            table.create(bind=engine, checkfirst=True)
        except (ProgrammingError, OperationalError) as e:
            if not _harmless(e):
                raise

    try:
        _ensure_schema()
    except (ProgrammingError, OperationalError):
        pass  # columns already present from a concurrent/prior run

    try:
        _drop_legacy_location_unique()
    except (ProgrammingError, OperationalError):
        pass  # already dropped, or another worker got there first

    # Each seed is independent so one racing worker can't stop the others.
    for _seed in (seed_departments, seed_locations, seed_classes,
                  normalize_flat_locations):
        try:
            with SessionLocal() as db:
                _seed(db)
        except (IntegrityError, ProgrammingError, OperationalError):
            pass  # already seeded by another worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    yield
    # shutdown: nothing to clean up


app = FastAPI(title="Asset Check-In", lifespan=lifespan)
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(public_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))