# Orchestrator

Головний мозок IT-компанії. Отримує повідомлення від користувача, планує роботу агентів, запускає їх в єдиному agentic loop і формулює фінальну відповідь.

---

## Файли

| Файл | Що містить |
|------|-----------|
| `orchestrator.py` | Клас `Orchestrator`, всі prompts, утиліти |

---

## Основний flow

```
Повідомлення юзера
       │
       ▼
_detect_language()       — визначає мову (Ukrainian / Russian / English)
       │
       ▼
_get_chat_history()      — останні 10 повідомлень чату
       │
       ▼
_make_decision()         — LLM планує: що потрібно → хто → в якому порядку (chain-of-thought)
       │
       ▼
┌──────────────────────────────────────────────┐
│           Unified agentic loop               │
│                                              │
│  _build_prior_context()                      │
│       │                                      │
│       ▼                                      │
│  _run_single_agent()  ← отримує контекст     │
│       │                 всіх попередніх      │
│       ▼                 агентів              │
│  _evaluate_result()   — LLM вирішує:         │
│       │                 готово чи потрібен   │
│       │                 ще агент?            │
│       ├── complete → вийти з циклу           │
│       └── not complete → наступний агент ────┘
│                         (до MAX_ORCHESTRATOR_ITERATIONS)
└──────────────────────────────────────────────┘
       │
       ▼
_synthesize_answer()     — LLM формулює фінальну відповідь на мові юзера
       │                   (пропускається якщо 1 агент + English)
       ▼
   Message в БД
```

---

## Класи та методи

### `OrchestratorResult`
Результат оркестрації. Поля:
- `reasoning` — chain-of-thought план оркестратора
- `selected_agents` — унікальні імена агентів що були запущені
- `tasks_created` — лог всіх задач з результатами
- `final_answer` — фінальна відповідь для юзера
- `agent_outputs` — `[{agent, output, iteration}]` — сирі виходи по ітераціях
- `errors` — помилки якщо були

---

### `Orchestrator`

Основний клас. Приймає `db: Session` в конструкторі.

#### LLM instances
| Метод | Що повертає |
|-------|------------|
| `_langchain_json()` | LangChain LLM з `json_mode=True` — для `_make_decision`, `_evaluate_result` |
| `_langchain_text()` | LangChain LLM без JSON режиму — для `_synthesize_answer` |

#### DB helpers
| Метод | Що робить |
|-------|-----------|
| `_log()` | Записує в `WorkerLog` і structlog |
| `_create_agent_run()` | Створює `AgentRun` зі статусом `pending` |
| `_update_agent_run()` | Оновлює статус / output / error агента |
| `_get_chat_history()` | Повертає останні 10 повідомлень чату як рядок |

#### Планування та оцінка
| Метод | Prompt | Що повертає |
|-------|--------|-------------|
| `_make_decision()` | `ORCHESTRATOR_SYSTEM_PROMPT` | JSON: agents + tasks (з chain-of-thought у `reasoning`) |
| `_evaluate_result()` | `EVALUATION_SYSTEM_PROMPT` | JSON: `{is_complete, reason, next_agent?, next_task?}` |
| `_synthesize_answer()` | `SYNTHESIS_SYSTEM_PROMPT` | Текст фінальної відповіді на мові юзера |

#### Запуск агентів
| Метод | Що робить |
|-------|-----------|
| `_build_prior_context()` | Збирає виходи всіх попередніх агентів у текст |
| `_run_single_agent()` | Запускає агента через CrewAI; приймає `prior_context` — додає його як `## Context from previous work` перед task description |

#### Головний метод
`run(chat_id, user_message, task_id)` — оркеструє весь flow, повертає `OrchestratorResult`.

---

## Prompts

### `ORCHESTRATOR_SYSTEM_PROMPT`
Chain-of-thought планування. LLM розбиває запит на кроки перед вибором агентів:
1. Що конкретно потрібно юзеру?
2. Який агент найкраще підходить для кожного під-завдання?
3. В якому порядку вони мають працювати?
4. Мінімальний набір — без зайвих агентів.

Змінні: `{agent_descriptions}`, `{user_language}`

### `EVALUATION_SYSTEM_PROMPT`
Перевірка після кожного агента. Явні патерни:
- Backend написав код → QA повинен перевірити
- QA знайшов баги → Backend повинен виправити
- Той самий агент двічі без покращення → зупинитись

Змінні: `{agent_descriptions}`

### `SYNTHESIS_SYSTEM_PROMPT`
Формує фінальну відповідь на мові юзера. Дистилює ключові результати всіх ітерацій.

Змінні: `{user_language}`

---

## Константи

| Константа | Значення | Де визначена |
|-----------|----------|--------------|
| `MAX_ORCHESTRATOR_ITERATIONS` | `5` (default) | `app/config.py` → `settings` |

---

## Agentic loop

Єдиний уніфікований цикл для всіх сценаріїв (включно з Backend+QA ітерацією):

1. `_make_decision()` визначає початковий список агентів і задач
2. `_build_prior_context()` збирає виходи всіх попередніх агентів
3. `_run_single_agent()` запускає агента — він бачить контекст попередніх
4. `_evaluate_result()` вирішує: готово чи потрібен наступний агент
5. Якщо не готово — LLM вказує наступного агента → повернутись до кроку 2
6. Після циклу — `_synthesize_answer()` формулює відповідь

**Backend+QA без hardcode:** `_evaluate_result()` сам розуміє що після Backend потрібен QA, і якщо QA знайшов проблеми — знову Backend. Немає спеціального `REVIEW_LOOP_AGENTS` або окремого методу — оркестратор вирішує динамічно.

---

## Synthesis — умовна

`_synthesize_answer()` пропускається (зайвий LLM-виклик) якщо:
- Тільки 1 агент запущений за 1 ітерацію
- Мова юзера — English

В інших випадках (кілька агентів / ітерацій / не English) — синтез завжди виконується.

---

## Утиліти

### `_detect_language(text)`
Визначає мову за символами:
- Кирилиця > латиниця → `Russian`
- Кирилиця + українські символи (`іїєґ`) → `Ukrainian`
- Інакше → `English`

### `_parse_json(raw)`
Витягує JSON з відповіді LLM: пробує `json.loads` → прибирає markdown-фенси → шукає перший `{...}` блок.
