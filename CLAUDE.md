# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ewsmon** is a Purolator API health monitoring system. It continuously probes Purolator SOAP/HTTP web services (shipping, tracking, estimates, pickups, freight, etc.) and tracks availability and performance. It provides a real-time status dashboard, 7-day uptime metrics, Teams alert notifications, and customer webhook subscriptions.

## Development Commands

**Start all services (development):**
```bash
docker compose -f docker-compose.dev.yml up -d --build
```

Services:
- `db` — PostgreSQL 16 on host port 5434
- `web` — FastAPI on host port 8008 (container port 8000)
- `worker` — Background probe loop (no exposed port)

**View logs:**
```bash
docker compose -f docker-compose.dev.yml logs -f web
docker compose -f docker-compose.dev.yml logs -f worker
```

**Restart a single service:**
```bash
docker compose -f docker-compose.dev.yml restart worker
```

**Test Teams webhook:**
```bash
python scripts/test_teams_alert.py
```

**Environment setup:**
```bash
cp .env.example .env
# Fill in Purolator credentials (KEY, PASSWORD, ACCOUNT for both PROD and UAT)
# Fill in TEAMS_WEBHOOK_URL, ADMIN_PASSWORD
```

## Architecture

Three Docker services sharing a PostgreSQL database:

```
[PostgreSQL DB]  ←→  [FastAPI Web Server]  ←→  Browser
                 ←→  [Background Worker]
```

### Web Server (`app/main.py`)
FastAPI app serving both the REST API and static HTML/JS frontend. Key endpoints:
- `GET /api/summary` — latest probe state + uptime for all targets (used by dashboard)
- `GET /api/targets/{id}/probes` — recent probes for charting
- `GET /api/targets/{id}/history` — bucketed failure events
- `POST /api/admin/login` — returns session token (in-memory, 7-day TTL)
- Admin endpoints (`/api/admin/*`, `/api/incidents/*`) require Bearer token auth; bypassed in `ENVIRONMENT=dev`

### Background Worker (`app/worker.py`)
Async loop (default 10s interval) that:
1. Fetches enabled targets from DB
2. Probes them concurrently via `httpx.AsyncClient`
3. Persists results to `api_probe`
4. Runs alert state machine and sends notifications
5. Periodically cleans up old probes (configurable retention)

**Alert state machine:**
- **DOWN**: triggers after `ALERT_FAILURE_THRESHOLD` (default 3) consecutive failures, with a per-target cooldown of `ALERT_COOLDOWN_SECONDS` (default 300s)
- **RECOVERED**: requires 2 consecutive successful probes after a down period
- State is persisted in `target_state` table so it survives restarts

### SOAP Payloads (`app/payloads.py`)
Builds SOAP XML request bodies and headers for each Purolator API type. Each builder function takes test data from environment variables (pins, account numbers, dates) and returns `(xml_string, headers_dict)`. When adding a new probe type, add a builder here.

### Database Models (`app/models.py`)
Key tables:
- `api_target` — endpoints to monitor (`name`, `url`, `api_type`, `enabled`)
- `api_probe` — individual probe results (`target_id`, `ts`, `ok`, `http_status`, `duration_ms`, `error`)
- `target_state` — persistent alert state per target (`consecutive_failures`, `pending_recovered`, `last_down_alert_ts`)
- `api_daily_rollup` — aggregated daily stats
- `webhook_subscription` — customer webhook subscriptions with HMAC-SHA256 signing
- `site_notice`, `api_note`, `incident_update` — admin/ops features

### Seeding (`app/seed.py`)
On first run, seeds 14 default Purolator targets. Each SOAP target is duplicated as a UAT variant (host changes to `certwebservices.purolator.com`, name gets ` (UAT)` suffix), resulting in ~26 total targets.

### Notifications (`app/notifications.py`)
Sends Teams Adaptive Cards to `TEAMS_WEBHOOK_URL`. Logs failures but never crashes the worker.

### Frontend (`app/static/`)
Vanilla JS with no framework. `app.js` polls `/api/summary` every ~30s and renders charts. Admin features require a login session stored in `localStorage`.

## Key Configuration Variables

| Variable | Default | Purpose |
|---|---|---|
| `POLL_INTERVAL_SECONDS` | 10 | Worker probe interval |
| `HTTP_TIMEOUT_SECONDS` | 20 | Per-probe timeout |
| `ALERT_FAILURE_THRESHOLD` | 3 | Consecutive failures before DOWN alert |
| `ALERT_COOLDOWN_SECONDS` | 300 | Min seconds between DOWN alerts per target |
| `PROBE_RETENTION_DAYS` | 14 | Cleanup age for old probes |
| `ENVIRONMENT` | — | Set to `dev` to bypass admin auth |
| `TEAMS_WEBHOOK_URL` | — | Optional Teams alert destination |

## Deployment

Push to `main` triggers `.github/workflows/deploy_ts140.yml`, which SSHs into the TS140 self-hosted runner at `/home/bruno/docker/ewsmon`, pulls latest, rebuilds images, and recreates containers.

## Critical Conventions

### Alert State Machine — Critical Invariants
Two invariants that must both hold to prevent spurious RECOVERED alerts:

1. `pending_recovered` must ONLY be set to `True` when `last_down_alert_ts is not None`
   (line ~501). Without this gate, targets that never sent a DOWN alert can trigger RECOVERED.

2. `last_down_alert_ts` must be reset to `None` when RECOVERED fires (line ~374).
   Without this reset, `last_down_alert_ts` leaks into subsequent incidents: the
   startup-DOWN same-state path (`last_down_alert_ts is None`) never fires, so no DOWN
   is sent for the new incident, but the DOWN→UP flip still sets `pending_recovered=True`
   (because `last_down_alert_ts is not None` from the old incident), producing a RECOVERED
   with no corresponding DOWN. Root cause of 66 RECOVERED vs 3 DOWN in production.

### Database
- Migrations use raw SQL via `op.execute()` only — never use Alembic ORM helpers
- Soft delete only — never hard delete targets or states
- After `db.commit()`, always re-fetch with `selectinload` before returning

### API / HTMX
- HTMX error responses return HTTP 200, not 4xx
- Never instantiate `Jinja2Templates` in routers

### Code Style
- Never generate Excel files — structured text/JSON only
- Route ordering matters in FastAPI — specific routes before parameterized ones
```
