from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import get_db
from app.core.llm import check_llm_health

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health(db: Session = Depends(get_db)):
    """Basic health check — verifies backend and database connectivity."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
        "service": "it-company-backend",
    }


@router.get("/llm")
def llm_health():
    """Check if the configured LLM (Ollama) is reachable and the model is available."""
    result = check_llm_health()
    return result
