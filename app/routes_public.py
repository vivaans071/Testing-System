"""
Public, no-login routes — this is what runs when someone scans the QR code
on their phone. No login is required here on purpose: this mirrors a badge
tap, not an account action. The page requires an explicit "Check in" tap
before anything is logged - opening the link alone does nothing.
  GET   /c/{code}                          -> mobile check-in page
  GET   /api/public/asset/{code}           -> asset info + current status
  POST  /api/public/checkin/{code}         -> logs a check-in (only called
                                               when the person taps "Check in")
  PATCH /api/public/checkin/{code}/{id}    -> add name/note, optionally change status
  POST  /api/public/checkout/{code}        -> check out to a borrowing department
  POST  /api/public/checkin_custody/{code} -> check back in from custody

Custody (checkout/checkin_custody) piggybacks on the same Easy Auth header
the rest of the app reads opportunistically (see security.Identity) - if the
phone happens to have an active company session it's used to fill in
"by_user" for the audit log; if not, it just falls back to "unknown", same
as everywhere else on this page.
"""
import os
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .security import Identity, current_identity

router = APIRouter(tags=["public"])
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _asset_by_code(db: Session, code: str) -> models.Asset:
    a = db.query(models.Asset).filter(models.Asset.code == code.upper()).first()
    if not a or not a.active:
        raise HTTPException(404, "This QR code doesn't match any active asset.")
    return a


def _live_statuses(db: Session):
    """Mirrors routes_admin._status_names - the admin-editable status list,
    falling back to the hardcoded defaults before the table is seeded."""
    rows = (db.query(models.AssetStatus)
            .order_by(models.AssetStatus.sort_order, models.AssetStatus.id).all())
    return [r.name for r in rows] or list(models.STATUSES)


def _parse_date(value):
    # Small local copy of routes_admin._parse_date - not imported to avoid
    # coupling this no-login module to the admin router at import time.
    if not value:
        return None
    try:
        return date_type.fromisoformat(str(value).strip())
    except ValueError:
        raise HTTPException(400, f"Date '{value}' must be YYYY-MM-DD.")


@router.get("/c/{code}", response_class=HTMLResponse, include_in_schema=False)
def scan_page(code: str):
    return FileResponse(os.path.join(STATIC_DIR, "checkin.html"))


@router.get("/api/public/asset/{code}")
def public_asset_info(code: str, db: Session = Depends(get_db)):
    a = _asset_by_code(db, code)
    last = a.checkins[0] if a.checkins else None
    return {
        "name": a.name, "location": a.location,
        "status": a.status, "status_note": a.status_note,
        "statuses": _live_statuses(db),
        "last_checkin": last.ts.isoformat(timespec="seconds") if last else None,
        "last_checked_in_by": last.checked_in_by if last else None,
        # For "View item details" and the check-out / check-in-custody UI.
        "asset_code": a.code,
        "department": a.department.name if a.department else None,
        "owner": a.owner,
        "vendor": a.vendor,
        "serial_number": a.serial_number,
        "checked_out": bool(a.checked_out),
        "holder_department": a.holder_department.name if a.holder_department else None,
        "holder_person": a.holder_person,
        "checked_out_at": a.checked_out_at.isoformat(timespec="seconds") if a.checked_out_at else None,
        "due_back": a.due_back.isoformat() if a.due_back else None,
    }


@router.post("/api/public/checkin/{code}")
def public_checkin(code: str, body: dict, request: Request, db: Session = Depends(get_db)):
    a = _asset_by_code(db, code)
    c = models.CheckIn(
        asset_id=a.id,
        checked_in_by=(body.get("checked_in_by") or None),
        note=(body.get("note") or None),
        lat=body.get("lat"), lon=body.get("lon"), accuracy_m=body.get("accuracy_m"),
        user_agent=request.headers.get("user-agent", "")[:250],
    )
    db.add(c); db.commit(); db.refresh(c)
    return {"checkin_id": c.id, "ts": c.ts.isoformat(timespec="seconds"),
            "asset_name": a.name, "status": a.status}


@router.patch("/api/public/checkin/{code}/{checkin_id}")
def public_checkin_update(code: str, checkin_id: int, body: dict, db: Session = Depends(get_db)):
    a = _asset_by_code(db, code)
    c = db.get(models.CheckIn, checkin_id)
    if not c or c.asset_id != a.id:
        raise HTTPException(404, "Check-in not found")
    if "checked_in_by" in body:
        c.checked_in_by = body["checked_in_by"] or None
    if "note" in body:
        c.note = body["note"] or None

    new_status = body.get("status")
    if new_status:
        valid = _live_statuses(db)
        if new_status not in valid and new_status != a.status:
            raise HTTPException(400, f"Status must be one of: {', '.join(valid)}")
        # Only record a status change when the status actually changes. A
        # check-in that just carries a note is one event, not two — the note
        # already lives on the CheckIn row above.
        if new_status != a.status:
            became_qualified = new_status == "Qualified"
            who = c.checked_in_by or "scanned check-in"
            db.add(models.StatusChange(
                asset_id=a.id, old_status=a.status, new_status=new_status,
                note=body.get("status_note"), changed_by=who))
            a.status = new_status
            a.status_note = body.get("status_note")
            a.status_updated_at = models.utcnow()
            if became_qualified:
                # Same notification as the dashboard path - a QR scan is the
                # most likely place someone marks equipment Qualified.
                from .routes_admin import notify_qualified
                notify_qualified(db, a, who, body.get("status_note"))
    db.commit()
    return {"ok": True}


@router.post("/api/public/checkout/{code}")
def public_checkout(code: str, body: dict, db: Session = Depends(get_db),
                    identity: Identity = Depends(current_identity)):
    """Check an asset out to a borrowing department from the QR page - same
    action as the desktop "Check out / lend" flow, keyed by scan code instead
    of asset id."""
    a = _asset_by_code(db, code)
    dept_id = body.get("department_id")
    if not dept_id:
        raise HTTPException(400, "A borrowing department is required to check out.")
    dept = db.get(models.Department, int(dept_id))
    if not dept:
        raise HTTPException(400, "Unknown department.")
    a.checked_out = True
    a.holder_department_id = dept.id
    a.holder_person = (body.get("person") or "").strip() or None
    a.checked_out_at = models.utcnow()
    a.due_back = _parse_date(body.get("due_back"))
    db.add(models.CustodyEvent(asset_id=a.id, action="out", department_id=dept.id,
                               person=a.holder_person, due_back=a.due_back,
                               note=(body.get("note") or "").strip() or None,
                               by_user=identity.email or "unknown"))
    db.commit()
    return {"ok": True}


@router.post("/api/public/checkin_custody/{code}")
def public_checkin_custody(code: str, body: dict, db: Session = Depends(get_db),
                           identity: Identity = Depends(current_identity)):
    """Check a borrowed asset back in (physical custody, not the lifecycle
    Check In above) from the QR page."""
    a = _asset_by_code(db, code)
    if not a.checked_out:
        raise HTTPException(400, "This asset isn't checked out.")
    db.add(models.CustodyEvent(asset_id=a.id, action="in",
                               department_id=a.holder_department_id, person=a.holder_person,
                               note=(body.get("note") or "").strip() or None,
                               by_user=identity.email or "unknown"))
    a.checked_out = False
    a.holder_department_id = None
    a.holder_person = None
    a.checked_out_at = None
    a.due_back = None
    db.commit()
    return {"ok": True}
