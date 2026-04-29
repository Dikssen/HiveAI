# IT Company AI Platform

Мінімальна web-платформа, яка симулює маленьку IT-компанію на базі **CrewAI**.

Користувач відкриває web-чат, пише задачу → **ChiefOrchestrator** аналізує запит, вибирає агентів, запускає їх через **Celery workers** → збирає результати і повертає відповідь у чат.

---

## Архітектура

```
Browser → FastAPI (backend) → Celery task → Orchestrator
                                               ↓
                               CrewAI Crew (selected agents)
                                    ↓
                               PostgreSQL (results + logs)
                                    ↓
                               Browser ← polling every 2.5s
```

**Сервіси:**
| Сервіс | Технологія | Порт |
|--------|-----------|------|
| frontend | React + Vite → nginx | 3000 |
| backend | FastAPI + Python | 8000 |
| worker | Celery | — |
| redis | Redis 7 (Celery broker) | 6379 |
| postgres | PostgreSQL 16 | 5432 |
| flower | Celery monitoring | 5555 |

**LLM:** Ollama запускається локально на хості (поза Docker).

---

## Встановлення і запуск

### 1. Встановіть Ollama локально

**macOS / Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:** завантажте інсталятор з [ollama.com](https://ollama.com)

### 2. Запустіть Ollama

```bash
ollama serve
```

Перевірте, що працює:
```bash
curl http://localhost:11434/api/tags
```

### 3. Завантажте модель

```bash
ollama pull qwen2.5:14b
```

Перевірте, що модель доступна:
```bash
ollama list
# Має показати: qwen2.5:14b
```

### 4. Налаштуйте .env

```bash
cp .env.example .env
```

Значення за замовчуванням вже правильні для локального запуску:
```
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:14b
LLM_BASE_URL=http://host.docker.internal:11434
```

> **Важливо для Linux:** `host.docker.internal` автоматично налаштовується через `extra_hosts` у docker-compose. Перевірте, що Docker версії 20.10+.

### 5. Запустіть через Docker Compose

```bash
cd it-company
docker compose up --build
```

Перший запуск займе 5-10 хвилин (завантаження образів, збірка frontend/backend).

### 6. Відкрийте браузер

- **Frontend:** http://localhost:3000
- **API Docs:** http://localhost:8000/docs
- **Flower (Celery monitor):** http://localhost:5555

---

## Використання

1. Відкрийте http://localhost:3000
2. Натисніть **+** щоб створити новий чат
3. Напишіть задачу, наприклад:

```
Потрібно зробити аналітику по використанню тех підтримки
```

4. Натисніть Enter або кнопку →
5. Спостерігайте в реальному часі:
   - Статус задачі: pending → running → completed
   - Agent Execution Timeline внизу (які агенти були викликані)
   - Фінальна відповідь з'явиться в чаті

### Приклади запитів для тестування

```
Зроби аналітику по зверненнях в техпідтримку

Подивись логи і знайди причину падіння сервісу

Проаналізуй помилку 503 в логах

Зроби ревʼю коду sample_code.py

Перевір docker конфігурацію і знайди проблеми

Підготуй план реалізації dark mode для web-додатку

Хто був відповідальний за інцидент 15 січня?

Поясни, які агенти були залучені і що вони зробили
```

---

## Застосування міграцій (вручну)

Міграції автоматично запускаються при старті backend. Якщо потрібно вручну:

```bash
# Всередині контейнера backend
docker compose exec backend alembic upgrade head

# Або локально (потрібен DATABASE_URL в .env)
cd backend
alembic upgrade head
```

Створити нову міграцію:
```bash
docker compose exec backend alembic revision --autogenerate -m "my_change"
```

---

## API Endpoints

| Метод | URL | Опис |
|-------|-----|------|
| `GET` | `/api/health` | Healthcheck backend + DB |
| `GET` | `/api/health/llm` | Перевірка Ollama + моделі |
| `POST` | `/api/chats` | Створити новий чат |
| `GET` | `/api/chats` | Список чатів |
| `GET` | `/api/chats/{id}` | Чат з повідомленнями |
| `POST` | `/api/chats/{id}/messages` | Відправити повідомлення |
| `GET` | `/api/chats/{id}/messages` | Повідомлення чату |
| `GET` | `/api/tasks/{id}` | Статус Celery задачі |
| `GET` | `/api/chats/{id}/agent-runs` | Agent runs по чату |
| `GET` | `/api/agent-runs/{id}/logs` | Логи agent run |

Swagger UI: http://localhost:8000/docs

---

## Як додати нового агента

1. Створіть файл `backend/app/agents/my_agent.py`:

```python
from app.agents.base import BaseITAgent
from app.tools.report_writer import ReportWriterTool

class MyCustomAgent(BaseITAgent):
    name = "MyCustomAgent"
    role = "My Custom Role"
    goal = "What this agent tries to achieve"
    backstory = "Background story for the LLM persona"
    description = "One-line description for the orchestrator"
    capabilities = ["capability 1", "capability 2"]

    def get_tools(self):
        return [ReportWriterTool()]
```

2. Зареєструйте в `backend/app/agents/agent_registry.py`:

```python
from app.agents.my_agent import MyCustomAgent

AGENT_REGISTRY = {
    ...
    "MyCustomAgent": MyCustomAgent(),
}
```

Після перезапуску backend/worker агент автоматично стане доступним для orchestrator.

---

## Як додати новий tool

1. Створіть файл `backend/app/tools/my_tool.py`:

```python
from pydantic import BaseModel, Field
from app.tools.base import LoggedTool

class MyToolInput(BaseModel):
    query: str = Field(description="What to search for")

class MyTool(LoggedTool):
    name: str = "MyTool"
    description: str = "What this tool does — the LLM reads this"
    args_schema: type[BaseModel] = MyToolInput

    def _run(self, query: str) -> str:
        # Tool logic here
        return f"Result for: {query}"
```

2. Додайте tool до потрібних агентів у їх `get_tools()` методі.

---

## Дебаг Celery Worker

```bash
# Переглянути логи worker
docker compose logs -f worker

# Flower UI (Celery monitor)
open http://localhost:5555

# Запустити worker локально (для дебагу)
cd backend
celery -A app.core.celery_app worker --loglevel=debug --concurrency=1

# Переглянути task queue
docker compose exec redis redis-cli LLEN celery
```

---

## Перегляд логів

```bash
# Всі сервіси
docker compose logs -f

# Тільки worker
docker compose logs -f worker

# Тільки backend
docker compose logs -f backend

# Agent runs через API
curl http://localhost:8000/api/chats/1/agent-runs | jq .

# Logs конкретного agent run
curl http://localhost:8000/api/agent-runs/1/logs | jq .
```

---

## Зміна LLM моделі

Відредагуйте `.env`:

```bash
# Ollama (локальна модель)
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1:8b
LLM_BASE_URL=http://host.docker.internal:11434

# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...

# OpenAI-compatible (LM Studio, LocalAI, etc.)
LLM_PROVIDER=openai
LLM_MODEL=local-model
LLM_BASE_URL=http://host.docker.internal:1234/v1
LLM_API_KEY=lm-studio
```

Перезапустіть: `docker compose restart backend worker`

---

## Перевірка LLM

```bash
# Через API
curl http://localhost:8000/api/health/llm | jq .

# Напряму до Ollama
curl http://localhost:11434/api/tags
```

---

## Linux: host.docker.internal

На Linux `host.docker.internal` автоматично додається через `extra_hosts: ["host.docker.internal:host-gateway"]` у docker-compose.yml.

Перевірте Docker версію (потрібно 20.10+):
```bash
docker --version
```

Якщо не працює, можна використати IP хосту напряму:
```bash
# Знайдіть IP docker bridge
ip route | grep docker0
# або
docker network inspect bridge | grep Gateway

# Встановіть в .env
LLM_BASE_URL=http://172.17.0.1:11434
```

---

## Структура проєкту

```
it-company/
├── docker-compose.yml
├── .env.example
├── README.md
├── sample_data/          # Mock data для тестування
│   ├── logs/
│   │   ├── service.log
│   │   └── error.log
│   ├── support_tickets.json
│   ├── sample_code.py
│   ├── backend_error.py
│   └── docker-compose-sample.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/001_initial_schema.py
│   └── app/
│       ├── main.py           # FastAPI app
│       ├── config.py         # Settings з .env
│       ├── api/              # FastAPI routes
│       ├── core/
│       │   ├── llm.py        # LLM factory (Ollama/OpenAI)
│       │   └── celery_app.py # Celery setup
│       ├── db/               # SQLAlchemy engine + session
│       ├── models/           # SQLAlchemy models
│       ├── schemas/          # Pydantic schemas
│       ├── agents/           # CrewAI agents
│       │   ├── base.py
│       │   ├── agent_registry.py   ← додавай агентів сюди
│       │   └── *.py          # Конкретні агенти
│       ├── tools/            # CrewAI tools
│       ├── orchestrator/
│       │   └── orchestrator.py  # ChiefOrchestrator (мозок системи)
│       └── workers/
│           └── tasks.py      # Celery tasks
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    └── src/
        ├── App.jsx
        ├── api/client.js
        └── components/
```
