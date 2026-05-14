.PHONY: install test lint typecheck ci run docker-up docker-down migrate \
        prod-up prod-down prod-logs prod-restart prod-ps prod-stats

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check app/ tests/
	ruff format --check app/ tests/

format:
	ruff format app/ tests/

typecheck:
	mypy app/

ci: lint typecheck test

run:
	python -m app.main

migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(msg)"

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

# ── Production (docker-compose.prod.yml) ──────────────────────────────────────
prod-up:
	docker compose -f docker-compose.prod.yml up -d --build

prod-down:
	docker compose -f docker-compose.prod.yml down

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f app

prod-restart:
	docker compose -f docker-compose.prod.yml restart app

prod-ps:
	docker compose -f docker-compose.prod.yml ps

prod-stats:
	docker stats
