"""
Database engine and session configuration.

SQLite is used per the task brief's allowed options. It is file-based,
requires no external service, and is sufficient for the scope of this
project (single-process demo app, not a production HR system).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./leave_scheduler.db")

# check_same_thread=False is required for SQLite when used with FastAPI's
# threaded request handling in a demo/single-file context.
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
