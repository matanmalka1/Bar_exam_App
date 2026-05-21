from pydantic import BaseModel, EmailStr, field_validator

from app.auth.password_policy import validate_password


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password(v)


class ResetPasswordResponse(BaseModel):
    message: str
