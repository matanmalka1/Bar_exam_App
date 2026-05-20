# User Progress + Practice Sessions Spec — Phase 2

> **Status: Implemented. This document reflects the actual Phase 2 behavior.**
> Do not start Phase 3 until this spec is confirmed to match the code.

---

## 1. Goal

Allow the backend to track a user's practice progress over imported questions.

A user can create a practice session over a selected set of questions, submit and update answers, complete the session, see their score, view mistakes, and bookmark questions for later review.

This phase does not implement a frontend. The API should be testable with a dev user, pytest, and a running PostgreSQL instance.

---

## 2. Non-Goals

The following are explicitly out of scope for this phase:

- JWT tokens, password hashing, login, registration, logout
- Email verification or password reset
- Role-based access control
- Multi-user isolation enforced by auth middleware
- Simulation timer (timer is a frontend concern)
- Statistics aggregation across sessions (Phase 3)
- Frontend
- Changes to the `questions` table

Do not implement any of these until this phase is complete and accepted.

### Why no real auth yet

The product needs to prove the core loop first:

```
question → answer → score → mistakes → continue
```

JWT/password/session token infrastructure adds complexity before the flow is validated. A dev user endpoint is sufficient to make all progress endpoints testable without an auth wall.

Auth can be layered on later by adding a `password_hash` column to `users`, a login endpoint, and a middleware guard — without changing the progress data model.

---

## 3. Data Model

### 3.1 users

| Column         | Type          | Notes                                              |
|----------------|---------------|----------------------------------------------------|
| `id`           | integer PK    |                                                    |
| `display_name` | varchar(128)  | non-empty                                          |
| `user_key`     | varchar(64)   | unique, nullable — used for idempotent upserts     |
| `created_at`   | timestamptz   | server default                                     |

`user_key` is a stable external identifier used to safely upsert users without relying on `display_name` uniqueness. The dev user uses `user_key = 'dev'`. Future auth users can use an email or external ID. Null is allowed for users created without a key.

No password, no email in this phase. Auth is not implemented.

---

### 3.2 practice_sessions

| Column            | Type          | Notes                                              |
|-------------------|---------------|----------------------------------------------------|
| `id`              | integer PK    |                                                    |
| `user_id`         | integer FK    | → users.id, NOT NULL                              |
| `mode`            | varchar(16)   | `exam`, `practice`, `mistakes`                    |
| `status`          | varchar(16)   | `active`, `completed`, `abandoned`                |
| `exam_date`       | date          | nullable — first day of month                     |
| `part`            | varchar(1)    | nullable — `B` or `C`                             |
| `total_questions` | integer       | count of questions in session, set at creation    |
| `answered_count`  | integer       | updated on each answer submission, default 0      |
| `correct_count`   | integer       | nullable until completed                          |
| `score_percent`   | numeric(5,2)  | nullable until completed                          |
| `started_at`      | timestamptz   | set at creation                                   |
| `completed_at`    | timestamptz   | nullable                                          |
| `created_at`      | timestamptz   | server default                                    |
| `updated_at`      | timestamptz   | updated on change                                 |

---

### 3.3 practice_session_questions

| Column       | Type        | Notes                          |
|--------------|-------------|--------------------------------|
| `id`         | integer PK  |                                |
| `session_id` | integer FK  | → practice_sessions.id NOT NULL |
| `question_id`| integer FK  | → questions.id NOT NULL        |
| `position`   | integer     | 1-based display order, NOT NULL |

Constraints:

- `unique(session_id, question_id)` — a question appears at most once per session
- `unique(session_id, position)` — positions are unique within a session

This table is the source of truth for which questions belong to a session and in what order. It is populated at session creation and never modified after that.

---

### 3.4 user_answers

| Column            | Type          | Notes                                             |
|-------------------|---------------|---------------------------------------------------|
| `id`              | integer PK    |                                                   |
| `session_id`      | integer FK    | → practice_sessions.id NOT NULL                  |
| `question_id`     | integer FK    | → questions.id NOT NULL                          |
| `selected_answer` | varchar(1)    | `A`, `B`, `C`, or `D` — DB representation       |
| `is_correct`      | boolean       | computed at submission time, NOT NULL            |
| `answered_at`     | timestamptz   | first submission time                            |
| `updated_at`      | timestamptz   | last update time                                 |

Constraints:

- `unique(session_id, question_id)` — one answer row per question per session (upsert)
- `selected_answer in ('A', 'B', 'C', 'D')`

Question text is not duplicated here. The question is referenced by FK only.

---

### 3.5 bookmarked_questions

| Column       | Type        | Notes                          |
|--------------|-------------|--------------------------------|
| `id`         | integer PK  |                                |
| `user_id`    | integer FK  | → users.id NOT NULL           |
| `question_id`| integer FK  | → questions.id NOT NULL       |
| `created_at` | timestamptz | server default                 |

Constraints:

- `unique(user_id, question_id)` — idempotent bookmark

---

## 4. DB Constraints

All constraints must be enforced at the DB level in addition to application validation.

| Table                        | Constraint                                               |
|------------------------------|----------------------------------------------------------|
| `users`                      | `length(trim(display_name)) > 0`                        |
| `users`                      | `unique(user_key)` — nullable unique                    |
| `practice_sessions`          | `mode IN ('exam', 'practice', 'mistakes')`              |
| `practice_sessions`          | `status IN ('active', 'completed', 'abandoned')`        |
| `practice_sessions`          | `part IN ('B', 'C')` or null                            |
| `practice_sessions`          | `total_questions > 0`                                   |
| `practice_sessions`          | `answered_count >= 0`                                   |
| `practice_sessions`          | `answered_count <= total_questions`                     |
| `practice_session_questions` | `unique(session_id, question_id)`                       |
| `practice_session_questions` | `unique(session_id, position)`                          |
| `practice_session_questions` | `position >= 1`                                         |
| `user_answers`               | `unique(session_id, question_id)`                       |
| `user_answers`               | `selected_answer IN ('A', 'B', 'C', 'D')`              |
| `bookmarked_questions`       | `unique(user_id, question_id)`                          |

---

## 5. API Endpoints

### POST /api/v1/users/dev

Creates or returns the fixed dev user. Idempotent.

This user exists to make all progress endpoints testable without an auth layer. The dev user is identified by `user_key = 'dev'`. The repository must upsert by `user_key` using `ON CONFLICT (user_key) DO NOTHING` (or equivalent), so concurrent calls cannot create duplicate rows.

**Request body:** none

**Response 200:**

```json
{
  "id": 1,
  "display_name": "Dev User",
  "user_key": "dev",
  "created_at": "2026-05-20T10:00:00Z"
}
```

---

### POST /api/v1/practice-sessions

Creates a new practice session for a user.

**Request body:**

```json
{
  "user_id": 1,
  "mode": "practice",
  "exam_date": "2025-04",
  "part": "B",
  "question_count": null,
  "include_invalidated": false
}
```

| Field                | Required | Notes                                                                 |
|----------------------|----------|-----------------------------------------------------------------------|
| `user_id`            | yes      |                                                                       |
| `mode`               | yes      | `exam`, `practice`, or `mistakes`                                    |
| `exam_date`          | no       | `YYYY-MM` — if omitted, questions span all exam dates for the selected part(s) |
| `part`               | no       | `B` or `C` — if omitted, both parts                                  |
| `question_count`     | no       | if set, select exactly N unique questions; if null, include all matching |
| `include_invalidated`| no       | default `false` — whether to include invalidated questions           |

### Selection algorithm

> **Important:** The final question order is always randomized. Canonical ordering applies only to the internal repository fetch — it is never the order shown to the user.

This is intentional product behavior. The backend owns all randomization. The frontend does not send seed or ordering parameters; no API field controls the shuffle.

1. Repository fetches the full candidate pool matching `part`, `exam_date`, and `include_invalidated`. The fetch uses a stable internal order (`exam_date ASC, part ASC, number ASC`) for reproducible queries, but this order is immediately discarded by the service — it is **not** the final question order.
   - If `exam_date` is provided, selection is restricted to that exam date.
   - If `exam_date` is omitted and `part` is provided, selection spans **all** imported exam dates for that part.
2. Repository returns the set of question IDs the user has already seen (any row in `practice_session_questions` joined through `practice_sessions` for this `user_id`).
3. Service splits candidates into `unseen` and `seen` groups.
4. Service shuffles each group independently using `random.Random()` (backend-owned, no seed exposed). Randomization is **not** exposed as a frontend/API parameter. Tests inject a deterministic seed by monkeypatching the module-level `_make_rng` factory. Production behavior is always random — never first-N canonical.
5. Final order = `unseen` shuffled + `seen` shuffled. Unseen questions are always preferred. Seen questions fill remaining slots only when the unseen pool is insufficient. Repeated questions are allowed only when the pool forces it.
6. If `question_count` is set, the first N from this combined list are taken. If `question_count > len(candidates)` → 422.
7. If `question_count` is null, all matching questions are included (unseen first, seen last, each group shuffled).
8. The selected order is persisted in `practice_session_questions.position` immediately at session creation. This is the source of truth from that point on. `GET /practice-sessions/{id}` returns the persisted order unchanged on every call — never reshuffles.

No DB `random()` is used. All shuffling happens in the service layer only.

If no matching questions are found → 422 with descriptive error.

**Response 201:**

```json
{
  "id": 42,
  "user_id": 1,
  "mode": "practice",
  "status": "active",
  "exam_date": "2025-04",
  "part": "B",
  "total_questions": 40,
  "answered_count": 0,
  "correct_count": null,
  "score_percent": null,
  "started_at": "2026-05-20T10:00:00Z",
  "completed_at": null,
  "created_at": "2026-05-20T10:00:00Z"
}
```

---

### GET /api/v1/practice-sessions/{session_id}

Returns session metadata, the ordered question list with answers, and current progress.

**Response 200:**

```json
{
  "id": 42,
  "user_id": 1,
  "mode": "practice",
  "status": "active",
  "exam_date": "2025-04",
  "part": "B",
  "total_questions": 40,
  "answered_count": 3,
  "correct_count": null,
  "score_percent": null,
  "started_at": "...",
  "completed_at": null,
  "questions": [
    {
      "position": 1,
      "stable_id": "2025-04_B_001",
      "number": 1,
      "body": "...",
      "options": { "א": "...", "ב": "...", "ג": "...", "ד": "..." },
      "status": "active",
      "answer": {
        "selected_answer": "א",
        "is_correct": true,
        "answered_at": "..."
      }
    },
    {
      "position": 2,
      "stable_id": "2025-04_B_002",
      "number": 2,
      "body": "...",
      "options": { ... },
      "status": "active",
      "answer": null
    }
  ]
}
```

Notes:

- `questions` are ordered by `position` ascending.
- `answer` is null if the question has not been answered yet.
- `correct_answer` and `reference` visibility follows the same rules as section 8:
  - `practice` / `mistakes` mode: always included in each question object.
  - `exam` mode, `active`: omitted.
  - `exam` mode, `completed`: included.
- 404 if session not found.

---

### POST /api/v1/practice-sessions/{session_id}/answers

Submit or update an answer for a question in this session.

**Request body:**

```json
{
  "stable_id": "2025-04_B_007",
  "selected_answer": "ב"
}
```

`stable_id` is the public domain identifier. The service resolves it to the internal `question.id`. `selected_answer` is accepted as a Hebrew letter (`א`/`ב`/`ג`/`ד`). The service maps it to `A`/`B`/`C`/`D` before storing.

Rules:

- Session must be `active` → 409 if already completed or abandoned.
- The resolved question must belong to this session → 422 if not.
- `is_correct` is computed server-side by comparing to `questions.correct_answer`.
- Invalidated questions have no correct answer → `is_correct = false` always.
- If an answer already exists for this `(session_id, question_id)`, upsert it.
- Update `practice_sessions.answered_count` atomically.

**Response 200 — `practice` or `mistakes` mode:**

```json
{
  "stable_id": "2025-04_B_007",
  "selected_answer": "ב",
  "is_correct": false,
  "correct_answer": "ג",
  "reference": "...",
  "answered_at": "..."
}
```

**Response 200 — `exam` mode (session still active):**

```json
{
  "stable_id": "2025-04_B_007",
  "selected_answer": "ב",
  "answered_at": "..."
}
```

`correct_answer` and `reference` are omitted from exam mode responses until the session is completed. This is enforced server-side (see section 8).

---

### POST /api/v1/practice-sessions/{session_id}/complete

Marks the session as completed and freezes the score.

Rules:

- Session must be `active` → 409 if already completed or abandoned.
- Service computes `correct_count` and `score_percent` from `user_answers`.
- Sets `status = 'completed'` and `completed_at = now()`.
- Score is immutable after this point.

**Response 200:**

```json
{
  "id": 42,
  "status": "completed",
  "total_questions": 40,
  "answered_count": 38,
  "correct_count": 30,
  "score_percent": 75.00,
  "completed_at": "..."
}
```

---

### GET /api/v1/users/{user_id}/sessions

Returns a list of sessions for the user, most recent first.

**Query parameters:**

| Parameter | Optional | Values                              |
|-----------|----------|-------------------------------------|
| `status`  | yes      | `active`, `completed`, `abandoned`  |

**Response 200:** array of session objects (same shape as POST response, without `questions`).

---

### GET /api/v1/users/{user_id}/mistakes

Returns questions the user answered incorrectly, across all completed sessions.

A question is a current mistake if the **most recent answer** (by `updated_at`) across all sessions is `is_correct = false`.

**Response 200:**

```json
[
  {
    "stable_id": "2025-04_B_007",
    "number": 7,
    "exam_date": "2025-04",
    "part": "B",
    "body": "...",
    "options": { "א": "...", ... },
    "correct_answer": "ג",
    "reference": "...",
    "times_answered": 3,
    "times_wrong": 2
  }
]
```

`correct_answer` and `reference` are included here because mistakes review is post-session.

---

### POST /api/v1/users/{user_id}/bookmarks/{stable_id}

Adds a bookmark. No request body.

Idempotent — if bookmark already exists, return 200 without error.

**Response 200:**

```json
{
  "user_id": 1,
  "stable_id": "2025-04_B_007",
  "created_at": "..."
}
```

---

### DELETE /api/v1/users/{user_id}/bookmarks/{stable_id}

Removes a bookmark. No request body.

Idempotent — if bookmark does not exist, return 200 without error.

**Response 200:**

```json
{ "removed": true }
```

---

### GET /api/v1/users/{user_id}/bookmarks

Returns bookmarked questions for the user.

**Response 200:** array of question objects (same shape as the review schema), with `correct_answer` and `reference` included.

---

## 6. Layering Rules

```
Router → Service → Repository → ORM
```

- **Router:** HTTP, path/query/body parsing, Depends injection. No DB. No business logic.
- **Service:** session creation logic, question selection, answer scoring, mistake derivation, score calculation, Hebrew ↔ DB answer mapping. No direct DB access.
- **Repository:** all `select()`, `insert`, `update`, `delete` operations. No business logic.
- **ORM models:** column definitions and constraints only. No methods.
- **Schemas:** Pydantic DTOs for all request and response bodies.
- No `db.query()`. Use `select(...)` with `session.scalars()` or `session.execute()`.
- No raw SQL unless justified and commented.
- No cross-domain repository calls (e.g. session repo must not call question repo directly).

---

## 7. Session Lifecycle

```
POST /practice-sessions          → status: active
POST /{id}/answers               → status: active (answers accumulate)
POST /{id}/complete              → status: completed (score frozen)
```

- A session is created with all its questions pre-selected and ordered.
- The question list does not change after creation.
- `answered_count` is updated atomically on each answer upsert.
- A completed session's `correct_count` and `score_percent` are immutable.
- `abandoned` status is reserved for future use (e.g. timeout, explicit abandon). Not required in this phase.

---

## 8. Answer Submission Behavior by Mode

The `correct_answer` and `reference` visibility rules are enforced at the API response level, not by UI hiding.

### On answer submit (`POST /answers`)

| Mode       | `correct_answer` / `reference` in response? |
|------------|---------------------------------------------|
| `practice` | Yes — always                                |
| `mistakes` | Yes — always                                |
| `exam`     | No — omitted while session is active        |

### On session fetch (`GET /sessions/{id}`)

| Mode + status        | `correct_answer` / `reference` per question? |
|----------------------|----------------------------------------------|
| `practice` — any     | Yes — always                                 |
| `mistakes` — any     | Yes — always                                 |
| `exam` — `active`    | No — omitted                                 |
| `exam` — `completed` | Yes — included                               |

The service layer is responsible for selecting the correct response schema based on `mode` and `status`. The router must not apply conditional field hiding.

---

## 9. Score Calculation

Score is calculated at `complete` time only.

```
correct_count = count of user_answers where is_correct = true, for this session
score_percent = (correct_count / total_questions) * 100, rounded to 2 decimal places
```

`is_correct` is set at answer submission time and does not change. Score is derived from the stored values — no re-evaluation at complete time.

Unanswered questions count as incorrect toward the score (they simply have no `user_answer` row, so they do not contribute to `correct_count`).

---

## 10. Bookmarks

- A bookmark is a (`user_id`, `question_id`) pair.
- Bookmarks are independent of sessions and mistakes.
- Adding a bookmark that already exists must not raise an error.
- Removing a bookmark that does not exist must not raise an error.
- Bookmarked questions include `correct_answer` and `reference` in the response.

---

## 11. Mistakes Tracking

- Mistakes are derived from `user_answers` across all sessions.
- A question is a **current mistake** if the most recent `user_answer` for that (`user_id`, `question_id`) pair across all sessions has `is_correct = false`.
- A question is resolved when a later answer for the same question, in a different or later session, has `is_correct = true`.
- The mistakes endpoint must query across sessions, not within a single session.

### user_answers mutability model

Within a single active session, `user_answers` has `unique(session_id, question_id)`. This means a user has one answer slot per question per session, and it can be updated (upserted) while the session is active. This is intentional — it lets users change their mind before completing.

Once the session is completed, the answer row for that session is frozen. Cross-session history is preserved because each session has its own `user_answer` rows. Mistakes are derived from the most recent `updated_at` across all sessions for a given `(user, question)` pair.

**There is no single "immutable history" row per answer.** The history is the set of rows across multiple sessions. Within one session, the answer can change.

---

## 12. Alembic Migration

Phase 2 migration is:

```
alembic/versions/20260520_0002_create_user_progress.py
```

The migration creates:

- `users`, `practice_sessions`, `practice_session_questions`, `user_answers`, `bookmarked_questions` in one migration.
- It does not modify the `questions` table.
- It is reversible via `downgrade()`.

---

## 13. Folder Structure Changes

Phase 2 added to `backend/app/`:

```
app/
├── models/
│   ├── question.py
│   ├── user.py
│   ├── practice_session.py
│   ├── practice_session_question.py
│   ├── bookmarked_question.py
│   └── user_answer.py
├── repositories/
│   ├── question_repository.py
│   ├── user_repository.py
│   ├── practice_session_repository.py
│   └── answer_repository.py
├── services/
│   ├── question_service.py
│   ├── user_service.py
│   ├── practice_session_service.py
│   └── answer_service.py
├── routers/
│   ├── questions.py
│   ├── users.py
│   ├── practice_sessions.py
│   └── answers.py
└── schemas/
    ├── question.py
    ├── user.py
    ├── session.py
    └── answer.py
```

---

## 14. Tests

Implemented tests in `tests/test_user_progress.py` cover:

- `POST /api/v1/users/dev` creates dev user on first call, returns same user on second call (idempotent)
- `POST /api/v1/practice-sessions` creates session with correct `total_questions` and `status=active`
- Session excludes invalidated questions by default
- Session includes invalidated questions when `include_invalidated=true`
- Session question order is stable across calls (consistent `position` values)
- `POST /answers` accepts `stable_id` and stores `selected_answer` as DB letter (`A`/`B`/`C`/`D`) with correct `is_correct`
- `POST /answers` on same question before completion updates the existing answer (upsert)
- `POST /answers` after session completion returns 409
- `POST /answers` with a `stable_id` not in session returns 422
- `POST /complete` calculates correct `correct_count` and `score_percent`
- `POST /complete` on already-completed session returns 409
- `GET /sessions/{id}` returns questions with `answer: null` for unanswered questions
- `GET /users/{id}/mistakes` returns questions where latest answer is incorrect
- `GET /users/{id}/mistakes` does not return questions resolved by a later correct answer
- `POST /users/{user_id}/bookmarks/{stable_id}` is idempotent
- `DELETE /users/{user_id}/bookmarks/{stable_id}` is idempotent
- `GET /users/{user_id}/bookmarks` returns bookmarked questions with `correct_answer` included
- Exam mode answer response does not include `correct_answer` or `reference`
- Practice mode answer response includes `correct_answer` and `reference`
- No `db.query()` used anywhere in new code

---

## 15. Risky Decisions to Review Before Coding

**1. `user_id` in request body and path instead of auth header**
Since there is no auth, `user_id` is passed as a plain path/query/body field. This is intentional for this phase, but must be replaced before any real user-facing deployment. Flag every location in code with a `# TODO(auth)` comment wherever user identity comes from the request rather than a verified token.

**2. Dev user idempotency is enforced by `users.user_key`**
`POST /users/dev` upserts by `user_key = 'dev'` using `ON CONFLICT (user_key) DO NOTHING`. The `users.user_key` column has a unique constraint. This prevents duplicate dev users under concurrent calls. `display_name` is not used as the uniqueness key.

**3. `answered_count` is a denormalized counter**
It is updated on each answer upsert. The update must be in the same transaction as the answer upsert. For MVP single-user flow, drift from concurrent writes is not a concern. If concurrency is added later, replace this with a derived count query.

**4. `score_percent` uses `total_questions` as denominator, not `answered_count`**
Unanswered questions count against the user. This is intentional (matches real exam behavior). The API response must include both `total_questions` and `answered_count` so the frontend can communicate this clearly.

**5. Mistakes query joins through `practice_sessions`, not through `user_answers.user_id`**
`user_answers` has no `user_id` column. The mistakes query must join `user_answers → practice_sessions → users`. Useful indexes for this query:

- `practice_sessions(user_id, status)`
- `user_answers(session_id, question_id)`
- `user_answers(question_id, updated_at)`
- `practice_session_questions(session_id, question_id)`

Do not add `user_id` to `user_answers` in this phase.

**6. `practice_session_questions` order is the persisted source of truth**
Positions are assigned at session creation by the selection algorithm (see section 5). After creation, the row order is frozen — `GET /sessions/{id}` returns it as-is and never reshuffles. The selection itself uses a backend-owned `random.Random()` instance; no seed is exposed via the API and the frontend sends no ordering parameters. Tests control randomness by monkeypatching `practice_session_service._make_rng`. Production behavior is always a fresh unseeded shuffle — never first-N canonical order.

**7. Anti-repeat is best-effort, not a guarantee**
A new session prefers questions the user has not seen before (any row in `practice_session_questions` for any of the user's sessions counts as "seen"). When the unseen pool is too small to fill `question_count`, the remaining slots are filled from previously seen questions. Repeats are only allowed when the pool forces it.

---

## 16. Acceptance Criteria

The phase is complete when:

- All tests in `test_user_progress.py` pass.
- New migrations apply cleanly on PostgreSQL without modifying the `questions` table.
- Existing Phase 1 API (`/health`, `/ready`, `/api/v1/exams`, `/api/v1/questions`) still passes all Phase 1 tests.
- A dev user can be created, start a session, answer questions, complete it, see the score, see mistakes, and bookmark questions — all through the API with no frontend.
- Exam mode does not expose `correct_answer` or `reference` in answer submission responses.
- No `db.query()` anywhere in the new code.
- No ORM objects returned from routers.
