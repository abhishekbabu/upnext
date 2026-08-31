"""Verify the agent docs stay one file rather than two that drift.

`AGENTS.md` is the source of truth and `CLAUDE.md` is a symlink to it, so that
Claude Code and Codex read the same rules. A copy would diverge the first time
someone edited one of them, and nothing would say so.

    just check-agents
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "AGENTS.md"
LINK = "CLAUDE.md"

# Rules an agent will not read are rules that do not apply. The cap is a
# forcing function: something has to come out before something goes in.
MAX_LINES = 200


def problems() -> list[str]:
    found = []
    source = ROOT / SOURCE
    link = ROOT / LINK

    if not source.exists():
        return [f"{SOURCE} is missing"]

    lines = source.read_text(encoding="utf-8").splitlines()
    if len(lines) > MAX_LINES:
        found.append(f"{SOURCE} is {len(lines)} lines, over the {MAX_LINES}-line cap")

    if not link.is_symlink():
        found.append(f"{LINK} must be a symlink to {SOURCE}, not a copy — `ln -sf {SOURCE} {LINK}`")
    elif link.readlink().name != SOURCE:
        found.append(f"{LINK} points at {link.readlink()}, not {SOURCE}")

    return found


def main() -> int:
    found = problems()
    for problem in found:
        print(f"error: {problem}")
    if found:
        return 1
    print(f"Agent docs OK — {LINK} → {SOURCE}, under {MAX_LINES} lines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
