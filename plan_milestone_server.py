#!/usr/bin/env python3
"""
MCP server: plan-milestone
Provides tools that support the /plan-milestone skill.

Generates structured implementation-plan document sets (top-level + sub-plans)
from a project's roadmap file and existing plan templates.

Project-agnostic: works with any project that keeps plan docs in .github/ and
a roadmap / dev-plan file somewhere in the repo. All paths are auto-detected or
can be overridden via parameters.
"""

import os
import re
import subprocess
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("plan-milestone")

# ---------------------------------------------------------------------------
# Repo-root detection
# ---------------------------------------------------------------------------

_ROOT_SENTINELS = (
    ".github",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "README.md",
    "Makefile",
    "CMakeLists.txt",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
)


def _repo_root() -> Path:
    """Return the project root by walking up from cwd."""
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if any((p / s).exists() for s in _ROOT_SENTINELS):
            return p
    return cwd


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return ""


# ---------------------------------------------------------------------------
# Path auto-detection helpers
# ---------------------------------------------------------------------------

def _find_dev_plan(root: Path) -> Path | None:
    """Locate the project's development / roadmap plan file."""
    candidates = [
        root / ".github" / "prompts" / "plan-developmentPlan.prompt.md",
        root / ".github" / "ROADMAP.md",
        root / "ROADMAP.md",
        root / "docs" / "roadmap.md",
        root / "docs" / "development-plan.md",
    ]
    for p in (root / ".github" / "prompts").glob("*.prompt.md"):
        candidates.append(p)
    return next((p for p in candidates if p.exists()), None)


def _find_capability_header(root: Path) -> Path | None:
    """Locate a source file that defines capability / feature-flag bits."""
    candidates = [
        root / "kernel" / "hwcaps.h",
        root / "include" / "caps.h",
        root / "include" / "features.h",
        root / "src" / "caps.h",
        root / "src" / "features.h",
    ]
    for pattern in ("**/caps.h", "**/hwcaps.h", "**/features.h", "**/feature_flags.h"):
        for p in root.glob(pattern):
            if "build" not in p.parts and "vendor" not in p.parts:
                candidates.append(p)
    return next((p for p in candidates if p.exists()), None)


def _find_init_file(root: Path) -> Path | None:
    """Locate the file containing the project's main init / boot sequence."""
    candidates = [
        root / "kernel" / "kernel.c",
        root / "src" / "main.c",
        root / "src" / "main.rs",
        root / "src" / "main.go",
        root / "main.c",
        root / "main.rs",
        root / "main.go",
        root / "src" / "app.c",
        root / "src" / "boot.c",
    ]
    return next((p for p in candidates if p.exists()), None)


def _find_plan_dir(root: Path) -> Path:
    """Return the directory where plan-*.md files live."""
    for candidate in (root / ".github", root / "docs" / "plans", root / "plans"):
        if candidate.exists() and list(candidate.glob("plan-*.md")):
            return candidate
    return root / ".github"


# ---------------------------------------------------------------------------
# Tool: capability_check
# ---------------------------------------------------------------------------

@mcp.tool()
def capability_check(header_path: str = "") -> dict:
    """
    Parse a capability / feature-flag header and return current bit assignments
    plus the next free slot.

    Looks for lines of the form:
        #define SOME_CAP  (1 << N)
        #define SOME_CAP  1<<N
        #define SOME_CAP  0x...   (single-bit hex values only)

    Parameters:
      header_path — override auto-detection; leave empty to auto-detect.

    Returns: {source, current_caps, next_bit_index, next_bit_value, next_bit_define}
    """
    root = _repo_root()
    path = Path(header_path) if header_path else _find_capability_header(root)
    src = _read(path) if path else ""
    caps = []
    source = str(path) if path else "not found"

    if src:
        for m in re.finditer(r"#define\s+(\w+)\s+\(?\s*1\s*<<\s*(\d+)\s*\)?", src):
            name, idx = m.group(1), int(m.group(2))
            caps.append({"name": name, "bit_index": idx,
                         "value": 1 << idx, "hex": f"0x{1 << idx:02X}"})
        for m in re.finditer(r"#define\s+(\w+)\s+(0x[0-9A-Fa-f]+)\b", src):
            val = int(m.group(2), 16)
            if val and (val & (val - 1)) == 0:
                idx = val.bit_length() - 1
                if not any(c["name"] == m.group(1) for c in caps):
                    caps.append({"name": m.group(1), "bit_index": idx,
                                 "value": val, "hex": f"0x{val:02X}"})
    else:
        # Try nm on compiled objects as a last resort
        nm_names = []
        for obj in list(root.glob("build/**/*.o"))[:5]:
            try:
                out = subprocess.check_output(["nm", str(obj)],
                                               stderr=subprocess.DEVNULL, text=True)
                nm_names += re.findall(r"\b(\w*[Cc]ap\w*|\w*[Ff]eature\w*)\b", out)
            except Exception:
                pass
        source = f"header not found; nm symbols: {list(dict.fromkeys(nm_names))[:10]}"

    caps.sort(key=lambda c: c["bit_index"])
    next_idx = (caps[-1]["bit_index"] + 1) if caps else 0
    next_val = 1 << next_idx

    return {
        "source": source,
        "current_caps": caps,
        "next_bit_index": next_idx,
        "next_bit_value": f"0x{next_val:02X}",
        "next_bit_define": f"(1 << {next_idx})",
    }


# ---------------------------------------------------------------------------
# Tool: plan_template
# ---------------------------------------------------------------------------

@mcp.tool()
def plan_template(milestone: str = "", plan_dir: str = "") -> dict:
    """
    Return the plan files for a completed milestone as template text.

    If `milestone` is given (e.g. "R0011", "v2.3") that set is returned;
    otherwise the highest-numbered complete set (top + a + b + c) is used.

    Parameters:
      milestone — optional milestone tag to fetch
      plan_dir  — override auto-detected plan directory

    Returns: {milestone, plan_dir, top_level, sub_a, sub_b, sub_c}
    """
    root = _repo_root()
    pdir = Path(plan_dir) if plan_dir else _find_plan_dir(root)

    if milestone:
        m = re.match(r"[Rr]?0*(\d+)", milestone)
        tag = f"R{int(m.group(1)):04d}" if m else milestone
    else:
        tag = None
        for top in sorted(pdir.glob("plan-R????.md"), reverse=True):
            m = re.search(r"plan-(R\d{4})\.md$", top.name)
            if not m:
                continue
            t = m.group(1)
            if all((pdir / f"plan-{t}{s}.md").exists() for s in ("a", "b", "c")):
                tag = t
                break
        if not tag:
            tops = sorted(pdir.glob("plan-*.md"), reverse=True)
            if tops:
                tag = re.search(r"plan-(\w+)\.md$", tops[0].name).group(1)
            else:
                return {"error": f"No plan files found in {pdir}"}

    def _r(suffix):
        for fname in (f"plan-{tag}{suffix}.md", f"plan_{tag}{suffix}.md"):
            text = _read(pdir / fname)
            if text:
                return text
        return ""

    return {
        "milestone": tag,
        "plan_dir": str(pdir),
        "top_level": _r(""),
        "sub_a":     _r("a"),
        "sub_b":     _r("b"),
        "sub_c":     _r("c"),
    }


# ---------------------------------------------------------------------------
# Tool: milestone_entry
# ---------------------------------------------------------------------------

@mcp.tool()
def milestone_entry(milestone: str, dev_plan_path: str = "") -> dict:
    """
    Extract the roadmap / dev-plan entry for a milestone.

    Parameters:
      milestone     — tag to search for (e.g. "R0012", "v3.0", "PHASE-4")
      dev_plan_path — override auto-detection of the roadmap file

    Returns: {milestone, source_file, entry_text, file_list, feature_goals}
    """
    root = _repo_root()
    path = Path(dev_plan_path) if dev_plan_path else _find_dev_plan(root)

    if not path:
        return {"error": "No development plan / roadmap file found. "
                         "Pass dev_plan_path explicitly."}

    src = _read(path)
    if not src:
        return {"error": f"Could not read {path}"}

    tag = milestone.strip()
    section_re = re.compile(
        rf"(#+\s+.*?{re.escape(tag)}.*?)(?=\n#+\s|\Z)", re.DOTALL
    )
    m = section_re.search(src)
    if m:
        entry = m.group(0)
    else:
        idx = src.find(tag)
        if idx == -1:
            return {"error": f"'{tag}' not found in {path}"}
        start = max(0, src.rfind("\n\n", 0, idx))
        entry = src[start:min(len(src), idx + 3000)]

    file_lines = [l.strip() for l in entry.splitlines()
                  if re.search(r"[a-zA-Z_/][a-zA-Z0-9_/.-]+\.[a-zA-Z]{1,5}", l)
                  and not l.strip().startswith("#")]

    feature_lines = [l.strip() for l in entry.splitlines()
                     if re.search(r"\b(add|impl|introduce|support|enable|extend|"
                                  r"replace|upgrade|migrate|new)\b", l, re.I)
                     and len(l.strip()) > 10]

    return {
        "milestone": tag,
        "source_file": str(path),
        "entry_text": entry,
        "file_list": file_lines[:40],
        "feature_goals": feature_lines[:20],
    }


# ---------------------------------------------------------------------------
# Tool: init_sequence
# ---------------------------------------------------------------------------

@mcp.tool()
def init_sequence(init_file_path: str = "") -> dict:
    """
    Extract the application's startup / initialisation call order so that new
    init calls can be slotted in at the correct position.

    Parameters:
      init_file_path — override auto-detection (looks for main.c, kernel.c, etc.)

    Returns: {source_file, init_calls, raw_main}
    """
    root = _repo_root()
    path = Path(init_file_path) if init_file_path else _find_init_file(root)

    if not path:
        return {"error": "No init / main file found. Pass init_file_path explicitly."}

    src = _read(path)
    if not src:
        return {"error": f"Could not read {path}"}

    main_re = re.compile(
        r"\b(?:void|int)\s+(?:main|kernel_main|app_main|boot_main|start)\s*\([^)]*\)\s*\{",
        re.MULTILINE,
    )
    m = main_re.search(src)
    if not m:
        return {"error": f"No main() function found in {path}", "src_preview": src[:500]}

    start = m.end()
    depth, pos = 1, start
    while pos < len(src) and depth:
        if src[pos] == "{":
            depth += 1
        elif src[pos] == "}":
            depth -= 1
        pos += 1
    raw_main = src[m.start():pos]

    init_re = re.compile(r"\b(\w+(?:_init|_setup|_start|_probe|_enable))\s*\(")
    calls = list(dict.fromkeys(im.group(1) for im in init_re.finditer(raw_main)))

    return {
        "source_file": str(path),
        "init_calls": calls,
        "raw_main": raw_main,
    }


# ---------------------------------------------------------------------------
# Tool: validate_plan_file
# ---------------------------------------------------------------------------

_REQUIRED_HEADINGS = {
    "":  ["Prior Release Context", "Overview", "Goals",
          "Test Results", "Sub-Phase Summary"],
    "a": ["Prior Release Context", "Overview", "Implementation",
          "Files", "Test Coverage", "Commit Message"],
    "b": ["Prior Release Context", "Overview", "Implementation",
          "Files", "Test Coverage", "Commit Message"],
    "c": ["Prior Release Context", "Overview", "Implementation",
          "Files", "Test Coverage", "Commit Message"],
}

_ASSERTION_FLOOR = {"": 0, "a": 30, "b": 30, "c": 60}


@mcp.tool()
def validate_plan_file(
    content: str,
    sub_phase: str = "",
    language: str = "c",
    extra_forbidden_tokens: str = "",
) -> dict:
    """
    Validate a plan document before writing it.

    Parameters:
      content                — full markdown text of the plan
      sub_phase              — "", "a", "b", or "c"
      language               — primary language for code-block style checks
                               ("c", "rust", "go", "python", …); use "" to skip
      extra_forbidden_tokens — comma-separated tokens to flag in code blocks

    Returns: {valid, errors, warnings, code_blocks_checked}
    """
    errors, warnings = [], []

    for heading in _REQUIRED_HEADINGS.get(sub_phase, []):
        if heading.lower() not in content.lower():
            errors.append(f"Missing required section: '{heading}'")

    lang_fence = f"```{language}" if language else "```"
    code_blocks = re.findall(rf"{re.escape(lang_fence)}(.*?)```", content, re.DOTALL)

    forbidden = [t.strip() for t in extra_forbidden_tokens.split(",") if t.strip()]
    if language == "c":
        forbidden += ["size_t", "malloc(", "free(", "printf(", "strlen("]
        forbidden += [f"#include <{h}.h>" for h in
                      ("string", "stdlib", "stdio", "stddef", "stdint")]

    for i, block in enumerate(code_blocks):
        for token in forbidden:
            if token in block:
                errors.append(f"Code block {i+1}: forbidden token '{token}'")
        if language == "c":
            if re.search(r"\t", block):
                errors.append(f"Code block {i+1}: tab character — use 4-space indent")
            if re.search(r"\)\s*\n\s*\{", block):
                warnings.append(
                    f"Code block {i+1}: opening brace may be on its own line"
                )

    # Capability-bit collision check
    cap_result = capability_check()
    if "current_caps" in cap_result:
        used = {c["bit_index"] for c in cap_result["current_caps"]}
        next_idx = cap_result["next_bit_index"]
        for idx_str in re.findall(r"1\s*<<\s*(\d+)", content):
            idx = int(idx_str)
            if idx < next_idx and idx not in used:
                warnings.append(
                    f"Bit 1<<{idx} referenced but not in capability header "
                    f"and below next free index ({next_idx}) — verify intentional"
                )

    # Assertion count floor
    floor = _ASSERTION_FLOOR.get(sub_phase, 0)
    if floor:
        counts = [int(m) for m in re.findall(r"(\d+)\+?\s*/\s*\d+\+?", content)
                  if int(m) >= 1]
        if counts:
            if max(counts) < floor:
                warnings.append(
                    f"Highest assertion count ({max(counts)}) is below "
                    f"floor ({floor}) for sub-phase '{sub_phase or 'top'}'"
                )
        else:
            warnings.append(
                f"No assertion counts found — expected ≥{floor} assertions documented"
            )

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
def write_plan_file(
    filename: str,
    content: str,
    sub_phase: str = "",
    plan_dir: str = "",
    language: str = "c",
    extra_forbidden_tokens: str = "",
) -> dict:
    """
    Validate then write a plan document atomically.
    Refuses to write if validation returns errors.

    Parameters:
      filename               — e.g. "plan-R0013.md" or "plan-R0013a.md"
      content                — full document text
      sub_phase              — "", "a", "b", or "c"
      plan_dir               — override auto-detected plan directory
      language               — passed to validate_plan_file
      extra_forbidden_tokens — passed to validate_plan_file

    Returns: {success, path, lines, validation}
    """
    root = _repo_root()
    pdir = Path(plan_dir) if plan_dir else _find_plan_dir(root)
    pdir.mkdir(parents=True, exist_ok=True)
    dest = pdir / filename

    validation = validate_plan_file(
        content, sub_phase, language, extra_forbidden_tokens
    )
    if not validation["valid"]:
        return {
            "success": False,
            "path": str(dest),
            "reason": "Validation failed — fix errors before writing",
            "validation": validation,
        }

    dest.write_text(content, encoding="utf-8")
    return {
        "success": True,
        "path": str(dest),
        "lines": content.count("\n") + 1,
        "validation": validation,
    }


# ---------------------------------------------------------------------------
# Tool: list_plan_files
# ---------------------------------------------------------------------------

@mcp.tool()
def list_plan_files(plan_dir: str = "") -> dict:
    """
    List all plan-*.md files and report whether each milestone forms a complete
    set (top-level + a + b + c).

    Parameters:
      plan_dir — override auto-detection

    Returns: {plan_dir, milestones}
    """
    root = _repo_root()
    pdir = Path(plan_dir) if plan_dir else _find_plan_dir(root)

    milestones: dict = {}
    for f in pdir.glob("plan-*.md"):
        m = re.match(r"plan-(\w+?)(a|b|c)?\.md$", f.name)
        if not m:
            continue
        tag, sub = m.group(1), m.group(2) or ""
        if tag not in milestones:
            milestones[tag] = {"top": False, "a": False, "b": False, "c": False,
                               "files": []}
        key = sub if sub else "top"
        milestones[tag][key] = True
        lines = f.read_text(encoding="utf-8").count("\n") + 1
        milestones[tag]["files"].append(
            {"name": f.name, "lines": lines, "sub": sub or "top"}
        )

    result = []
    for tag in sorted(milestones):
        d = milestones[tag]
        complete = all(d[k] for k in ("top", "a", "b", "c"))
        result.append({
            "milestone": tag,
            "complete": complete,
            "files": sorted(d["files"], key=lambda x: x["sub"]),
        })

    return {"plan_dir": str(pdir), "milestones": result}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
