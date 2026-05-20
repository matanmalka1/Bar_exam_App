# Data Ingestion Spec

## 1. Purpose

Define the JSON to DB import step for the bar exam question bank.

The import stage loads already validated pipeline output files into the database. It does not parse PDFs, normalize text, or repair question data.

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

Each imported question must preserve the final JSON structure:

- `stable_id`
- `exam_date`
- `label`
- `part`
- `part_name`
- `number`
- `body`
- `options`
  - Hebrew keys: `א`, `ב`, `ג`, `ד`
  - DB columns may map these to `option_a`, `option_b`, `option_c`, `option_d`
- `status`: `active` or `invalidated`
- `correct_answer`: nullable
- `reference`
- `invalidation_note`: nullable
- `created_at`
- `updated_at`

For DB storage, the MVP can flatten `options` into four columns:

- `option_a`
- `option_b`
- `option_c`
- `option_d`

## 6. DB Tables For MVP

The MVP data model includes:

- `questions`
- `users`
- `sessions`
- `user_answers`
- `bookmarked_questions`

Current import scope:

Only `questions` is implemented in the first import step.

The other tables are defined for later application features and are out of scope for the initial JSON to DB import.

## 7. Constraints

The `questions` table must enforce:

- `stable_id` is unique
- `unique(exam_date, part, number)`
- `part in ('B', 'C')`
- `status in ('active', 'invalidated')`
- `active => correct_answer in ('א', 'ב', 'ג', 'ד')`
- `invalidated => correct_answer is null`
- `invalidated => invalidation_note is not null`
- invalidated questions must still keep the official reference text
- `body` is not empty
- `reference` is not empty
- all four options are not empty

## 8. Import Behavior

The importer must be:

- transactional
- idempotent
- upsert-based by `stable_id`
- fail-all on any validation error
- strict about ignoring debug files
- explicit in its printed summary

If validation fails for any file or question, the importer must roll back the entire import.

## 9. Post-Import Validation

After import, run validation queries/checks for:

- total question count
- active question count
- invalidated question count
- exactly 40 questions per exam part
- no duplicate `stable_id`
- no forbidden artifact strings in final text fields:
  - `00:00`
  - ``
  - `ð`
- final JSON must not contain `correct_answer: "נפסלה"`
- invalidated question exists:
  - `2025-12_B_020`
- invalidated question has:
  - `status = 'invalidated'`
  - `correct_answer is null`
  - non-empty `invalidation_note`
  - non-empty official `reference`

## 10. Expected Summary

Expected successful import summary:

```json
{
  "total_questions": 320,
  "active_questions": 319,
  "invalidated_questions": 1,
  "exam_parts": 8,
  "each_part_count": 40
}
```

## 11. Out Of Scope

The following are not part of this stage:

- API
- UI
- auth implementation
- simulation logic
- statistics
- admin upload
- PDF parsing
- text normalization
- question extraction
