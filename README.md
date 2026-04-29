# HiveAI

An AI-powered operations platform for IT companies. Business users describe tasks in natural language — a multi-agent system handles the execution across your internal tools and systems.

**Current integrations:** Confluence  
**Planned:** OpenStack · Fleio · Jira · Analytics

---

## How it works

```
User writes a task in chat
        ↓
ChiefOrchestrator (LangGraph) analyzes and builds an execution plan
        ↓
Specialized agents run in parallel or sequentially via Celery workers
        ↓
Each agent uses tools to interact with real systems (Confluence, etc.)
        ↓
Results are synthesized and returned to the user
```

**Example flow:**
> *"Write technical documentation for the SSH key sync module and place it under the Backend section in Confluence"*
1. Orchestrator assigns the task to `BackendDeveloperAgent`
2. Agent calls `ConfluenceGetSpaceRoot` → navigates to the correct parent page
3. Agent calls `ConfluenceCreatePage` with structured content
4. Final answer includes the Confluence page URL

---

## Architecture

```
Browser
  │
  ▼
FastAPI (backend :8000)
  │  REST API + polling
  ▼
Celery Task  ──────────────────────────────────────
  │                                               │
  ▼                                               ▼
LangGraph Orchestrator                      PostgreSQL
  │  plan → run → evaluate → synthesize     (results, logs,
  │                                          agent run history)
  ├── ProjectManagerAgent
  ├── BackendDeveloperAgent  ──► Confluence tools
  ├── DevOpsAgent
  ├── DataAnalystAgent
  ├── SupportEngineerAgent
  ├── QAEngineerAgent
  └── BusinessAnalystAgent

Redis ← Celery broker
```

| Service | Technology | Port |
|---------|-----------|------|
| frontend | React + Vite → nginx | 3000 |
| backend | FastAPI + Python | 8000 |
| worker | Celery (prefork) | — |
| redis | Redis 7 | 6379 |
| postgres | PostgreSQL 16 | 5432 |
| flower | Celery monitor | 5555 |

**LLM:** Runs via Ollama on the host machine (outside Docker). Any OpenAI-compatible provider also works.

---

## Quick Start

### 1. Install Ollama

**macOS / Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve
ollama pull qwen2.5:14b
```

**Windows:** download from [ollama.com](https://ollama.com)

### 2. Configure environment

```bash
cp .env.example .env
```

Defaults work for local Ollama out of the box:
```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:14b
LLM_BASE_URL=http://host.docker.internal:11434
LLM_SUPPORTS_TOOLS=true

ORCHESTRATOR_RUNNER=langgraph
MAX_ORCHESTRATOR_ITERATIONS=5
```

**Confluence integration (optional):**
```env
CONFLUENCE_URL=https://your-company.atlassian.net
CONFLUENCE_USER=your@email.com
CONFLUENCE_API_TOKEN=your_token
CONFLUENCE_SPACE_KEY=DEV
CONFLUENCE_WRITE_ENABLED=true
```

### 3. Start

```bash
docker compose up --build
```

First run takes 5–10 minutes (image downloads + frontend build).

### 4. Open

| URL | Description |
|-----|-------------|
| http://localhost:3000 | Chat UI |
| http://localhost:8000/docs | API docs (Swagger) |
| http://localhost:5555 | Celery Flower monitor |

---

## Usage examples

```
Write technical documentation for the auth module and publish it to Confluence

Analyze support ticket trends from last month

Review the deployment configuration and suggest improvements

Create a project plan for implementing dark mode

Investigate the 503 errors in service logs and summarize the root cause
```

---

## Switching LLM

Edit `.env` and restart `backend` + `worker`:

```env
# Ollama (local)
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1:8b
LLM_BASE_URL=http://host.docker.internal:11434

# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...

# Any OpenAI-compatible provider (LM Studio, LocalAI, etc.)
LLM_PROVIDER=openai
LLM_MODEL=local-model
LLM_BASE_URL=http://host.docker.internal:1234/v1
LLM_API_KEY=lm-studio
```

```bash
docker compose restart backend worker
```

---

## Adding a new agent

1. Create `backend/app/agents/my_agent.py`:

```python
from app.agents.base import BaseITAgent
from app.tools.my_tool import MyTool

class MyAgent(BaseITAgent):
    name = "MyAgent"
    role = "Senior My Role"
    goal = "What this agent achieves"
    backstory = "Background that shapes how the LLM behaves"
    description = "One-line description for the orchestrator"
    capabilities = ["capability 1", "capability 2"]

    def get_tools(self):
        return [MyTool()]
```

2. Register in `backend/app/agents/agent_registry.py`:

```python
from app.agents.my_agent import MyAgent

AGENT_REGISTRY = {
    ...
    "MyAgent": MyAgent(),
}
```

Restart `backend` + `worker` — the orchestrator discovers agents from the registry automatically.

---

## Adding a new tool

```python
from pydantic import BaseModel, Field
from app.tools.base import LoggedTool

class MyToolInput(BaseModel):
    query: str = Field(description="What to search for")

class MyTool(LoggedTool):
    name: str = "MyTool"
    description: str = "Clear description — the LLM reads this to decide when to use the tool"
    args_schema: type[BaseModel] = MyToolInput

    def _run(self, query: str) -> str:
        return f"result for: {query}"
```

Add it to the relevant agent's `get_tools()` method.

---

## Project structure

```
it-company/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── agent_registry.py     # Register agents here
│   │   │   ├── base.py               # BaseITAgent
│   │   │   ├── backend_developer.py
│   │   │   ├── business_analyst.py
│   │   │   ├── data_analyst.py
│   │   │   ├── devops.py
│   │   │   ├── project_manager.py
│   │   │   ├── qa_engineer.py
│   │   │   ├── support_engineer.py
│   │   │   └── runners/
│   │   │       ├── langgraph_runner.py  # ReAct agent runner (default)
│   │   │       └── crewai_runner.py     # CrewAI runner (alternative)
│   │   ├── orchestrator/
│   │   │   ├── graph.py              # LangGraph orchestration graph
│   │   │   ├── orchestrator.py       # Core logic (planning, evaluation, synthesis)
│   │   │   └── base.py
│   │   ├── tools/
│   │   │   ├── base.py               # LoggedTool base class
│   │   │   └── confluence.py         # Confluence read/write/navigate tools
│   │   ├── models/                   # SQLAlchemy models
│   │   ├── api/                      # FastAPI routes
│   │   ├── core/
│   │   │   ├── llm.py                # LLM factory (Ollama / OpenAI-compatible)
│   │   │   └── celery_app.py
│   │   └── workers/tasks.py          # Celery task entry point
│   └── alembic/                      # DB migrations
└── frontend/
    └── src/
        ├── App.jsx
        └── components/
            ├── MessageList.jsx       # Markdown rendering (tables, code, etc.)
            ├── ChatInput.jsx
            └── Sidebar.jsx
```

---

## Database schema

```
chats
  └── tasks (Celery task per message)
        └── agent_runs (one per agent invocation)
              ├── parent_run_id → orchestrator run
              ├── input_payload (full task + prior context)
              ├── output_payload
              └── worker_logs
```

Query all activity for a chat:
```sql
SELECT ar.agent_name, ar.status, ar.created_at,
       ar.input_payload->>'task' AS task,
       ar.output_payload->>'result' AS result
FROM agent_runs ar
WHERE ar.chat_id = <chat_id>
ORDER BY ar.created_at;
```

---

## Useful commands

```bash
# View worker logs
docker compose logs -f worker

# Run migration manually
docker compose exec backend alembic upgrade head

# Check LLM health
curl http://localhost:8000/api/health/llm | jq .

# View agent runs via API
curl http://localhost:8000/api/chats/1/agent-runs | jq .

# Rebuild a single service
docker compose up -d --build worker
```

---

## Roadmap

- [x] Multi-agent orchestration with LangGraph
- [x] Confluence integration (read, write, navigate, move pages)
- [x] Full agent run history in DB with context
- [ ] OpenStack integration
- [ ] Fleio ticket system integration
- [ ] Jira integration
- [ ] Analytics module
- [ ] Streaming responses
- [ ] Agent run UI timeline
