import pathlib


def test_no_db_query_in_new_modules():
    root = pathlib.Path(__file__).resolve().parents[2] / "app"
    new_files = []
    for name in (
        "models/user.py",
        "models/practice_session.py",
        "models/practice_session_question.py",
        "models/user_answer.py",
        "models/bookmarked_question.py",
        "repositories/user_repository.py",
        "repositories/practice_session_repository.py",
        "repositories/answer_repository.py",
        "repositories/bookmark_repository.py",
        "services/user_service.py",
        "auth/security.py",
        "auth/dependencies.py",
        "auth/services/auth_service.py",
        "auth/api/routes.py",
        "services/practice_session_service.py",
        "services/answer_service.py",
        "routers/users.py",
        "routers/practice_sessions.py",
        "schemas/user.py",
        "schemas/session.py",
        "schemas/answer.py",
    ):
        new_files.append(root / name)
    for path in new_files:
        text = path.read_text(encoding="utf-8")
        assert ".query(" not in text, f"{path} uses db.query()"
