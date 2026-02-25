# Teams webhook alerts

Alerts are sent only on **state changes**, not every probe cycle.

- **DOWN**: Sent when the service goes from UP to DOWN. Cooldown applies here only (default 300s per target) to avoid spam when flapping (e.g. timeouts, wifi drops).
- **RECOVERED**: Sent only after the service is **stable** again: we require **2 consecutive UP** probes. So DOWN→UP sets a “pending recovered”; the next cycle if still UP we send RECOVERED. No cooldown on RECOVERED so you get it as soon as it’s stable.

## Configuration

- **`TEAMS_WEBHOOK_URL`** (optional): Teams Workflows webhook URL. If empty or unset, alerts are disabled.
- **`ALERT_COOLDOWN_SECONDS`** (optional, default `300`): Minimum seconds between **DOWN** alerts per target. Does not delay RECOVERED.

See `.env.example` for all env vars.

## Testing the webhook

Send a test card without running the worker:

```bash
export TEAMS_WEBHOOK_URL="https://your-workflow-webhook-url"
python scripts/test_teams_alert.py
```

Or from Python (with `python-dotenv` loaded):

```python
import asyncio
from app.notifications import send_teams_card
from datetime import datetime, timezone

async def test():
    await send_teams_card(
        title="✅ My Service RECOVERED",
        subtitle="State change detected by EWS Monitoring",
        facts={
            "Service": "My Service",
            "Environment": "dev",
            "URL": "https://example.com/ews",
            "HTTP Status": "200",
            "Last Latency": "45 ms",
            "Time": datetime.now(timezone.utc).isoformat(),
        },
        webhook_url="https://your-teams-webhook-url",
    )
asyncio.run(test())
```

## Testing state-change alerts (force DOWN)

1. **Temporarily disable a target** in the admin UI so it stops being probed, or
2. **Point a test target’s URL** to an invalid endpoint or one that returns 5xx, run the worker until it probes it, then fix the URL so the next probe is UP — you should get one DOWN alert and one RECOVERED alert (subject to cooldown).

With `ALERT_COOLDOWN_SECONDS=0` you can test back-to-back transitions without waiting.
