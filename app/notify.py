"""Email notification when an asset becomes Qualified.

SMTP is configured with environment variables (nothing secret goes in the DB);
the recipient list is a normal app setting an admin can edit in the UI.

  CHECKIN_SMTP_HOST      e.g. smtp.sendgrid.net       (unset = notifications off)
  CHECKIN_SMTP_PORT      default 587
  CHECKIN_SMTP_USER      optional
  CHECKIN_SMTP_PASSWORD  optional
  CHECKIN_SMTP_FROM      default no-reply@<host>
  CHECKIN_SMTP_TLS       "0" to disable STARTTLS

Sending happens on a background thread and every failure is swallowed: an
unreachable mail server must never block or fail a status change.
"""
import os
import smtplib
import threading
from email.message import EmailMessage

SMTP_HOST = os.environ.get("CHECKIN_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("CHECKIN_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("CHECKIN_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("CHECKIN_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("CHECKIN_SMTP_FROM", "")
SMTP_TLS = os.environ.get("CHECKIN_SMTP_TLS", "1") != "0"


def is_configured() -> bool:
    return bool(SMTP_HOST)


def _send(to_list, subject, body):
    msg = EmailMessage()
    msg["From"] = SMTP_FROM or f"no-reply@{SMTP_HOST}"
    msg["To"] = ", ".join(to_list)
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
        if SMTP_TLS:
            try:
                smtp.starttls()
            except smtplib.SMTPNotSupportedError:
                pass
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)


def send_async(to_list, subject, body):
    """Fire and forget. Returns immediately; errors are logged, never raised."""
    if not is_configured() or not to_list:
        return False

    def run():
        try:
            _send(to_list, subject, body)
        except Exception as e:                       # noqa: BLE001
            print(f"[notify] email failed: {e}")

    threading.Thread(target=run, daemon=True).start()
    return True


def qualified_email(asset, changed_by, note, url):
    subject = f"Qualified: {asset.name}"
    code = asset.asset_code or asset.code
    lines = [
        f"{asset.name} has been marked QUALIFIED.",
        "",
        "Qualified means the product is READY to be put into its intended use.",
        "",
        f"Asset code : {code}",
        f"Department : {asset.department.name if asset.department else '-'}",
        f"Location   : {asset.location or '-'}",
        f"Owner      : {asset.owner or '-'}",
        f"Changed by : {changed_by or 'unknown'}",
    ]
    if note:
        lines.append(f"Note       : {note}")
    if url:
        lines += ["", f"View the asset: {url}"]
    return subject, "\n".join(lines)
