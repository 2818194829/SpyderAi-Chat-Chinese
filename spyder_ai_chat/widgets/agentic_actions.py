# -*- coding: utf-8 -*-
"""Agentic action execution for AI Chat plugin. (C) 2026 by Maciej Piecko

Handles file creation, console execution, package installation, and patch
application triggered by special code fences in LLM responses.
"""

import os
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace

# Suppress console-window flash on Windows for every subprocess call
_SUBPROCESS_FLAGS = (
    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
)

# ---------------------------------------------------------------------------
# Action type constants �?single source of truth for fence action names.
# Avoids scattered raw string literals like "file", "run", "patch" etc.
# ---------------------------------------------------------------------------
_AT = SimpleNamespace(
    FILE       = "file",
    RUN        = "run",
    INSTALL    = "install",
    PATCH      = "patch",
    GIT        = "git",
    INSPECT    = "inspect",
    READ       = "read",
    LS         = "ls",
    GREP       = "grep",
    DELETE     = "delete",
    DELETE_DIR = "delete_dir",
    RENAME     = "rename",
    RENAME_DIR = "rename_dir",
)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def find_git():
    """Return the path to the git executable, or None if not found."""
    return shutil.which("git")


def run_git_command(args, cwd=None):
    """
    Run a git command.  args is a list of strings (without the leading 'git').
    Returns (stdout: str, stderr: str, returncode: int).
    Raises RuntimeError if git is not installed.
    """
    git = find_git()
    if not git:
        raise RuntimeError(
            "git is not installed or not on PATH.\n"
            "Please install Git and make sure it is available in your system PATH."
        )
    try:
        result = subprocess.run(
            [git] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=_SUBPROCESS_FLAGS,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "git command timed out after 30 seconds.", 1
    except Exception as exc:
        return "", str(exc), 1


# ---------------------------------------------------------------------------
# File inspection helpers (read, ls, grep) �?pure Python, cross-platform
# ---------------------------------------------------------------------------

def _count_lines(path):
    """Return line count for a text file, or None if binary/unreadable."""
    try:
        with open(path, "rb") as fb:
            if b"\x00" in fb.read(512):
                return None       # binary file
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return None


def read_file(path, base_dir=None, line_from=None, line_to=None):
    """
    Read a file, optionally restricted to lines line_from..line_to (1-based, inclusive).
    Returns (content: str, error: str, rc: int).
    content always starts with a header:
      "[filename �?N lines]"  or  "[filename �?lines A-B of N total]"
    """
    if base_dir and not os.path.isabs(path):
        full = os.path.join(base_dir, path)
    else:
        full = path
    full = os.path.normpath(os.path.abspath(full))
    # Reject reads that traverse any excluded directory (e.g. .spyproject, .git)
    path_parts = full.replace("\\", "/").split("/")
    for part in path_parts[:-1]:   # skip filename itself; check every directory component
        if part in _EXCL_DIRS:
            return "", f"Access denied: '{part}' is a protected directory.", 1
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except FileNotFoundError:
        return "", f"File not found: {full}", 1
    except Exception as exc:
        return "", str(exc), 1

    total = len(all_lines)
    fname = os.path.basename(full)

    if line_from is not None and line_to is not None:
        a = max(1, line_from)
        b = min(total, line_to)
        body   = "".join(all_lines[a - 1:b])
        header = f"[{fname} �?lines {a}-{b} of {total} total]"
    else:
        body   = "".join(all_lines)
        header = f"[{fname} �?{total} lines]"

    return f"{header}\n{body}", "", 0


_LS_LINE_COUNT_THRESHOLD = 50


def ls_dir(path, base_dir=None):
    """
    List a directory. Returns (listing: str, error: str, rc: int).
    Directories get a trailing '/'. For directories with �?50 entries,
    text file line counts are shown as '  (N lines)'.
    """
    if base_dir and not os.path.isabs(path):
        full = os.path.join(base_dir, path)
    else:
        full = path
    full = os.path.normpath(os.path.abspath(full))
    # Block direct listing of any excluded directory
    if os.path.basename(full) in _EXCL_DIRS:
        return "", f"Access denied: '{os.path.basename(full)}' is a protected directory.", 1
    try:
        entries = sorted(os.listdir(full))
    except FileNotFoundError:
        return "", f"Directory not found: {full}", 1
    except Exception as exc:
        return "", str(exc), 1

    # Filter out excluded directories before counting / displaying
    entries = [e for e in entries
               if not (os.path.isdir(os.path.join(full, e)) and e in _EXCL_DIRS)]
    show_counts = len(entries) <= _LS_LINE_COUNT_THRESHOLD
    dirs, files = [], []
    for e in entries:
        epath = os.path.join(full, e)
        if os.path.isdir(epath):
            dirs.append(f"{e}/")
        elif show_counts:
            count = _count_lines(epath)
            suffix = f"  ({count} lines)" if count is not None else ""
            files.append(f"{e}{suffix}")
        else:
            files.append(e)

    # Separate directories and files into labelled sections so the LLM
    # cannot confuse files that are alphabetically after a subdirectory
    # name with being *inside* that subdirectory.
    sections = []
    if dirs:
        sections.append("Subdirectories:\n" + "\n".join(f"  {d}" for d in dirs))
    if files:
        sections.append("Files:\n" + "\n".join(f"  {f}" for f in files))

    return ("\n\n".join(sections) if sections else "(empty)"), "", 0


# Directories excluded from all agentic read operations (ls, grep, read).
# .spyproject is Spyder's internal project metadata and must never be exposed.
_EXCL_DIRS = frozenset({
    ".git", ".spyproject",
    "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    ".venv", "venv", "env", "node_modules", "dist", "build",
    ".idea", ".vscode", ".tox",
})
_GREP_EXCL_DIRS = _EXCL_DIRS   # kept for any external references
_GREP_MAX_RESULTS = 200


def grep_files(pattern, base_dir, scope=""):
    """
    Search files under base_dir (or base_dir/scope) for a regex pattern.
    Returns (results: str, error: str, rc: int).
    Result lines are formatted as "rel/path/file.py:lineno: matching text".
    Results are capped at _GREP_MAX_RESULTS lines.
    Binary files (detected by null-byte probe) are skipped.
    """
    search_root = os.path.join(base_dir, scope) if scope else base_dir
    search_root = os.path.normpath(os.path.abspath(search_root))
    if not os.path.isdir(search_root):
        return "", f"Directory not found: {search_root}", 1
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return "", f"Invalid regex: {exc}", 1

    lines_out = []
    for dirpath, dirnames, filenames in os.walk(search_root):
        dirnames[:] = [d for d in dirnames if d not in _GREP_EXCL_DIRS]
        for fname in sorted(filenames):
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "rb") as fb:
                    if b"\x00" in fb.read(512):
                        continue
            except OSError:
                continue
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if rx.search(line):
                            rel = os.path.relpath(fpath, base_dir).replace("\\", "/")
                            lines_out.append(f"{rel}:{lineno}: {line.rstrip()}")
                            if len(lines_out) >= _GREP_MAX_RESULTS:
                                lines_out.append(
                                    f"�?(results capped at {_GREP_MAX_RESULTS} lines)")
                                return "\n".join(lines_out), "", 0
            except OSError:
                continue

    return ("\n".join(lines_out) if lines_out else "(no matches)"), "", 0


# ---------------------------------------------------------------------------
# Agentic system prompt injected when agentic mode is enabled
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Agentic system prompt �?section constants (one per fence type / shared rule)
# ---------------------------------------------------------------------------

# Preamble �?four variants, one per autonomous mode
_PROMPT_PREAMBLE_MANUAL = """\
你可以通过使用特殊的代码围栏来执行直接操作。每个操作会在执行前通过批量对话框呈现给用户以获取明确确认。\
结果不会自动转发——由用户决定将哪些内容发送回给你�?""

_PROMPT_PREAMBLE_SEMI = """\
你可以通过使用特殊的代码围栏来执行直接操作。每个操作会在执行前通过批量对话框呈现给用户以获取明确确认。\
执行后，结果会自动转发给你�?""

_PROMPT_PREAMBLE_FULL_CONFIRM = """\
你可以通过使用特殊的代码围栏来执行直接操作。只读检查围栏（read:、ls:、grep:）\
静默执行，其结果会自动转发给你。文件修改操作（file:、patch:、run:python、\
install:、run:git、delete:、rename:）在执行前仍需要用户确认，之后结果会自动转发给你�?""

_PROMPT_PREAMBLE_FULL_SILENT = """\
你可以通过使用特殊的代码围栏来执行直接操作。所有操作立即执行，无需任何用户确认，\
结果会自动转发给你�?""

_PROMPT_CLOSING = """\
仅当用户明确要求你创建或修改文件、运行代码、安装包或与 git 交互时，才使用这些操作围栏。\
始终在操作围栏之前解释你正在做什么�?""

# file: vs patch: rule �?three variants depending on which fences are enabled
_PROMPT_FILE_VS_PATCH_BOTH = """\
重要规则 �?file vs patch�?- 使用 `patch:` 围栏来编辑或修改已存在的文件。永远不要使�?`file:` 围栏完整重写已有文件�?- 仅在创建尚不存在的新文件时使�?`file:` 围栏�?- 当用户说"编辑"�?更改"�?更新"�?修复"�?重构"�?修改"文件时——始终生�?`patch:` 围栏，而不�?`file:` 围栏�?""

_PROMPT_FILE_ONLY_RULE = """\
重要规则 �?file 围栏�?- 仅使�?`file:` 围栏来创建尚不存在的新文件。永远不要用它来重写已有文件�?""

_PROMPT_PATCH_ONLY_RULE = """\
重要规则 �?patch 围栏�?- 使用 `patch:` 围栏来编辑或修改已存在的文件。当用户�?编辑"�?更改"�?更新"�?修复"、\
"重构"�?修改"文件时，始终生成 `patch:` 围栏�?""

# Per-fence sections
_PROMPT_FILE = """\
创建一个全新的文件（路径相对于项目根目录，或使用绝对路径）�?```file:path/to/new_file.py
# 完整的文件内容在�?```"""

_PROMPT_RUN_PYTHON = """\
�?IPython 控制台中运行 Python 代码�?```run:python
print("hello world")
```"""

_PROMPT_INSTALL = """\
安装 Python 包：
```install:pip
numpy pandas
```"""

_PROMPT_PATCH = """\
应用统一差异补丁来修改已存在的文件：
```patch:path/to/file.py
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -1,3 +1,3 @@
 上下文行
-旧行
+新行
```"""

# Git �?two variants: manual (user attaches output) vs auto-send
_PROMPT_GIT_MANUAL = """\
在项目目录中运行 git 命令�?```run:git
log --oneline -10
```
命令输出将内联显示。用户可以将它附加到聊天中供你读取和分析，或忽略它。\
使用只读命令（log、diff、status、show、blame）检查仓库。\
使用写入命令（commit、branch、checkout）执行操作。始终向用户展示你正在运行的命令及其原因�?""

_PROMPT_GIT_AUTO = """\
在项目目录中运行 git 命令�?```run:git
log --oneline -10
```
命令输出会自动转发给你。使用只读命令（log、diff、status、show、blame）检查仓库。\
使用写入命令（commit、branch、checkout）执行操作。始终向用户展示你正在运行的命令及其原因�?""

_PROMPT_READ = """\
读取文件（完整内容）�?```read:path/to/file.py
```
读取特定行范围（�?1 开始，包含两端）：
```read:path/to/file.py:100-150
```
结果始终以显示文件名和总行数的头部开始，例如"[file.py �?250 lines]"。\
在读取大文件前使用小范围�?:1-1"来了解总大小�?""

_PROMPT_LS = """\
列出目录�?```ls:some/directory/
```
对于条目�?�?50 的目录，会显示每个文本文件的行数�?""

_PROMPT_GREP = """\
在所有项目文件中搜索正则表达式模式：
```grep:pattern
```
在特定子目录中搜索：
```grep:pattern:src/
```
结果�?文件:行号: 匹配文本"的格式返回。结果上限为 200 行。\
在进行更改前使用 read:/ls:/grep: 探索项目——只请求你实际需要的文件，而不是请求完整的项目上下文�?""

# Delete �?two variants: confirmation required vs silent (full-silent mode)
_PROMPT_DELETE_CONFIRM = """\
删除单个文件（不可�?�?用户将看到确认对话框）：
```delete:path/to/file.py
```"""

_PROMPT_DELETE_SILENT = """\
删除单个文件（不可�?�?立即执行无需确认）：
```delete:path/to/file.py
```"""

_PROMPT_DELETE_DIR_CONFIRM = """\
递归删除整个目录树（不可�?�?用户将看到确认对话框）：
```delete_dir:path/to/directory/
```"""

_PROMPT_DELETE_DIR_SILENT = """\
递归删除整个目录树（不可�?�?立即执行无需确认）：
```delete_dir:path/to/directory/
```"""

_PROMPT_RENAME = """\
重命名或移动文件 �?将新路径放在围栏体中�?```rename:path/to/old_file.py
path/to/new_file.py
```"""

_PROMPT_RENAME_DIR = """\
重命名或移动目录 �?将新路径放在围栏体中�?```rename_dir:path/to/old_dir/
path/to/new_dir/
```"""

_PROMPT_RENAME_NOTE = """\
路径相对于项目根目录，或使用绝对路径。rename:/rename_dir: 也可以将文件或目录移动到不同位置（相当于 mv）�?""

# Inspection discipline �?two variants: manual (user clicks "Send to LLM") vs auto-send
_PROMPT_INSPECTION_DISCIPLINE_MANUAL = """\
重要 �?检查围栏纪律：当你输出 read:、ls: �?grep: 围栏时，请在围栏后立即结束你的回复。\
在真正看到内容之前，不要推测或描述内容。用户必须点�?发送给 LLM"来将结果转发给你；\
他们也可以忽略，在这种情况下你将不会收到输出。你可以在一次回复中输出多个检查围栏\
（它们将一起执行），但不要有其他内容——没有评论、没有假设、没有部分答案。等待结果�?""

_PROMPT_INSPECTION_DISCIPLINE_AUTO = """\
重要 �?检查围栏纪律：当你输出 read:、ls: �?grep: 围栏时，请在围栏后立即结束你的回复。\
在真正看到内容之前，不要推测或描述内容。结果会自动转发给你，然后你可以分析它们。\
你可以在一次回复中输出多个检查围栏（它们将一起执行），但不要有其他内容——\
没有评论、没有假设、没有部分答案。等待结果�?""


def build_agentic_system_prompt(agentic_cfg: dict) -> str:
    """Return the agentic system prompt containing only the enabled fence sections.

    Reads allow_* flags and autonomous_mode from *agentic_cfg* (same dict
    returned by AIChatPanel._agentic_cfg()) and assembles only the relevant
    sections, with wording appropriate for the active confirmation/auto-send mode.
    """
    c = agentic_cfg
    mode         = c.get("autonomous_mode", "semi")           # "off"|"semi"|"full"
    full_confirm = c.get("full_auto_confirm_modifying", True)  # only relevant when mode="full"
    is_manual    = (mode == "off")
    is_full_silent = (mode == "full" and not full_confirm)
    auto_send    = not is_manual   # semi + full both auto-send results

    # ── Preamble (mode-dependent) ────────────────────────────────────────────
    if is_manual:
        sections = [_PROMPT_PREAMBLE_MANUAL]
    elif mode == "semi":
        sections = [_PROMPT_PREAMBLE_SEMI]
    elif full_confirm:
        sections = [_PROMPT_PREAMBLE_FULL_CONFIRM]
    else:
        sections = [_PROMPT_PREAMBLE_FULL_SILENT]

    # ── file: vs patch: rule ─────────────────────────────────────────────────
    has_file  = c.get("allow_create_file", False)
    has_patch = c.get("allow_patch", False)
    if has_file and has_patch:
        sections.append(_PROMPT_FILE_VS_PATCH_BOTH)
    elif has_file:
        sections.append(_PROMPT_FILE_ONLY_RULE)
    elif has_patch:
        sections.append(_PROMPT_PATCH_ONLY_RULE)

    # ── Per-fence sections ───────────────────────────────────────────────────
    if has_file:                          sections.append(_PROMPT_FILE)
    if c.get("allow_run_console", False): sections.append(_PROMPT_RUN_PYTHON)
    if c.get("allow_install",     False): sections.append(_PROMPT_INSTALL)
    if has_patch:                         sections.append(_PROMPT_PATCH)
    if c.get("allow_git", False):
        sections.append(_PROMPT_GIT_AUTO if auto_send else _PROMPT_GIT_MANUAL)
    if c.get("allow_read",        False): sections.append(_PROMPT_READ)
    if c.get("allow_ls",          False): sections.append(_PROMPT_LS)
    if c.get("allow_grep",        False): sections.append(_PROMPT_GREP)
    if c.get("allow_delete", False):
        sections.append(_PROMPT_DELETE_SILENT if is_full_silent else _PROMPT_DELETE_CONFIRM)
    if c.get("allow_delete_dir", False):
        sections.append(_PROMPT_DELETE_DIR_SILENT if is_full_silent else _PROMPT_DELETE_DIR_CONFIRM)
    if c.get("allow_rename",      False): sections.append(_PROMPT_RENAME)
    if c.get("allow_rename_dir",  False): sections.append(_PROMPT_RENAME_DIR)

    if c.get("allow_rename", False) or c.get("allow_rename_dir", False):
        sections.append(_PROMPT_RENAME_NOTE)

    if c.get("allow_read", False) or c.get("allow_ls", False) or c.get("allow_grep", False):
        sections.append(
            _PROMPT_INSPECTION_DISCIPLINE_AUTO if auto_send
            else _PROMPT_INSPECTION_DISCIPLINE_MANUAL
        )

    sections.append(_PROMPT_CLOSING)
    return "\n\n".join(sections)


# Backward-compat shim �?all fences enabled, semi mode (closest to old default).
# Any remaining import of AGENTIC_SYSTEM_PROMPT keeps working without crashing.
AGENTIC_SYSTEM_PROMPT = build_agentic_system_prompt({
    "allow_create_file": True, "allow_run_console": True, "allow_install": True,
    "allow_patch": True, "allow_git": True, "allow_read": True,
    "allow_ls": True, "allow_grep": True, "allow_delete": True,
    "allow_delete_dir": True, "allow_rename": True, "allow_rename_dir": True,
    "autonomous_mode": "semi", "full_auto_confirm_modifying": True,
})


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

def execute_create_file(path, content, base_dir=None):
    """Create or overwrite a file. Returns the absolute path written."""
    if base_dir and not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    path = os.path.normpath(os.path.abspath(path))
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return path


def execute_patch_file(path, diff_text, base_dir=None):
    """Apply a unified diff to a file. Returns the absolute path written."""
    if base_dir and not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    path = os.path.normpath(os.path.abspath(path))
    try:
        with open(path, "r", encoding="utf-8") as f:
            original = f.read()
    except FileNotFoundError:
        original = ""
    result = _apply_unified_diff(original, diff_text)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(result)
    return path


def execute_delete_file(path, base_dir=None):
    """Delete a single file. Returns the absolute path deleted."""
    if base_dir and not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    path = os.path.normpath(os.path.abspath(path))
    os.remove(path)
    return path


def execute_delete_dir(path, base_dir=None):
    """Delete a directory tree recursively. Returns the absolute path deleted."""
    import shutil as _shutil
    if base_dir and not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    path = os.path.normpath(os.path.abspath(path))
    _shutil.rmtree(path)
    return path


def execute_rename(old_path, new_path, base_dir=None):
    """Rename (or move) a file or directory. Returns (old_abs, new_abs)."""
    if base_dir:
        if not os.path.isabs(old_path):
            old_path = os.path.join(base_dir, old_path)
        if not os.path.isabs(new_path):
            new_path = os.path.join(base_dir, new_path)
    old_path = os.path.normpath(os.path.abspath(old_path))
    new_path = os.path.normpath(os.path.abspath(new_path))
    parent = os.path.dirname(new_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    os.rename(old_path, new_path)
    return old_path, new_path


def _find_hunk_position(lines, hunk_old):
    """Find where hunk_old appears in lines.  Returns (start_index, exact) or
    (None, False) when not found.

    Two passes:
    1. Exact match �?content must be identical.
    2. Stripped match �?leading/trailing whitespace on every line is ignored.
       Used as a fallback when the LLM's diff has slightly wrong indentation.
       The caller must use the file's original lines for context entries
       (see _build_hunk_chunk) to avoid propagating the LLM's whitespace errors.

    Returns a 2-tuple so callers can distinguish exact vs fuzzy matches.
    """
    if not hunk_old:
        return 0, True
    # Pass 1: exact
    for start in range(len(lines) - len(hunk_old) + 1):
        if lines[start:start + len(hunk_old)] == hunk_old:
            return start, True
    # Pass 2: stripped (ignores leading/trailing whitespace)
    hunk_stripped = [l.strip() for l in hunk_old]
    for start in range(len(lines) - len(hunk_old) + 1):
        if [l.strip() for l in lines[start:start + len(hunk_old)]] == hunk_stripped:
            return start, False
    return None, False


def _build_hunk_chunk(result_lines, pos, hunk_actions, preserve_context):
    """Build the replacement chunk for a hunk.

    hunk_actions  list of (kind, content) where kind is 'context'|'add'|'remove'.
    preserve_context
        True  �?use the FILE's version for context lines (indentation preserved).
                 Used when the match was fuzzy (stripped whitespace).
        False �?use the diff's version for all lines (used for exact matches).

    Returns the list of lines that should replace result_lines[pos:pos+n_old].
    """
    chunk = []
    fi = pos                         # walking index into result_lines
    for kind, content in hunk_actions:
        if kind == "context":
            if preserve_context and fi < len(result_lines):
                # Keep the FILE's exact line �?preserves indentation /
                # trailing whitespace that the LLM may have got slightly wrong.
                chunk.append(result_lines[fi])
            else:
                chunk.append(content)
            fi += 1
        elif kind == "remove":
            fi += 1                  # consume file line without emitting it
        else:                        # "add"
            chunk.append(content)
    return chunk


def _check_patch_line_numbers(diff_text, file_path):
    """Scan unified-diff hunks and return info about stale @@ line numbers.

    For each hunk whose stated old_start does not match the actual position
    found in the file, returns a tuple:
        (hunk_header_str, llm_line_no, actual_line_no)

    Returns an empty list when the file doesn't exist, can't be read, or
    all hunk positions are already correct.

    Used only for *display* purposes �?the actual patch application via
    ``_apply_unified_diff`` uses its own fuzzy search independently.
    """
    if not file_path or not os.path.isfile(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            orig_lines = fh.read().splitlines()
    except OSError:
        return []

    stale  = []
    _hre   = re.compile(r"@@\s+-(\d+)(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@")
    dlines = diff_text.splitlines()
    i      = 0
    while i < len(dlines):
        ln = dlines[i]
        if not ln.startswith("@@"):
            i += 1
            continue
        m = _hre.match(ln)
        if not m:
            i += 1
            continue
        try:
            old_start = int(m.group(1))
        except ValueError:
            i += 1
            continue
        hunk_header = ln.strip()
        i += 1
        hunk_old = []
        while i < len(dlines):
            hl = dlines[i]
            if hl.startswith("@@"):
                break
            if not (hl.startswith("---") or hl.startswith("+++")):
                if hl.startswith("-"):
                    hunk_old.append(hl[1:])
                elif hl.startswith(" "):
                    hunk_old.append(hl[1:])
                elif hl == "":
                    hunk_old.append("")
            i += 1
        if not hunk_old:
            continue
        # Check whether the stated position is already correct
        exp = old_start - 1
        if (0 <= exp and exp + len(hunk_old) <= len(orig_lines)
                and orig_lines[exp:exp + len(hunk_old)] == hunk_old):
            continue  # numbers are accurate �?not stale
        # Try to find the actual position via the same fuzzy search
        pos, _ = _find_hunk_position(orig_lines, hunk_old)
        if pos is None:
            continue  # can't locate (new file or too different) �?skip
        actual_line = pos + 1
        if actual_line != old_start:
            stale.append((hunk_header, old_start, actual_line))
    return stale


def _apply_unified_diff(original_text, diff_text):
    """Apply a unified diff string to original_text. Returns new text.

    Matching strategy (per hunk)
    ────────────────────────────
    1.  If the @@ header supplies line numbers, compute the expected position
        as ``old_start + offset`` (offset = net lines added/removed by all
        earlier hunks, translating original-file numbers to current positions).
    2.  **Verify** that ``result[pos:end]`` matches ``hunk_old`` before writing.
        LLMs frequently produce slightly stale line numbers; a blind write to
        the wrong position silently corrupts the file.
    3.  If the content does not match, or the header had no line numbers,
        fall back to ``_find_hunk_position`` (fuzzy / stripped-whitespace
        search).  When a fuzzy match is found, ``offset`` is recalibrated so
        subsequent line-number hunks also land at the right place.
    4.  If neither strategy locates the hunk, skip it �?better to miss a
        change than to corrupt the file with a misplaced write.

    Whitespace / indentation safety
    ────────────────────────────────
    Whenever the match was fuzzy (stripped whitespace), we rebuild the output
    chunk via ``_build_hunk_chunk(preserve_context=True)``:
    �? *Context* lines keep the FILE's original content verbatim �?indentation
       and trailing whitespace are never changed for lines the diff didn't
       intend to modify.  This prevents the common failure where the LLM's
       context lines have slightly wrong indentation (e.g. 3 spaces instead of
       4) and the wholesale hunk_new replacement silently mis-indents the last
       line of the changed section.
    �? *Added* lines use the diff content as-is; the LLM chose their
       indentation intentionally.
    �? *Removed* lines are consumed (skipped) from the file.

    For exact matches the replacement is wholesale (hunk_new verbatim) since
    the context lines were verified to be identical to the file anyway.
    """
    orig_lines = original_text.splitlines()
    result     = list(orig_lines)
    offset     = 0
    i          = 0
    diff_lines = diff_text.splitlines()

    while i < len(diff_lines):
        line = diff_lines[i]
        if not line.startswith("@@"):
            i += 1
            continue

        m = re.match(r"@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@", line)
        try:
            old_start = max(0, int(m.group(1)) - 1) if (m and m.group(1)) else None
        except (ValueError, AttributeError):
            old_start = None
        i += 1

        # ── Collect hunk lines with action-type metadata ─────────────────
        # Keeping 'context'/'add'/'remove' lets _build_hunk_chunk decide
        # later whether to take lines from the file or from the diff.
        hunk_actions = []   # list of ('context'|'add'|'remove', content)
        while i < len(diff_lines):
            hl = diff_lines[i]
            if hl.startswith("@@"):
                break
            if hl.startswith("---") or hl.startswith("+++"):
                i += 1
                continue
            if hl.startswith("-"):
                hunk_actions.append(("remove",  hl[1:]))
            elif hl.startswith("+"):
                hunk_actions.append(("add",     hl[1:]))
            elif hl.startswith(" "):
                hunk_actions.append(("context", hl[1:]))
            elif hl == "":
                # Bare blank line in hunk body �?treat as context
                hunk_actions.append(("context", ""))
            i += 1

        # Derive the flat old/new lists that location-finding needs
        hunk_old = [c for k, c in hunk_actions if k in ("context", "remove")]
        hunk_new = [c for k, c in hunk_actions if k in ("context", "add")]

        # ── Locate hunk in current result ────────────────────────────────
        preserve_context = False   # True �?use file content for context lines

        if old_start is None:
            # No line numbers from the LLM �?pure fuzzy search
            pos, exact = _find_hunk_position(result, hunk_old)
            if pos is None:
                continue           # can't locate hunk �?skip rather than corrupt
            preserve_context = not exact
        else:
            pos = max(0, min(old_start + offset, len(result)))
            end = min(pos + len(hunk_old), len(result))

            if hunk_old and result[pos:end] == hunk_old:
                # Exact match at the expected position �?fast path
                exact = True
            else:
                # Line numbers stale/wrong �?try fuzzy fallback
                pos, exact = _find_hunk_position(result, hunk_old)
                if pos is None:
                    continue       # cannot locate hunk �?skip rather than corrupt
                # Recalibrate offset so subsequent hunks land correctly too
                offset = pos - old_start
            preserve_context = not exact

        end   = min(pos + len(hunk_old), len(result))
        chunk = _build_hunk_chunk(result, pos, hunk_actions, preserve_context)

        result[pos:end] = chunk
        offset += len(hunk_new) - len(hunk_old)

    return "\n".join(result)


# ---------------------------------------------------------------------------
# Qt confirm dialog  (imported lazily to avoid Qt import at module load)
# ---------------------------------------------------------------------------

def _is_dialog_dark():
    """Return True when the UI is running in dark mode (Spyder or Qt palette)."""
    try:
        from spyder.config.manager import CONF
        return CONF.get("appearance", "ui_theme") != "light"
    except Exception:
        pass
    try:
        from qtpy.QtWidgets import QApplication
        pal = QApplication.instance().palette()
        return pal.window().color().lightness() < 128
    except Exception:
        return True

def show_confirm_dialog(parent, action_type, target, content, base_dir=None):
    """
    Show a modal confirmation dialog for one agentic action.

    Returns:
        (confirmed: bool, final_path: str)  �?final_path may differ from
        target if the user edited it in the dialog (file/patch actions).
    """
    from qtpy.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel,
        QPlainTextEdit, QLineEdit, QDialogButtonBox, QPushButton,
        QFrame, QSizePolicy,
    )
    from qtpy.QtCore import Qt
    from qtpy.QtGui import QFont as _QFont

    _dark = _is_dialog_dark()
    # Colour palette �?dark vs light theme
    _fg_dim    = "#c8c8c8" if _dark else "#444444"
    _border    = "#444444" if _dark else "#cccccc"
    _info_bg   = "#2a2a2a" if _dark else "#f5f5f5"
    _info_bd   = "#555555" if _dark else "#bbbbbb"
    _git_fg    = "#f0c080" if _dark else "#7a4a00"
    _git_bg    = "#2a1a00" if _dark else "#fff3e0"
    _git_bd    = "#e8a050"
    _insp_fg   = "#b0deff" if _dark else "#1a3a6a"
    _insp_bg   = "#0d1e2e" if _dark else "#e8f4ff"
    _insp_bd   = "#80c8f0"
    _del_fg    = "#ffb0b0" if _dark else "#7a0000"
    _del_bg    = "#2a0000" if _dark else "#fff0f0"
    _del_bd    = "#e05050"
    _rn_fg     = "#f0c880" if _dark else "#7a4a00"
    _rn_bg     = "#1e1400" if _dark else "#fff8e0"
    _rn_bd     = "#e8a050"
    _warn_fg   = "#e8c060" if _dark else "#7a5000"
    _warn_bg   = "#2a2000" if _dark else "#fff8e0"
    _warn_bd   = "#c8a030"
    _prev_bg   = "#1e1e1e" if _dark else "#ffffff"
    _prev_fg   = "#d4d4d4" if _dark else "#222222"
    _prev_bd   = "#444444" if _dark else "#cccccc"
    _ok_fg     = "#80c880" if _dark else "#1a5a1a"
    _ok_bg     = "#2a4a2a" if _dark else "#e8f5e8"
    _ok_bd     = "#4a8a4a"
    _ok_hov    = "#3a5a3a" if _dark else "#d0ecd0"

    dlg = QDialog(parent)
    dlg.setWindowTitle("Confirm Agentic Action")
    dlg.setMinimumWidth(480)

    lay = QVBoxLayout(dlg)
    lay.setSpacing(8)
    lay.setContentsMargins(14, 14, 14, 14)

    # ── Header ──────────────────────────────────────────────────────────
    _ICONS = {
        "file":       "📄",
        "patch":      "🩹",
        "run":        "�?,
        "install":    "📦",
        "git":        "�?,
        "read":       "📄",
        "ls":         "📁",
        "grep":       "🔍",
        "delete":     "🗑",
        "delete_dir": "🗑",
        "rename":     "�?,
        "rename_dir": "�?,
    }
    _LABELS = {
        "file":       "Create / Overwrite File",
        "patch":      "Apply Patch",
        "run":        "Run in IPython Console",
        "install":    "Install Package",
        "git":        "Run Git Command",
        "read":       "Read File",
        "ls":         "List Directory",
        "grep":       "Search in Files",
        "delete":     "Delete File",
        "delete_dir": "Delete Directory  (recursive)",
        "rename":     "Rename / Move File",
        "rename_dir": "Rename / Move Directory",
    }
    icon  = _ICONS.get(action_type, "?")
    label = _LABELS.get(action_type, action_type)

    _hdr_color = (
        "#e8a050" if action_type == "git" else
        "#80c8f0" if action_type in ("read", "ls", "grep") else
        "#e05050" if action_type in ("delete", "delete_dir") else
        "#e8a050" if action_type in ("rename", "rename_dir") else
        "#4ec9b0"
    )
    hdr = QLabel(f"<b>{icon} {label}</b>")
    hdr.setStyleSheet(f"font-size: 11pt; color: {_hdr_color};")
    lay.addWidget(hdr)

    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet(f"color: {_border}; margin: 2px 0;")
    lay.addWidget(sep)

    # ── Path / target field (editable for file/patch) ───────────────────
    _path_edit = None
    if action_type in ("file", "patch"):
        if base_dir:
            base_note = QLabel(f"📁 基础路径： <code>{base_dir}</code>")
            base_note.setTextFormat(Qt.RichText)
            base_note.setStyleSheet(
                f"color: {_fg_dim}; font-size: 9pt; "
                f"background: {_info_bg}; border: 1px solid {_info_bd}; "
                "border-radius: 3px; padding: 3px 6px;")
            lay.addWidget(base_note)
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("路径�?))
        _path_edit = QLineEdit(target)
        _path_edit.setPlaceholderText("Relative to base path above, or absolute")
        _path_edit.setStyleSheet("font-size: 9pt;")
        path_row.addWidget(_path_edit, 1)
        lay.addLayout(path_row)
    elif action_type == "install":
        pkg_lbl = QLabel(f"<b>包：</b> <code>{target or content.strip()}</code>")
        pkg_lbl.setTextFormat(Qt.RichText)
        lay.addWidget(pkg_lbl)
    elif action_type == "run":
        run_lbl = QLabel(f"<b>语言�?/b> {target}")
        lay.addWidget(run_lbl)
    elif action_type == "git":
        cmd_first_line = content.strip().split("\n")[0]
        cmd_lbl = QLabel(f"<b>命令�?/b> <code>$ git {cmd_first_line}</code>")
        cmd_lbl.setTextFormat(Qt.RichText)
        cmd_lbl.setWordWrap(True)
        cmd_lbl.setStyleSheet(
            f"color: {_git_fg}; font-size: 10pt; "
            f"background: {_git_bg}; border: 1px solid {_git_bd}; "
            "border-radius: 3px; padding: 4px 8px;")
        lay.addWidget(cmd_lbl)
        _cwd = base_dir or "~ (home directory)"
        dir_lbl = QLabel(f"📁 工作目录�?code>{_cwd}</code>")
        dir_lbl.setTextFormat(Qt.RichText)
        dir_lbl.setStyleSheet(
            f"color: {_fg_dim}; font-size: 9pt; "
            f"background: {_info_bg}; border: 1px solid {_info_bd}; "
            "border-radius: 3px; padding: 3px 6px;")
        lay.addWidget(dir_lbl)
    elif action_type == "read":
        path_lbl = QLabel(f"<b>文件�?/b> <code>{target}</code>")
        path_lbl.setTextFormat(Qt.RichText)
        path_lbl.setWordWrap(True)
        path_lbl.setStyleSheet(
            f"color: {_insp_fg}; font-size: 10pt; "
            f"background: {_insp_bg}; border: 1px solid {_insp_bd}; "
            "border-radius: 3px; padding: 4px 8px;")
        lay.addWidget(path_lbl)
        if base_dir:
            bd_lbl = QLabel(f"📁 基础路径： <code>{base_dir}</code>")
            bd_lbl.setTextFormat(Qt.RichText)
            bd_lbl.setStyleSheet(
                f"color: {_fg_dim}; font-size: 9pt; "
                f"background: {_info_bg}; border: 1px solid {_info_bd}; "
                "border-radius: 3px; padding: 3px 6px;")
            lay.addWidget(bd_lbl)
    elif action_type == "ls":
        dir_lbl2 = QLabel(f"<b>目录�?/b> <code>{target or '.'}</code>")
        dir_lbl2.setTextFormat(Qt.RichText)
        dir_lbl2.setWordWrap(True)
        dir_lbl2.setStyleSheet(
            f"color: {_insp_fg}; font-size: 10pt; "
            f"background: {_insp_bg}; border: 1px solid {_insp_bd}; "
            "border-radius: 3px; padding: 4px 8px;")
        lay.addWidget(dir_lbl2)
        if base_dir:
            bd_lbl = QLabel(f"📁 基础路径： <code>{base_dir}</code>")
            bd_lbl.setTextFormat(Qt.RichText)
            bd_lbl.setStyleSheet(
                f"color: {_fg_dim}; font-size: 9pt; "
                f"background: {_info_bg}; border: 1px solid {_info_bd}; "
                "border-radius: 3px; padding: 3px 6px;")
            lay.addWidget(bd_lbl)
    elif action_type == "grep":
        _gparts  = target.split(":", 1)
        _pattern = _gparts[0]
        _scope   = _gparts[1] if len(_gparts) > 1 else "（整个项目）"
        grep_lbl = QLabel(
            f"<b>模式�?/b> <code>{_pattern}</code><br>"
            f"<b>范围�?/b>&nbsp; <code>{_scope}</code>")
        grep_lbl.setTextFormat(Qt.RichText)
        grep_lbl.setWordWrap(True)
        grep_lbl.setStyleSheet(
            f"color: {_insp_fg}; font-size: 10pt; "
            f"background: {_insp_bg}; border: 1px solid {_insp_bd}; "
            "border-radius: 3px; padding: 4px 8px;")
        lay.addWidget(grep_lbl)
        if base_dir:
            bd_lbl = QLabel(f"📁 基础路径： <code>{base_dir}</code>")
            bd_lbl.setTextFormat(Qt.RichText)
            bd_lbl.setStyleSheet(
                f"color: {_fg_dim}; font-size: 9pt; "
                f"background: {_info_bg}; border: 1px solid {_info_bd}; "
                "border-radius: 3px; padding: 3px 6px;")
            lay.addWidget(bd_lbl)

    elif action_type in ("delete", "delete_dir"):
        _is_dir = action_type == "delete_dir"
        _del_path = target
        if base_dir and not os.path.isabs(target):
            _del_path = os.path.join(base_dir, target)
        del_lbl = QLabel(
            f"<b>{'Directory' if _is_dir else 'File'}:</b>&nbsp;"
            f"<code>{target}</code>")
        del_lbl.setTextFormat(Qt.RichText)
        del_lbl.setWordWrap(True)
        del_lbl.setStyleSheet(
            f"color: {_del_fg}; font-size: 10pt; "
            f"background: {_del_bg}; border: 1px solid {_del_bd}; "
            "border-radius: 3px; padding: 4px 8px;")
        lay.addWidget(del_lbl)
        warn_lbl = QLabel(
            "�?&nbsp;<b>This action is irreversible.</b> "
            + ("The entire directory tree will be permanently deleted."
               if _is_dir else "The file will be permanently deleted."))
        warn_lbl.setTextFormat(Qt.RichText)
        warn_lbl.setWordWrap(True)
        warn_lbl.setStyleSheet(
            f"color: {_warn_fg}; font-size: 9pt; "
            f"background: {_warn_bg}; border: 1px solid {_warn_bd}; "
            "border-radius: 3px; padding: 4px 8px;")
        lay.addWidget(warn_lbl)
        if base_dir:
            bd_lbl = QLabel(f"📁 基础路径： <code>{base_dir}</code>")
            bd_lbl.setTextFormat(Qt.RichText)
            bd_lbl.setStyleSheet(
                f"color: {_fg_dim}; font-size: 9pt; "
                f"background: {_info_bg}; border: 1px solid {_info_bd}; "
                "border-radius: 3px; padding: 3px 6px;")
            lay.addWidget(bd_lbl)
    elif action_type in ("rename", "rename_dir"):
        new_path = content.strip()
        rn_lbl = QLabel(
            f"<b>From:</b> <code>{target}</code><br>"
            f"<b>To:</b>&nbsp;&nbsp;&nbsp; <code>{new_path}</code>")
        rn_lbl.setTextFormat(Qt.RichText)
        rn_lbl.setWordWrap(True)
        rn_lbl.setStyleSheet(
            f"color: {_rn_fg}; font-size: 10pt; "
            f"background: {_rn_bg}; border: 1px solid {_rn_bd}; "
            "border-radius: 3px; padding: 4px 8px;")
        lay.addWidget(rn_lbl)
        if base_dir:
            bd_lbl = QLabel(f"📁 基础路径： <code>{base_dir}</code>")
            bd_lbl.setTextFormat(Qt.RichText)
            bd_lbl.setStyleSheet(
                f"color: {_fg_dim}; font-size: 9pt; "
                f"background: {_info_bg}; border: 1px solid {_info_bd}; "
                "border-radius: 3px; padding: 3px 6px;")
            lay.addWidget(bd_lbl)

    # ── Content preview (not shown for git/read/ls/grep/delete/rename) ──
    if action_type not in ("git", "read", "ls", "grep",
                           "delete", "delete_dir", "rename", "rename_dir"):
        if action_type == "patch":
            from qtpy.QtWidgets import QTextEdit as _QTE
            from qtpy.QtGui import QTextOption as _QTO
            from .markdown_renderer import _diff_to_html
            # Check whether the LLM's @@ line numbers match the actual file
            _fp = target
            if base_dir and not os.path.isabs(target):
                _fp = os.path.join(base_dir, target)
            _stale = _check_patch_line_numbers(content, _fp)
            if _stale:
                _warn_parts = []
                for _hdr, _llm_ln, _act_ln in _stale:
                    _warn_parts.append(
                        f"&nbsp;&nbsp;�?<code>{_hdr}</code>"
                        f" �?LLM wrote line&nbsp;<b>{_llm_ln}</b>,"
                        f" actual position: line&nbsp;<b>{_act_ln}</b>")
                warn_lbl = QLabel(
                    "�?&nbsp;<b>Stale line numbers in LLM diff</b> �?the @@ headers "
                    "below are incorrect, but the patch will be applied correctly "
                    "using content matching:<br>" + "<br>".join(_warn_parts))
                warn_lbl.setTextFormat(Qt.RichText)
                warn_lbl.setWordWrap(True)
                warn_lbl.setStyleSheet(
                    f"color: {_warn_fg}; font-size: 9pt; "
                    f"background: {_warn_bg}; border: 1px solid {_warn_bd}; "
                    "border-radius: 3px; padding: 5px 8px;")
                lay.addWidget(warn_lbl)
            preview = _QTE()
            preview.setReadOnly(True)
            preview.setWordWrapMode(_QTO.NoWrap)
            preview.setMaximumHeight(240)
            preview.setStyleSheet(
                f"QTextEdit {{ background: {_prev_bg}; border: 1px solid {_prev_bd}; "
                "border-radius: 3px; padding: 4px; }")
            preview.setHtml(_diff_to_html(content, 9))
        else:
            preview = QPlainTextEdit()
            preview.setReadOnly(True)
            preview.setPlainText(content)
            preview.setMaximumHeight(240)
            preview.setFont(_QFont("Monospace", 9))
            preview.setStyleSheet(
                f"QPlainTextEdit {{ background: {_prev_bg}; color: {_prev_fg}; "
                f"border: 1px solid {_prev_bd}; border-radius: 3px; padding: 4px; }}")
        preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(preview)


    # ── Buttons ─────────────────────────────────────────────────────────
    btns = QDialogButtonBox()
    ok_btn = QPushButton(f"{icon} 执行")
    ok_btn.setDefault(True)
    ok_btn.setStyleSheet(
        f"QPushButton {{ background: {_ok_bg}; color: {_ok_fg}; "
        f"border: 1px solid {_ok_bd}; border-radius: 3px; padding: 4px 16px; }}"
        f"QPushButton:hover {{ background: {_ok_hov}; }}")
    cancel_btn = QPushButton("取消")
    cancel_btn.setStyleSheet(
        "QPushButton { padding: 4px 16px; }")
    btns.addButton(ok_btn, QDialogButtonBox.AcceptRole)
    btns.addButton(cancel_btn, QDialogButtonBox.RejectRole)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)

    result = dlg.exec_()
    confirmed = result == QDialog.Accepted
    final_path = _path_edit.text().strip() if _path_edit else target
    return confirmed, final_path


def show_batch_confirm_dialog(parent, entries, base_dir=""):
    """
    Show all pending agentic actions in a single confirmation dialog.
    entries: dict {block_idx: {action_type, target, content, run_direct, run_direct_chained}}
    Returns list of approved block_idx values (empty list = cancelled / nothing selected).

    Upper area: scrollable list of action rows �?click any row to preview its
    content below.  Checkbox controls whether the action is included in the run.
    Lower area: content preview �?diff (patch), code (run/file), command (git).
    """
    from qtpy.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                 QPushButton, QScrollArea, QWidget, QCheckBox,
                                 QFrame, QTextEdit, QSizePolicy)
    from qtpy.QtCore import Qt, QEvent, QObject
    from qtpy.QtGui import QFont

    _ICONS = {
        "file": "📄", "patch": "🩹", "run": "�?, "install": "📦", "git": "�?,
        "read": "📄", "ls": "📁", "grep": "🔍",
        "delete": "🗑", "delete_dir": "🗑", "rename": "�?, "rename_dir": "�?,
    }
    _COLORS = {
        "file":       "#4a9eff", "patch": "#80c040",
        "run":        "#4ec970", "install": "#40c0c0", "git": "#e8a050",
        "read":       "#80c8f0", "ls":   "#80c8f0",   "grep": "#80c8f0",
        "delete":     "#e05050", "delete_dir": "#c03030",
        "rename":     "#e8a050", "rename_dir": "#e8a050",
    }
    _VERBS = {
        "file":       "Create file",
        "patch":      "Apply patch to",
        "run":        "Run in console",
        "install":    "Install package",
        "git":        "Run git command",
        "read":       "Read file",
        "ls":         "List directory",
        "grep":       "Search in files",
        "delete":     "Delete file",
        "delete_dir": "Delete directory",
        "rename":     "Rename",
        "rename_dir": "Rename directory",
    }

    _dark = _is_dialog_dark()
    # Colour palette �?dark vs light theme
    _bg         = "#1a1a1a" if _dark else "#ffffff"
    _bg2        = "#252525" if _dark else "#f0f0f0"
    _bg3        = "#1e1e1e" if _dark else "#f8f8f8"
    _fg         = "#d4d4d4" if _dark else "#222222"
    _fg_dim     = "#aaaaaa" if _dark else "#555555"
    _fg_hdr     = "#cccccc" if _dark else "#333333"
    _border     = "#444444" if _dark else "#cccccc"
    _sel_bg     = "#1e2a1e" if _dark else "#e8f5e8"
    _warn_fg    = "#e8c060" if _dark else "#7a5000"
    _warn_bg    = "#2a2000" if _dark else "#fff8e0"
    _warn_bd    = "#c8a030"
    _wd_bg      = "#1a2030" if _dark else "#e8f0ff"
    _wd_fg      = "#8ab4f8" if _dark else "#1a3a8a"
    _wd_bd      = "#3a5080" if _dark else "#8ab4f8"
    _chk_col    = "#aaaaaa" if _dark else "#333333"
    _cancel_hfg = "#ffffff" if _dark else "#000000"
    _cancel_hbd = "#aaaaaa" if _dark else "#666666"

    dlg = QDialog(parent)
    dlg.setWindowTitle("Run agentic actions?")
    dlg.setModal(True)
    dlg.setMinimumWidth(520)
    dlg.setMinimumHeight(500)
    lay = QVBoxLayout(dlg)
    lay.setSpacing(6)

    hdr = QLabel("LLM 请求了以下操作：")
    hdr.setStyleSheet(f"color: {_fg_hdr}; font-size: 11px;")
    lay.addWidget(hdr)

    # ── Upper: scrollable list of action rows ────────────────────────────────
    list_scroll = QScrollArea()
    list_scroll.setWidgetResizable(True)
    list_scroll.setFrameShape(QFrame.NoFrame)
    list_scroll.setMaximumHeight(200)
    list_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    list_scroll.setStyleSheet(f"QScrollArea {{ background: {_bg}; border: none; }}")
    inner = QWidget()
    inner.setStyleSheet(f"QWidget {{ background: {_bg}; }}")
    inner_lay = QVBoxLayout(inner)
    inner_lay.setContentsMargins(0, 0, 0, 0)
    inner_lay.setSpacing(4)

    checkboxes   = {}  # block_idx �?QCheckBox
    row_frames   = {}  # block_idx �?QFrame
    _sel         = [None]   # currently selected block_idx (mutable cell)
    _evt_filters = []       # keep event-filter objects alive

    # ── Lower: content preview ───────────────────────────────────────────────
    preview_hdr = QLabel("")
    preview_hdr.setStyleSheet(
        f"color: {_fg_dim}; font-size: 10px; padding: 2px 4px; "
        f"background: {_bg2}; border-radius: 3px;")
    preview_hdr.setWordWrap(False)

    preview_edit = QTextEdit()
    preview_edit.setReadOnly(True)
    preview_edit.setFont(QFont("Monospace", 9))
    preview_edit.setStyleSheet(
        f"QTextEdit {{ background: {_bg}; color: {_fg}; border: 1px solid {_border}; "
        "border-radius: 3px; selection-background-color: #264f78; }")
    preview_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    preview_warn = QLabel()
    preview_warn.setTextFormat(Qt.RichText)
    preview_warn.setWordWrap(True)
    preview_warn.setVisible(False)
    preview_warn.setStyleSheet(
        f"color: {_warn_fg}; font-size: 9pt; "
        f"background: {_warn_bg}; border: 1px solid {_warn_bd}; "
        "border-radius: 3px; padding: 5px 8px;")

    def _row_ss(color, selected):
        """Stylesheet for an action row frame."""
        if selected:
            return (f"QFrame {{ background: {_sel_bg}; border: 2px solid {color}; "
                    "border-radius: 3px; padding: 1px; }}")
        return (f"QFrame {{ background: {_bg3}; border: 1px solid {color}44; "
                "border-radius: 3px; padding: 2px; }}")

    def _preview_for(entry):
        """Populate the preview panel for the given registry entry."""
        atype   = entry["action_type"]
        content = entry.get("content", "")
        tgt     = entry.get("target", "")
        verb    = _VERBS.get(atype, atype)
        color   = _COLORS.get(atype, "#aaa")

        # Header line above the preview
        if atype == "git":
            cmd = content.strip().split("\n")[0]
            preview_hdr.setText(f"$ git {cmd}")
        elif tgt:
            preview_hdr.setText(f"{verb}: {tgt}")
        else:
            preview_hdr.setText(verb)
        preview_hdr.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: bold; padding: 2px 4px; "
            f"background: {_bg2}; border-radius: 3px;")

        # Content
        if atype == "patch" and content.strip():
            from .markdown_renderer import _diff_to_html
            # Check whether the LLM's @@ line numbers match the actual file
            _fp = tgt
            if base_dir and not os.path.isabs(tgt):
                _fp = os.path.join(base_dir, tgt)
            _stale = _check_patch_line_numbers(content, _fp)
            if _stale:
                _warn_parts = []
                for _hdr, _llm_ln, _act_ln in _stale:
                    _warn_parts.append(
                        f"&nbsp;&nbsp;�?<code>{_hdr}</code>"
                        f" �?LLM wrote line&nbsp;<b>{_llm_ln}</b>,"
                        f" actual position: line&nbsp;<b>{_act_ln}</b>")
                preview_warn.setText(
                    "�?&nbsp;<b>Stale line numbers in LLM diff</b> �?the @@ headers "
                    "below are incorrect, but the patch will be applied correctly "
                    "using content matching:<br>" + "<br>".join(_warn_parts))
                preview_warn.setVisible(True)
            else:
                preview_warn.setVisible(False)
            preview_edit.setHtml(_diff_to_html(content, 9))
        elif atype in ("delete", "delete_dir"):
            preview_warn.setVisible(False)
            _kind = "directory tree" if atype == "delete_dir" else "file"
            preview_edit.setPlainText(
                f"�?Permanently delete {_kind}:\n\n  {tgt}\n\n"
                + ("This will recursively remove all contents." if atype == "delete_dir"
                   else "This action cannot be undone."))
        elif atype in ("rename", "rename_dir"):
            preview_warn.setVisible(False)
            new_path = content.strip().split("\n")[0]
            preview_edit.setPlainText(f"From:  {tgt}\nTo:    {new_path}")
        elif content.strip():
            preview_warn.setVisible(False)
            preview_edit.setPlainText(content)
        elif tgt:
            preview_warn.setVisible(False)
            preview_edit.setPlainText(tgt)
        else:
            preview_warn.setVisible(False)
            preview_edit.setPlainText("(no preview)")

    def _select_row(idx):
        """Select a row: highlight it and update the preview."""
        prev = _sel[0]
        _sel[0] = idx

        # Update border/background on old and new row
        for i, fr in row_frames.items():
            entry_i = entries[i]
            color_i = _COLORS.get(entry_i["action_type"], "#aaa")
            fr.setStyleSheet(_row_ss(color_i, i == idx))

        _preview_for(entries[idx])

    # ── Build rows ───────────────────────────────────────────────────────────
    class _RowClickFilter(QObject):
        """Event filter: clicking anywhere on a row (except the checkbox) selects it."""
        def __init__(self, idx_):
            super().__init__()
            self._idx = idx_
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
                _select_row(self._idx)
            return False   # never consume �?let checkbox handle itself

    sorted_idxs = sorted(entries.keys())
    for idx in sorted_idxs:
        entry = entries[idx]
        atype  = entry["action_type"]
        tgt    = entry["target"]
        icon   = _ICONS.get(atype, "�?)
        color  = _COLORS.get(atype, "#aaa")
        verb   = _VERBS.get(atype, atype)
        content = entry.get("content", "")

        row = QFrame()
        row.setStyleSheet(_row_ss(color, False))
        row.setCursor(Qt.PointingHandCursor)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(6, 3, 6, 3)
        rl.setSpacing(8)

        if atype == "git":
            full_cmd    = content.strip().split("\n")[0]
            cmd_preview = full_cmd[:60] + ("�? if len(full_cmd) > 60 else "")
            lbl_text    = f"{icon}  $ git {cmd_preview}"
            tooltip     = f"$ git {full_cmd}"
        elif atype == "run":
            lbl_text  = f"{icon}  {verb} ({tgt})"
            tooltip   = content.strip()[:300]
        elif atype == "grep":
            parts    = tgt.split(":", 1)
            pat      = parts[0]
            scope    = f"  in {parts[1]}" if len(parts) > 1 else ""
            lbl_text = f"{icon}  {verb}: {pat}{scope}"
            tooltip  = tgt
        elif atype in ("rename", "rename_dir"):
            new_path = content.strip().split("\n")[0]
            lbl_text = f"{icon}  {verb}: {tgt} �?{new_path}"
            tooltip  = f"{tgt} �?{new_path}"
        else:
            lbl_text  = f"{icon}  {verb}: {tgt}"
            tooltip   = tgt
        if len(lbl_text) > 74:
            lbl_text = lbl_text[:71] + "�?

        lbl = QLabel(lbl_text)
        lbl.setToolTip(tooltip)
        lbl.setStyleSheet(
            f"color: {color}; font-size: 10px; background: transparent; border: none;")
        rl.addWidget(lbl, 1)

        chk = QCheckBox()
        chk.setChecked(True)
        chk.setStyleSheet(f"QCheckBox {{ color: {_chk_col}; }}")
        # Clicking the checkbox also selects this row for preview
        chk.clicked.connect(lambda _checked, i=idx: _select_row(i))
        rl.addWidget(chk)
        checkboxes[idx]  = chk
        row_frames[idx]  = row

        # Install click filter on row frame AND its label
        for widget in (row, lbl):
            f = _RowClickFilter(idx)
            widget.installEventFilter(f)
            _evt_filters.append(f)

        inner_lay.addWidget(row)

    inner_lay.addStretch(1)
    list_scroll.setWidget(inner)
    lay.addWidget(list_scroll)

    # ── Separator ────────────────────────────────────────────────────────────
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet(f"color: {_border};")
    lay.addWidget(sep)

    # ── Preview section ──────────────────────────────────────────────────────
    lay.addWidget(preview_hdr)
    lay.addWidget(preview_warn)      # stale-line-number warning (hidden by default)
    lay.addWidget(preview_edit, 1)   # stretch factor 1 �?takes remaining space

    # Auto-select the first row so the preview is populated immediately
    if sorted_idxs:
        _select_row(sorted_idxs[0])

    # ── Working dir line ─────────────────────────────────────────────────────
    if base_dir:
        wd_lbl = QLabel(f"📁  {base_dir}")
        wd_lbl.setToolTip(f"Working directory: {base_dir}")
        wd_lbl.setStyleSheet(
            f"color: {_wd_fg}; font-size: 10px; "
            f"background: {_wd_bg}; border: 1px solid {_wd_bd}; "
            "border-radius: 3px; padding: 3px 6px;")
        lay.addWidget(wd_lbl)

    # ── Buttons ──────────────────────────────────────────────────────────────
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    run_btn = QPushButton("运行选中�?)
    run_btn.setDefault(True)
    run_btn.setStyleSheet(
        "QPushButton { color: #4ec970; border: 1px solid #4ec970; border-radius: 3px; "
        "padding: 4px 16px; background: transparent; }"
        "QPushButton:hover { background: #4ec97033; }")
    cancel_btn = QPushButton("取消")
    cancel_btn.setStyleSheet(
        f"QPushButton {{ color: {_fg_dim}; border: 1px solid {_border}; border-radius: 3px; "
        "padding: 4px 16px; background: transparent; }"
        f"QPushButton:hover {{ color: {_cancel_hfg}; border-color: {_cancel_hbd}; }}")
    btn_row.addWidget(run_btn)
    btn_row.addWidget(cancel_btn)
    lay.addLayout(btn_row)

    run_btn.clicked.connect(dlg.accept)
    cancel_btn.clicked.connect(dlg.reject)

    if dlg.exec_() != QDialog.Accepted:
        return []

    return [idx for idx, chk in checkboxes.items() if chk.isChecked()]
