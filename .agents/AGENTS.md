# Skills

Shared agent skills for this repo. Every skill is a directory under `skills/`
containing a `SKILL.md` with YAML frontmatter (`name`, `description`).

Tools discover these through a symlink rather than a copy, so there is one
source of truth:

- Claude Code — `.claude/skills` → `.agents/skills`
- Codex — reads the root `AGENTS.md` natively

## Available skills

- **`improve`** — survey the repo as a senior advisor and write self-contained
  implementation plans for another agent to execute. Read-only on source:
  `skills/improve/SKILL.md`
- **`review-tests`** — audit tests for quality and hygiene, and the guidelines
  to write them by: `skills/review-tests/SKILL.md`
- **`thermo-nuclear-code-quality-review`** — an unusually strict maintainability
  review: abstraction quality, oversized files, spaghetti-condition growth:
  `skills/thermo-nuclear-code-quality-review/SKILL.md`

Every skill's rules cite this repo's own layering, its counts, its migrations
and its front end. Keep them that way: a rule illustrated with someone else's
example stops being read.

## Conventions

- `AGENTS.md` is the source of truth; `CLAUDE.md` beside it is a symlink to it.
  Never edit `CLAUDE.md` — it is the same file.
- Every `AGENTS.md` needs a tracked sibling `CLAUDE.md` symlink, and the root
  one must stay under 200 lines. `just check-agents` enforces both, plus that
  every skill has frontmatter with a `name` matching its directory.
