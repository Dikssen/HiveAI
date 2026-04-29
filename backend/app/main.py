from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chats import router as chats_router
from app.api.tasks import router as tasks_router
from app.api.agent_runs import router as agent_runs_router
from app.api.health import router as health_router

app = FastAPI(
    title="HiveAI",
    description="Multi-agent AI operations platform. Powered by LangGraph + Ollama.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chats_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(agent_runs_router, prefix="/api")
app.include_router(health_router, prefix="/api")


@app.get("/")
def root():
    return {"message": "HiveAI", "docs": "/docs"}
