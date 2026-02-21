import os
from dotenv import load_dotenv

load_dotenv()

# ----------------------------
# DB
# ----------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://ews:ews@db:5432/ews")

# ----------------------------
# Worker config
# ----------------------------
# keep old name but map it to what worker expects
WORKER_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))

# timeout for SOAP calls
HTTP_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "20"))

# ----------------------------
# Purolator creds
# ----------------------------
PUROLATOR_KEY = os.getenv("PUROLATOR_KEY", "")
PUROLATOR_PASSWORD = os.getenv("PUROLATOR_PASSWORD", "")
PUROLATOR_ACCOUNT = os.getenv("PUROLATOR_ACCOUNT", "")

# ----------------------------
# Alerts (future)
# ----------------------------
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

# ----------------------------
# DB Clean Up
# ----------------------------
PROBE_RETENTION_DAYS = int(os.getenv("PROBE_RETENTION_DAYS", "14"))
CLEANUP_EVERY_SECONDS = int(os.getenv("CLEANUP_EVERY_SECONDS", str(60*60)))  # 1 hour