"""Verify the agent docs stay one file rather than two that drift.

`AGENTS.md` is the source of truth and `CLAUDE.md` is a symlink to it, so that
Claude Code and Codex read the same rules. A copy would diverge the first time
someone edited one of them, and nothing would say so.

Also checks the skills under `.agents/skills/`: every one needs frontmatter a
tool can read, a `name` matching its directory, and an entry in the index —
a skill nothing lists is a skill nobody invokes.

    just check-agents
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "AGENTS.md"
LINK = "CLAUDE.md"
SKILLS = ROOT / ".agents" / "skills"
INDEX = ROOT / ".agents" / SOURCE

# Rules an agent will not read are rules that do not apply. The cap is a
# forcing function: something has to come out before something goes in.
MAX_LINES = 200

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def symlink_problems(directory: Path) -> list[str]:
    """`CLAUDE.md` beside an `AGENTS.md` must be a symlink to it, not a copy."""
    source, link = directory / SOURCE, directory / LINK
    where = source.relative_to(ROOT)

    if not source.exists():
        return [f"{where} is missing"]
    if not link.is_symlink():
        return [f"{link.relative_to(ROOT)} must be a symlink to {SOURCE}, not a copy — `ln -sf {SOURCE} {LINK}`"]
    if link.readlink().name != SOURCE:
        return [f"{link.relative_to(ROOT)} points at {link.readlink()}, not {SOURCE}"]
    return []


def skill_problems() -> list[str]:
    """Every skill needs readable frontmatter, a matching name, and an index entry."""
    if not SKILLS.is_dir():
        return []

    found: list[str] = []
    index = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""

    for directory in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        skill = directory / "SKILL.md"
        if not skill.exists():
            found.append(f"{directory.relative_to(ROOT)} has no SKILL.md")
            continue

        match = FRONTMATTER.match(skill.read_text(encoding="utf-8"))
        if match is None:
            found.append(f"{skill.relative_to(ROOT)} has no YAML frontmatter — tools discover skills by it")
            continue

        block = match.group(1)
        if f"name: {directory.name}" not in block:
            found.append(f"{skill.relative_to(ROOT)} frontmatter name does not match its directory, {directory.name}")
        if "description:" not in block:
            found.append(f"{skill.relative_to(ROOT)} frontmatter has no description — it is what a tool matches on")
        if directory.name not in index:
            found.append(f"{directory.name} is not listed in .agents/{SOURCE}")

    return found


def problems() -> list[str]:
    found = symlink_problems(ROOT)
    if not found:
        lines = (ROOT / SOURCE).read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            found.append(f"{SOURCE} is {len(lines)} lines, over the {MAX_LINES}-line cap")

    if (ROOT / ".agents" / SOURCE).exists():
        found += symlink_problems(ROOT / ".agents")
    found += skill_problems()
    return found


def main() -> int:
    found = problems()
    for problem in found:
        print(f"error: {problem}")
    if found:
        return 1

    skills = sorted(p.name for p in SKILLS.iterdir() if p.is_dir()) if SKILLS.is_dir() else []
    print(f"Agent docs OK — {LINK} → {SOURCE}, under {MAX_LINES} lines, {len(skills)} skills listed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
