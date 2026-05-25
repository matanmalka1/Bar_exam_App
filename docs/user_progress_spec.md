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
  "question_count": 20
}
```

`mode` is one of:

- `practice`
- `exam`
- `simulation`
- `mistakes`
- `bookmarks`

Extra fields are rejected.

## DB Invariants

- `practice_sessions.mode` is constrained to `exam`, `simulation`, `practice`, `mistakes`, or `bookmarks`.
- `practice_sessions.status` is constrained to `active`, `completed`, or `abandoned`.
- `practice_sessions.part` is either `B`, `C`, or null.
- `practice_session_questions` has `unique(session_id, question_id)`.
- `practice_session_questions` has `unique(session_id, position)` and `position >= 1`.
- `user_answers` has `unique(session_id, question_id)`.
- `user_answers.selected_answer` is stored as `A`/`B`/`C`/`D`.
- `bookmarked_questions` has `unique(user_id, question_id)`.

## Mode Behavior

| Mode | Selection | Answer visibility |
| --- | --- | --- |
| `practice` | Question pool filtered by optional `exam_date`, `part`, `question_count` | Revealed after the question is answered |
| `exam` | One official exam date; all 80 questions if `part` is omitted, or one 40-question part if provided | Hidden until session completion |
| `simulation` | 40 Part B and 40 Part C questions from the full pool | Hidden until session completion |
| `mistakes` | Current user's active mistakes from completed sessions | Revealed after the question is answered |
| `bookmarks` | Current user's bookmarked questions | Revealed after the question is answered |

Session question order is created once and then stays fixed.

Answer visibility is enforced by the backend:

- `practice`, `mistakes`, and `bookmarks` expose `correct_answer`, `reference`, and `is_correct` only after the user answered that question.
- `exam` and `simulation` hide answer keys and correctness while the session is active.
- Completed `exam` and `simulation` sessions reveal answer keys and return result breakdowns.

Invalidated questions are visible in session question payloads with `status = "invalidated"` and `invalidation_note`.

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

Invalidated questions are answerable. The submitted answer is persisted like any other answer. The response/session detail uses `scoring_status = "invalidated"` when correctness is visible so clients can separate invalidated credit from genuine correct answers.

## Completion

`POST /api/v1/practice-sessions/{session_id}/complete`

Completion freezes scoring. Exam and simulation completions include `part_breakdown` and a mistake list.

Invalidated questions keep `correct_answer = null`, stay visible in the session, are included in scoring denominators, and always grant full credit. They are excluded from mistake lists even if the user selected an answer that would otherwise be wrong. `correct_count` includes invalidated credit; analytics fields distinguish that credit from genuinely correct answers.

## Scoring Model

Scores are raw points, not percentages.

| Session type | `score` | `max_score` |
| --- | --- | --- |
| Full exam / simulation (B + C) | sum of correct points across both parts | 80 |
| Single-part exam (B or C only) | correct points in that part | 40 |
| Practice / mistakes / bookmarks | correct count | total questions in session |

`PartBreakdown` fields:

- `score` — points earned in this part (each correct answer = 1 point; invalidated questions grant full credit).
- `max_score` — always 40 for both Part B and Part C.

The Israeli bar exam also includes Part A (20% of the final grade), which is not implemented in this app. The maximum score in this app is therefore 80 out of the full real-exam grade.

## Mistakes Semantics

- Mistake history is preserved; old answer rows are not deleted when a later session fixes a question.
- Active mistakes are computed from completed sessions only.
- A question is an active mistake when the latest completed-session answer for that question is wrong.
- Invalidated questions never become active or repeated mistakes.
- Latest answer ordering is `answered_at DESC, id DESC`.
- Repeated mistakes are questions with at least two wrong answers across completed sessions.
- Active sessions are ignored by mistakes queries.

## User Routes

- `GET /api/v1/users/me/sessions`
- `GET /api/v1/users/me/mistakes`
- `GET /api/v1/users/me/bookmarks`
- `POST /api/v1/users/me/bookmarks/{stable_id}`
- `DELETE /api/v1/users/me/bookmarks/{stable_id}`
- `DELETE /api/v1/users/me/data`
- `DELETE /api/v1/practice-sessions/{session_id}`

All are scoped to the authenticated user. `DELETE /users/me/data` resets all progress rows for the current user. `DELETE /practice-sessions/{session_id}` abandons an active session.

## Critical Tests Expected

- Exam and simulation sessions do not leak answer keys before completion.
- Invalidated questions are visible, answerable, included in score denominators, and always grant full credit.
- Invalidated credit is distinguishable from genuinely correct answers in session/stats payloads.
- Invalidated questions are not counted as mistakes.
- Mistakes endpoint follows latest-answer semantics.
- Session question order is preserved after creation.
- Bookmark add/remove operations are idempotent.
