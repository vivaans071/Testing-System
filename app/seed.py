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


# Default locations, as parent -> [children]. The dash in "Metrology - PZT" is
# now produced by the parent/child relationship rather than being part of a
# single flat name, so the picker can offer Metrology first and PZT second.
DEFAULT_LOCATIONS = {
    "Support Area": [],
    "Metrology": ["LiquidJet", "PZT", "Systems", "SQA", "CE", "TestDev"],
    "Process Lab": [],
    "Clean Lab": [],
    "Reliability": [],
    "Acoustic": [],
}

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
    for parent, children in DEFAULT_LOCATIONS.items():
        p = models.Location(name=parent, parent_id=None)
        db.add(p); db.flush()
        for child in children:
            db.add(models.Location(name=child, parent_id=p.id))
    db.commit()


def normalize_flat_locations(db: Session):
    """One-time cleanup for databases seeded before sub-locations existed.

    Older installs stored "Metrology - PZT" as a single top-level row. Split
    those into a real parent and child so the two-step picker works. Assets are
    deliberately left alone: their location text reads "Metrology - PZT" either
    way, so nothing needs rewriting.
    """
    flat = (db.query(models.Location)
            .filter(models.Location.parent_id.is_(None)).all())
    by_name = {l.name: l for l in flat}
    changed = False
    for loc in flat:
        if " - " not in loc.name:
            continue
        head, _, tail = loc.name.partition(" - ")
        head, tail = head.strip(), tail.strip()
        if not head or not tail:
            continue
        # don't touch one that already has children of its own
        if db.query(models.Location).filter(models.Location.parent_id == loc.id).first():
            continue
        parent = by_name.get(head)
        if parent is None:
            parent = models.Location(name=head, parent_id=None)
            db.add(parent); db.flush()
            by_name[head] = parent
        # reuse this row as the child rather than deleting and re-creating
        loc.name = tail
        loc.parent_id = parent.id
        changed = True
    if changed:
        db.commit()


def seed_statuses(db: Session):
    """Populates the editable status list from models.STATUSES on first run,
    preserving the original order."""
    if db.query(models.AssetStatus).first():
        # Backfill colors on statuses that don't have one yet (existing DBs
        # predating the color feature). Only touches NULL color rows.
        default_colors = {
            "PO": "#1976d2", "Arrived": "#2e7d32", "Purchased": "#2e7d32",
            "Qualified": "#00838f", "Maintenance": "#ef6c00",
            "In Transit": "#5e35b1", "Disposed": "#757575", "Missing": "#c62828",
        }
        default_notes = {
            "Qualified": "Qualified means the product is READY to be put into its intended use.",
        }
        changed = False
        for row in db.query(models.AssetStatus).all():
            if not row.color and row.name in default_colors:
                row.color = default_colors[row.name]
                changed = True
            if not row.popup_note and row.name in default_notes:
                row.popup_note = default_notes[row.name]
                changed = True
        if changed:
            db.commit()
        return
    default_colors = {
        "PO": "#1976d2",           # blue
        "Arrived": "#2e7d32",      # green
        "Purchased": "#2e7d32",    # green (legacy name)
        "Qualified": "#00838f",    # teal
        "Maintenance": "#ef6c00",  # orange
        "In Transit": "#5e35b1",   # purple
        "Disposed": "#757575",     # grey
        "Missing": "#c62828",      # red
    }
    default_notes = {
        "Qualified": "Qualified means the product is READY to be put into its intended use.",
    }
    for i, name in enumerate(models.STATUSES):
        db.add(models.AssetStatus(name=name, sort_order=i,
                                  color=default_colors.get(name),
                                  popup_note=default_notes.get(name)))
    db.commit()


def seed_classes(db: Session):
    if db.query(models.AssetClass).first():
        return
    for name in DEFAULT_CLASSES:
        db.add(models.AssetClass(name=name))
    db.commit()
