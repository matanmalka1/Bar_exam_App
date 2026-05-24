from typing import Any

STATUS_ERROR_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "unprocessable_entity",
    429: "rate_limit_exceeded",
}

STATUS_ERROR_MESSAGES = {
    401: "יש להתחבר כדי להמשיך",
    403: "אין לך הרשאה לבצע פעולה זו",
    404: "המשאב המבוקש לא נמצא",
    409: "הפעולה מתנגשת עם מצב קיים",
    422: "חלק מהנתונים אינם תקינים",
    429: "יותר מדי ניסיונות. נסה שוב מאוחר יותר",
    500: "אירעה שגיאה לא צפויה",
}


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def app_error_code_for_status(status_code: int) -> str:
    return STATUS_ERROR_CODES.get(status_code, "application_error")


def app_error_message_for_status(status_code: int) -> str:
    return STATUS_ERROR_MESSAGES.get(status_code, "אירעה שגיאה בבקשה")


def http_error_code_for_status(status_code: int) -> str:
    return STATUS_ERROR_CODES.get(status_code, "http_error")


def http_error_message_for_status(status_code: int) -> str:
    return STATUS_ERROR_MESSAGES.get(status_code, "אירעה שגיאה בבקשה")


def contains_hebrew(value: str) -> bool:
    return any("\u0590" <= char <= "\u05ff" for char in value)


def frontend_safe_details(detail: str) -> dict[str, str] | None:
    return None if contains_hebrew(detail) else {"detail": detail}
