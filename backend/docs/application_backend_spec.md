# Application Backend Spec — Phase 1: Read-Only Question API

## 1. Goal

Expose the imported question data through a read-only FastAPI application.

This is the first application backend slice. It provides practice endpoints that hide official answer data, plus explicit review endpoints over the already-imported `questions` table.

## 2. Non-Goals

The following are explicitly out of scope for this phase:

- Users, registration, login, auth
- Sessions and simulation mode
- User answers, scoring, feedback
- Mistake tracking and bookmarks
- Statistics
- Any write operation on questions
- Changes to the `questions` table schema
- Frontend

Do not implement any of these until this slice is complete and tested.

## 3. Folder Structure

Add the following to `backend/app/`:

```
app/
├── db/
│   └── base.py              # existing
├── models/
│   └── question.py          # existing
├── repositories/
│   └── question_repository.py
├── services/
│   └── question_service.py
├── routers/
│   └── questions.py
├── schemas/
│   └── question.py
└── main.py                  # FastAPI app entry point
```

No other new files are needed for this phase.

## 4. Layering Rules

```
Router → Service → Repository → ORM Model
```

Rules:

- Router handles HTTP, path/query parameter parsing, and response serialization. No DB access.
- Service owns business logic: filtering, label computation, answer letter mapping. No DB access directly.
- Repository owns all DB access. Uses SQLAlchemy 2.0 `select()`. No business logic.
- ORM models (`app/models/`) contain no business logic.
- Pydantic schemas (`app/schemas/`) are API contracts. Routes return schemas, not ORM objects.
- No `db.query()`. Use `select(...)` with `session.scalars()` or `session.execute()`.
- No raw SQL unless justified.
- No cross-domain repository calls.

## 5. Endpoints

### GET /health

Returns service health status. No DB access required.

**Response 200:**

```json
{ "status": "ok" }
```

---

### GET /api/v1/exams

Returns a list of distinct exam parts derived from the `questions` table.

Each entry represents one exam part (a unique `exam_date` + `part` combination) and includes computed Hebrew display labels.

**Response 200:**

```json
[
  {
    "exam_date": "2024-06",
    "part": "B",
    "part_name": "דין דיוני",
    "label": "יוני 2024",
    "question_count": 40
  },
  {
    "exam_date": "2025-04",
    "part": "B",
    "part_name": "דין דיוני",
    "label": "אפריל 2025",
    "question_count": 40
  }
]
```

Ordered by `exam_date` ascending, then `part` ascending (`B` before `C`).

**label computation** (Hebrew month names):

| Month | Label prefix |
|-------|--------------|
| 04    | אפריל        |
| 06    | יוני         |
| 12    | דצמבר        |

Format: `{month_name} {year}`, e.g. `יוני 2024`.

**part_name computation:**

| part | part_name   |
|------|-------------|
| `B`  | דין דיוני   |
| `C`  | דין מהותי   |

`question_count` must count only `status='active'` questions.

---

### GET /api/v1/questions

Returns all questions for a given exam part as a practice payload.

This endpoint must not expose `correct_answer` or `reference`. It is intended for regular practice and future simulation screens before submission.

**Query parameters:**

| Parameter  | Required | Values            |
|------------|----------|-------------------|
| `exam_date`| yes      | `YYYY-MM` string  |
| `part`     | yes      | `B` or `C`        |

**Validation:**

- `exam_date` must match `^\d{4}-\d{2}$`
- `part` must be `B` or `C`
- If either is missing or invalid → 422

**Response 200:**

```json
[
  {
    "stable_id": "2025-04_B_001",
    "exam_date": "2025-04",
    "part": "B",
    "part_name": "דין דיוני",
    "label": "אפריל 2025",
    "number": 1,
    "body": "...",
    "options": {
      "א": "...",
      "ב": "...",
      "ג": "...",
      "ד": "..."
    },
    "status": "active",
    "invalidation_note": null
  }
]
```

Ordered by `number` ascending.

Includes both `active` and `invalidated` questions. Invalidated questions may include `invalidation_note`.

---

### GET /api/v1/questions/review

Returns all questions for a given exam part with official answer data.

This endpoint is for QA, post-submit review, and future result screens only. It must not be used for pre-submit simulation payloads.

These endpoints are not access-protected in this phase. The separation prevents accidental answer leakage in frontend flows, but it is not an authorization boundary.

**Query parameters:** same as `GET /api/v1/questions`.

**Response 200:** Same as `GET /api/v1/questions`, plus:

```json
{
  "correct_answer": "א",
  "reference": "..."
}
```

`correct_answer` is returned as a Hebrew letter (`א`/`ב`/`ג`/`ד`), not the DB value (`A`/`B`/`C`/`D`). The service layer applies the reverse mapping.

**DB-to-display mapping:**

| DB  | Display |
|-----|---------|
| `A` | `א`     |
| `B` | `ב`     |
| `C` | `ג`     |
| `D` | `ד`     |

`options` must be returned as a dict with Hebrew keys, reconstructed from `option_a`/`option_b`/`option_c`/`option_d`.

---

### GET /api/v1/questions/{stable_id}

Returns a single question by its stable ID.

This is also a practice payload and must not expose `correct_answer` or `reference`.

**Path parameter:**

| Parameter   | Format                          |
|-------------|---------------------------------|
| `stable_id` | `YYYY-MM_[BC]_\d{3}`, e.g. `2025-04_B_017` |

**Response 200:** Same schema as individual item in the list endpoint.

**Response 404:**

```json
{ "detail": "question not found" }
```

---

### GET /api/v1/questions/{stable_id}/review

Returns a single question by stable ID with official answer data.

This endpoint is for QA, post-submit review, and future result screens only.

These endpoints are not access-protected in this phase. The separation prevents accidental answer leakage in frontend flows, but it is not an authorization boundary.

## 6. Pydantic Schemas

Define in `app/schemas/question.py`:

```python
class ExamSummary(BaseModel):
    exam_date: str          # "YYYY-MM"
    part: str               # "B" or "C"
    part_name: str          # Hebrew
    label: str              # Hebrew
    question_count: int

class QuestionOptions(BaseModel):
    א: str
    ב: str
    ג: str
    ד: str

class QuestionPracticeOut(BaseModel):
    stable_id: str
    exam_date: str          # "YYYY-MM"
    part: str
    part_name: str          # Hebrew, computed
    label: str              # Hebrew, computed
    number: int
    body: str
    options: QuestionOptions
    status: str             # "active" or "invalidated"
    invalidation_note: str | None

    model_config = ConfigDict(from_attributes=True)

class QuestionReviewOut(QuestionPracticeOut):
    correct_answer: str | None   # Hebrew letter or null
    reference: str

    model_config = ConfigDict(from_attributes=True)
```

All schemas use `model_config = ConfigDict(from_attributes=True)` for ORM compatibility.

## 7. Repository

`app/repositories/question_repository.py`

```python
def get_exams(session: Session) -> list[Row]:
    """Return distinct (exam_date, part, active_count) rows ordered by exam_date, part."""

def get_questions_by_exam(session: Session, exam_date: date, part: str) -> list[Question]:
    """Return all questions for a given exam_date and part, ordered by number."""

def get_question_by_stable_id(session: Session, stable_id: str) -> Question | None:
    """Return a single question by stable_id, or None."""
```

Use `select(...)` with `session.scalars()` or `session.execute()`. No business logic.

## 8. Service

`app/services/question_service.py`

Responsibilities:

- Parse `YYYY-MM` string to `date` object before passing to repository.
- Compute `label` and `part_name` from `exam_date` and `part`.
- Reverse-map DB answer `A`/`B`/`C`/`D` → Hebrew `א`/`ב`/`ג`/`ד` only for review schemas.
- Reconstruct `options` dict with Hebrew keys from `option_a`/`option_b`/`option_c`/`option_d`.
- Build and return Pydantic `ExamSummary`, `QuestionPracticeOut`, and `QuestionReviewOut` objects.

The service must not access the DB directly.

## 9. Router

`app/routers/questions.py`

Responsibilities:

- Declare routes and path/query parameters.
- Validate parameters (FastAPI handles 422 automatically from Pydantic/type annotations).
- Call service functions.
- Return Pydantic schemas.

The router must not access the DB or ORM directly.

## 10. Dependency Injection

Inject a SQLAlchemy `Session` using FastAPI's `Depends`:

```python
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
```

Use this in router functions: `session: Session = Depends(get_session)`.

## 11. Error Handling

- Invalid `exam_date` or `part` query params → 422 (handled automatically by FastAPI).
- `stable_id` not found → 404 with `{ "detail": "question not found" }`.
- No exam data found for a valid `exam_date`/`part` → return empty list `[]`, not 404.
- Unhandled server errors → 500 (FastAPI default).

Do not return ORM objects or raw DB errors to the client.

## 12. main.py

```python
app = FastAPI(title="Bar Exam API")
app.include_router(questions_router, prefix="/api/v1")
```

Include a `/health` route at the top level (not under `/api/v1`).

## 13. Tests

Add tests in `tests/test_questions_api.py`.

Use `pytest` with `httpx.AsyncClient` (or `TestClient`) and an in-memory SQLite DB.

Required test cases:

- `GET /health` → 200 `{ "status": "ok" }`
- `GET /api/v1/exams` → 200, returns list of exam summaries with correct labels and counts
- `GET /api/v1/questions?exam_date=2025-04&part=B` → 200, 40 questions, ordered by number
- `GET /api/v1/questions?exam_date=2025-04&part=B` → each question has Hebrew `options` keys and does not include `correct_answer` or `reference`
- `GET /api/v1/questions/review?exam_date=2025-04&part=B` → each question has Hebrew `correct_answer`, `reference`, and Hebrew `options` keys
- `GET /api/v1/questions?exam_date=9999-99&part=B` → 200, empty list (no data)
- `GET /api/v1/questions` (missing params) → 422
- `GET /api/v1/questions?exam_date=2025-04&part=X` → 422
- `GET /api/v1/questions/2025-04_B_001` → 200, correct practice question without official answer data
- `GET /api/v1/questions/2025-04_B_001/review` → 200, correct question with official answer data
- `GET /api/v1/questions/does-not-exist` → 404
- Invalidated question on review endpoint: `correct_answer` is null, `invalidation_note` is non-empty
- `exam_count` on `/api/v1/exams` counts only active questions

## 14. Acceptance Criteria

The phase is complete when:

- All 6 endpoints return correct data from a real PostgreSQL DB with the imported dataset.
- Practice endpoints do not expose `correct_answer` or `reference`.
- Review endpoints return Hebrew `correct_answer` and Hebrew `options` keys correctly.
- `label` and `part_name` are computed correctly for all 4 exam dates.
- `GET /api/v1/exams` returns 8 entries (4 dates × 2 parts), ordered.
- Invalidated question `2025-12_B_020` is returned on review endpoints with `correct_answer: null`.
- All tests pass.
- No ORM objects leak into router responses.
- No `db.query()` anywhere in the codebase.
