# CLAUDE.md
## Project Overview
This project is a Hebrew RTL PWA / Web Mobile First application for practicing past Israeli Bar Association qualification exams.
The app is intended for multiple examinees preparing for the Israeli Bar exam.
The app includes only:
- Part B — דין דיוני
- Part C — דין מהותי
Each full exam simulation contains:
- 40 questions from Part B
- 40 questions from Part C
- 80 questions total
The app uses official past exam PDFs as the source of truth.
Current phase:
- Product specification
- MVP planning
- Data modeling
- JSON import design
- PDF extraction validation
- Architecture planning
Do not jump to implementation unless explicitly requested.
---
## Core Product Principle
This app does not teach law.
It helps users practice the real exam format using original past questions.
The system must preserve the original exam content exactly.
---
## Hard Rules
These rules are mandatory.
Do not:
- Rewrite questions
- Fix Hebrew wording
- Change answer order
- Normalize legal phrasing
- Add explanations
- Generate AI legal explanations
- Infer missing answers
- Override the official answer key
- Silently fix source inconsistencies
- Merge questions across exams
- Use internal database IDs as business identifiers
If source data looks wrong, fail validation or mark it for manual review.
---
## Source Data
The source data comes from PDF files published by the Israeli Bar Association.
Available exam dates:
- June 2024
- April 2025
- June 2025
- December 2025
For each exam date there are 4 files:
- Questions — Part B — דין דיוני
- Questions — Part C — דין מהותי
- Answers — Part B — דין דיוני
- Answers — Part C — דין מהותי
Total files:
- 8 question PDFs
- 8 answer PDFs
- 16 PDFs total
---
## Question Structure
Each question includes:
- Factual scenario / case description
- The actual question
- 4 answer options
- Exactly 1 correct answer
Answer labels are:
- א
- ב
- ג
- ד
---
## Answer Key Structure
Each answer file contains:
- Question number
- Correct answer
- Legal reference / סימוכין
The app may display only:
- Correct / incorrect
- Correct answer
- סימוכין
No additional legal explanation should be shown.
---
## Target Platform
- PWA
- Web
- Mobile First
- Hebrew only
- Full RTL support
Desktop support is acceptable, but the UX must be designed mobile first.
---
## Users
The app is for multiple examinees.
Authentication should be simple.
Required user fields:
- id
- name
- email
- password_hash
- created_at
Not needed in MVP:
- Roles
- Teams
- Organizations
- Admin permissions
- 2FA
- Complex security model
Users are needed because progress must sync across devices.
---
## Practice Modes
### Regular Practice
Flow:
1. Show question
2. User selects answer
3. User submits answer
4. Show correct / incorrect
5. Show correct answer
6. Show סימוכין
7. Continue to next question
### Simulation
Simulation and exam mode are the same thing.
Flow:
1. User starts full simulation
2. System loads 80 questions
3. 40 from Part B
4. 40 from Part C
5. Timer starts
6. User answers questions
7. No feedback during simulation
8. User submits simulation
9. System shows final summary
Final summary includes:
- Score
- Correct answers out of 80
- Percentage
- Part B breakdown
- Part C breakdown
- Mistake list
- Correct answer and סימוכין for each mistake
### Mistakes Practice
Users can practice questions they previously answered incorrectly.
Rules:
- Keep full mistake history
- Do not delete historical mistakes
- A question is an active mistake until answered correctly later
- Track repeated mistakes
### Specific Exam Practice
User can practice by exam date:
- June 2024
- April 2025
- June 2025
- December 2025
User can filter by:
- Part B
- Part C
- Both
### Bookmarked Questions
Users can mark questions for review.
Users can practice only bookmarked questions.
Bookmarks are independent from mistakes.
---
## MVP Screens
### Auth Screen
Required:
- Login
- Register
Optional later:
- Forgot password
### Home Screen
Show:
- Continue practice
- Start simulation
- Practice by exam date
- Practice mistakes
- Bookmarked questions
- Short statistics summary
### Practice Selection Screen
User selects:
- Exam date
- Part: B / C / both
- Mode: regular practice / simulation
### Regular Question Screen
Show:
- Exam label
- Part name
- Question number
- Original question text
- Answer options א / ב / ג / ד
- Submit button
- Bookmark button
After submit:
- Correct / incorrect
- Correct answer
- סימוכין
- Next question button
### Simulation Screen
Show:
- Timer
- Question text
- Answer options
- Question navigation
- Bookmark button
- Submit simulation button
Do not show feedback during simulation.
### Simulation Result Screen
Show:
- Final score
- Percentage
- Correct count
- Part B score
- Part C score
- Mistakes
- Correct answers
- סימוכין
### Mistakes Screen
Show:
- Active mistakes
- Repeated mistakes
- Filter by exam
- Filter by part
- Start mistakes practice
### Bookmarks Screen
Show:
- Bookmarked questions
- Filter by exam
- Filter by part
- Start bookmarked practice
### Statistics Screen
MVP only.
Show:
- Overall success rate
- Success rate by Part B
- Success rate by Part C
- Total answered questions
- Number of simulations completed
- Average time per question
- Repeated mistakes
Avoid complex charts in MVP.
---
## Stable Question ID
Every question must have a stable business identifier.
Format:
```txt
YYYY-MM_PART_QNUMBER

Examples:

2024-06_B_001
2024-06_C_040
2025-04_B_017
2025-12_C_003

Where:

* YYYY-MM = exam date
* PART = B or C
* QNUMBER = question number padded to 3 digits

Part mapping:

* B = דין דיוני
* C = דין מהותי

Do not use only database IDs for business logic.

Use stable IDs for:

* Import matching
* Debugging
* Logs
* Bookmarks
* User answers
* QA reports

⸻

Conceptual Data Model

User

Fields:

* id
* name
* email
* password_hash
* created_at

Exam

Fields:

* id
* exam_date
* year
* month
* label
* part
* part_name

Rules:

* part must be B or C
* B must map to דין דיוני
* C must map to דין מהותי

Question

Fields:

* id
* stable_id
* exam_id
* part
* question_number
* body
* option_a
* option_b
* option_c
* option_d
* created_at

MVP decision:

Use option_a, option_b, option_c, option_d directly on Question.

Do not create a separate AnswerOption table in MVP.

Reason:

* Every question has exactly 4 options
* Labels are fixed
* Queries are simpler
* Less over-engineering

AnswerKey

Fields:

* id
* question_id
* correct_answer
* reference

Rules:

* correct_answer must be one of א / ב / ג / ד
* reference is the official סימוכין text from the PDF

Session

Fields:

* id
* user_id
* mode
* exam_date
* started_at
* finished_at
* total_questions
* correct_count
* score_percent
* duration_seconds

Modes:

* regular_practice
* simulation
* mistakes
* bookmarks

UserAnswer

Fields:

* id
* user_id
* question_id
* session_id
* selected_answer
* is_correct
* answered_at
* time_spent_seconds
* mode

Rules:

* Every answer belongs to a session
* UserAnswer is immutable history
* Do not delete answers when mistake state changes

BookmarkedQuestion

Fields:

* id
* user_id
* question_id
* created_at

Rules:

* Bookmark is not a mistake
* Mistakes and bookmarks are separate concepts

⸻

JSON Import Format

The app must not parse PDFs during normal runtime.

PDFs should be converted into validated JSON first.

The app loads validated JSON into the database.

Recommended JSON format:

{
  "exam_date": "2025-04",
  "label": "אפריל 2025",
  "part": "B",
  "part_name": "דין דיוני",
  "questions": [
    {
      "stable_id": "2025-04_B_001",
      "number": 1,
      "body": "טקסט השאלה המקורי בדיוק כפי שמופיע במקור...",
      "options": {
        "א": "תשובה א כפי שמופיעה במקור",
        "ב": "תשובה ב כפי שמופיעה במקור",
        "ג": "תשובה ג כפי שמופיעה במקור",
        "ד": "תשובה ד כפי שמופיעה במקור"
      },
      "correct_answer": "ג",
      "reference": "סעיף 23א לפקודת סדר הדין הפלילי..."
    }
  ]
}

⸻

PDF Import Pipeline

PDF parsing must be separated from the runtime app.

Correct flow:

PDF
→ text extraction
→ OCR/Bidi cleanup
→ header/footer removal
→ question splitting
→ answer option splitting
→ answer key extraction
→ match by question number
→ generate JSON
→ validate JSON
→ import to DB

Do not:

* Parse PDFs in the frontend
* Parse PDFs during normal backend runtime
* Import directly from PDF into DB
* Allow partial import by default
* Build Admin PDF upload in MVP

Use an internal import pipeline or script.

⸻

Import Validation Rules

Hard-fail validation:

* Each exam part must contain exactly 40 questions
* Question numbers must be 1–40
* Question numbers must be unique per exam date and part
* Question numbers must be continuous
* Every question must have a body
* Every question must have exactly 4 options
* No option may be empty
* Correct answer must be one of א / ב / ג / ד
* Every question must have a correct answer
* Every question must have a reference
* Every answer key row must match an existing question
* Every question must match an answer key row
* stable_id must be unique globally
* stable_id must match exam_date, part, and question number
* part must be B or C
* part_name must match part

Manual-review validation:

* Suspiciously short question body
* Suspiciously short answer option
* Missing legal source markers
* Broken Hebrew text
* OCR artifacts
* Strange line breaks
* Duplicate-looking question text
* Reference that appears split incorrectly
* Repeated page headers inside question body

⸻

Import QA Report

Every import must produce a QA report.

Report fields:

* exam_date
* part
* questions_count
* answer_keys_count
* missing_questions
* missing_answers
* duplicate_ids
* invalid_options
* warnings
* manual_review_items

No silent import.

⸻

Runtime Rules

Backend is the source of truth

Backend must calculate:

* is_correct
* score
* percentage
* part breakdown
* mistake list
* simulation result

Frontend may display progress, but must not be trusted for official scoring.

Simulation feedback

In simulation mode:

* User can answer
* User can navigate
* User can bookmark
* User cannot see correct / incorrect
* User cannot see סימוכין before submission

This must be enforced by backend response design, not only by UI hiding.

Mistake tracking

Correct model:

UserAnswer = immutable history
Active mistake = derived or stored state

A question is an active mistake if the latest meaningful answer was wrong.

Repeated mistakes should be countable.

⸻

API Design Guidelines

API contracts must be explicit.

Good endpoint direction:

GET /exams
GET /questions?exam_date=2025-04&part=B
POST /sessions
GET /sessions/{id}
POST /sessions/{id}/answers
POST /sessions/{id}/submit
GET /stats/summary
GET /mistakes
GET /bookmarks

Avoid:

* Huge unrelated payloads
* Endpoints that mix unrelated concerns
* Frontend-only scoring
* Business logic hidden in UI state

⸻

Recommended Tech Stack

Frontend:

* React
* Vite
* TypeScript
* PWA
* RTL support
* Mobile First layout

Backend:

* FastAPI
* SQLAlchemy 2.0
* Pydantic
* Alembic

Database:

* PostgreSQL

Auth:

* Simple email + password

Storage:

* Validated JSON imported into DB

Do not keep the app dependent only on static JSON because users need synced progress, mistake tracking, simulations, and statistics.

⸻

Backend Architecture

Use strict layers:

API Router → Service → Repository → ORM Model

Rules:

* Router handles HTTP, auth, and input parsing
* Service owns business logic
* Repository owns DB access
* ORM models do not contain business logic
* Pydantic schemas are API contracts
* No DB queries inside routers
* No business rules inside repositories
* Import and validation logic must be isolated from runtime app logic

Avoid:

* God services
* Cross-domain repository calls
* Business logic in routers
* Raw SQL unless justified
* Over-engineered abstractions
* Premature generic systems

⸻

SQLAlchemy Rules

Use SQLAlchemy 2.0 style.

Prefer:

select(...)
session.scalars(...)
session.execute(...)

Avoid:

db.query(...)

⸻

Frontend Rules

RTL and Hebrew are core requirements.

Do not treat RTL as polish.

Rules:

* Use dir="rtl"
* Hebrew labels only
* Mobile-first layout
* Long legal text must be readable
* Answer options must align correctly
* Avoid LTR assumptions in components
* Avoid broken punctuation layout

This is a reading app, not a dashboard.

Question UI must support:

* Long text
* Multi-paragraph content
* Comfortable line height
* Clear answer area
* Large enough tap targets
* No dense cards
* No tiny text

⸻

Testing Priorities

High-value tests:

* PDF/import validation
* Question splitting
* Answer key matching
* stable_id generation
* JSON schema validation
* Simulation scoring
* No feedback before simulation submit
* Mistake active/inactive behavior
* Bookmark toggle behavior
* Stats calculation

Do not prioritize snapshot/UI tests before data correctness is stable.

⸻

Out of Scope for MVP

Do not build these in MVP:

* AI explanations
* Generated legal reasoning
* Admin dashboard
* PDF upload UI
* Payments
* Native mobile app
* Teams
* Organizations
* Roles
* Complex permissions
* Question topic classification
* CMS
* Advanced charts
* Social features
* Leaderboards

Every extra feature must justify itself against the MVP.

⸻

Development Style

When working on this project:

* Be concise
* Be critical
* Avoid fluff
* Avoid over-engineering
* Prefer simple maintainable solutions
* Prefer boring explicit code
* Preserve legal source data exactly
* Treat PDF import accuracy as the highest-risk area
* Prefer clear naming over clever abstractions
* Do not add features unless they directly serve the MVP

Avoid:

* Dynamic magic
* Premature plugin systems
* Over-flexible schemas
* Deeply nested state
* Generic frameworks too early

⸻

Product Decisions Already Made

* Hebrew only
* RTL only
* PWA / Web Mobile First
* Users are required
* Auth is simple
* No complex permissions
* No AI explanations
* No legal commentary beyond official סימוכין
* Simulation and exam mode are unified
* Questions preserve source wording
* Answers preserve source wording
* Correct answers come only from answer PDFs
* PDF import is internal, not user-facing
* JSON must be validated before DB import
* Stable question IDs are required
* Backend is source of truth for scoring

⸻
