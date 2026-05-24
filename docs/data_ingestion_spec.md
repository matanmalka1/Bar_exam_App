# Data Ingestion Spec

## 1. Purpose

Define the JSON to DB import step for the bar exam question bank.

The import stage loads already validated pipeline output files into the database. It does not parse PDFs, normalize text, or repair question data.

## 1.1 Source Data Rules

- Preserve original question text exactly.
- Do not rewrite Hebrew wording.
- Do not change answer order.
- Do not infer missing answers.
- Do not override official answer keys.
- Use `stable_id` as the question business identifier.
- Invalid source data must fail validation or be marked for manual review.

## 2. Allowed Input Files

The importer may read only final question JSON files:

```text
backend/outputs/*/*_questions.json
```

## 3. Forbidden Input Files

The importer must not read or import:

- `raw_*.txt`
- `normalized_*.txt`
- `*_dev.json`
- `qa_report_*.json`
- `normalization_report_*.json`
- PDF files
- Any file under `debug/`

## 4. Expected Dataset

The current validated dataset contains:

- 8 exam parts
- 320 total questions
- 319 active questions
- 1 invalidated question
- 40 questions per exam part

Expected exam parts:

- `2024-06_B`
- `2024-06_C`
- `2025-04_B`
- `2025-04_C`
- `2025-06_B`
- `2025-06_C`
- `2025-12_B`
- `2025-12_C`

## 5. Question Schema

The formal JSON Schema is stored at:

```text
backend/docs/question_import.schema.json
```

The schema defines the file envelope and per-question shape. The Python importer still owns cross-record validation that JSON Schema cannot express cleanly, such as global `stable_id` uniqueness and continuous question numbers.

### Input JSON fields (per question object)

| Field               | Type                      | Notes                                     |
|---------------------|---------------------------|-------------------------------------------|
| `stable_id`         | string                    | e.g. `2025-04_B_017`                      |
| `number`            | integer 1–40              |                                           |
| `status`            | `active` / `invalidated`  |                                           |
| `body`              | string                    | non-empty                                 |
| `options`           | object                    | keys: `א`, `ב`, `ג`, `ד` — all non-empty |
| `correct_answer`    | `א`/`ב`/`ג`/`ד` or null  | null if invalidated                       |
| `reference`         | string                    | non-empty                                 |
| `invalidation_note` | string or null            | non-empty if invalidated, null if active  |

### Input JSON envelope fields (per file)

| Field       | Notes                                       |
|-------------|---------------------------------------------|
| `exam_date` | `YYYY-MM` string, e.g. `"2025-04"`         |
| `label`     | Hebrew display label — **not stored in DB** |
| `part`      | `B` or `C`                                 |
| `part_name` | Hebrew part name — **not stored in DB**     |

## 6. DB Storage Decisions

### correct_answer mapping

Hebrew answer letters are an input and display concern only.
The DB stores Latin single-character values:

| Input | DB value |
|-------|----------|
| `א`   | `A`      |
| `ב`   | `B`      |
| `ג`   | `C`      |
| `ד`   | `D`      |

The importer applies this mapping. The API layer reverses it for display.

### exam_date type

`exam_date` is stored as `DATE` (PostgreSQL), set to the first day of the exam month.

Examples:

- `"2025-04"` → `2025-04-01`
- `"2024-06"` → `2024-06-01`

### label and part_name

`label` and `part_name` from the input JSON are not persisted.
They are computed at display time from `exam_date` and `part`.

### options mapping

`options.א` → `option_a`, `options.ב` → `option_b`, `options.ג` → `option_c`, `options.ד` → `option_d`.

## 7. DB Tables

The current data model includes:

- `questions`
- `users`
- `practice_sessions`
- `practice_session_questions`
- `user_answers`
- `bookmarked_questions`

Current import scope is only `questions`. User, session, answer, and bookmark rows are created by the application at runtime.

There is no separate `exams` table. Exam metadata is derived from `questions.exam_date` and `questions.part` at query time.

There is no separate `answer_keys` table. `correct_answer` and `reference` are stored directly on `questions` because each imported question has exactly one official answer key row. The API must still avoid exposing those fields in pre-submit practice payloads.

Invalidated questions remain in the `questions` table. They keep their stable IDs, are included in source-data QA views, are excluded from active question counts, and are not selected for simulation. Official exam replay includes them to preserve the source exam.

## 8. Constraints

The `questions` table enforces:

- `stable_id` is unique
- `unique(exam_date, part, number)`
- `part in ('B', 'C')`
- `number between 1 and 40`
- `status in ('active', 'invalidated')`
- `active => correct_answer in ('A', 'B', 'C', 'D') AND invalidation_note IS NULL`
- `invalidated => correct_answer IS NULL AND invalidation_note IS NOT NULL AND length(trim(invalidation_note)) > 0`
- `body` is not empty
- `reference` is not empty
- all four options are not empty

## 9. Import Behavior

The importer (`scripts/import_questions.py`) is:

- transactional (single transaction for all 320 rows)
- idempotent (upsert by `stable_id`)
- fail-all on any validation error (full rollback)
- strict about ignoring debug files
- explicit in its printed summary
- deterministic for a given set of JSON files

If validation fails for any file or question, the importer rolls back the entire import.

The importer does not silently delete DB rows that are absent from the input. Missing or extra input data must be caught by validation before import is considered successful.

Validation must hard-fail on missing question numbers, malformed question structure, duplicate `stable_id`, missing answer keys for active questions, invalid answer labels, and invalidated questions that still contain a correct answer. Source inconsistencies that cannot be repaired mechanically must remain in `manual_review_items` until checked against the official PDF.

### Run command

```bash
python scripts/import_questions.py --input-dir outputs
```

By default the importer reads `DATABASE_URL` from the environment, falling back to `sqlalchemy.url` in `alembic.ini`.

To override:

```bash
python scripts/import_questions.py --input-dir outputs --database-url postgresql+psycopg://...
```

## 10. Post-Import Validation

After import, the importer runs validation queries for:

- total question count = 320
- active question count = 319
- invalidated question count = 1
- exactly 40 questions per exam part (8 parts)
- no duplicate `stable_id` in DB
- no forbidden artifact strings in text fields: `00:00`, ``, `ð`
- invalidated question `2025-12_B_020` exists with `status='invalidated'`, `correct_answer IS NULL`, non-empty `invalidation_note`

## 10.1 QA Report Contract

Every PDF pipeline run writes `qa_report_<YYYY-MM_PART>.json`. The report must be useful for manual review, not only pass/fail status.

Required report fields:

- `exam_date`
- `part`
- `questions_count`
- `answers_count`
- `missing_questions`
- `missing_answers`
- `duplicate_q_ids`
- `duplicate_ids`
- `invalid_options`
- `short_question_bodies`
- `short_answer_options`
- `suspicious_references`
- `source_artifacts`
- `hard_failures`
- `manual_review`
- `manual_review_items`
- `warnings`

`hard_failures` block import. `manual_review` and `manual_review_items` require human inspection against the official PDF before accepting the generated JSON.

## 11. Expected Summary

Expected successful import output:

```json
{
  "total_questions": 320,
  "active_questions": 319,
  "invalidated_questions": 1,
  "exam_parts": 8,
  "each_part_count": 40
}
```

## 12. Running Migrations

Apply all migrations before running the importer:

```bash
alembic upgrade head
```

This creates the tables, constraints, and indexes expected by the application.

## 13. Running Tests

```bash
pytest tests/test_import_questions.py -v
```

The import tests cover:

- active question with `correct_answer=null` → fails validation
- invalidated question with non-null `correct_answer` → fails validation
- active question with non-null `invalidation_note` → fails validation
- `correct_answer='נפסלה'` literal → fails validation
- missing option key → fails validation
- valid question maps `exam_date` to `date(YYYY, MM, 1)` and `correct_answer` to Latin letter
- duplicate `stable_id` across files → fails validation
- upsert updates existing row without duplicating

## 14. What Must Not Be Committed

```text
__pycache__/
*.pyc
*.pyo
.venv/
outputs/**/debug/
outputs/**/raw_*.txt
outputs/**/normalized_*.txt
outputs/**/*_dev.json
.env
.env.*
```

These are covered by `.gitignore` at the repo root.

## 15. Out Of Scope

The following are not part of the import stage:

- UI
- password reset
- admin upload
- PDF parsing
- text normalization
- question extraction
- Exam table
