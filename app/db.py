from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.settings import DATABASE_URL
from app.models import Base
from app.logger import get_logger

log = get_logger(__name__)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _migrate_incident_update() -> None:
    """Add new columns to incident_update for existing PostgreSQL DBs."""
    if "postgresql" not in DATABASE_URL:
        return
    with engine.connect() as conn:
        for col, typ in [
            ("incident_id", "INTEGER REFERENCES incident_update(id) ON DELETE CASCADE"),
            ("affected_service", "VARCHAR(200)"),
            ("resolved_at", "TIMESTAMP WITH TIME ZONE"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE incident_update ADD COLUMN IF NOT EXISTS {col} {typ}"))
                conn.commit()
            except Exception as e:
                log.debug("migrate incident_update column %s: %s", col, e)
        try:
            conn.execute(text("ALTER TABLE incident_update ALTER COLUMN title DROP NOT NULL"))
            conn.commit()
        except Exception as e:
            log.debug("migrate incident_update title nullable: %s", e)


def init_db() -> None:
    # create tables if not exist
    Base.metadata.create_all(bind=engine)
    _migrate_incident_update()
    log.debug("database initialized")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()