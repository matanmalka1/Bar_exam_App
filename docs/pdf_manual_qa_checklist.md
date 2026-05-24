# PDF Manual QA Checklist

Use this checklist after the PDF pipeline produces JSON and QA reports, before importing data into a shared database.

The goal is not to improve wording. The goal is to prove the generated JSON matches the official PDFs exactly enough for MVP use.

## Scope

Check every exam part:

- `2024-06_B`
- `2024-06_C`
- `2025-04_B`
- `2025-04_C`
- `2025-06_B`
- `2025-06_C`
- `2025-12_B`
- `2025-12_C`

## Required Checks Per Exam Part

1. Open the official question PDF and answer PDF.
2. Open the matching `outputs/<YYYY-MM_PART>/<YYYY-MM_PART>_questions.json`.
3. Open `qa_report_<YYYY-MM_PART>.json`.
4. Confirm `questions_count` is 40 and `answers_count` is 40.
5. Confirm `hard_failures` is empty.
6. Review every item in `manual_review_items`.
7. Compare at least questions 1, 10, 20, 30, and 40 against the PDF.
8. For each sampled question, compare the body text without rewriting it.
9. Compare answer options `א`, `ב`, `ג`, `ד` in exact order.
10. Compare the official correct answer from the answer PDF.
11. Compare the official `סימוכין` text from the answer PDF.
12. Confirm no repeated page headers remain inside `body`, `options`, or `reference`.

## Stop Conditions

Stop and fix the pipeline or source JSON if any of these appear:

- A question body is missing or belongs to the wrong question.
- Answer option order differs from the PDF.
- A correct answer differs from the official answer PDF.
- A `סימוכין` row is missing, split incorrectly, or attached to the wrong question.
- OCR artifacts appear in legal text.
- A header/footer appears inside question or answer text.
- Any issue requires guessing.

Do not silently correct legal text. Document the issue and rerun validation.
