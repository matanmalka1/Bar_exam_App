from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.api.routes import router as auth_router
from app.core.config import CORS_ORIGINS
from app.db.deps import get_session
from app.routers.practice_sessions import router as sessions_router
from app.routers.questions import router as questions_router
from app.routers.stats import router as stats_router
from app.routers.users import router as users_router

app = FastAPI(title="Bar Exam API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready(session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    return {"status": "ready"}


app.include_router(auth_router, prefix="/api/v1")
app.include_router(questions_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(stats_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
