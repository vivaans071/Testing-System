"""
Identity + light gating for an internal tool that sits BEHIND the company's
own login (Azure App Service "Easy Auth" / Entra).

There is no login screen in the app. Two things provide identity/authority:

1. Who the user is  -> read from the Easy Auth header that Azure injects on
   every request once Easy Auth is enabled:
       X-MS-CLIENT-PRINCIPAL-NAME   (the signed-in email)
       X-MS-CLIENT-PRINCIPAL-ID     (stable user id)
   Before Easy Auth is turned on, or locally, this is absent and the user is
   recorded as "unknown". Nothing breaks in the meantime.

2. Admin actions (departments, settings, permanent delete) are gated by a
   single shared ADMIN PASSWORD entered in Settings, not a user account. The
   browser holds a short signed token after a correct entry and sends it as
   the X-Admin-Token header. This is a lightweight UI gate, not real security
   - the real security is the company login in front of the whole app.
"""
import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException
from urllib.parse import unquote

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "storage")

TOKEN_TTL_SECONDS = 60 * 60 * 12  # admin gate lasts 12h per browser
ADMIN_PASSWORD = os.environ.get("CHECKIN_ADMIN_PASSWORD", "admin1234")


def _secret() -> bytes:
    """Key for signing the admin-gate token. Set CHECKIN_SECRET in production
    so it survives restarts / is shared across instances; falls back to a local
    file for dev."""
    env = os.environ.get("CHECKIN_SECRET")
    if env:
        return env.encode()
    path = os.path.join(DATA_DIR, "secret.key")
    if not os.path.exists(path):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, "wb") as f:
            f.write(os.urandom(32))
    with open(path, "rb") as f:
        return f.read()


# --------------------------------------------------------------- identity
class Identity:
    """Who is making this request, from the Easy Auth header (or 'unknown')."""
    def __init__(self, email: str | None, name: str | None):
        self.email = email
        self.full_name = name or email or "unknown"

    def __repr__(self):
        return f"Identity({self.full_name!r})"


def current_identity(
    x_ms_client_principal_name: str = Header(None),
    x_ms_client_principal: str = Header(None),
) -> Identity:
    """Pull the signed-in user from Easy Auth headers.

    - X-MS-CLIENT-PRINCIPAL-NAME is the email, present on every request once
      Easy Auth is on. Easiest source.
    - X-MS-CLIENT-PRINCIPAL is a base64 JSON blob of all claims; we read it as
      a fallback to also recover the display name when available.
    """
    email = (x_ms_client_principal_name or "").strip() or None
    name = None
    if x_ms_client_principal:
        try:
            decoded = json.loads(base64.b64decode(x_ms_client_principal))
            claims = {c.get("typ"): c.get("val") for c in decoded.get("claims", [])}
            name = claims.get("name") or claims.get(
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name")
            email = email or claims.get(
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress")
        except Exception:
            pass
    return Identity(email, name)


# Kept under the old name so the ~40 existing route dependencies don't change.
# Everyone authenticated by the company login may view + edit + check assets in
# and out; there is no per-user role any more.
def current_user(identity: Identity = Depends(current_identity)) -> Identity:
    return identity


# Creating / editing / deactivating assets is open to everyone (they're already
# behind the company login), so these guards are now just the identity.
require_support = current_user
require_owner = current_user


# --------------------------------------------------------------- admin gate
def make_admin_token() -> str:
    payload = json.dumps({"adm": 1, "exp": int(time.time()) + TOKEN_TTL_SECONDS}).encode()
    sig = hmac.new(_secret(), payload, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload).decode() + "." + sig


def _valid_admin_token(token: str) -> bool:
    try:
        payload_b64, sig = token.split(".")
        payload = base64.urlsafe_b64decode(payload_b64.encode())
        if not hmac.compare_digest(hmac.new(_secret(), payload, hashlib.sha256).hexdigest(), sig):
            return False
        return json.loads(payload)["exp"] >= time.time()
    except Exception:
        return False


def check_admin_password(password: str) -> bool:
    return hmac.compare_digest((password or ""), ADMIN_PASSWORD)


def require_admin(x_admin_token: str = Header(None),
                  identity: Identity = Depends(current_identity)) -> Identity:
    """Gate for admin-only actions (departments, settings, permanent delete).
    The browser obtains the token by entering the admin password in Settings."""
    if not x_admin_token or not _valid_admin_token(x_admin_token):
        raise HTTPException(403, "Admin access required. Enter the admin password in Settings.")
    return identity
