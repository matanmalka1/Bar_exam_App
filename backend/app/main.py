from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.api.routes import router as auth_router
from app.core.config import CORS_ORIGINS, settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging_config import configure_logging
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.sentry import configure_sentry
from app.db.deps import get_session
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.routers.practice_sessions import router as sessions_router
from app.routers.questions import router as questions_router
from app.routers.stats import router as stats_router
from app.routers.users import router as users_router

configure_logging(settings)
configure_sentry(settings)

app = FastAPI(title="Bar Exam API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]
register_exception_handlers(app)

# Middleware order (add_middleware is LIFO — last added runs first on request path):
# RequestID → RequestLogging → CORS → route
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RequestIDMiddleware)


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
