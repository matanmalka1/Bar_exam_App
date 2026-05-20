# Bar Exam App — Backend

Hebrew RTL PWA for practicing past Israeli Bar Association qualification exams.

## Project Status

| Layer              | Status      |
|--------------------|-------------|
| PDF extraction     | Complete    |
| JSON validation    | Complete    |
| DB schema          | Complete    |
| Data import        | Complete    |
| Application API    | Read-only questions complete |
| Frontend           | Not started |

The questions table is populated with 320 questions across 8 exam parts. The read-only FastAPI question API is implemented. Auth, sessions, scoring, mistakes, bookmarks, statistics, and frontend have not been implemented yet.

## Folder Structure

```
backend/
├── alembic/                  # DB migrations
│   └── versions/
│       └── 20260520_0001_create_questions.py
├── app/
│   ├── db/
│   │   └── base.py           # SQLAlchemy declarative base
│   └── models/
│       └── question.py       # Question ORM model
├── docs/
│   ├── data_ingestion_spec.md
│   ├── application_backend_spec.md
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
│   └── import_questions.py   # JSON → DB importer
├── tests/
│   └── test_import_questions.py
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

| Column             | Type          | Notes                                            |
|--------------------|---------------|--------------------------------------------------|
| `id`               | integer PK    |                                                  |
| `stable_id`        | varchar(32)   | unique, e.g. `2025-04_B_017`                     |
| `exam_date`        | date          | first day of exam month, e.g. `2025-04-01`       |
| `part`             | varchar(1)    | `B` or `C`                                       |
| `number`           | integer       | 1–40                                             |
| `body`             | text          | original question text                           |
| `option_a`         | text          | answer option א                                  |
| `option_b`         | text          | answer option ב                                  |
| `option_c`         | text          | answer option ג                                  |
| `option_d`         | text          | answer option ד                                  |
| `status`           | varchar(16)   | `active` or `invalidated`                        |
| `correct_answer`   | varchar(1)    | `A`/`B`/`C`/`D` for active, NULL for invalidated |
| `reference`        | text          | official סימוכין                                 |
| `invalidation_note`| text          | non-empty for invalidated, NULL for active        |
| `created_at`       | timestamptz   |                                                  |
| `updated_at`       | timestamptz   |                                                  |

`correct_answer` is stored as a Latin letter (`A`/`B`/`C`/`D`). The Hebrew display labels (`א`/`ב`/`ג`/`ד`) are computed by the API layer.

There is no `exams` table. Exam metadata is derived from `questions.exam_date` and `questions.part`.

There is no separate `answer_keys` table in the MVP implementation. `correct_answer` and `reference` are stored directly on `questions` as an intentional MVP simplification.

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

Invalidated questions stay in the database with their stable IDs. They are included in source-data QA and review views, excluded from active exam counts, and must not be selected for normal practice or simulation unless a future QA-only flow explicitly requests them.

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
