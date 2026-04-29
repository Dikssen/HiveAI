# Tools Reference

Всі tools знаходяться в `backend/app/tools/`. Кожен наслідує `LoggedTool` — він автоматично логує кожен виклик (input/output/errors) в базу даних.

---

## Як додати новий tool

1. Створи файл `backend/app/tools/my_tool.py`
2. Наслідуй `LoggedTool`
3. Додай до `get_tools()` потрібного агента в `backend/app/agents/*.py`
4. `docker compose restart backend worker`

```python
from pydantic import BaseModel, Field
from app.tools.base import LoggedTool

class MyToolInput(BaseModel):
    query: str = Field(description="Що LLM має сюди передати — конкретно і зрозуміло")

class MyTool(LoggedTool):
    name: str = "MyTool"
    description: str = (
        "Що tool робить. Коли його треба викликати. Що він повертає."
    )
    args_schema: type[BaseModel] = MyToolInput

    def _run(self, query: str) -> str:
        return "result"
```

**Правила для `description` tool:**
- Що робить
- Коли викликати (до/після якого іншого tool)
- Що повертає

**Правила для `Field(description=...)`:**
- Конкретно що передати в параметр, з прикладом якщо можна
- НЕ копіювати опис tool сюди

**Tool без аргументів** — не потрібні `args_schema` і `BaseModel`:
```python
class MyTool(LoggedTool):
    name: str = "MyTool"
    description: str = "..."

    def _run(self) -> str:
        return "result"
```

---

## Існуючі tools

### `read_logs.py`
| Tool | Аргументи | Опис |
|------|-----------|------|
| `ReadLogsTool` | `log_type`, `lines` | Читає лог-файли з `sample_data/logs/` |

### `support_analytics.py`
| Tool | Аргументи | Опис |
|------|-----------|------|
| `SupportAnalyticsTool` | `period` | Аналізує тікети з `sample_data/support_tickets.json` |

### `code_review.py`
| Tool | Аргументи | Опис |
|------|-----------|------|
| `CodeReviewTool` | `file_path` | Читає файл коду для review |

### `docker_inspect.py`
| Tool | Аргументи | Опис |
|------|-----------|------|
| `DockerInspectTool` | `compose_file` | Читає docker-compose файл для аналізу |

### `report_writer.py`
| Tool | Аргументи | Опис |
|------|-----------|------|
| `ReportWriterTool` | `title`, `content` | Зберігає звіт у файл |

### `git_serch.py`
| Tool | Аргументи | Опис |
|------|-----------|------|
| `ListRepositoriesTool` | — | Повертає список всіх GitHub репозиторіїв з описами. Використовувати щоб знайти правильну назву репо. |

### `local_repo.py`
Репозиторії клонуються в `./repos/` і зберігаються між сесіями. Правильний порядок викликів:
`ListRepositories` → `CloneOrUpdateRepo` → `ListBranches` → `SwitchBranch` → `ListLocalFiles` → `ReadLocalFile`

| Tool | Аргументи | Опис |
|------|-----------|------|
| `CloneOrUpdateRepoTool` | `repo_name`, `branch?` | Clone якщо немає локально, pull якщо є. Завжди викликати перед читанням файлів. |
| `ListBranchesTool` | `repo_name` | Список всіх гілок. Поточна позначена `*`. |
| `SwitchBranchTool` | `repo_name`, `branch` | Переключитись на іншу гілку. |
| `ListLocalFilesTool` | `repo_name`, `path?` | Список файлів і папок в репо (або підпапці). |
| `ReadLocalFileTool` | `repo_name`, `file_path` | Читає вміст файлу з локального репо. |
