import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


def send_password_reset_email(to_email: str, first_name: str, reset_link: str) -> None:
    payload = {
        "to": [{"email": to_email}],
        "templateId": settings.BREVO_TEMPLATE_PASSWORD_RESET,
        "params": {"first_name": first_name, "reset_link": reset_link},
        "sender": {"email": settings.BREVO_SENDER_EMAIL, "name": settings.BREVO_SENDER_NAME},
    }
    response = httpx.post(
        _BREVO_SEND_URL,
        json=payload,
        headers={"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json"},
        timeout=10,
    )
    response.raise_for_status()
    logger.info("Password reset email sent to %s", to_email)
