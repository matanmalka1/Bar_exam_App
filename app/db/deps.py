from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
