# app/worker.py
from __future__ import annotations

import asyncio
import hmac
import hashlib
import json
import time
from datetime import datetime
from typing import Tuple, Dict, Optional
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.logger import configure_root_logging, get_logger
from app.models import ApiTarget, ApiProbe, WebhookSubscription, TargetState
from app import notifications
from app import payloads
import app.settings as settings

log = get_logger(__name__)


def _now_et_iso() -> str:
    """Current time in America/Toronto (ET) for alert cards."""
    return datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %I:%M:%S %p ET")


def _is_uat_target(target: ApiTarget) -> bool:
    """
    Detect cert/UAT targets based on the host.
    (Seed uses certwebservices.purolator.com)
    """
    return "://certwebservices.purolator.com" in (target.url or "")


def _env_auth_and_account(target: ApiTarget) -> tuple[str, str, str]:
    """
    Returns (key, password, account) for the target environment.
    """
    if _is_uat_target(target):
        return (
            getattr(settings, "PUROLATOR_UAT_KEY", "") or "",
            getattr(settings, "PUROLATOR_UAT_PASSWORD", "") or "",
            getattr(settings, "PUROLATOR_UAT_ACCOUNT", "") or "",
        )
    return (
        getattr(settings, "PUROLATOR_KEY", "") or "",
        getattr(settings, "PUROLATOR_PASSWORD", "") or "",
        getattr(settings, "PUROLATOR_ACCOUNT", "") or "",
    )


def _env_label(target: ApiTarget) -> str:
    return "UAT" if _is_uat_target(target) else "PROD"


def build_payload(target: ApiTarget, acct: str) -> Tuple[Optional[str], Dict[str, str]]:
    """
    Returns: (soap_xml_string or None, headers_dict)

    If soap_xml is None, caller should treat it as a failed probe
    and store an error message (instead of crashing the worker).
    """
    builders = {
        "validate": payloads.build_validate_payload,
        "track": payloads.build_track_payload,
        "freighttrack": payloads.build_freighttrack_payload,
        "freightestimate": payloads.build_freightestimate_payload,
        "freightshipping": payloads.build_freightshipping_payload,
        "locate": payloads.build_locate_payload,
        "estimate": payloads.build_estimate_payload,
        "pickup": payloads.build_pickup_payload,
        "sa": payloads.build_sa_payload,
        "shiptrack": payloads.build_shiptrack_payload,
        "return": payloads.build_return_payload,
        "docservice": payloads.build_docservice_payload,
    }
    builder = builders.get(target.api_type)
    if builder is not None:
        soap_xml, headers = builder(target, acct)
        return soap_xml, headers
    # http or unknown: no SOAP payload
    headers: Dict[str, str] = {
        "Content-Type": "text/xml;charset=UTF-8",
    }
    if target.soap_action:
        headers["SOAPAction"] = target.soap_action
    return None, headers



async def probe_one(client: httpx.AsyncClient, target: ApiTarget) -> dict:
    # HTTP targets — simple GET, no auth, no SOAP
    if target.api_type == "http":
        start = time.perf_counter()
        try:
            resp = await client.get(target.url)
            ms = (time.perf_counter() - start) * 1000.0
            ok = resp.status_code < 500
            return {"ok": ok, "status": resp.status_code, "ms": ms, "error": None if ok else f"http {resp.status_code}"}
        except Exception as e:
            ms = (time.perf_counter() - start) * 1000.0
            return {"ok": False, "status": None, "ms": ms, "error": f"{type(e).__name__}: {e}"}
    key, pwd, acct = _env_auth_and_account(target)
    soap_xml, headers = build_payload(target, acct)

    if not soap_xml:
        return {
            "ok": False,
            "status": None,
            "ms": None,
            "error": f"payload not implemented for api_type={target.api_type}",
        }

    # Avoid noisy errors if env vars are missing
    if not key or not pwd:
        env = _env_label(target)
        return {"ok": False, "status": None, "ms": None, "error": f"missing creds for {env} (PUROLATOR_* env vars)"}

    start = time.perf_counter()
    try:
        resp = await client.post(
            target.url,
            content=soap_xml,
            headers=headers,
            auth=(key, pwd),
        )
        ms = (time.perf_counter() - start) * 1000.0

        ok = resp.status_code == 200
        if ok:
            return {"ok": True, "status": resp.status_code, "ms": ms, "error": None}

        # Capture some upstream info for debugging (stored in ApiProbe.error)
        ct = resp.headers.get("content-type", "")
        body_snip = (resp.text or "")[:800].replace("\n", "\\n")
        err = f"[{_env_label(target)}] http {resp.status_code} ct={ct} body_snip={body_snip}"

        return {"ok": False, "status": resp.status_code, "ms": ms, "error": err}

    except Exception as e:
        ms = (time.perf_counter() - start) * 1000.0
        return {"ok": False, "status": None, "ms": ms, "error": f"[{_env_label(target)}] {type(e).__name__}: {e}"}


def persist_probes(db: Session, results: list[tuple[int, dict]]) -> int:
    """
    Insert probe rows for this cycle.
    Returns number inserted.
    """
    for target_id, probe in results:
        db.add(
            ApiProbe(
                target_id=target_id,
                ok=bool(probe.get("ok")),
                http_status=probe.get("status"),
                duration_ms=probe.get("ms"),
                error=probe.get("error"),
            )
        )
    db.commit()
    return len(results)


def cleanup_old_probes(db: Session, days: int) -> int:
    """
    Delete probes older than `days` days.
    Returns number deleted.
    """
    res = db.execute(
        text(
            """
            delete from api_probe
            where ts < (now() - (:days || ' days')::interval)
            """
        ),
        {"days": int(days)},
    )
    db.commit()
    return int(res.rowcount or 0)


def get_previous_probe_state(db: Session, target_ids: list[int]) -> dict[int, bool]:
    """
    For each target_id, return the ok state of the most recent probe before this cycle.
    Returns {target_id: ok}. Missing target_ids have no prior probe.
    """
    if not target_ids:
        return {}
    # PostgreSQL: DISTINCT ON (target_id) with ORDER BY target_id, ts DESC gives latest per target
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (target_id) target_id, ok
            FROM api_probe
            WHERE target_id = ANY(:target_ids)
            ORDER BY target_id, ts DESC
            """
        ),
        {"target_ids": target_ids},
    ).fetchall()
    return {int(r[0]): bool(r[1]) for r in rows}


def get_target_state(db: Session, target_id: int) -> TargetState:
    """Fetch or create a TargetState row for the given target_id."""
    state = db.get(TargetState, target_id)
    if state is not None:
        return state
    state = TargetState(target_id=target_id)
    db.add(state)
    db.flush()
    return state


def save_target_state(db: Session, state: TargetState) -> None:
    """Commit the state row."""
    db.commit()


WEBHOOK_REQUEST_TIMEOUT = 5


async def fire_customer_webhooks(event_type: str, payload: dict) -> None:
    """
    POST payload to all active webhook subscriptions that subscribe to event_type.
    event_type is one of: up, down, incident, maintenance.
    Sends Content-Type: application/json and X-Webhook-Signature (HMAC-SHA256 of JSON body).
    Uses httpx with 5s timeout; logs success/failure, does not raise.
    """
    with SessionLocal() as db:
        subs = db.query(WebhookSubscription).filter(WebhookSubscription.active == True).all()
        log.info("fire_customer_webhooks called", extra={"event_type": event_type, "subs_found": len(subs)})

    subscribed = [
        s for s in subs
        if event_type in [e.strip() for e in (s.events or "").split(",") if e.strip()]
    ]
    if not subscribed:
        return
    body = json.dumps(payload).encode("utf-8")
    async with httpx.AsyncClient() as client:
        for sub in subscribed:
            try:
                sig = hmac.new(
                    sub.secret.encode("utf-8"),
                    body,
                    hashlib.sha256,
                ).hexdigest()
                headers = {
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": f"sha256={sig}",
                }
                r = await client.post(sub.url, content=body, headers=headers, timeout=WEBHOOK_REQUEST_TIMEOUT)
                if r.is_success:
                    log.info(
                        "webhook delivered",
                        extra={"webhook_id": sub.id, "event_type": event_type, "status_code": r.status_code},
                    )
                else:
                    log.warning(
                        "webhook delivery failed",
                        extra={"webhook_id": sub.id, "event_type": event_type, "status_code": r.status_code, "response": (r.text or "")[:200]},
                    )
            except Exception as e:
                log.warning(
                    "webhook delivery error",
                    extra={"webhook_id": sub.id, "event_type": event_type, "error": str(e), "error_type": type(e).__name__},
                )


def _is_up(probe: dict) -> bool:
    """Current app: ok is True only for status 200. Treat that as UP."""
    return bool(probe.get("ok"))


async def main():
    configure_root_logging()
    init_db()

    # Support both names (your settings.py currently defines WORKER_INTERVAL_SECONDS)
    interval = int(getattr(settings, "POLL_INTERVAL_SECONDS", getattr(settings, "WORKER_INTERVAL_SECONDS", 30)))
    timeout_seconds = int(getattr(settings, "HTTP_TIMEOUT_SECONDS", 20))
    cleanup_every = int(getattr(settings, "CLEANUP_EVERY_SECONDS", 300))
    retention_days = int(getattr(settings, "PROBE_RETENTION_DAYS", 7))

    timeout = httpx.Timeout(timeout_seconds)
    last_cleanup = 0.0

    log.info(
        "worker started",
        extra={"interval_seconds": interval, "timeout_seconds": timeout_seconds},
    )

    async with httpx.AsyncClient(http2=False, timeout=timeout) as client:
        while True:
            # Fetch targets using a short-lived session
            with SessionLocal() as db:
                targets = db.scalars(select(ApiTarget).where(ApiTarget.enabled == True)).all()

            if not targets:
                log.warning("no enabled targets")
            else:
                tasks = [probe_one(client, t) for t in targets]
                probes = await asyncio.gather(*tasks)
                results = list(zip([t.id for t in targets], probes))

                # Persist + cleanup + state-change alerts (same session for consistent prev state)
                target_ids = [t.id for t in targets]
                id_to_target = {t.id: t for t in targets}
                with SessionLocal() as db:
                    prev_state = get_previous_probe_state(db, target_ids)
                    inserted = persist_probes(db, results)

                    now = time.time()
                    if now - last_cleanup >= cleanup_every:
                        deleted = cleanup_old_probes(db, retention_days)
                        log.info(
                            "cleanup: deleted old probes",
                            extra={"deleted": deleted, "retention_days": retention_days},
                        )
                        last_cleanup = now

                    # State-change alerts: DOWN (with cooldown + consecutive-failure threshold); RECOVERED only after 2 consecutive UPs (stable)
                    webhook_url = getattr(settings, "TEAMS_WEBHOOK_URL", "") or ""
                    cooldown_sec = int(getattr(settings, "ALERT_COOLDOWN_SECONDS", 300))
                    failure_threshold = int(getattr(settings, "ALERT_FAILURE_THRESHOLD", 3))
                    for target_id, probe in results:
                        try:
                            state = get_target_state(db, target_id)
                        except Exception as e:
                            log.warning(
                                "get_target_state failed, skipping alert logic for target",
                                extra={"target_id": target_id, "error": str(e), "error_type": type(e).__name__},
                            )
                            continue

                        current_up = _is_up(probe)
                        if current_up:
                            state.consecutive_failures = 0
                        else:
                            state.consecutive_failures = state.consecutive_failures + 1

                        prev_up = prev_state.get(target_id)
                        if prev_up is None:
                            try:
                                save_target_state(db, state)
                            except Exception as e:
                                log.warning(
                                    "save_target_state failed",
                                    extra={"target_id": target_id, "error": str(e), "error_type": type(e).__name__},
                                )
                            continue
                        target = id_to_target.get(target_id)
                        if not target or not webhook_url:
                            try:
                                save_target_state(db, state)
                            except Exception as e:
                                log.warning(
                                    "save_target_state failed",
                                    extra={"target_id": target_id, "error": str(e), "error_type": type(e).__name__},
                                )
                            continue

                        # Same state as last time: check RECOVERED (2nd consecutive UP); handle startup-DOWN; no re-alerts while DOWN
                        if prev_up == current_up:
                            if current_up and state.pending_recovered:
                                # Stable: two UPs in a row after a DOWN -> send RECOVERED
                                state.pending_recovered = False
                                state.consecutive_failures = 0
                                state.last_down_alert_ts = None  # reset so the next incident starts fresh
                                status_str = str(probe.get("status")) if probe.get("status") is not None else "timeout"
                                latency = probe.get("ms")
                                latency_str = f"{latency:.0f} ms" if latency is not None else "—"
                                time_str = _now_et_iso()
                                env = _env_label(target)
                                facts = {
                                    "Service": target.name,
                                    "Environment": env,
                                    "URL": target.url or "—",
                                    "HTTP Status": status_str,
                                    "Last Latency": latency_str,
                                    "Time": time_str,
                                }
                                await notifications.send_teams_card(
                                    f"{target.name} RECOVERED",
                                    "State change detected by EWS Monitoring (stable)",
                                    facts,
                                    webhook_url,
                                )
                                webhook_payload = {
                                    "event_type": "up",
                                    "service": target.name,
                                    "environment": env,
                                    "url": target.url or "",
                                    "http_status": status_str,
                                    "last_latency_ms": probe.get("ms"),
                                    "time": time_str,
                                }
                                await fire_customer_webhooks("up", webhook_payload)
                                log.info(
                                    "alert sent",
                                    extra={
                                        "target_id": target_id,
                                        "prev_up": prev_up,
                                        "current_up": current_up,
                                        "status_code": probe.get("status"),
                                        "latency_ms": probe.get("ms"),
                                    },
                                )
                                try:
                                    save_target_state(db, state)
                                except Exception as e:
                                    log.warning(
                                        "save_target_state failed",
                                        extra={"target_id": target_id, "error": str(e), "error_type": type(e).__name__},
                                    )
                            elif (
                                not current_up
                                and state.last_down_alert_ts is None
                                and state.consecutive_failures >= failure_threshold
                            ):
                                # Service was already DOWN when worker started: send initial DOWN (then behave like normal DOWN state)
                                if (state.last_down_alert_ts is not None) and (
                                    now - state.last_down_alert_ts < cooldown_sec
                                ):
                                    try:
                                        save_target_state(db, state)
                                    except Exception as e:
                                        log.warning(
                                            "save_target_state failed",
                                            extra={"target_id": target_id, "error": str(e), "error_type": type(e).__name__},
                                        )
                                else:
                                    status_str = str(probe.get("status")) if probe.get("status") is not None else "timeout"
                                    latency = probe.get("ms")
                                    latency_str = f"{latency:.0f} ms" if latency is not None else "—"
                                    time_str = _now_et_iso()
                                    env = _env_label(target)
                                    facts = {
                                        "Service": target.name,
                                        "Environment": env,
                                        "URL": target.url or "—",
                                        "HTTP Status": status_str,
                                        "Last Latency": latency_str,
                                        "Time": time_str,
                                    }
                                    await notifications.send_teams_card(
                                        f"{target.name} DOWN",
                                        "State change detected by EWS Monitoring",
                                        facts,
                                        webhook_url,
                                    )
                                    log.info(
                                        "about to fire customer webhooks",
                                        extra={"target_id": target_id, "event_type": "down"},
                                    )
                                    webhook_payload = {
                                        "event_type": "down",
                                        "service": target.name,
                                        "environment": env,
                                        "url": target.url or "",
                                        "http_status": status_str,
                                        "last_latency_ms": probe.get("ms"),
                                        "time": time_str,
                                    }
                                    await fire_customer_webhooks("down", webhook_payload)
                                    state.last_down_alert_ts = now
                                    log.info(
                                        "alert sent",
                                        extra={
                                            "target_id": target_id,
                                            "prev_up": prev_up,
                                            "current_up": current_up,
                                            "status_code": probe.get("status"),
                                            "latency_ms": probe.get("ms"),
                                        },
                                    )
                                    try:
                                        save_target_state(db, state)
                                    except Exception as e:
                                        log.warning(
                                            "save_target_state failed",
                                            extra={"target_id": target_id, "error": str(e), "error_type": type(e).__name__},
                                        )
                            else:
                                # Same state but no alert sent (e.g. current_up and not pending_recovered); still persist consecutive_failures
                                try:
                                    save_target_state(db, state)
                                except Exception as e:
                                    log.warning(
                                        "save_target_state failed",
                                        extra={"target_id": target_id, "error": str(e), "error_type": type(e).__name__},
                                    )
                            continue

                        # State flip
                        if not prev_up and current_up and state.last_down_alert_ts is not None:
                            # DOWN -> UP: wait for one more UP before sending RECOVERED (stable)
                            state.pending_recovered = True
                            try:
                                save_target_state(db, state)
                            except Exception as e:
                                log.warning(
                                    "save_target_state failed",
                                    extra={"target_id": target_id, "error": str(e), "error_type": type(e).__name__},
                                )
                            continue
                        # UP -> DOWN: only send DOWN when consecutive failures reach threshold (then cooldown applies)
                        state.pending_recovered = False
                        if state.consecutive_failures < failure_threshold:
                            try:
                                save_target_state(db, state)
                            except Exception as e:
                                log.warning(
                                    "save_target_state failed",
                                    extra={"target_id": target_id, "error": str(e), "error_type": type(e).__name__},
                                )
                            continue
                        if (state.last_down_alert_ts is not None) and (
                            now - state.last_down_alert_ts < cooldown_sec
                        ):
                            try:
                                save_target_state(db, state)
                            except Exception as e:
                                log.warning(
                                    "save_target_state failed",
                                    extra={"target_id": target_id, "error": str(e), "error_type": type(e).__name__},
                                )
                            continue
                        status_str = str(probe.get("status")) if probe.get("status") is not None else "timeout"
                        latency = probe.get("ms")
                        latency_str = f"{latency:.0f} ms" if latency is not None else "—"
                        time_str = _now_et_iso()
                        env = _env_label(target)
                        facts = {
                            "Service": target.name,
                            "Environment": env,
                            "URL": target.url or "—",
                            "HTTP Status": status_str,
                            "Last Latency": latency_str,
                            "Time": time_str,
                        }
                        await notifications.send_teams_card(
                            f"{target.name} DOWN",
                            "State change detected by EWS Monitoring",
                            facts,
                            webhook_url,
                        )
                        log.info("about to fire customer webhooks", extra={"target_id": target_id, "event_type": "down"})

                        webhook_payload = {
                            "event_type": "down",
                            "service": target.name,
                            "environment": env,
                            "url": target.url or "",
                            "http_status": status_str,
                            "last_latency_ms": probe.get("ms"),
                            "time": time_str,
                        }
                        await fire_customer_webhooks("down", webhook_payload)
                        state.last_down_alert_ts = now
                        log.info(
                            "alert sent",
                            extra={
                                "target_id": target_id,
                                "prev_up": prev_up,
                                "current_up": current_up,
                                "status_code": probe.get("status"),
                                "latency_ms": probe.get("ms"),
                            },
                        )
                        try:
                            save_target_state(db, state)
                        except Exception as e:
                            log.warning(
                                "save_target_state failed",
                                extra={"target_id": target_id, "error": str(e), "error_type": type(e).__name__},
                            )

                ok_count = sum(1 for _, r in results if r.get("ok"))
                log.info(
                    "probe cycle completed",
                    extra={"targets": inserted, "ok": ok_count},
                )

            await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())