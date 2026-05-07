.PHONY: install test lint run docker-up docker-down migrate

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check app/ tests/
	ruff format --check app/ tests/

format:
	ruff format app/ tests/

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
