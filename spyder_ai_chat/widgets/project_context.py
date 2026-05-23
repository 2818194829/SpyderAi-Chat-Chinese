# -*- coding: utf-8 -*-
"""Project-wide context collection for AI Chat plugin. (C) 2026 by Maciej Piecko"""

import fnmatch
import hashlib
import os

# ---------------------------------------------------------------------------
# Default exclusions
# ---------------------------------------------------------------------------

DEFAULT_EXCL_DIRS = {
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    ".venv", "venv", "env",
    "node_modules",
    "dist", "build",
    ".idea", ".vscode", ".tox",
}

DEFAULT_EXCL_PATTERNS = (
    "*.pyc", "*.pyo", "*.pyd",
    "*.egg-info", "*.egg",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.ico",
    "*.woff", "*.woff2", "*.ttf", "*.eot",
    "*.zip", "*.tar", "*.gz", "*.bz2", "*.rar", "*.7z",
    "*.exe", "*.dll", "*.so", "*.dylib", "*.bin", "*.obj",
    "*.db", "*.sqlite", "*.sqlite3",
    ".DS_Store", "Thumbs.db",
    "*.lock", "*.min.js", "*.min.css",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash(text):
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


# Readable metadata files allowed directly inside the .git/ directory.
# Subdirectories of .git/ (objects/, logs/, refs/, hooks/, …) remain excluded.
_GIT_ALLOWED_FILES = {
    "HEAD", "COMMIT_EDITMSG", "MERGE_MSG", "config",
    "ORIG_HEAD", "FETCH_HEAD", "MERGE_HEAD", "packed-refs",
}


def _is_excluded(rel_path, gitignore_patterns, extra_patterns):
    parts = rel_path.replace("\\", "/").split("/")
    # Special-case: allow specific readable files directly inside .git/
    if len(parts) == 2 and parts[0] == ".git" and parts[1] in _GIT_ALLOWED_FILES:
        return False
    # Check directory components
    for part in parts[:-1]:
        if part in DEFAULT_EXCL_DIRS or part.startswith("."):
            return True
    name = parts[-1]
    # Default file patterns
    for pat in DEFAULT_EXCL_PATTERNS:
        if fnmatch.fnmatch(name, pat):
            return True
    # Gitignore patterns (name and full relative path)
    for pat in gitignore_patterns:
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel_path, pat):
            return True
    # Extra user patterns
    for pat in extra_patterns:
        pat = pat.strip()
        if pat and (fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel_path, pat)):
            return True
    return False


def _lang(path):
    ext = os.path.splitext(path)[1].lower()
    return {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".html": "html", ".css": "css", ".json": "json",
        ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
        ".toml": "toml", ".sh": "bash", ".cpp": "cpp", ".c": "c",
        ".h": "c", ".java": "java", ".rs": "rust", ".go": "go",
        ".rb": "ruby", ".php": "php", ".cs": "csharp", ".r": "r",
        ".sql": "sql", ".xml": "xml",
    }.get(ext, "")


def _file_block(f, label=None):
    lang = _lang(f["path"])
    fence = f"```{lang}" if lang else "```"
    suffix = f"  ({label})" if label else ""
    # Prefer absolute path so the LLM can use it directly in patch/file fences
    display_path = f.get("abs_path") or f["path"]
    return f"### File: {display_path}{suffix}\n{fence}\n{f['content']}\n```\n---"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_gitignore(root):
    """Return list of non-comment gitignore patterns from the project root."""
    patterns = []
    try:
        with open(os.path.join(root, ".gitignore"), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    except Exception:
        pass
    return patterns


def get_top_level_folders(root):
    """Return sorted list of non-excluded top-level subdirectory names."""
    try:
        return sorted(
            d for d in os.listdir(root)
            if os.path.isdir(os.path.join(root, d))
            and d not in DEFAULT_EXCL_DIRS
            and not d.startswith(".")
        )
    except Exception:
        return []


def collect_project_files(root, included_folders=None, extra_patterns=(),
                          max_file_kb=256, max_files=500):
    """
    Walk the project root and return a list of FileEntry dicts for text files.

    included_folders: list of top-level folder names to include (None = all).
    extra_patterns:   additional glob exclusion patterns (from settings).
    """
    results = []
    max_bytes = max_file_kb * 1024
    gi = parse_gitignore(root)
    extra = [p for p in extra_patterns if p.strip()]

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""

        # Prune excluded dirs in-place (prevents os.walk descending into them).
        # Exception: allow one-level descent into .git at root to collect
        # readable metadata files via _GIT_ALLOWED_FILES in _is_excluded.
        if rel_dir == ".git":
            dirnames[:] = []   # never descend into .git sub-dirs
        else:
            dirnames[:] = [
                d for d in dirnames
                if (d not in DEFAULT_EXCL_DIRS and not d.startswith("."))
                or (rel_dir == "" and d == ".git")   # allow .git at root only
            ]

        # Restrict top-level descent to included_folders if specified
        if included_folders is not None and rel_dir == "":
            dirnames[:] = [
                d for d in dirnames
                if d in included_folders or d == ".git"
            ]

        for fname in filenames:
            if len(results) >= max_files:
                return results
            rel_path = f"{rel_dir}/{fname}" if rel_dir else fname
            if _is_excluded(rel_path, gi, extra):
                continue
            abs_path = os.path.join(dirpath, fname)
            try:
                if os.path.getsize(abs_path) > max_bytes:
                    continue
                with open(abs_path, "r", encoding="utf-8", errors="strict") as fh:
                    content = fh.read()
            except Exception:
                continue
            results.append({
                "path": rel_path,
                "abs_path": abs_path,
                "hash": _hash(content),
                "size": len(content.encode("utf-8")),
                "content": content,
                "virtual": False,
            })
    return results


def collect_unsaved_files(editor_widget):
    """
    Collect truly new (never-saved) files from open editor buffers.
    These have no valid disk path so they cannot be found by collect_project_files.
    Always included in project context regardless of folder selection.

    editor_widget: result of editor_plugin.get_widget()
    """
    if editor_widget is None:
        return []
    results = []
    seen = set()
    for editorstack in _iter_editorstacks(editor_widget):
        if not hasattr(editorstack, "data"):
            continue
        for finfo in editorstack.data:
            editor = getattr(finfo, "editor", None)
            filename = getattr(finfo, "filename", "") or ""
            if editor is None or id(editor) in seen:
                continue
            seen.add(id(editor))
            if filename and os.path.exists(filename):
                continue  # real disk file — handled by collect_project_files
            display = os.path.basename(filename) if filename else f"untitled_{id(editor)}"
            content = editor.toPlainText()
            if not content.strip():
                continue
            results.append({
                "path": f"[unsaved] {display}",
                "abs_path": None,
                "hash": _hash(content),
                "size": len(content.encode("utf-8")),
                "content": content,
                "virtual": True,
            })
    return results


def get_effective_files(disk_files, editor_widget):
    """
    For disk files currently open in the editor, replace cached disk content
    with the live buffer content (includes unsaved edits).
    Returns updated list with refreshed hashes.
    """
    if editor_widget is None:
        return disk_files
    path_to_editor = {}
    for editorstack in _iter_editorstacks(editor_widget):
        if not hasattr(editorstack, "data"):
            continue
        for finfo in editorstack.data:
            fn = getattr(finfo, "filename", "") or ""
            ed = getattr(finfo, "editor", None)
            if fn and ed:
                path_to_editor[fn] = ed
    result = []
    for f in disk_files:
        abs_path = f.get("abs_path")
        if abs_path and abs_path in path_to_editor:
            content = path_to_editor[abs_path].toPlainText()
            result.append({**f, "content": content, "hash": _hash(content)})
        else:
            result.append(f)
    return result


def diff_files(old_hashes, current_files):
    """
    Compare old_hashes {path: hash} against current_files list.
    Returns (changed, added, removed_paths).
    """
    old = set(old_hashes)
    cur = {f["path"]: f for f in current_files}
    cur_paths = set(cur)
    added   = [cur[p] for p in cur_paths - old]
    removed = list(old - cur_paths)
    changed = [cur[p] for p in cur_paths & old if cur[p]["hash"] != old_hashes[p]]
    return changed, added, removed


def build_full_context_text(root, files, branch=None, diff_stat=None):
    """Build the full project context block sent with the first message."""
    name = os.path.basename(root) if root else "Project"
    tok  = estimate_tokens(files)
    header = (
        f"Project context: {name}  ({len(files)} files, ~{tok:,} tokens)\n"
        f"Root: {root}"
    )
    if branch:
        header += f"\nBranch: {branch}"
    if diff_stat:
        header += f"\nUncommitted: {diff_stat}"
    blocks = [header] + [_file_block(f) for f in files]
    return "\n\n".join(blocks)


def build_delta_text(changed, added, removed_paths, root=None,
                     branch=None, diff_stat=None):
    """Build the delta block appended to messages when files change."""
    n = len(changed) + len(added) + len(removed_paths)
    header = f"[Project context update — {n} change(s)]"
    if root:
        header += f"\nRoot: {root}"
    if branch:
        header += f"\nBranch: {branch}"
    if diff_stat:
        header += f"\nUncommitted: {diff_stat}"
    parts = [header]
    for f in added:
        parts.append(_file_block(f, "new"))
    for f in changed:
        parts.append(_file_block(f, "changed"))
    for p in removed_paths:
        parts.append(f"### File: {p}  (deleted)")
    return "\n\n".join(parts)


def estimate_tokens(files):
    """Rough token estimate: 1 token ≈ 4 characters."""
    return sum(len(f.get("content", "")) for f in files) // 4


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _iter_editorstacks(widget):
    from qtpy.QtWidgets import QWidget as _QW
    out = []
    try:
        if type(widget).__name__ == "EditorStack":
            out.append(widget)
        for child in widget.children():
            if isinstance(child, _QW):
                out.extend(_iter_editorstacks(child))
    except Exception:
        pass
    return out
