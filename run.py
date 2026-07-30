"""Start the Asset Check-In app locally.

  python run.py            -> http://localhost:8000
  PORT=8080 python run.py  -> custom port

In production (Azure App Service) don't use this file; the platform runs
gunicorn/uvicorn directly via the startup command (see README).
"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
