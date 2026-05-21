# AGENTS.md

## Project

FastAPI backend for the Bar Exam Study app. The app serves original Israeli Bar Association exam questions to a Hebrew RTL frontend.

## Current State

- Question ingestion and validation are implemented.
- The database contains imported questions, users, sessions, answers, bookmarks, and auth columns.
- Email/password auth with JWT access tokens and HttpOnly refresh cookies is implemented.
- User progress endpoints are scoped to the authenticated user.
- Stats overview is implemented.
- Backend password reset endpoints are implemented.
- Global exception handling returns a consistent frontend-safe error envelope.

## Source Data Rules

- Preserve official question text and answer order exactly.
- Do not rewrite Hebrew wording.
- Do not add legal explanations.
- Do not infer missing answers.
- Do not override official answer keys.
- Do not repair official data silently.
- Use `stable_id` as the question business identifier.
- Invalid source data must fail validation or be marked for manual review.

## Non-Negotiable Product Rules

- Do not expose answer keys before a user is allowed to see them.
- Do not accept client-provided `user_id` for user progress.
- Use `/users/me/*` for authenticated user data.

## Development Rules

- Router handles HTTP only.
- Service owns business rules.
- Repository owns database access.
- ORM models stay free of business logic.
- Pydantic schemas define API contracts.
- Error responses must use `{ "error": { "code", "message", "details" } }`.
- Reserve `validation_error` for FastAPI/Pydantic request validation; domain-level 422 errors use `unprocessable_entity`.
- Do not leak SQL, connection strings, tracebacks, or internal exception messages to clients.
- Use SQLAlchemy 2.0 `select()` patterns.
- Keep comments short and only for non-obvious behavior.

## Checks

Run from `backend/`:

```bash
pytest
ruff check .
pylint app scripts tests alembic/env.py alembic/versions/*.py
pyright
vulture
```
