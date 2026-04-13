# plan-milestone

Analyse source planning and documentation artefacts for a NexTinyOS milestone, then
generate a complete set of structured implementation-detail plan documents following
the project standard.

## Input

The command accepts an optional milestone identifier argument (e.g. `R0012`, `R0013`).
If omitted, infer the milestone from the current branch name or ask the user.

$ARGUMENTS

## MCP Plugin Tools

This skill is backed by the **plan-milestone MCP server** (`plan_milestone_server.py`).
Call these tools at the steps indicated — they do the file I/O and validation so you
don't have to read/parse the files manually:

| Tool | When to call |
|------|-------------|
| `mcp__plan-milestone__hwcap_check` | Step 1 — get current bits and next available index |
| `mcp__plan-milestone__plan_template` | Step 1 — fetch latest completed milestone plans as templates |
| `mcp__plan-milestone__milestone_entry` | Step 1 — extract the target milestone's dev-plan entry |
| `mcp__plan-milestone__boot_sequence` | Step 1 — get kernel.c init order for slot placement |
| `mcp__plan-milestone__validate_plan_file` | Step 6 — validate content before writing |
| `mcp__plan-milestone__write_plan_file` | Step 7 — validate + write atomically |
| `mcp__plan-milestone__list_plan_files` | Any time — audit existing plan completeness |

## Procedure

### 1 — Gather source material

Call all four read tools **in parallel**:

```
mcp__plan-milestone__hwcap_check()
mcp__plan-milestone__plan_template()          # auto-detects latest complete milestone
mcp__plan-milestone__milestone_entry(milestone=<target>)
mcp__plan-milestone__boot_sequence()
```

Also read `docs/developer-manual.md` directly — it is too large for a tool and must
be read with the Read tool to extract section structure for the doc-update spec.

### 2 — Determine sub-phase split

Identify the natural implementation boundary that splits the milestone into exactly
**three sub-phases** (a / b / c) following this heuristic:

| Sub-phase | Character |
|-----------|-----------|
| **a** | Core detection / hardware init / new `HWCAP_*` bits; first diagnostic command |
| **b** | Routing / programming / mask-unmask shims; second diagnostic command |
| **c** | Higher-level driver; `nexlib` wrapper; master test suite; all doc updates |

Document the rationale for the split in the top-level plan's Sub-Phase Summary table.

### 3 — Create the top-level plan `.github/plan-RXXXX.md`

Sections (in order):

1. **Header** — branch name, prerequisite releases, next release.
2. **Prior Release Context** — bullet list (10–20 items) of constants, syscall
   numbers, struct fields, and decisions from the previous milestone that constrain
   this one. Facts only; no code blocks; no prose.
3. **Hardware Target** — matrix table (CPU family rows × feature columns); note if
   the release is a no-op on older hardware.
4. **New `HWCAP_*` bits** — table of bit name, value, and what it guards; assign
   consecutive bit positions after the last used bit in `hwcaps.h`.
5. **Overview** — 2–3 paragraph prose: what changes, why, fallback guarantee.
6. **Goals** — sub-sections for Kernel mechanisms, Shell commands (table with
   sub-phase column), NexLib, Documentation, Tests.
7. **New Constants & Symbols** — table: symbol, value, meaning.
8. **Architecture Changes to Document** — table: document, section, change.
9. **Test Results Target** — code block with per-suite pass counts and total;
   note all prior suites must remain green.
10. **Sub-Phase Summary** — table with links to `plan-RXXXXa.md` etc. and one-line
    summaries.

### 4 — Create sub-plan `.github/plan-RXXXXa.md`

Sections (in order):

1. **Header** — sub-phase title, branch, prerequisite.
2. **Prior Release Context** — same format as top-level; focus on facts directly
   relevant to this sub-phase.
3. **Overview** — what this sub-phase delivers and why it is self-contained.
4. **Kernel Implementation** — detailed design per new file:
   - Data structures (C struct definitions in code blocks).
   - Key function signatures with brief behavioural description.
   - Critical sequences (init order, register writes, MMIO patterns) in code blocks.
   - EOI / interrupt-path changes if any.
5. **Shell Commands** — for each new command: man-page-style usage, options table,
   example output block.
6. **Updated Commands** — what existing commands change and how.
7. **Implementation Standards** — cross-references to CLAUDE.md rules relevant to
   this sub-phase (hwcaps gating, stream layer, no-libc).
8. **Security** — any MMIO bounds, ACPI validation, or trust-boundary notes.
9. **Files Changed / Created** — table: file, new/modified, purpose.
10. **Test Coverage** — list of test groups, assertion counts, and what each covers.
11. **Commit Message** — verbatim `feat(RXXXXa): …` message to copy-paste.

### 5 — Create sub-plans b and c

Follow the same section template as sub-plan a. Sub-plan c **must also include**:

- **NexLib changes** — new functions, signature-stable upgrades, fallback behaviour.
- **Documentation update spec** — per-section instructions for `developer-manual.md`
  and `plan-developmentPlan.prompt.md`.
- **Master integration test suite** — full assertion list for the combined
  `tests/test_<topic>.c` file covering all three sub-phases (60+ assertions target).

### 6 — Validate before writing

For each document call `mcp__plan-milestone__validate_plan_file(content, sub_phase)`
where `sub_phase` is `""`, `"a"`, `"b"`, or `"c"`.

Fix every item in `errors` before proceeding. Review `warnings` and address any that
indicate real problems (style violations, low assertion counts).

Additionally verify manually:
- Prior-release context bullets reference real symbols visible in the template files.
- Every new shell command documents its `HWCAP_*` gate in the help text.

### 7 — Write files

Use `mcp__plan-milestone__write_plan_file(filename, content, sub_phase)` for each
document — it re-validates and writes atomically, refusing if errors remain.

Order:
1. `plan-RXXXX.md`  (sub_phase `""`)
2. `plan-RXXXXa.md` (sub_phase `"a"`)
3. `plan-RXXXXb.md` (sub_phase `"b"`)
4. `plan-RXXXXc.md` (sub_phase `"c"`)

Report the `lines` value returned by each write call.

### 8 — Branch and commit (only if user confirms)

Ask the user whether to also create the release branch and commit now.
If yes:
- Create branch `REL-XXXX` from `development`.
- `git add` the four plan files only (never add `.claude/` or unrelated files).
- Commit with message: `docs(RXXXX): add implementation plan — <one-line summary>`.
- Push with `-u origin REL-XXXX`.

## Output format

After all files are written, print a summary table:

| File | Lines | Sub-phase |
|------|-------|-----------|
| plan-RXXXX.md  | N | top-level |
| plan-RXXXXa.md | N | a |
| plan-RXXXXb.md | N | b |
| plan-RXXXXc.md | N | c |

Then list the new `HWCAP_*` bits introduced and the test assertion floor for each suite.
