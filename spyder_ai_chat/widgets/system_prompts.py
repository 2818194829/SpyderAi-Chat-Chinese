# -*- coding: utf-8 -*-
"""Saved system prompts manager (C) 2026 by Maciej Piecko"""

import json
import os
import uuid
from datetime import datetime

CONFIG_DIR  = os.path.join(os.path.expanduser("~"), ".spyder_ai_chat")
PROMPTS_FILE = os.path.join(CONFIG_DIR, "system_prompts.json")

# Sentinel ID used for "Use custom" (no saved prompt selected)
CUSTOM_ID = "__custom__"


def _ensure_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_prompts():
    """Return list of prompt dicts: [{id, title, content}, ...], ordered by title."""
    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save_prompts(prompts):
    """Persist the full prompts list to disk."""
    _ensure_dir()
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)


def new_prompt(title, content):
    """Create and persist a new prompt. Returns the new prompt dict."""
    prompts = load_prompts()
    prompt = {
        "id":      str(uuid.uuid4()),
        "title":   title.strip(),
        "content": content.strip(),
        "created": datetime.now().isoformat(),
    }
    prompts.append(prompt)
    save_prompts(prompts)
    return prompt


def update_prompt(prompt_id, title, content):
    """Update an existing prompt by id. Returns True on success."""
    prompts = load_prompts()
    for p in prompts:
        if p["id"] == prompt_id:
            p["title"]   = title.strip()
            p["content"] = content.strip()
            save_prompts(prompts)
            return True
    return False


def delete_prompt(prompt_id):
    """Delete a prompt by id. Returns True on success."""
    prompts = load_prompts()
    new = [p for p in prompts if p["id"] != prompt_id]
    if len(new) == len(prompts):
        return False
    save_prompts(new)
    return True


def get_prompt(prompt_id):
    """Return a single prompt dict by id, or None."""
    for p in load_prompts():
        if p["id"] == prompt_id:
            return p
    return None
