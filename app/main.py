# app/main.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import init_db, get_db, SessionLocal
from app.logger import configure_root_logging, get_logger
from app.seed import seed_targets
from app.settings import ENVIRONMENT

from fastapi import Request, HTTPException
from pydantic import BaseModel
from app.models import SiteNotice, ApiNote, IncidentUpdate
from fastapi.responses import FileResponse
log = get_logger(__name__)

app = FastAPI(title="EWS Monitoring (ewsmon)")

# Serve UI assets (index.html, app.js, css, etc.)
# Ensure these files exist in the container at /app/app/static
app.mount("/static", StaticFiles(directory="app/static"), name="static")


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        return response

app.add_middleware(RequestLoggingMiddleware)

from app.models import SiteNotice

@app.on_event("startup")
def on_startup():
    configure_root_logging()
    log.info("web startup: initializing database")
    init_db()

    with SessionLocal() as db:
        seed_targets(db)

        # Ensure a banner row exists (id=1)
        exists = db.query(SiteNotice).filter(SiteNotice.id == 1).first()
        if not exists:
            db.add(
                SiteNotice(
                    id=1,
                    enabled=False,
                    notice_type="info",
                    message="All systems operational."
                )
            )
            db.commit()
            log.debug("web startup: created default site notice")

        # Dev-only: sample maintenance incident if none exist
        if ENVIRONMENT == "dev":
            if db.query(IncidentUpdate).first() is None:
                db.add(
                    IncidentUpdate(
                        is_active=True,
                        status="maintenance",
                        title="Scheduled maintenance window",
                        message="Example incident. EWS APIs may be briefly unavailable during the maintenance window.",
                    )
                )
                db.commit()
                log.debug("web startup: created sample dev incident")

    log.info("web startup complete", extra={"env": ENVIRONMENT})


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "env": ENVIRONMENT}


from fastapi.responses import RedirectResponse

import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(os.path.join(BASE_DIR, "static/index.html"))

@app.get("/admin", include_in_schema=False)
def admin():
    return FileResponse(os.path.join(BASE_DIR, "static/admin.html"))


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(os.path.join(BASE_DIR, "static/login.html"))
# -----------------------------
# API used by the frontend UI
# -----------------------------

@app.get("/api/targets")
def api_targets(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            select id, name, url, soap_action, api_type, enabled
            from api_target
            order by name
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@app.get("/api/summary")
def api_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Frontend expects either:
      - an array
      - OR an object with `items: [...]`

    We return:
      { generated_at, totals, items }
    where:
      - items[] includes `uptime_today` and `uptime_7d` as ratios (0..1),
        because app.js's fmtPct() multiplies by 100.
    """
    rows = db.execute(
        text(
            """
            with last_probe as (
              select distinct on (p.target_id)
                p.target_id,
                p.ts,
                p.ok,
                p.http_status,
                p.duration_ms
              from api_probe p
              order by p.target_id, p.ts desc, p.id desc
            ),
            today as (
              select
                p.target_id,
                count(*)::int as total,
                sum(case when p.ok then 1 else 0 end)::int as ok_count,
                avg(p.duration_ms) as avg_ms
              from api_probe p
              where p.ts >= date_trunc('day', now())
              group by p.target_id
            ),
            wk as (
              select
                p.target_id,
                count(*)::int as total,
                sum(case when p.ok then 1 else 0 end)::int as ok_count,
                avg(p.duration_ms) as avg_ms
              from api_probe p
              where p.ts >= (now() - interval '7 days')
              group by p.target_id
            )
            select
              t.id,
              t.name,
              t.api_type,
              t.url,
              lp.ts as last_checked,
              lp.ok as last_ok,
              lp.http_status as http_status,
              lp.duration_ms as last_ms,
              coalesce(today.total, 0) as today_total,
              coalesce(today.ok_count, 0) as today_ok,
              today.avg_ms as today_avg_ms,
              coalesce(wk.total, 0) as wk_total,
              coalesce(wk.ok_count, 0) as wk_ok,
              wk.avg_ms as wk_avg_ms
            from api_target t
            left join last_probe lp on lp.target_id = t.id
            left join today on today.target_id = t.id
            left join wk on wk.target_id = t.id
            where t.enabled = true
            order by t.name
            """
        )
    ).mappings().all()

    DEGRADED_MS = 1500  # response time >= this (ms) counts as degraded when up
    items: list[dict[str, Any]] = []
    up = 0
    down = 0
    degraded = 0

    for r in rows:
        last_ok = bool(r["last_ok"]) if r["last_ok"] is not None else False
        is_up = bool(r["last_checked"]) and last_ok
        last_ms = float(r["last_ms"]) if r["last_ms"] is not None else None

        if is_up:
            up += 1
            if last_ms is not None and last_ms >= DEGRADED_MS:
                degraded += 1
        else:
            down += 1

        today_total = int(r["today_total"] or 0)
        wk_total = int(r["wk_total"] or 0)

        # IMPORTANT: keep these as ratios 0..1 (JS fmtPct multiplies by 100)
        today_uptime = (float(r["today_ok"]) / today_total) if today_total > 0 else None
        wk_uptime = (float(r["wk_ok"]) / wk_total) if wk_total > 0 else None

        items.append(
            {
                "id": r["id"],
                "name": r["name"],
                "api_type": r["api_type"],
                "url": r["url"],
                "last_checked": r["last_checked"].isoformat() if r["last_checked"] else None,
                "is_up": is_up,
                "http_status": r["http_status"],
                "last_ms": round(last_ms, 2) if last_ms is not None else None,
                "avg_today_ms": round(float(r["today_avg_ms"]), 2) if r["today_avg_ms"] is not None else None,
                "avg_7d_ms": round(float(r["wk_avg_ms"]), 2) if r["wk_avg_ms"] is not None else None,
                "uptime_today": today_uptime,
                "uptime_7d": wk_uptime,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "services": len(items),
            "up": up,
            "down": down,
            "degraded": degraded,
        },
        # ✅ app.js reads data.items
        "items": items,
        # optional compat keys (harmless)
        "services": items,
        "rows": items,
    }


@app.get("/api/targets/{target_id}/probes")
def api_target_probes(
    target_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Recent probes for a given target (for charts).
    """
    limit = max(1, min(limit, 500))

    rows = db.execute(
        text(
            """
            select ts, ok, http_status, duration_ms, error
            from api_probe
            where target_id = :target_id
            order by ts desc, id desc
            limit :limit
            """
        ),
        {"target_id": target_id, "limit": limit},
    ).mappings().all()

    # return oldest->newest (nice for charting)
    probes = list(reversed([dict(r) for r in rows]))
    return {"target_id": target_id, "count": len(probes), "probes": probes}

@app.get("/api/notices")
def api_notices(db: Session = Depends(get_db)):
    row = db.query(SiteNotice).filter(SiteNotice.id == 1).first()

    if not row:
        return {"banner": {"enabled": False}}

    return {
        "banner": {
            "enabled": row.enabled,
            "type": row.notice_type,
            "message": row.message,
            "starts_at": row.starts_at.isoformat() if row.starts_at else None,
            "ends_at": row.ends_at.isoformat() if row.ends_at else None,
        }
    }

import secrets

from fastapi import HTTPException, Request
from app.settings import ADMIN_USERNAME, ADMIN_PASSWORD, ENVIRONMENT

# In-memory session store: token -> {"username", "expires_at"}
_admin_sessions: dict[str, dict] = {}
SESSION_TTL = timedelta(days=7)


def _get_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def require_admin(request: Request) -> None:
    """Require valid admin session (Bearer token)."""
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise HTTPException(500, "ADMIN_USERNAME and ADMIN_PASSWORD must be set")
    token = _get_bearer_token(request)
    if not token:
        raise HTTPException(401, "Unauthorized")
    session = _admin_sessions.get(token)
    if not session or datetime.now(timezone.utc) > session["expires_at"]:
        if token in _admin_sessions:
            del _admin_sessions[token]
        raise HTTPException(401, "Unauthorized")


def require_incident_admin(request: Request) -> None:
    """When ENVIRONMENT != 'dev', require same admin session as require_admin."""
    if ENVIRONMENT == "dev":
        return
    require_admin(request)


class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/api/admin/login")
def api_admin_login(payload: LoginBody) -> dict[str, Any]:
    """Validate credentials and return a session token (store in localStorage)."""
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise HTTPException(500, "Admin login not configured")
    if payload.username != ADMIN_USERNAME or payload.password != ADMIN_PASSWORD:
        raise HTTPException(401, "Invalid username or password")
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + SESSION_TTL
    _admin_sessions[token] = {"username": payload.username, "expires_at": expires_at}
    return {"token": token}


class BannerUpdate(BaseModel):
    enabled: bool
    notice_type: str
    message: str
    starts_at: str | None = None
    ends_at: str | None = None


@app.put("/api/admin/notices/banner")
def update_banner(payload: BannerUpdate, request: Request, db: Session = Depends(get_db)):
    require_admin(request)

    row = db.query(SiteNotice).filter(SiteNotice.id == 1).first()

    row.enabled = payload.enabled
    row.notice_type = payload.notice_type
    row.message = payload.message
    row.starts_at = payload.starts_at
    row.ends_at = payload.ends_at

    db.commit()

    return {"ok": True}

@app.get("/api/targets/{target_id}/notes")
def get_notes(target_id: int, db: Session = Depends(get_db)):
    notes = (
        db.query(ApiNote)
        .filter(ApiNote.target_id == target_id)
        .order_by(ApiNote.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "created_at": n.created_at.isoformat(),
            }
            for n in notes
        ]
    }

class NoteCreate(BaseModel):
    title: str
    body: str


@app.post("/api/admin/targets/{target_id}/notes")
def create_note(
    target_id: int,
    payload: NoteCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin(request)

    note = ApiNote(
        target_id=target_id,
        title=payload.title,
        body=payload.body,
    )

    db.add(note)
    db.commit()

    return {"ok": True}


# -----------------------------
# Incident Updates API (public GET; POST protected when ENVIRONMENT != "dev")
# -----------------------------

VALID_INCIDENT_STATUSES = {"investigating", "identified", "monitoring", "resolved", "maintenance"}
OPEN_STATUSES = {"investigating", "identified", "monitoring", "maintenance"}  # not resolved


def _incident_timeline_rows(root: IncidentUpdate) -> list[IncidentUpdate]:
    """Root + all updates ordered by created_at."""
    all_rows = [root] + sorted(root.updates, key=lambda u: u.created_at)
    return sorted(all_rows, key=lambda r: r.created_at)


def _latest_status_row(root: IncidentUpdate) -> IncidentUpdate:
    """Row that defines current status/message (latest by created_at)."""
    timeline = _incident_timeline_rows(root)
    return timeline[-1] if timeline else root


@app.get("/api/incidents/current")
def api_incidents_current(db: Session = Depends(get_db)):
    """Single most recent active incident (root only). Kept for backward compat."""
    root = (
        db.query(IncidentUpdate)
        .filter(IncidentUpdate.incident_id.is_(None), IncidentUpdate.is_active == True)
        .order_by(IncidentUpdate.created_at.desc())
        .limit(1)
        .first()
    )
    if not root:
        return {"active": False}
    latest = _latest_status_row(root)
    title = root.title or latest.message[:80] if latest.message else ""
    return {
        "active": True,
        "id": root.id,
        "status": latest.status,
        "title": title or "Incident",
        "message": latest.message,
        "created_at": latest.created_at.isoformat(),
    }


@app.get("/api/incidents/active")
def api_incidents_active(db: Session = Depends(get_db)):
    """List of open incidents (roots with is_active=True). Only Investigating, Identified, Monitoring, Maintenance."""
    roots = (
        db.query(IncidentUpdate)
        .filter(IncidentUpdate.incident_id.is_(None), IncidentUpdate.is_active == True)
        .order_by(IncidentUpdate.created_at.desc())
        .all()
    )
    items = []
    for root in roots:
        latest = _latest_status_row(root)
        items.append({
            "id": root.id,
            "title": root.title or "Incident",
            "affected_service": root.affected_service,
            "status": latest.status,
            "message": latest.message,
            "created_at": root.created_at.isoformat(),
            "updated_at": latest.created_at.isoformat(),
        })
    return {"items": items}


@app.get("/api/incidents/history")
def api_incidents_history(limit: int = 50, db: Session = Depends(get_db)):
    """Resolved incidents for the Incident History section."""
    limit = max(1, min(limit, 100))
    roots = (
        db.query(IncidentUpdate)
        .filter(IncidentUpdate.incident_id.is_(None), IncidentUpdate.is_active == False)
        .order_by(IncidentUpdate.resolved_at.desc().nulls_last(), IncidentUpdate.created_at.desc())
        .limit(limit)
        .all()
    )
    items = []
    for root in roots:
        resolved_at = root.resolved_at or root.created_at
        opened_at = root.created_at
        duration_seconds = int((resolved_at - opened_at).total_seconds()) if resolved_at and opened_at else None
        items.append({
            "id": root.id,
            "title": root.title or "Incident",
            "affected_service": root.affected_service,
            "created_at": opened_at.isoformat(),
            "resolved_at": resolved_at.isoformat() if resolved_at else None,
            "duration_seconds": duration_seconds,
        })
    return {"items": items}


@app.get("/api/incidents/{incident_id}")
def api_incident_get(incident_id: int, db: Session = Depends(get_db)):
    """Full incident with timeline (root + all updates)."""
    root = db.query(IncidentUpdate).filter(
        IncidentUpdate.id == incident_id,
        IncidentUpdate.incident_id.is_(None),
    ).first()
    if not root:
        raise HTTPException(404, "Incident not found")
    timeline = _incident_timeline_rows(root)
    return {
        "id": root.id,
        "title": root.title or "Incident",
        "affected_service": root.affected_service,
        "is_active": root.is_active,
        "created_at": root.created_at.isoformat(),
        "resolved_at": root.resolved_at.isoformat() if root.resolved_at else None,
        "timeline": [
            {
                "id": r.id,
                "status": r.status,
                "title": r.title,
                "message": r.message,
                "created_at": r.created_at.isoformat(),
            }
            for r in timeline
        ],
    }


@app.get("/api/incidents")
def api_incidents_list(limit: int = 20, db: Session = Depends(get_db)):
    """List all incident roots (for admin)."""
    limit = max(1, min(limit, 100))
    rows = (
        db.query(IncidentUpdate)
        .filter(IncidentUpdate.incident_id.is_(None))
        .order_by(IncidentUpdate.created_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        latest = _latest_status_row(r)
        out.append({
            "id": r.id,
            "is_active": r.is_active,
            "status": latest.status,
            "title": r.title or "Incident",
            "message": latest.message,
            "affected_service": r.affected_service,
            "created_at": r.created_at.isoformat(),
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        })
    return {"items": out}


class IncidentCreate(BaseModel):
    status: str
    title: str
    message: str
    is_active: bool | None = True
    affected_service: str | None = None


class IncidentUpdateCreate(BaseModel):
    status: str
    message: str


@app.post("/api/incidents")
def api_incidents_create(
    payload: IncidentCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    require_incident_admin(request)
    if payload.status not in VALID_INCIDENT_STATUSES:
        raise HTTPException(400, f"status must be one of: {sorted(VALID_INCIDENT_STATUSES)}")
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    row = IncidentUpdate(
        incident_id=None,
        is_active=payload.is_active if payload.is_active is not None else True,
        status=payload.status,
        title=title,
        message=(payload.message or "").strip(),
        affected_service=(payload.affected_service or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id}


@app.post("/api/incidents/{incident_id}/updates")
def api_incidents_add_update(
    incident_id: int,
    payload: IncidentUpdateCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    require_incident_admin(request)
    if payload.status not in VALID_INCIDENT_STATUSES:
        raise HTTPException(400, f"status must be one of: {sorted(VALID_INCIDENT_STATUSES)}")
    root = db.query(IncidentUpdate).filter(
        IncidentUpdate.id == incident_id,
        IncidentUpdate.incident_id.is_(None),
    ).first()
    if not root:
        raise HTTPException(404, "Incident not found")
    if not root.is_active:
        raise HTTPException(400, "Cannot add updates to a resolved incident")
    now = datetime.now(timezone.utc)
    update_row = IncidentUpdate(
        incident_id=root.id,
        is_active=True,
        status=payload.status,
        title=None,
        message=(payload.message or "").strip(),
        parent=root,
    )
    db.add(update_row)
    if payload.status == "resolved":
        root.is_active = False
        root.resolved_at = now
    db.commit()
    db.refresh(update_row)
    return {"ok": True, "id": update_row.id}


@app.post("/api/incidents/{incident_id}/resolve")
def api_incidents_resolve(
    incident_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    require_incident_admin(request)
    root = db.query(IncidentUpdate).filter(
        IncidentUpdate.id == incident_id,
        IncidentUpdate.incident_id.is_(None),
    ).first()
    if not root:
        raise HTTPException(404, "Incident not found")
    if not root.is_active:
        return {"ok": True}
    now = datetime.now(timezone.utc)
    update_row = IncidentUpdate(
        incident_id=root.id,
        is_active=False,
        status="resolved",
        title=None,
        message="Incident resolved.",
        parent=root,
    )
    db.add(update_row)
    root.is_active = False
    root.resolved_at = now
    db.commit()
    return {"ok": True}