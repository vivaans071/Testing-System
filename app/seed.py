"""Seeds the fixed set of Frore departments the first time the database is
empty. No user accounts are seeded any more - identity comes from the company
login (Easy Auth), and admin actions are gated by the admin password."""
from sqlalchemy.orm import Session

from . import models

# Exactly the departments requested. Codes are short labels only (no longer part
# of any generated asset code - assets are identified by their random id).
DEFAULT_DEPARTMENTS = [
    ("AirJetBU", "AJBU"),
    ("LiquidJetBU", "LJBU"),
    ("Acoustics", "ACST"),
    ("PZT", "PZT"),
    ("FabOps", "FBOP"),
    ("Reliability", "RELI"),
    ("Systems", "SYST"),
    ("Firmware", "FRMW"),
    ("Hardware", "HDWR"),
]


# The locations and classes that used to be hardcoded in the frontend.
# Seeded once so the dropdowns aren't empty on an existing database that
# predates the Locations/Classes editors.
DEFAULT_LOCATIONS = [
    "Support Area", "Metrology - LiquidJet", "Metrology - PZT",
    "Metrology - Systems", "Metrology - SQA", "Metrology - CE",
    "Metrology - TestDev", "Process Lab", "Clean Lab", "Reliability", "Acoustic",
]

DEFAULT_CLASSES = ["CapEx AirJet", "CapEx LiquidJet", "Not R&D / Production"]


def seed_departments(db: Session):
    """Only runs when there are no departments at all, so it never fights an
    existing list or re-creates ones deleted on purpose."""
    if db.query(models.Department).first():
        return
    for name, code in DEFAULT_DEPARTMENTS:
        db.add(models.Department(name=name, code=code or None))
    db.commit()


def seed_locations(db: Session):
    """Same one-shot rule as departments: only populates a completely empty
    table, so deleting a location keeps it deleted across restarts."""
    if db.query(models.Location).first():
        return
    for name in DEFAULT_LOCATIONS:
        db.add(models.Location(name=name, parent_id=None))
    db.commit()


def seed_classes(db: Session):
    if db.query(models.AssetClass).first():
        return
    for name in DEFAULT_CLASSES:
        db.add(models.AssetClass(name=name))
    db.commit()
