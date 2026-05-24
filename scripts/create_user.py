"""Seed a user with email + password.

Usage:
    python -m scripts.create_user <full_name> <email> <password>
"""

import sys

from app.auth.security import hash_password
from app.db.session import SessionLocal
from app.repositories import user_repository


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    _, full_name, email, password = sys.argv
    email = email.lower()

    with SessionLocal() as session:
        existing = user_repository.get_by_email(session, email)
        if existing is not None:
            print(f"User already exists: id={existing.id}")
            return 1
        user = user_repository.create(
            session,
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
        )
        session.commit()
        print(f"Created user id={user.id} email={user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
