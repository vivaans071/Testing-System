"""
Public, no-login routes — this is what runs when someone scans the QR code
on their phone. No login is required here on purpose: this mirrors a badge
tap, not an account action. The page requires an explicit "Check in" tap
before anything is logged - opening the link alone does nothing.
  GET  /c/{code}                          -> mobile check-in page
  GET  /api/public/asset/{code}           -> asset info + current status
  POST /api/public/checkin/{code}         -> logs a check-in (only called
                                              when the person taps "Check in")
  PATCH /api/public/checkin/{code}/{id}   -> add name/note, optionally change status
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from . import models
from .database import get_db

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
    return {
        "name": a.name, "location": a.location,
        "status": a.status, "status_note": a.status_note,
        "statuses": models.STATUSES,
        "last_checkin": last.ts.isoformat(timespec="seconds") if last else None,
        "last_checked_in_by": last.checked_in_by if last else None,
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
        if new_status not in models.STATUSES and new_status != a.status:
            raise HTTPException(400, f"Status must be one of: {', '.join(models.STATUSES)}")
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
