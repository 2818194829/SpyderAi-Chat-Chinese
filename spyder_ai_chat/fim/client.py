# -*- coding: utf-8 -*-
"""
AI FIM Completion – HTTP client worker.

A QThread subclass that performs a single FIM HTTP request and emits the
result (or an error) via Qt signals.  The caller discards the worker if
a newer request supersedes it before the response arrives.

Supported backends
------------------
* ollama_generate    – POST /api/generate  (Ollama native, uses prompt+suffix)
* openai_completions – POST /v1/completions (OpenAI-compat legacy endpoint)
* codestral          – POST /v1/fim/completions (Mistral/Codestral)
* chat               – POST /v1/chat/completions (chat-based FIM fallback)

(C) 2026 Maciej Piecko
"""

import json
import logging
import urllib.error
import urllib.request

from qtpy.QtCore import QThread, Signal

from .config import get_fim_template, get_stop_tokens

logger = logging.getLogger(__name__)


class FimWorker(QThread):
    """
    One-shot thread: build payload → HTTP POST → emit result.

    Signals
    -------
    sig_result(int, str)
        Emitted on success.  First arg is the req_id, second is the
        completion text (may be empty if the model returned nothing useful).
    sig_error(int, str)
        Emitted on any error.  First arg is req_id, second is the message.
    """

    sig_result = Signal(object, str)   # req_id may be None for manual triggers
    sig_error  = Signal(object, str)

    # ------------------------------------------------------------------
    def __init__(
        self,
        req_id:       int,
        prefix:       str,
        suffix:       str,
        api_url:      str,
        api_key:      str,
        model:        str,
        backend_type: str,
        max_tokens:   int   = 128,
        temperature:  float = 0.0,
        parent=None,
    ):
        super().__init__(parent)
        self.req_id       = req_id
        self.prefix       = prefix
        self.suffix       = suffix
        self.api_url      = api_url.rstrip("/")
        self.api_key      = api_key
        self.model        = model
        self.backend_type = backend_type
        self.max_tokens   = max_tokens
        self.temperature  = temperature
        self._cancelled   = False

    # ------------------------------------------------------------------
    def cancel(self):
        """Mark this worker as superseded; result will be silently dropped."""
        self._cancelled = True

    # ------------------------------------------------------------------
    def run(self):
        try:
            text = self._do_request()
            if not self._cancelled:
                self.sig_result.emit(self.req_id, text)
        except Exception as exc:
            if not self._cancelled:
                self.sig_error.emit(self.req_id, str(exc))

    # ------------------------------------------------------------------
    # Backend dispatch
    # ------------------------------------------------------------------
    def _do_request(self) -> str:
        bt = self.backend_type
        if bt == "ollama_generate":
            return self._call_ollama()
        elif bt == "openai_completions":
            return self._call_openai_completions()
        elif bt == "codestral":
            return self._call_codestral()
        elif bt == "chat":
            return self._call_chat()
        else:
            raise ValueError(f"Unknown backend_type: {bt!r}")

    # ------------------------------------------------------------------
    # Backend A – Ollama /api/generate
    # ------------------------------------------------------------------
    def _call_ollama(self) -> str:
        url = f"{self.api_url}/api/generate"
        payload = {
            "model":  self.model,
            "prompt": self.prefix,
            "suffix": self.suffix,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
                "stop":        get_stop_tokens(self.model),
            },
        }
        data = self._post(url, payload)
        return (data.get("response") or "").strip()

    # ------------------------------------------------------------------
    # Backend B – OpenAI-compatible /v1/completions  (legacy endpoint)
    # ------------------------------------------------------------------
    def _call_openai_completions(self) -> str:
        url = f"{self.api_url}/v1/completions"
        payload = {
            "model":       self.model,
            "prompt":      self.prefix,
            "suffix":      self.suffix,
            "max_tokens":  self.max_tokens,
            "temperature": self.temperature,
            "stream":      False,
            "stop":        get_stop_tokens(self.model),
        }
        data = self._post(url, payload)
        try:
            return (data["choices"][0]["text"] or "").strip()
        except (KeyError, IndexError):
            return ""

    # ------------------------------------------------------------------
    # Backend C – Codestral /v1/fim/completions
    # ------------------------------------------------------------------
    def _call_codestral(self) -> str:
        url = f"{self.api_url}/v1/fim/completions"
        payload = {
            "model":       self.model,
            "prompt":      self.prefix,
            "suffix":      self.suffix,
            "max_tokens":  self.max_tokens,
            "temperature": self.temperature,
        }
        data = self._post(url, payload)
        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError):
            return ""

    # ------------------------------------------------------------------
    # Backend D – Chat completions (FIM prompt injection, last resort)
    # ------------------------------------------------------------------
    def _call_chat(self) -> str:
        url = f"{self.api_url}/v1/chat/completions"
        fim_template = get_fim_template(self.model)
        if "{suffix}" in fim_template and "{prefix}" in fim_template:
            combined = fim_template.format(
                prefix=self.prefix, suffix=self.suffix
            )
        else:
            # Generic chat FIM instruction
            combined = (
                "Complete the code at the <FILL> marker. "
                "Return only the inserted code with no explanation.\n\n"
                f"<PREFIX>\n{self.prefix}\n</PREFIX>\n"
                f"<FILL>\n"
                f"<SUFFIX>\n{self.suffix}\n</SUFFIX>"
            )
        payload = {
            "model":       self.model,
            "max_tokens":  self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {"role": "user", "content": combined},
            ],
        }
        data = self._post(url, payload)
        try:
            content = data["choices"][0]["message"]["content"] or ""
            # Strip any markdown code fences the model might have added
            content = _strip_code_fences(content)
            return content.strip()
        except (KeyError, IndexError):
            return ""

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------
    def _post(self, url: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, data=body, headers=headers,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            body_text = ""
            try:
                body_text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(
                f"HTTP {exc.code} from {url}: {body_text[:200]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc

        return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def _strip_code_fences(text: str) -> str:
    """Remove leading/trailing ``` or ```python fences if present."""
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)
