#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, TypeGuard

from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.question import Question  # noqa: E402

EXPECTED_TOTAL = 320
EXPECTED_ACTIVE = 319
EXPECTED_INVALIDATED = 1
EXPECTED_EXAM_PARTS = 8
EXPECTED_PART_COUNT = 40
EXPECTED_INVALIDATED_STABLE_ID = "2025-12_B_020"
OPTION_KEYS = ("א", "ב", "ג", "ד")
ANSWER_TO_DB = {"א": "A", "ב": "B", "ג": "C", "ד": "D"}
VALID_PARTS = {"B": "דין דיוני", "C": "דין מהותי"}
VALID_STATUSES = {"active", "invalidated"}
DISQUALIFIED_ANSWER = "נפסלה"
FORBIDDEN_ARTIFACTS = ("00:00", "", "ð")
STABLE_ID_RE = re.compile(r"^\d{4}-\d{2}_[BC]_\d{3}$")
EXAM_DATE_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})$")
STABLE_ID_FULL_RE = re.compile(r"^(?P<exam_date>\d{4}-\d{2})_(?P<part>[BC])_(?P<number>\d{3})$")


class ImportValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import validated question JSON files into DB.")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    return parser.parse_args()


def resolve_database_url(cli_database_url: str | None) -> str | None:
    if cli_database_url:
        return cli_database_url

    alembic_ini = BACKEND_DIR / "alembic.ini"
    if not alembic_ini.exists():
        return None

    parser = configparser.ConfigParser()
    parser.read(alembic_ini)
    return parser.get("alembic", "sqlalchemy.url", fallback=None)


def is_non_empty_text(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def parse_exam_month(value: Any) -> date | None:
    if not isinstance(value, str):
        return None

    match = EXAM_DATE_RE.match(value)
    if match is None:
        return None

    try:
        return date(int(match.group("year")), int(match.group("month")), 1)
    except ValueError:
        return None


def parse_stable_id(value: Any) -> tuple[str, str, int] | None:
    if not isinstance(value, str):
        return None

    match = STABLE_ID_FULL_RE.match(value)
    if match is None:
        return None

    exam_date = match.group("exam_date")
    if parse_exam_month(exam_date) is None:
        return None

    number = int(match.group("number"))
    if not 1 <= number <= 40:
        return None

    return exam_date, match.group("part"), number


def find_question_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists() or not input_dir.is_dir():
        raise ImportValidationError([f"input directory does not exist: {input_dir}"])

    files: list[Path] = []
    for path in input_dir.rglob("*_questions.json"):
        parts = set(path.parts)
        if "debug" in parts:
            continue
        if path.name.endswith("_dev.json"):
            continue
        files.append(path)
    return sorted(files)


def validate_question_file(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[str] = []
    exam_date = payload.get("exam_date")
    label = payload.get("label")
    part = payload.get("part")
    part_name = payload.get("part_name")
    questions = payload.get("questions")
    location = str(path)
    exam_month = parse_exam_month(exam_date)

    if exam_month is None:
        errors.append(f"{location}: exam_date must be a real YYYY-MM month")
    if not is_non_empty_text(label):
        errors.append(f"{location}: label is required")
    if part not in VALID_PARTS:
        errors.append(f"{location}: part must be B or C")
    elif part_name != VALID_PARTS[part]:
        errors.append(f"{location}: part_name must be {VALID_PARTS[part]!r} for part {part}")
    if not isinstance(questions, list):
        errors.append(f"{location}: questions must be a list")
        raise ImportValidationError(errors)
    if len(questions) != EXPECTED_PART_COUNT:
        errors.append(f"{location}: expected 40 questions, got {len(questions)}")

    numbers: list[int] = []
    rows: list[dict[str, Any]] = []
    for raw_question in questions:
        if not isinstance(raw_question, dict):
            errors.append(f"{location}: question entry must be an object")
            continue

        number = raw_question.get("number")
        stable_id = raw_question.get("stable_id")
        question_location = f"{location}:{stable_id or number or '?'}"
        if isinstance(number, int):
            numbers.append(number)

        options = raw_question.get("options")
        status = raw_question.get("status")
        correct_answer = raw_question.get("correct_answer")
        reference = raw_question.get("reference")
        invalidation_note = raw_question.get("invalidation_note")

        if not isinstance(number, int) or not 1 <= number <= 40:
            errors.append(f"{question_location}: number must be an integer from 1 to 40")
        stable_id_parts = parse_stable_id(stable_id)
        if not is_non_empty_text(stable_id):
            errors.append(f"{question_location}: stable_id format is invalid")
        elif not STABLE_ID_RE.match(stable_id) or stable_id_parts is None:
            errors.append(f"{question_location}: stable_id format is invalid")
        elif isinstance(number, int) and isinstance(exam_date, str) and part in VALID_PARTS:
            expected_stable_id = f"{exam_date}_{part}_{number:03d}"
            if stable_id != expected_stable_id:
                errors.append(f"{question_location}: stable_id must be {expected_stable_id}")

        if not is_non_empty_text(raw_question.get("body")):
            errors.append(f"{question_location}: body is required")
        if not isinstance(options, dict):
            errors.append(f"{question_location}: options must be an object")
            continue
        if set(options) != set(OPTION_KEYS):
            errors.append(f"{question_location}: options must contain exactly א/ב/ג/ד")
        for key in OPTION_KEYS:
            if not is_non_empty_text(options.get(key)):
                errors.append(f"{question_location}: option {key} is required")

        if status not in VALID_STATUSES:
            errors.append(f"{question_location}: status must be active or invalidated")
        if correct_answer == DISQUALIFIED_ANSWER:
            errors.append(f"{question_location}: correct_answer='נפסלה' is forbidden")
        if status == "active" and correct_answer not in OPTION_KEYS:
            errors.append(f"{question_location}: active question must have correct_answer א/ב/ג/ד")
        if status == "active" and invalidation_note is not None:
            errors.append(f"{question_location}: active question must have invalidation_note=null")
        if status == "invalidated":
            if correct_answer is not None:
                errors.append(f"{question_location}: invalidated question must have correct_answer=null")
            if not is_non_empty_text(invalidation_note):
                errors.append(f"{question_location}: invalidated question must have invalidation_note")
        if not is_non_empty_text(reference):
            errors.append(f"{question_location}: reference is required")

        text_fields = [
            ("body", raw_question.get("body")),
            ("reference", reference),
            ("option_א", options.get("א")),
            ("option_ב", options.get("ב")),
            ("option_ג", options.get("ג")),
            ("option_ד", options.get("ד")),
        ]
        for field_name, value in text_fields:
            if isinstance(value, str):
                for artifact in FORBIDDEN_ARTIFACTS:
                    if artifact in value:
                        errors.append(f"{question_location}: forbidden artifact {artifact!r} in {field_name}")

        rows.append(
            {
                "stable_id": stable_id,
                "exam_date": exam_month,
                "part": part,
                "number": number,
                "body": raw_question.get("body"),
                "option_a": options.get("א"),
                "option_b": options.get("ב"),
                "option_c": options.get("ג"),
                "option_d": options.get("ד"),
                "status": status,
                "correct_answer": ANSWER_TO_DB.get(correct_answer) if correct_answer is not None else None,
                "reference": reference,
                "invalidation_note": invalidation_note,
            }
        )

    if sorted(numbers) != list(range(1, 41)):
        errors.append(f"{location}: question numbers must be unique and continuous 1-40")
    stable_ids = [question.get("stable_id") for question in questions if isinstance(question, dict)]
    duplicate_stable_ids = sorted(
        stable_id for stable_id, count in Counter(stable_ids).items() if stable_id is not None and count > 1
    )
    for stable_id in duplicate_stable_ids:
        errors.append(f"{location}: duplicate stable_id {stable_id}")
    if errors:
        raise ImportValidationError(errors)
    return rows


def load_and_validate(input_dir: Path) -> list[dict[str, Any]]:
    files = find_question_files(input_dir)
    if not files:
        raise ImportValidationError([f"no final *_questions.json files found under {input_dir}"])

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ImportValidationError([f"{path}: root JSON value must be an object"])
            rows.extend(validate_question_file(path, payload))
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
        except ImportValidationError as exc:
            errors.extend(exc.errors)

    stable_ids = [row["stable_id"] for row in rows]
    duplicate_stable_ids = sorted(item for item, count in Counter(stable_ids).items() if count > 1)
    for stable_id in duplicate_stable_ids:
        errors.append(f"duplicate stable_id in input: {stable_id}")

    exam_part_numbers = [(row["exam_date"], row["part"], row["number"]) for row in rows]
    duplicate_exam_part_numbers = sorted(item for item, count in Counter(exam_part_numbers).items() if count > 1)
    for exam_date, part, number in duplicate_exam_part_numbers:
        errors.append(f"duplicate exam_date/part/number in input: {exam_date}/{part}/{number}")

    exam_parts = {(row["exam_date"], row["part"]) for row in rows}
    if len(rows) != EXPECTED_TOTAL:
        errors.append(f"expected {EXPECTED_TOTAL} total input questions, got {len(rows)}")
    if len(exam_parts) != EXPECTED_EXAM_PARTS:
        errors.append(f"expected {EXPECTED_EXAM_PARTS} exam parts, got {len(exam_parts)}")

    if errors:
        raise ImportValidationError(errors)
    return rows


def upsert_questions(session: Session, rows: list[dict[str, Any]]) -> None:
    dialect_name = session.bind.dialect.name if session.bind is not None else ""
    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError(f"unsupported database dialect for upsert: {dialect_name}")

    insert_stmt = insert(Question).values(rows)
    update_columns = {
        column.name: getattr(insert_stmt.excluded, column.name)
        for column in Question.__table__.columns
        if column.name not in {"id", "stable_id", "created_at", "updated_at"}
    }
    update_columns["updated_at"] = func.now()
    session.execute(
        insert_stmt.on_conflict_do_update(
            index_elements=[Question.stable_id],
            set_=update_columns,
        )
    )


def run_post_import_validation(session: Session) -> dict[str, Any]:
    errors: list[str] = []

    total_questions = session.scalar(select(func.count()).select_from(Question)) or 0
    active_questions = (
        session.scalar(select(func.count()).select_from(Question).where(Question.status == "active")) or 0
    )
    invalidated_questions = (
        session.scalar(select(func.count()).select_from(Question).where(Question.status == "invalidated")) or 0
    )
    exam_parts = (
        session.scalar(
            select(func.count()).select_from(
                select(Question.exam_date, Question.part).group_by(Question.exam_date, Question.part).subquery()
            )
        )
        or 0
    )
    part_counts = session.execute(
        select(Question.exam_date, Question.part, func.count())
        .group_by(Question.exam_date, Question.part)
        .order_by(Question.exam_date, Question.part)
    ).all()
    duplicate_stable_ids = (
        session.execute(select(Question.stable_id).group_by(Question.stable_id).having(func.count() > 1))
        .scalars()
        .all()
    )

    if total_questions != EXPECTED_TOTAL:
        errors.append(f"expected total_questions={EXPECTED_TOTAL}, got {total_questions}")
    if active_questions != EXPECTED_ACTIVE:
        errors.append(f"expected active_questions={EXPECTED_ACTIVE}, got {active_questions}")
    if invalidated_questions != EXPECTED_INVALIDATED:
        errors.append(f"expected invalidated_questions={EXPECTED_INVALIDATED}, got {invalidated_questions}")
    if exam_parts != EXPECTED_EXAM_PARTS:
        errors.append(f"expected exam_parts={EXPECTED_EXAM_PARTS}, got {exam_parts}")
    bad_part_counts = [(exam_date, part, count) for exam_date, part, count in part_counts if count != 40]
    if bad_part_counts:
        errors.append(f"exam parts with count != 40: {bad_part_counts}")
    if duplicate_stable_ids:
        errors.append(f"duplicate stable_id rows found: {duplicate_stable_ids}")

    invalidated = session.scalar(select(Question).where(Question.stable_id == EXPECTED_INVALIDATED_STABLE_ID))
    if invalidated is None:
        errors.append(f"missing invalidated question {EXPECTED_INVALIDATED_STABLE_ID}")
    else:
        if invalidated.status != "invalidated":
            errors.append(f"{EXPECTED_INVALIDATED_STABLE_ID}: status must be invalidated")
        if invalidated.correct_answer is not None:
            errors.append(f"{EXPECTED_INVALIDATED_STABLE_ID}: correct_answer must be null")
        if not is_non_empty_text(invalidated.invalidation_note):
            errors.append(f"{EXPECTED_INVALIDATED_STABLE_ID}: invalidation_note must be non-empty")
        if not is_non_empty_text(invalidated.reference):
            errors.append(f"{EXPECTED_INVALIDATED_STABLE_ID}: reference must be non-empty")

    artifact_filters = []
    for artifact in FORBIDDEN_ARTIFACTS:
        like_value = f"%{artifact}%"
        artifact_filters.append(Question.body.like(like_value))
        artifact_filters.append(Question.option_a.like(like_value))
        artifact_filters.append(Question.option_b.like(like_value))
        artifact_filters.append(Question.option_c.like(like_value))
        artifact_filters.append(Question.option_d.like(like_value))
        artifact_filters.append(Question.reference.like(like_value))
    artifact_rows = (
        session.execute(select(Question.stable_id).where(or_(*artifact_filters)).order_by(Question.stable_id))
        .scalars()
        .all()
    )
    if artifact_rows:
        errors.append(f"forbidden artifacts found in DB text fields: {artifact_rows}")

    summary = {
        "total_questions": total_questions,
        "active_questions": active_questions,
        "invalidated_questions": invalidated_questions,
        "exam_parts": exam_parts,
        "each_part_count": EXPECTED_PART_COUNT if not bad_part_counts else None,
    }
    if errors:
        raise ImportValidationError(errors)
    return summary


def main() -> int:
    args = parse_args()
    database_url = resolve_database_url(args.database_url)
    if not database_url:
        print("ERROR: provide --database-url or set DATABASE_URL", file=sys.stderr)
        return 2

    try:
        rows = load_and_validate(args.input_dir)
        engine = create_engine(database_url)
        with Session(engine) as session:
            with session.begin():
                upsert_questions(session, rows)
                summary = run_post_import_validation(session)
    except ImportValidationError as exc:
        print("IMPORT FAILED", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print("IMPORT FAILED", file=sys.stderr)
        print(f"- database error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
