# -*- coding: utf-8 -*-
"""
AI FIM Completion – configuration, provider registry, FIM prompt templates.
(C) 2026 Maciej Piecko
"""

# ---------------------------------------------------------------------------
# CONF_DEFAULTS  (list of (key, default_value) tuples)
# ---------------------------------------------------------------------------
CONF_DEFAULTS = [
    # Keys prefixed with fim_ so they live alongside ai_chat_plugin keys
    # in the "ai_chat_plugin" CONF_SECTION without collision.
    ("fim_enabled",             False),
    ("fim_api_url",             "http://localhost:11434"),
    ("fim_api_key",             ""),
    ("fim_model",               "qwen2.5-coder:7b"),
    ("fim_backend_type",        "ollama_generate"),
    ("fim_max_tokens",          128),
    ("fim_temperature_x10",     0),      # stored x10: 0 = 0.0, 7 = 0.7
    ("fim_context_before",      4000),
    ("fim_context_after",       1000),
    ("fim_trigger_mode",        "auto"),
    ("fim_debounce_ms",         600),
    ("fim_trigger_languages",   ["python", "r"]),
]

# ---------------------------------------------------------------------------
# Backend types
# ---------------------------------------------------------------------------
# "ollama_generate"    – POST /api/generate  (prompt + suffix fields)
# "openai_completions" – POST /v1/completions (prompt + suffix fields, OpenAI compat)
# "codestral"          – POST /v1/fim/completions (Mistral/Codestral dedicated FIM)
# "chat"               – POST /v1/chat/completions (chat-based FIM, last resort)
BACKEND_TYPES = [
    "ollama_generate",
    "openai_completions",
    "codestral",
    "chat",
]

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------
# Each entry:
#   "label"        – human-readable name shown in settings dropdown
#   "api_url"      – default base URL
#   "backend_type" – one of BACKEND_TYPES
#   "models"       – suggested model names shown as hints
#   "needs_key"    – whether an API key is normally required
#   "key_note"     – tooltip note about the key
# ---------------------------------------------------------------------------
PROVIDER_REGISTRY = {
    "ollama": {
        "label":        "Ollama（本地）",
        "api_url":      "http://localhost:11434",
        "backend_type": "ollama_generate",
        "models":       ["qwen2.5-coder:7b", "deepseek-coder-v2:16b",
                         "codegemma:2b", "starcoder2:7b"],
        "needs_key":    False,
        "key_note":     "Ollama 不需要 API 密钥。",
    },
    "lmstudio": {
        "label":        "LM Studio（本地）",
        "api_url":      "http://localhost:1234",
        "backend_type": "openai_completions",
        "models":       ["可在 LM Studio 中加载的任何支持 FIM 的模型"],
        "needs_key":    False,
        "key_note":     "LM Studio 默认不需要 API 密钥。",
    },
    "vllm": {
        "label":        "vLLM（本地/远程）",
        "api_url":      "http://localhost:8000",
        "backend_type": "openai_completions",
        "models":       ["Qwen2.5-Coder-7B-Instruct", "deepseek-coder-v2-lite-instruct"],
        "needs_key":    False,
        "key_note":     "仅当你的 vLLM 服务器使用 --api-key 启动时才需要添加密钥。",
    },
    "deepseek": {
        "label":        "DeepSeek",
        "api_url":      "https://api.deepseek.com/beta",
        "backend_type": "openai_completions",
        "models":       ["deepseek-chat"],
        "needs_key":    True,
        "key_note":     "在 platform.deepseek.com 获取你的密钥。",
    },
    "codestral": {
        "label":        "Mistral / Codestral",
        "api_url":      "https://codestral.mistral.ai",
        "backend_type": "codestral",
        "models":       ["codestral-latest"],
        "needs_key":    True,
        "key_note":     "在 console.mistral.ai 获取你的密钥。",
    },
    "openrouter": {
        "label":        "OpenRouter（聊天 FIM）",
        "api_url":      "https://openrouter.ai/api",
        "backend_type": "chat",
        "models":       ["deepseek/deepseek-coder", "qwen/qwen-2.5-coder-32b-instruct"],
        "needs_key":    True,
        "key_note":     "在 openrouter.ai/keys 获取你的密钥。",
    },
    "custom": {
        "label":        "Custom",
        "api_url":      "http://localhost:8080",
        "backend_type": "openai_completions",
        "models":       [],
        "needs_key":    False,
        "key_note":     "Enter your API key if required.",
    },
}

# ---------------------------------------------------------------------------
# FIM prompt templates  (used only when raw token injection is needed)
# These are NOT used for Ollama (/api/generate), which takes prompt+suffix.
# They are available for models that don't support a native suffix parameter.
# ---------------------------------------------------------------------------
# {prefix} and {suffix} are replaced at build time.
FIM_TEMPLATES = {
    "deepseek": "<｜fim▁begin｜>{prefix}<｜fim▁hole｜>{suffix}<｜fim▁end｜>",
    "codegemma": "<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>",
    "starcoder": "<fim_prefix>{prefix}<fim_suffix>{suffix}<fim_middle>",
    "qwen":      "<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>",
    "generic":   "{prefix}",   # fallback: just send the prefix, no suffix injection
}

# Map model name substrings (lower-case) → template key
MODEL_TEMPLATE_MAP = [
    ("deepseek",   "deepseek"),
    ("codegemma",  "codegemma"),
    ("starcoder",  "starcoder"),
    ("qwen",       "qwen"),
]

def get_fim_template(model_name: str) -> str:
    """Return the FIM template string for a given model name."""
    name_lower = model_name.lower()
    for substr, key in MODEL_TEMPLATE_MAP:
        if substr in name_lower:
            return FIM_TEMPLATES[key]
    return FIM_TEMPLATES["generic"]


# ---------------------------------------------------------------------------
# Stop tokens per model family (used to trim runaway completions)
# ---------------------------------------------------------------------------
STOP_TOKENS = {
    "deepseek":  ["<｜fim▁end｜>", "<|endoftext|>", "\n\n\n"],
    "codegemma": ["<|file_separator|>", "<|endoftext|>", "\n\n\n"],
    "starcoder": ["<|endoftext|>", "<fim_pad>", "\n\n\n"],
    "qwen":      ["<|endoftext|>", "<|fim_pad|>", "\n\n\n"],
    "generic":   ["\n\n\n", "<|endoftext|>"],
}

CONF_VERSION = "1.0.0"


def get_stop_tokens(model_name: str) -> list:
    """Return stop token list for a given model name."""
    name_lower = model_name.lower()
    for substr, key in MODEL_TEMPLATE_MAP:
        if substr in name_lower:
            return STOP_TOKENS[key]
    return STOP_TOKENS["generic"]
