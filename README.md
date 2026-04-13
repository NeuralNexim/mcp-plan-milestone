# mcp-plan-milestone

A [Model Context Protocol](https://modelcontextprotocol.io) server and Claude Code
skill that automates milestone implementation-plan document generation for
[NexTinyOS](https://github.com/NeuralNexim/NexTinyOS)-style projects.

Given a development plan prompt and developer manual, it produces a complete set of
structured plan documents (`plan-RXXXX.md` + `plan-RXXXXa/b/c.md`) following the
project's established format — with hardware capability gating, HWCAP bit collision
detection, C style validation, and assertion count enforcement.

---

## Tools provided

| Tool | Purpose |
|------|---------|
| `hwcap_check` | Parse `kernel/hwcaps.h` for current `HWCAP_*` bits and next available index; falls back to CLAUDE.md known bits when the header doesn't exist yet |
| `plan_template` | Return the latest complete milestone's plan files as template text |
| `milestone_entry` | Extract a milestone's block from `plan-developmentPlan.prompt.md` |
| `boot_sequence` | Parse `kernel/kernel.c` `main()` for the ordered `*_init()` call list |
| `validate_plan_file` | Check required headings, C style, HWCAP collisions, assertion count floors |
| `write_plan_file` | Validate then write a plan file atomically — refuses if errors remain |
| `list_plan_files` | Audit all existing plan files and their completeness |

---

## Requirements

- Python 3.10+
- `mcp >= 1.27.0`
- Claude Code CLI (for the `/plan-milestone` skill)

---

## Installation

### 1 — Clone and install dependencies

```bash
git clone https://github.com/NeuralNexim/mcp-plan-milestone
cd mcp-plan-milestone
pip install -r requirements.txt
```

### 2 — Register the MCP server

Add to `~/.claude/settings.json` (user-global) **or** your project's
`.claude/settings.json`:

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

> **Tip — project-local install:** if you clone this repo into your project under
> `.claude/mcp/`, use a relative path:
> ```json
> "args": [".claude/mcp/plan_milestone_server.py"]
> ```

### 3 — Install the slash command skill

Copy the skill file to your Claude Code commands directory:

```bash
# User-global (available in every project)
cp skill/plan-milestone.md ~/.claude/commands/plan-milestone.md

# Or project-local (available only in this repo)
cp skill/plan-milestone.md /your/project/.claude/commands/plan-milestone.md
```

### 4 — Restart Claude Code

Reload the Claude Code session so the new MCP server and skill are picked up.

---

## Usage

```
/plan-milestone R0013
```

Claude will:

1. Call all four read tools in parallel to gather source material
2. Determine the a/b/c sub-phase split
3. Draft all four plan documents
4. Validate each document (style, HWCAP bits, assertion counts)
5. Write the files via `write_plan_file` (refuses if validation errors remain)
6. Optionally create the release branch, commit, and push — after your confirmation

---

## Project structure expected

The server auto-detects the repo root by looking for `kernel/kernel.c` or
`kernel/shell_cmd.h`. It expects:

```
.github/
  prompts/plan-developmentPlan.prompt.md
  plan-RXXXX.md   (existing completed milestone plans — used as templates)
  plan-RXXXXa.md
  plan-RXXXXb.md
  plan-RXXXXc.md
docs/
  developer-manual.md
kernel/
  hwcaps.h        (optional — falls back to CLAUDE.md known bits if absent)
  kernel.c
```

---

## License

MIT
