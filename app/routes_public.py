"""
Public QR routes — what runs when someone scans an asset's QR on their phone.
The whole app sits behind the company login (Easy Auth), so the person is
already identified: we read their email from the Easy Auth header instead of
asking for a name. Opening the link shows the asset; an explicit tap logs the
action.

  GET   /c/{code}                       -> mobile page (check in / out)
  GET   /api/public/asset/{code}        -> asset info + status + custody + labs
  POST  /api/public/checkin/{code}      -> log a check-in (no notification)
  POST  /api/public/checkout/{code}     -> check out to a lab
  POST  /api/public/return/{code}       -> check the asset back in
  PATCH /api/public/checkin/{code}/{id} -> optional status/note update
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .security import current_identity, Identity

router = APIRouter(tags=["public"])
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _asset_by_code(db: Session, code: str) -> models.Asset:
    a = db.query(models.Asset).filter(models.Asset.code == code.upper()).first()
    if not a or not a.active:
        raise HTTPException(404, "This QR code doesn't match any active asset.")
    return a


@router.get("/c/{code}", response_class=HTMLResponse, include_in_schema=False)
def scan_page(code: str):
    return FileResponse(os.path.join(STATIC_DIR, "checkin.html"))


@router.get("/api/public/asset/{code}")
def public_asset_info(code: str, db: Session = Depends(get_db)):
    a = _asset_by_code(db, code)
    last = a.checkins[0] if a.checkins else None
    labs = [{"id": d.id, "name": d.name}
            for d in db.query(models.Department).order_by(models.Department.name).all()]
    return {
        "name": a.name,
        "status": a.status, "status_note": a.status_note,
        "statuses": models.STATUSES,
        "checked_out": bool(a.checked_out),
        "holder_lab": a.holder_department.name if a.holder_department else None,
        "holder_person": a.holder_person,
        "labs": labs,
        "last_checkin": last.ts.isoformat(timespec="seconds") if last else None,
        "last_checked_in_by": last.checked_in_by if last else None,
    }


@router.post("/api/public/checkin/{code}")
def public_checkin(code: str, body: dict, request: Request,
                   db: Session = Depends(get_db),
                   identity: Identity = Depends(current_identity)):
    """Log a check-in. Identity comes from Easy Auth (the signed-in email);
    no name is asked for, no location is recorded, and no notification fires."""
    a = _asset_by_code(db, code)
    who = identity.email or "unknown"
    c = models.CheckIn(
        asset_id=a.id,
        checked_in_by=who,
        note=(body.get("note") or None),
        user_agent=request.headers.get("user-agent", "")[:250],
    )
    db.add(c); db.commit(); db.refresh(c)
    return {"checkin_id": c.id, "ts": c.ts.isoformat(timespec="seconds"),
            "asset_name": a.name, "status": a.status}


@router.post("/api/public/checkout/{code}")
def public_checkout(code: str, body: dict, db: Session = Depends(get_db),
                    identity: Identity = Depends(current_identity)):
    """Check an asset out to a lab from the phone (mirrors the dashboard)."""
    a = _asset_by_code(db, code)
    lab_id = body.get("department_id")
    if not lab_id:
        raise HTTPException(400, "Pick a department to check this out to.")
    lab = db.get(models.Department, int(lab_id))
    if not lab:
        raise HTTPException(400, "Unknown department.")
    a.checked_out = True
    a.holder_department_id = lab.id
    a.holder_person = (body.get("person") or "").strip() or (identity.email or None)
    a.checked_out_at = models.utcnow()
    db.add(models.CustodyEvent(asset_id=a.id, action="out", department_id=lab.id,
                               person=a.holder_person, note="scanned out (QR)",
                               by_user=identity.email))
    db.commit()
    return {"ok": True, "checked_out": True, "holder_lab": lab.name}


@router.post("/api/public/return/{code}")
def public_return(code: str, body: dict, db: Session = Depends(get_db),
                  identity: Identity = Depends(current_identity)):
    """Check a borrowed asset back in from the phone."""
    a = _asset_by_code(db, code)
    if not a.checked_out:
        return {"ok": True, "checked_out": False}
    db.add(models.CustodyEvent(asset_id=a.id, action="in",
                               department_id=a.holder_department_id,
                               person=a.holder_person, note="scanned in (QR)",
                               by_user=identity.email))
    a.checked_out = False
    a.holder_department_id = None
    a.holder_person = None
    a.checked_out_at = None
    a.due_back = None
    db.commit()
    return {"ok": True, "checked_out": False}


@router.patch("/api/public/checkin/{code}/{checkin_id}")
def public_checkin_update(code: str, checkin_id: int, body: dict,
                          db: Session = Depends(get_db),
                          identity: Identity = Depends(current_identity)):
    a = _asset_by_code(db, code)
    c = db.get(models.CheckIn, checkin_id)
    if not c or c.asset_id != a.id:
        raise HTTPException(404, "Check-in not found")
    if "note" in body:
        c.note = body["note"] or None

    new_status = body.get("status")
    if new_status and new_status != a.status:
        if new_status not in models.STATUSES:
            raise HTTPException(400, f"Status must be one of: {', '.join(models.STATUSES)}")
        who = identity.email or "scanned check-in"
        db.add(models.StatusChange(
            asset_id=a.id, old_status=a.status, new_status=new_status,
            note=body.get("status_note"), changed_by=who))
        a.status = new_status
        a.status_note = body.get("status_note")
        a.status_updated_at = models.utcnow()
        # No notification on scan-driven changes, per request.
    db.commit()
    return {"ok": True}
