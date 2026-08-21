# Database migration tasks (uv + Alembic)
#
#   make db-create-migration MESSAGE="add users table"
#   make db-upgrade
#   make db-downgrade
#   make db-history
#   make db-current
#   make db-stamp REV=head
#
# Test tasks (uv + pytest)
#
#   make test              run the default suite (fast, no external deps)
#   make test-verbose      run with -v for per-test output
#   make test-coverage     run with coverage (terminal + HTML + XML), 80% gate
#   make test-integration  run integration tests (real APIs, opt-in)
#   make test-performance  run performance tests (timing budgets, opt-in)
#   make test-postgres     run PostgreSQL-backed tests (TEST_DATABASE_URL)

.PHONY: db-create-migration db-upgrade db-downgrade db-history db-current db-stamp
.PHONY: test test-verbose test-coverage test-integration test-performance test-postgres

MESSAGE ?= "migration description"
REV ?= -1

db-create-migration:
	uv run alembic revision --autogenerate -m "$(MESSAGE)"

db-upgrade:
	uv run alembic upgrade head

db-downgrade:
	uv run alembic downgrade $(REV)

db-history:
	uv run alembic history --verbose

db-current:
	uv run alembic current

db-stamp:
	uv run alembic stamp $(REV)

test:
	uv run pytest

test-verbose:
	uv run pytest -v

test-coverage:
	uv run pytest --cov=app --cov-report=term-missing --cov-report=html --cov-report=xml

test-integration:
	uv run pytest --run-integration

test-performance:
	uv run pytest --run-performance

test-postgres:
	uv run pytest -m postgres