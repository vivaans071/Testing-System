"""
No user accounts and no login screen any more - the company login (Easy Auth)
sits in front of the whole app. This module now only exposes:

  GET  /api/auth/me            -> who Easy Auth says you are (email/name)
  POST /api/auth/admin-login   -> exchange the admin password for a gate token
  GET  /api/auth/admin-status  -> is the presented admin token still valid?
"""
from fastapi import APIRouter, Depends, Header, HTTPException

from .security import (Identity, current_identity, check_admin_password,
                       make_admin_token, _valid_admin_token)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
def me(identity: Identity = Depends(current_identity)):
    # email is None until Easy Auth is enabled; the UI shows "Guest" then.
    return {"email": identity.email, "full_name": identity.full_name,
            "authenticated": identity.email is not None}


@router.post("/admin-login")
def admin_login(body: dict):
    if not check_admin_password(body.get("password", "")):
        raise HTTPException(403, "Incorrect admin password.")
    return {"admin_token": make_admin_token()}


@router.get("/admin-status")
def admin_status(x_admin_token: str = Header(None)):
    return {"is_admin": bool(x_admin_token and _valid_admin_token(x_admin_token))}
