# Database migration tasks (uv + Alembic)
#
#   make db-create-migration MESSAGE="add users table"
#   make db-upgrade
#   make db-downgrade
#   make db-history
#   make db-current
#   make db-stamp REV=head

.PHONY: db-create-migration db-upgrade db-downgrade db-history db-current db-stamp

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