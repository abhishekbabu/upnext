# Every recipe shells out to `uv`, which resolves the project venv itself —
# no .venv/bin activation, no shell dependency.

# List available recipes
default:
    @just --list

# ============================================================================
# Setup
# ============================================================================

# Create the venv, install the locked dependencies and the git hooks
install:
    uv sync
    uv run pre-commit install
    @echo "Ready. Copy .env.template to .env and add your TMDB key."

# Re-resolve the lockfile after changing dependencies in pyproject.toml
lock:
    uv lock
    uv sync

# ============================================================================
# Quality
# ============================================================================

# Everything CI runs
check: lint typecheck check-agents coverage-gate
    @echo "All checks passed."

# Lint and auto-fix, then format
fmt:
    uv run ruff check src/ tests/ scripts/ --fix
    uv run ruff format src/ tests/ scripts/

# Lint without fixing — fails on any finding
lint:
    uv run ruff check src/ tests/ scripts/
    uv run ruff format --check src/ tests/ scripts/

# Verify CLAUDE.md is still a symlink to AGENTS.md, and AGENTS.md still fits
check-agents:
    uv run python scripts/check_agent_docs.py

# Type check
typecheck:
    uv run pyrefly check

# Run the hermetic test suite
test *args:
    uv run pytest {{args}}

# Test suite with a coverage report
coverage:
    uv run pytest --cov --cov-report=term-missing

# Fail if coverage drops below the agreed floor
coverage-gate:
    uv run pytest --cov --cov-report=term-missing --cov-fail-under=95

# The tests that hit the live TMDB API (needs UPNEXT_TMDB_API_KEY)
test-integration:
    uv run pytest -m integration

# Run all hooks against every file, as pre-commit would
hooks:
    uv run pre-commit run --all-files

# ============================================================================
# Run
# ============================================================================

# Ingest a TV Time export folder into the library
import export_dir:
    uv run upnext import {{export_dir}}

# Resolve every imported title against TMDB
enrich *args:
    uv run upnext enrich {{args}}

# Summarise the library
stats:
    uv run upnext stats

# Report what this machine is configured for, and flag typo'd .env keys
doctor:
    uv run python scripts/doctor.py

# Serve the API on http://localhost:8000
serve:
    uv run upnext serve
