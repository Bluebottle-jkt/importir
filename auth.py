"""
auth.py
Session-based authentication and role management.

Roles:
  admin  — full access: can download source, upload patch, pull git
  user   — view/filter dashboards only

Credentials (hard-coded regular users):
  user / yauser

Admin credentials (env vars, with unsafe default):
  ADMIN_USERNAME  default: admin
  ADMIN_PASSWORD  default: admin  ← WARNING logged if unchanged
"""

from __future__ import annotations

import logging
import os

from flask import session

logger = logging.getLogger(__name__)

# ── Regular users ─────────────────────────────────────────────────────────────
# Add more rows here for additional users.
USERS: dict[str, dict] = {
    "user": {"password": "yauser", "role": "user"},
}


# ── Admin credentials ─────────────────────────────────────────────────────────

def get_admin_creds() -> tuple[str, str]:
    u = os.environ.get("ADMIN_USERNAME", "admin")
    p = os.environ.get("ADMIN_PASSWORD", "admin")
    if u == "admin" and p == "admin":
        logger.warning(
            "[AUTH] Admin credentials are DEFAULT (admin/admin). "
            "Set ADMIN_USERNAME and ADMIN_PASSWORD environment variables in production!"
        )
    return u, p


# ── Credential validation ─────────────────────────────────────────────────────

def check_credentials(username: str, password: str) -> str | None:
    """Return role string ('admin' / 'user') or None if invalid."""
    admin_u, admin_p = get_admin_creds()
    if username == admin_u and password == admin_p:
        return "admin"
    entry = USERS.get(username)
    if entry and entry["password"] == password:
        return entry["role"]
    return None


# ── Session helpers (call inside Flask/Dash request context) ──────────────────

def current_user() -> str:
    return session.get("user", "")


def current_role() -> str:
    return session.get("role", "")


def is_authenticated() -> bool:
    return bool(session.get("authenticated"))


def is_admin() -> bool:
    return session.get("role") == "admin"
