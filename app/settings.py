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

# UAT (cert) creds
PUROLATOR_UAT_KEY = os.getenv("PUROLATOR_UAT_KEY", "")
PUROLATOR_UAT_PASSWORD = os.getenv("PUROLATOR_UAT_PASSWORD", "")
PUROLATOR_UAT_ACCOUNT = os.getenv("PUROLATOR_UAT_ACCOUNT", "")

# Optional: environment-specific test data (pins / tracking ids)
PUROLATOR_TRACK_PIN = os.getenv("PUROLATOR_TRACK_PIN", "335258857374")
PUROLATOR_TRACK_PIN_UAT = os.getenv("PUROLATOR_TRACK_PIN_UAT", PUROLATOR_TRACK_PIN)

PUROLATOR_SHIPTRACK_ID = os.getenv("PUROLATOR_SHIPTRACK_ID", "520111990344")
PUROLATOR_SHIPTRACK_ID_UAT = os.getenv("PUROLATOR_SHIPTRACK_ID_UAT", PUROLATOR_SHIPTRACK_ID)

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

# ----------------------------
# Future Admin Backend
# ----------------------------

ADMIN_KEY = os.getenv("ADMIN_KEY", "")