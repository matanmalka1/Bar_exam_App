import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"
_MAX_PROVIDER_ERROR_BODY_LENGTH = 1000


class EmailDeliveryError(RuntimeError):
    """Raised when the configured email provider cannot accept the message."""


def send_password_reset_email(to_email: str, first_name: str, reset_link: str) -> None:
    if not settings.BREVO_API_KEY:
        raise EmailDeliveryError("BREVO_API_KEY is not configured")

    payload = {
        "to": [{"email": to_email}],
        "templateId": settings.BREVO_TEMPLATE_PASSWORD_RESET,
        "params": {"first_name": first_name, "reset_link": reset_link},
        "sender": {"email": settings.BREVO_SENDER_EMAIL, "name": settings.BREVO_SENDER_NAME},
    }
    try:
        response = httpx.post(
            _BREVO_SEND_URL,
            json=payload,
            headers={"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:_MAX_PROVIDER_ERROR_BODY_LENGTH]
        raise EmailDeliveryError(
            "Brevo rejected password reset email: "
            f"status={exc.response.status_code} body={body}"
        ) from exc
    except httpx.RequestError as exc:
        raise EmailDeliveryError(f"Brevo password reset email request failed: {exc}") from exc

    logger.info("Password reset email sent to %s", to_email)
