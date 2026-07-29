PYTHON ?= python

.PHONY: install dev format lint typecheck test test-unit test-integration coverage migrate migration db-check workbook-check smoke run clean

install:
	$(PYTHON) -m pip install -e .

dev:
	$(PYTHON) -m pip install -e ".[dev]"

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

lint:
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy openleadkit scripts

test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest tests/unit

test-integration:
	$(PYTHON) -m pytest -m integration tests/integration

coverage:
	$(PYTHON) -m pytest tests/unit --cov=openleadkit --cov-report=term-missing --cov-report=xml

migrate:
	$(PYTHON) -m alembic upgrade head

migration:
	$(PYTHON) -m alembic revision --autogenerate -m "$(message)"

db-check:
	$(PYTHON) scripts/check_database.py

workbook-check:
	$(PYTHON) scripts/inspect_workbook.py

smoke:
	$(PYTHON) scripts/smoke_test.py

run:
	$(PYTHON) -m streamlit run app.py

clean:
	find . -type d -name __pycache__ -prune -exec rm -r {} +
	find . -type d -name .pytest_cache -prune -exec rm -r {} +
	find . -type d -name .mypy_cache -prune -exec rm -r {} +
	find . -type d -name .ruff_cache -prune -exec rm -r {} +
	rm -f .coverage coverage.xml
