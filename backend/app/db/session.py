from collections.abc import Generator
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/bar_exam_study",
)

engine = create_engine(DATABASE_URL)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
