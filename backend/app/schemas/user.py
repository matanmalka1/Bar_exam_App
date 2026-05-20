from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    id: int
    display_name: str
    user_key: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
