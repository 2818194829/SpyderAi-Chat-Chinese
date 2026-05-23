# -*- coding: utf-8 -*-
"""
Slash-command aliases for AI Chat plugin. (C) 2026 by Maciej Piecko

Commands are stored in ~/.spyder_ai_chat/commands.json as a list of:
  { "name": "tests", "prompt": "Write comprehensive unit tests for the following code:" }

The 'name' is without the leading '/'.  Minimum 2 characters.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in default commands (shipped with the plugin)
# ---------------------------------------------------------------------------
DEFAULT_COMMANDS = [
    {
        "name": "tests",
        "prompt": (
            "为以下代码生成全面的单元测试。"
            "覆盖边界情况、典型输入和错误条件。"
            "使用适合该语言的测试框架。"
        ),
    },
    {
        "name": "simplify",
        "prompt": (
            "简化以下代码。使其更简洁、更易读、"
            "更易维护，但不改变其行为。"
        ),
    },
    {
        "name": "fix",
        "prompt": (
            "修复以下代码中的所有问题和编译错误。"
            "简要解释每个修复。"
        ),
    },
    {
        "name": "explain",
        "prompt": (
            "解释以下代码的工作原理。"
            "描述整体结构、关键逻辑以及任何不明显的部分。"
        ),
    },
    {
        "name": "doc",
        "prompt": (
            "为以下代码编写文档。添加清晰的文档字符串、"
            "参数说明、返回值说明"
            "以及在有帮助的地方添加内联注释。"
        ),
    },
]


# ---------------------------------------------------------------------------
# Built-in plugin commands (not user-editable; action-based, not prompt-based)
# ---------------------------------------------------------------------------
BUILTIN_COMMANDS = [
    {
        "name":        "clear",
        "description": "清除所有消息 — 保留模型、系统提示词和所有设置",
        "tooltip": (
            "清除当前对话中的所有消息（包括压缩\n"
            "总结），保留活跃模型、系统提示词、推理\n"
            "参数、项目上下文和集合。\n\n"
            "清除的聊天会先保存到历史。"
        ),
        "action":      "clear",
        "visible_when": lambda cfg, proj, ag: True,
    },
    {
        "name":        "compact",
        "description": "手动触发 LLM 总结压缩聊天历史",
        "tooltip": (
            "手动触发 LLM 总结压缩聊天历史。\n\n"
            "仅在满足以下所有条件时可见和可用：\n"
            "  • 上下文历史压缩已启用\n"
            "    （设置 → 上下文 → 上下文历史压缩）\n"
            "  • 压缩策略设置为 LLM 总结\n"
            "  • 自主模式设置为完全\n"
            "    （设置 → 代理 → 自主模式）\n"
            "  • 当前聊天未启用项目上下文\n\n"
            "与自动压缩不同，此命令忽略 Token 阈值\n"
            "并立即触发。"
        ),
        "action":      "compact",
        # visible_when(history_cfg, proj_enabled, agentic_cfg) -> bool
        # Mirrors the same guards as _maybe_trigger_compaction():
        #   compaction enabled + LLM strategy + full autonomous mode + no project context
        "visible_when": lambda cfg, proj, ag: (
            cfg.get("compaction_enabled", False)
            and cfg.get("compaction_strategy", "cutoff") == "llm"
            and not proj
            and ag.get("autonomous_mode") == "full"
        ),
    },
]


def get_builtin_names():
    """Return set of reserved built-in command names (case-sensitive)."""
    return {b["name"] for b in BUILTIN_COMMANDS}


def get_active_builtins(history_cfg, proj_enabled=False, agentic_cfg=None):
    """Return built-in commands whose visibility condition passes.

    Args:
        history_cfg:  dict from _history_cfg()
        proj_enabled: bool — whether project context is currently active
        agentic_cfg:  dict from _agentic_cfg()
    """
    agentic_cfg = agentic_cfg or {}
    return [b for b in BUILTIN_COMMANDS
            if b.get("visible_when", lambda c, p, a: True)(
                history_cfg, proj_enabled, agentic_cfg)]


# ---------------------------------------------------------------------------
# Storage path
# ---------------------------------------------------------------------------
def _commands_path():
    d = os.path.join(os.path.expanduser("~"), ".spyder_ai_chat")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "commands.json")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load_commands():
    """Load commands from disk.  Returns list of {name, prompt} dicts.
    If no file exists yet, seeds with DEFAULT_COMMANDS and saves."""
    path = _commands_path()
    if not os.path.exists(path):
        save_commands(DEFAULT_COMMANDS)
        return list(DEFAULT_COMMANDS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Validate minimal structure
        result = []
        for item in data:
            if isinstance(item, dict) and "name" in item and "prompt" in item:
                name = str(item["name"]).strip().lstrip("/")
                prompt = str(item["prompt"]).strip()
                if len(name) >= 2 and prompt:
                    result.append({"name": name, "prompt": prompt})
        return result
    except Exception:
        logger.warning("Failed to load commands from %s — using defaults", path,
                       exc_info=True)
        return list(DEFAULT_COMMANDS)


def save_commands(commands):
    """Persist the given list of {name, prompt} dicts to disk."""
    try:
        with open(_commands_path(), "w", encoding="utf-8") as f:
            json.dump(commands, f, indent=2, ensure_ascii=False)
    except Exception:
        logger.warning("Failed to save commands to %s", _commands_path(),
                       exc_info=True)


def get_command_prompt(name, commands):
    """Return the prompt string for the given command name (without '/'),
    or None if not found."""
    for cmd in commands:
        if cmd["name"] == name:
            return cmd["prompt"]
    return None
