#!/usr/bin/env python3
"""
Test Teams webhook without running the worker.

Usage:
  export TEAMS_WEBHOOK_URL="https://..."
  python scripts/test_teams_alert.py

Or with dotenv (from repo root):
  python -c "from dotenv import load_dotenv; load_dotenv(); from scripts.test_teams_alert import run; import asyncio; asyncio.run(run())"
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

# Run from repo root so app is importable
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _repo_root)

# Load .env from repo root if present (no python-dotenv required)
_env_path = os.path.join(_repo_root, ".env")
if os.path.isfile(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if v.startswith('"') and v.endswith('"'):
                    v = v[1:-1].replace('\\"', '"')
                elif v.startswith("'") and v.endswith("'"):
                    v = v[1:-1].replace("\\'", "'")
                if k and k not in os.environ:
                    os.environ[k] = v

from app.notifications import send_teams_card


async def run() -> None:
    url = os.getenv("TEAMS_WEBHOOK_URL", "").strip()
    if not url:
        print("Set TEAMS_WEBHOOK_URL in .env or environment and run again.")
        return
    facts = {
        "Service": "Shipping (test)",
        "Environment": os.getenv("ENVIRONMENT", "dev"),
        "URL": "https://example.com/ews",
        "HTTP Status": "500",
        "Last Latency": "1200 ms",
        "Time": datetime.now(timezone.utc).isoformat(),
    }
    await send_teams_card(
        title="🚨 Shipping (test) DOWN",
        subtitle="State change detected by EWS Monitoring (test run)",
        facts=facts,
        webhook_url=url,
    )
    print("Sent test card to Teams webhook.")


if __name__ == "__main__":
    asyncio.run(run())
