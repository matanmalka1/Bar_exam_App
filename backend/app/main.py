from fastapi import FastAPI

from app.routers.questions import router as questions_router


app = FastAPI(title="Bar Exam API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(questions_router, prefix="/api/v1")
