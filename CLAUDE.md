# CLAUDE.md

## Project

Bar Exam Study backend: FastAPI API for a Hebrew RTL bar-exam practice app.

Frontend repository: `/Users/matanmalka/Desktop/Bar_exam_frontend`.

## Stack

- Python 3.12+
- FastAPI
- SQLAlchemy 2.0
- Alembic
- PostgreSQL with `psycopg`
- Pydantic v2
- PyJWT
- pytest
- ruff, pylint, pyright, vulture

## Current Implementation

- Imports 320 questions across 8 exam parts.
- Stores 319 active questions and 1 invalidated question.
- Exposes read-only question and exam metadata endpoints.
- Supports email/password registration and login.
- Issues JWT access tokens and HttpOnly refresh-token cookies.
- Protects user progress, bookmark, mistake, and stats endpoints with bearer auth.
- Supports practice, exam, simulation, mistakes, and bookmarks sessions.
- Hides answer keys in exam/simulation sessions until completion.
- Exposes aggregate stats for the authenticated user.

Password reset is not implemented.

## Product Rules

- Preserve imported legal question text exactly.
- Do not rewrite Hebrew wording.
- Do not change answer option order.
- Do not add legal explanations.
- Do not infer missing official answers.
- Do not expose `correct_answer` or `reference` in pre-submit practice payloads.
- Do not accept `user_id` from clients for progress APIs. Use the authenticated user from the token.
- Use `/users/me/*` for user-scoped routes.

## API Surface

Health:

- `GET /health`
- `GET /ready`

Auth:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

Questions:

- `GET /api/v1/exams`
- `GET /api/v1/questions`
- `GET /api/v1/questions/review`
- `GET /api/v1/questions/{stable_id}`
- `GET /api/v1/questions/{stable_id}/review`

Progress:

- `POST /api/v1/practice-sessions`
- `GET /api/v1/practice-sessions/{session_id}`
- `POST /api/v1/practice-sessions/{session_id}/answers`
- `POST /api/v1/practice-sessions/{session_id}/complete`
- `GET /api/v1/users/me/sessions`
- `GET /api/v1/users/me/mistakes`
- `GET /api/v1/users/me/bookmarks`
- `POST /api/v1/users/me/bookmarks/{stable_id}`
- `DELETE /api/v1/users/me/bookmarks/{stable_id}`
- `GET /api/v1/users/me/stats/overview`

There is no `/api/v1/users/dev` endpoint.

## Environment

See `backend/.env.example`.

Important keys:

- `DATABASE_URL`
- `CORS_ORIGINS`
- `AUTH_SECRET_KEY`
- `AUTH_ALGORITHM`
- `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES`
- `AUTH_REFRESH_TOKEN_EXPIRE_DAYS`
- `REFRESH_COOKIE_NAME`
- `REFRESH_COOKIE_PATH`
- `REFRESH_COOKIE_SECURE`
- `REFRESH_COOKIE_SAMESITE`

## Commands

Run from `backend/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python scripts/import_questions.py --input-dir outputs
uvicorn app.main:app --reload --reload-dir app
```

Checks:

```bash
pytest
ruff check .
pylint app scripts tests alembic/env.py alembic/versions/*.py
pyright
vulture
```
