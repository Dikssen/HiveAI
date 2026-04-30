# HiveAI

An AI-powered operations platform for IT companies. Business users describe tasks in natural language — a multi-agent system handles the execution across your internal tools and systems.

**Current integrations:** Confluence · Jira · GitHub · Fleio (MySQL)

---

## How it works

```
User writes a task in chat
        ↓
ChiefOrchestrator analyzes and builds an execution plan
        ↓
Specialized agents run sequentially via Celery workers
        ↓
Each agent uses tools to interact with real systems (Confluence, Jira, GitHub, Fleio, etc.)
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
ChiefOrchestrator                           PostgreSQL
  │  plan → run → evaluate → synthesize     (results, logs,
  │                                          agent runs, knowledge)
  ├── ProjectManagerAgent     ──► Confluence · Jira
  ├── BackendDeveloperAgent   ──► Confluence · Jira · GitHub
  ├── QAEngineerAgent         ──► Jira · GitHub
  ├── BusinessAnalystAgent    ──► Confluence · Jira · Fleio
  ├── SupportEngineerAgent    ──► Jira · Fleio
  ├── DataAnalystAgent        ──► Fleio
  └── DevOpsAgent             ──► GitHub · logs

All agents ──► Knowledge Base (private + global entries)

Redis ← Celery broker
Fleio MySQL ← read-only (host machine)
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

ORCHESTRATOR_RUNNER=custom
MAX_ORCHESTRATOR_ITERATIONS=5
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

## Configuring integrations

All credentials are stored in the database — no restart needed after changes.

**Configure via API:**
```bash
curl -X PATCH http://localhost:8000/api/integrations/CONFLUENCE_URL \
  -H "Content-Type: application/json" \
  -d '{"value": "https://mycompany.atlassian.net/wiki"}'
```

Or use the Swagger UI at `http://localhost:8000/docs` → `PATCH /api/integrations/{key}`.

### Confluence

| Key | Description |
|-----|-------------|
| `CONFLUENCE_URL` | Base URL, e.g. `https://mycompany.atlassian.net/wiki` |
| `CONFLUENCE_USER` | Login email |
| `CONFLUENCE_API_TOKEN` | API token (masked in API responses) |
| `CONFLUENCE_SPACE_KEY` | Default space key, e.g. `DEV` |
| `CONFLUENCE_WRITE_ENABLED` | `true` to allow creating/editing pages |

### Jira

| Key | Description |
|-----|-------------|
| `JIRA_URL` | Base URL, e.g. `https://mycompany.atlassian.net` (no `/wiki`) |
| `JIRA_USER` | Login email (same as Confluence) |
| `JIRA_API_TOKEN` | API token (same as Confluence) |
| `JIRA_PROJECT_KEY` | Default project key, e.g. `DEV` |
| `JIRA_WRITE_ENABLED` | `true` to allow creating/updating issues |

### GitHub

| Key | Description |
|-----|-------------|
| `GITHUB_TOKEN` | Personal access token (masked in API responses) |

### Fleio (MySQL)

Direct read-only connection to your Fleio support database.

| Key | Description |
|-----|-------------|
| `FLEIO_DB_HOST` | MySQL host. In Docker: `host.docker.internal` |
| `FLEIO_DB_PORT` | MySQL port, default `3306` |
| `FLEIO_DB_USER` | MySQL user with read access |
| `FLEIO_DB_PASSWORD` | MySQL password (masked in API responses) |
| `FLEIO_DB_NAME` | Database name, e.g. `fleio` |

> MySQL must bind to `0.0.0.0` (not `127.0.0.1`) for Docker to reach it via `host.docker.internal`.

---

## Agent & tool management

Enable or disable individual agents and their tools via API — no restart needed.

```bash
# Disable an agent
curl -X PATCH http://localhost:8000/api/agents/BackendDeveloperAgent \
  -H "Content-Type: application/json" -d '{"is_enabled": false}'

# Disable a specific tool for an agent
curl -X PATCH http://localhost:8000/api/agents/ProjectManagerAgent/tools/JiraCreateIssueTool \
  -H "Content-Type: application/json" -d '{"is_enabled": false}'

# List all agents and their tools
curl http://localhost:8000/api/agents | jq .
```

---

## Knowledge base

Agents have a persistent knowledge base for storing infrastructure facts, DB schemas, server configs, and known issue patterns. Each agent has private entries (visible only to itself) and access to global entries (shared across all agents).

The orchestrator sees a summary of available knowledge topics when planning tasks.

```bash
# Create a global knowledge entry
curl -X POST http://localhost:8000/api/knowledge \
  -H "Content-Type: application/json" \
  -d '{"title": "Fleio Database Schema", "content": "...", "tags": "fleio,mysql"}'

# List all entries
curl http://localhost:8000/api/knowledge | jq .

# List entries for a specific agent
curl "http://localhost:8000/api/knowledge?agent_name=DataAnalystAgent" | jq .

# Update an entry
curl -X PATCH http://localhost:8000/api/knowledge/1 \
  -H "Content-Type: application/json" -d '{"content": "updated content"}'
```

Agents can also write to the knowledge base themselves using `KnowledgeSave` and `KnowledgeAppend` tools — with a mandatory `reason` field to prevent noise.

---

## Usage examples

```
Write technical documentation for the auth module and publish it to Confluence

Create a Jira task for implementing dark mode with High priority

Analyze support ticket trends from last month and find the top recurring issues

Review the deployment configuration and suggest improvements

Investigate the 503 errors in service logs and summarize the root cause

List all open In Progress tickets in the DEV project

Which clients submitted the most support tickets this week?

Show SLA performance for the last 30 days
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
from app.tools.knowledge import get_knowledge_tools

class MyAgent(BaseITAgent):
    name = "MyAgent"
    role = "Senior My Role"
    goal = "What this agent achieves"
    backstory = "Background that shapes how the LLM behaves"
    description = "One-line description for the orchestrator"
    capabilities = ["capability 1", "capability 2"]

    def get_tools(self):
        return [*get_knowledge_tools(agent_name=self.name)]
```

2. Register in `backend/app/agents/agent_registry.py`:

```python
from app.agents.my_agent import MyAgent

AGENT_REGISTRY = {
    ...
    "MyAgent": MyAgent(),
}
```

Restart `backend` + `worker` — the orchestrator discovers agents from the registry automatically. The agent and its tools are seeded into the database on next startup.

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

Add it to the relevant agent's `get_tools()` method. See [backend/app/tools/TOOLS.md](backend/app/tools/TOOLS.md) for full tools reference.

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
│   │   │   ├── base.py               # BaseITAgent + get_active_tools()
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
│   │   │   └── orchestrator.py       # Planning, evaluation, synthesis
│   │   ├── tools/
│   │   │   ├── base.py               # LoggedTool base class
│   │   │   ├── confluence.py         # Confluence read/write tools
│   │   │   ├── jira.py               # Jira read/write tools
│   │   │   ├── git_serch.py          # GitHub repository listing
│   │   │   ├── local_repo.py         # Clone, read, edit local repos
│   │   │   ├── fleio_support.py      # Fleio MySQL read-only tools
│   │   │   ├── knowledge.py          # Agent knowledge base tools
│   │   │   └── TOOLS.md              # Full tools reference
│   │   ├── models/                   # SQLAlchemy models
│   │   │   ├── agent.py              # Agent enable/disable
│   │   │   ├── agent_tool_config.py  # Per-agent tool enable/disable
│   │   │   ├── integration_config.py # External service credentials
│   │   │   └── knowledge_entry.py    # Knowledge base entries
│   │   ├── api/
│   │   │   ├── agent_config.py       # GET/PATCH /api/agents
│   │   │   ├── integrations.py       # GET/PATCH /api/integrations
│   │   │   └── knowledge.py          # CRUD /api/knowledge
│   │   ├── db/
│   │   │   ├── seed.py               # Upsert agents, tools, integration configs on startup
│   │   │   └── integration_config_helper.py  # DB reads with 60s TTL cache
│   │   └── core/
│   │       ├── llm.py                # LLM factory (Ollama / OpenAI-compatible)
│   │       └── celery_app.py
│   └── alembic/                      # DB migrations
└── frontend/
    └── src/
        ├── App.jsx
        └── components/
            ├── MessageList.jsx
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

agents
  └── agent_tool_configs (per-agent tool enable/disable)

integration_configs (Confluence, Jira, GitHub, Fleio credentials)

knowledge_entries
  ├── agent_name NULL  → global (visible to all agents)
  └── agent_name SET   → private (visible only to that agent)
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

# List all agents with their tools
curl http://localhost:8000/api/agents | jq .

# List all integration configs
curl http://localhost:8000/api/integrations | jq .

# List all knowledge entries
curl http://localhost:8000/api/knowledge | jq .

# View agent runs via API
curl http://localhost:8000/api/chats/1/agent-runs | jq .

# Rebuild a single service
docker compose up -d --build worker
```

---

## Roadmap

- [x] Multi-agent orchestration
- [x] Confluence integration (read, write, navigate, move pages)
- [x] Jira integration (search, read, create, comment, transition issues)
- [x] GitHub integration (list repos, clone, read, edit files)
- [x] Fleio integration (ticket analytics, SLA reports, trends via MySQL)
- [x] DB-driven agent & tool enable/disable (no restart needed)
- [x] DB-driven integration credentials (no restart needed)
- [x] Full agent run history with context
- [x] Agent knowledge base (persistent memory, private + global entries)
- [ ] OpenStack integration
- [ ] Streaming responses
- [ ] Agent run UI timeline
