# User Progress Notes

This document reflects the current user progress implementation.

## Tables

- `users`
- `practice_sessions`
- `practice_session_questions`
- `user_answers`
- `bookmarked_questions`

Users have `full_name`, `email`, `password_hash`, `is_active`, `token_version`, `created_at`, and `last_login_at`.

## Identity

Progress routes are authenticated. The backend reads the current user from the bearer access token and rejects unauthenticated requests with 401.

There is no dev-user route. Clients must not send `user_id` in progress requests.

## Session Creation

`POST /api/v1/practice-sessions`

Request body:

```json
{
  "mode": "practice",
  "exam_date": "2025-04",
  "part": "B",
  "question_count": 20,
  "include_invalidated": false
}
```

`mode` is one of:

- `practice`
- `exam`
- `simulation`
- `mistakes`
- `bookmarks`

Extra fields are rejected.

## Mode Behavior

| Mode | Selection | Answer visibility |
| --- | --- | --- |
| `practice` | Active pool filtered by optional `exam_date`, `part`, `question_count`; `include_invalidated` is supported for QA-style practice | Revealed after the question is answered |
| `exam` | One official exam date; all 80 questions if `part` is omitted, or one 40-question part if provided | Hidden until session completion |
| `simulation` | 40 Part B and 40 Part C active questions from the full pool | Hidden until session completion |
| `mistakes` | Current user's active mistakes from completed sessions | Revealed after the question is answered |
| `bookmarks` | Current user's bookmarked questions | Revealed after the question is answered |

Session question order is created once and then stays fixed.

## Answers

`POST /api/v1/practice-sessions/{session_id}/answers`

Request body:

```json
{
  "stable_id": "2025-04_B_001",
  "selected_answer": "א"
}
```

Within an active session, submitting the same question again updates the existing answer row. Completed sessions reject further answer changes.

## Completion

`POST /api/v1/practice-sessions/{session_id}/complete`

Completion freezes scoring. Exam and simulation completions include `part_breakdown` and a mistake list. Invalidated official questions are excluded from scoring denominators.

## User Routes

- `GET /api/v1/users/me/sessions`
- `GET /api/v1/users/me/mistakes`
- `GET /api/v1/users/me/bookmarks`
- `POST /api/v1/users/me/bookmarks/{stable_id}`
- `DELETE /api/v1/users/me/bookmarks/{stable_id}`

All are scoped to the authenticated user.
