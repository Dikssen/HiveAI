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

### `confluence.py`
Конфігурація через `/api/integrations`: `CONFLUENCE_URL`, `CONFLUENCE_USER`, `CONFLUENCE_API_TOKEN`, `CONFLUENCE_SPACE_KEY`, `CONFLUENCE_WRITE_ENABLED`.

Правильний порядок для навігації: `ConfluenceSearch` або `ConfluenceGetSpaceRoot` → `ConfluenceGetChildPages` → `ConfluenceGetPage`

| Tool | Аргументи | Тип | Опис |
|------|-----------|-----|------|
| `ConfluenceSearchTool` | `query`, `limit?` | read | Повнотекстовий пошук сторінок у просторі за ключовими словами |
| `ConfluenceGetPageTool` | `page_id?`, `title?` | read | Читає повний вміст сторінки за ID або заголовком |
| `ConfluenceGetSpaceRootTool` | `limit?` | read | Список сторінок верхнього рівня простору |
| `ConfluenceGetChildPagesTool` | `page_id`, `limit?` | read | Список дочірніх сторінок заданої батьківської |
| `ConfluenceGetSectionTool` | `page_id`, `heading` | read | Читає конкретну секцію сторінки за заголовком |
| `ConfluenceCreatePageTool` | `title`, `content_markdown`, `parent_id?` | write* | Створює нову сторінку (Markdown → Storage Format) |
| `ConfluenceUpdateSectionTool` | `page_id`, `heading`, `new_content_markdown` | write* | Замінює вміст секції, не чіпаючи решту сторінки |
| `ConfluenceAppendSectionTool` | `page_id`, `heading`, `content_markdown`, `heading_level?` | write* | Додає нову секцію в кінець сторінки |
| `ConfluenceMovePageTool` | `page_id`, `new_parent_id` | write* | Переміщує сторінку під нового батька |

*write — тільки якщо `CONFLUENCE_WRITE_ENABLED=true`

---

### `jira.py`
Конфігурація через `/api/integrations`: `JIRA_URL`, `JIRA_USER`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `JIRA_WRITE_ENABLED`.

Токен і email — ті самі що для Confluence (один Atlassian акаунт). URL без `/wiki` в кінці.

| Tool | Аргументи | Тип | Опис |
|------|-----------|-----|------|
| `JiraSearchIssuesTool` | `jql`, `limit?` | read | JQL-пошук тікетів. Найпотужніший інструмент — покриває більшість сценаріїв |
| `JiraGetIssueTool` | `issue_key` | read | Повні деталі тікета: summary, description, статус, assignee, останні 5 коментарів |
| `JiraGetProjectIssuesTool` | `project_key?`, `status?`, `limit?` | read | Список тікетів проєкту з фільтром по статусу |
| `JiraCreateIssueTool` | `summary`, `description?`, `issue_type?`, `priority?`, `project_key?`, `labels?` | write* | Створити тікет (Bug, Task, Story, Epic) |
| `JiraAddCommentTool` | `issue_key`, `comment` | write* | Додати коментар до тікета |
| `JiraTransitionIssueTool` | `issue_key`, `status` | write* | Змінити статус (To Do → In Progress → Done) |
| `JiraUpdateIssueTool` | `issue_key`, `summary?`, `description?`, `priority?`, `assignee_account_id?` | write* | Оновити поля тікета |

*write — тільки якщо `JIRA_WRITE_ENABLED=true`

---

### `fleio_support.py`
Пряме підключення до MySQL бази даних Fleio (read-only). Конфігурація через `/api/integrations`: `FLEIO_DB_HOST`, `FLEIO_DB_PORT`, `FLEIO_DB_USER`, `FLEIO_DB_PASSWORD`, `FLEIO_DB_NAME`.

> В Docker: `FLEIO_DB_HOST=host.docker.internal`. MySQL повинен слухати `0.0.0.0`, не `127.0.0.1`.

| Tool | Аргументи | Опис |
|------|-----------|------|
| `FleioTicketSummaryTool` | `days?` | Зведена статистика за N днів: кількість тікетів, топ категорії, статуси, середній час відповіді |
| `FleioListTicketsTool` | `status?`, `client_id?`, `limit?` | Список тікетів з фільтром по статусу або клієнту |
| `FleioGetTicketTool` | `ticket_id` | Повний тікет: деталі + всі повідомлення |
| `FleioClientTicketsTool` | `client_id`, `limit?` | Всі тікети конкретного клієнта |
| `FleioSlaReportTool` | `sla_hours?` | SLA звіт: протерміновані тікети без відповіді, розподіл часу відповіді (<2h, 2-8h, 8-24h, >24h) |
| `FleioTrendsTool` | `weeks?` | Тренди: тижневий/місячний обсяг, топ ключових слів у заголовках, сервіси що генерують найбільше тікетів, продуктивність співробітників |

---

### `knowledge.py`
Постійна пам'ять агентів — база знань про інфраструктуру, схеми БД, конфіги, патерни відомих проблем. Кожен агент має свої приватні записи + доступ до глобальних (agent_name IS NULL). Керування через `/api/knowledge`.

Правильний порядок: `KnowledgeSearch` → `KnowledgeGet` → `KnowledgeSave` або `KnowledgeAppend`

| Tool | Аргументи | Тип | Опис |
|------|-----------|-----|------|
| `KnowledgeSearchTool` | `query` | read | Пошук по title, tags, content. Повертає до 10 записів з коротким preview |
| `KnowledgeGetTool` | `title` | read | Читає повний вміст запису за точним заголовком |
| `KnowledgeSaveTool` | `title`, `content`, `reason`, `tags?`, `scope?` | write | Створює або повністю замінює запис. `scope`: `private` (тільки для себе) або `global` (для всіх агентів). Вимагає обґрунтування `reason` |
| `KnowledgeAppendTool` | `title`, `content`, `reason` | write | Додає новий блок до існуючого запису з датою. Запис повинен вже існувати |

**Коли писати в knowledge base:**
- Виявлена нова інфраструктурна деталь (схема БД, конфіг сервера)
- Знайдений і перевірений workaround для повторюваної проблеми
- Схема або конфіг, який знадобиться в наступних сесіях

**Не писати:** прогрес поточного завдання, тимчасові висновки, разові знахідки.
