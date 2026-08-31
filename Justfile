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

# Check lint and formatting without rewriting files (for CI)
lint_check:
    uv run ruff check
    uv run ruff format --check

# Run type checking (mypy + ty)
typecheck:
    uv run mypy
    uv run ty check

# Run tests (pytest)
test *ARGS:
    uv run pytest {{ ARGS }}

# Audit GitHub Actions workflows (zizmor)
audit:
    uv run zizmor .

# Run all checks (lint, typecheck, test, audit)
check: lint typecheck test audit

# What GitHub Actions runs: check, minus the file rewriting and the audit
# that the zizmor workflow already does online
ci: lint_check typecheck test

# Build the man page from its Markdown source (requires pandoc)
[unix]
build_man:
    mkdir -p data/share/man/man1
    pandoc docs/tublub.1.md -s -f markdown-smart -t man \
        -M footer="tublub $(uv version --short)" -M date="$(date -I)" \
        -o data/share/man/man1/tublub.1

# Build the package (sdist + wheel), man page included
[unix]
build: build_man
    uv build
