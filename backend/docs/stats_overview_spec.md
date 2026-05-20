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

Count of questions where the user's most recent answer is `is_correct = false`. "Most recent" is defined as `answered_at DESC, id DESC` across all completed sessions.

This must use the same semantics as the Phase 2 mistakes endpoint. See Section 6 for cross-repository rules.

---

### `repeated_mistakes_count`

Count of distinct questions where the user has at least 2 answers with `is_correct = false` across all completed sessions.

This measures persistent difficulty — questions the user has gotten wrong more than once. Note this counts wrong answers, not sessions: if a user answers a question wrong, then right, then wrong again, that is 2 wrong answers and it counts.

Invalidated questions are excluded.

---

### `avg_session_duration_seconds`

Average of `(completed_at - started_at)` in seconds across all completed sessions (`status = 'completed'`, all modes).

Returns `null` if no completed sessions exist.

**Query guard:** Filter on `completed_at IS NOT NULL AND started_at IS NOT NULL` explicitly. Do not rely on `status = 'completed'` alone to guarantee both fields are populated — a data bug could produce a null timestamp on an otherwise completed session, which would cause a DB error or null result depending on dialect. Additionally, discard any row where `completed_at < started_at` (negative duration) rather than letting it silently distort the average.

**Limitation:** This is a session-level approximation, not per-question timing. It includes navigation time, pauses, and any time the user left the session open. A proper per-question metric would require `time_spent_seconds` on `user_answers` — that is a future schema change and is out of scope here.

---

## 6. Query Design

All stats for a user must be computed in as few DB round-trips as possible. The recommended approach:

| # | Stat group | Query |
|---|---|---|
| 1 | User existence check | `SELECT id FROM users WHERE id = :user_id` — must run first. The `users` table exists from Phase 2 migration `20260520_0002`. A user with no sessions and a non-existent user must return different responses (empty stats vs. 404). |
| 2 | `total_answered`, `overall_success_rate`, `part_b`, `part_c` | Single query: join `user_answers → practice_sessions → questions`, filter `status='completed'` and `questions.status='active'`, group by `questions.part` |
| 3 | `simulations_completed` + `avg_session_duration_seconds` | Single query over `practice_sessions` for this user, filtered on `status='completed'`. Count rows with `mode='exam'` for simulations. For SQLite/test portability, fetch the raw `mode`, `started_at`, and `completed_at` columns and apply the duration guards in the service (filter nulls, filter negative durations, average). This returns one row per session rather than a single aggregate — acceptable for MVP scale (a few hundred sessions per user at most). |
| 4 | `active_mistakes_count` | Implemented in `stats_repository.py` with the same semantics as the Phase 2 mistakes endpoint. See cross-repository rules below. |
| 5 | `repeated_mistakes_count` | Single query: `user_answers → practice_sessions → questions`, filter `status='completed'` and `questions.status='active'`, group by `question_id`, having `SUM(CASE WHEN is_correct = false THEN 1 ELSE 0 END) >= 2`. In SQLAlchemy: `func.sum(case((UserAnswer.is_correct.is_(False), 1), else_=0)) >= 2`. Do not use `count(*) filter (where ...)` — that syntax is Postgres-specific and will break SQLite-based tests. |

**Cross-repository rule for `active_mistakes_count`:** Do not import or call methods from `answer_repository` inside `stats_repository`. Repositories must not call each other. Two options — pick one:

- **Option A (preferred if the logic is short):** Duplicate the aggregate query in `stats_repository.py`. Add a test in `test_stats.py` that asserts `active_mistakes_count` equals `len(GET /users/{id}/mistakes)` for the same user. This verifies semantic equivalence without coupling.
- **Option B:** Extract a shared private query builder (e.g. `app/repositories/_mistakes_query.py`) that both repositories import. Document clearly that it is a shared internal helper and must not grow into a god module.

Whichever option is chosen, document the decision in a comment at the top of the relevant repository method.

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

Do not import repository methods across repositories. See Section 6 for the explicit rule on `active_mistakes_count` cross-repository semantics.

---

## 8. Folder Structure Changes

Add:

```
app/
├── repositories/
│   └── stats_repository.py   # new
├── services/
│   └── stats_service.py      # new
├── routers/
│   └── stats.py              # new (or add route to users.py — see note below)
└── schemas/
    └── stats.py              # new — inside app/schemas/, matching existing layout
```

`schemas/` lives under `app/`, not at the repo root. Do not create a top-level `schemas/` directory — it does not match the existing project layout.

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
- `active_mistakes_count` matches the count of results from the mistakes endpoint for the same user (semantic equivalence test)
- Answers from `active` (not-yet-completed) sessions are not counted in `active_mistakes_count` or `repeated_mistakes_count`, and are not counted in answered stats
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

**6. `overall_success_rate` and per-part rates — float vs. Decimal**

The response schema uses `float` with 2 decimal places. Do not use Python `float` arithmetic internally if the division is done in Python — floating-point rounding can produce inconsistent values in tests (e.g. `62.499999...` vs `62.50`). Options:

- Compute the percentage in SQL (`ROUND(100.0 * correct / total, 2)`) and return the result directly.
- Or compute in Python using `Decimal` and convert to `float` only at the Pydantic output boundary.

Tests must compare rates as rounded values (e.g., `pytest.approx(62.5, abs=0.01)` or compare as strings). Pick one approach, document it in `stats_service.py`, and be consistent.

**7. Parts are always B and C**

`part_b` and `part_c` are hardcoded fields in the response schema. The DB `questions.part` column is constrained to `B` and `C`. The service must handle the case where the grouped query returns only one part (or neither) for a user without crashing — default missing parts to `{"total_answered": 0, "success_rate": null}`. If a future part were added, the response schema would need a new field; the grouped-by-part query would not crash but the new part would be silently ignored until a schema change is made.

**8. No caching in this phase**

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

---

## 13. Implementation Notes

The `active_mistakes_count` query must include a short comment near the query explaining:

- it intentionally matches the Phase 2 mistakes endpoint semantics
- latest answer ordering uses `answered_at DESC, id DESC`
