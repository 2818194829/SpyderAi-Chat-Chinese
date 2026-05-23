# -*- coding: utf-8 -*-
"""Settings dialog for AI Chat plugin (C) 2026 by Maciej Piecko"""

from qtpy.QtWidgets import (
    QDialog, QTabWidget, QTabBar, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLineEdit, QLabel, QDialogButtonBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QRadioButton, QButtonGroup, QComboBox, QPlainTextEdit, QPushButton,
    QFrame, QSizePolicy, QGroupBox, QListWidget, QListWidgetItem, QScrollArea,
    QFileDialog, QStylePainter, QStyleOptionTab, QStyle,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from qtpy.QtCore import Qt, QThread, QTimer, Signal, QRect, QPoint
from qtpy.QtGui import QFont, QBrush, QColor, QPixmap

from .system_prompts import (
    load_prompts, new_prompt, update_prompt, delete_prompt, CUSTOM_ID,
)
from .commands import (load_commands, save_commands, DEFAULT_COMMANDS,
                       BUILTIN_COMMANDS, get_builtin_names)


# ---------------------------------------------------------------------------
# Provider registry — single source of truth for all provider metadata.
# Each entry defines connection fields and supported inference parameters.
# ---------------------------------------------------------------------------

# Master list of all possible inference parameters across all providers.
# Each entry: (param_id, display_label, type, range/options, tooltip)
PARAM_DEFS = {
    "temperature": (
        "温度", "float", (0.0, 2.0),
        "输出的随机性。0 = 确定性的，越高 = 越有创造力。"
    ),
    "max_tokens": (
        "最大 Token 数", "int", (1, 128000),
        "响应中的最大 Token 数。设为 0 使用提供商默认值。"
    ),
    "top_p": (
        "Top-p", "float", (0.0, 1.0),
        "核采样。仅考虑概率质量前 p% 的 token。"
    ),
    "top_k": (
        "Top-k", "int", (1, 200),
        "仅从最可能的 K 个 token 中采样。"
    ),
    "min_p": (
        "Min-p", "float", (0.0, 1.0),
        "相对于最高概率 token 的最小概率阈值。"
    ),
    "presence_penalty": (
        "存在惩罚", "float", (-2.0, 2.0),
        "惩罚所有已出现的 token（鼓励新主题）。"
    ),
    "frequency_penalty": (
        "频率惩罚", "float", (-2.0, 2.0),
        "按 token 出现频率成比例地惩罚（减少重复）。"
    ),
    "repetition_penalty": (
        "重复惩罚", "float", (0.0, 2.0),
        "重复 token 的乘法惩罚（1.0 = 无惩罚）。"
    ),
    "seed": (
        "随机种子", "int", (0, 2**31 - 1),
        "用于可重现输出的随机种子。0 = 随机。"
    ),
    "num_ctx": (
        "上下文窗口 (num_ctx)", "int", (512, 131072),
        "Ollama：模型使用的上下文 token 数量。默认值取决于模型。"
    ),
}

# Provider definitions
PROVIDERS = {
    "openai": {
        "label":         "OpenAI",
        "default_url":   "https://api.openai.com/v1",
        "url_editable":  False,
        "needs_api_key": True,
        "extra_fields":  [],
        "supported_params": [
            "temperature", "max_tokens", "top_p",
            "presence_penalty", "frequency_penalty", "seed",
        ],
        "param_warnings": {},
        "temperature_max": 2.0,
        "notes": "",
    },
    "groq": {
        "label":         "Groq",
        "default_url":   "https://api.groq.com/openai/v1",
        "url_editable":  False,
        "needs_api_key": True,
        "extra_fields":  [],
        "supported_params": [
            "temperature", "max_tokens", "top_p", "seed",
        ],
        "param_warnings": {
            "presence_penalty": "API 接受此参数，但目前对 Groq 无效。",
            "frequency_penalty": "API 接受此参数，但目前对 Groq 无效。",
        },
        "temperature_max": 2.0,
        "notes": "max_tokens 会自动作为 max_completion_tokens 发送。",
    },
    "mistral": {
        "label":         "Mistral AI",
        "default_url":   "https://api.mistral.ai/v1",
        "url_editable":  False,
        "needs_api_key": True,
        "extra_fields":  [],
        "supported_params": [
            "temperature", "max_tokens", "top_p",
            "presence_penalty", "seed",
        ],
        "param_warnings": {},
        "temperature_max": 1.0,
        "notes": "温度范围为 0–1。不建议使用高于 0.7 的值。",
    },
    "deepseek": {
        "label":         "DeepSeek",
        "default_url":   "https://api.deepseek.com",
        "url_editable":  False,
        "needs_api_key": True,
        "extra_fields":  [],
        "supported_params": [
            "temperature", "max_tokens", "top_p",
            "presence_penalty", "frequency_penalty", "seed",
        ],
        "param_warnings": {},
        "temperature_max": 2.0,
        "notes": (
            "⚠ 推理模型（deepseek-reasoner）会忽略 temperature、top_p "
            "和惩罚参数——它们被接受但无效果。"
        ),
    },
    "together": {
        "label":         "Together AI",
        "default_url":   "https://api.together.xyz/v1",
        "url_editable":  False,
        "needs_api_key": True,
        "extra_fields":  [],
        "supported_params": [
            "temperature", "max_tokens", "top_p",
            "top_k", "repetition_penalty", "seed",
        ],
        "param_warnings": {},
        "temperature_max": 2.0,
        "notes": "",
    },
    "fireworks": {
        "label":         "Fireworks AI",
        "default_url":   "https://api.fireworks.ai/inference/v1",
        "url_editable":  False,
        "needs_api_key": True,
        "extra_fields":  [],
        "supported_params": [
            "temperature", "max_tokens", "top_p", "top_k",
            "presence_penalty", "frequency_penalty", "seed",
        ],
        "param_warnings": {},
        "temperature_max": 2.0,
        "notes": (
            "如果 max_tokens 超过上下文窗口，"
            "Fireworks 会自动截断提示词而不是返回错误。"
        ),
    },
    "openrouter": {
        "label":         "OpenRouter",
        "default_url":   "https://openrouter.ai/api/v1",
        "url_editable":  False,
        "needs_api_key": True,
        "extra_fields":  [],
        "supported_params": [
            "temperature", "max_tokens", "top_p", "top_k", "min_p",
            "presence_penalty", "frequency_penalty", "repetition_penalty", "seed",
        ],
        "param_warnings": {},
        "temperature_max": 2.0,
        "notes": (
            "OpenRouter 路由到 300+ 模型。使用类似 "
            "openai/gpt-4o 或 meta-llama/llama-3.1-70b-instruct 的模型名称。"
            "每个模型会静默忽略不支持的参数。"
        ),
    },
    "ollama": {
        "label":         "Ollama (local)",
        "default_url":   "http://localhost:11434/v1",
        "url_editable":  True,
        "needs_api_key": False,
        "extra_fields":  [],
        "supported_params": [
            "temperature", "max_tokens", "top_p",
            "top_k", "seed", "num_ctx",
        ],
        "param_warnings": {},
        "temperature_max": 2.0,
        "notes": (
            "Ollama 的默认温度为 0.8（高于 OpenAI 的 1.0）。"
            "使用 num_ctx 将上下文窗口增加到模型默认值以上。"
        ),
    },
    "lmstudio": {
        "label":         "LM Studio (local)",
        "default_url":   "http://localhost:1234/v1",
        "url_editable":  True,
        "needs_api_key": True,
        "extra_fields":  [],
        "supported_params": [
            "temperature", "max_tokens", "top_p", "top_k",
            "presence_penalty", "frequency_penalty", "seed",
        ],
        "param_warnings": {},
        "temperature_max": 2.0,
        "notes": "API 密钥是可选的——仅在 LM Studio 启动时启用了身份验证时才需要。",
    },
    "vllm": {
        "label":         "vLLM (local/server)",
        "default_url":   "http://localhost:8000/v1",
        "url_editable":  True,
        "needs_api_key": True,
        "extra_fields":  [],
        "supported_params": [
            "temperature", "max_tokens", "top_p", "top_k", "min_p",
            "presence_penalty", "frequency_penalty", "repetition_penalty", "seed",
        ],
        "param_warnings": {},
        "temperature_max": 2.0,
        "notes": "API 密钥是可选的——仅在 vLLM 启动时使用了 --api-key 参数时才需要。",
    },
    "azure": {
        "label":         "Azure OpenAI",
        "default_url":   "",
        "url_editable":  True,
        "needs_api_key": True,
        "extra_fields":  ["azure_deployment", "azure_api_version"],
        "supported_params": [
            "temperature", "max_tokens", "top_p",
            "presence_penalty", "frequency_penalty", "seed",
        ],
        "param_warnings": {},
        "temperature_max": 2.0,
        "notes": (
            "基础 URL 格式：https://<资源名>.openai.azure.com/openai/deployments/<部署名>"
        ),
    },
    "custom": {
        "label":         "Custom (OpenAI-compatible)",
        "default_url":   "",
        "url_editable":  True,
        "needs_api_key": True,
        "extra_fields":  [],
        "supported_params": [
            "temperature", "max_tokens", "top_p", "top_k", "min_p",
            "presence_penalty", "frequency_penalty", "repetition_penalty", "seed",
        ],
        "param_warnings": {},
        "temperature_max": 2.0,
        "notes": (
            "任何兼容 OpenAI 的端点。不支持的参数通常会被服务器忽略。"
        ),
    },
}

# Ordered list for the dropdown — local first, then cloud, then custom
PROVIDER_ORDER = [
    "ollama", "lmstudio", "vllm",                                     # local
    "openai", "groq", "mistral", "deepseek", "together", "fireworks",  # cloud
    "openrouter", "azure",                                             # cloud (meta/other)
    "custom",                                                          # custom
]

# Groups shown in the dropdown (label, [provider ids])
PROVIDER_GROUPS = [
    ("── 本地 ──", ["ollama", "lmstudio", "vllm"]),
    ("── 云 API ──", ["openai", "groq", "mistral", "deepseek",
                         "together", "fireworks", "openrouter", "azure"]),
    ("── 自定义 ──", ["custom"]),
]


# Default font size configuration
EDITOR_DEFAULTS = {
    "fs_ui":      9,   # 界面 UI 字体
    "fs_base":    10,
    "fs_code":    10,
    "fs_heading": 14,
    "fs_list":    10,
    "fs_table":   10,
    "fs_think":    9,
}

HISTORY_DEFAULTS = {
    "autosave":              True,
    "save_on_new":           True,
    "proj_max_file_kb":      256,
    "proj_max_files":        500,
    "proj_extra_exclusions":  "",
    "proj_reset_on_new_chat": True,
    "show_git_bar":           False,
    "git_poll_interval":      10,
    # Compaction
    "compaction_enabled":          True,
    "compaction_strategy":         "cutoff",   # "cutoff" | "llm"
    "compaction_threshold_pct":    80,          # trigger at X % of limit
    "compaction_default_limit":    100_000,     # fallback token limit
    "compaction_model_limits":     [],          # [[provider, model, max_tokens], …]
}


def _read_compaction_table(table):
    """Read rows from the compaction QTableWidget into a list of [provider, model, tokens]."""
    rows = []
    for r in range(table.rowCount()):
        # Column 0 — provider: may be a QComboBox cell widget or a plain item
        pw = table.cellWidget(r, 0)
        if isinstance(pw, QComboBox):
            provider = (pw.currentData() or pw.currentText()).strip()
        else:
            provider = (table.item(r, 0) or QTableWidgetItem()).text().strip()
        # Column 1 — model: may be QComboBox (editable) or QLineEdit or plain item
        mw = table.cellWidget(r, 1)
        if isinstance(mw, QComboBox):
            model = mw.currentText().strip()
        elif isinstance(mw, QLineEdit):
            model = mw.text().strip()
        else:
            model = (table.item(r, 1) or QTableWidgetItem()).text().strip()
        # Column 2 — token limit: plain item
        try:
            limit = int((table.item(r, 2) or QTableWidgetItem()).text().strip())
        except ValueError:
            limit = 0
        if (provider or model) and limit > 0:
            rows.append([provider, model, limit])
    return rows

AGENTIC_DEFAULTS = {
    "enabled":           True,
    "allow_create_file": True,
    "allow_run_console": True,
    "allow_install":     False,   # off by default — higher risk
    "allow_patch":       True,
    "allow_git":         True,
    "allow_read":        True,
    "allow_ls":          True,
    "allow_grep":        True,
    "allow_delete":      False,   # off by default — irreversible
    "allow_delete_dir":  False,   # off by default — irreversible, recursive
    "allow_rename":      False,   # off by default — modifies paths
    "allow_rename_dir":  False,   # off by default — modifies paths
    "base_path":               "",      # empty = project root, falls back to ~
    "autonomous_mode":         "semi",  # "off" | "semi" | "full"
    "full_auto_confirm_modifying": True,  # full mode: still confirm file/patch/run/git
}


# ---------------------------------------------------------------------------
# FIM provider defaults (URL auto-filled when provider changes)
# ---------------------------------------------------------------------------
_FIM_PROVIDER_URLS = {
    "lmstudio":   "http://localhost:1234",
    "ollama":     "http://localhost:11434",
    "vllm":       "http://localhost:8000",
    "deepseek":   "https://api.deepseek.com",
    "codestral":  "https://codestral.mistral.ai",
    "openrouter": "https://openrouter.ai/api",
    "custom":     "",
}


class _ConnTester(QThread):
    """Background thread: verify provider connectivity via GET /models.

    Uses the /models endpoint (OpenAI-compat) which is available on every
    supported provider without triggering any generation or billing.
    Azure optionally appends ?api-version=<ver> to the same path.
    """

    sig_ok    = Signal(str)   # success message
    sig_error = Signal(str)   # error/failure message

    def __init__(self, url, key, api_version="", parent=None):
        super().__init__(parent)
        self._url     = url.rstrip("/")
        self._key     = key
        self._api_ver = api_version

    def run(self):
        import urllib.request, urllib.error, json

        # Use an OpenAI-SDK-style User-Agent so Cloudflare and other WAFs
        # do not block the request as a generic Python bot (HTTP 403 / 1010).
        headers = {
            "Content-Type": "application/json",
            "User-Agent":   "OpenAI/Python 1.0.0",
            "Accept":       "application/json",
        }
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"

        path = "/models"
        if self._api_ver:
            path += f"?api-version={self._api_ver}"

        try:
            req = urllib.request.Request(
                f"{self._url}{path}", headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            if data.get("error"):
                self.sig_error.emit(str(data["error"]))
                return

            # Count available models when the list is present
            count = None
            if isinstance(data.get("data"), list):
                count = len(data["data"])
            elif isinstance(data.get("models"), list):
                count = len(data["models"])

            msg = f"已连接 — {count} 个模型可用" if count is not None \
                  else "已连接"
            self.sig_ok.emit(msg)

        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode()[:200]
            except Exception:
                body = e.reason
            self.sig_error.emit(f"HTTP {e.code}: {body}")
        except Exception as e:
            self.sig_error.emit(str(e))


class _FimLoader(QThread):
    """Background thread: fetch model list then probe available backends."""

    sig_status   = Signal(str)
    sig_models   = Signal(list)   # list[str] — model names
    sig_backends = Signal(list)   # list[tuple[str,str]] — (key, label) pairs
    sig_error    = Signal(str)

    _ALL_BACKENDS = [
        ("ollama_generate",    "Ollama /api/generate（原生 FIM）"),
        ("openai_completions", "OpenAI 兼容 /v1/completions（传统 FIM）"),
        ("codestral",          "Codestral /v1/fim/completions（Mistral）"),
        ("chat",               "聊天补全（提示注入，后备方案）"),
    ]

    def __init__(self, url, key, provider_id, parent=None):
        super().__init__(parent)
        self._url = url.rstrip("/")
        self._key = key
        self._pid = provider_id

    def _headers(self):
        h = {
            "Content-Type": "application/json",
            "User-Agent":   "OpenAI/Python 1.0.0",
            "Accept":       "application/json",
        }
        if self._key:
            h["Authorization"] = f"Bearer {self._key}"
        return h

    def _get(self, path, timeout=10):
        import urllib.request, json
        req = urllib.request.Request(
            f"{self._url}{path}", headers=self._headers())
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    def _post(self, path, body, timeout=8):
        import urllib.request, json
        data = json.dumps(body).encode()
        req  = urllib.request.Request(
            f"{self._url}{path}", data=data,
            headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    def run(self):
        self.sig_status.emit("获取模型列表中…")
        models = self._fetch_models()
        if models is None:
            return
        if not models:
            self.sig_error.emit("此端点未找到模型")
            return
        self.sig_models.emit(models)

        self.sig_status.emit(
            f"找到 {len(models)} 个模型，正在测试后端…")
        backends = self._probe_backends(models[0])
        if not backends:
            backends = list(self._ALL_BACKENDS)
        self.sig_backends.emit(backends)

    def _fetch_models(self):
        try:
            if self._pid == "ollama":
                data = self._get("/api/tags")
                return [m["name"] for m in data.get("models", [])]
            else:
                data = self._get("/v1/models")
                return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            self.sig_error.emit(f"无法连接：{e}")
            return None

    @staticmethod
    def _validate(data, backend_key):
        """Raise ValueError if the response body signals an unsupported endpoint.

        Some providers (e.g. LM Studio) return HTTP 200 for unknown endpoints
        but include an error message in the JSON body instead of the expected
        fields.  We must check the body — not just the status code.
        """
        # Top-level "error" key means the endpoint is not supported
        if data.get("error"):
            raise ValueError(f"endpoint error: {data['error']}")

        # Each backend has a required field that a real response must contain
        required = {
            "ollama_generate":    lambda d: "response" in d or "done" in d,
            "openai_completions": lambda d: "choices" in d,
            "codestral":          lambda d: "choices" in d,
            "chat":               lambda d: "choices" in d,
        }
        if not required[backend_key](data):
            raise ValueError(
                f"missing expected field in response: {list(data.keys())}")

    def _probe_backends(self, model):
        working = []
        probes = [
            ("ollama_generate",    "/api/generate",
             {"model": model, "prompt": "x", "suffix": "",
              "stream": False, "num_predict": 1}),
            ("openai_completions", "/v1/completions",
             {"model": model, "prompt": "x",
              "max_tokens": 1, "stream": False}),
            ("codestral",          "/v1/fim/completions",
             {"model": model, "prompt": "x", "suffix": "",
              "max_tokens": 1}),
            ("chat",               "/v1/chat/completions",
             {"model": model,
              "messages": [{"role": "user", "content": "x"}],
              "max_tokens": 1, "stream": False}),
        ]
        for key, path, body in probes:
            label = next(lbl for k, lbl in self._ALL_BACKENDS if k == key)
            try:
                data = self._post(path, body)
                self._validate(data, key)
                working.append((key, label))
            except Exception:
                pass
        return working


class _HTabBar(QTabBar):
    """
    Tab bar that renders text horizontally when placed on the West side.
    Qt normally rotates West-tab text 90°; we bypass CE_TabBarTabLabel and
    draw text directly so there is no rotation complication.
    Tab height = font height + 2 * _V_PAD (12 px top + 12 px bottom).
    """

    _V_PAD   = 12  # pixels above and below the text
    _L_PAD   = 15  # pixels from the left edge to the text

    def tabSizeHint(self, index):
        hint = super().tabSizeHint(index)
        # For West tabs Qt returns QSize(bar_thickness, along_bar_size).
        # We keep bar_thickness and shrink along_bar_size to font + padding.
        fm_h = self.fontMetrics().height()
        compact_h = fm_h + 2 * self._V_PAD
        return hint.__class__(hint.width(), compact_h)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        opt = QStyleOptionTab()
        for i in range(self.count()):
            self.initStyleOption(opt, i)
            # Draw tab background / selection highlight (handles state colours).
            painter.drawControl(QStyle.CE_TabBarTabShape, opt)
            # Draw text directly — left-aligned with _L_PAD, vertically centred.
            rect = opt.rect.adjusted(self._L_PAD, 0, 0, 0)
            is_selected = bool(opt.state & QStyle.State_Selected)
            color = (opt.palette.highlightedText().color() if is_selected
                     else opt.palette.text().color())
            painter.setPen(color)
            painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft | Qt.TextShowMnemonic,
                             self.tabText(i))


def _is_dialog_dark():
    """Return True when Spyder (or Qt) is running in dark mode."""
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


class SettingsDialog(QDialog):
    """
    Tabbed settings dialog:
      1. Connection  — provider dropdown + dynamic URL/key/extra fields
      2. Editor      — font sizes for rendered markdown elements
      3. History     — auto-save toggles
      4. System Prompts
    """

    def __init__(self, parent, provider_type, api_url, api_key,
                 editor_cfg, history_cfg,
                 azure_deployment="", azure_api_version="2024-02-01",
                 commands=None, fim_cfg=None,
                 default_system_prompt_id=None,
                 agentic_cfg=None,
                 model_list=None,
                 initial_tab=0):
        super().__init__(parent)
        # Prevent a transient ~180×130 "Spyder"-titled flash on Windows.
        # Without this guard, Qt materialises the dialog's native HWND at
        # its default minimum size (~180×130) with the application-wide
        # title ("Spyder") the moment any child widget triggers an HWND
        # lookup during construction — visible for a frame before exec_()
        # finishes the layout pass and paints the real dialog.
        #
        # Sequence matters:
        #   1. Hide via WA_DontShowOnScreen so the HWND cannot paint.
        #   2. Set title + final size so when we re-enable painting the
        #      HWND already carries correct metadata.
        #   3. All child widgets are built while the dialog is non-paintable.
        #   4. At end of __init__, re-enable painting — exec_() shows the
        #      fully-formed dialog in one frame.
        # Theme flag — used throughout __init__ to pick light-vs-dark colours.
        _dark = _is_dialog_dark()

        self.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.setWindowTitle("AI 聊天 – 设置")
        self.resize(820, 770)
        self.setMinimumWidth(820)
        self.setMinimumHeight(770)

        tabs = QTabWidget(self)
        tabs.setTabBar(_HTabBar(tabs))
        tabs.setTabPosition(QTabWidget.West)
        tabs.setStyleSheet(
            "QTabBar::tab {"
            "    padding: 6px 14px;"
            "    min-width: 110px;"
            "    min-height: 22px;"
            "}"
            "QTabBar::tab:selected { font-weight: bold; }"
        )

        # ── Tab 1: Connection ────────────────────────────────────────
        conn_w = QWidget(self)
        conn_lay = QVBoxLayout(conn_w)
        conn_lay.setContentsMargins(12, 12, 12, 12)
        conn_lay.setSpacing(6)

        # Tab title
        conn_title = QLabel("连接到 LLM 提供商")
        _conn_title_fg = "#e0e0e0" if _dark else "#111111"
        conn_title.setStyleSheet(f"font-size: 13pt; font-weight: bold; color: {_conn_title_fg};")
        conn_lay.addWidget(conn_title)

        conn_title_sep = QFrame(conn_w)
        conn_title_sep.setFrameShape(QFrame.HLine)
        conn_title_sep.setStyleSheet("color: #444; margin: 2px 0 6px 0;")
        conn_lay.addWidget(conn_title_sep)

        # Info notices
        info_lbl1 = QLabel("仅支持兼容 OpenAI 的 API 提供商。")
        info_lbl1.setStyleSheet("color: #888; font-size: 9pt;")
        conn_lay.addWidget(info_lbl1)

        info_lbl2 = QLabel("一次只能激活一个提供商。")
        info_lbl2.setStyleSheet("color: #888; font-size: 9pt;")
        conn_lay.addWidget(info_lbl2)

        # Separator
        conn_sep = QFrame(conn_w)
        conn_sep.setFrameShape(QFrame.HLine)
        conn_sep.setStyleSheet("color: #444; margin: 4px 0;")
        conn_lay.addWidget(conn_sep)

        # Provider row with "Configure active provider:" label above
        active_lbl = QLabel("配置活跃提供商：")
        active_lbl.setStyleSheet("color: #ccc; font-size: 9pt;")
        conn_lay.addWidget(active_lbl)

        # Provider dropdown
        prov_row = QHBoxLayout()
        prov_lbl = QLabel("提供商：")
        prov_lbl.setFixedWidth(127)
        self._prov_combo = QComboBox()
        self._prov_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        for group_label, pids in PROVIDER_GROUPS:
            # Group header — non-selectable separator item
            sep_idx = self._prov_combo.count()
            self._prov_combo.addItem(group_label, userData=None)
            item = self._prov_combo.model().item(sep_idx)
            item.setEnabled(False)
            # Style: bold, slightly muted colour
            f = QFont(); f.setBold(True)
            item.setFont(f)
            item.setForeground(QBrush(QColor("#888888")))
            # Actual providers in this group
            for pid in pids:
                self._prov_combo.addItem(PROVIDERS[pid]["label"], userData=pid)
        prov_row.addWidget(prov_lbl)
        prov_row.addWidget(self._prov_combo, 1)
        conn_lay.addLayout(prov_row)

        # Dynamic fields form — built ONCE, rows shown/hidden per provider.
        # Never use takeRow/addRow after init — Wayland loses keyboard grab
        # when widgets are re-parented dynamically.
        self._conn_form = QFormLayout()
        self._conn_form.setSpacing(6)
        conn_lay.addLayout(self._conn_form)

        # Notes label (provider-specific)
        self._prov_notes = QLabel()
        self._prov_notes.setWordWrap(True)
        self._prov_notes.setTextFormat(Qt.RichText)
        self._prov_notes.setStyleSheet(
            "color: #aaa; font-size: 9pt; padding: 6px 4px 2px 4px;")
        conn_lay.addWidget(self._prov_notes)
        conn_lay.addStretch()

        tabs.addTab(conn_w, "🔌 连接")

        # ── persistent field widgets (created once, shown/hidden) ────
        # URL
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://…")
        # API key
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.Password)
        self._key_edit.setPlaceholderText("sk-…（本地模型可留空）")
        # "No key needed" label shown instead of key field for local providers
        self._no_key_lbl = QLabel("本地模型无需 API 密钥。")
        self._no_key_lbl.setStyleSheet("color: gray; font-size: 9pt;")
        # Azure extras
        self._azure_dep_edit = QLineEdit(azure_deployment)
        self._azure_dep_edit.setPlaceholderText("my-gpt4o-deployment")
        self._azure_ver_combo = QComboBox()
        for ver in ["2024-02-01", "2024-05-01-preview", "2024-08-01-preview",
                    "2024-10-01-preview", "2025-01-01-preview"]:
            self._azure_ver_combo.addItem(ver)
        idx = self._azure_ver_combo.findText(azure_api_version)
        if idx >= 0:
            self._azure_ver_combo.setCurrentIndex(idx)

        # Set initial values
        self._url_edit.setText(api_url)
        self._key_edit.setText(api_key)


        # Add ALL rows to the form permanently — visibility toggled in
        # _build_conn_form(), never removed/re-added
        self._url_lbl = QLabel("基础 URL：")
        self._conn_form.addRow(self._url_lbl, self._url_edit)

        self._key_lbl = QLabel("API 密钥：")
        self._conn_form.addRow(self._key_lbl, self._key_edit)

        self._no_key_lbl_row_lbl = QLabel("API 密钥：")
        self._conn_form.addRow(self._no_key_lbl_row_lbl, self._no_key_lbl)

        self._azure_dep_lbl = QLabel("部署名称：")
        self._conn_form.addRow(self._azure_dep_lbl, self._azure_dep_edit)

        self._azure_ver_lbl = QLabel("API 版本：")
        self._conn_form.addRow(self._azure_ver_lbl, self._azure_ver_combo)

        # Test connection row — always visible
        _test_row = QHBoxLayout()
        self._conn_test_btn = QPushButton("测试连接")
        self._conn_test_btn.setFixedWidth(138)
        self._conn_test_lbl = QLabel("")
        self._conn_test_lbl.setWordWrap(True)
        _test_row.addWidget(self._conn_test_btn)
        _test_row.addWidget(self._conn_test_lbl, 1)
        self._conn_form.addRow("", _test_row)

        # Spinner state for test button
        self._conn_spinner_frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._conn_spinner_idx    = 0
        self._conn_status_msg     = ""
        self._conn_spinner_timer  = QTimer(self)
        self._conn_spinner_timer.setInterval(80)
        self._conn_spinner_timer.timeout.connect(self._conn_spinner_tick)
        self._conn_tester         = None

        self._conn_test_btn.clicked.connect(self._on_conn_test)

        # Wire provider change
        self._prov_combo.currentIndexChanged.connect(self._on_provider_changed)

        # Select the saved provider (triggers _on_provider_changed → updates visibility)
        saved_idx = self._prov_combo.findData(provider_type)
        if saved_idx < 0:
            saved_idx = self._prov_combo.findData("custom")
        self._prov_combo.setCurrentIndex(saved_idx)
        self._build_conn_form()

        # ── Tab 2: Dialogs (font sizes) ──────────────────────────────
        editor_w = QWidget(self)
        editor_outer = QVBoxLayout(editor_w)
        editor_outer.setContentsMargins(12, 12, 12, 12)
        editor_outer.setSpacing(6)

        dialogs_info = QLabel("更改对话框中各文本类型的字体大小。")
        dialogs_info.setStyleSheet("color: #888; font-size: 9pt;")
        editor_outer.addWidget(dialogs_info)

        ef = QFormLayout()
        ef.setSpacing(8)
        editor_outer.addLayout(ef)

        def _spin(key, max_val=24):
            s = QSpinBox()
            s.setRange(6, max_val)
            s.setValue(editor_cfg.get(key, EDITOR_DEFAULTS[key]))
            s.setSuffix(" pt")
            s.setFixedWidth(83)
            return s

        self.fs_ui      = _spin("fs_ui", max_val=32)
        self.fs_base    = _spin("fs_base")
        self.fs_code    = _spin("fs_code")
        self.fs_heading = _spin("fs_heading", max_val=48)
        self.fs_list    = _spin("fs_list")
        self.fs_table   = _spin("fs_table")
        self.fs_think   = _spin("fs_think")

        # ── Separator: global UI font ─────────────────────────────────
        ui_sep = QFrame(editor_w)
        ui_sep.setFrameShape(QFrame.HLine)
        ui_sep.setStyleSheet("color: #444; margin: 4px 0;")
        ef.addRow(ui_sep)

        ui_note = QLabel("以下设置影响整个插件界面（按钮、标签、输入框等）。")
        ui_note.setStyleSheet("color: #888; font-size: 9pt;")
        ef.addRow(ui_note)

        ef.addRow("界面 UI 字体：", self.fs_ui)

        ef.addRow("基础文本：", self.fs_base)
        ef.addRow("代码块：", self.fs_code)
        ef.addRow("标题（H1 基准）：", self.fs_heading)
        ef.addRow("列表：", self.fs_list)
        ef.addRow("表格：", self.fs_table)
        ef.addRow("思考框：", self.fs_think)

        note = QLabel("更改在保存后应用于新消息。")
        note.setStyleSheet("color: gray; font-size: 9pt;")
        ef.addRow(note)
        editor_outer.addStretch()
        tabs.addTab(editor_w, "🖊 对话框")

        # ── Tab 3: History ───────────────────────────────────────────
        hist_w = QWidget(self)
        hl = QVBoxLayout(hist_w)
        hl.setContentsMargins(12, 12, 12, 12)
        hl.setSpacing(8)

        self.cb_autosave = QCheckBox("自动保存聊天记录到历史")
        self.cb_autosave.setChecked(
            history_cfg.get("autosave", HISTORY_DEFAULTS["autosave"]))

        self.cb_save_on_new = QCheckBox(
            "开始新聊天时保存未发送的聊天")
        self.cb_save_on_new.setChecked(
            history_cfg.get("save_on_new", HISTORY_DEFAULTS["save_on_new"]))

        def _sync_hist():
            enabled = not self.cb_autosave.isChecked()
            self.cb_save_on_new.setEnabled(enabled)
            if not enabled:
                self.cb_save_on_new.setChecked(True)
        self.cb_autosave.toggled.connect(_sync_hist)
        _sync_hist()

        info = QLabel(
            "<b>工作原理：</b><br>"
            "当<i>自动保存</i>开启时，每一轮完成的对话（你的消息和 AI 回复）"
            "会自动写入磁盘——你永远不会丢失对话。<br><br>"
            "当<i>自动保存</i>关闭时，除非你手动从历史中加载聊天，否则不会保存任何内容。"
            "在这种情况下，<i>开始新聊天时保存未发送的聊天</i>会在你点击新聊天时进行一次性保存，"
            "这样当前未保存的对话就不会丢失。"
        )
        info.setWordWrap(True)
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet(
            "color: gray; font-size: 9pt; padding: 8px; "
            "background: rgba(128,128,128,0.08); border-radius: 4px;")

        hl.addWidget(self.cb_autosave)
        hl.addWidget(self.cb_save_on_new)
        hl.addSpacing(4)
        hl.addWidget(info)
        hl.addStretch()
        tabs.addTab(hist_w, "🗂 历史")

        # ── Tab 4: Git bar ────────────────────────────────────────────
        git_w   = QWidget(self)
        git_lay = QVBoxLayout(git_w)
        git_lay.setContentsMargins(12, 12, 12, 12)
        git_lay.setSpacing(10)

        grp_git = QGroupBox("⎇  Git 状态栏")
        grp_git.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 9pt; "
            "border: 1px solid #555; border-radius: 4px; margin-top: 6px; padding-top: 4px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        grp_git_lay = QVBoxLayout(grp_git)
        grp_git_lay.setContentsMargins(10, 10, 10, 10)
        grp_git_lay.setSpacing(7)

        self.chk_show_git_bar = QCheckBox(
            "显示 Git 状态栏（分支、未提交更改、快速操作按钮）")
        self.chk_show_git_bar.setChecked(
            history_cfg.get("show_git_bar", HISTORY_DEFAULTS["show_git_bar"]))

        self._git_check_lbl = QLabel()
        self._git_check_lbl.setStyleSheet("font-size: 8pt;")
        self._git_check_lbl.setVisible(False)

        git_chk_row = QHBoxLayout()
        git_chk_row.setContentsMargins(0, 0, 0, 0)
        git_chk_row.setSpacing(8)
        git_chk_row.addWidget(self.chk_show_git_bar)
        git_chk_row.addWidget(self._git_check_lbl)
        git_chk_row.addStretch()
        grp_git_lay.addLayout(git_chk_row)

        def _on_git_bar_toggled(state):
            import shutil
            if not self.chk_show_git_bar.isChecked():
                self._git_check_lbl.setVisible(False)
                return
            if shutil.which("git"):
                self._git_check_lbl.setStyleSheet("font-size: 8pt; color: #4ec94e;")
                self._git_check_lbl.setText("✓ 在 PATH 中找到 git")
            else:
                self._git_check_lbl.setStyleSheet("font-size: 8pt; color: #e05050;")
                self._git_check_lbl.setText("⚠ 在 PATH 中未找到 git — 状态栏将无法工作")
                self.chk_show_git_bar.setChecked(False)
            self._git_check_lbl.setVisible(True)

        self.chk_show_git_bar.stateChanged.connect(_on_git_bar_toggled)
        # Run check immediately if already enabled (loaded from saved state)
        if self.chk_show_git_bar.isChecked():
            _on_git_bar_toggled(None)

        poll_row = QHBoxLayout()
        poll_row.setContentsMargins(0, 0, 0, 0)
        poll_lbl = QLabel("刷新间隔（秒）：")
        poll_lbl.setStyleSheet("font-size: 9pt;")
        self.sp_git_poll = QSpinBox()
        self.sp_git_poll.setRange(5, 300)
        self.sp_git_poll.setSuffix(" s")
        self.sp_git_poll.setValue(
            history_cfg.get("git_poll_interval", HISTORY_DEFAULTS["git_poll_interval"]))
        self.sp_git_poll.setFixedWidth(80)
        self.sp_git_poll.setToolTip(
            "Git 状态栏轮询工作区更改的频率。\n"
            "分支切换和暂存通过文件监视器即时检测；\n"
            "此定时器捕获不涉及 .git/HEAD 或 .git/index 的普通文件编辑。")
        poll_row.addWidget(poll_lbl)
        poll_row.addWidget(self.sp_git_poll)
        poll_row.addStretch()
        grp_git_lay.addLayout(poll_row)

        git_bar_info = QLabel(
            "当打开包含 git 仓库的 Spyder 项目时，在上下文标签栏下方显示紧凑的状态栏。"
            "显示当前分支名称（<b>⎇ 分支名</b>）、未提交的差异统计，"
            "以及三个向 LLM 发送预填提示的快速操作按钮：<br>"
            "• <b>提交</b> — 收集 <i>git status</i> 和 <i>git diff</i>，"
            "让 LLM 建议提交信息并生成 <code>run:git commit</code> 代码围栏。<br>"
            "• <b>PR 描述</b> — 将当前分支与 main/master 比较，"
            "让 LLM 编写拉取请求描述。<br>"
            "• <b>更改</b> — 总结所有未提交的更改。<br>"
            "该状态栏还会将当前分支名称和差异统计注入到随每条消息发送的项目上下文头部中。"
        )
        git_bar_info.setWordWrap(True)
        git_bar_info.setTextFormat(Qt.RichText)
        git_bar_info.setStyleSheet("color: gray; font-size: 8pt;")
        grp_git_lay.addWidget(git_bar_info)

        git_lay.addWidget(grp_git)
        git_lay.addStretch()
        tabs.addTab(git_w, "⎇ Git 状态栏")

        # ── Tab 5: Project Context ────────────────────────────────────
        proj_w      = QWidget(self)
        proj_scroll = QScrollArea(self)
        proj_scroll.setWidgetResizable(True)
        proj_scroll.setFrameShape(QFrame.NoFrame)
        proj_scroll.setWidget(proj_w)
        pl = QVBoxLayout(proj_w)
        pl.setContentsMargins(12, 12, 12, 12)
        pl.setSpacing(10)

        # ── Group 1: LLM Project Context ─────────────────────────────
        grp_proj = QGroupBox("📁  LLM 项目上下文")
        grp_proj.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 9pt; "
            "border: 1px solid #555; border-radius: 4px; margin-top: 6px; padding-top: 4px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        grp_proj_lay = QVBoxLayout(grp_proj)
        grp_proj_lay.setContentsMargins(10, 10, 10, 10)
        grp_proj_lay.setSpacing(7)

        proj_top_info = QLabel(
            "让 AI 查看你的整个 Spyder 项目，无需逐个附加文件。"
            "使用聊天栏中的 <b>📁 项目 ○ / ●</b> 切换按钮来启用或禁用它。"
            "启用后，文件夹选择对话框让你选择要包含的顶级文件夹。"
        )
        proj_top_info.setWordWrap(True)
        proj_top_info.setTextFormat(Qt.RichText)
        proj_top_info.setStyleSheet("font-size: 9pt;")
        grp_proj_lay.addWidget(proj_top_info)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("最大文件大小 (KB)："))
        self.sp_proj_max_kb = QSpinBox()
        self.sp_proj_max_kb.setRange(16, 4096)
        self.sp_proj_max_kb.setValue(
            history_cfg.get("proj_max_file_kb", HISTORY_DEFAULTS["proj_max_file_kb"]))
        self.sp_proj_max_kb.setFixedWidth(80)
        size_row.addWidget(self.sp_proj_max_kb)
        size_row.addSpacing(16)
        size_row.addWidget(QLabel("最大文件数："))
        self.sp_proj_max_files = QSpinBox()
        self.sp_proj_max_files.setRange(10, 5000)
        self.sp_proj_max_files.setValue(
            history_cfg.get("proj_max_files", HISTORY_DEFAULTS["proj_max_files"]))
        self.sp_proj_max_files.setFixedWidth(80)
        size_row.addWidget(self.sp_proj_max_files)
        size_row.addStretch()
        grp_proj_lay.addLayout(size_row)

        grp_proj_lay.addWidget(QLabel("额外排除的 glob 模式（每行一个）："))
        self.te_proj_exclusions = QPlainTextEdit()
        self.te_proj_exclusions.setPlaceholderText("例如：*.log\ndata/\ntmp/")
        self.te_proj_exclusions.setMaximumHeight(72)
        self.te_proj_exclusions.setPlainText(
            history_cfg.get("proj_extra_exclusions",
                            HISTORY_DEFAULTS["proj_extra_exclusions"]))
        grp_proj_lay.addWidget(self.te_proj_exclusions)

        self.chk_proj_reset_on_new = QCheckBox(
            "开始新聊天时始终禁用项目上下文")
        self.chk_proj_reset_on_new.setChecked(
            history_cfg.get("proj_reset_on_new_chat",
                            HISTORY_DEFAULTS["proj_reset_on_new_chat"]))
        grp_proj_lay.addWidget(self.chk_proj_reset_on_new)

        proj_info = QLabel(
            "• <b>首条消息</b> — 所有收集的文件完整嵌入并与你的消息一起发送给 LLM。<br>"
            "• <b>后续消息</b> — 仅重新附加自上次发送以来更改的文件（增量）。未更改的文件不会重新发送。<br>"
            "• <b>未保存/打开的文件</b> — 新的未保存文件和带有未保存编辑的打开文件始终使用实时编辑器缓冲区内容。<br>"
            "• <b>内置排除项</b> — .git、__pycache__、*.pyc、.venv、"
            "node_modules、dist、build、二进制文件以及项目的 .gitignore 始终被排除。"
            "<i>额外排除模式</i>字段在此基础上添加额外的排除规则。"
        )
        proj_info.setWordWrap(True)
        proj_info.setTextFormat(Qt.RichText)
        proj_info.setStyleSheet("color: gray; font-size: 8pt;")
        grp_proj_lay.addWidget(proj_info)

        proj_warn = QLabel(
            "⚠  <b>警告：</b>项目上下文可能导致非常高的 Token 消耗——"
            "整个项目随每条消息一起发送。"
            "如果您的模型支持，请优先使用<b>代理自主模式</b>（read / ls / grep 代码围栏）；"
            "它们只获取 LLM 实际需要的内容。"
        )
        proj_warn.setWordWrap(True)
        proj_warn.setTextFormat(Qt.RichText)
        _pw_fg = "#e8a050" if _dark else "#7a4500"
        _pw_bg = "#1e1200" if _dark else "#fff3e0"
        _pw_bd = "#7a4a00" if _dark else "#c89050"
        proj_warn.setStyleSheet(
            f"color: {_pw_fg}; font-size: 8pt; "
            f"background: {_pw_bg}; border: 1px solid {_pw_bd}; "
            "border-radius: 3px; padding: 5px 7px;")
        grp_proj_lay.addWidget(proj_warn)

        pl.addWidget(grp_proj)

        # ── Group 2: Context History Compaction ───────────────────────
        grp_compact = QGroupBox("⚡  上下文历史压缩")
        grp_compact.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 9pt; "
            "border: 1px solid #555; border-radius: 4px; margin-top: 6px; padding-top: 4px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        grp_compact_lay = QVBoxLayout(grp_compact)
        grp_compact_lay.setContentsMargins(10, 10, 10, 10)
        grp_compact_lay.setSpacing(7)

        self.chk_compaction_enabled = QCheckBox("启用上下文历史压缩")
        self.chk_compaction_enabled.setChecked(
            history_cfg.get("compaction_enabled", HISTORY_DEFAULTS["compaction_enabled"]))
        grp_compact_lay.addWidget(self.chk_compaction_enabled)

        # Strategy row
        strat_lbl = QLabel("压缩策略：")
        strat_lbl.setStyleSheet("font-size: 9pt;")
        grp_compact_lay.addWidget(strat_lbl)

        self.rb_co_cutoff = QRadioButton(
            "截断 — 超过限制时静默丢弃最早的消息")
        self.rb_co_llm    = QRadioButton(
            "LLM 总结 — 让 LLM 总结历史；保存一个压缩块")
        self.co_strategy_group = QButtonGroup(self)
        self.co_strategy_group.addButton(self.rb_co_cutoff)
        self.co_strategy_group.addButton(self.rb_co_llm)
        _strat = history_cfg.get("compaction_strategy", HISTORY_DEFAULTS["compaction_strategy"])
        self.rb_co_cutoff.setChecked(_strat == "cutoff")
        self.rb_co_llm.setChecked(_strat == "llm")

        strat_indent = QVBoxLayout()
        strat_indent.setContentsMargins(16, 0, 0, 0)
        strat_indent.setSpacing(4)
        strat_indent.addWidget(self.rb_co_cutoff)
        strat_indent.addWidget(self.rb_co_llm)
        grp_compact_lay.addLayout(strat_indent)

        # Warning shown when llm strategy selected but autonomous_mode != full
        self.lbl_llm_strategy_warn = QLabel(
            "⚠  LLM 总结策略需要完全自主模式"
            "（在代理设置标签页中配置）")
        self.lbl_llm_strategy_warn.setWordWrap(True)
        _sw_fg = "#ffb347" if _dark else "#7a5000"
        _sw_bg = "#2a1a00" if _dark else "#fff8e0"
        _sw_bd = "#886622" if _dark else "#c8a030"
        self.lbl_llm_strategy_warn.setStyleSheet(
            f"color: {_sw_fg}; background: {_sw_bg}; border: 1px solid {_sw_bd}; "
            "border-radius: 3px; padding: 5px; font-size: 8pt;")
        _current_ag_mode = (agentic_cfg or {}).get("autonomous_mode", "semi")
        self.lbl_llm_strategy_warn.setVisible(
            history_cfg.get("compaction_enabled", False)
            and _strat == "llm"
            and _current_ag_mode != "full")
        grp_compact_lay.addWidget(self.lbl_llm_strategy_warn)

        # Threshold row
        thresh_row = QHBoxLayout()
        thresh_row.setContentsMargins(0, 0, 0, 0)
        thresh_lbl = QLabel("当估计 Token 数超过时触发：")
        thresh_lbl.setStyleSheet("font-size: 9pt;")
        self.sp_compaction_threshold = QSpinBox()
        self.sp_compaction_threshold.setRange(10, 99)
        self.sp_compaction_threshold.setSuffix(" %")
        self.sp_compaction_threshold.setValue(
            history_cfg.get("compaction_threshold_pct",
                            HISTORY_DEFAULTS["compaction_threshold_pct"]))
        self.sp_compaction_threshold.setFixedWidth(70)
        self.sp_compaction_threshold.setToolTip(
            "当历史窗口的估计 Token 数量超过当前模型配置的 Token 限制的\n"
            "此百分比时，触发压缩。")
        thresh_row.addWidget(thresh_lbl)
        thresh_row.addWidget(self.sp_compaction_threshold)
        thresh_row.addStretch()
        grp_compact_lay.addLayout(thresh_row)

        # Per-model limits table
        table_lbl = QLabel("每个提供商/模型的 Token 限制：")
        table_lbl.setStyleSheet("font-size: 9pt;")
        grp_compact_lay.addWidget(table_lbl)

        self.compaction_table = QTableWidget(0, 3)
        self.compaction_table.setHorizontalHeaderLabels(["提供商", "模型", "最大 Token 数"])
        self.compaction_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.compaction_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.compaction_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.compaction_table.setColumnWidth(2, 100)
        self.compaction_table.setMaximumHeight(130)
        self.compaction_table.setStyleSheet(
            "QTableWidget { font-size: 9pt; } "
            "QHeaderView::section { font-size: 9pt; padding: 2px; }")

        # ── Cell-widget helpers ───────────────────────────────────────
        _prov_ids = list(PROVIDERS.keys())
        _avail_models = list(model_list) if model_list else []

        def _make_prov_combo(initial_id=""):
            cb = QComboBox()
            cb.setStyleSheet("font-size: 9pt;")
            for _pid in _prov_ids:
                cb.addItem(PROVIDERS[_pid]["label"], userData=_pid)
            cb.addItem("其他/自定义", userData="")
            idx = next((i for i in range(cb.count())
                        if cb.itemData(i) == initial_id), -1)
            if idx >= 0:
                cb.setCurrentIndex(idx)
            else:
                # saved value may be a label string or non-standard id
                idx2 = cb.findText(initial_id, Qt.MatchFixedString | Qt.MatchCaseSensitive)
                cb.setCurrentIndex(idx2 if idx2 >= 0 else cb.count() - 1)
            return cb

        def _make_model_widget(prov_id, initial_model=""):
            """QComboBox (editable) when models available for this provider, else QLineEdit."""
            if prov_id == provider_type and _avail_models:
                cb = QComboBox()
                cb.setEditable(True)
                cb.setStyleSheet("font-size: 9pt;")
                cb.addItems(_avail_models)
                idx = cb.findText(initial_model)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
                else:
                    cb.setEditText(initial_model)
                return cb
            le = QLineEdit(initial_model)
            le.setStyleSheet("font-size: 9pt;")
            le.setPlaceholderText("model name…")
            return le

        def _insert_row_widgets(r, prov_id="", model_text=""):
            prov_cb = _make_prov_combo(prov_id)
            model_w = _make_model_widget(prov_id, model_text)
            self.compaction_table.setCellWidget(r, 0, prov_cb)
            self.compaction_table.setCellWidget(r, 1, model_w)

            def _on_prov_changed(_idx, _pcb=prov_cb):
                # Find this row by locating the combo in column 0
                _r = next((i for i in range(self.compaction_table.rowCount())
                            if self.compaction_table.cellWidget(i, 0) is _pcb), -1)
                if _r < 0:
                    return
                new_prov_id = _pcb.currentData() or ""
                old_mw = self.compaction_table.cellWidget(_r, 1)
                old_text = (old_mw.currentText() if isinstance(old_mw, QComboBox)
                            else old_mw.text() if isinstance(old_mw, QLineEdit)
                            else "")
                self.compaction_table.setCellWidget(_r, 1,
                                                    _make_model_widget(new_prov_id, old_text))
            prov_cb.currentIndexChanged.connect(_on_prov_changed)

        # Populate from saved config
        for row_data in history_cfg.get("compaction_model_limits",
                                        HISTORY_DEFAULTS["compaction_model_limits"]):
            r = self.compaction_table.rowCount()
            self.compaction_table.insertRow(r)
            _prov_val  = str(row_data[0]) if len(row_data) > 0 else ""
            _model_val = str(row_data[1]) if len(row_data) > 1 else ""
            _insert_row_widgets(r, _prov_val, _model_val)
            if len(row_data) > 2:
                self.compaction_table.setItem(r, 2, QTableWidgetItem(str(row_data[2])))
        grp_compact_lay.addWidget(self.compaction_table)

        tbl_btn_row = QHBoxLayout()
        tbl_btn_row.setContentsMargins(0, 0, 0, 0)
        self.btn_co_add_row = QPushButton("+ 添加行")
        self.btn_co_rm_row  = QPushButton("− 删除行")
        self.btn_co_add_row.setFixedWidth(90)
        self.btn_co_rm_row.setFixedWidth(110)
        for _b in (self.btn_co_add_row, self.btn_co_rm_row):
            _b.setStyleSheet("QPushButton { font-size: 9pt; padding: 2px 6px; }")
        tbl_btn_row.addWidget(self.btn_co_add_row)
        tbl_btn_row.addWidget(self.btn_co_rm_row)
        tbl_btn_row.addStretch()
        grp_compact_lay.addLayout(tbl_btn_row)

        def _co_add_row():
            r = self.compaction_table.rowCount()
            self.compaction_table.insertRow(r)
            _insert_row_widgets(r, provider_type, "")
            self.compaction_table.setItem(r, 2, QTableWidgetItem(""))
            self.compaction_table.setCurrentCell(r, 2)
        self.btn_co_add_row.clicked.connect(_co_add_row)

        def _co_rm_row():
            rows = sorted({idx.row() for idx in self.compaction_table.selectedIndexes()},
                          reverse=True)
            for r in rows:
                self.compaction_table.removeRow(r)
            if not rows and self.compaction_table.rowCount() > 0:
                self.compaction_table.removeRow(self.compaction_table.rowCount() - 1)
        self.btn_co_rm_row.clicked.connect(_co_rm_row)

        # Default token limit
        default_row = QHBoxLayout()
        default_row.setContentsMargins(0, 0, 0, 0)
        default_lbl = QLabel("默认 Token 限制（表中未列出模型时）：")
        default_lbl.setStyleSheet("font-size: 9pt;")
        self.sp_compaction_default = QSpinBox()
        self.sp_compaction_default.setRange(1000, 1_000_000)
        self.sp_compaction_default.setSingleStep(1000)
        self.sp_compaction_default.setSuffix(" tokens")
        self.sp_compaction_default.setValue(
            history_cfg.get("compaction_default_limit",
                            HISTORY_DEFAULTS["compaction_default_limit"]))
        self.sp_compaction_default.setFixedWidth(120)
        default_row.addWidget(default_lbl)
        default_row.addWidget(self.sp_compaction_default)
        default_row.addStretch()
        grp_compact_lay.addLayout(default_row)

        compact_info = QLabel(
            "启用后，插件会限制每轮发送给 LLM 的聊天历史量。<b>截断</b>静默修剪最早的消息。"
            "<b>LLM 总结</b>在达到阈值时让模型编写总结；"
            "该总结保存为聊天日志中的压缩块，并作为所有后续消息的上下文注释。<br>"
            "⚠ 旧消息<i>永远不会</i>从本地聊天日志中删除——只有转发给 LLM 的部分受到影响。<br>"
            "⚠ 当项目上下文激活时，压缩会自动禁用。"
        )
        compact_info.setWordWrap(True)
        compact_info.setTextFormat(Qt.RichText)
        compact_info.setStyleSheet("color: gray; font-size: 8pt;")
        grp_compact_lay.addWidget(compact_info)

        # Sub-option widgets that enable/disable with master checkbox
        _compact_sub_widgets = [
            self.rb_co_cutoff, self.rb_co_llm,
            self.sp_compaction_threshold,
            self.compaction_table, self.btn_co_add_row, self.btn_co_rm_row,
            self.sp_compaction_default,
        ]

        def _sync_compaction():
            on = self.chk_compaction_enabled.isChecked()
            for _w in _compact_sub_widgets:
                _w.setEnabled(on)
            _is_llm = on and self.rb_co_llm.isChecked()
            _ag_mode = (agentic_cfg or {}).get("autonomous_mode", "semi")
            self.lbl_llm_strategy_warn.setVisible(_is_llm and _ag_mode != "full")

        self.chk_compaction_enabled.toggled.connect(_sync_compaction)
        self.co_strategy_group.buttonToggled.connect(lambda *_: _sync_compaction())
        _sync_compaction()

        pl.addWidget(grp_compact)
        pl.addStretch()
        tabs.addTab(proj_scroll, "📁 上下文")

        # ── Tab 5: System Prompts ────────────────────────────────────
        sp_w = QWidget(self)
        sp_lay = QVBoxLayout(sp_w)
        sp_lay.setContentsMargins(12, 12, 12, 12)
        sp_lay.setSpacing(8)

        top_bar = QHBoxLayout()
        self.sp_combo = QComboBox()
        self.sp_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_bar.addWidget(self.sp_combo, 1)

        self.sp_delete_btn = QPushButton("删除")
        self.sp_new_btn    = QPushButton("+ 新建")
        for btn in (self.sp_delete_btn, self.sp_new_btn):
            btn.setFixedWidth(74)
            top_bar.addWidget(btn)
        sp_lay.addLayout(top_bar)

        line = QFrame(sp_w)
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #444;")
        sp_lay.addWidget(line)

        default_row = QHBoxLayout()
        default_lbl = QLabel("新聊天的默认提示词：")
        default_lbl.setStyleSheet("font-size: 9pt; color: #aaa;")
        default_row.addWidget(default_lbl)
        self.sp_default_combo = QComboBox()
        self.sp_default_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.sp_default_combo.setStyleSheet("font-size: 9pt;")
        default_row.addWidget(self.sp_default_combo, 1)
        sp_lay.addLayout(default_row)

        self._sp_default_id = default_system_prompt_id  # track current selection

        line2 = QFrame(sp_w)
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("color: #444;")
        sp_lay.addWidget(line2)

        form2 = QFormLayout()
        form2.setSpacing(6)
        self.sp_title_edit = QLineEdit()
        self.sp_title_edit.setPlaceholderText("提示词标题…")
        form2.addRow("标题：", self.sp_title_edit)
        sp_lay.addLayout(form2)

        self.sp_content_edit = QPlainTextEdit()
        self.sp_content_edit.setPlaceholderText("提示词内容…")
        self.sp_content_edit.setMinimumHeight(138)
        sp_lay.addWidget(self.sp_content_edit, 1)

        save_row = QHBoxLayout()
        save_row.addStretch()
        self.sp_save_btn = QPushButton("💾 保存提示词")
        self.sp_save_btn.setFixedWidth(150)
        save_row.addWidget(self.sp_save_btn)
        sp_lay.addLayout(save_row)

        tabs.addTab(sp_w, "💬 系统提示词")

        self._sp_current_id   = None
        self._sp_orig_title   = ""
        self._sp_orig_content = ""
        self._sp_populate_combo()

        self.sp_combo.currentIndexChanged.connect(self._sp_on_select)
        self.sp_new_btn.clicked.connect(self._sp_on_new)
        self.sp_delete_btn.clicked.connect(self._sp_on_delete)
        self.sp_save_btn.clicked.connect(self._sp_on_save)
        self.sp_title_edit.textChanged.connect(self._sp_mark_dirty)
        self.sp_content_edit.textChanged.connect(self._sp_mark_dirty)

        self._sp_set_editor_enabled(False)


        # ── Tab 5: Commands ──────────────────────────────────────────
        cmd_w = QWidget(self)
        cmd_lay = QVBoxLayout(cmd_w)
        cmd_lay.setContentsMargins(12, 12, 12, 12)
        cmd_lay.setSpacing(8)

        cmd_info = QLabel(
            "为聊天输入字段定义斜杠命令别名。"
            "在输入框中输入 <b>/</b> 可查看命令选择器——"
            "内置插件命令显示在列表底部。"
            "命令名称至少 2 个字符，不包含前导 /。"
        )
        cmd_info.setWordWrap(True)
        cmd_info.setTextFormat(Qt.RichText)
        cmd_info.setStyleSheet("color: #aaa; font-size: 9pt;")
        cmd_lay.addWidget(cmd_info)

        # — Built-in commands (read-only display) —
        _bi_fg   = "#8888cc" if _dark else "#4444aa"
        _bi_bg   = "#1a1a2a" if _dark else "#f0f0ff"
        _bi_bd   = "#444444" if _dark else "#aaaacc"
        bi_grp = QGroupBox("⚡  内置命令（只读）")
        bi_grp.setStyleSheet(
            f"QGroupBox {{ border: 1px solid {_bi_bd}; border-radius: 4px; margin-top: 6px; "
            f"font-size: 9pt; color: {_bi_fg}; }} "
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }"
        )
        bi_vl = QVBoxLayout(bi_grp)
        bi_vl.setContentsMargins(8, 8, 8, 8)
        bi_vl.setSpacing(3)

        self._cmd_builtin_list = QListWidget()
        self._cmd_builtin_list.setStyleSheet(
            f"QListWidget {{ background: {_bi_bg}; border: none; "
            f"color: {_bi_fg}; font-size: 9pt; }}"
            "QListWidget::item { padding: 3px 6px; }"
        )
        self._cmd_builtin_list.setFixedHeight(max(36, len(BUILTIN_COMMANDS) * 28 + 4))
        for b in BUILTIN_COMMANDS:
            item = QListWidgetItem(f"⚡ /{b['name']}   —   {b['description']}")
            item.setFlags(Qt.ItemIsEnabled)   # visible but not selectable
            if b.get("tooltip"):
                item.setToolTip(b["tooltip"])
            self._cmd_builtin_list.addItem(item)
        bi_vl.addWidget(self._cmd_builtin_list)

        bi_note = QLabel(
            "这些命令由插件提供，无法编辑或删除。")
        bi_note.setStyleSheet("color: #666; font-size: 8pt;")
        bi_note.setWordWrap(True)
        bi_vl.addWidget(bi_note)
        cmd_lay.addWidget(bi_grp)

        cmd_top = QHBoxLayout()
        self._cmd_list = QListWidget()
        self._cmd_list.setStyleSheet(
            "QListWidget { border: 1px solid #444; border-radius: 3px; }"
            "QListWidget::item { padding: 3px 6px; }"
            "QListWidget::item:selected { background: #2a4a2a; color: #b8e090; }"
        )
        self._cmd_list.setFixedHeight(161)
        cmd_top.addWidget(self._cmd_list, 1)

        cmd_btns = QVBoxLayout()
        cmd_btns.setSpacing(4)
        self._cmd_new_btn    = QPushButton("+ 新建")
        self._cmd_delete_btn = QPushButton("删除")
        self._cmd_reset_btn  = QPushButton("恢复\n内置默认值")
        builtin_names = ", ".join(f"/{c['name']}" for c in DEFAULT_COMMANDS)
        self._cmd_reset_btn.setToolTip(
            f"将内置命令恢复为默认提示文本：\n"
            f"{builtin_names}\n\n"
            f"用户定义的命令不受影响。"
        )
        for b in (self._cmd_new_btn, self._cmd_delete_btn, self._cmd_reset_btn):
            b.setFixedWidth(127)
            cmd_btns.addWidget(b)
        cmd_btns.addStretch()
        cmd_top.addLayout(cmd_btns)
        cmd_lay.addLayout(cmd_top)

        cmd_sep = QFrame(cmd_w)
        cmd_sep.setFrameShape(QFrame.HLine)
        cmd_sep.setStyleSheet("color: #444;")
        cmd_lay.addWidget(cmd_sep)

        cmd_form = QFormLayout()
        cmd_form.setSpacing(6)
        self._cmd_name_edit = QLineEdit()
        self._cmd_name_edit.setPlaceholderText("命令名称（至少 2 个字符，不含 /）")
        cmd_form.addRow("名称：", self._cmd_name_edit)
        cmd_lay.addLayout(cmd_form)

        self._cmd_prompt_edit = QPlainTextEdit()
        self._cmd_prompt_edit.setPlaceholderText(
            "使用此命令时发送给 LLM 的提示文本…")
        self._cmd_prompt_edit.setMinimumHeight(92)
        cmd_lay.addWidget(self._cmd_prompt_edit, 1)

        cmd_save_row = QHBoxLayout()
        cmd_save_row.addStretch()
        self._cmd_save_btn = QPushButton("保存命令")
        self._cmd_save_btn.setFixedWidth(150)
        cmd_save_row.addWidget(self._cmd_save_btn)
        cmd_lay.addLayout(cmd_save_row)

        tabs.addTab(cmd_w, "/ 命令")

        self._cmd_commands    = list(commands) if commands else load_commands()
        self._cmd_current_idx = -1
        self._cmd_orig_name   = ""
        self._cmd_orig_prompt = ""
        self._cmd_populate_list()
        self._cmd_set_editor_enabled(False)

        self._cmd_list.currentRowChanged.connect(self._cmd_on_select)
        self._cmd_new_btn.clicked.connect(self._cmd_on_new)
        self._cmd_delete_btn.clicked.connect(self._cmd_on_delete)
        self._cmd_reset_btn.clicked.connect(self._cmd_on_reset)
        self._cmd_save_btn.clicked.connect(self._cmd_on_save)
        self._cmd_name_edit.textChanged.connect(self._cmd_mark_dirty)
        self._cmd_prompt_edit.textChanged.connect(self._cmd_mark_dirty)



        # ── Tab 6: Auto-complete ─────────────────────────────────────
        fim_cfg = fim_cfg or {}
        fim_w = QWidget(self)
        fim_outer = QVBoxLayout(fim_w)
        fim_outer.setContentsMargins(10, 10, 10, 10)

        # Enable checkbox — unchecked by default (requires explicit setup)
        self.fim_enabled = QCheckBox("在编辑器中启用 AI 自动补全")
        self.fim_enabled.setChecked(fim_cfg.get("enabled", False))
        fim_outer.addWidget(self.fim_enabled)

        # ── Provider group ──────────────────────────────────────────
        prov_group = QGroupBox("提供商")
        pf = QFormLayout()
        pf.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.fim_provider_combo = QComboBox()
        for k, label in [
            ("lmstudio",    "LM Studio（本地）"),
            ("ollama",      "Ollama（本地）"),
            ("vllm",        "vLLM（本地/远程）"),
            ("deepseek",    "DeepSeek"),
            ("codestral",   "Mistral / Codestral"),
            ("openrouter",  "OpenRouter"),
            ("custom",      "自定义"),
        ]:
            self.fim_provider_combo.addItem(label, userData=k)
        cur_prov = fim_cfg.get("provider", "lmstudio")
        idx = self.fim_provider_combo.findData(cur_prov)
        if idx >= 0:
            self.fim_provider_combo.setCurrentIndex(idx)
        pf.addRow("提供商：", self.fim_provider_combo)

        default_url = fim_cfg.get(
            "api_url",
            _FIM_PROVIDER_URLS.get(cur_prov, "http://localhost:1234"))
        self.fim_url_edit = QLineEdit(default_url)
        pf.addRow("API URL：", self.fim_url_edit)

        self.fim_key_edit = QLineEdit(fim_cfg.get("api_key", ""))
        self.fim_key_edit.setEchoMode(QLineEdit.Password)
        self.fim_key_edit.setPlaceholderText(
            "（可选 — 本地服务器可留空）")
        pf.addRow("API 密钥：", self.fim_key_edit)

        # Load button + inline status label
        load_row = QHBoxLayout()
        self.fim_load_btn = QPushButton("加载模型")
        self.fim_load_btn.setFixedWidth(127)
        self.fim_status_lbl = QLabel("")
        self.fim_status_lbl.setWordWrap(True)
        load_row.addWidget(self.fim_load_btn)
        load_row.addWidget(self.fim_status_lbl, 1)
        pf.addRow("", load_row)

        # Model combo — editable so user can also type a name manually.
        # Restore the full model list saved from the previous session so the
        # user gets their full dropdown back without needing to re-load models.
        self.fim_model_combo = QComboBox()
        self.fim_model_combo.setEditable(True)
        self.fim_model_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.fim_model_combo.setMinimumContentsLength(30)
        saved_model  = fim_cfg.get("model", "")
        saved_models = fim_cfg.get("models", [])
        if saved_models:
            for m in saved_models:
                self.fim_model_combo.addItem(m)
            idx = self.fim_model_combo.findText(saved_model)
            if idx >= 0:
                self.fim_model_combo.setCurrentIndex(idx)
        elif saved_model:
            self.fim_model_combo.addItem(saved_model)
        pf.addRow("模型：", self.fim_model_combo)

        # Backend combo — restore the tested/filtered list from the previous
        # session; fall back to the full list only when nothing was saved yet.
        self.fim_backend_combo = QComboBox()
        saved_backends = fim_cfg.get("backends", [])   # list of [key, label]
        backend_source = (
            saved_backends if saved_backends else _FimLoader._ALL_BACKENDS)
        for k, label in backend_source:
            self.fim_backend_combo.addItem(label, userData=k)
        cur_bt = fim_cfg.get("backend_type", "openai_completions")
        idx = self.fim_backend_combo.findData(cur_bt)
        if idx >= 0:
            self.fim_backend_combo.setCurrentIndex(idx)
        pf.addRow("后端类型：", self.fim_backend_combo)

        prov_group.setLayout(pf)
        fim_outer.addWidget(prov_group)

        # ── Model Parameters group ──────────────────────────────────
        param_group = QGroupBox("模型参数")
        paramf = QFormLayout()

        self.fim_max_tokens = QSpinBox()
        self.fim_max_tokens.setRange(16, 1024)
        self.fim_max_tokens.setSingleStep(16)
        self.fim_max_tokens.setValue(fim_cfg.get("max_tokens", 128))
        paramf.addRow("最大 Token 数：", self.fim_max_tokens)

        self.fim_temperature = QDoubleSpinBox()
        self.fim_temperature.setRange(0.0, 2.0)
        self.fim_temperature.setSingleStep(0.05)
        self.fim_temperature.setDecimals(2)
        self.fim_temperature.setValue(fim_cfg.get("temperature", 0.5))
        paramf.addRow("温度：", self.fim_temperature)

        self.fim_ctx_before = QSpinBox()
        self.fim_ctx_before.setRange(1, 32000)
        self.fim_ctx_before.setSingleStep(500)
        self.fim_ctx_before.setValue(fim_cfg.get("context_before", 100))
        paramf.addRow("光标前上下文（字符）：", self.fim_ctx_before)

        self.fim_ctx_after = QSpinBox()
        self.fim_ctx_after.setRange(0, 8000)
        self.fim_ctx_after.setSingleStep(100)
        self.fim_ctx_after.setValue(fim_cfg.get("context_after", 100))
        paramf.addRow("光标后上下文（字符）：", self.fim_ctx_after)

        param_group.setLayout(paramf)
        fim_outer.addWidget(param_group)

        # ── Trigger group ───────────────────────────────────────────
        trig_group = QGroupBox("触发方式")
        trigf = QFormLayout()

        self.fim_trigger_combo = QComboBox()
        for k, label in [("auto",         "自动（输入暂停后）"),
                          ("newline_only", "仅在新行后"),
                          ("manual",       "仅手动 (Alt+\\)")]:
            self.fim_trigger_combo.addItem(label, userData=k)
        cur_tm = fim_cfg.get("trigger_mode", "auto")
        idx = self.fim_trigger_combo.findData(cur_tm)
        if idx >= 0:
            self.fim_trigger_combo.setCurrentIndex(idx)
        trigf.addRow("触发模式：", self.fim_trigger_combo)

        self.fim_debounce = QSpinBox()
        self.fim_debounce.setRange(100, 5000)
        self.fim_debounce.setSingleStep(100)
        self.fim_debounce.setSuffix(" ms")
        self.fim_debounce.setValue(fim_cfg.get("debounce_ms", 600))
        trigf.addRow("防抖延迟：", self.fim_debounce)

        trig_group.setLayout(trigf)
        fim_outer.addWidget(trig_group)

        fim_outer.addStretch()

        # Keep refs for state management
        self._fim_param_group = param_group
        self._fim_trig_group  = trig_group
        self._fim_loader      = None

        # Spinner animation for loading feedback
        self._fim_spinner_frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._fim_spinner_idx    = 0
        self._fim_status_msg     = ""
        self._fim_spinner_timer  = QTimer(self)
        self._fim_spinner_timer.setInterval(80)
        self._fim_spinner_timer.timeout.connect(self._fim_spinner_tick)

        # Connect signals (after all widgets exist — avoids spurious init triggers)
        self.fim_enabled.toggled.connect(self._fim_on_enabled_toggled)
        self.fim_provider_combo.activated.connect(self._fim_on_provider_changed)
        self.fim_load_btn.clicked.connect(self._fim_load_models)

        # Apply initial state
        has_model = bool(fim_cfg.get("model", ""))
        if fim_cfg.get("enabled", False) and has_model:
            self._fim_set_state("ready")
        elif fim_cfg.get("enabled", False):
            self._fim_set_state("provider_only")
        else:
            self._fim_set_state("disabled")

        tabs.addTab(fim_w, "⚡ 自动补全")

        # ── Tab 8: Agentic Actions ───────────────────────────────────
        ag_cfg = {**AGENTIC_DEFAULTS, **(agentic_cfg or {})}
        ag_w   = QWidget(self)
        ag_scroll = QScrollArea(self)
        ag_scroll.setWidgetResizable(True)
        ag_scroll.setFrameShape(QFrame.NoFrame)
        ag_scroll.setWidget(ag_w)
        agl    = QVBoxLayout(ag_w)
        agl.setContentsMargins(12, 12, 12, 12)
        agl.setSpacing(8)

        ag_info = QLabel(
            "启用后，LLM 可以生成特殊的代码围栏来触发实际操作："
            "创建/覆盖文件、在 IPython 控制台中运行代码、安装包以及应用统一差异补丁。"
            "启用时代理系统提示词始终会被注入。"
        )
        ag_info.setWordWrap(True)
        ag_info.setTextFormat(Qt.PlainText)
        ag_info.setStyleSheet(
            "color: #aaa; font-size: 9pt; padding: 6px; "
            "background: rgba(128,128,128,0.08); border-radius: 4px;")
        agl.addWidget(ag_info)

        sep_ag = QFrame(ag_w)
        sep_ag.setFrameShape(QFrame.HLine)
        sep_ag.setStyleSheet("color: #444; margin: 2px 0;")
        agl.addWidget(sep_ag)

        # Master switch + batch confirm — side by side in one row
        switch_row = QHBoxLayout()
        switch_row.setSpacing(24)
        self.ag_enabled = QCheckBox("启用代理模式")
        self.ag_enabled.setChecked(ag_cfg.get("enabled", True))
        self.ag_enabled.setToolTip(
            "主开关。关闭时，操作围栏会渲染为普通代码块。")
        switch_row.addWidget(self.ag_enabled)

        agl.addLayout(switch_row)

        # ── Autonomous Mode section ────────────────────────────────────────
        _mode_cur = ag_cfg.get("autonomous_mode", "semi")

        _mode_hdr_row = QHBoxLayout()
        mode_hdr = QLabel("自主模式：")
        mode_hdr.setStyleSheet("font-weight: bold; font-size: 9pt;")
        _mode_hdr_row.addWidget(mode_hdr)
        _info_btn = QPushButton("ℹ")
        _info_btn.setFixedSize(20, 20)
        _info_btn.setToolTip("显示自主模式行为矩阵")
        _info_btn.setStyleSheet(
            "QPushButton { background: #2a3a5a; color: #8ab4e8; border: 1px solid #446; "
            "border-radius: 10px; font-size: 8pt; font-weight: bold; padding: 0; } "
            "QPushButton:hover { background: #3a4a6a; }")

        def _show_mode_info():
            _dlg = QDialog(self)
            _dlg.setWindowTitle("自主模式 — 行为矩阵")
            _dlg.setMinimumWidth(620)
            _dlg_lay = QVBoxLayout(_dlg)
            _dlg_lay.setContentsMargins(18, 16, 18, 14)
            _dlg_lay.setSpacing(0)

            # ── palette (reuses the _dark closure from __init__) ─────────────
            _title_fg  = "#c8d8f0" if _dark else "#1a3a6a"
            _sub_fg    = "#888888" if _dark else "#555555"
            _th_bg     = "#2a3a5a" if _dark else "#dde8f5"
            _th_fg     = "#8ab4e8" if _dark else "#1a3a6a"
            _th_bd     = "#446688" if _dark else "#8ab4e8"
            _td_bg     = "#1a1a2e" if _dark else "#f8f8ff"
            _td2_bg    = "#141420" if _dark else "#f0f0f8"
            _td_bd     = "#444444" if _dark else "#cccccc"
            _td_fg     = "#cccccc" if _dark else "#222222"
            _act_bg    = "#1a1a2e" if _dark else "#e8e8f5"
            _act2_bg   = "#141420" if _dark else "#dcdcee"
            _act_fg    = "#aaaaaa" if _dark else "#333333"
            _dlg_col   = "#e0a050" if _dark else "#8a5000"   # "Batch/Confirm dialog"
            _yes_col   = "#6cbe6c" if _dark else "#1a6a1a"   # auto-sent ✓
            _pnl_col   = "#50c8c8" if _dark else "#007a7a"   # per-block panel
            _sil_col   = "#8888cc" if _dark else "#4444aa"   # Silent

            _TH  = (f"style='background:{_th_bg};color:{_th_fg};padding:5px 8px;"
                    f"border:1px solid {_th_bd};text-align:center;'")
            _TD  = (f"style='padding:5px 8px;border:1px solid {_td_bd};color:{_td_fg};"
                    f"vertical-align:top;background:{_td_bg};'")
            _TD2 = (f"style='padding:5px 8px;border:1px solid {_td_bd};color:{_td_fg};"
                    f"vertical-align:top;background:{_td2_bg};'")
            _ACT = (f"style='padding:5px 8px;border:1px solid {_td_bd};color:{_act_fg};"
                    f"font-weight:bold;vertical-align:top;background:{_act_bg};'")
            _ACT2= (f"style='padding:5px 8px;border:1px solid {_td_bd};color:{_act_fg};"
                    f"font-weight:bold;vertical-align:top;background:{_act2_bg};'")
            _DLG = f"style='color:{_dlg_col};'"
            _YES = f"style='color:{_yes_col};'"
            _PNL = f"style='color:{_pnl_col};'"
            _SIL = f"style='color:{_sil_col};'"

            # — Title —
            _title = QLabel("自主模式 — 行为矩阵")
            _title.setStyleSheet(
                f"font-size: 11pt; font-weight: bold; color: {_title_fg};")
            _dlg_lay.addWidget(_title)
            _dlg_lay.addSpacing(4)

            # — Subtitle —
            _sub = QLabel(
                "每种模式如何处理代理操作以及结果是否转发给 LLM。")
            _sub.setWordWrap(True)
            _sub.setStyleSheet(f"font-size: 8pt; color: {_sub_fg};")
            _dlg_lay.addWidget(_sub)
            _dlg_lay.addSpacing(14)

            # — Table —
            _tbl = QLabel()
            _tbl.setTextFormat(Qt.RichText)
            _tbl.setText(
                f"<table style='border-collapse:collapse;width:100%;font-size:9pt;'>"
                f"<tr>"
                f"  <th {_TH}>操作类型</th>"
                f"  <th {_TH}>手动</th>"
                f"  <th {_TH}>半自动</th>"
                f"  <th {_TH}>完全<br><small>（确认修改）</small></th>"
                f"  <th {_TH}>完全<br><small>（全部静默）</small></th>"
                f"</tr>"
                f"<tr>"
                f"  <td {_ACT}>Read / ls / grep</td>"
                f"  <td {_TD}><span {_DLG}>Batch dialog</span><br>"
                f"             <span {_PNL}>panel → user decides</span></td>"
                f"  <td {_TD}><span {_DLG}>Batch dialog</span><br>"
                f"             <span {_YES}>auto-sent ✓</span></td>"
                f"  <td {_TD}><span {_SIL}>Silent</span><br>"
                f"             <span {_YES}>auto-sent ✓</span></td>"
                f"  <td {_TD}><span {_SIL}>Silent</span><br>"
                f"             <span {_YES}>auto-sent ✓</span></td>"
                f"</tr>"
                f"<tr>"
                f"  <td {_ACT2}>Git</td>"
                f"  <td {_TD2}><span {_DLG}>Batch dialog</span><br>"
                f"              <span {_PNL}>panel → user decides</span></td>"
                f"  <td {_TD2}><span {_DLG}>Batch dialog</span><br>"
                f"              <span {_YES}>auto-sent ✓</span></td>"
                f"  <td {_TD2}><span {_DLG}>Confirm dialog</span><br>"
                f"              <span {_YES}>auto-sent ✓</span></td>"
                f"  <td {_TD2}><span {_SIL}>Silent</span><br>"
                f"              <span {_YES}>auto-sent ✓</span></td>"
                f"</tr>"
                f"<tr>"
                f"  <td {_ACT}>其他修改<br>"
                f"              <small>（文件 / 补丁 / 运行 / 安装<br>"
                f"               删除 / 重命名）</small></td>"
                f"  <td {_TD}><span {_DLG}>Batch dialog</span><br>"
                f"             <span {_YES}>auto-sent ✓</span></td>"
                f"  <td {_TD}><span {_DLG}>Batch dialog</span><br>"
                f"             <span {_YES}>auto-sent ✓</span></td>"
                f"  <td {_TD}><span {_DLG}>Confirm dialog</span><br>"
                f"             <span {_YES}>auto-sent ✓</span></td>"
                f"  <td {_TD}><span {_SIL}>Silent</span><br>"
                f"             <span {_YES}>auto-sent ✓</span></td>"
                f"</tr>"
                f"</table>"
            )
            _dlg_lay.addWidget(_tbl)
            _dlg_lay.addSpacing(12)

            # — Legend —
            _legend = QLabel()
            _legend.setWordWrap(True)
            _legend.setTextFormat(Qt.RichText)
            _legend.setStyleSheet(f"color: {_sub_fg}; font-size: 8pt;")
            _legend.setText(
                f"<b>手动</b> — 所有操作都通过批量确认对话框进行。"
                f"检查结果（读取/列出/搜索）和 git 输出出现在每个块的输出面板中，"
                f"你可以选择<em>发送给 LLM</em>或<em>忽略</em>。"
                f"其他修改结果（文件写入、补丁应用、删除、重命名等）作为简要确认自动发送，"
                f"以便 LLM 知道哪些操作已完成。<br>"
                f"<b>半自动</b> — 每次 LLM 回复后显示批量对话框；所有批准的操作执行后，"
                f"其结果自动转发给 LLM。<br>"
                f"<b>完全（确认修改）</b> — 读取静默运行；写入/运行/git 操作通过确认对话框；"
                f"所有结果自动发送。<br>"
                f"<b>完全（全部静默）</b> — 每个操作无需任何确认即可执行；"
                f"结果立即自动发送。"
            )
            _dlg_lay.addWidget(_legend)
            _dlg_lay.addSpacing(12)

            _ok = QPushButton("关闭")
            _ok.clicked.connect(_dlg.accept)
            _ok.setFixedWidth(80)
            _h = QHBoxLayout()
            _h.addStretch()
            _h.addWidget(_ok)
            _dlg_lay.addLayout(_h)
            _dlg.exec_()

        _info_btn.clicked.connect(_show_mode_info)
        _mode_hdr_row.addWidget(_info_btn)
        _mode_hdr_row.addStretch()
        agl.addLayout(_mode_hdr_row)

        # Three mutually-exclusive radio buttons
        self.ag_mode_group = QButtonGroup(self)
        self.ag_mode_off  = QRadioButton(
            "手动 — 所有操作的批量对话框，结果不会自动发送给 LLM")
        self.ag_mode_semi = QRadioButton("半自动 — 每次 LLM 回复后的批量对话框，结果自动发送")
        self.ag_mode_full = QRadioButton("完全 — 无需确认即可执行所有 LLM 操作")
        self.ag_mode_off.setChecked(_mode_cur == "off")
        self.ag_mode_semi.setChecked(_mode_cur == "semi")
        self.ag_mode_full.setChecked(_mode_cur == "full")
        for _rb in (self.ag_mode_off, self.ag_mode_semi, self.ag_mode_full):
            self.ag_mode_group.addButton(_rb)
            agl.addWidget(_rb)

        # Sub-option for Full mode only: confirm modifying actions
        _full_indent = QHBoxLayout()
        _full_indent.setContentsMargins(24, 0, 0, 0)
        self.ag_confirm_modifying = QCheckBox(
            "仅确认修改操作（文件、补丁、git、运行、安装）")
        self.ag_confirm_modifying.setChecked(
            ag_cfg.get("full_auto_confirm_modifying", True))
        self.ag_confirm_modifying.setEnabled(_mode_cur == "full")
        _full_indent.addWidget(self.ag_confirm_modifying)
        _full_indent.addStretch()
        agl.addLayout(_full_indent)

        # Red warning box — visible only in Full mode
        self.ag_full_warning = QLabel(
            "⚠  警告：在完全自主模式下，LLM 可以执行任何允许的操作而无需用户审查。"
            "请将上方允许的操作类型限制为只有你信任 LLM 在无人监督下执行的操作。")
        self.ag_full_warning.setWordWrap(True)
        _aw_fg = "#e8a050" if _dark else "#7a4500"
        _aw_bg = "#1e1200" if _dark else "#fff3e0"
        _aw_bd = "#7a4a00" if _dark else "#c89050"
        self.ag_full_warning.setStyleSheet(
            f"color: {_aw_fg}; background: {_aw_bg}; border: 1px solid {_aw_bd}; "
            "border-radius: 3px; padding: 6px; font-size: 8pt;")
        self.ag_full_warning.setVisible(_mode_cur == "full")
        agl.addWidget(self.ag_full_warning)

        def _sync_mode():
            _is_full = self.ag_mode_full.isChecked()
            self.ag_confirm_modifying.setEnabled(_is_full)
            self.ag_full_warning.setVisible(_is_full)
            self._refresh_agentic_preview()

        self.ag_mode_group.buttonToggled.connect(lambda *_: _sync_mode())
        self.ag_confirm_modifying.stateChanged.connect(self._refresh_agentic_preview)

        sep_ag3 = QFrame(ag_w)
        sep_ag3.setFrameShape(QFrame.HLine)
        sep_ag3.setStyleSheet("color: #444; margin: 2px 0;")
        agl.addWidget(sep_ag3)

        # Allow checkboxes — 2 × 2 grid
        allow_lbl = QLabel("允许的操作：")
        allow_lbl.setStyleSheet("font-weight: bold; font-size: 9pt;")
        agl.addWidget(allow_lbl)

        allow_grid = QGridLayout()
        allow_grid.setSpacing(4)
        allow_grid.setColumnStretch(0, 1)
        allow_grid.setColumnStretch(1, 1)

        self.ag_allow_create = QCheckBox("允许：创建/覆盖文件")
        self.ag_allow_create.setChecked(ag_cfg.get("allow_create_file", True))
        allow_grid.addWidget(self.ag_allow_create, 0, 0)

        self.ag_allow_run = QCheckBox("允许：在控制台运行代码")
        self.ag_allow_run.setChecked(ag_cfg.get("allow_run_console", True))
        allow_grid.addWidget(self.ag_allow_run, 0, 1)

        self.ag_allow_install = QCheckBox(
            "允许：安装包（默认关闭 — 风险较高）")
        self.ag_allow_install.setChecked(ag_cfg.get("allow_install", False))
        allow_grid.addWidget(self.ag_allow_install, 1, 0)

        self.ag_allow_patch = QCheckBox("允许：应用补丁")
        self.ag_allow_patch.setChecked(ag_cfg.get("allow_patch", True))
        allow_grid.addWidget(self.ag_allow_patch, 1, 1)

        self.ag_allow_git = QCheckBox("允许：运行 git 命令")
        self.ag_allow_git.setChecked(ag_cfg.get("allow_git", True))
        allow_grid.addWidget(self.ag_allow_git, 2, 0)

        self.ag_allow_read = QCheckBox("允许：读取文件 (read:path)")
        self.ag_allow_read.setChecked(ag_cfg.get("allow_read", True))
        allow_grid.addWidget(self.ag_allow_read, 2, 1)

        self.ag_allow_ls = QCheckBox("允许：列出目录 (ls:path/)")
        self.ag_allow_ls.setChecked(ag_cfg.get("allow_ls", True))
        allow_grid.addWidget(self.ag_allow_ls, 3, 0)

        self.ag_allow_grep = QCheckBox("允许：搜索文件 (grep:pattern)")
        self.ag_allow_grep.setChecked(ag_cfg.get("allow_grep", True))
        allow_grid.addWidget(self.ag_allow_grep, 3, 1)

        self.ag_allow_delete = QCheckBox(
            "允许：删除文件（默认关闭 — 不可逆）")
        self.ag_allow_delete.setChecked(ag_cfg.get("allow_delete", False))
        allow_grid.addWidget(self.ag_allow_delete, 4, 0)

        self.ag_allow_delete_dir = QCheckBox(
            "允许：删除目录（默认关闭 — 递归、不可逆）")
        self.ag_allow_delete_dir.setChecked(ag_cfg.get("allow_delete_dir", False))
        allow_grid.addWidget(self.ag_allow_delete_dir, 4, 1)

        self.ag_allow_rename = QCheckBox(
            "允许：重命名/移动文件（默认关闭）")
        self.ag_allow_rename.setChecked(ag_cfg.get("allow_rename", False))
        allow_grid.addWidget(self.ag_allow_rename, 5, 0)

        self.ag_allow_rename_dir = QCheckBox(
            "允许：重命名/移动目录（默认关闭）")
        self.ag_allow_rename_dir.setChecked(ag_cfg.get("allow_rename_dir", False))
        allow_grid.addWidget(self.ag_allow_rename_dir, 5, 1)

        agl.addLayout(allow_grid)

        allow_note = QLabel(
            "当操作类型被禁用时，LLM 的代码围栏将显示为普通代码块——内容可见但不显示操作按钮。")
        allow_note.setWordWrap(True)
        allow_note.setStyleSheet("color: #888; font-size: 8pt;")
        agl.addWidget(allow_note)

        sep_ag3 = QFrame(ag_w)
        sep_ag3.setFrameShape(QFrame.HLine)
        sep_ag3.setStyleSheet("color: #444; margin: 2px 0;")
        agl.addWidget(sep_ag3)

        # Default base path
        base_lbl = QLabel("相对文件路径的默认基础路径：")
        base_lbl.setStyleSheet("font-weight: bold; font-size: 9pt;")
        agl.addWidget(base_lbl)

        base_row = QHBoxLayout()
        self.ag_base_path = QLineEdit(ag_cfg.get("base_path", ""))
        self.ag_base_path.setPlaceholderText(
            "留空使用当前项目根目录（回退到 ~）")
        self.ag_base_path.setStyleSheet("font-size: 9pt;")
        base_row.addWidget(self.ag_base_path, 1)
        ag_browse_btn = QPushButton("浏览…")
        ag_browse_btn.setFixedWidth(70)

        def _ag_browse():
            d = QFileDialog.getExistingDirectory(
                ag_w, "Select base path", self.ag_base_path.text() or "")
            if d:
                self.ag_base_path.setText(d)

        ag_browse_btn.clicked.connect(_ag_browse)
        base_row.addWidget(ag_browse_btn)
        agl.addLayout(base_row)

        base_note = QLabel(
            "file: 和 patch: 围栏中的路径相对于此目录解析。"
            "空 = 使用当前 Spyder 项目根目录，回退到 ~。")
        base_note.setWordWrap(True)
        base_note.setStyleSheet("color: #888; font-size: 8pt;")
        agl.addWidget(base_note)

        sep_ag4 = QFrame(ag_w)
        sep_ag4.setFrameShape(QFrame.HLine)
        sep_ag4.setStyleSheet("color: #444; margin: 2px 0;")
        agl.addWidget(sep_ag4)

        # Prompt preview — read-only, collapsible; updates live as checkboxes change
        tpl_header_row = QHBoxLayout()
        tpl_header_row.setSpacing(4)
        tpl_lbl = QLabel("代理系统提示词预览：")
        tpl_lbl.setStyleSheet("font-weight: bold; font-size: 9pt;")
        tpl_header_row.addWidget(tpl_lbl)
        tpl_toggle_btn = QPushButton("▶")
        tpl_toggle_btn.setFixedSize(22, 22)
        tpl_toggle_btn.setFlat(True)
        tpl_toggle_btn.setToolTip("显示/隐藏提示词预览")
        _tgl_hover = "#dddddd" if _dark else "#333333"
        tpl_toggle_btn.setStyleSheet(
            "QPushButton { color: #888; font-size: 11pt; border: none; "
            "background: transparent; padding: 0; }"
            f"QPushButton:hover {{ color: {_tgl_hover}; }}")
        tpl_header_row.addWidget(tpl_toggle_btn)
        tpl_header_row.addStretch()
        agl.addLayout(tpl_header_row)

        tpl_body = QWidget(ag_w)
        tpl_body_lay = QVBoxLayout(tpl_body)
        tpl_body_lay.setContentsMargins(0, 0, 0, 0)
        tpl_body_lay.setSpacing(4)
        tpl_note = QLabel(
            "显示将要注入的确切系统提示词，基于上方启用了哪些操作围栏。自动生成——不可编辑。")
        tpl_note.setWordWrap(True)
        tpl_note.setStyleSheet("color: #888; font-size: 8pt;")
        tpl_body_lay.addWidget(tpl_note)

        _prev_bg = "#1a1a1a" if _dark else "#f5f5f5"
        _prev_fg = "#aaaaaa" if _dark else "#333333"
        _prev_bd = "#444444" if _dark else "#bbbbbb"
        self.ag_prompt_preview = QPlainTextEdit()
        self.ag_prompt_preview.setReadOnly(True)
        self.ag_prompt_preview.setFont(QFont("Monospace", 9))
        self.ag_prompt_preview.setStyleSheet(
            f"QPlainTextEdit {{ background: {_prev_bg}; color: {_prev_fg}; "
            f"border: 1px solid {_prev_bd}; border-radius: 3px; padding: 4px; }}")
        self.ag_prompt_preview.setMinimumHeight(120)
        tpl_body_lay.addWidget(self.ag_prompt_preview)

        tpl_body.setVisible(False)   # collapsed by default
        agl.addWidget(tpl_body)

        def _toggle_tpl():
            visible = not tpl_body.isVisible()
            tpl_body.setVisible(visible)
            tpl_toggle_btn.setText("▼" if visible else "▶")
            if visible:
                self._refresh_agentic_preview()   # populate on first expand

        tpl_toggle_btn.clicked.connect(_toggle_tpl)

        # Connect all allow-checkboxes so the preview updates live
        for _cb in (
            self.ag_allow_create, self.ag_allow_run, self.ag_allow_install,
            self.ag_allow_patch,  self.ag_allow_git,
            self.ag_allow_read,   self.ag_allow_ls,  self.ag_allow_grep,
            self.ag_allow_delete, self.ag_allow_delete_dir,
            self.ag_allow_rename, self.ag_allow_rename_dir,
        ):
            _cb.stateChanged.connect(self._refresh_agentic_preview)

        agl.addStretch()
        tabs.addTab(ag_scroll, "🤖 代理")

        # ── Dialog buttons + version label ───────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        # Version label — bottom row, left side
        from spyder_ai_chat import __version__ as _ver
        ver_lbl = QLabel(f"Spyder AI 聊天  v{_ver}")
        ver_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        ver_lbl.setStyleSheet("color: #555; font-size: 8pt;")

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.addWidget(ver_lbl)
        bottom_row.addStretch()
        bottom_row.addWidget(btns)

        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addLayout(bottom_row)

        if initial_tab:
            tabs.setCurrentIndex(initial_tab)

        # Floating logo — child of dialog, positioned in the tab bar column.
        # QTimer.singleShot(0) defers until layout is computed (sizes known).
        self._logo_overlay = None
        self._logo_tabs    = tabs
        try:
            from pathlib import Path as _P
            _lp = _P(__file__).parent.parent / "resources" / "spyder_ai_chat_plugin_bg_small.png"
            if _lp.exists():
                _raw = QPixmap(str(_lp))
                if not _raw.isNull():
                    _ol = QLabel(self)
                    _ol.setPixmap(_raw.scaled(60, 60, Qt.KeepAspectRatio,
                                              Qt.SmoothTransformation))
                    _ol.setStyleSheet("background: transparent;")
                    _ol.setAttribute(Qt.WA_TransparentForMouseEvents)
                    _ol.adjustSize()
                    self._logo_overlay = _ol
                    QTimer.singleShot(0, self._place_logo_overlay)
        except Exception:
            pass

        # Construction complete — re-enable on-screen painting. exec_() will
        # now show the fully-constructed dialog with correct title + size.
        self.setAttribute(Qt.WA_DontShowOnScreen, False)

    def _place_logo_overlay(self):
        """Position the floating logo label in the bottom of the tab bar column."""
        ol = self._logo_overlay
        if ol is None:
            return
        tw  = self._logo_tabs
        bar = tw.tabBar()
        lw, lh = ol.width(), ol.height()
        # Tab bar column position in dialog coordinates
        bx = tw.x() + bar.x()
        bw = bar.width()
        x  = bx + (bw - lw) // 2          # centred in the bar column
        y  = tw.y() + tw.height() - lh - 12  # 12 px above the tab widget bottom
        ol.move(x, y)
        ol.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_logo_overlay()

    # ── Connection tab helpers ───────────────────────────────────────

    def _current_provider_id(self):
        return self._prov_combo.currentData() or "custom"

    # ── Connection test helpers ───────────────────────────────────────

    def _on_conn_test(self):
        url = self._url_edit.text().strip()
        if not url:
            self._conn_test_lbl.setText("⚠ 请先输入基础 URL")
            self._conn_test_lbl.setStyleSheet("color: orange;")
            return
        # Stop any running tester
        if self._conn_tester is not None:
            self._conn_tester.quit()
            self._conn_tester.wait(500)
        # Azure needs api-version query param
        api_ver = ""
        if self._current_provider_id() == "azure":
            api_ver = self._azure_ver_combo.currentText()
        key = self._key_edit.text().strip()
        self._conn_status_msg = "测试连接中…"
        self._conn_test_btn.setEnabled(False)
        self._conn_test_lbl.setStyleSheet("")
        self._conn_spinner_timer.start()
        tester = _ConnTester(url, key, api_ver, parent=self)
        tester.sig_ok.connect(self._conn_test_ok)
        tester.sig_error.connect(self._conn_test_error)
        tester.finished.connect(self._conn_test_finished)
        self._conn_tester = tester
        tester.start()

    def _conn_spinner_tick(self):
        self._conn_spinner_idx = (
            (self._conn_spinner_idx + 1) % len(self._conn_spinner_frames))
        frame = self._conn_spinner_frames[self._conn_spinner_idx]
        self._conn_test_lbl.setText(f"{frame}  {self._conn_status_msg}")
        self._conn_test_lbl.setStyleSheet("")

    def _conn_test_ok(self, msg):
        self._conn_spinner_timer.stop()
        self._conn_test_lbl.setText(f"✓ {msg}")
        self._conn_test_lbl.setStyleSheet("color: green;")

    def _conn_test_error(self, msg):
        self._conn_spinner_timer.stop()
        self._conn_test_lbl.setText(f"✗ {msg}")
        self._conn_test_lbl.setStyleSheet("color: red;")

    def _conn_test_finished(self):
        self._conn_spinner_timer.stop()
        self._conn_test_btn.setEnabled(True)
        self._conn_test_btn.setText("测试连接")

    def _on_provider_changed(self, _idx=None):
        """Rebuild connection form when provider selection changes."""
        pid = self._current_provider_id()
        pdef = PROVIDERS[pid]

        # Update URL field with provider default IF the current URL looks like
        # it belongs to a different provider (i.e. don't overwrite a custom URL
        # the user has already typed in an editable field).
        old_url = self._url_edit.text().strip()
        new_default = pdef["default_url"]
        # Always set to default for fixed-URL providers; for editable providers
        # only replace if the field is empty or still holds another provider's default.
        is_other_default = any(
            old_url == PROVIDERS[p]["default_url"]
            for p in PROVIDER_ORDER
            if p != pid and PROVIDERS[p]["default_url"]
        )
        if not pdef["url_editable"] or not old_url or is_other_default:
            self._url_edit.setText(new_default)

        # Clear stale test result when provider changes
        self._conn_test_lbl.setText("")
        self._conn_test_lbl.setStyleSheet("")

        self._build_conn_form()

    def _build_conn_form(self):
        """Update connection form visibility for the current provider.
        Never removes or re-adds rows — only shows/hides them.
        This avoids the Wayland keyboard-grab bug caused by widget re-parenting.
        """
        pid  = self._current_provider_id()
        pdef = PROVIDERS[pid]

        # URL row — always visible, editable flag varies
        self._url_edit.setReadOnly(not pdef["url_editable"])
        self._url_edit.setStyleSheet(
            "color: gray;" if not pdef["url_editable"] else "")
        self._url_lbl.show()
        self._url_edit.show()

        # API key vs "no key" label
        if pdef["needs_api_key"]:
            self._key_lbl.show()
            self._key_edit.show()
            self._no_key_lbl_row_lbl.hide()
            self._no_key_lbl.hide()
        else:
            self._key_lbl.hide()
            self._key_edit.hide()
            self._no_key_lbl_row_lbl.show()
            self._no_key_lbl.show()

        # Azure extra fields
        show_dep = "azure_deployment" in pdef["extra_fields"]
        show_ver = "azure_api_version" in pdef["extra_fields"]
        self._azure_dep_lbl.setVisible(show_dep)
        self._azure_dep_edit.setVisible(show_dep)
        self._azure_ver_lbl.setVisible(show_ver)
        self._azure_ver_combo.setVisible(show_ver)

        # Provider notes
        notes = pdef.get("notes", "")
        self._prov_notes.setText(notes)
        self._prov_notes.setVisible(bool(notes))

    # ── System Prompts tab helpers ───────────────────────────────────

    def _sp_populate_combo(self, select_id=None):
        self.sp_combo.blockSignals(True)
        self.sp_combo.clear()
        self.sp_combo.addItem("— 选择一个提示词 —", userData=None)
        prompts = load_prompts()
        target_idx = 0
        for i, p in enumerate(prompts):
            self.sp_combo.addItem(p["title"], userData=p["id"])
            if p["id"] == select_id:
                target_idx = i + 1
        self.sp_combo.blockSignals(False)
        self.sp_combo.setCurrentIndex(target_idx)
        self._sp_on_select(target_idx)

        # Refresh the "Default for new chat" combo, preserving the selection
        current_default = (self.sp_default_combo.currentData()
                           if self.sp_default_combo.count() > 0
                           else self._sp_default_id)
        self.sp_default_combo.blockSignals(True)
        self.sp_default_combo.clear()
        self.sp_default_combo.addItem("— 无 —", userData=None)
        default_idx = 0
        for i, p in enumerate(prompts):
            self.sp_default_combo.addItem(p["title"], userData=p["id"])
            if p["id"] == current_default:
                default_idx = i + 1
        self.sp_default_combo.blockSignals(False)
        self.sp_default_combo.setCurrentIndex(default_idx)

    def _sp_on_select(self, idx):
        prompt_id = self.sp_combo.currentData()
        if prompt_id is None:
            self._sp_current_id = None
            self._sp_set_editor_enabled(False)
            self.sp_title_edit.blockSignals(True)
            self.sp_content_edit.blockSignals(True)
            self.sp_title_edit.clear()
            self.sp_content_edit.clear()
            self.sp_title_edit.blockSignals(False)
            self.sp_content_edit.blockSignals(False)
            self.sp_delete_btn.setEnabled(False)
        else:
            self._sp_current_id = prompt_id
            self.sp_delete_btn.setEnabled(True)
            from .system_prompts import get_prompt
            p = get_prompt(prompt_id)
            if p:
                self.sp_title_edit.blockSignals(True)
                self.sp_content_edit.blockSignals(True)
                self.sp_title_edit.setText(p["title"])
                self.sp_content_edit.setPlainText(p["content"])
                self.sp_title_edit.blockSignals(False)
                self.sp_content_edit.blockSignals(False)
                self._sp_orig_title   = p["title"]
                self._sp_orig_content = p["content"]
            self._sp_set_editor_enabled(True)
            self.sp_save_btn.setEnabled(False)  # not dirty yet

    def _sp_set_editor_enabled(self, enabled):
        # Use setReadOnly instead of setEnabled — setEnabled(False) on Wayland
        # can cause the widget to lose keyboard grab when re-enabled.
        self.sp_title_edit.setReadOnly(not enabled)
        self.sp_content_edit.setReadOnly(not enabled)
        # Save button is controlled by dirty tracking; only force-disable when
        # the fields are not editable at all.
        if not enabled:
            self.sp_save_btn.setEnabled(False)
        # Dim the fields visually when not editable
        style = "color: gray;" if not enabled else ""
        self.sp_title_edit.setStyleSheet(style)
        self.sp_content_edit.setStyleSheet(style)

    def _sp_mark_dirty(self):
        """Enable Save only when the content differs from the last-saved values."""
        if self.sp_title_edit.isReadOnly():
            return
        title   = self.sp_title_edit.text()
        content = self.sp_content_edit.toPlainText()
        dirty = (title != self._sp_orig_title or content != self._sp_orig_content)
        self.sp_save_btn.setEnabled(dirty)

    def _sp_on_new(self):
        self._sp_current_id = None
        self.sp_combo.blockSignals(True)
        self.sp_combo.setCurrentIndex(0)
        self.sp_combo.blockSignals(False)
        self.sp_title_edit.blockSignals(True)
        self.sp_content_edit.blockSignals(True)
        self.sp_title_edit.clear()
        self.sp_content_edit.clear()
        self.sp_title_edit.blockSignals(False)
        self.sp_content_edit.blockSignals(False)
        self._sp_orig_title   = ""
        self._sp_orig_content = ""
        self._sp_set_editor_enabled(True)
        self.sp_save_btn.setEnabled(False)
        self.sp_title_edit.setFocus()
        self.sp_delete_btn.setEnabled(False)

    def _sp_on_delete(self):
        prompt_id = self._sp_current_id
        if not prompt_id:
            return
        delete_prompt(prompt_id)
        self._sp_current_id = None
        self._sp_populate_combo()

    def _sp_on_save(self):
        title   = self.sp_title_edit.text().strip()
        content = self.sp_content_edit.toPlainText().strip()
        if not title:
            self.sp_title_edit.setPlaceholderText("⚠ Title is required")
            return
        if self._sp_current_id:
            update_prompt(self._sp_current_id, title, content)
            saved_id = self._sp_current_id
        else:
            p = new_prompt(title, content)
            saved_id = p["id"]
        self._sp_populate_combo(select_id=saved_id)

    # ── Commands tab helpers ─────────────────────────────────────────────

    def _cmd_populate_list(self):
        self._cmd_list.clear()
        for cmd in self._cmd_commands:
            self._cmd_list.addItem(f"/{cmd['name']}")

    def _cmd_set_editor_enabled(self, enabled):
        self._cmd_name_edit.setEnabled(enabled)
        self._cmd_prompt_edit.setEnabled(enabled)
        self._cmd_save_btn.setEnabled(False)  # controlled by dirty tracking
        self._cmd_delete_btn.setEnabled(bool(self._cmd_commands))

    def _cmd_mark_dirty(self):
        """Enable Save only when the content differs from the last-saved values."""
        name   = self._cmd_name_edit.text().strip().lstrip("/")
        prompt = self._cmd_prompt_edit.toPlainText()
        dirty = (name != self._cmd_orig_name or prompt != self._cmd_orig_prompt)
        self._cmd_save_btn.setEnabled(dirty and len(name) >= 2)

    def _refresh_agentic_preview(self):
        """Rebuild the read-only agentic prompt preview from the current UI state.

        Called on first expand of the preview panel and whenever any allow-checkbox
        or autonomous-mode control changes.  Guards against signals fired before
        the widget is fully constructed.
        """
        if not hasattr(self, "ag_prompt_preview"):
            return
        from .agentic_actions import build_agentic_system_prompt
        mode = ("full" if self.ag_mode_full.isChecked()
                else "off" if self.ag_mode_off.isChecked()
                else "semi")
        self.ag_prompt_preview.setPlainText(build_agentic_system_prompt({
            "allow_create_file":          self.ag_allow_create.isChecked(),
            "allow_run_console":          self.ag_allow_run.isChecked(),
            "allow_install":              self.ag_allow_install.isChecked(),
            "allow_patch":                self.ag_allow_patch.isChecked(),
            "allow_git":                  self.ag_allow_git.isChecked(),
            "allow_read":                 self.ag_allow_read.isChecked(),
            "allow_ls":                   self.ag_allow_ls.isChecked(),
            "allow_grep":                 self.ag_allow_grep.isChecked(),
            "allow_delete":               self.ag_allow_delete.isChecked(),
            "allow_delete_dir":           self.ag_allow_delete_dir.isChecked(),
            "allow_rename":               self.ag_allow_rename.isChecked(),
            "allow_rename_dir":           self.ag_allow_rename_dir.isChecked(),
            "autonomous_mode":            mode,
            "full_auto_confirm_modifying": self.ag_confirm_modifying.isChecked(),
        }))

    def _cmd_on_select(self, row):
        if 0 <= row < len(self._cmd_commands):
            self._cmd_current_idx = row
            cmd = self._cmd_commands[row]
            self._cmd_name_edit.blockSignals(True)
            self._cmd_prompt_edit.blockSignals(True)
            self._cmd_name_edit.setText(cmd["name"])
            self._cmd_prompt_edit.setPlainText(cmd["prompt"])
            self._cmd_name_edit.blockSignals(False)
            self._cmd_prompt_edit.blockSignals(False)
            self._cmd_orig_name   = cmd["name"]
            self._cmd_orig_prompt = cmd["prompt"]
            self._cmd_name_edit.setEnabled(True)
            self._cmd_prompt_edit.setEnabled(True)
            self._cmd_save_btn.setEnabled(False)  # not dirty yet
            self._cmd_delete_btn.setEnabled(True)
        else:
            self._cmd_current_idx = -1

    def _cmd_on_new(self):
        self._cmd_list.clearSelection()
        self._cmd_current_idx = -1
        self._cmd_name_edit.blockSignals(True)
        self._cmd_prompt_edit.blockSignals(True)
        self._cmd_name_edit.clear()
        self._cmd_prompt_edit.clear()
        self._cmd_name_edit.blockSignals(False)
        self._cmd_prompt_edit.blockSignals(False)
        self._cmd_orig_name   = ""
        self._cmd_orig_prompt = ""
        self._cmd_name_edit.setEnabled(True)
        self._cmd_prompt_edit.setEnabled(True)
        self._cmd_save_btn.setEnabled(False)
        self._cmd_name_edit.setFocus()

    def _cmd_on_delete(self):
        row = self._cmd_list.currentRow()
        if 0 <= row < len(self._cmd_commands):
            self._cmd_commands.pop(row)
            save_commands(self._cmd_commands)
            self._cmd_populate_list()
            self._cmd_name_edit.blockSignals(True)
            self._cmd_prompt_edit.blockSignals(True)
            self._cmd_name_edit.clear()
            self._cmd_prompt_edit.clear()
            self._cmd_name_edit.blockSignals(False)
            self._cmd_prompt_edit.blockSignals(False)
            self._cmd_orig_name   = ""
            self._cmd_orig_prompt = ""
            self._cmd_current_idx = -1
            self._cmd_set_editor_enabled(False)

    def _cmd_on_reset(self):
        """Restore built-in commands to default prompts; keep user-defined commands."""
        builtin_names = {c["name"] for c in DEFAULT_COMMANDS}
        # Keep any command whose name is NOT in the built-in set (user-defined)
        user_commands = [c for c in self._cmd_commands
                         if c["name"] not in builtin_names]
        # Rebuild: built-in defaults first, then user commands
        self._cmd_commands = list(DEFAULT_COMMANDS) + user_commands
        save_commands(self._cmd_commands)
        self._cmd_populate_list()
        self._cmd_name_edit.blockSignals(True)
        self._cmd_prompt_edit.blockSignals(True)
        self._cmd_name_edit.clear()
        self._cmd_prompt_edit.clear()
        self._cmd_name_edit.blockSignals(False)
        self._cmd_prompt_edit.blockSignals(False)
        self._cmd_orig_name   = ""
        self._cmd_orig_prompt = ""
        self._cmd_current_idx = -1
        self._cmd_set_editor_enabled(False)

    def _cmd_on_save(self):
        name = self._cmd_name_edit.text().strip().lstrip("/")
        prompt = self._cmd_prompt_edit.toPlainText().strip()
        if len(name) < 2:
            self._cmd_name_edit.setPlaceholderText("Name must be at least 2 characters")
            self._cmd_name_edit.setFocus()
            return
        if not prompt:
            self._cmd_prompt_edit.setPlaceholderText("Prompt cannot be empty")
            self._cmd_prompt_edit.setFocus()
            return
        if name in get_builtin_names():
            self._cmd_name_edit.setPlaceholderText(
                f"'{name}' is a reserved built-in command name")
            self._cmd_name_edit.clear()
            self._cmd_name_edit.setFocus()
            return
        for i, cmd in enumerate(self._cmd_commands):
            if cmd["name"] == name and i != self._cmd_current_idx:
                self._cmd_name_edit.setPlaceholderText(f"Name '{name}' already exists")
                self._cmd_name_edit.clear()
                self._cmd_name_edit.setFocus()
                return
        new_cmd = {"name": name, "prompt": prompt}
        if self._cmd_current_idx >= 0:
            self._cmd_commands[self._cmd_current_idx] = new_cmd
        else:
            self._cmd_commands.append(new_cmd)
            self._cmd_current_idx = len(self._cmd_commands) - 1
        save_commands(self._cmd_commands)
        saved_idx = self._cmd_current_idx
        self._cmd_populate_list()
        self._cmd_list.setCurrentRow(saved_idx)
        # _cmd_on_select resets originals and disables save via currentRowChanged

    # ── Auto-complete tab helpers ─────────────────────────────────────────

    def _fim_set_state(self, state):
        """state: 'disabled' | 'provider_only' | 'loading' | 'ready'"""
        is_on      = state != "disabled"
        is_ready   = state == "ready"
        is_loading = state == "loading"

        # Provider connection widgets — enabled when checkbox is on and not loading
        for w in (self.fim_provider_combo, self.fim_url_edit,
                  self.fim_key_edit, self.fim_load_btn):
            w.setEnabled(is_on and not is_loading)

        # Model + backend — only when models have been loaded
        self.fim_model_combo.setEnabled(is_ready)
        self.fim_backend_combo.setEnabled(is_ready)

        # Params and trigger groups
        self._fim_param_group.setEnabled(is_ready)
        self._fim_trig_group.setEnabled(is_ready)

        if state == "loading":
            self.fim_load_btn.setText("加载中…")
            self._fim_spinner_timer.start()
        else:
            self._fim_spinner_timer.stop()
            self.fim_load_btn.setText("加载模型")

        if state == "disabled":
            self.fim_status_lbl.setText("")
            self.fim_status_lbl.setStyleSheet("")
        elif state == "provider_only":
            if not self.fim_status_lbl.text():
                self.fim_status_lbl.setText("点击'加载模型'进行连接")
                self.fim_status_lbl.setStyleSheet("")

    def _fim_on_enabled_toggled(self, checked):
        if checked:
            has_model = bool(self.fim_model_combo.currentText().strip())
            self._fim_set_state("ready" if has_model else "provider_only")
        else:
            self._fim_set_state("disabled")

    def _fim_on_provider_changed(self, _idx):
        pid = self.fim_provider_combo.currentData()
        default_url = _FIM_PROVIDER_URLS.get(pid, "")
        if default_url:
            self.fim_url_edit.setText(default_url)
        # Reset — require re-loading models for the new provider
        self.fim_model_combo.clear()
        self.fim_status_lbl.setText("点击'加载模型'进行连接")
        self.fim_status_lbl.setStyleSheet("")
        if self.fim_enabled.isChecked():
            self._fim_set_state("provider_only")

    def _fim_load_models(self):
        url = self.fim_url_edit.text().strip()
        if not url:
            self.fim_status_lbl.setText("⚠ 请先输入 API URL")
            self.fim_status_lbl.setStyleSheet("color: orange;")
            return
        # Stop any previous loader
        if self._fim_loader is not None:
            self._fim_loader.quit()
            self._fim_loader.wait(500)
        self._fim_status_msg = "连接中…"
        self._fim_set_state("loading")
        loader = _FimLoader(
            url, self.fim_key_edit.text().strip(),
            self.fim_provider_combo.currentData(), parent=self)
        loader.sig_status.connect(self._fim_on_status)
        loader.sig_models.connect(self._fim_on_models)
        loader.sig_backends.connect(self._fim_on_backends)
        loader.sig_error.connect(self._fim_on_load_error)
        loader.finished.connect(self._fim_on_load_finished)
        self._fim_loader = loader
        loader.start()

    def _fim_spinner_tick(self):
        self._fim_spinner_idx = (
            (self._fim_spinner_idx + 1) % len(self._fim_spinner_frames))
        frame = self._fim_spinner_frames[self._fim_spinner_idx]
        self.fim_status_lbl.setText(f"{frame}  {self._fim_status_msg}")
        self.fim_status_lbl.setStyleSheet("")

    def _fim_on_status(self, msg):
        self._fim_status_msg = msg
        self.fim_status_lbl.setStyleSheet("")
        if not self._fim_spinner_timer.isActive():
            self.fim_status_lbl.setText(msg)

    def _fim_on_models(self, models):
        current = self.fim_model_combo.currentText()
        self.fim_model_combo.clear()
        for m in models:
            self.fim_model_combo.addItem(m)
        # Restore previously selected model if present
        idx = self.fim_model_combo.findText(current)
        if idx >= 0:
            self.fim_model_combo.setCurrentIndex(idx)

    def _fim_on_backends(self, backends):
        current_key = self.fim_backend_combo.currentData()
        self.fim_backend_combo.clear()
        for k, label in backends:
            self.fim_backend_combo.addItem(label, userData=k)
        idx = self.fim_backend_combo.findData(current_key)
        if idx >= 0:
            self.fim_backend_combo.setCurrentIndex(idx)

    def _fim_on_load_error(self, msg):
        self._fim_spinner_timer.stop()   # stop before setting text — prevents overwrite
        self.fim_status_lbl.setText(f"✗ {msg}")
        self.fim_status_lbl.setStyleSheet("color: red;")

    def _fim_on_load_finished(self):
        # _fim_set_state stops the spinner timer
        if self.fim_model_combo.count() > 0:
            n = self.fim_model_combo.count()
            self._fim_set_state("ready")
            self.fim_status_lbl.setText(f"✓ 已加载 {n} 个模型")
            self.fim_status_lbl.setStyleSheet("color: green;")
        else:
            # Error already shown by _fim_on_load_error; just restore state
            self._fim_set_state("provider_only")

    def values(self):
        """Return all settings as a dict ready to pass to _save_state."""
        pid = self._current_provider_id()
        return {
            "provider_type":       pid,
            "api_url":             self._url_edit.text().strip(),
            "api_key":             self._key_edit.text().strip(),
            "azure_deployment":    self._azure_dep_edit.text().strip(),
            "azure_api_version":   self._azure_ver_combo.currentText(),
            "editor": {
                "fs_ui":      self.fs_ui.value(),
                "fs_base":    self.fs_base.value(),
                "fs_code":    self.fs_code.value(),
                "fs_heading": self.fs_heading.value(),
                "fs_list":    self.fs_list.value(),
                "fs_table":   self.fs_table.value(),
                "fs_think":   self.fs_think.value(),
            },
            "history": {
                "autosave":              self.cb_autosave.isChecked(),
                "save_on_new":           self.cb_save_on_new.isChecked(),
                "proj_max_file_kb":      self.sp_proj_max_kb.value(),
                "proj_max_files":        self.sp_proj_max_files.value(),
                "proj_extra_exclusions":  self.te_proj_exclusions.toPlainText(),
                "proj_reset_on_new_chat": self.chk_proj_reset_on_new.isChecked(),
                "show_git_bar":           self.chk_show_git_bar.isChecked(),
                "git_poll_interval":      self.sp_git_poll.value(),
                "compaction_enabled":       self.chk_compaction_enabled.isChecked(),
                "compaction_strategy":      ("llm" if self.rb_co_llm.isChecked()
                                             else "cutoff"),
                "compaction_threshold_pct": self.sp_compaction_threshold.value(),
                "compaction_default_limit": self.sp_compaction_default.value(),
                "compaction_model_limits":  _read_compaction_table(self.compaction_table),
            },
            "default_system_prompt_id": self.sp_default_combo.currentData(),
            "commands": self._cmd_commands,
            "agentic": {
                "enabled":           self.ag_enabled.isChecked(),
                "allow_create_file": self.ag_allow_create.isChecked(),
                "allow_run_console": self.ag_allow_run.isChecked(),
                "allow_install":     self.ag_allow_install.isChecked(),
                "allow_patch":       self.ag_allow_patch.isChecked(),
                "allow_git":         self.ag_allow_git.isChecked(),
                "allow_read":        self.ag_allow_read.isChecked(),
                "allow_ls":          self.ag_allow_ls.isChecked(),
                "allow_grep":        self.ag_allow_grep.isChecked(),
                "allow_delete":      self.ag_allow_delete.isChecked(),
                "allow_delete_dir":  self.ag_allow_delete_dir.isChecked(),
                "allow_rename":      self.ag_allow_rename.isChecked(),
                "allow_rename_dir":  self.ag_allow_rename_dir.isChecked(),
                "base_path":               self.ag_base_path.text().strip(),
                "autonomous_mode":         ("full" if self.ag_mode_full.isChecked()
                                            else "off" if self.ag_mode_off.isChecked()
                                            else "semi"),
                "full_auto_confirm_modifying": self.ag_confirm_modifying.isChecked(),
            },
            "fim": {
                "enabled":       self.fim_enabled.isChecked(),
                "provider":      self.fim_provider_combo.currentData(),
                "api_url":       self.fim_url_edit.text().strip(),
                "api_key":       self.fim_key_edit.text().strip(),
                "model":         self.fim_model_combo.currentText().strip(),
                "models":        [self.fim_model_combo.itemText(i)
                                  for i in range(self.fim_model_combo.count())],
                "backend_type":  self.fim_backend_combo.currentData(),
                "backends":      [[self.fim_backend_combo.itemData(i),
                                   self.fim_backend_combo.itemText(i)]
                                  for i in range(self.fim_backend_combo.count())],
                "max_tokens":    self.fim_max_tokens.value(),
                "temperature":   self.fim_temperature.value(),
                "context_before":self.fim_ctx_before.value(),
                "context_after": self.fim_ctx_after.value(),
                "trigger_mode":  self.fim_trigger_combo.currentData(),
                "debounce_ms":   self.fim_debounce.value(),
            },
        }
