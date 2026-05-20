# Stats Overview Spec — Phase 3

> **Status: Spec only. Do not implement code yet.**
> Point out any risky product or backend decisions before coding begins.

---

## 1. Goal

Expose a single summary endpoint that returns a user's practice statistics.

No new tables. No schema changes. All stats are derived from existing Phase 2 data: `practice_sessions`, `user_answers`, and `questions`.

This phase does not implement auth, frontend, or time-series breakdowns.

---

## 2. Non-Goals

The following are explicitly out of scope for this phase:

- Auth or user identity enforcement
- Per-session or per-exam breakdown
- Streak tracking or daily activity
- Charts or time-series data
- Admin statistics across users
- Any schema migration
- Per-question timing (requires schema change — see section 9)

---

## 3. No Migration Needed

Phase 3 adds no new tables and modifies no existing tables.

All stats are computed over `practice_sessions`, `user_answers`, and `questions`. The migration file created in Phase 2 (`20260520_0002_create_user_progress.py`) is sufficient.

---

## 4. Endpoint

### GET /api/v1/users/{user_id}/stats/overview

Returns a summary of the user's practice activity.

**Path parameter:** `user_id` — integer, required

**Response 200:**

```json
{
  "total_answered": 120,
  "overall_success_rate": 62.50,
  "part_b": {
    "total_answered": 60,
    "success_rate": 70.00
  },
  "part_c": {
    "total_answered": 60,
    "success_rate": 55.00
  },
  "simulations_completed": 3,
  "active_mistakes_count": 15,
  "repeated_mistakes_count": 7,
  "avg_session_duration_seconds": 1840
}
```

**Response 404:** user not found

---

## 5. Field Definitions

### `total_answered`

Count of `user_answers` rows where the session is completed and the underlying question is active (`questions.status = 'active'`).

Counts answer events, not unique questions. If the user answered the same question in three different sessions, it counts as 3.

Invalidated questions are excluded. Their answers are always `is_correct = false` (per Phase 2 rules) and would distort the success rate and answered count.

---

### `overall_success_rate`

```
correct_active_answers / total_active_answered * 100
```

Computed over all completed sessions, all modes (`practice`, `exam`, `mistakes`). Rounded to 2 decimal places.

Excludes answers to invalidated questions.

Returns `null` if `total_answered = 0`.

---

### `part_b` and `part_c`

Per-part breakdown: `total_answered` and `success_rate`, using the same rules as above.

Part is determined by `questions.part`, not `practice_sessions.part`. A session with `part = null` (both parts) will still contribute correctly to the per-part breakdown because we join through to the actual question.

`success_rate` returns `null` if `total_answered = 0` for that part.

---

### `simulations_completed`

Count of `practice_sessions` where `mode = 'exam'` and `status = 'completed'` for this user.

---

### `active_mistakes_count`

Count of questions where the user's most recent answer (by `updated_at` across all completed sessions) is `is_correct = false`.

This is the same definition as the mistakes endpoint in Phase 2. Reuse the existing query logic.

---

### `repeated_mistakes_count`

Count of distinct questions where the user has at least 2 answers with `is_correct = false` across all completed sessions.

This measures persistent difficulty — questions the user has gotten wrong more than once. Note this counts wrong answers, not sessions: if a user answers a question wrong, then right, then wrong again, that is 2 wrong answers and it counts.

Invalidated questions are excluded.

---

### `avg_session_duration_seconds`

Average of `(completed_at - started_at)` in seconds across all completed sessions (`status = 'completed'`, all modes).

Returns `null` if no completed sessions exist.

**Limitation:** This is a session-level approximation, not per-question timing. It includes navigation time, pauses, and any time the user left the session open. A proper per-question metric would require `time_spent_seconds` on `user_answers` — that is a future schema change and is out of scope here.

---

## 6. Query Design

All stats for a user must be computed in as few DB round-trips as possible. The recommended approach is one query per stat group:

| Stat group | Query |
|---|---|
| `total_answered`, `overall_success_rate`, `part_b`, `part_c` | Single query: join `user_answers → practice_sessions → questions`, filter `status='completed'` and `questions.status='active'`, group by `questions.part` |
| `simulations_completed` | Single count: `practice_sessions` where `user_id`, `mode='exam'`, `status='completed'` |
| `active_mistakes_count` | Reuse existing `get_latest_mistakes` logic from `answer_repository`, count results |
| `repeated_mistakes_count` | Single query: `user_answers → practice_sessions → questions`, group by `question_id`, having `sum(is_correct = false) >= 2` |
| `avg_session_duration_seconds` | Single avg: `completed_at - started_at` over completed sessions |

Do not run one query per field. Combine where possible.

---

## 7. Layering Rules

Same rules as Phase 2.

```
Router → Service → Repository → ORM
```

- **`stats_repository.py`**: all DB queries for stats. Returns raw aggregated values.
- **`stats_service.py`**: assembles the response from repository results, handles null cases, formats decimals.
- **Router**: adds the route to `users.py` or a new `stats.py` — either is acceptable. No business logic.

Do not add stats queries to `answer_repository.py` or `practice_session_repository.py`. Keep them in `stats_repository.py`.

---

## 8. Folder Structure Changes

Add:

```
app/
├── repositories/
│   └── stats_repository.py   # new
├── services/
│   └── stats_service.py      # new
└── routers/
    └── stats.py              # new (or add route to users.py — see note below)
schemas/
└── stats.py                  # new
```

The stats endpoint is scoped to a user (`/users/{user_id}/stats/overview`), so it fits naturally under `users.py`. Either location is acceptable — pick one and be consistent. A separate `stats.py` router is preferred if more stat endpoints are anticipated.

---

## 9. Per-Question Timing — Deferred

The CLAUDE.md conceptual model lists `time_spent_seconds` on `UserAnswer`. This field was not added in Phase 2.

`avg_session_duration_seconds` is a proxy.

When per-question timing is needed, add `time_spent_seconds integer nullable` to `user_answers` in a future migration and have the client send it on answer submission. Do not add it in this phase unless explicitly requested.

---

## 10. Tests

Add `tests/test_stats.py`.

Required test cases:

- User with no completed sessions returns zero counts, null rates, null duration
- `total_answered` counts answer events across sessions (same question in two sessions = 2)
- `overall_success_rate` is null when `total_answered = 0`
- `overall_success_rate` is correct with known correct/incorrect answers
- `part_b.success_rate` and `part_c.success_rate` computed from `questions.part`, not `sessions.part`
- `part_b.success_rate` is null when no part B answers exist
- Answers to invalidated questions are excluded from `total_answered` and success rates
- `simulations_completed` counts only `mode='exam'` completed sessions
- `active_mistakes_count` matches the count of results from the mistakes endpoint
- `repeated_mistakes_count` counts questions with ≥ 2 wrong answers; a question answered wrong once does not count
- `repeated_mistakes_count` excludes invalidated questions
- `avg_session_duration_seconds` is null with no completed sessions
- `avg_session_duration_seconds` is the average across multiple completed sessions
- Sessions with `status='active'` do not contribute to any stat
- 404 returned for unknown user
- No `db.query()` anywhere in new code

---

## 11. Risky Decisions to Review Before Coding

**1. Invalidated questions are excluded from all success rate metrics**

Answers to invalidated questions are stored with `is_correct = false` (Phase 2 behavior). Including them would artificially lower the success rate. Exclusion is implemented by joining `user_answers → questions` and filtering on `questions.status = 'active'`.

This means `total_answered` also excludes invalidated question answers. The user may notice the count is lower than the number of questions they actually submitted answers to. This is intentional.

**2. Part success rate is computed from `questions.part`, not `sessions.part`**

`practice_sessions.part` can be `null` when both parts are included in a session. Always join through to `questions.part` for per-part stats. Never group by `sessions.part`.

**3. `overall_success_rate` includes all modes**

Practice, exam, and mistakes sessions all count equally toward the overall rate. Mistakes practice sessions may lower the rate (users are practicing questions they previously got wrong). This is the accurate picture of total practice performance.

If a mode-specific rate is needed later (e.g., exam-only success rate), add it as a separate field — do not change the definition of `overall_success_rate`.

**4. `repeated_mistakes_count` counts wrong answers, not sessions**

A question answered wrong → right → wrong across three sessions has 2 wrong answers and counts. A question answered wrong once in one session does not count. The threshold is ≥ 2 wrong `user_answers` rows (across completed sessions).

**5. `avg_session_duration_seconds` is session-level, not per question**

This is a proxy. The denominator is number of completed sessions, not number of questions. It does not normalize for session length. A 40-question exam session and a 5-question practice session contribute equally to the average, which makes this metric imprecise. Accept this for MVP. Document it clearly in the API response if needed.

**6. No caching in this phase**

Stats are computed on every request. With the current scale (a few users, a few hundred sessions), this is fine. Do not add caching until profiling shows it is needed.

---

## 12. Acceptance Criteria

The phase is complete when:

- All tests in `test_stats.py` pass.
- No new migrations were added.
- Existing Phase 1 and Phase 2 tests still pass.
- `GET /api/v1/users/{user_id}/stats/overview` returns correct values for a dev user who has completed sessions across both parts.
- The endpoint returns correct null/zero values for a new user with no sessions.
- No `db.query()` in any new code.
- No ORM objects returned from routers.
