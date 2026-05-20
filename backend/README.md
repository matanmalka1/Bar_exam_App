# Bar Exam App — Backend

Hebrew RTL PWA for practicing past Israeli Bar Association qualification exams.

## Project Status

| Layer                                                                   | Status          |
| ----------------------------------------------------------------------- | --------------- |
| PDF extraction                                                          | Implemented     |
| JSON validation                                                         | Implemented     |
| DB schema                                                               | Implemented     |
| Data import                                                             | Implemented     |
| Phase 1 read-only question API                                          | Implemented     |
| Phase 2 user progress API (practice / mistakes / bookmarks / exam / simulation) | Implemented     |
| Real auth (email/password, JWT)                                         | Not implemented |
| Statistics dashboard                                                    | Not implemented |
| Per-question timing                                                     | Not implemented |
| Frontend                                                                | Not implemented |

The questions table is populated with 320 questions across 8 exam parts. The Phase 1 read-only question API is implemented. The Phase 2 user progress layer is implemented and covers: practice sessions, mistakes-only sessions, bookmark-only sessions, official past-exam replay (`exam` mode, requires `exam_date`; full 80 questions or single 40-question part from that exam), and mixed 80-question simulation (`simulation` mode; 40 B + 40 C drawn from the full pool across all imported dates). Both `exam` and `simulation` hide the answer key until completion and return a per-part score breakdown and mistake list on complete. Real authentication (only a dev user exists today), statistics endpoints, and the frontend are not implemented.

## Folder Structure

```
backend/
├── alembic/                  # DB migrations
│   └── versions/
│       ├── 20260520_0001_create_questions.py
│       └── 20260520_0002_create_user_progress.py
├── app/
│   ├── db/
│   │   └── base.py           # SQLAlchemy declarative base
│   ├── models/
│   │   ├── question.py       # Question ORM model
│   │   ├── user.py           # User ORM model
│   │   ├── practice_session.py
│   │   ├── practice_session_question.py
│   │   ├── user_answer.py
│   │   └── bookmarked_question.py
│   ├── repositories/
│   │   ├── question_repository.py
│   │   ├── practice_session_repository.py
│   │   └── user_repository.py
│   ├── services/
│   │   ├── question_service.py
│   │   ├── practice_session_service.py
│   │   └── user_service.py
│   ├── routers/
│   │   ├── questions.py
│   │   ├── practice_sessions.py
│   │   └── users.py
│   ├── schemas/
│   │   ├── question.py
│   │   ├── session.py
│   │   ├── answer.py
│   │   └── user.py
│   └── main.py
├── docs/
│   ├── data_ingestion_spec.md
│   ├── application_backend_spec.md
│   ├── user_progress_spec.md
│   ├── pdf_manual_qa_checklist.md
│   ├── question_import.schema.json
│   └── mvp_spec_delta.md
├── outputs/                  # Pipeline output (one dir per exam part)
│   └── <YYYY-MM_PART>/
│       ├── <YYYY-MM_PART>_questions.json   ← importer reads this
│       ├── qa_report_<YYYY-MM_PART>.json
│       ├── normalization_report_<YYYY-MM_PART>.json
│       └── debug/                          ← not committed
├── scripts/
│   ├── pipeline.py           # PDF → JSON extraction pipeline
│   ├── import_questions.py   # JSON → DB importer
│   └── smoke_api.sh          # API smoke test script
├── tests/
│   ├── conftest.py
│   ├── test_import_questions.py
│   └── test_user_progress.py
├── uploads/                  # Source PDFs (not committed)
├── alembic.ini
└── requirements.txt
```

## Setup

### Requirements

- Python 3.12+
- PostgreSQL running locally

### Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Database

Default connection (see `alembic.ini`):

```
postgresql+psycopg://postgres:postgres@localhost:5432/bar_exam_study
```

Override with environment variable:

```bash
export DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname
```

If you prefer file-based env vars, export them through your shell or process manager before starting the app.

## Run Commands

### Apply migrations

```bash
alembic upgrade head
```

### Import questions

```bash
python scripts/import_questions.py --input-dir outputs
```

The importer validates all JSON files, maps Hebrew answer letters to A/B/C/D, performs an upsert by `stable_id`, and runs post-import validation. On any error it rolls back and exits with a non-zero code.

Expected output on success:

```json
{
  "total_questions": 320,
  "active_questions": 319,
  "invalidated_questions": 1,
  "exam_parts": 8,
  "each_part_count": 40
}
```

### Run API

```bash
uvicorn app.main:app --reload --reload-dir app
```

### Smoke test API

With the API running and questions imported:

```bash
scripts/smoke_api.sh
```

Use `BASE_URL` to target a non-default host or port:

```bash
BASE_URL=http://127.0.0.1:8001 scripts/smoke_api.sh
```

### Run tests

```bash
pytest tests/ -v
```

### Run linters

```bash
ruff check .
pylint app scripts tests alembic/env.py alembic/versions/*.py
pyright
vulture
```

## Data Model

### questions table

| Column              | Type        | Notes                                            |
| ------------------- | ----------- | ------------------------------------------------ |
| `id`                | integer PK  |                                                  |
| `stable_id`         | varchar(32) | unique, e.g. `2025-04_B_017`                     |
| `exam_date`         | date        | first day of exam month, e.g. `2025-04-01`       |
| `part`              | varchar(1)  | `B` or `C`                                       |
| `number`            | integer     | 1–40                                             |
| `body`              | text        | original question text                           |
| `option_a`          | text        | answer option א                                  |
| `option_b`          | text        | answer option ב                                  |
| `option_c`          | text        | answer option ג                                  |
| `option_d`          | text        | answer option ד                                  |
| `status`            | varchar(16) | `active` or `invalidated`                        |
| `correct_answer`    | varchar(1)  | `A`/`B`/`C`/`D` for active, NULL for invalidated |
| `reference`         | text        | official סימוכין                                 |
| `invalidation_note` | text        | non-empty for invalidated, NULL for active       |
| `created_at`        | timestamptz |                                                  |
| `updated_at`        | timestamptz |                                                  |

`correct_answer` is stored as a Latin letter (`A`/`B`/`C`/`D`). The Hebrew display labels (`א`/`ב`/`ג`/`ד`) are computed by the API layer.

There is no `exams` table. Exam metadata is derived from `questions.exam_date` and `questions.part`.

There is no separate `answer_keys` table in the MVP implementation. `correct_answer` and `reference` are stored directly on `questions` as an intentional MVP simplification.

## User Progress API

### Users

| Endpoint                 | Description                                  |
| ------------------------ | -------------------------------------------- |
| `POST /api/v1/users/dev` | Upsert a dev user by `user_key` (idempotent) |

### Practice Sessions

| Endpoint                                       | Description                                                   |
| ---------------------------------------------- | ------------------------------------------------------------- |
| `POST /api/v1/practice-sessions`               | Create a new session (practice / exam / simulation / mistakes / bookmarks) |
| `GET /api/v1/practice-sessions/{id}`           | Get session with questions and answers                        |
| `POST /api/v1/practice-sessions/{id}/answers`  | Submit or update an answer for a question                     |
| `POST /api/v1/practice-sessions/{id}/complete` | Complete a session and freeze scoring                         |

### User History

| Endpoint                               | Description                                |
| -------------------------------------- | ------------------------------------------ |
| `GET /api/v1/users/{user_id}/sessions` | List all sessions for a user               |
| `GET /api/v1/users/{user_id}/mistakes` | List active mistakes (latest answer wrong) |

### Bookmarks

| Endpoint                                               | Description                   |
| ------------------------------------------------------ | ----------------------------- |
| `GET /api/v1/users/{user_id}/bookmarks`                | List all bookmarked questions |
| `POST /api/v1/users/{user_id}/bookmarks/{stable_id}`   | Add bookmark (idempotent)     |
| `DELETE /api/v1/users/{user_id}/bookmarks/{stable_id}` | Remove bookmark               |

Session mode behavior (see `docs/user_progress_spec.md` for the full spec):

| Mode         | Question pool                                                                                             | Filter args                                                                                  | Answer-key visibility                                                                            |
| ------------ | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `practice`   | All active questions filtered by request                                                                  | `exam_date`, `part`, `question_count`, `include_invalidated` accepted                        | Revealed per-question after the user answers that question                                       |
| `mistakes`   | User's current active mistakes (latest answer wrong across _completed_ sessions; active sessions ignored) | `question_count` accepted; other filter args rejected (422)                                  | Revealed per-question after the user answers that question                                       |
| `bookmarks`  | User's bookmarked questions                                                                               | `question_count` accepted; other filter args rejected (422)                                  | Revealed per-question after the user answers that question                                       |
| `exam`       | Single official exam by date. If `part` omitted: 40 B + 40 C from that date (grouped B-then-C). If `part` set: 40 from that part. Dates never mixed. Invalidated questions are included to preserve the official source. | `exam_date` **required**; `part` optional; `question_count` and `include_invalidated=true` rejected | Hidden for every question while active; revealed for all questions after completion |
| `simulation` | Mixed 80-question simulation: 40 B + 40 C from the full active pool across all dates (unseen-first)       | `exam_date`, `part`, `question_count`, `include_invalidated=true` all rejected (422)         | Hidden for every question while active; revealed for all questions after completion              |

Exam and simulation completion responses include `part_breakdown` (only the scorable active questions in the parts present in the session, each with `total` / `answered` / `correct` / `score_percent`) and `mistakes` (list of unanswered or incorrect active questions with `stable_id`, `part`, `number`, `body`, `options`, `selected_answer`, `correct_answer`, `reference`). For practice / mistakes / bookmarks sessions both fields are `null`. Simulation score denominator is `total_questions` because simulation selects only active questions. Exam score denominator excludes invalidated questions; invalidated questions stay in the session and are visible with `status=invalidated`, but they are not counted as wrong and are not included in the mistakes list.

Answer mutability: within an active session, the user can resubmit an answer for a given question and the row is upserted by `(session_id, question_id)`. Once the session is completed, its answer rows are frozen. Cross-session history is preserved because each session has its own answer rows.

## API Answer Visibility

Practice endpoints do not expose official answer data:

- `GET /api/v1/questions`
- `GET /api/v1/questions/{stable_id}`

Review endpoints expose `correct_answer` and `reference` and are intended only for QA, post-submit review, and future result screens:

- `GET /api/v1/questions/review`
- `GET /api/v1/questions/{stable_id}/review`

These endpoints are not access-protected in this phase. The separation prevents accidental answer leakage in frontend flows, but it is not an authorization boundary.

Simulation and regular practice flows must use practice payloads before submission.

## Invalidated Questions

Invalidated questions stay in the database with their stable IDs. They are included in source-data QA and review views. Official `exam` mode includes them to preserve the original exam source, but excludes them from scoring denominators and mistakes. Simulation selects only active questions. Normal practice excludes invalidated questions unless `include_invalidated=true`.

## What Is Not Committed

```text
__pycache__/
*.pyc
.venv/
uploads/
outputs/**/debug/
outputs/**/raw_*.txt
outputs/**/normalized_*.txt
outputs/**/*_dev.json
.env
.env.*
```
