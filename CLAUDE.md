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
- Shows invalidated questions in sessions, allows answers, grants full credit after answer submission, and tracks that credit separately from genuinely correct answers.
- Exposes aggregate stats for the authenticated user.
- Supports backend forgot-password and reset-password endpoints.
- Uses global exception handlers to return one frontend-safe error envelope.

## Source Data Rules

- Preserve imported legal question text exactly.
- Do not rewrite Hebrew wording.
- Do not change answer option order.
- Do not add legal explanations.
- Do not infer missing official answers.
- Do not override official answer keys.
- Do not use internal database IDs as business identifiers; use `stable_id` for questions.
- Invalid source data must fail validation or be marked for manual review.

## Product Rules

- Do not expose `correct_answer` or `reference` in pre-submit practice payloads.
- Invalidated questions are visible and answerable in all session contexts where they are selected.
- Invalidated questions are included in score denominators. Once answered, they grant full credit regardless of the selected answer.
- Persist selected answers for invalidated questions.
- Use `scoring_status = "invalidated"` and `is_correct = null` in exposed answer payloads to distinguish invalidated-question credit from genuine correctness.
- Invalidated questions must not be counted as active mistakes or repeated mistakes.
- Do not accept `user_id` from clients for progress APIs. Use the authenticated user from the token.
- Use `/users/me/*` for user-scoped routes.

## Scoring Model

Scores are raw points, not percentages. Never use `score_percent`; the API fields are `score` and `max_score`.

| Session type | `score` | `max_score` |
| --- | --- | --- |
| Full exam / simulation (B + C) | sum of points across both parts | 80 |
| Single-part exam | correct points in that part | 40 |
| Practice / mistakes / bookmarks | correct count | question count in session |

`PartBreakdown.score` = points earned (1 per correct/invalidated answer). `PartBreakdown.max_score` = 40.

Part A of the real Israeli bar exam is not in this app. Maximum achievable score is 80.

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
- `POST /api/v1/auth/forgot-password`
- `POST /api/v1/auth/reset-password`

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
- `DELETE /api/v1/practice-sessions/{session_id}`
- `GET /api/v1/users/me/sessions`
- `GET /api/v1/users/me/mistakes`
- `GET /api/v1/users/me/bookmarks`
- `POST /api/v1/users/me/bookmarks/{stable_id}`
- `DELETE /api/v1/users/me/bookmarks/{stable_id}`
- `GET /api/v1/users/me/stats/overview`
- `DELETE /api/v1/users/me/data`

There is no `/api/v1/users/dev` endpoint.

## Error Contract

Successful responses keep their endpoint-specific schema. Error responses always use:

```json
{
  "error": {
    "code": "string_machine_readable_code",
    "message": "הודעת שגיאה בעברית",
    "details": null
  }
}
```

- Pydantic/FastAPI validation errors use `validation_error`.
- Domain `422` errors use `unprocessable_entity`, not `validation_error`.
- Domain errors may include frontend-friendly business context in `error.details`.
- SQLAlchemy and generic 500 handlers log stack traces but do not expose internals to clients.

## Environment

Copy `backend/.env.example` to `backend/.env`. `pydantic-settings` auto-loads `.env` on startup.

Important keys:

- `ENV` — `development` / `production` / `test`
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
- `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`
- `FRONTEND_PASSWORD_RESET_URL`
- `PASSWORD_RESET_DEV_LOG`
- `LOG_LEVEL`
- `OBSERVABILITY_JSON_LOGS`
- `SENTRY_ENABLED`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`
- `RATE_LIMIT_ENABLED`, `RATE_LIMIT_STORAGE_URI`
- `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME`, `BREVO_TEMPLATE_PASSWORD_RESET`

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
