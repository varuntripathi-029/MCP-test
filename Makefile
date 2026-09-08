.PHONY: install browsers test test-unit test-ui test-mcp test-ai test-fast lint typecheck

install:
	pip install -r requirements.txt

browsers:
	playwright install --with-deps chromium

test:
	pytest

test-ui:
	pytest -m ui

test-mcp:
	pytest -m mcp

test-ai:
	pytest -m ai

test-fast:
	pytest -m "not ai and not slow"

test-unit:
	pytest tests/unit

lint:
	ruff check .

typecheck:
	mypy --ignore-missing-imports .
