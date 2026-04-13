# plan-milestone

Analyse a project's roadmap and existing plan documents, then generate a complete
set of structured implementation-detail plan files for the next milestone
(top-level plan + three sub-plans: a, b, c).

Works with any project that keeps plan documents in `.github/` (or a similar
plans directory) and has a roadmap / development-plan file somewhere in the repo.

## Input

Optional milestone identifier (e.g. `R0013`, `v3.0`, `PHASE-4`).
If omitted, the milestone is inferred from the current branch name or you are
asked to confirm.

$ARGUMENTS

## MCP Plugin Tools

This skill is backed by the **plan-milestone MCP server**.
Call these tools at the steps indicated:

| Tool | When to call |
|------|-------------|
| `mcp__plan-milestone__capability_check` | Step 1 — get current feature-flag bits and next free slot |
| `mcp__plan-milestone__plan_template` | Step 1 — fetch latest complete milestone plans as templates |
| `mcp__plan-milestone__milestone_entry` | Step 1 — extract the target milestone's roadmap entry |
| `mcp__plan-milestone__init_sequence` | Step 1 — get the startup init call order |
| `mcp__plan-milestone__validate_plan_file` | Step 6 — validate content before writing |
| `mcp__plan-milestone__write_plan_file` | Step 7 — validate + write atomically |
| `mcp__plan-milestone__list_plan_files` | Any time — audit existing plan completeness |

All four read tools in Step 1 are independent — call them **in parallel**.

## Procedure

### 1 — Gather source material

Call in parallel:
```
mcp__plan-milestone__capability_check()
mcp__plan-milestone__plan_template()
mcp__plan-milestone__milestone_entry(milestone=<target>)
mcp__plan-milestone__init_sequence()
```

Also read the project's developer / API documentation directly (it is typically
too large for a single tool call) to extract section structure for the doc-update
spec in sub-plan c.

### 2 — Determine the sub-phase split

Divide the milestone into exactly **three sub-phases** (a / b / c):

| Sub-phase | Typical character |
|-----------|------------------|
| **a** | Detection / capability init / first new feature flag; first diagnostic |
| **b** | Routing / programming / adapter shims; second diagnostic |
| **c** | Higher-level integration; library wrappers; master test suite; all doc updates |

Adapt the split to the project's domain — the principle is that each sub-phase is
independently reviewable and testable. Document the rationale in the top-level
plan's Sub-Phase Summary table.

### 3 — Draft the top-level plan

Sections (in order):

1. **Header** — branch, prerequisite releases, next release.
2. **Prior Release Context** — bullet list (10–20 items) of constants, API symbols,
   struct fields, and decisions from the previous milestone that constrain this one.
   Facts only; no code blocks.
3. **Platform / Hardware Target** — matrix or list of supported targets; note if the
   release is a no-op on older/simpler targets.
4. **New Feature Flags** — table of flag name, value, and what it guards (if the
   project uses capability or feature bits).
5. **Overview** — 2–3 paragraphs: what changes, why, fallback guarantee.
6. **Goals** — sub-sections: Core mechanisms, CLI commands (table with sub-phase
   column), Library / SDK changes, Documentation, Tests.
7. **New Constants & Symbols** — table: symbol, value, meaning.
8. **Architecture Changes to Document** — table: document, section, change.
9. **Test Results Target** — code block with per-suite pass counts and total;
   note all prior suites must remain green.
10. **Sub-Phase Summary** — table with links to sub-plan files and one-line summaries.

### 4 — Draft sub-plan a

Sections (in order):

1. **Header** — sub-phase title, branch, prerequisite.
2. **Prior Release Context** — same format; focus on facts relevant to this sub-phase.
3. **Overview** — what this sub-phase delivers and why it is self-contained.
4. **Implementation** — detailed design per new file or module:
   - Data structures and key types (code blocks in the project's language).
   - Key function / method signatures with brief behavioural description.
   - Critical sequences (init order, register writes, protocol steps) in code blocks.
   - Any interrupt / event-path or concurrency changes.
5. **CLI / Shell Commands** — for each new command: usage synopsis, options table,
   example output block.
6. **Updated Existing Components** — what changes and how.
7. **Implementation Standards** — cross-reference to project style rules relevant
   to this sub-phase (capability gating, IO abstraction, language constraints).
8. **Security** — trust boundaries, input validation, access control notes.
9. **Files Changed / Created** — table: file, new/modified, purpose.
10. **Test Coverage** — test groups, assertion counts, what each covers.
11. **Commit Message** — verbatim commit message to copy-paste.

### 5 — Draft sub-plans b and c

Follow the same section template as sub-plan a.

Sub-plan c **must also include**:

- **Library / SDK changes** — new public functions, signature-stable upgrades,
  fallback behaviour when the new feature is absent.
- **Documentation update spec** — per-section instructions for each doc file that
  needs updating.
- **Master integration test suite** — full assertion list for the combined test
  file covering all three sub-phases (target: 60+ assertions).

### 6 — Validate before writing

For each document call:
```
mcp__plan-milestone__validate_plan_file(content, sub_phase, language,
                                        extra_forbidden_tokens)
```

Fix every item in `errors`. Review `warnings` and address any real problems.
Verify manually:
- Prior-context bullets reference real symbols visible in the template files.
- Every new CLI command documents its capability-gate or prerequisite.
- Assertion count floors: a ≥ 30, b ≥ 30, c ≥ 60, total ≥ 120.

### 7 — Write files

Use `mcp__plan-milestone__write_plan_file` for each document:

1. `plan-<TAG>.md`   — top-level (sub_phase `""`)
2. `plan-<TAG>a.md`  — sub-phase a
3. `plan-<TAG>b.md`  — sub-phase b
4. `plan-<TAG>c.md`  — sub-phase c

Report the `lines` value returned by each write call.

### 8 — Branch and commit (only if user confirms)

Ask the user whether to also create the release branch and commit now.
If yes:
- Create branch `REL-<TAG>` (or the project's equivalent) from the integration branch.
- Stage the four plan files only.
- Commit with message: `docs(<TAG>): add implementation plan — <one-line summary>`.
- Push with `-u origin <branch>`.

## Output format

After all files are written, print a summary table:

| File | Lines | Sub-phase |
|------|-------|-----------|
| plan-TAG.md  | N | top-level |
| plan-TAGa.md | N | a |
| plan-TAGb.md | N | b |
| plan-TAGc.md | N | c |

Then list any new capability / feature-flag bits introduced and the test assertion
floor for each suite.
