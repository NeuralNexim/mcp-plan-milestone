#!/usr/bin/env python3
"""
MCP server: plan-milestone plugin
Provides tools that support the /plan-milestone skill in NexTinyOS.
"""

import os
import re
import glob
import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("plan-milestone")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Return the NexTinyOS repo root (or cwd if not detectable)."""
    cwd = Path.cwd()
    sentinels = ("kernel/kernel.c", "kernel/shell_cmd.h", "Makefile")
    for p in [cwd, *cwd.parents]:
        if any((p / s).exists() for s in sentinels):
            return p
    return cwd


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# Tool: hwcap_check
# ---------------------------------------------------------------------------

@mcp.tool()
def hwcap_check() -> dict:
    """
    Parse kernel/hwcaps.h and return:
      - current_bits: list of {name, value, hex} for every HWCAP_* define
      - next_bit_index: integer index (e.g. 4 means next is 1<<4)
      - next_bit_value: hex string (e.g. "0x10")
      - raw_snippet: the relevant lines from hwcaps.h

    Use this before assigning new HWCAP_* values to avoid collisions.
    """
    root = _repo_root()
    src = _read(root / "kernel" / "hwcaps.h")
    bits = []
    source = "kernel/hwcaps.h"

    if src:
        pattern = re.compile(r"#define\s+(HWCAP_\w+)\s+\(1\s*<<\s*(\d+)\)")
        for m in pattern.finditer(src):
            name, idx = m.group(1), int(m.group(2))
            bits.append({"name": name, "bit_index": idx, "value": 1 << idx,
                         "hex": f"0x{1 << idx:02X}"})
    else:
        # hwcaps.h not yet created (pre-implementation branch).
        # Try extracting HWCAP symbols from build/hwcaps.o via nm.
        source = "build/hwcaps.o (nm fallback — hwcaps.h not yet created)"
        obj = root / "build" / "hwcaps.o"
        if obj.exists():
            import subprocess
            try:
                nm_out = subprocess.check_output(["nm", str(obj)],
                                                  stderr=subprocess.DEVNULL,
                                                  text=True)
                # nm won't give us #define values; report what's known from plan docs
            except Exception:
                pass
        # Fall back to known R0011 constants (documented in CLAUDE.md)
        known = [
            ("HWCAP_CPUID", 0), ("HWCAP_FPU", 1),
            ("HWCAP_FXSR", 2), ("HWCAP_SSE", 3),
        ]
        for name, idx in known:
            bits.append({"name": name, "bit_index": idx, "value": 1 << idx,
                         "hex": f"0x{1 << idx:02X}"})
        source += " + CLAUDE.md known bits"

    bits.sort(key=lambda b: b["bit_index"])
    next_idx = (bits[-1]["bit_index"] + 1) if bits else 0
    next_val = 1 << next_idx

    snippet_lines = [l for l in src.splitlines() if "HWCAP_" in l or "hwcaps" in l.lower()] if src else []
    return {
        "source": source,
        "current_bits": bits,
        "next_bit_index": next_idx,
        "next_bit_value": f"0x{next_val:02X}",
        "next_bit_define": f"(1 << {next_idx})",
        "raw_snippet": "\n".join(snippet_lines),
        "note": "" if src else "hwcaps.h will be created in R0012a; current_bits derived from CLAUDE.md",
    }


# ---------------------------------------------------------------------------
# Tool: plan_template
# ---------------------------------------------------------------------------

@mcp.tool()
def plan_template(milestone: str = "") -> dict:
    """
    Return the plan files for the most recently completed milestone as
    template text. If `milestone` is given (e.g. "R0011") that specific
    milestone's files are returned; otherwise the highest-numbered complete
    set is auto-detected.

    Returns a dict with keys: top_level, sub_a, sub_b, sub_c.
    Each value is the full file text (empty string if not found).
    """
    root = _repo_root()
    github = root / ".github"

    if milestone:
        tag = milestone.upper().lstrip("R").lstrip("0") or "0"
        tag = f"R{int(tag):04d}" if tag.isdigit() else milestone.upper()
    else:
        # find highest complete set (top + a + b + c all exist)
        tops = sorted(github.glob("plan-R????.md"))
        tag = None
        for top in reversed(tops):
            m = re.search(r"plan-(R\d{4})\.md$", top.name)
            if not m:
                continue
            t = m.group(1)
            if all((github / f"plan-{t}{s}.md").exists() for s in ("a", "b", "c")):
                tag = t
                break
        if tag is None:
            return {"error": "No complete milestone plan set found in .github/"}

    def _r(suffix):
        fname = f"plan-{tag}{suffix}.md"
        return _read(github / fname)

    return {
        "milestone": tag,
        "top_level": _r(""),
        "sub_a":     _r("a"),
        "sub_b":     _r("b"),
        "sub_c":     _r("c"),
    }


# ---------------------------------------------------------------------------
# Tool: milestone_entry
# ---------------------------------------------------------------------------

@mcp.tool()
def milestone_entry(milestone: str) -> dict:
    """
    Extract the roadmap entry for `milestone` (e.g. "R0012") from
    .github/prompts/plan-developmentPlan.prompt.md.

    Returns:
      - entry_text: the relevant block of text
      - file_list: lines that look like file paths within that block
      - nexlib_goals: lines mentioning nexlib within that block
    """
    root = _repo_root()
    src = _read(root / ".github" / "prompts" / "plan-developmentPlan.prompt.md")
    if not src:
        return {"error": "plan-developmentPlan.prompt.md not found"}

    tag = milestone.upper()
    # Find the section header for this milestone and grab until the next one
    section_re = re.compile(
        rf"(#+\s+.*?{re.escape(tag)}.*?)(?=\n#+\s+[A-Z]|\Z)", re.DOTALL
    )
    m = section_re.search(src)
    if not m:
        # Fallback: grab 120 lines surrounding first occurrence
        idx = src.find(tag)
        if idx == -1:
            return {"error": f"{tag} not found in development plan"}
        start = max(0, src.rfind("\n", 0, idx) - 200)
        end = min(len(src), idx + 3000)
        entry = src[start:end]
    else:
        entry = m.group(0)

    file_lines = [l.strip() for l in entry.splitlines()
                  if re.search(r"[a-z_/]+\.[ch]", l)]
    nexlib_lines = [l.strip() for l in entry.splitlines()
                    if "nexlib" in l.lower()]

    return {
        "milestone": tag,
        "entry_text": entry,
        "file_list": file_lines,
        "nexlib_goals": nexlib_lines,
    }


# ---------------------------------------------------------------------------
# Tool: boot_sequence
# ---------------------------------------------------------------------------

@mcp.tool()
def boot_sequence() -> dict:
    """
    Extract the kernel init sequence from kernel/kernel.c (the main()
    function body) so that new *_init() calls can be slotted in at the
    correct position.

    Returns:
      - init_calls: ordered list of *_init() / subsystem calls found in main()
      - raw_main: full text of the main() function
    """
    root = _repo_root()
    src = _read(root / "kernel" / "kernel.c")
    if not src:
        return {"error": "kernel/kernel.c not found"}

    # Extract main() body
    m = re.search(r"\bvoid\s+main\s*\(.*?\)\s*\{", src)
    if not m:
        m = re.search(r"\bint\s+main\s*\(.*?\)\s*\{", src)
    if not m:
        return {"error": "main() not found in kernel.c", "src_preview": src[:500]}

    start = m.end()
    depth = 1
    pos = start
    while pos < len(src) and depth:
        if src[pos] == "{":
            depth += 1
        elif src[pos] == "}":
            depth -= 1
        pos += 1
    raw_main = src[m.start():pos]

    init_re = re.compile(r"\b(\w+_init|hwcaps_probe|pic_init|pit_init|scheduler_\w+)\s*\(")
    calls = []
    for lm in init_re.finditer(raw_main):
        line_no = src[:m.start() + (lm.start() - len(src[m.start():lm.start()]) + lm.start() - m.start())].count("\n") + 1
        calls.append(lm.group(0).rstrip("("))

    return {
        "init_calls": calls,
        "raw_main": raw_main,
    }


# ---------------------------------------------------------------------------
# Tool: validate_plan_file
# ---------------------------------------------------------------------------

@mcp.tool()
def validate_plan_file(content: str, sub_phase: str = "") -> dict:
    """
    Validate a plan document before writing it to disk.
    `content` is the full markdown text; `sub_phase` is "", "a", "b", or "c".

    Checks:
      - Required section headings are present
      - Code blocks use correct C style (no size_t, no tabs, brace-on-same-line)
      - HWCAP values cited in the text don't collide with existing bits
      - Test assertion count floor: top≥0, a≥30, b≥30, c≥60
      - No forbidden libc includes (#include <string.h> etc.)

    Returns: {valid: bool, errors: [...], warnings: [...]}
    """
    errors = []
    warnings = []

    # Required headings per document type
    required_headings = {
        "":  ["Prior Release Context", "Hardware Target", "Overview", "Goals",
              "New Constants", "Test Results", "Sub-Phase Summary"],
        "a": ["Prior Release Context", "Overview", "Kernel Implementation",
              "Shell Commands", "Files", "Test Coverage", "Commit Message"],
        "b": ["Prior Release Context", "Overview", "Kernel Implementation",
              "Shell Commands", "Files", "Test Coverage", "Commit Message"],
        "c": ["Prior Release Context", "Overview", "Kernel Implementation",
              "NexLib", "Documentation", "Files", "Test Coverage", "Commit Message"],
    }
    for heading in required_headings.get(sub_phase, []):
        if heading.lower() not in content.lower():
            errors.append(f"Missing required section: '{heading}'")

    # C code block style checks
    code_blocks = re.findall(r"```c(.*?)```", content, re.DOTALL)
    for i, block in enumerate(code_blocks):
        if "size_t" in block:
            errors.append(f"Code block {i+1}: uses 'size_t' — use 'unsigned int' instead")
        if re.search(r"\t", block):
            errors.append(f"Code block {i+1}: contains tab — use 4-space indentation")
        if re.search(r"#include\s*<(string|stdlib|stdio|stddef)\.h>", block):
            errors.append(f"Code block {i+1}: forbidden libc include")
        # brace-on-same-line check: detect function definitions with brace on next line
        if re.search(r"\)\s*\n\s*\{", block):
            warnings.append(f"Code block {i+1}: opening brace may be on its own line — style requires same-line brace")

    # HWCAP collision check
    hwcap_mentions = re.findall(r"1\s*<<\s*(\d+)", content)
    existing = hwcap_check()
    if "current_bits" in existing:
        used_indices = {b["bit_index"] for b in existing["current_bits"]}
        next_idx = existing["next_bit_index"]
        for idx_str in hwcap_mentions:
            idx = int(idx_str)
            if idx < next_idx and idx in used_indices:
                # It's referencing an existing bit — not a collision unless it claims to be new
                pass  # allowed: referencing existing bits
            elif idx < next_idx and idx not in used_indices:
                warnings.append(f"Bit index {idx} (1<<{idx}) is below next_bit_index={next_idx} and not in hwcaps.h — verify intentional")

    # Test assertion count floor
    count_matches = re.findall(r"(\d+)\+?\s*/\s*(\d+)\+?", content)
    min_floor = {"": 0, "a": 30, "b": 30, "c": 60}.get(sub_phase, 0)
    if min_floor:
        counts = [int(m[0]) for m in count_matches if int(m[0]) >= 1]
        if counts:
            if max(counts) < min_floor:
                warnings.append(
                    f"Highest assertion count found ({max(counts)}) is below floor ({min_floor})"
                )
        else:
            warnings.append(f"No assertion counts found — expected ≥{min_floor} assertions documented")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "code_blocks_checked": len(code_blocks),
    }


# ---------------------------------------------------------------------------
# Tool: write_plan_file
# ---------------------------------------------------------------------------

@mcp.tool()
def write_plan_file(filename: str, content: str, sub_phase: str = "") -> dict:
    """
    Validate and write a plan document to .github/<filename>.
    `sub_phase` is "", "a", "b", or "c" — used to pick the right validation rules.

    Returns: {success: bool, path: str, lines: int, validation: {...}}
    """
    root = _repo_root()
    dest = root / ".github" / filename

    # Validate first
    validation = validate_plan_file(content, sub_phase)
    if not validation["valid"]:
        return {
            "success": False,
            "path": str(dest),
            "reason": "Validation failed — fix errors before writing",
            "validation": validation,
        }

    dest.write_text(content, encoding="utf-8")
    lines = content.count("\n") + 1
    return {
        "success": True,
        "path": str(dest),
        "lines": lines,
        "validation": validation,
    }


# ---------------------------------------------------------------------------
# Tool: list_plan_files
# ---------------------------------------------------------------------------

@mcp.tool()
def list_plan_files() -> dict:
    """
    List all plan-RXXXX*.md files in .github/ with their line counts and
    whether they form a complete set (top + a + b + c).
    """
    root = _repo_root()
    github = root / ".github"
    files = sorted(github.glob("plan-R????.md")) + sorted(github.glob("plan-R?????.md"))

    milestones: dict = {}
    for f in github.glob("plan-R*.md"):
        m = re.match(r"plan-(R\d{4})(a|b|c)?\.md$", f.name)
        if not m:
            continue
        tag, sub = m.group(1), m.group(2) or ""
        if tag not in milestones:
            milestones[tag] = {"top": False, "a": False, "b": False, "c": False, "files": []}
        key = sub if sub else "top"
        milestones[tag][key] = True
        lines = f.read_text(encoding="utf-8").count("\n") + 1
        milestones[tag]["files"].append({"name": f.name, "lines": lines, "sub": sub or "top"})

    result = []
    for tag in sorted(milestones):
        d = milestones[tag]
        complete = all(d[k] for k in ("top", "a", "b", "c"))
        result.append({
            "milestone": tag,
            "complete": complete,
            "files": sorted(d["files"], key=lambda x: x["sub"]),
        })
    return {"milestones": result}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
