import re

_PASSWORD_RE = re.compile(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*[^a-zA-Z0-9]).{8,}$")


def validate_password(v: str) -> str:
    """Raise ValueError if password fails requirements. Returns v unchanged (no strip)."""
    if not v or not v.strip():
        raise ValueError("הסיסמה לא יכולה להיות ריקה")
    if len(v) < 8:
        raise ValueError("הסיסמה חייבת להכיל לפחות 8 תווים")
    if len(v) > 128:
        raise ValueError("הסיסמה ארוכה מדי")
    if not _PASSWORD_RE.match(v):
        raise ValueError("הסיסמה חייבת להכיל לפחות אות גדולה, אות קטנה ותו מיוחד אחד")
    return v
