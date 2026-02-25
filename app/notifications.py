"""
Teams webhook notifications for EWS Monitoring.

Sends Adaptive Cards to a Teams Workflows webhook on state changes (UP->DOWN, DOWN->UP).
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.logger import get_logger

log = get_logger(__name__)

TEAMS_POST_TIMEOUT = 5.0
MAX_PAYLOAD_BYTES = 256 * 1024  # 256KB


def _build_adaptive_card(title: str, subtitle: str, facts: dict[str, str]) -> dict[str, Any]:
    """Build an Adaptive Card 1.4 body with title, subtitle, and a FactSet."""
    body: list[dict[str, Any]] = [
        {"type": "TextBlock", "text": title, "size": "Large", "weight": "Bolder", "wrap": True},
        {"type": "TextBlock", "text": subtitle, "wrap": True, "spacing": "Small"},
        {
            "type": "FactSet",
            "facts": [{"title": k, "value": str(v)[:500]} for k, v in facts.items()],
        },
    ]
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }


async def send_teams_card(
    title: str,
    subtitle: str,
    facts: dict[str, str],
    webhook_url: str,
) -> None:
    """
    POST an Adaptive Card to a Teams Workflows webhook.

    Uses attachments format: [{ contentType, content }].
    On failure, logs a warning and returns without raising.
    """
    if not webhook_url or not webhook_url.strip():
        return
    content = _build_adaptive_card(title, subtitle, facts)
    payload = {
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": content,
            }
        ]
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    if len(payload_bytes) > MAX_PAYLOAD_BYTES:
        log.warning(
            "teams card payload too large, skipping send",
            extra={"size": len(payload_bytes), "max": MAX_PAYLOAD_BYTES},
        )
        return
    try:
        async with httpx.AsyncClient(timeout=TEAMS_POST_TIMEOUT) as client:
            r = await client.post(webhook_url, json=payload)
            if r.is_error:
                log.warning(
                    "teams webhook request failed",
                    extra={"status_code": r.status_code, "response": (r.text or "")[:200]},
                )
    except Exception as e:
        log.warning(
            "teams webhook request error",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
