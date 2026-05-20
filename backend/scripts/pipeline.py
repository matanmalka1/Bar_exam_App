#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bar Exam PDF → JSON pipeline  —  v2
====================================

שכבות:
  1. raw_text       — חילוץ טקסט גולמי מ-PDF (pypdfium2)
  2. normalized     — ניקוי תווים שבורים, הסרת headers (תיעוד מלא)
  3. questions      — חילוץ שאלות + אפשרויות תשובה + normalization לכל שדה
  4. answers        — חילוץ תשובות + סימוכין
  5. merge+QA       — מיזוג, ולידציות, JSON, QA report, normalization report

תיקונים לעומת v1:
  - header removal: substring matching (לא regex) — עמיד בפני NBSP ו-soft-hyphen
  - normalization: U+F8FF → נ  (מתועד לכל שאלה ושדה)
  - ולידציה חדשה: hard-fail אם body/options מכילים header artifacts
  - normalization_report נפרד עם פירוט כל שינוי
  - CLI מלא: --exam-date --label --part --part-name --questions-pdf --answers-pdf --out-dir

כלל עקרון: אם יש ספק — manual_review. לא מנחשים. לא מתקנים אוטומטית ללא תיעוד.
"""

import re
import json
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

import pypdfium2 as pdfium


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(
        description="Bar exam PDF → JSON pipeline (v2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python pipeline.py \\
    --exam-date 2025-04 \\
    --label "אפריל 2025" \\
    --part B \\
    --part-name "דין דיוני" \\
    --questions-pdf "/path/to/ שאלות ... .pdf" \\
    --answers-pdf   "/path/to/ תשובות ... .pdf" \\
    --out-dir       "/path/to/output"
        """,
    )
    p.add_argument("--exam-date",     required=True,
                   help='תאריך הבחינה בפורמט YYYY-MM  (e.g. "2025-04")')
    p.add_argument("--label",         required=True,
                   help='תווית קריאה בעברית  (e.g. "אפריל 2025")')
    p.add_argument("--part",          required=True,
                   help='אות החלק באנגלית  (e.g. "B")')
    p.add_argument("--part-name",     required=True,
                   help='שם החלק בעברית  (e.g. "דין דיוני")')
    p.add_argument("--questions-pdf", required=True, type=Path,
                   help="נתיב מלא לקובץ השאלות")
    p.add_argument("--answers-pdf",   required=True, type=Path,
                   help="נתיב מלא לקובץ התשובות")
    p.add_argument("--out-dir",       required=True, type=Path,
                   help="תיקיית פלט (תיווצר אם לא קיימת)")
    return p.parse_args()


# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

EXPECTED_Q     = 40
OPTION_LETTERS = ['א', 'ב', 'ג', 'ד']
VALID_ANSWERS  = set(OPTION_LETTERS)
DISQUALIFIED_ANSWER = "נפסלה"
PART_HEBREW = {
    "A": "חלק א",
    "B": "חלק ב",
    "C": "חלק ג",
}

# U+F8FF — Apple Private Use Area — used as Hebrew nun (נ) via custom font mapping
UFFF_CHAR   = ''

# U+00A0 — Non-Breaking Space — appears in running page headers
NBSP        = '\xa0'

# U+00AD — Soft Hyphen — appears as separator in running page headers
SOFT_HYPHEN = '\xad'

# Running page headers contain the part name and exam timer.
# The part name is supplied by --part-name because each exam part differs.
HEADER_MARKER_B = '00:00'        # exam timer — never appears in question text

# Answer-key marker in answers PDF: .N X' or .N נפסלה
A_MARKER_RE = re.compile(r"\.\s*(\d{1,2})\s+((?:[א-ד]')|נפסלה)")

# Option start (beginning of line, letter + optional space + period)
OPTION_START_RE = re.compile(r"^([אבגד])\s*\.", re.MULTILINE)

# Option split (same, but for splitting the options block)
OPTION_SPLIT_RE = re.compile(r"(?m)^([אבגד])\s*\.\s*", re.UNICODE)

# Space-bounded גד → potential missing נ  (after uf8ff normalization)
GAD_RE = re.compile(r'(?<!\w)גד(?!\w)', re.UNICODE)


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class NormRecord:
    """One documented normalization change (for normalization_report.json)."""
    question_number: int   # 0 = pre-split (whole-text change), 1-40 = per question
    field: str             # "text" | "body" | "option_א" | "option_ב" | ... | "reference"
    before: str            # representative sample or count description
    after: str             # what it became
    rule: str              # short rule identifier
    reason: str            # human-readable explanation in Hebrew/English


@dataclass
class ParsedQuestion:
    number:  int
    body:    str
    options: dict          # {"א": "...", "ב": "...", "ג": "...", "ד": "..."}
    flags:   list = field(default_factory=list)


@dataclass
class ParsedAnswer:
    number:    int
    correct:   str         # "א" / "ב" / "ג" / "ד" / "נפסלה"
    reference: str
    flags:     list = field(default_factory=list)


@dataclass
class QAReport:
    exam_date:          str
    part:               str
    questions_count:    int  = 0
    answers_count:      int  = 0
    missing_questions:  list = field(default_factory=list)
    missing_answers:    list = field(default_factory=list)
    duplicate_q_ids:    list = field(default_factory=list)
    invalid_options:    list = field(default_factory=list)
    hard_failures:      list = field(default_factory=list)
    manual_review:      list = field(default_factory=list)
    warnings:           list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.hard_failures) == 0


# ═══════════════════════════════════════════════════════════════════════════════
#  LAYER 1 — raw text extraction
# ═══════════════════════════════════════════════════════════════════════════════

def extract_raw_text_questions(pdf_path: Path) -> str:
    """
    חילוץ טקסט מקובץ השאלות.
    קובץ PDF זה משתמש ב-XObject Form משותף — כל הדפים זהים.
    מחלצים רק את דף 0.
    """
    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    textpage = page.get_textpage()
    raw = textpage.get_text_range()
    doc.close()
    return raw


def extract_raw_text_answers(pdf_path: Path) -> str:
    """
    חילוץ טקסט מקובץ התשובות.
    הדפים אינם זהים — דף 0: שאלות 1-25, דף 1: שאלות 26-40.
    מחלצים את כל הדפים ומשרשרים.
    """
    doc = pdfium.PdfDocument(str(pdf_path))
    pages_text = []
    for i in range(len(doc)):
        page = doc[i]
        textpage = page.get_textpage()
        pages_text.append(textpage.get_text_range())
    doc.close()
    return "\n".join(pages_text)


# ═══════════════════════════════════════════════════════════════════════════════
#  LAYER 2 — text-level normalization
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_questions_text(raw: str, norm_log: list, part_name: str) -> str:
    """
    ניקוי ברמת הטקסט (לפני פיצול לשאלות):

    1. ניקוי סיומות שורה
    2. NBSP (U+00A0) → רווח רגיל
       [נדרש לפני הסרת headers — ה-header מכיל NBSP בין מילים]
    3. Soft hyphen (U+00AD) → הסרה
       [מופיע כמקף-מפריד ב-header בלבד]
    4. הסרת שורות header — בדיקת substring (לא regex!)
       שורה שמכילה גם את שם החלק וגם '00:00' → header → מוסרת
    5. חיתוך רווחים בסוף שורה

    מה שלא נעשה כאן:
    - U+F8FF → נ  (נעשה per-field ב-Layer 3, כדי לתעד per שאלה)
    - שום תיקון תוכן
    """
    text = raw.replace('\r\n', '\n').replace('\r', '\n')

    # ── 2. NBSP → space ──────────────────────────────────────────────────────
    nbsp_count = text.count(NBSP)
    if nbsp_count > 0:
        text = text.replace(NBSP, ' ')
        norm_log.append(NormRecord(
            question_number=0,
            field="text",
            before=f"[{nbsp_count} occurrences of U+00A0 NBSP throughout questions text]",
            after="[replaced with regular space U+0020]",
            rule="nbsp→space",
            reason=(
                "NBSP (U+00A0) מופיע ב-running page headers — למשל: 'חלק\\xa0ב\\xa0\\xad\\xa0דין\\xa0דיוני'."
                " הסרת NBSP נדרשת לפני זיהוי ה-headers כי regex רגיל עם \\s לא מזהה NBSP."
                " ההחלפה בטוחה: NBSP לא משנה משמעות משפטית."
            )
        ))

    # ── 3. Soft hyphen → remove ───────────────────────────────────────────────
    shyp_count = text.count(SOFT_HYPHEN)
    if shyp_count > 0:
        text = text.replace(SOFT_HYPHEN, '')
        norm_log.append(NormRecord(
            question_number=0,
            field="text",
            before=f"[{shyp_count} occurrences of U+00AD soft-hyphen throughout questions text]",
            after="[removed entirely]",
            rule="soft-hyphen→remove",
            reason=(
                "Soft hyphen (U+00AD) משמש כמקף-מפריד ב-running page header בלבד"
                " ('חלק ב \\xad דין דיוני ...'). אינו מופיע בטקסט השאלות."
                " הוסר לחלוטין."
            )
        ))

    # ── 4. Remove running page headers ───────────────────────────────────────
    lines = text.splitlines()
    cleaned = []
    headers_removed = 0
    removed_examples = []

    for line in lines:
        # בדיקת COMBINATION: שתי מחרוזות חייבות להופיע ביחד
        # '00:00' לא מופיע לעולם בטקסט שאלות → בטוח לשימוש כ-sentinel
        if part_name in line and HEADER_MARKER_B in line:
            headers_removed += 1
            if len(removed_examples) < 3:
                removed_examples.append(repr(line[:80]))
            continue
        cleaned.append(line.rstrip())

    if headers_removed > 0:
        norm_log.append(NormRecord(
            question_number=0,
            field="text",
            before=f"[{headers_removed} running page header line(s) removed. Examples: {removed_examples}]",
            after="[lines removed from text]",
            rule="header-removal",
            reason=(
                f"שורות header (המכילות '{part_name}' ו-'{HEADER_MARKER_B}') הוסרו."
                " זיהוי על-פי substring combination — לא regex — כדי להתמודד עם NBSP, soft-hyphen וריווחים לא-תקניים."
                f" {headers_removed} שורה/ות הוסרו."
            )
        ))

    return '\n'.join(cleaned)


def normalize_answers_text(raw: str, norm_log: list) -> str:
    """
    ניקוי ברמת הטקסט לקובץ התשובות:

    1. ניקוי סיומות שורה
    2. ð (U+00F0, Latin eth) → נ (U+05E0, Hebrew nun)
       [שגיאת font-encoding ספציפית לקובץ PDF זה]
    3. NBSP → רווח רגיל
    4. Soft hyphen → הסרה
    5. חיתוך רווחים בסוף שורה
    """
    text = raw.replace('\r\n', '\n').replace('\r', '\n')

    # ── ð → נ ────────────────────────────────────────────────────────────────
    eth_count = text.count('ð')
    if eth_count > 0:
        text = text.replace('ð', 'נ')
        norm_log.append(NormRecord(
            question_number=0,
            field="reference",
            before=f"[{eth_count} occurrences of ð (U+00F0 Latin eth) in answers text]",
            after="[replaced with נ (U+05E0 Hebrew nun)]",
            rule="ð→נ",
            reason=(
                "ð (Latin lowercase eth, U+00F0) מופיע כ-artifact של font-encoding בקובץ התשובות."
                " הוא מייצג באופן עקבי את האות הנ (nun) עברית, בשל font mapping מותאם-אישית."
                " Latin eth אינו מופיע בטקסט משפטי עברי — ההחלפה בטוחה ב-100%."
            )
        ))

    # ── NBSP → space ──────────────────────────────────────────────────────────
    nbsp_count = text.count(NBSP)
    if nbsp_count > 0:
        text = text.replace(NBSP, ' ')
        norm_log.append(NormRecord(
            question_number=0,
            field="reference",
            before=f"[{nbsp_count} occurrences of U+00A0 NBSP in answers text]",
            after="[replaced with regular space]",
            rule="nbsp→space",
            reason="NBSP בקובץ התשובות הוחלף ברווח רגיל לאחידות."
        ))

    # ── Soft hyphen → remove ──────────────────────────────────────────────────
    shyp_count = text.count(SOFT_HYPHEN)
    if shyp_count > 0:
        text = text.replace(SOFT_HYPHEN, '')
        norm_log.append(NormRecord(
            question_number=0,
            field="reference",
            before=f"[{shyp_count} occurrences of U+00AD soft-hyphen in answers text]",
            after="[removed]",
            rule="soft-hyphen→remove",
            reason="Soft hyphen הוסר מקובץ התשובות."
        ))

    lines = text.splitlines()
    cleaned = [line.rstrip() for line in lines]
    return '\n'.join(cleaned)


# ═══════════════════════════════════════════════════════════════════════════════
#  PER-FIELD NORMALIZATION (called from Layer 3, per question per field)
# ═══════════════════════════════════════════════════════════════════════════════

def apply_field_normalization(
    q_num: int,
    field_name: str,
    text: str,
    norm_log: list,
) -> str:
    """
    Normalization ברמת שדה בודד (body / option_א / option_ב / ...):

    כלל 1: U+F8FF → נ
    כלל 2: אחרי כלל 1 — space-bounded 'גד' → 'נגד'
            (רק אם ב-word boundary — לא שם פרטי)
    """
    # ── כלל 1: U+F8FF → נ ────────────────────────────────────────────────────
    if UFFF_CHAR in text:
        count = text.count(UFFF_CHAR)

        # דוגמאות להמחשה (עד 5)
        examples = []
        for m in re.finditer(re.escape(UFFF_CHAR), text):
            s = max(0, m.start() - 4)
            e = min(len(text), m.end() + 4)
            ctx_before = repr(text[s:e])
            fixed = text[s:m.start()] + 'נ' + text[m.end():e]
            ctx_after = repr(fixed)
            examples.append(f"{ctx_before} → {ctx_after}")
            if len(examples) >= 5:
                break

        new_text = text.replace(UFFF_CHAR, 'נ')

        norm_log.append(NormRecord(
            question_number=q_num,
            field=field_name,
            before=f"[{count} occurrence(s) of U+F8FF. Examples: {examples}]",
            after="[replaced with נ (U+05E0)]",
            rule="uf8ff→נ",
            reason=(
                f"U+F8FF (Apple Private Use Area) מייצג את האות נ (nun) עברית"
                f" באמצעות font mapping פרטי בקובץ PDF זה."
                f" מופיע {count} פעמים בשדה '{field_name}' של שאלה {q_num}."
                " הוחלף ב-U+05E0 (Hebrew nun)."
            )
        ))
        text = new_text

    # ── כלל 2: space-bounded 'גד' → 'נגד' ────────────────────────────────────
    # מופעל רק אחרי כלל 1 (רוב המקרים כבר תוקנו ע"י כלל 1)
    gad_matches = GAD_RE.findall(text)
    if gad_matches:
        new_text = GAD_RE.sub('נגד', text)
        norm_log.append(NormRecord(
            question_number=q_num,
            field=field_name,
            before=repr(text[:100]),
            after=repr(new_text[:100]),
            rule="גד→נגד",
            reason=(
                f"'גד' עצמאי (word-boundary) הוחלף ב-'נגד' ב-{len(gad_matches)} מקום/מקומות."
                " מתרחש לאחר כלל uf8ff→נ כאשר הרצף היה \\uf8ffגד."
                " ✔ manual review מומלץ: 'גד' הוא גם שם פרטי תקין."
            )
        ))
        text = new_text

    return text


# ═══════════════════════════════════════════════════════════════════════════════
#  HEADER ARTIFACT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def check_header_artifacts(
    q_num: int,
    field_name: str,
    text: str,
    qa: QAReport,
    part_name: str,
    part_hebrew: str,
):
    """
    Hard-fail אם שדה מכיל שרידי header.
    בדיקה על COMBINATION — לא על מילה בודדת.

    הסבר:
    - Q24 מכיל 'חלק ב' בטקסט החוקי הלגיטימי → לא מספיק לבדוק מילה בודדת
    - '00:00' לעולם לא מופיע בשאלה → בדיקה בטוחה
    - שם החלק + '00:00' = combination חד-משמעית של header, ללא תלות בתאריך המועד
    """
    combos = [
        (part_name, HEADER_MARKER_B),
        (part_hebrew, HEADER_MARKER_B),
    ]
    if HEADER_MARKER_B in text:
        qa.hard_failures.append(
            f"HARD-FAIL: Q{q_num} שדה '{field_name}' מכיל header artifact: "
            f"'{HEADER_MARKER_B}' — הסרת ה-header נכשלה לשאלה זו. נדרש תיקון ידני."
        )
        return
    for c0, c1 in combos:
        if c0 in text and c1 in text:
            qa.hard_failures.append(
                f"HARD-FAIL: Q{q_num} שדה '{field_name}' מכיל header artifact: "
                f"'{c0}' + '{c1}' — הסרת ה-header נכשלה לשאלה זו. נדרש תיקון ידני."
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  LAYER 3 — question extraction
# ═══════════════════════════════════════════════════════════════════════════════

def find_questions_section_start(lines: list) -> int:
    """מוצא את אינדקס השורה הראשונה של השאלות (אחרי הוראות)."""
    last_hatzlacha = -1
    for i, line in enumerate(lines):
        if re.search(r'ב\s*ה\s*צ\s*ל\s*ח\s*ה', line):
            last_hatzlacha = i

    if last_hatzlacha == -1:
        raise ValueError(
            "HARD-FAIL: לא נמצאה שורת 'ב ה צ ל ח ה' — "
            "לא ניתן לקבוע היכן מסתיימות ההוראות ומתחילות השאלות."
        )

    for i in range(last_hatzlacha + 1, len(lines)):
        if re.match(r'^\s*\.1\s*\S', lines[i]):
            return i

    raise ValueError(
        "HARD-FAIL: נמצאה 'ב ה צ ל ח ה' אך לא נמצא סמן '.1' אחריה."
    )


def split_question_blocks(questions_text: str) -> list:
    """
    מפצל את חלק השאלות ל-tuples של (מספר_שאלה, טקסט_הבלוק).
    מטפל גם ב-'.13 טקסט' וגם ב-'.13טקסט' (ללא רווח).
    """
    marker_re = re.compile(r"(?m)^\.(\d{1,2})(?!\d)(?=\s*\S)", re.UNICODE)
    candidates = list(marker_re.finditer(questions_text))
    matches = []
    expected_next = 1
    for candidate in candidates:
        q_num = int(candidate.group(1))
        if q_num == expected_next:
            matches.append(candidate)
            expected_next += 1
            if expected_next > EXPECTED_Q:
                break
    if not matches:
        raise ValueError("HARD-FAIL: לא נמצאו סמני שאלות בחלק השאלות.")

    blocks = []
    for i, m in enumerate(matches):
        q_num = int(m.group(1))
        start = m.start()
        end   = matches[i + 1].start() if i + 1 < len(matches) else len(questions_text)
        block_text = questions_text[start:end].strip()
        blocks.append((q_num, block_text))

    return sorted(blocks, key=lambda x: x[0])


def parse_question_block(
    q_num:    int,
    block_text: str,
    qa:       QAReport,
    norm_log: list,
    part_name: str,
    part_hebrew: str,
) -> Optional[ParsedQuestion]:
    """
    מנתח בלוק שאלה אחד: body + options.
    מפעיל per-field normalization ובדיקת header artifacts.
    """
    flags = []

    # הסרת קידומת .N
    block_text = re.sub(r"^\.\d{1,2}\s*", "", block_text).strip()

    # מציאת תחילת אפשרויות התשובה
    first_option_match = OPTION_START_RE.search(block_text)
    if not first_option_match:
        qa.hard_failures.append(f"Q{q_num}: לא נמצאו אפשרויות תשובה בבלוק")
        return None

    raw_body     = block_text[:first_option_match.start()].strip()
    options_text = block_text[first_option_match.start():]

    if not raw_body:
        qa.hard_failures.append(f"Q{q_num}: body ריק")
        return None

    # Normalization של body
    body = apply_field_normalization(q_num, "body", raw_body, norm_log)

    # ולידציה של body
    if len(body) < 20:
        flags.append(f"short body ({len(body)} chars)")
        qa.manual_review.append(f"Q{q_num}: body קצר חשוד: {body!r}")

    # בדיקת header artifacts ב-body
    check_header_artifacts(q_num, "body", body, qa, part_name, part_hebrew)

    # פיצול ו-normalization של אפשרויות
    parts = OPTION_SPLIT_RE.split(options_text)
    options = {}
    if len(parts) >= 2:
        i = 1
        while i + 1 <= len(parts) - 1:
            letter = parts[i].strip()
            text   = parts[i + 1].strip()
            if letter in OPTION_LETTERS:
                # Normalization per option
                text = apply_field_normalization(q_num, f"option_{letter}", text, norm_log)
                # בדיקת header artifacts
                check_header_artifacts(q_num, f"option_{letter}", text, qa, part_name, part_hebrew)
                options[letter] = text
            i += 2

    # ולידציה: כל 4 האפשרויות חייבות להיות קיימות ולא ריקות
    for letter in OPTION_LETTERS:
        if letter not in options:
            qa.hard_failures.append(f"Q{q_num}: אפשרות '{letter}' חסרה")
            return None
        if not options[letter]:
            qa.hard_failures.append(f"Q{q_num}: אפשרות '{letter}' ריקה")
            return None
        if len(options[letter]) < 3:
            flags.append(f"short option {letter}")
            qa.manual_review.append(
                f"Q{q_num}: אפשרות '{letter}' קצרה חשוד: {options[letter]!r}"
            )

    return ParsedQuestion(number=q_num, body=body, options=options, flags=flags)


def extract_questions(
    norm_q_text: str,
    qa:          QAReport,
    norm_log:    list,
    part_name:   str,
    part_hebrew: str,
) -> list:
    """Layer 3 entry point — מקבל טקסט מנורמל (אחרי Layer 2)."""
    lines = norm_q_text.splitlines()
    try:
        q_start_idx = find_questions_section_start(lines)
    except ValueError as e:
        qa.hard_failures.append(str(e))
        return []

    questions_section = '\n'.join(lines[q_start_idx:])

    try:
        blocks = split_question_blocks(questions_section)
    except ValueError as e:
        qa.hard_failures.append(str(e))
        return []

    # בדיקת מספרי שאלות כפולים
    seen_nums = {}
    for q_num, _ in blocks:
        if q_num in seen_nums:
            qa.hard_failures.append(f"מספר שאלה כפול: {q_num}")
        seen_nums[q_num] = True

    questions = []
    for q_num, block_text in blocks:
        if q_num < 1 or q_num > 40:
            qa.warnings.append(f"מספר שאלה {q_num} מחוץ לטווח 1-40 — מדולג")
            continue
        q = parse_question_block(q_num, block_text, qa, norm_log, part_name, part_hebrew)
        if q is not None:
            questions.append(q)

    qa.questions_count = len(questions)
    return questions


# ═══════════════════════════════════════════════════════════════════════════════
#  LAYER 4 — answer extraction
# ═══════════════════════════════════════════════════════════════════════════════

def extract_answers(norm_a_text: str, qa: QAReport, norm_log: list) -> dict:
    """
    Layer 4 — מקבל טקסט מנורמל (אחרי Layer 2).

    הטבלה דו-עמודית ב-RTL מחולצת linearly ויוצרת שני patterns:

    Pattern A — סמן בתחילת שורה (סימוכין קצרים):
        .1 ג'
        סעיף 23א לפקודת...

    Pattern B — סמן בסוף שורה (סימוכין ארוכים שנמזגו):
        סעיפים ,26 64 לחוק בתי המשפט..., התשמ"ד- .10 ב'
         1984

    אלגוריתם:
    1. מצא את כל סמני התשובות
    2. לכל סמן: pre_line = טקסט באותה שורה לפני הסמן (Pattern B)
                 post_text = טקסט אחרי הסמן עד לשורת הסמן הבא (Pattern A)
    3. reference = clean(pre_line + post_text)
    """
    markers = list(A_MARKER_RE.finditer(norm_a_text))

    if len(markers) == 0:
        qa.hard_failures.append("HARD-FAIL: לא נמצאו סמני תשובות בקובץ התשובות")
        return {}

    answers = {}
    for i, m in enumerate(markers):
        q_num        = int(m.group(1))
        answer       = m.group(2).replace("'", "")
        marker_start = m.start()
        marker_end   = m.end()

        # pre_line (Pattern B)
        line_start = norm_a_text.rfind('\n', 0, marker_start)
        line_start = line_start + 1 if line_start != -1 else 0
        pre_line   = norm_a_text[line_start:marker_start].strip()

        # post_text עד לשורת הסמן הבא (Pattern A)
        if i + 1 < len(markers):
            next_marker_start = markers[i + 1].start()
            next_line_start   = norm_a_text.rfind('\n', 0, next_marker_start)
            next_line_start   = next_line_start + 1 if next_line_start != -1 else 0
            post_text = norm_a_text[marker_end:next_line_start].strip()
        else:
            post_text = norm_a_text[marker_end:].strip()

        # שיחזור reference
        ref_parts = []
        if pre_line:
            ref_parts.append(pre_line)
        if post_text:
            ref_parts.append(post_text)
        reference = _clean_reference(' '.join(ref_parts))

        # ולידציה
        if answer not in VALID_ANSWERS and answer != DISQUALIFIED_ANSWER:
            qa.hard_failures.append(f"A{q_num}: תשובה '{answer}' אינה אחת מ-א/ב/ג/ד/נפסלה")
            continue

        if not reference:
            qa.manual_review.append(f"A{q_num}: סימוכין ריקים — לבדוק ב-PDF המקורי")
        elif len(reference) < 10:
            qa.manual_review.append(
                f"A{q_num}: סימוכין קצרים חשוד ({len(reference)} תווים): {reference!r}"
            )

        if q_num in answers:
            qa.hard_failures.append(f"ערך תשובה כפול לשאלה {q_num}")
            continue

        answers[q_num] = ParsedAnswer(number=q_num, correct=answer, reference=reference)

    qa.answers_count = len(answers)
    return answers


def _clean_reference(text: str) -> str:
    """ניקוי מחרוזת סימוכין — collapse whitespace, הסרת artifacts של מספרי עמודים."""
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'^\s*\d{6,8}\s*', '', text)
    text = re.sub(r'^\s*\d+/\d+\s*', '', text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  LAYER 5 — merge, validate, JSON output
# ═══════════════════════════════════════════════════════════════════════════════

def merge_and_validate(
    questions:  list,
    answers:    dict,
    qa:         QAReport,
    exam_date:  str,
    part:       str,
) -> list:
    """מיזוג שאלות ותשובות + כל ולידציות hard-fail."""

    q_by_num = {q.number: q for q in questions}
    q_nums   = set(q_by_num.keys())
    a_nums   = set(answers.keys())

    # בדיקות כמות
    if len(questions) != EXPECTED_Q:
        qa.hard_failures.append(f"צפוי {EXPECTED_Q} שאלות, נמצאו {len(questions)}")
    if len(answers) != EXPECTED_Q:
        qa.hard_failures.append(f"צפוי {EXPECTED_Q} תשובות, נמצאו {len(answers)}")

    # שאלות/תשובות חסרות
    for n in sorted(a_nums - q_nums):
        qa.hard_failures.append(f"קיימת תשובה לשאלה {n} אך אין שאלה מתאימה")
        qa.missing_questions.append(n)
    for n in sorted(q_nums - a_nums):
        qa.hard_failures.append(f"שאלה {n} ללא תשובה בקובץ התשובות")
        qa.missing_answers.append(n)

    # רציפות מספרים
    all_nums       = sorted(q_nums | a_nums)
    expected_range = list(range(1, EXPECTED_Q + 1))
    if all_nums != expected_range:
        gaps = [n for n in expected_range if n not in (q_nums & a_nums)]
        qa.hard_failures.append(f"מספרי שאלות לא רציפים. חסרים/עודפים: {gaps}")

    if not qa.passed:
        return []

    # בניית output
    output = []
    for num in range(1, EXPECTED_Q + 1):
        q = q_by_num[num]
        a = answers[num]

        if a.correct == DISQUALIFIED_ANSWER:
            pass
        elif a.correct not in VALID_ANSWERS:
            qa.hard_failures.append(f"Q{num}: תשובה נכונה '{a.correct}' לא חוקית")
            continue

        if a.correct != DISQUALIFIED_ANSWER and a.correct not in q.options:
            qa.hard_failures.append(
                f"Q{num}: תשובה נכונה '{a.correct}' לא מופיעה באפשרויות {list(q.options.keys())}"
            )
            continue

        if not a.reference:
            qa.hard_failures.append(f"Q{num}: סימוכין ריקים")
            continue

        stable_id = f"{exam_date}_{part}_{num:03d}"
        is_invalidated = a.correct == DISQUALIFIED_ANSWER

        output.append({
            "stable_id":      stable_id,
            "number":         num,
            "status":         "invalidated" if is_invalidated else "active",
            "body":           q.body,
            "options": {
                "א": q.options["א"],
                "ב": q.options["ב"],
                "ג": q.options["ג"],
                "ד": q.options["ד"],
            },
            "correct_answer": None if is_invalidated else a.correct,
            "reference":      a.reference,
            "invalidation_note": (
                "השאלה נפסלה לפי מפתח התשובות הרשמי"
                if is_invalidated else None
            ),
            "_flags":         q.flags + a.flags,   # dev only — לא נכנס ל-DB
        })

    return output


def build_json_output(
    questions_data: list,
    exam_date:      str,
    exam_label:     str,
    part:           str,
    part_name:      str,
) -> dict:
    return {
        "exam_date": exam_date,
        "label":     exam_label,
        "part":      part,
        "part_name": part_name,
        "questions": [
            {k: v for k, v in q.items() if k != "_flags"}
            for q in questions_data
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def run_pipeline(args):
    exam_date  = args.exam_date
    exam_label = args.label
    part       = args.part.upper()
    part_name  = args.part_name
    part_hebrew = PART_HEBREW.get(part, f"חלק {part}")
    q_pdf      = args.questions_pdf
    a_pdf      = args.answers_pdf
    out_dir    = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = out_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{exam_date}_{part}"
    qa       = QAReport(exam_date=exam_date, part=part)
    norm_log = []   # list[NormRecord]

    print("=" * 60)
    print("Bar Exam PDF Pipeline  v2")
    print(f"Exam: {exam_label} | Part: {part} ({part_name})")
    print("=" * 60)

    # ── Layer 1: extract raw text ──────────────────────────────────────────────
    print("\n[Layer 1] Extracting raw text...")

    if not q_pdf.exists():
        print(f"  ❌ Questions PDF not found: {q_pdf}")
        sys.exit(1)
    if not a_pdf.exists():
        print(f"  ❌ Answers PDF not found: {a_pdf}")
        sys.exit(1)

    raw_q = extract_raw_text_questions(q_pdf)
    raw_a = extract_raw_text_answers(a_pdf)

    (debug_dir / f"raw_questions_{prefix}.txt").write_text(raw_q, encoding="utf-8")
    (debug_dir / f"raw_answers_{prefix}.txt").write_text(raw_a, encoding="utf-8")
    print(f"  Questions raw: {len(raw_q):,} chars")
    print(f"  Answers raw:   {len(raw_a):,} chars")

    # ── Layer 2: text-level normalization ─────────────────────────────────────
    print("\n[Layer 2] Normalizing text...")

    norm_q = normalize_questions_text(raw_q, norm_log, part_name)
    norm_a = normalize_answers_text(raw_a, norm_log)

    (debug_dir / f"normalized_questions_{prefix}.txt").write_text(norm_q, encoding="utf-8")
    (debug_dir / f"normalized_answers_{prefix}.txt").write_text(norm_a, encoding="utf-8")
    print(f"  Normalized questions: {len(norm_q):,} chars")
    print(f"  Normalized answers:   {len(norm_a):,} chars")

    # ── Layer 3: question extraction + per-field normalization ─────────────────
    print("\n[Layer 3] Extracting questions...")
    questions = extract_questions(norm_q, qa, norm_log, part_name, part_hebrew)
    print(f"  Found: {len(questions)} questions")

    # ── Layer 4: answer extraction ─────────────────────────────────────────────
    print("\n[Layer 4] Extracting answers...")
    answers = extract_answers(norm_a, qa, norm_log)
    print(f"  Found: {len(answers)} answers")

    # ── Layer 5: merge + validate ──────────────────────────────────────────────
    print("\n[Layer 5] Merging and validating...")
    merged = merge_and_validate(questions, answers, qa, exam_date, part)

    # ── Normalization report ───────────────────────────────────────────────────
    norm_report = {
        "exam_date":     exam_date,
        "part":          part,
        "total_changes": len(norm_log),
        "records":       [asdict(r) for r in norm_log],
    }
    norm_report_path = out_dir / f"normalization_report_{prefix}.json"
    norm_report_path.write_text(
        json.dumps(norm_report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # ── QA report ─────────────────────────────────────────────────────────────
    qa_path = out_dir / f"qa_report_{prefix}.json"
    qa_path.write_text(
        json.dumps(asdict(qa), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("QA REPORT")
    print("=" * 60)
    print(f"  Questions found:         {qa.questions_count}")
    print(f"  Answers found:           {qa.answers_count}")
    print(f"  Normalization changes:   {len(norm_log)}")
    print(f"  Hard failures:           {len(qa.hard_failures)}")
    print(f"  Manual review items:     {len(qa.manual_review)}")
    print(f"  Warnings:                {len(qa.warnings)}")

    if qa.hard_failures:
        print("\n  ❌ HARD FAILURES:")
        for f in qa.hard_failures:
            print(f"     • {f}")

    if qa.manual_review:
        print("\n  ⚠  MANUAL REVIEW REQUIRED:")
        for item in qa.manual_review:
            print(f"     • {item}")

    if qa.warnings:
        print("\n  ℹ  WARNINGS:")
        for w in qa.warnings:
            print(f"     • {w}")

    if not qa.passed:
        print("\n  ❌ PIPELINE FAILED — JSON לא נכתב")
        print(f"     QA report:           {qa_path}")
        print(f"     Normalization report:{norm_report_path}")
        return False

    # ── Write JSON ─────────────────────────────────────────────────────────────
    output     = build_json_output(merged, exam_date, exam_label, part, part_name)
    json_path  = out_dir / f"{prefix}_questions.json"
    dev_path   = debug_dir / f"{prefix}_questions_dev.json"

    json_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    dev_output = {**output, "questions": merged}
    dev_path.write_text(
        json.dumps(dev_output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n  ✅ SUCCESS — {len(merged)} שאלות נכתבו")
    print(f"     JSON:                {json_path}")
    print(f"     Dev JSON (+ flags):  {dev_path}")
    print(f"     QA report:           {qa_path}")
    print(f"     Normalization report:{norm_report_path}")
    return True


if __name__ == "__main__":
    args = parse_args()
    ok = run_pipeline(args)
    sys.exit(0 if ok else 1)
