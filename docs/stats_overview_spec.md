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
  "genuine_correct_answers": 70,
  "invalidated_credit_answers": 5,
  "latest_genuine_correct_answers": 45,
  "latest_invalidated_credit_answers": 1,
  "part_b": {
    "total_answered": 60,
    "success_rate": 70.0,
    "genuine_correct_answers": 40,
    "invalidated_credit_answers": 2
  },
  "part_c": {
    "total_answered": 60,
    "success_rate": 55.0,
    "genuine_correct_answers": 30,
    "invalidated_credit_answers": 3
  },
  "simulations_completed": 3,
  "active_mistakes_count": 15,
  "repeated_mistakes_count": 7,
  "avg_session_duration_seconds": 1840
}
```

## Semantics

- `total_answered`: answers from completed sessions, including invalidated questions.
- `overall_success_rate`: credited answers divided by total answers. Credited answers include genuinely correct answers and invalidated-question credit.
- `genuine_correct_answers`: completed-session answers that were correct on active questions.
- `invalidated_credit_answers`: completed-session answers on invalidated questions. These grant full credit but are not genuine correct answers.
- `latest_genuine_correct_answers`: latest-answer mastery count for active questions answered correctly.
- `latest_invalidated_credit_answers`: latest-answer mastery count for invalidated questions.
- `part_b` / `part_c`: same calculation grouped by `questions.part`.
- `simulations_completed`: completed sessions with `mode = "simulation"`.
- `active_mistakes_count`: questions whose latest completed-session answer is wrong.
- `repeated_mistakes_count`: active questions answered wrong at least twice.
- `avg_session_duration_seconds`: average completed-session duration based on `started_at` and `completed_at`.

Answered invalidated questions are included in answer totals and success rates as full-credit answers, but are exposed separately through invalidated-credit fields and never count as active or repeated mistakes.

## Implementation

- Router: `app/routers/stats.py`
- Service: `app/services/stats_service.py`
- Repository: `app/repositories/stats_repository.py`
- Schema: `app/schemas/stats.py`

`stats_repository.count_active_mistakes` intentionally duplicates the mistakes-query semantics without importing `answer_repository`, keeping repositories independent.
