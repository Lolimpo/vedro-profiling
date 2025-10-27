PROJECT_NAME=vedro_profiling

.PHONY: install
install:
	uv sync --group dev

.PHONY: sort-imports
sort-imports:
	uv run ruff check --fix ${PROJECT_NAME}

.PHONY: lint
lint:
	uv run mypy ${PROJECT_NAME} --strict
	uv run ruff check --fix ${PROJECT_NAME}

.PHONY: all
all: install lint test

.PHONY: clean
clean:
	rm -rf dist/
