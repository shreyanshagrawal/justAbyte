.PHONY: install lint format typecheck test check

install:
	pip install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src

test:
	pytest

check: lint typecheck test
