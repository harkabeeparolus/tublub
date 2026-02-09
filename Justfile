# List available recipes
default:
    @just --list

# Run the tool (pass extra args like: just run -- --list)
run *ARGS:
    uv run tublub {{ ARGS }}

# Run linter with auto-fix and formatter
lint:
    uv run ruff check --fix
    uv run ruff format

# Run type checking (mypy + ty)
typecheck:
    uv run mypy --ignore-missing-imports src
    uv run ty check

# Run tests (pytest)
test *ARGS:
    uv run pytest {{ ARGS }}

# Run all checks (lint, typecheck, test)
check: lint typecheck test
