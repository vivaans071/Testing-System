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


def seed_departments(db: Session):
    """Only runs when there are no departments at all, so it never fights an
    existing list or re-creates ones deleted on purpose."""
    if db.query(models.Department).first():
        return
    for name, code in DEFAULT_DEPARTMENTS:
        db.add(models.Department(name=name, code=code or None))
    db.commit()
