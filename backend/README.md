# Bar Exam App — Backend

Hebrew RTL PWA for practicing past Israeli Bar Association qualification exams.

## Project Status

| Layer              | Status      |
|--------------------|-------------|
| PDF extraction     | Complete    |
| JSON validation    | Complete    |
| DB schema          | Complete    |
| Data import        | Complete    |
| Application API    | Not started |
| Frontend           | Not started |

The questions table is populated with 320 questions across 8 exam parts. The application backend (FastAPI, auth, sessions, statistics) has not been implemented yet.

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

### Run tests

```bash
pytest tests/ -v
```

### Run linters

```bash
ruff check .
pylint app scripts tests alembic/env.py alembic/versions/*.py
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
