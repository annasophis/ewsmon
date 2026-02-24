# app/main.py
from __future__ import annotations

from datetime import datetime, timezone
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
from app.models import SiteNotice, ApiNote

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

    log.info("web startup complete", extra={"env": ENVIRONMENT})


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "env": ENVIRONMENT}


from fastapi.responses import RedirectResponse

@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(url="/static/index.html")

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

    items: list[dict[str, Any]] = []
    up = 0
    down = 0
    slowest_name = None
    slowest_ms = None

    for r in rows:
        last_ok = bool(r["last_ok"]) if r["last_ok"] is not None else False
        is_up = bool(r["last_checked"]) and last_ok

        if is_up:
            up += 1
        else:
            down += 1

        last_ms = float(r["last_ms"]) if r["last_ms"] is not None else None
        if last_ms is not None and (slowest_ms is None or last_ms > slowest_ms):
            slowest_ms = last_ms
            slowest_name = r["name"]

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
            "slowest_last": {
                "name": slowest_name,
                "ms": round(slowest_ms, 2) if slowest_ms is not None else None,
            },
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

from fastapi import HTTPException, Request
from app.settings import ADMIN_KEY

def require_admin(request: Request):
    if not ADMIN_KEY:
        raise HTTPException(500, "ADMIN_KEY not set")
    if request.headers.get("x-admin-key") != ADMIN_KEY:
        raise HTTPException(401, "Unauthorized")
    

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