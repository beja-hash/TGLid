.DEFAULT_GOAL := help

.PHONY: help up down build logs migrate create-admin cleanup-sessions test test-backend-integration lint format typecheck check

help: ## Показать доступные команды
	@awk 'BEGIN {FS = ":.*##"}; /^[a-zA-Z_-]+:.*##/ {printf "%-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Запустить локальный стек в Docker
	@sh scripts/check-env.sh
	docker compose up --build

down: ## Остановить локальный Docker-стек
	docker compose down

build: ## Собрать Docker-образы
	@sh scripts/check-env.sh
	docker compose build

logs: ## Показать логи Docker-стека
	docker compose logs -f

migrate: ## Применить Alembic-миграции в запущенном API-контейнере
	docker compose exec api uv run --no-sync alembic upgrade head

create-admin: ## Создать первого администратора: make create-admin EMAIL=... NAME="..."
	docker compose exec -it api uv run --no-sync python -m app.cli create-admin "$(EMAIL)" "$(NAME)"

cleanup-sessions: ## Удалить истёкшие и давно отозванные сессии
	docker compose exec api uv run --no-sync python -m app.cli cleanup-sessions

test: ## Запустить тесты frontend и backend локально
	pnpm --dir apps/web test
	cd apps/api && /Users/user/Library/Python/3.12/bin/uv run pytest

test-backend-integration: ## Запустить auth-интеграционные тесты в изолированной PostgreSQL
	docker compose up -d postgres redis
	docker compose exec -T postgres sh -c 'if [ -z "$$(psql -U "$$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='\''tglid_test'\''")" ]; then createdb -U "$$POSTGRES_USER" tglid_test; fi'
	docker compose --profile test run --build --rm api-test

lint: ## Запустить ESLint и Ruff
	pnpm --dir apps/web lint
	cd apps/api && /Users/user/Library/Python/3.12/bin/uv run ruff check .

format: ## Отформатировать исходный код
	pnpm --dir apps/web format
	cd apps/api && /Users/user/Library/Python/3.12/bin/uv run ruff format .

typecheck: ## Запустить TypeScript и mypy
	pnpm --dir apps/web typecheck
	cd apps/api && /Users/user/Library/Python/3.12/bin/uv run mypy

check: lint typecheck test ## Выполнить основные локальные проверки
	pnpm --dir apps/web build
