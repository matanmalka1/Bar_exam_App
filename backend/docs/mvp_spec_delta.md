# MVP Spec Delta — Implementation Corrections

This document records where the implemented data layer diverges from the conceptual model described in `CLAUDE.md` and `bar_exam_mvp_spec.docx`. These are not regressions — they are intentional decisions made during implementation. The spec documents should be read in light of these corrections.

## 1. correct_answer storage

**Spec said:** correct_answer is one of `א` / `ב` / `ג` / `ד`

**Implemented:** correct_answer is stored as `A` / `B` / `C` / `D` in the DB.

Hebrew letters are an input and display concern only. The importer maps them:

| Input | DB  |
|-------|-----|
| `א`   | `A` |
| `ב`   | `B` |
| `ג`   | `C` |
| `ד`   | `D` |

The API layer reverses this mapping for display.

## 2. exam_date type

**Spec said:** exam_date is a `YYYY-MM` string.

**Implemented:** exam_date is a `DATE` column, stored as the first day of the exam month.

Examples:
- `"2024-06"` → `2024-06-01`
- `"2025-04"` → `2025-04-01`

API responses expose this as `YYYY-MM` by formatting the date.

## 3. label and part_name not persisted

**Spec said:** Question JSON includes `label` and `part_name`.

**Implemented:** `label` and `part_name` are present in the input JSON but are not stored in the DB. They are computed at display time from `exam_date` and `part`:

| part | part_name   |
|------|-------------|
| `B`  | דין דיוני   |
| `C`  | דין מהותי   |

Hebrew exam labels (e.g. `יוני 2024`) are computed from `exam_date`.

## 4. No Exam table

**Spec said:** There is an `Exam` entity with fields `id`, `exam_date`, `year`, `month`, `label`, `part`, `part_name`.

**Implemented:** No `Exam` table exists. Exam metadata is derived from `questions.exam_date` and `questions.part` at query time.

The API endpoint `GET /api/v1/exams` will compute and return exam metadata from the questions table directly.

## 5. Ingestion complete — application backend not yet started

The data ingestion layer is complete:

- `questions` table created and migrated
- All 320 questions imported (319 active, 1 invalidated)
- Import script, validation, and tests are in place

The following layers are **not yet implemented**:

- FastAPI application
- `users`, `sessions`, `user_answers`, `bookmarked_questions` tables
- Auth
- Simulation logic
- Statistics
- Frontend
