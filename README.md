# Bar Exam Study Backend

FastAPI backend for a Hebrew RTL Israeli bar-exam practice app.

## What Exists

- Question import pipeline output for 8 exam parts.
- Alembic migrations for questions, user progress, bookmarks, simulation mode, and auth.
- Email/password auth with JWT access tokens and HttpOnly refresh-token cookies.
- Authenticated practice sessions for `practice`, `exam`, `simulation`, `mistakes`, and `bookmarks`.
- User-scoped sessions, mistakes, bookmarks, and stats via `/users/me/*`.
- Read-only question endpoints and answer-review endpoints.
- Backend forgot-password and reset-password endpoints.
- Invalidated questions remain visible and answerable in sessions, grant full credit, and are tracked separately from genuinely correct answers.

## Requirements

- Python 3.12+
- PostgreSQL

## Setup From Clean Clone

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and edit as needed. `pydantic-settings` auto-loads `.env` when the app starts.

Default local database URL:

```text
postgresql+psycopg://postgres:postgres@localhost:5432/bar_exam_study
```

## Database

```bash
alembic upgrade head
python scripts/import_questions.py --input-dir outputs
```

Expected import summary:

```json
{
  "total_questions": 320,
  "active_questions": 319,
  "invalidated_questions": 1,
  "exam_parts": 8,
  "each_part_count": 40
}
```

## Run API

```bash
uvicorn app.main:app --reload --reload-dir app
```

Health endpoints:

- `GET /health`
- `GET /ready`

Interactive docs are available at `/docs` when the API is running.

## Environment Variables

| Key | Default |
| --- | --- |
| `ENV` | `development` |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/bar_exam_study` |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |
| `AUTH_SECRET_KEY` | `dev-secret-change-me` |
| `AUTH_ALGORITHM` | `HS256` |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` |
| `AUTH_REFRESH_TOKEN_EXPIRE_DAYS` | `7` |
| `REFRESH_COOKIE_NAME` | `refresh_token` |
| `REFRESH_COOKIE_PATH` | `/api/v1/auth` |
| `REFRESH_COOKIE_SECURE` | `false` |
| `REFRESH_COOKIE_SAMESITE` | `lax` |
| `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | `30` |
| `FRONTEND_PASSWORD_RESET_URL` | `http://localhost:5173/reset-password` |
| `PASSWORD_RESET_DEV_LOG` | `false` |
| `LOG_LEVEL` | `INFO` |
| `OBSERVABILITY_JSON_LOGS` | `true` |
| `SENTRY_ENABLED` | `false` |
| `SENTRY_DSN` | `` |
| `SENTRY_ENVIRONMENT` | `development` |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` |
| `RATE_LIMIT_ENABLED` | `true` |
| `RATE_LIMIT_STORAGE_URI` | `memory://` |
| `BREVO_API_KEY` | `` |
| `BREVO_SENDER_EMAIL` | `matan1391@gmail.com` |
| `BREVO_SENDER_NAME` | `איפוס סיסמה - בר עורכי דין` |
| `BREVO_TEMPLATE_PASSWORD_RESET` | `4` |

Use a strong `AUTH_SECRET_KEY` outside local development. In production, `ENV=production` enforces additional guards (see `app/core/config.py`).

## API Summary

Auth:

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Creates user, returns access token, sets refresh cookie |
| `POST` | `/api/v1/auth/login` | Returns access token, sets refresh cookie |
| `POST` | `/api/v1/auth/refresh` | Reads refresh cookie, returns new access token |
| `POST` | `/api/v1/auth/logout` | Revokes current token version and clears refresh cookie |
| `GET` | `/api/v1/auth/me` | Bearer token required |
| `POST` | `/api/v1/auth/forgot-password` | Creates reset token for active users and returns a generic message |
| `POST` | `/api/v1/auth/reset-password` | Uses a valid reset token to update password and invalidate existing tokens |

Questions:

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/v1/exams` | Distinct imported exam parts |
| `GET` | `/api/v1/questions` | Practice payload without answer key |
| `GET` | `/api/v1/questions/review` | Includes `correct_answer` and `reference` |
| `GET` | `/api/v1/questions/{stable_id}` | Single practice question |
| `GET` | `/api/v1/questions/{stable_id}/review` | Single review question |

Authenticated progress:

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/api/v1/practice-sessions` | Creates practice/exam/simulation/mistakes/bookmarks session |
| `GET` | `/api/v1/practice-sessions/{session_id}` | Returns session detail for current user |
| `POST` | `/api/v1/practice-sessions/{session_id}/answers` | Submits or updates an answer while active |
| `POST` | `/api/v1/practice-sessions/{session_id}/complete` | Completes session and freezes score |
| `DELETE` | `/api/v1/practice-sessions/{session_id}` | Abandons an active session |
| `GET` | `/api/v1/users/me/sessions` | Current user's sessions |
| `GET` | `/api/v1/users/me/mistakes` | Current active mistakes |
| `GET` | `/api/v1/users/me/bookmarks` | Current bookmarks |
| `POST` | `/api/v1/users/me/bookmarks/{stable_id}` | Adds bookmark |
| `DELETE` | `/api/v1/users/me/bookmarks/{stable_id}` | Removes bookmark |
| `GET` | `/api/v1/users/me/stats/overview` | Aggregate stats |
| `DELETE` | `/api/v1/users/me/data` | Resets all progress data for current user |

There is no `/api/v1/users/dev` endpoint and progress endpoints do not accept client-provided `user_id`.

## Error Responses

All API errors use one JSON envelope so the Hebrew frontend can render errors consistently:

```json
{
  "error": {
    "code": "string_machine_readable_code",
    "message": "הודעת שגיאה בעברית",
    "details": null
  }
}
```

- `error.code` is stable enough for frontend branching.
- `error.message` is safe for user display.
- `error.details` is `null` unless the handler has frontend-friendly structured details.
- Legacy top-level `detail` responses are not part of the current API contract.
- Pydantic/FastAPI request validation uses `validation_error`; domain-level `422` errors use `unprocessable_entity`.

Validation errors return `422` with:

```json
{
  "error": {
    "code": "validation_error",
    "message": "חלק מהשדות אינם תקינים",
    "details": [
      {
        "field": "items.0.name",
        "message": "Field required",
        "type": "missing"
      }
    ]
  }
}
```

Database and unhandled server errors are logged with stack traces, but client responses do not expose SQL, connection strings, tracebacks, or internal exception messages.

## Source Data Rules

- Preserve original question text exactly.
- Do not rewrite Hebrew wording.
- Do not change answer order.
- Do not infer missing answers.
- Do not override official answer keys.
- Use `stable_id` as the question business identifier.
- Invalid source data must fail validation or be marked for manual review.

## Session Modes

| Mode | Behavior |
| --- | --- |
| `practice` | Questions filtered by optional `exam_date`, `part`, and `question_count` |
| `exam` | Official exam replay for one `exam_date`; full 80-question exam or a single 40-question part |
| `simulation` | Mixed 80-question session: 40 Part B and 40 Part C from the full question pool |
| `mistakes` | Current user's active mistakes |
| `bookmarks` | Current user's bookmarked questions |

Exam and simulation answer keys are hidden until completion. Practice, mistakes, and bookmarks reveal feedback after the question is answered.

Invalidated questions are included wherever they are selected. They are visually/semantically marked as invalidated, the user's selected answer is persisted, they are included in score denominators, and they always grant full credit with `scoring_status = "invalidated"`. They do not count as mistakes. Stats expose invalidated credit separately from genuine correct answers.

## Observability

- Structured JSON logs via `LOG_LEVEL` and `OBSERVABILITY_JSON_LOGS`. Set `OBSERVABILITY_JSON_LOGS=false` for human-readable dev output.
- Each request gets a `X-Request-Id` header (middleware: `app/middleware/request_id.py`). Request/response pairs are logged by `app/middleware/request_logging.py`.
- Sentry integration is off by default (`SENTRY_ENABLED=false`). Set `SENTRY_DSN` and `SENTRY_ENABLED=true` to enable.
- Rate limiting uses `slowapi` with in-memory storage by default. Use `RATE_LIMIT_STORAGE_URI=redis://...` for multi-process deployments.

## Checks

Run all checks from `backend/`:

```bash
pytest
ruff check .
pylint app scripts tests alembic/env.py alembic/versions/*.py
pyright
vulture
```

## Data Notes

- `questions.correct_answer` is stored as `A`/`B`/`C`/`D`.
- API responses use Hebrew answer labels `א`/`ב`/`ג`/`ד`.
- Exam metadata is derived from `questions.exam_date` and `questions.part`; there is no `exams` table.
- There is no separate answer-key table.
- Invalidated questions remain in the database with `correct_answer = null` and non-empty `invalidation_note`.
- Invalidated questions are included in session scoring denominators and grant full credit without being counted as mistakes.
