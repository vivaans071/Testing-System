"""
Tables:
  Asset        - one row per physical thing you put a QR code on
  CheckIn      - one row per QR scan/check-in event (a log, not current state)
  StatusChange - one row per time an asset's current status changes (also a log)
  Department   - managed dropdown list, empty until you add entries yourself
  Setting      - key/value app config (e.g. the QR base URL)
  User         - login accounts (admin / viewer)

`Asset.code` is the short random string embedded in the QR code's URL
(e.g. /c/AB3XQ9) - not guessable, unrelated to `Asset.asset_code` below.
`Asset.asset_code` is a separate, blank-by-default, freely-editable business
identifier field for whatever numbering scheme you define later.
"""
import datetime
import secrets

from sqlalchemy import (Boolean, Column, Date, DateTime, Float, ForeignKey,
                        Integer, String, Text)
from sqlalchemy.orm import relationship

from .database import Base

STATUSES = ["Purchased", "Qualified", "Maintenance", "In Transit", "Disposed", "Missing"]
DEFAULT_STATUS = "Purchased"

# Roles are a ladder: each one can do everything the one below it can.
# viewer      - read, check in, add notes, export
# lab_support - the above + create/edit/delete assets, Excel import, manage
#               owners, and add users (but only viewer/lab_support accounts -
#               they cannot create or promote an admin)
# admin       - everything + departments/codes, admin users, settings
ROLES = ["viewer", "lab_support", "admin"]
ROLE_RANK = {"viewer": 0, "lab_support": 1, "admin": 2}
ROLE_LABELS = {"viewer": "Viewer", "lab_support": "Lab Support", "admin": "Admin"}
LEGACY_ROLE_MAP = {"lab_owner": "lab_support"}   # merged into lab_support


def new_code():
    # 8 chars, URL-safe, upper-cased for easy reading off a printed label
    return secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:8].upper()


def utcnow():
    # Naive UTC on purpose: the whole app (and frontend, which appends "Z")
    # treats stored timestamps as UTC. datetime.utcnow() is deprecated, so
    # take an aware "now" and strip the tzinfo to keep identical behavior.
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    # Short code used in generated asset codes, e.g. "DETC" in 6184-A30-DETC-23.
    code = Column(String(8), nullable=True)


class Location(Base):
    """Admin-editable list of physical locations, two levels deep. A location
    with parent_id=None is a top-level place (e.g. "Reliability"); one with a
    parent_id is a sub-location of it (e.g. "Reliability - Building A").

    Asset.location stays a plain string rather than a foreign key: imported
    assets often carry free-text locations that aren't on this list, and
    editing one should never silently wipe that value. This table only drives
    the dropdown."""
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True)
    # NOT globally unique: two parents may each have a sub-location called
    # "104" or "PZT". Uniqueness is enforced per-parent in routes_admin.
    name = Column(String(255), nullable=False)
    parent_id = Column(Integer, ForeignKey("locations.id"), nullable=True)


class AssetClass(Base):
    """Admin-editable list of asset classes (CapEx AirJet / CapEx LiquidJet /
    Not R&D / Production ...). Same rationale as Location above - Asset.asset_class
    remains free text, this just populates the picker."""
    __tablename__ = "asset_classes"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)


class UserDepartment(Base):
    """Remembers which department each signed-in user belongs to, keyed by their
    Easy Auth email so it follows them across devices. A row with a NULL
    department_id is a deliberate "none" choice - distinct from having no row
    at all, which is what triggers the first-login prompt."""
    __tablename__ = "user_departments"
    email = Column(String(255), primary_key=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)


class UserActivitySeen(Base):
    """When each user last cleared their activity notifications, keyed by Easy
    Auth email. Server-side rather than localStorage so the badge agrees across
    devices and can't drift out of sync with the count it's compared against."""
    __tablename__ = "user_activity_seen"
    email = Column(String(255), primary_key=True)
    seen_at = Column(DateTime, default=utcnow)


class CodeCounter(Base):
    """Monotonic sequence per location prefix (A, B, C, FE, FR, O, S).

    Lives in its own table rather than being derived from existing asset codes
    so a number is never handed out twice: deleting an asset does not free its
    number, and the counter only ever moves forward.
    """
    __tablename__ = "code_counters"
    prefix = Column(String(4), primary_key=True)
    next_seq = Column(Integer, nullable=False, default=1)


class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True, index=True, default=new_code)
    asset_code = Column(String, nullable=True)  # your own scheme, blank until defined
    name = Column(String, nullable=False)
    location = Column(String, nullable=True)     # home/assigned location
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    owner = Column(String, nullable=True)
    vendor = Column(String, nullable=True)
    cost = Column(Float, nullable=True)
    serial_number = Column(String, nullable=True)
    asset_class = Column(String, nullable=True)  # CapEx AirJet / CapEx LiquidJet / Not R&D / Production
    # What kind of thing it is. Only matters for the accounting segment of a
    # generated asset code, and only when the cost is at/below the $2500
    # capitalisation threshold (above that, everything is a fixed asset).
    equipment_type = Column(String, nullable=True)
    date_purchased = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default=DEFAULT_STATUS)
    status_note = Column(Text, nullable=True)
    status_updated_at = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True)  # soft-disable instead of hard delete
    created_at = Column(DateTime, default=utcnow)

    # Physical custody, separate from lifecycle status. An asset can be
    # Qualified AND checked out at once - different questions. checked_out=False
    # means it's at its home location and available.
    checked_out = Column(Boolean, default=False)
    holder_department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    holder_person = Column(String, nullable=True)
    checked_out_at = Column(DateTime, nullable=True)
    due_back = Column(Date, nullable=True)

    department = relationship("Department", foreign_keys=[department_id])
    holder_department = relationship("Department", foreign_keys=[holder_department_id])
    checkins = relationship("CheckIn", back_populates="asset",
                            cascade="all, delete-orphan",
                            order_by="CheckIn.ts.desc()")
    status_changes = relationship("StatusChange", back_populates="asset",
                                  cascade="all, delete-orphan",
                                  order_by="StatusChange.ts.desc()")
    reminders_list = relationship("Reminder", cascade="all, delete-orphan",
                                  overlaps="asset")
    # Custody events also point at this asset. Without an explicit cascade the
    # rows are left behind and a permanent delete fails on the foreign key -
    # SQLite doesn't enforce FKs by default so this only ever bit on SQL Server.
    custody_events = relationship("CustodyEvent", cascade="all, delete-orphan")


class CheckIn(Base):
    __tablename__ = "checkins"
    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    ts = Column(DateTime, default=utcnow, index=True)
    checked_in_by = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    accuracy_m = Column(Float, nullable=True)
    user_agent = Column(String, nullable=True)
    source = Column(String, nullable=False, default="qr_scan")  # "qr_scan" or "barcode_scan"

    asset = relationship("Asset", back_populates="checkins")


class StatusChange(Base):
    __tablename__ = "status_changes"
    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    ts = Column(DateTime, default=utcnow, index=True)
    old_status = Column(String, nullable=True)
    new_status = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    changed_by = Column(String, nullable=True)  # typed name, or admin's email

    asset = relationship("Asset", back_populates="status_changes")


class CustodyEvent(Base):
    """Append-only log of physical check-outs / check-ins so an asset's custody
    history (who had it, which department, how long) is preserved."""
    __tablename__ = "custody_events"
    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    ts = Column(DateTime, default=utcnow, index=True)
    action = Column(String, nullable=False)            # "out" | "in"
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    person = Column(String, nullable=True)
    due_back = Column(Date, nullable=True)
    note = Column(Text, nullable=True)
    by_user = Column(String, nullable=True)


class Reminder(Base):
    """A fully custom reminder attached to an asset (e.g. a calibration check).

    kind="interval": recurs every `interval_days`; completing it rolls next_due
      forward by that many days (from the due date, keeping a clean grid).
    kind="date": a one-off; completing it marks the reminder done and it stops
      coming due.
    """
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    label = Column(String, nullable=False)             # free text, e.g. "Calibration check"
    kind = Column(String, nullable=False, default="interval")   # "interval" | "date"
    interval_days = Column(Integer, nullable=True)     # for kind="interval"
    next_due = Column(Date, nullable=True, index=True)
    active = Column(Boolean, default=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    created_by = Column(String, nullable=True)
    last_done_at = Column(Date, nullable=True)

    asset = relationship("Asset")
    # Deleting an asset cascades to its reminders, so the reminder's own log
    # rows have to go with it or the FK blocks the delete.
    logs = relationship("ReminderLog", cascade="all, delete-orphan")


class ReminderLog(Base):
    """Each time a reminder is marked done, for history."""
    __tablename__ = "reminder_logs"
    id = Column(Integer, primary_key=True)
    reminder_id = Column(Integer, ForeignKey("reminders.id"), nullable=False, index=True)
    ts = Column(DateTime, default=utcnow)
    done_on = Column(Date, nullable=True)
    by_user = Column(String, nullable=True)
    note = Column(Text, nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(255), primary_key=True)
    value = Column(String, nullable=True)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="viewer")  # "admin" or "viewer"
    created_at = Column(DateTime, default=utcnow)
