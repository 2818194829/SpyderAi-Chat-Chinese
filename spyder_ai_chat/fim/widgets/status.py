# -*- coding: utf-8 -*-
"""
AI FIM Completion – status bar indicator widget.

Shows a small ⚡ icon in Spyder's status bar that cycles through three
states: idle, busy (request in flight), error.

Usage
-----
The provider creates one instance and updates it via ``set_state()``:

    status = FimStatusWidget(parent=main_window)
    status.set_state("idle")   # ⚡ AI FIM
    status.set_state("busy")   # ⚡ AI FIM …
    status.set_state("error")  # ⚡ AI FIM ✗

(C) 2026 Maciej Piecko
"""

from qtpy.QtWidgets import QLabel


class FimStatusWidget(QLabel):
    """Tiny status bar label for the FIM provider."""

    _TEXTS = {
        "idle":  "⚡ AI 补全",
        "busy":  "⚡ AI 补全 …",
        "error": "⚡ AI 补全 ✗",
        "off":   "",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("font-size: 11px; padding: 0 4px;")
        self.set_state("idle")

    def set_state(self, state: str):
        """Update label text.  state ∈ {'idle','busy','error','off'}."""
        self.setText(self._TEXTS.get(state, ""))
        if state == "error":
            self.setStyleSheet(
                "font-size: 11px; padding: 0 4px; color: #cc4444;")
        elif state == "busy":
            self.setStyleSheet(
                "font-size: 11px; padding: 0 4px; color: #888800;")
        else:
            self.setStyleSheet("font-size: 11px; padding: 0 4px;")
