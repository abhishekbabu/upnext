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

# Everything CI runs for the Python side
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

# Move a season's watches to the TMDB title they belong to
move *args:
    uv run upnext move {{args}}

# Re-match recorded watches against stored episodes (no network)
relink:
    uv run upnext relink

# Summarise the library
stats:
    uv run upnext stats

# Report what this machine is configured for, and flag typo'd .env keys
doctor:
    uv run python scripts/doctor.py

# Build the UI and serve everything from one process (http://localhost:8000)
ui: web-build
    uv run upnext serve

# API only, reloading on change. Pair with `just web` in a second terminal.
serve:
    uv run upnext serve

# UI dev server with hot reload (http://localhost:5173), proxying /api to `just serve`
web:
    cd web && pnpm dev

# Install front-end dependencies
web-install:
    cd web && pnpm install

# Compile the UI into web/dist, which `ui` then serves
web-build: web-install
    cd web && pnpm build

# Lint, typecheck, test and build the front end — this is what CI runs
check-web: web-install
    cd web && pnpm lint
    cd web && pnpm exec tsc -b
    cd web && pnpm test
    # Builds because the bundle budget is checked by the build and nothing
    # else. Without this the recipe passes on a change CI then rejects.
    cd web && pnpm build
