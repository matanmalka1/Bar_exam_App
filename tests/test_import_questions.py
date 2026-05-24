import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import Base
from app.models.question import Question
from scripts.import_questions import (
    ImportValidationError,
    load_and_validate,
    upsert_questions,
    validate_question_file,
)


def make_question(number: int, **overrides):
    data = {
        "stable_id": f"2025-04_B_{number:03d}",
        "number": number,
        "status": "active",
        "body": f"גוף שאלה {number}",
        "options": {
            "א": "אפשרות א",
            "ב": "אפשרות ב",
            "ג": "אפשרות ג",
            "ד": "אפשרות ד",
        },
        "correct_answer": "א",
        "reference": "סימוכין רשמי",
        "invalidation_note": None,
    }
    data.update(overrides)
    return data


def make_payload(**overrides):
    payload = {
        "exam_date": "2025-04",
        "label": "אפריל 2025",
        "part": "B",
        "part_name": "דין דיוני",
        "questions": [make_question(number) for number in range(1, 41)],
    }
    payload.update(overrides)
    return payload


def assert_validation_fails(payload, expected_message):
    with pytest.raises(ImportValidationError) as exc:
        validate_question_file(Path("2025-04_B_questions.json"), payload)
    assert expected_message in str(exc.value)


def test_active_question_with_null_correct_answer_fails():
    payload = make_payload()
    payload["questions"][0]["correct_answer"] = None

    assert_validation_fails(payload, "active question must have correct_answer א/ב/ג/ד")


def test_invalidated_question_with_correct_answer_fails():
    payload = make_payload()
    payload["questions"][0] = make_question(
        1,
        status="invalidated",
        correct_answer="א",
        invalidation_note="השאלה נפסלה לפי מפתח התשובות הרשמי",
    )

    assert_validation_fails(payload, "invalidated question must have correct_answer=null")


def test_active_question_with_invalidation_note_fails():
    payload = make_payload()
    payload["questions"][0]["invalidation_note"] = "לא אמור להופיע בשאלה פעילה"

    assert_validation_fails(payload, "active question must have invalidation_note=null")


def test_disqualified_answer_literal_fails():
    payload = make_payload()
    payload["questions"][0]["correct_answer"] = "נפסלה"

    assert_validation_fails(payload, "correct_answer='נפסלה' is forbidden")


def test_missing_option_fails():
    payload = make_payload()
    del payload["questions"][0]["options"]["ד"]

    assert_validation_fails(payload, "options must contain exactly א/ב/ג/ד")


def test_invalid_exam_date_month_fails():
    payload = make_payload(exam_date="2025-13")
    payload["questions"] = [make_question(number, stable_id=f"2025-13_B_{number:03d}") for number in range(1, 41)]

    assert_validation_fails(payload, "exam_date must be a real YYYY-MM month")


def test_invalid_stable_id_month_fails():
    payload = make_payload()
    payload["questions"][0]["stable_id"] = "2025-13_B_001"

    assert_validation_fails(payload, "stable_id format is invalid")


def test_stable_id_number_must_be_question_range():
    payload = make_payload()
    payload["questions"][0]["stable_id"] = "2025-04_B_041"

    assert_validation_fails(payload, "stable_id format is invalid")


def test_valid_question_maps_exam_date_and_answer_to_db_values():
    rows = validate_question_file(Path("2025-04_B_questions.json"), make_payload())

    assert rows[0]["exam_date"] == date(2025, 4, 1)
    assert rows[0]["correct_answer"] == "A"
    assert "label" not in rows[0]
    assert "part_name" not in rows[0]


def test_duplicate_stable_id_fails(tmp_path):
    input_dir = tmp_path / "outputs"
    input_dir.mkdir()

    for index, exam_part in enumerate(
        [
            ("2024-06", "B", "דין דיוני"),
            ("2024-06", "C", "דין מהותי"),
            ("2025-04", "B", "דין דיוני"),
            ("2025-04", "C", "דין מהותי"),
            ("2025-06", "B", "דין דיוני"),
            ("2025-06", "C", "דין מהותי"),
            ("2025-12", "B", "דין דיוני"),
            ("2025-12", "C", "דין מהותי"),
        ]
    ):
        exam_date, part, part_name = exam_part
        part_dir = input_dir / f"{exam_date}_{part}"
        part_dir.mkdir()
        questions = []
        for number in range(1, 41):
            if index == 0 and number == 2:
                questions.append(make_question(1, stable_id=f"{exam_date}_{part}_001", body="שכפול stable_id לבדיקה"))
                continue
            stable_id = f"{exam_date}_{part}_{number:03d}"
            questions.append(make_question(number, stable_id=stable_id))
        payload = {
            "exam_date": exam_date,
            "label": "מועד בדיקה",
            "part": part,
            "part_name": part_name,
            "questions": questions,
        }
        (part_dir / f"{exam_date}_{part}_questions.json").write_text(
            __import__("json").dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    with pytest.raises(ImportValidationError) as exc:
        load_and_validate(input_dir)
    assert "duplicate stable_id" in str(exc.value)


def test_upsert_updates_existing_row_instead_of_duplicating():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    row = {
        "stable_id": "2025-04_B_001",
        "exam_date": date(2025, 4, 1),
        "part": "B",
        "number": 1,
        "body": "גוף מקורי",
        "option_a": "אפשרות א",
        "option_b": "אפשרות ב",
        "option_c": "אפשרות ג",
        "option_d": "אפשרות ד",
        "status": "active",
        "correct_answer": "A",
        "reference": "סימוכין רשמי",
        "invalidation_note": None,
    }

    with Session(engine) as session:
        with session.begin():
            upsert_questions(session, [row])
        row["body"] = "גוף מעודכן"
        with session.begin():
            upsert_questions(session, [row])

        questions = session.scalars(select(Question)).all()

    assert len(questions) == 1
    assert questions[0].body == "גוף מעודכן"
