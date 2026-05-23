# -*- coding: utf-8 -*-
"""
AI FIM Completion – SpyderCompletionProvider implementation.
(C) 2026 Maciej Piecko

Key lessons from working provider reference:
- Empty/skip responses MUST be {"params": []} — not {} or None.
  Using {} or None causes Spyder's aggregator to crash LSP handlers.
- DID_OPEN / DID_CHANGE / DID_CLOSE must be handled (responded to).
- Context is extracted using req["offset"] directly, not line+column.
- Document text is tracked via DID_OPEN/DID_CHANGE for accurate prefix/suffix.
"""

import logging

from qtpy.QtCore import QTimer, Signal

from spyder.plugins.completion.api import (
    CompletionRequestTypes,
    SpyderCompletionProvider,
)

from .client import FimWorker

logger = logging.getLogger(__name__)

# Shorthand constants
_COMPLETION = CompletionRequestTypes.DOCUMENT_COMPLETION
_DID_OPEN   = CompletionRequestTypes.DOCUMENT_DID_OPEN
_DID_CHANGE = CompletionRequestTypes.DOCUMENT_DID_CHANGE
_DID_CLOSE  = CompletionRequestTypes.DOCUMENT_DID_CLOSE

# The correct empty response — anything else breaks Spyder's aggregator
# The only empty response we ever emit — for DOCUMENT_COMPLETION skips.
_EMPTY_LIST = {"params": []}

# Module-level reference so plugin.py can connect signals without
# searching through Spyder's internal provider registry.
_INSTANCE = None




class AiFimProvider(SpyderCompletionProvider):
    """
    FIM completion provider registered via the spyder.completions entry-point.
    Configuration is stored in the "ai_chat_plugin" section of Spyder's config
    (same section as the chat plugin) under fim_* prefixed keys, and is
    edited via the ⚡ FIM tab in the AI Chat settings dialog (⚙ button).
    """

    # Signal emitted when a completion is ready for ghost text display.
    # (filename, completion_text, target_dict)
    sig_ghost_text_ready = Signal(str, str, dict)

    COMPLETION_PROVIDER_NAME = "ai_fim_provider"
    DEFAULT_ORDER             = 2       # after LSP (1), before fallback (3)
    SLOW                      = True    # network-bound
    CONF_SECTION              = "ai_chat_plugin"
    CONF_VERSION              = "1.0.0"

    # Flat list of (key, default) — required format for completion providers
    CONF_DEFAULTS = [
        ("fim_enabled",           False),
        ("fim_api_url",           "http://localhost:11434"),
        ("fim_api_key",           ""),
        ("fim_model",             "qwen2.5-coder:7b"),
        ("fim_backend_type",      "ollama_generate"),
        ("fim_max_tokens",        128),
        ("fim_temperature_x10",   0),
        ("fim_context_before",    4000),
        ("fim_context_after",     1000),
        ("fim_trigger_mode",      "auto"),
        ("fim_debounce_ms",       150),
    ]

    # ------------------------------------------------------------------
    def __init__(self, parent, config):
        super().__init__(parent, config)
        global _INSTANCE
        _INSTANCE = self
        self._started        = False
        self._pending_worker = None   # FimWorker | None
        self._pending_req_id = None
        self._pending_target: dict = {}  # target dict for the in-flight request
        self._queued         = None   # {req, req_id, target} to fire after debounce
        self._document_texts = {}     # filename → str  (tracked via DID_OPEN/CHANGE)
        self._get_editor_text_fn = None  # set by plugin: fn(filename) -> str

        self._get_cursor_offset_fn = None  # set by plugin: fn(filename) -> int

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._fire_pending)

    # ------------------------------------------------------------------
    # SpyderCompletionProvider API
    # ------------------------------------------------------------------
    def get_name(self):
        return "AI FIM Completion"

    def start(self):
        logger.debug("AiFimProvider.start()")
        self._started = True
        self.sig_provider_ready.emit(self.COMPLETION_PROVIDER_NAME)

    def shutdown(self):
        logger.debug("AiFimProvider.shutdown()")
        self._started = False
        self._debounce_timer.stop()
        self._cancel_pending()
        self._document_texts.clear()

    def start_completion_services_for_language(self, language):
        # When Spyder calls this, it updates language_status[language]["ai_fim_provider"].
        # This is the gate that controls whether send_notification reaches us.
        # Returning True here ensures DID_CHANGE notifications flow to our provider
        # for this language going forward.
        logger.debug("start_completion_services_for_language: %s -> %s",
                     language, self._started)
        return self._started

    def can_close(self):
        return True

    # ------------------------------------------------------------------
    def send_notification(self, language, notification_type, notification):
        """Handle document lifecycle notifications (DID_OPEN/CHANGE/CLOSE)."""
        filename = notification.get("file", "")

        if not filename:
            return
        if notification_type in (_DID_OPEN, _DID_CHANGE):
            text = notification.get("text", "")
            self._document_texts[filename] = text

            logger.debug("%s tracked %s (%d chars)",
                         notification_type, filename, len(text))
        elif notification_type == _DID_CLOSE:
            self._document_texts.pop(filename, None)
            logger.debug("DID_CLOSE removed %s", filename)

    def send_request(self, language, req_type, req, req_id=None):
        # ── Document tracking (DID_OPEN/CHANGE/CLOSE via send_request) ─
        if req_type in (_DID_OPEN, _DID_CHANGE):
            filename = req.get("file", "")
            text = req.get("text", "")
            if filename and text:
                self._document_texts[filename] = text
            return

        if req_type == _DID_CLOSE:
            self._document_texts.pop(req.get("file", ""), None)
            return

        # ── Completion request ─────────────────────────────────────────
        if req_type == _COMPLETION:
            self._handle_completion(req, req_id)
            return

        # ── All other request types (signatures, hover, symbols, etc.) ─
        # Do NOT respond — Spyder's aggregator skips us via timeout.

    # ------------------------------------------------------------------
    # Completion handling
    # ------------------------------------------------------------------
    def _handle_completion(self, req, req_id, force=False):
        """Handle a completion request.
        force=True bypasses trigger_mode and debounce (Alt+Backslash manual trigger).
        req_id may be None for manual triggers (no Spyder request to satisfy).
        """
        if not self._fim_conf("fim_enabled", False):
            if req_id is not None: self._emit_empty(req_id)
            return

        prefix, suffix = self._extract_context(req)
        if not prefix.strip():
            if req_id is not None: self._emit_empty(req_id)
            return

        if self._cursor_in_string_or_comment(prefix):
            if req_id is not None: self._emit_empty(req_id)
            return

        if not force:
            trigger_mode = self._fim_conf("fim_trigger_mode", "auto")
            if trigger_mode == "manual":
                if req_id is not None: self._emit_empty(req_id)
                return
            if trigger_mode == "newline_only":
                if not prefix.rstrip(" \t").endswith("\n"):
                    if req_id is not None: self._emit_empty(req_id)
                    return

        filename = req.get("file", "")
        offset   = int(req.get("offset", 0))
        target   = {"filename": filename,
                    "offset":   offset,
                    "line":     int(req.get("line", 0)),
                    "column":   int(req.get("column", 0))}
        # Store req so _fire_pending can re-extract context with live cursor offset
        self._queued = dict(req=req, req_id=req_id, target=target)
        self._debounce_timer.stop()
        if force:
            self._fire_pending()   # immediate — no debounce
        else:
            self._debounce_timer.start(int(self._fim_conf("fim_debounce_ms", 150)))

    def _fire_pending(self):
        if self._queued is None:
            return
        args = self._queued
        self._queued = None
        self._cancel_pending()

        req    = args["req"]
        target = args.get("target", {})

        # Refresh cursor offset — user may have typed more during debounce.
        # _document_texts is already up-to-date via DID_CHANGE; we only need
        # to re-sample where the cursor currently sits so the prefix/suffix
        # split is at the actual cursor position, not the stale request offset.
        # The plugin returns (line, col) rather than a raw position so we can
        # compute the correct offset in _document_texts regardless of whether
        # the stored text uses \r\n or \n line endings.
        if self._get_cursor_offset_fn is not None:
            try:
                result = self._get_cursor_offset_fn(req.get("file", ""))
                if result is not None:
                    line, col = result
                    text = self._document_texts.get(req.get("file", ""), "")
                    live_offset = self._line_col_to_offset(text, line, col)
                    req    = dict(req)
                    req["offset"] = live_offset
                    target = dict(target)
                    target["offset"] = live_offset
                    target["line"]   = line
                    target["column"] = col
            except Exception:
                logger.debug("Failed to get live cursor offset", exc_info=True)

        prefix, suffix = self._extract_context(req)
        if not prefix.strip():
            req_id = args["req_id"]
            if req_id is not None:
                self._emit_empty(req_id)
            return

        cfg = self._read_fim_config()
        self._pending_target   = target
        worker = FimWorker(
            req_id       = args["req_id"],
            prefix       = prefix,
            suffix       = suffix,
            api_url      = cfg["api_url"],
            api_key      = cfg["api_key"],
            model        = cfg["model"],
            backend_type = cfg["backend_type"],
            max_tokens   = cfg["max_tokens"],
            temperature  = cfg["temperature"],
            parent       = self,
        )
        worker.sig_result.connect(self._on_result)
        worker.sig_error.connect(self._on_error)
        self._pending_worker  = worker
        self._pending_req_id  = args["req_id"]
        worker.start()

    def _cancel_pending(self):
        if self._pending_worker is not None:
            self._pending_worker.cancel()
            self._pending_worker = None
            self._pending_req_id = None

    def _on_result(self, req_id, text):
        self._pending_worker = None
        self._pending_req_id = None
        # Emit ghost text FIRST — before satisfying the aggregator.
        # _emit_empty() can raise if Spyder's aggregator has already timed out
        # or discarded the req_id (common when LLM response is slow).  Placing
        # sig_ghost_text_ready first ensures the ghost text always reaches the
        # editor regardless of aggregator state.
        if text:
            target   = self._pending_target
            filename = target.get("filename", "")
            self.sig_ghost_text_ready.emit(filename, text, target)
        # Satisfy Spyder's aggregator — wrapped so any exception (stale req_id,
        # aggregator API change, None req_id on manual trigger) doesn't crash
        # the completion system.
        if req_id is not None:
            try:
                self._emit_empty(req_id)
            except Exception:
                logger.debug("_emit_empty failed for req_id=%r", req_id,
                             exc_info=True)

    def _on_error(self, req_id, msg):
        self._pending_worker = None
        self._pending_req_id = None
        logger.warning("AiFimProvider error req %r: %s", req_id, msg)
        if req_id is not None:
            try:
                self._emit_empty(req_id)
            except Exception:
                logger.debug("_emit_empty failed for req_id=%r", req_id,
                             exc_info=True)

    # ------------------------------------------------------------------
    # Context extraction — use req["offset"] directly (like the reference)
    # ------------------------------------------------------------------
    def _extract_context(self, req):
        ctx_before = int(self._fim_conf("fim_context_before", 4000))
        ctx_after  = int(self._fim_conf("fim_context_after",  1000))

        filename = req.get("file", "")
        offset   = int(req.get("offset", 0))

        # 1. Use tracked document text (updated via DID_OPEN / DID_CHANGE)
        text = self._document_texts.get(filename, "")

        # 2. If offset exceeds tracked text, use live editor text.
        #    This happens when didChange and the completion request arrive
        #    in the same event loop tick — didChange updates _document_texts
        #    but the completion offset already reflects the new text length.
        if offset > len(text) and self._get_editor_text_fn is not None:
            try:
                live = self._get_editor_text_fn(filename)
                if live and len(live) >= offset:
                    text = live
                    self._document_texts[filename] = live
                    logger.debug("Used live editor text (%d chars) for %s",
                                 len(live), filename)
            except Exception:
                logger.debug("Failed to get live editor text for %s", filename,
                             exc_info=True)

        if text:
            offset = max(0, min(offset, len(text)))
            prefix = text[:offset]
            suffix = text[offset:]
        else:
            # 4. Last resort: reconstruct from code field + line/column
            code   = req.get("code", "")
            line   = int(req.get("line", 0))
            col    = int(req.get("column", 0))
            lines  = code.splitlines(keepends=True)
            off    = sum(len(l) for l in lines[:line])
            off   += min(col, len(lines[line]) if line < len(lines) else 0)
            prefix = code[:off]
            suffix = code[off:]

        prefix = prefix[-ctx_before:] if len(prefix) > ctx_before else prefix
        suffix = suffix[:ctx_after]   if len(suffix) > ctx_after  else suffix
        return prefix, suffix

    @staticmethod
    def _line_col_to_offset(text, line, col):
        """Convert 0-based (line, col) to a character offset in text.

        Works correctly whether text uses \\r\\n, \\n, or \\r line endings.
        Qt's blockNumber/columnNumber are in the \\n-normalised view, but
        splitlines(keepends=True) matches Qt's block boundaries, so summing
        the raw (\\r\\n-including) lengths of preceding lines gives the right
        offset in the stored document text.
        """
        lines = text.splitlines(keepends=True)
        offset = sum(len(l) for l in lines[:line])
        if line < len(lines):
            content_len = len(lines[line].rstrip('\r\n'))
            offset += min(col, content_len)
        return offset

    # ------------------------------------------------------------------
    # Heuristic: skip inside strings / comments
    # ------------------------------------------------------------------
    @staticmethod
    def _cursor_in_string_or_comment(prefix):
        """Return True only if the cursor is mid-string (unclosed quote).
        Comment detection removed — FIM completions after a comment line
        (e.g. '# do X\ndef ') are valid and useful.
        """
        if not prefix:
            return False
        last_nl      = prefix.rfind("\n")
        current_line = prefix[last_nl + 1:]
        if current_line.count("'") % 2 == 1:
            return True
        if current_line.count('"') % 2 == 1:
            return True
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _emit_empty(self, req_id):
        """Emit an empty completion response — only used for DOCUMENT_COMPLETION
        skips where {"params": []} is the correct payload."""
        self.sig_response_ready.emit(
            self.COMPLETION_PROVIDER_NAME, req_id, _EMPTY_LIST)

    def _fim_conf(self, key, default=None):
        """Read a fim_ config key from state.json.

        The settings dialog writes all FIM settings to state.json under the
        "fim" key (without the "fim_" prefix). We read directly from there
        instead of get_conf(), because get_conf() would return the CONF_DEFAULTS
        value (always True/default) since the dialog never writes to Spyder's
        config system.
        """
        state_key = key.replace("fim_", "")
        return self._load_state_json().get("fim", {}).get(state_key, default)

    @staticmethod
    def _load_state_json():
        import json, os
        path = os.path.join(
            os.path.expanduser("~"), ".spyder_ai_chat", "state.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.debug("Failed to load state.json from %s", path, exc_info=True)
            return {}

    def _read_fim_config(self):
        fim = self._load_state_json().get("fim", {})
        return {
            "api_url":      fim.get("api_url",      "http://localhost:11434"),
            "api_key":      fim.get("api_key",      ""),
            "model":        fim.get("model",         "qwen2.5-coder:7b"),
            "backend_type": fim.get("backend_type",  "ollama_generate"),
            "max_tokens":   int(fim.get("max_tokens",   128)),
            "temperature":  float(fim.get("temperature", 0.0)),
        }
