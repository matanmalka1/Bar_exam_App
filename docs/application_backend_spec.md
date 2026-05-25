# Application Backend Notes

This document reflects the current backend implementation.

## Layering

```text
Router -> Service -> Repository -> ORM model
```

- Routers handle HTTP, dependencies, and response models.
- Services own business rules and convert ORM rows to API schemas.
- Repositories own SQLAlchemy queries.
- ORM models contain schema definitions and constraints only.
- API contracts live in Pydantic schemas.
- Global exception formatting lives in `app/core/exception_handlers.py`.

## Middleware

Middleware stack (outermost to innermost on request path):

1. `RequestIDMiddleware` — attaches `X-Request-Id` to every request and response.
2. `RequestLoggingMiddleware` — logs method, path, status, and duration per request.
3. `CORSMiddleware` — standard FastAPI CORS, origins from `CORS_ORIGINS`.

Rate limiting uses `slowapi` (key: remote address). The `RateLimitExceeded` handler returns the standard error envelope with code `rate_limit_exceeded`.

## Public Endpoints

- `GET /health`
- `GET /ready`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/forgot-password`
- `POST /api/v1/auth/reset-password`
- `GET /api/v1/exams`
- `GET /api/v1/questions`
- `GET /api/v1/questions/review`
- `GET /api/v1/questions/{stable_id}`
- `GET /api/v1/questions/{stable_id}/review`

`/auth/me` and all progress, bookmark, mistake, and stats endpoints require a bearer access token.

## Authenticated Endpoints

- `GET /api/v1/auth/me`
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

## Answer Visibility

Answer visibility is enforced by backend services, not only by the UI.

Practice question endpoints do not expose official answer data:

- `GET /api/v1/questions`
- `GET /api/v1/questions/{stable_id}`

Review endpoints expose `correct_answer` and `reference`:

- `GET /api/v1/questions/review`
- `GET /api/v1/questions/{stable_id}/review`

Session payloads follow mode-specific visibility:

| Context | `correct_answer` / `reference` behavior |
| --- | --- |
| `GET /api/v1/questions` | Never returned |
| `GET /api/v1/questions/{stable_id}` | Never returned |
| Review endpoints | Returned for QA/review use |
| Active `practice`, `mistakes`, `bookmarks` session | Returned only for questions the user already answered |
| Active `exam` or `simulation` session | Hidden for every question |
| Completed `exam` or `simulation` session | Revealed for all questions |

Invalidated questions are still visible and answerable in sessions. They have `status = "invalidated"` and `invalidation_note`, keep `correct_answer = null`, and are marked with `scoring_status = "invalidated"` whenever scoring details are visible.

Invalidated questions are included in score denominators and always grant full credit. The selected answer is persisted. They are excluded from mistake lists and must remain distinguishable from genuinely correct answers in stats and UI analytics.

## User Scoping

Progress APIs use the authenticated user from the access token. The request body does not accept `user_id`, and legacy `/users/{user_id}/...` routes are not present.

## Error Contract

Successful responses keep their endpoint-specific Pydantic shape. Error responses are normalized globally and always use this envelope:

```json
{
  "error": {
    "code": "string_machine_readable_code",
    "message": "Hebrew user-facing message",
    "details": null
  }
}
```

Handlers are registered once in `app/main.py` via `register_exception_handlers(app)`.

| Error source | Status | Code | Message |
| --- | --- | --- | --- |
| `AppError` domain/application errors | exception-defined | exception-defined | exception-defined Hebrew message |
| FastAPI/Pydantic request validation | `422` | `validation_error` | `חלק מהשדות אינם תקינים` |
| Domain/application unprocessable input | `422` | `unprocessable_entity` | `חלק מהנתונים אינם תקינים` or an explicit Hebrew domain message |
| SQLAlchemy errors | `500` | `database_error` | `אירעה שגיאת מסד נתונים` |
| Unhandled exceptions | `500` | `internal_server_error` | `אירעה שגיאה לא צפויה` |
| HTTP `401` | `401` | `unauthorized` | `יש להתחבר כדי להמשיך` |
| HTTP `403` | `403` | `forbidden` | `אין לך הרשאה לבצע פעולה זו` |
| HTTP `404` | `404` | `not_found` | `המשאב המבוקש לא נמצא` |
| HTTP `409` | `409` | `conflict` | `הפעולה מתנגשת עם מצב קיים` |
| HTTP `429` | `429` | `rate_limit_exceeded` | `יותר מדי ניסיונות. נסה שוב מאוחר יותר` |

Validation `details` are normalized for UI rendering:

```json
[
  {
    "field": "items.0.name",
    "message": "Field required",
    "type": "missing"
  }
]
```

The field path strips transport prefixes such as `body`, `query`, and `path`, so `["body", "items", 0, "name"]` becomes `items.0.name`.

SQLAlchemy and generic exception handlers must log the original exception with a stack trace and must not leak SQL, connection strings, tracebacks, table names, or internal exception messages to clients.
