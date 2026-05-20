from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.db.deps import get_session
from app.schemas.stats import StatsOverviewOut
from app.services import stats_service
from app.services.stats_service import StatsError

router = APIRouter()


@router.get("/users/me/stats/overview", response_model=StatsOverviewOut)
def get_my_stats_overview(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> StatsOverviewOut:
    try:
        return stats_service.get_overview(session, current_user.id)
    except StatsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
