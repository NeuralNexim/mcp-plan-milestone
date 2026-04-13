# mcp-plan-milestone

A [Model Context Protocol](https://modelcontextprotocol.io) server and
[Claude Code](https://claude.ai/code) skill that automates milestone
implementation-plan document generation.

Given a project roadmap and existing plan templates, the `/plan-milestone` skill
produces a complete set of structured plan documents — top-level plan plus three
sub-phase plans (a/b/c) — with validation built in.

**Project-agnostic.** Works with any codebase that keeps plan documents in
`.github/` (or a similar directory) and has a roadmap file. All file paths are
auto-detected or can be overridden as parameters.

---

## Tools provided

| Tool | Purpose |
|------|---------|
| `capability_check` | Parse a feature-flag / capability header for current bit assignments and next free slot; falls back to `nm` on compiled objects if the header doesn't exist yet |
| `plan_template` | Return the latest complete milestone's plan files as template text |
| `milestone_entry` | Extract a milestone's block from the project roadmap file |
| `init_sequence` | Parse the application entry point for the ordered init call list |
| `validate_plan_file` | Check required headings, code-block style, capability-bit collisions, assertion count floors |
| `write_plan_file` | Validate then write a plan file atomically — refuses if errors remain |
| `list_plan_files` | Audit all existing plan files and completeness of each milestone set |

All path parameters have sensible defaults and auto-detect the project structure.
Override any of them explicitly when the defaults don't match your layout.

---

## Requirements

- Python 3.10+
- `mcp >= 1.27.0`
- [Claude Code CLI](https://claude.ai/code)

---

## Installation

### 1 — Clone and install dependencies

```bash
git clone https://github.com/NeuralNexim/mcp-plan-milestone
cd mcp-plan-milestone
pip install -r requirements.txt
```

### 2 — Register the MCP server

Add to `~/.claude/settings.json` (user-global, works in every project):

```json
{
  "mcpServers": {
    "plan-milestone": {
      "type": "stdio",
      "command": "python3",
      "args": ["/absolute/path/to/mcp-plan-milestone/plan_milestone_server.py"]
    }
  }
}
```

Or register it only for a specific project in `.claude/settings.json` at the repo
root — use a relative path so teammates don't need to edit it:

```json
{
  "mcpServers": {
    "plan-milestone": {
      "type": "stdio",
      "command": "python3",
      "args": [".claude/mcp/plan_milestone_server.py"]
    }
  }
}
```

### 3 — Install the slash command skill

```bash
# User-global — available in every project
cp skill/plan-milestone.md ~/.claude/commands/plan-milestone.md

# Or project-local — only in this repo
cp skill/plan-milestone.md /your/project/.claude/commands/plan-milestone.md
```

### 4 — Restart Claude Code

Reload the Claude Code session so the MCP server and skill are picked up.

---

## Usage

```
/plan-milestone R0013
/plan-milestone v3.0
/plan-milestone PHASE-4
```

Claude will:

1. Call all four read tools in parallel to gather source material
2. Determine the a/b/c sub-phase split and explain its rationale
3. Draft all four plan documents following your project's existing format
4. Validate each document (required headings, code style, capability-bit collisions,
   assertion count floors ≥ 30/30/60)
5. Write the files — refuses if validation errors remain
6. Optionally create the release branch, commit, and push — after your confirmation

---

## Project structure expected

The server auto-detects the repo root by looking for `.github/`, `CLAUDE.md`,
`Makefile`, `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, etc.

```
.github/                          ← default plan directory
  plan-RXXXX.md                   ← existing milestone plans (used as templates)
  plan-RXXXXa.md
  plan-RXXXXb.md
  plan-RXXXXc.md
  prompts/
    plan-developmentPlan.prompt.md ← roadmap (auto-detected; one of several candidates)
```

**Roadmap / dev-plan** — auto-detected at these locations (first found wins):
- `.github/prompts/plan-developmentPlan.prompt.md`
- `.github/ROADMAP.md`
- `ROADMAP.md`
- `docs/roadmap.md`
- `docs/development-plan.md`
- Any `*.prompt.md` in `.github/prompts/`

**Capability header** — auto-detected at:
- `kernel/hwcaps.h`, `include/caps.h`, `include/features.h`, `src/caps.h`, etc.
- Any `hwcaps.h`, `caps.h`, `features.h`, `feature_flags.h` found outside
  `build/` and `vendor/`

**Init / main file** — auto-detected at:
- `kernel/kernel.c`, `src/main.c`, `main.c`, `src/main.rs`, `src/main.go`, etc.

Override any path by passing it explicitly to the tool:

```
mcp__plan-milestone__capability_check(header_path="src/platform/caps.h")
mcp__plan-milestone__milestone_entry(milestone="v3.0", dev_plan_path="docs/roadmap.md")
mcp__plan-milestone__init_sequence(init_file_path="src/runtime/boot.rs")
```

---

## Validation rules

`validate_plan_file` checks:

| Check | Detail |
|-------|--------|
| Required headings | Prior Release Context, Overview, Goals/Implementation, Files, Test Coverage, Commit Message (per sub-phase) |
| Code style — C | No `size_t`, no stdlib includes, no tabs, brace-on-same-line |
| Code style — other | Pass `language=""` to skip, or `extra_forbidden_tokens` to add project-specific rules |
| Capability-bit collision | Bits cited below the next free index and absent from the header are flagged |
| Assertion count floor | Sub-plan a ≥ 30, b ≥ 30, c ≥ 60 |

---

## License

MIT
