from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=128)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def _trim_full_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("full_name must not be blank")
        return trimmed

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email_input(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v


class AuthUserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserOut


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
