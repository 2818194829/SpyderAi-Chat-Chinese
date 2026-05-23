# -*- coding: utf-8 -*-
"""Chat History Manager — one JSON file per chat session. (C) 2026 by Maciej Piecko

Collections are stored as subdirectories of CHATS_DIR.
The Default collection lives at the CHATS_DIR root (backward compatible).
"""

import json
import os
from datetime import datetime


CHATS_DIR = os.path.join(os.path.expanduser("~"), ".spyder_ai_chat", "chats")

# Reserved collection name used internally for "search all" mode
_ALL_MARKER = "__all__"


def _ensure_dir():
    os.makedirs(CHATS_DIR, exist_ok=True)


def _collection_dir(collection):
    """Return the absolute directory for a given collection.

    collection=None or '' → Default (CHATS_DIR root).
    Any other string      → CHATS_DIR/<collection> subdir (created lazily).
    """
    _ensure_dir()
    if collection and collection != _ALL_MARKER:
        d = os.path.join(CHATS_DIR, collection)
        os.makedirs(d, exist_ok=True)
        return d
    return CHATS_DIR


def _chat_path(filename, collection=None):
    return os.path.join(_collection_dir(collection), filename)


def _new_filename():
    """Generate a unique filename based on current timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json"


# ---------------------------------------------------------------------------
# Collection management helpers
# ---------------------------------------------------------------------------

def list_collections():
    """Return sorted list of user-named collection names (subdir names)."""
    _ensure_dir()
    try:
        return sorted(
            e.name for e in os.scandir(CHATS_DIR)
            if e.is_dir() and not e.name.startswith('.')
        )
    except Exception:
        return []


def validate_collection_name(name):
    """Return (ok, error_message) for a proposed collection name."""
    if not name or not name.strip():
        return False, "集合名称不能为空。"
    name = name.strip()
    if name == _ALL_MARKER:
        return False, f"'{_ALL_MARKER}' 是保留名称。"
    if any(c in name for c in ('/', '\\', '\0')):
        return False, "集合名称不能包含斜杠或空字符。"
    if name.startswith('.'):
        return False, "集合名称不能以点开头。"
    # Case-insensitive duplicate check (important on Windows)
    existing = [c.lower() for c in list_collections()]
    if name.lower() in existing:
        return False, f"名为 '{name}' 的集合已存在。"
    return True, ""


def create_collection(name):
    """Create a new collection directory.
    Returns (True, '') on success, (False, error_msg) on failure.
    """
    ok, err = validate_collection_name(name)
    if not ok:
        return False, err
    try:
        os.makedirs(os.path.join(CHATS_DIR, name.strip()), exist_ok=False)
        return True, ""
    except FileExistsError:
        return False, f"集合 '{name}' 已存在。"
    except Exception as e:
        return False, str(e)


def rename_collection(old_name, new_name):
    """Rename a collection directory.
    Returns (True, '') on success, (False, error_msg) on failure.
    """
    new_name = new_name.strip()
    # Validate new name but skip the duplicate check (we'll do it manually)
    if not new_name:
        return False, "新名称不能为空。"
    if new_name == _ALL_MARKER:
        return False, f"'{_ALL_MARKER}' 是保留名称。"
    if any(c in new_name for c in ('/', '\\', '\0')):
        return False, "名称不能包含斜杠或空字符。"
    if new_name.startswith('.'):
        return False, "名称不能以点开头。"

    existing = [c.lower() for c in list_collections() if c != old_name]
    if new_name.lower() in existing:
        return False, f"名为 '{new_name}' 的集合已存在。"

    old_path = os.path.join(CHATS_DIR, old_name)
    new_path = os.path.join(CHATS_DIR, new_name)
    if not os.path.isdir(old_path):
        return False, f"Collection '{old_name}' not found."
    try:
        os.rename(old_path, new_path)
        return True, ""
    except Exception as e:
        return False, str(e)


def move_chat(filename, from_collection, to_collection):
    """Move a chat file from one collection to another.
    Returns True on success, False on error.
    from_collection / to_collection: '' or None = Default root.
    """
    src = _chat_path(filename, from_collection)
    dst_dir = _collection_dir(to_collection)
    dst = os.path.join(dst_dir, filename)
    if not os.path.isfile(src):
        return False
    if os.path.abspath(src) == os.path.abspath(dst):
        return True  # already there
    try:
        os.makedirs(dst_dir, exist_ok=True)
        os.rename(src, dst)
        return True
    except Exception:
        return False


def delete_collection(name, move_to=None):
    """Delete a collection directory.

    move_to=None  → delete all chats inside (and remove dir).
    move_to=''    → move chats to Default collection first.
    move_to='X'   → move chats to collection X first.

    Returns (True, '') on success, (False, error_msg) on failure.
    """
    coll_path = os.path.join(CHATS_DIR, name)
    if not os.path.isdir(coll_path):
        return False, f"集合 '{name}' 未找到。"
    try:
        for fname in os.listdir(coll_path):
            if not fname.endswith(".json"):
                continue
            if move_to is not None:
                move_chat(fname, name, move_to)
            else:
                try:
                    os.remove(os.path.join(coll_path, fname))
                except Exception:
                    pass
        # Remove directory (only if empty, or force-remove)
        try:
            os.rmdir(coll_path)
        except OSError:
            # Might have non-json files; remove remaining contents
            import shutil
            shutil.rmtree(coll_path, ignore_errors=True)
        return True, ""
    except Exception as e:
        return False, str(e)


def get_chat_collection(filename):
    """Find which collection a given filename is in.
    Returns the collection name ('' for Default) or None if not found.
    """
    # Check Default first
    if os.path.isfile(_chat_path(filename, None)):
        return ""
    for coll in list_collections():
        if os.path.isfile(_chat_path(filename, coll)):
            return coll
    return None


# ---------------------------------------------------------------------------
# Core chat functions (all with optional collection param)
# ---------------------------------------------------------------------------

def save_chat(messages, system_prompt="", model="", filename=None,
              prompt_id=None, provider=None, infer_params=None,
              project_context=None, collection=None):
    """
    Save a chat session to disk.
    Returns the filename used (so caller can track the current chat file).

    collection:   name of the collection subdir, or None/'' for Default.
    prompt_id:    id of the saved system prompt used, or None / CUSTOM_ID.
    provider:     provider type string (e.g. "openai", "groq", "ollama").
    infer_params: dict of explicitly-set inference parameter values only.
    """
    if not messages:
        return None
    _ensure_dir()

    # If updating an existing file, check if messages changed
    existing_saved_at = None
    existing_msg_count = None
    if filename:
        try:
            with open(_chat_path(filename, collection), "r", encoding="utf-8") as f:
                existing = json.load(f)
                existing_saved_at = existing.get("saved_at")
                existing_msg_count = len(existing.get("messages", []))
        except Exception:
            pass

    # Only bump saved_at if message count changed (new messages added)
    if (existing_saved_at is not None and
            existing_msg_count == len(messages)):
        saved_at = existing_saved_at
    else:
        saved_at = datetime.now().isoformat()

    if filename is None:
        filename = _new_filename()

    # Preview: first user message, up to 60 chars.
    preview = ""
    for m in messages:
        if m.get("role") == "user":
            content = m.get("content", "")
            if content.startswith("File: "):
                parts = content.rsplit("```", 2)
                content = parts[-1].strip() if len(parts) >= 2 else content
            spans = m.get("command_spans")
            if spans:
                remaining = content
                for s, l in sorted(spans, key=lambda x: x[0], reverse=True):
                    remaining = remaining[:s] + remaining[s+l:]
                remaining = remaining.strip(" \n")
                cmd_tokens = " ".join(
                    content[s:s+l] for s, l in sorted(spans, key=lambda x: x[0])
                )
                if remaining:
                    suffix = remaining
                else:
                    attachments = m.get("attachments", [])
                    if attachments:
                        suffix = attachments[0].get("name", "")
                    else:
                        from datetime import datetime as _dt
                        suffix = "at " + _dt.now().strftime("%Y-%m-%d %H:%M")
                preview = f"{cmd_tokens} — {suffix}"
            else:
                preview = content
            preview = preview[:60].replace("\n", " ")
            break

    data = {
        "filename":        filename,
        "saved_at":        saved_at,
        "preview":         preview,
        "model":           model,
        "system_prompt":   system_prompt,
        "prompt_id":       prompt_id,
        "provider":        provider,
        "infer_params":    infer_params or {},
        "project_context": project_context,
        "messages":        messages,
    }
    with open(_chat_path(filename, collection), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return filename


def load_chat(filename, collection=None):
    """Load a chat session from disk. Returns dict or None on error.

    Always returns 'provider' (str or None) and 'infer_params' (dict)
    even for old files that predate these fields.
    """
    try:
        with open(_chat_path(filename, collection), "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("provider", None)
        data.setdefault("infer_params", {})
        return data
    except Exception:
        return None


def delete_chat(filename, collection=None):
    """Delete a chat file. Returns True on success."""
    try:
        os.remove(_chat_path(filename, collection))
        return True
    except Exception:
        return False


def _list_chats_in_dir(directory, collection_name="", limit=None):
    """Internal: list chat metadata from a single directory."""
    results = []
    try:
        for fname in os.listdir(directory):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(directory, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append({
                    "filename":   fname,
                    "collection": collection_name,
                    "saved_at":   data.get("saved_at", ""),
                    "preview":    data.get("preview", "(no preview)"),
                    "model":      data.get("model", ""),
                })
            except Exception:
                continue
    except Exception:
        pass
    return results


def list_chats(collection=None, all_collections=False, limit=200):
    """
    Return list of chat metadata dicts, newest first.
    Each dict has: filename, collection, saved_at, preview, model.

    collection=None/'' → Default (root dir).
    all_collections=True → merge results from all collections + Default.
    """
    _ensure_dir()
    if all_collections:
        results = _list_chats_in_dir(CHATS_DIR, "")
        for coll in list_collections():
            coll_dir = os.path.join(CHATS_DIR, coll)
            results.extend(_list_chats_in_dir(coll_dir, coll))
    else:
        coll_name = collection if (collection and collection != _ALL_MARKER) else ""
        results = _list_chats_in_dir(_collection_dir(collection), coll_name)

    results.sort(key=lambda x: x["saved_at"], reverse=True)
    return results[:limit]


def search_chats(query, collection=None, all_collections=False, limit=200):
    """
    Return chats whose preview or message content contains *query* (case-insensitive).
    Same metadata format as list_chats(), same newest-first ordering.
    """
    if not query:
        return list_chats(collection=collection,
                          all_collections=all_collections, limit=limit)

    q = query.lower()
    _ensure_dir()

    if all_collections:
        dirs = [(CHATS_DIR, "")]
        for coll in list_collections():
            dirs.append((os.path.join(CHATS_DIR, coll), coll))
    else:
        coll_name = collection if (collection and collection != _ALL_MARKER) else ""
        dirs = [(_collection_dir(collection), coll_name)]

    results = []
    for directory, coll_name in dirs:
        try:
            for fname in os.listdir(directory):
                if not fname.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(directory, fname), "r",
                              encoding="utf-8") as f:
                        data = json.load(f)
                    preview = data.get("preview", "")
                    matched = q in preview.lower()
                    if not matched:
                        for msg in data.get("messages", []):
                            content = msg.get("content", "")
                            if isinstance(content, str) and q in content.lower():
                                matched = True
                                break
                    if matched:
                        results.append({
                            "filename":   fname,
                            "collection": coll_name,
                            "saved_at":   data.get("saved_at", ""),
                            "preview":    preview or "(no preview)",
                            "model":      data.get("model", ""),
                        })
                except Exception:
                    continue
        except Exception:
            continue

    results.sort(key=lambda x: x["saved_at"], reverse=True)
    return results[:limit]
