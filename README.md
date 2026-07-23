# TGLid — поиск и квалификация Telegram-лидов

TGLid — внутренняя веб-система для обработки потенциальных клиентов из разрешённых Telegram-групп. Реализованы технический фундамент блока 2.1 и backend-подэтап 2.2A: серверная авторизация, роли, сотрудники, аудит и защита сессий.

> Frontend авторизации относится к 2.2B и пока не реализован. Telegram, AI, мониторинг, лиды, Kanban и переписки также остаются за границами текущего состояния.

## Документация продукта

- [Требования к продукту](docs/product-requirements.md)
- [Пользовательские сценарии](docs/user-flows.md)
- [Системная архитектура](docs/system-architecture.md)
- [Модель данных](docs/data-model.md)
- [Автомат статусов лида](docs/lead-state-machine.md)
- [Политика AI-диалога](docs/ai-dialog-policy.md)
- [Контракты API](docs/api-contracts.md)
- [Безопасность и риски](docs/security-and-risks.md)
- [Аналитика и расходы](docs/analytics-and-costs.md)
- [Границы MVP](docs/mvp-scope.md)
- [Дорожная карта](docs/development-roadmap.md)
- [Открытые вопросы](docs/open-questions.md)

## Стек

- Frontend: Next.js 15, React 19, TypeScript, App Router, ESLint.
- Backend: Python 3.12, FastAPI, Pydantic Settings, SQLAlchemy async, Alembic, Redis async.
- Инфраструктура: PostgreSQL 16, Redis 7, Docker Compose.
- Управление зависимостями: pnpm 11 и uv 0.11.

## Требования локального окружения

- Docker Desktop с Docker Compose v2;
- Node.js 22 и pnpm 11 — для локальных frontend-проверок;
- Python 3.12 и uv — для локальных backend-проверок.

Установленный `uv` должен быть доступен в `PATH`. В используемом окружении его путь: `/Users/user/Library/Python/3.12/bin/uv`.

## Быстрый запуск

```bash
cp .env.example .env
make up
```

Compose применяет инфраструктурную Alembic-миграцию при запуске API. Для отдельного повторного запуска миграций используйте:

```bash
make migrate
```

Локальные адреса после запуска:

- frontend: http://localhost:3000
- backend: http://localhost:8000
- liveness API: http://localhost:8000/health
- readiness API: http://localhost:8000/health/ready
- безопасный статус для frontend: http://localhost:8000/api/v1/system/status

PostgreSQL и Redis не публикуют порты наружу: они доступны только сервисам сети Compose.

## Конфигурация

Скопируйте `.env.example` в `.env`. В нём указаны только локальные демонстрационные значения. Помимо адресов сервисов и CORS, backend настраивает срок сессии, имена и атрибуты cookies, минимальную длину пароля, Redis rate limit, интервал обновления `last_seen_at` и срок хранения старых сессий. `CORS_ORIGINS` не принимает `*`; в production `SESSION_COOKIE_SECURE=true` обязателен. Строки подключения и иные секреты не должны попадать в Git.

## Команды

```bash
make help       # список команд
make up         # собрать и запустить стек
make down       # остановить стек
make build      # собрать образы
make logs       # посмотреть логи
make migrate    # применить миграции в запущенном API
make create-admin EMAIL=admin@example.com NAME="Administrator"  # создать ADMIN
make cleanup-sessions             # очистить старые сессии
make test       # frontend и backend тесты
make test-backend-integration     # integration tests в Docker
make lint       # ESLint и Ruff
make format     # форматирование
make typecheck  # TypeScript и mypy
make check      # основные проверки и production build frontend
```

## Health endpoints

`GET /health` проверяет только работающий FastAPI и отвечает `{"status":"ok","service":"api"}`. `GET /health/ready` выполняет `SELECT 1` к PostgreSQL и `PING` Redis; при недоступной зависимости возвращает `503` и безопасный структурированный ответ без адресов, паролей и stack trace. Эти два endpoint публичны. `GET /api/v1/system/status` требует активную сессию и завершённую смену временного пароля.

## Backend-авторизация

Сессия хранится серверно в PostgreSQL; клиент получает случайный session token только в `HttpOnly`, `SameSite=Lax` cookie, а в БД сохраняется его SHA-256 hash. CSRF token привязан к сессии, хранится в БД только как hash и передаётся в заголовке `X-CSRF-Token` для изменяющих запросов. Пароли хешируются Argon2id. Login ограничен Redis-счётчиком по hash нормализованного email и IP и fail-closed возвращает `503` при недоступном Redis.

Пользователь с временным паролем может вызвать только `/auth/me`, `/auth/change-password`, `/auth/logout` и публичные health endpoints. Административные `/users`, reset пароля, `/audit-logs` и `/system/status` требуют завершённой смены пароля; управление пользователями и аудит дополнительно требуют роли `ADMIN`.

## Структура

```text
apps/
  api/       FastAPI, Alembic и backend-тесты
  web/       Next.js App Router
docs/        утверждённая проектная документация
scripts/     проверки локального окружения
```

## Типовые проблемы запуска

- **Нет `.env`:** выполните `cp .env.example .env`.
- **Порт 3000 или 8000 занят:** освободите порт или измените проброс в `docker-compose.yml`.
- **`/health/ready` возвращает 503:** проверьте `docker compose logs api postgres redis`; API не выводит строки подключений в ответе.
- **Нет `uv` в PATH:** используйте путь из раздела требований либо добавьте каталог установки Python user scripts в `PATH`.

## Следующий подэтап

Подэтап 2.2B добавит только frontend для уже существующих auth/RBAC API. Telegram, AI и любые операции с лидами остаются за границами блока 2.2.
