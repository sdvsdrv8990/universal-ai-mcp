# Universal AI MCP Server

Модульный MCP-сервер для подключения любых AI-моделей к структурированному рабочему процессу.
Работает полностью в пользовательском пространстве — **root не требуется**.

---

## Содержание

- [Возможности](#возможности)
- [Быстрый старт](#быстрый-старт)
- [Все команды](#все-команды)
- [Структура проекта](#структура-проекта)
- [Модули и инструменты](#модули-и-инструменты)
- [Подключение к AI-клиентам](#подключение-к-ai-клиентам)
- [LLM Провайдеры](#llm-провайдеры)
- [Зеркала и офлайн-режим](#зеркала-и-офлайн-режим)
- [Docker-деплой](#docker-деплой)
- [Переменные окружения](#переменные-окружения)
- [Тесты](#тесты)
- [Документация](#документация)

---

## Возможности

| Функция | Описание |
|---------|----------|
| **Planning Gate** | AI не может начать работу без утверждённого плана |
| **Blockify контекст** | IdeaBlocks сжимают контекст в 3x — экономия токенов |
| **Мульти-провайдер** | Anthropic → OpenRouter → Ollama с автопереключением |
| **Автодетект проекта** | Определяет стек, конвенции, структуру папок |
| **Поиск решений** | Ищет готовый код на GitHub перед написанием с нуля |
| **GSD-workflow** | Состояние сохраняется в `.planning/` между сессиями |
| **Зеркала** | Автовыбор PyPI/Docker зеркала при недоступности основного |

---

## Быстрый старт

```bash
# 1. Клонировать проект
git clone <repo-url>
cd universal-ai-mcp

# 2. Установить (без root, без Docker)
./scripts/setup.sh

# 3. Добавить API-ключи
nano .env
#   ANTHROPIC_API_KEY=<anthropic-api-key>
#   MCP_AUTH_SECRET=$(openssl rand -hex 32)

# 4. Запустить сервер
uv run universal-ai-mcp
```

Сервер запустится на `http://0.0.0.0:8000`.
Healthcheck: `curl http://localhost:8000/health`

---

## Все команды

### Установка и настройка

```bash
# Полная установка (зеркала + uv + зависимости + .env)
./scripts/setup.sh

# Проверить доступность зеркал и выбрать быстрейшее
./scripts/check-mirrors.sh

# Показать текущий выбор зеркал
./scripts/check-mirrors.sh --show

# Проверить только PyPI зеркала
./scripts/check-mirrors.sh --pypi-only

# Проверить только Docker зеркала
./scripts/check-mirrors.sh --docker-only

# Сгенерировать безопасный MCP_AUTH_SECRET
openssl rand -hex 32
```

### Запуск сервера

```bash
# HTTP/SSE режим (облако, команда по умолчанию)
uv run universal-ai-mcp

# stdio режим (локальный Claude Code / Cursor)
MCP_TRANSPORT=stdio uv run universal-ai-mcp

# Другой порт
MCP_PORT=9000 uv run universal-ai-mcp

# С кастомным Ollama
OLLAMA_BASE_URL=http://192.168.1.10:11434 uv run universal-ai-mcp

# Только с Ollama (без платных API)
MCP_TRANSPORT=http \
ANTHROPIC_API_KEY="" \
OPENROUTER_API_KEY="" \
LLM_DEFAULT_PROVIDER=ollama \
uv run universal-ai-mcp
```

### Разработка

```bash
# Установить зависимости включая dev
uv sync --all-extras

# Запустить все тесты
uv run pytest tests/

# Только юнит-тесты
uv run pytest tests/unit/ -v

# Конкретный тест
uv run pytest tests/unit/test_idea_block.py -v

# Линтер
uv run ruff check src/

# Авто-исправление линтера
uv run ruff check src/ --fix

# Проверка типов
uv run mypy src/
```

### Зеркала (если основные недоступны)

```bash
# Автовыбор — пишет .mirrors.env
./scripts/check-mirrors.sh

# Установить PyPI зеркало вручную (Tsinghua)
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uv sync

# Установить PyPI зеркало вручную (Alibaba)
UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple uv sync

# Сделать зеркало постоянным (раскомментировать в uv.toml)
nano uv.toml
```

### Docker

```bash
# Сборка с автовыбором зеркала (рекомендуется)
./scripts/deploy.sh

# Сборка с явным указанием образа
docker build --build-arg BASE_PYTHON_IMAGE=python:3.12-slim .

# Сборка с Alibaba Cloud зеркалом (если Docker Hub недоступен)
docker build \
  --build-arg BASE_PYTHON_IMAGE=registry.cn-hangzhou.aliyuncs.com/library/python:3.12-slim \
  .

# Локальный запуск Docker-образа
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=<anthropic-api-key> \
  -e MCP_AUTH_SECRET=your-secret \
  universal-ai-mcp:latest

# Только проверить Docker зеркала (без сборки)
./scripts/deploy.sh --check-only
```

---

## Структура проекта

```
universal-ai-mcp/
│
├── src/universal_ai_mcp/          # Исходный код сервера
│   ├── __init__.py
│   │
│   ├── core/                      # Инфраструктура сервера
│   │   ├── server.py              # Точка входа, HTTP/SSE транспорт, BearerAuth
│   │   ├── registry.py            # Реестр модулей и MCP-инструментов
│   │   ├── session_store.py       # Хранилище сессий в памяти
│   │   ├── config.py              # Настройки из переменных окружения
│   │   └── logging.py             # Structlog конфигурация
│   │
│   ├── entities/                  # Доменные сущности (объявлены ровно по одному разу)
│   │   ├── __init__.py            # Единственная точка импорта сущностей
│   │   ├── idea_block_entity.py   # IdeaBlock + IdeaBlockCollection (Blockify)
│   │   ├── plan_entity.py         # ExecutionPlan + PlanStep + PlanStepStatus
│   │   ├── project_entity.py      # ProjectContext + ProjectStack + NamingConventions
│   │   ├── provider_entity.py     # LLMProvider + LLMRequest + LLMResponse
│   │   ├── session_entity.py      # AgentSession + SessionState
│   │   ├── module_entity.py       # Module + ModuleScenario + ScenarioType
│   │   └── task_entity.py         # Task + TaskResult + TaskStatus
│   │
│   ├── types/                     # Перечисления и type-алиасы
│   │   ├── module_types.py        # ComplexityLevel, ModuleCategory
│   │   ├── provider_types.py      # ModelTier, RoutingStrategy
│   │   └── workflow_types.py      # WorkflowPhase
│   │
│   ├── modules/                   # Функциональные модули
│   │   ├── planning/              # Planning gate
│   │   │   ├── planner.py         # Оркестратор: вопросы → инструменты → план
│   │   │   ├── question_engine.py # Генерация уточняющих вопросов
│   │   │   └── tool_selector.py   # Выбор MCP-инструментов с обоснованием
│   │   │
│   │   ├── context/               # Оптимизация токенов (Blockify)
│   │   │   ├── idea_block_builder.py  # Конвертация текста в IdeaBlocks
│   │   │   ├── context_manager.py     # Бюджет токенов + автосжатие
│   │   │   └── semantic_compressor.py # Обрезка по важности при переполнении
│   │   │
│   │   ├── llm/                   # Абстракция LLM-провайдеров
│   │   │   ├── provider_registry.py   # Регистрация провайдеров из настроек
│   │   │   ├── router.py              # Маршрутизация по tier (heavy/balanced/fast)
│   │   │   └── providers/
│   │   │       ├── anthropic_provider.py   # Claude API
│   │   │       ├── openrouter_provider.py  # OpenRouter (200+ моделей)
│   │   │       └── ollama_provider.py      # Ollama (локальные модели)
│   │   │
│   │   ├── project_detection/     # Автодетект проекта
│   │   │   ├── stack_detector.py      # Определение языка, фреймворков, конвенций
│   │   │   ├── convention_adapter.py  # Адаптация имён под конвенции проекта
│   │   │   └── stack_advisor.py       # AI-рекомендация стека для нового проекта
│   │   │
│   │   ├── solutions/             # Поиск готовых решений
│   │   │   ├── github_finder.py       # Поиск репозиториев на GitHub
│   │   │   ├── dependency_optimizer.py # Минимизация зависимостей
│   │   │   └── integration_planner.py  # План послойной интеграции
│   │   │
│   │   └── workflow/              # Движок выполнения (GSD)
│   │       ├── task_executor.py   # Параллельное выполнение волнами
│   │       ├── work_verifier.py   # Проверка результата, поиск пробелов
│   │       └── state_manager.py   # Запись .planning/ артефактов
│   │
│   └── tools/                     # Регистрация MCP-инструментов (1 файл = 1 модуль)
│       ├── planning_tools.py      # task_analyze, task_plan_build, task_plan_approve, task_plan_status
│       ├── context_tools.py       # context_add_content, context_get_xml, context_token_usage, context_compress_now
│       ├── llm_tools.py           # llm_complete, llm_list_providers, llm_list_models
│       ├── project_tools.py       # project_detect, project_recommend_stack, project_adapt_name
│       ├── solutions_tools.py     # solutions_find, solutions_optimize_deps, solutions_plan_integration
│       └── workflow_tools.py      # workflow_execute_plan, workflow_verify_work, workflow_save_state, workflow_load_state, workflow_append_context
│
├── config/                        # Конфигурационные файлы
│   ├── modules.yaml               # Порядок загрузки и зависимости модулей
│   ├── providers.yaml             # Настройки LLM-провайдеров
│   ├── stack_templates.yaml       # Шаблоны стеков для новых проектов
│   └── mirrors.yaml               # Список PyPI и Docker зеркал
│
├── docs/
│   ├── project/
│   │   ├── architecture.md        # Архитектура, слои, planning gate
│   │   └── api-reference.md       # Справочник всех MCP-инструментов
│   └── development/
│       ├── blockify/              # Документация по интеграции Blockify
│       ├── get-shit-done/         # Документация по интеграции GSD
│       └── claude-best-practice/  # Паттерны из лучших практик Claude Code
│
├── scripts/
│   ├── setup.sh                   # Локальная установка (без root, без Docker)
│   ├── deploy.sh                  # Docker-сборка с автовыбором зеркала
│   └── check-mirrors.sh           # Тест зеркал + запись .mirrors.env
│
├── tests/
│   ├── unit/
│   │   ├── test_idea_block.py
│   │   ├── test_convention_adapter.py
│   │   ├── test_semantic_compressor.py
│   │   ├── test_stack_detector.py
│   │   └── test_task_executor.py
│   └── integration/               # (в разработке)
│
├── .env.example                   # Шаблон переменных окружения
├── .mirrors.env                   # Авто-генерируется check-mirrors.sh (в .gitignore)
├── pyproject.toml                 # Python-зависимости и настройки инструментов
├── uv.toml                        # Конфигурация uv (зеркала PyPI)
├── Dockerfile                     # Multi-arg образ с поддержкой зеркал
└── .gitignore
```

---

## Модули и инструменты

### Planning (18 инструментов всего)

Обязательный шлюз: любая задача проходит через план перед выполнением.

```
task_analyze(task)          → complexity + questions[]
task_plan_build(answers)    → ExecutionPlan (шаги, инструменты, обоснование)
task_plan_approve(plan_id)  → разрешает выполнение
task_plan_status(session)   → прогресс плана
```

### Context (Blockify)

```
context_add_content(text)   → IdeaBlocks, статистика сжатия
context_get_xml(session)    → XML-контекст для LLM (3x эффективнее raw текста)
context_token_usage(session)→ {used, budget, utilization, status}
context_compress_now(session)→ принудительное сжатие
```

### LLM Router

```
llm_complete(prompt, tier)  → {content, provider, model, tokens}
llm_list_providers()        → список активных провайдеров
llm_list_models(provider)   → доступные модели
```

### Project Detection

```
project_detect(path)              → стек, конвенции, модули
project_recommend_stack(desc)     → AI-рекомендация стека
project_adapt_name(name, session) → имя под конвенции проекта
```

### Solutions

```
solutions_find(requirement)              → GitHub-репозитории
solutions_optimize_deps(lib, features)   → минимальный набор зависимостей
solutions_plan_integration(repo, feature)→ план послойной интеграции
```

### Workflow

```
workflow_execute_plan(session, path)  → выполнение волнами
workflow_verify_work(session)         → проверка, список пробелов
workflow_save_state(session, path)    → запись .planning/
workflow_load_state(plan_id, session) → восстановление из .planning/
workflow_append_context(key, value)   → запись в CONTEXT.md
```

---

## Подключение к AI-клиентам

### Claude Code (HTTP/SSE)

```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "universal-ai": {
      "url": "http://localhost:8000/sse",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_AUTH_SECRET"
      }
    }
  }
}
```

### Claude Code (stdio — локальный запуск)

```json
{
  "mcpServers": {
    "universal-ai": {
      "command": "uv",
      "args": ["run", "--project", "/home/admin/projects/universal-ai-mcp", "universal-ai-mcp"],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
        "MCP_AUTH_SECRET": "${MCP_AUTH_SECRET}"
      }
    }
  }
}
```

### Cursor / Windsurf

```json
{
  "mcpServers": {
    "universal-ai": {
      "url": "http://localhost:8000/sse",
      "headers": { "Authorization": "Bearer YOUR_SECRET" }
    }
  }
}
```

### Health check

```bash
curl http://localhost:8000/health
# {"status":"ok","server":"universal-ai-mcp","version":"1.0.0","modules":6,"tools":18}
```

---

## LLM Провайдеры

| Приоритет | Провайдер | Переменная | Модели |
|-----------|----------|-----------|--------|
| 1 | Anthropic | `ANTHROPIC_API_KEY` | claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5 |
| 2 | OpenRouter | `OPENROUTER_API_KEY` | 200+ моделей |
| 3 | Ollama | `OLLAMA_BASE_URL` | llama3.2, mistral, qwen2.5-coder и др. |

Маршрутизация по тирам:

| Тир | Модель | Используется для |
|-----|--------|-----------------|
| `heavy` | claude-opus-4-7 | Сложные задачи |
| `balanced` | claude-sonnet-4-6 | Планирование, выполнение |
| `fast` | claude-haiku-4-5 | Вопросы, сжатие контекста |

---

## Зеркала и офлайн-режим

### Автоматический выбор (рекомендуется)

```bash
# Проверить все зеркала и выбрать доступное
./scripts/check-mirrors.sh

# Посмотреть текущий выбор
./scripts/check-mirrors.sh --show
```

Результат записывается в `.mirrors.env`:
```
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
DOCKER_BASE_PYTHON=registry.cn-hangzhou.aliyuncs.com/library/python:3.12-slim
```

### Ручная установка PyPI-зеркала

```bash
# Разовая установка с зеркалом
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uv sync

# Постоянное зеркало — раскомментировать в uv.toml:
# url = "https://pypi.tuna.tsinghua.edu.cn/simple"
```

### Список зеркал PyPI

| Зеркало | URL |
|---------|-----|
| PyPI (официальный) | `https://pypi.org/simple` |
| Tsinghua | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| USTC | `https://pypi.mirrors.ustc.edu.cn/simple` |
| Alibaba Cloud | `https://mirrors.aliyun.com/pypi/simple` |
| Douban | `https://pypi.doubanio.com/simple` |
| BFSU | `https://mirrors.bfsu.edu.cn/pypi/web/simple` |

### Offline-режим с Ollama

```bash
# Запустить только с локальными моделями (без интернета после установки)
ollama pull llama3.2     # один раз с интернетом
ollama pull qwen2.5-coder

ANTHROPIC_API_KEY="" \
OPENROUTER_API_KEY="" \
LLM_DEFAULT_PROVIDER=ollama \
MCP_TRANSPORT=stdio \
uv run universal-ai-mcp
```

---

## Docker-деплой

### Автоматический (рекомендуется — проверяет зеркала)

```bash
./scripts/deploy.sh
```

### С явным зеркалом

```bash
# Docker Hub (нужен docker login при rate limit)
docker login
docker build -t universal-ai-mcp .

# Alibaba Cloud (если Docker Hub недоступен)
docker build \
  --build-arg BASE_PYTHON_IMAGE=registry.cn-hangzhou.aliyuncs.com/library/python:3.12-slim \
  -t universal-ai-mcp .

# Tencent Cloud
docker build \
  --build-arg BASE_PYTHON_IMAGE=ccr.ccs.tencentyun.com/library/python:3.12-slim \
  -t universal-ai-mcp .
```

### Docker Compose

```yaml
# docker-compose.yml
services:
  universal-ai-mcp:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      start_period: 15s
```

```bash
docker compose up -d
docker compose logs -f
```

---

## Переменные окружения

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `MCP_TRANSPORT` | `http` | Транспорт: `http` или `stdio` |
| `MCP_HOST` | `0.0.0.0` | Хост сервера |
| `MCP_PORT` | `8000` | Порт сервера |
| `MCP_AUTH_SECRET` | — | **Обязательно.** Bearer-токен для авторизации |
| `ANTHROPIC_API_KEY` | — | Ключ Anthropic Claude API |
| `OPENROUTER_API_KEY` | — | Ключ OpenRouter API |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL Ollama сервера |
| `LLM_DEFAULT_PROVIDER` | `anthropic` | Провайдер по умолчанию |
| `CONTEXT_MAX_TOKENS` | `150000` | Бюджет токенов на сессию |
| `CONTEXT_TARGET_RATIO` | `0.6` | Сжатие при достижении этой доли |
| `PLANNING_REQUIRE_APPROVAL` | `true` | Требовать явного approve плана |
| `GITHUB_TOKEN` | — | Токен для GitHub API (solutions_find) |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `LOG_FORMAT` | `json` | Формат логов: `json` или `text` |
| `UV_INDEX_URL` | — | PyPI зеркало (авто из `.mirrors.env`) |

Полный список с описанием: `.env.example`

---

## Тесты

```bash
# Все тесты
uv run pytest tests/ -v

# Только юнит
uv run pytest tests/unit/ -v

# С покрытием (нужен pytest-cov)
uv run pytest tests/unit/ --cov=src --cov-report=term-missing
```

Текущее покрытие: **18/18 тестов**, 0 предупреждений.

Тестируемые компоненты:
- `IdeaBlock` + `IdeaBlockCollection` — XML-сериализация, фильтрация, подсчёт токенов
- `ConventionAdapter` — преобразование имён (snake_case, kebab-case, PascalCase)
- `SemanticCompressor` — соблюдение бюджета токенов, сохранение важных блоков
- `StackDetector` — определение Python / TypeScript / Unknown проекта
- `TaskExecutor` — шлюз approve, параллельные волны, обработка ошибок

---

## Документация

| Документ | Описание |
|---------|----------|
| `docs/project/architecture.md` | Архитектура, слои, диаграммы |
| `docs/project/api-reference.md` | Справочник всех 18 MCP-инструментов |
| `docs/development/blockify/overview.md` | Что такое IdeaBlocks и зачем |
| `docs/development/blockify/idea-blocks-spec.md` | Спецификация реализации |
| `docs/development/blockify/integration-plan.md` | v1.0 готово, v2.0 roadmap |
| `docs/development/get-shit-done/overview.md` | GSD паттерны в этом проекте |
| `docs/development/get-shit-done/integration-plan.md` | Что взято из GSD |
| `docs/development/claude-best-practice/overview.md` | Паттерны Claude Code |

---

## На основе

- [Blockify](https://github.com/iternal-technologies-partners/blockify-agentic-data-optimization) — IdeaBlocks: 40x сжатие, 3x токен-эффективность
- [GSD](https://github.com/gsd-build/get-shit-done) — planning gate, wave execution, .planning/ артефакты
- [Claude Code Best Practice](https://github.com/shanraisshan/claude-code-best-practice) — MCP паттерны, workflow conventions
