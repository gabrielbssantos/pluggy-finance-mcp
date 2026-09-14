.PHONY: install check test run audit container container-smoke openapi-check
install:
	uv sync --frozen
check:
	uv run ruff check src scripts tests
	uv run ruff format --check src scripts tests
	uv run mypy
	uv run python scripts/check_openapi_drift.py
	uv run pytest -q
run:
	uv run --env-file .env python -m pluggy_finance_mcp
test:
	uv run pytest -q
audit:
	uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file /tmp/pluggy-requirements.txt
	uv run pip-audit -r /tmp/pluggy-requirements.txt
container:
	docker build -t pluggy-finance-mcp:local .
container-smoke:
	bash scripts/smoke_container.sh pluggy-finance-mcp:local
openapi-check:
	uv run python scripts/check_openapi_drift.py --remote
