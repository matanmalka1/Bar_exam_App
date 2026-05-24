# Stats Overview Notes

The stats endpoint is implemented at:

```text
GET /api/v1/users/me/stats/overview
```

It requires a bearer access token and returns stats for the authenticated user only.

## Response

```json
{
  "total_answered": 120,
  "overall_success_rate": 62.5,
  "part_b": {
    "total_answered": 60,
    "success_rate": 70.0
  },
  "part_c": {
    "total_answered": 60,
    "success_rate": 55.0
  },
  "simulations_completed": 3,
  "active_mistakes_count": 15,
  "repeated_mistakes_count": 7,
  "avg_session_duration_seconds": 1840
}
```

## Semantics

- `total_answered`: answers from completed sessions for active questions.
- `overall_success_rate`: correct active answers divided by total active answers.
- `part_b` / `part_c`: same calculation grouped by `questions.part`.
- `simulations_completed`: completed sessions with `mode = "simulation"`.
- `active_mistakes_count`: questions whose latest completed-session answer is wrong.
- `repeated_mistakes_count`: active questions answered wrong at least twice.
- `avg_session_duration_seconds`: average completed-session duration based on `started_at` and `completed_at`.

Invalidated questions are excluded from answer totals and success rates.

## Implementation

- Router: `app/routers/stats.py`
- Service: `app/services/stats_service.py`
- Repository: `app/repositories/stats_repository.py`
- Schema: `app/schemas/stats.py`

`stats_repository.count_active_mistakes` intentionally duplicates the mistakes-query semantics without importing `answer_repository`, keeping repositories independent.
