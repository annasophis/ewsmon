from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.settings import DATABASE_URL
from app.models import Base

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def init_db() -> None:
    # create tables if not exist
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()