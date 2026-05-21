# Current Data Model Decisions

This file records implemented data-model decisions that are easy to misread from older planning material.

## Answers

Imported JSON and API responses use Hebrew answer labels:

- `א`
- `ב`
- `ג`
- `ד`

The database stores `correct_answer` and submitted answers as:

- `A`
- `B`
- `C`
- `D`

The importer maps Hebrew to Latin values. API services map values back to Hebrew for clients.

## Exam Dates

API and import JSON use `YYYY-MM`.

The database stores `questions.exam_date` as a date on the first day of that month:

- `2024-06` -> `2024-06-01`
- `2025-04` -> `2025-04-01`

## Exam Metadata

There is no `exams` table. Labels and part names are computed from `questions.exam_date` and `questions.part`.

## Answer Keys

There is no separate answer-key table. `questions.correct_answer` and `questions.reference` store the official answer key data.

## Invalidated Questions

Invalidated questions keep their stable IDs and remain in the `questions` table. Official exam mode includes them to preserve source order, but scoring excludes them.
