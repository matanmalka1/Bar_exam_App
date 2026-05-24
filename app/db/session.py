from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.config import normalize_database_url, settings

engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global engine
    if engine is None:
        engine = create_engine(normalize_database_url(settings.DATABASE_URL))
    return engine


def get_sessionmaker() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal


def SessionLocal():  # noqa: N802
    return get_sessionmaker()()
