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
- `GET /api/v1/users/me/sessions`
- `GET /api/v1/users/me/mistakes`
- `GET /api/v1/users/me/bookmarks`
- `POST /api/v1/users/me/bookmarks/{stable_id}`
- `DELETE /api/v1/users/me/bookmarks/{stable_id}`
- `GET /api/v1/users/me/stats/overview`

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

## User Scoping

Progress APIs use the authenticated user from the access token. The request body does not accept `user_id`, and legacy `/users/{user_id}/...` routes are not present.
