# -*- coding: utf-8 -*-
"""AI Chat Panel — Spyder 6 plugin (C) 2026 by Maciej Piecko"""

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

from qtpy.QtCore import Qt, Signal, Slot, QEvent, QObject, QThread, QTimer
from qtpy.QtGui import QFont, QTextCursor, QTextCharFormat, QColor
from qtpy.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QFrame, QPlainTextEdit, QPushButton, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget, QSizePolicy, QToolButton, QStyle, QScrollArea,
    QSpinBox, QSplitter,
)
from qtpy.QtCore import QFileSystemWatcher

from .chat_history_manager import (
    save_chat, load_chat, delete_chat, list_chats, search_chats,
    list_collections, move_chat,
)
from .collection_manager import ChatCollectionManagerDialog
from .commands import load_commands, save_commands, get_command_prompt

DEFAULT_MODELS = [
    "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo",
    "llama3", "mistral", "codellama", "phi3",
]


def _find_main_window():
    """Return Spyder's visible MainWindow, or None if not found."""
    try:
        return next(
            (w for w in QApplication.topLevelWidgets()
             if w.isVisible() and "MainWindow" in type(w).__name__),
            None,
        )
    except Exception:
        return None


def _is_dark_theme():
    """Return True when the application is running in a dark colour scheme."""
    try:
        from spyder.config.gui import is_dark_interface
        return is_dark_interface()
    except Exception:
        pass
    try:
        from qtpy.QtGui import QPalette
        bg = QApplication.instance().palette().color(QPalette.Window)
        lum = (bg.red() * 299 + bg.green() * 587 + bg.blue() * 114) // 1000
        return lum < 128
    except Exception:
        return True   # safe default


def _agentic_action_labels(executed: list) -> list:
    """Convert an agentic_executed list to de-duplicated human-readable labels.

    Each element of *executed* is a dict with at least a ``"type"`` key.
    Duplicate types (same fence used twice in one response) are shown once.
    """
    _TYPE_LABELS = {
        "read":       "读取文件",
        "ls":         "列出目录",
        "grep":       "搜索文件",
        "git":        "Git 命令",
        "file":       "创建文件",
        "patch":      "应用补丁",
        "delete":     "删除文件",
        "delete_dir": "删除目录",
        "rename":     "重命名文件",
        "rename_dir": "重命名目录",
        "install":    "安装包",
        "run":        "在控制台运行",
    }
    seen = []
    for e in executed:
        lbl = _TYPE_LABELS.get(e.get("type", ""), e.get("type", "Action"))
        if lbl not in seen:
            seen.append(lbl)
    return seen


# Styles for the inference params summary bar label — called at apply time
def _params_bar_idle_style():
    if _is_dark_theme():
        return ("QPushButton { color: #aaa; font-size: 9px; text-align: left; "
                "border: none; padding: 0 4px; }"
                "QPushButton:hover { color: #eee; }")
    else:
        return ("QPushButton { color: #444; font-size: 9px; text-align: left; "
                "border: none; padding: 0 4px; }"
                "QPushButton:hover { color: #111; }")

def _params_bar_active_style():
    if _is_dark_theme():
        return ("QPushButton { color: #c8a000; font-size: 9px; text-align: left; "
                "border: none; padding: 0 4px; }"
                "QPushButton:hover { color: #ffe080; }")
    else:
        return ("QPushButton { color: #7a5000; font-size: 9px; text-align: left; "
                "border: none; padding: 0 4px; }"
                "QPushButton:hover { color: #4a3000; }")

# Context-size button styles — computed at call time via _ctx_size_style()
# so they respect the active theme.
def _ctx_size_style(level="normal"):
    """Return the stylesheet for the context-size button at the given level."""
    if _is_dark_theme():
        popup_ss = (
            "QToolTip { background: #1e2a1e; color: #d0d0d0; "
            "border: 1px solid #4a6a4a; padding: 6px; font-size: 10px; }")
        fg   = {"normal": "#e0e0e0", "warn": "#c8a000", "error": "#ff5555"}[level]
        fgh  = {"normal": "#ffffff",  "warn": "#ffe080", "error": "#ff8888"}[level]
    else:
        popup_ss = (
            "QToolTip { background: #f0f8f0; color: #333333; "
            "border: 1px solid #80a880; padding: 6px; font-size: 10px; }")
        fg   = {"normal": "#333333", "warn": "#9a7000", "error": "#cc0000"}[level]
        fgh  = {"normal": "#000000",  "warn": "#7a5000", "error": "#aa0000"}[level]
    return (
        f"QPushButton {{ color: {fg}; font-size: 9px; text-align: right; "
        "border: none; padding: 0 6px; }"
        f"QPushButton:hover {{ color: {fgh}; }}" + popup_ss
    )



# ---------------------------------------------------------------------------
# Command-input widget
# A QPlainTextEdit that:
#  - watches for "/" typed by the user and shows a command-picker dropdown
#  - tracks which text spans are "active commands" (typed via the picker)
#  - highlights active-command spans with a tinted background
#  - translates active-command spans to their prompt text at send-time
#
# KEY DESIGN: "active command" tracking
#   self._active_commands = list of dicts:
#       { "start": int, "length": int, "name": str }
#   start/length are character positions in the document.
#   A span is ONLY considered an active command if it was selected via the
#   dropdown — typing "/tests" manually (after dismissing the dropdown with
#   Escape) is never added to _active_commands and is sent verbatim.
# ---------------------------------------------------------------------------
class _CommandInput(QPlainTextEdit):
    """Input field with slash-command picker dropdown."""

    # Emitted when Ctrl+Enter is pressed (parent wires this to _send)
    send_requested = Signal()
    # Emitted when a built-in command is selected from the dropdown
    builtin_action_requested = Signal(str)   # action name, e.g. "compact"

    # Background colour for highlighted command tokens
    _CMD_BG   = QColor("#2a3a1a")   # dark green tint
    _CMD_FG   = QColor("#b8e090")   # light green text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._commands = []          # list of {name, prompt} — loaded externally
        self._active_commands = []   # list of {start, length, name}
        self._dropdown = None        # _CommandDropdown instance (lazy)
        self._dropdown_slash_pos = -1  # doc position of the '/' that opened dropdown
        self._suppress_change = False
        self._builtin_commands = []  # active built-ins shown at last dropdown open
        self._builtin_factory  = None  # callable() -> list of built-in dicts

        self.document().contentsChange.connect(self._on_contents_change)

    # ── public ───────────────────────────────────────────────────────────

    def set_commands(self, commands, builtin_factory=None):
        self._commands = commands
        if builtin_factory is not None:
            self._builtin_factory = builtin_factory

    def get_text_for_send(self):
        """Return the plain text with all active-command spans replaced by their prompts."""
        raw = self.toPlainText()
        if not self._active_commands:
            return raw
        # Sort by start position, process in reverse so replacements don't shift offsets
        cmds = sorted(self._active_commands, key=lambda c: c["start"], reverse=True)
        result = list(raw)
        for cmd in cmds:
            s, l = cmd["start"], cmd["length"]
            prompt = get_command_prompt(cmd["name"], self._commands)
            replacement = prompt if prompt else raw[s:s+l]
            result[s:s+l] = list(replacement)
        return "".join(result)

    def clear(self):
        self._active_commands.clear()
        self._dropdown_slash_pos = -1
        self._close_dropdown()
        super().clear()

    # ── dropdown interaction ─────────────────────────────────────────────

    def _open_dropdown(self, slash_pos):
        """Show the command picker anchored near the slash character."""
        # Refresh built-in list each time the dropdown opens (visibility may change)
        self._builtin_commands = self._builtin_factory() if self._builtin_factory else []
        if not self._commands and not self._builtin_commands:
            return
        self._dropdown_slash_pos = slash_pos
        if self._dropdown is None:
            self._dropdown = _CommandDropdown(self)
            self._dropdown.command_selected.connect(self._on_command_selected)
            self._dropdown.cancelled.connect(self._on_dropdown_cancelled)
        self._dropdown.populate(self._commands, self._builtin_commands)
        self._reposition_dropdown()
        self._dropdown.show()
        self._dropdown.raise_()
        self.setFocus()

    def _close_dropdown(self):
        if self._dropdown and self._dropdown.isVisible():
            self._dropdown.hide()
        self._dropdown_slash_pos = -1

    def _reposition_dropdown(self):
        if self._dropdown is None:
            return
        # Position relative to the slash character, not current cursor
        cursor = self.textCursor()
        if self._dropdown_slash_pos >= 0:
            cursor.setPosition(self._dropdown_slash_pos)
        rect = self.cursorRect(cursor)
        # Global position of the bottom of the slash character
        global_pt = self.mapToGlobal(rect.bottomLeft())
        dd = self._dropdown
        dd.adjustSize()
        dh = dd.sizeHint().height()
        dw = dd.sizeHint().width()
        # Screen geometry to decide above/below
        from qtpy.QtWidgets import QApplication
        screen = QApplication.screenAt(global_pt)
        if screen is None:
            screen = QApplication.primaryScreen()
        sg = screen.availableGeometry()
        # Show above the slash if not enough space below
        if global_pt.y() + dh > sg.bottom():
            y = self.mapToGlobal(rect.topLeft()).y() - dh
        else:
            y = global_pt.y()
        # Clamp horizontally
        x = min(global_pt.x(), sg.right() - dw)
        x = max(x, sg.left())
        dd.move(x, y)

    def _on_command_selected(self, name):
        """User picked a command — check if it's a built-in action or a user command."""
        # Check if this is a built-in action command
        for b in self._builtin_commands:
            if b["name"] == name:
                self._handle_builtin_selected(name)
                return

        # — Normal user command: replace '/' + partial text with '/name' —
        slash_pos = self._dropdown_slash_pos
        self._close_dropdown()
        if slash_pos < 0:
            return

        cursor = self.textCursor()
        current_pos = cursor.position()

        # Replace from slash_pos to current cursor position with '/name'
        cmd_text = "/" + name
        self._suppress_change = True
        cursor.setPosition(slash_pos)
        cursor.setPosition(current_pos, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(cmd_text)
        self._suppress_change = False

        # Register this as an active command
        self._active_commands.append({
            "start":  slash_pos,
            "length": len(cmd_text),
            "name":   name,
        })
        self._apply_highlights()
        self.setFocus()

    def _handle_builtin_selected(self, name):
        """User selected a built-in command — clear the '/' and fire the action."""
        slash_pos = self._dropdown_slash_pos
        self._close_dropdown()
        # Remove the '/' and any partial text typed after it
        if slash_pos >= 0:
            cursor = self.textCursor()
            current_pos = cursor.position()
            self._suppress_change = True
            cursor.setPosition(slash_pos)
            cursor.setPosition(current_pos, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            self._suppress_change = False
        # Find the action name and emit it
        for b in self._builtin_commands:
            if b["name"] == name:
                self.builtin_action_requested.emit(b.get("action", name))
                return
        self.setFocus()

    def _on_dropdown_cancelled(self):
        """Escape pressed — close dropdown, leave '/' as plain text (not a command)."""
        self._close_dropdown()
        self.setFocus()

    # ── highlights ───────────────────────────────────────────────────────

    def _apply_highlights(self):
        """Re-apply background highlights for all active-command spans."""
        # Clear all existing extra selections
        self.setExtraSelections([])
        selections = []
        raw = self.toPlainText()
        for cmd in self._active_commands:
            s, l = cmd["start"], cmd["length"]
            if s + l > len(raw):
                continue
            # Verify text still matches (guard against out-of-sync after edit)
            if raw[s:s+l] != "/" + cmd["name"]:
                continue
            cursor = self.textCursor()
            cursor.setPosition(s)
            cursor.setPosition(s + l, QTextCursor.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(self._CMD_BG)
            fmt.setForeground(self._CMD_FG)
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = fmt
            selections.append(sel)
        self.setExtraSelections(selections)

    # ── content-change tracking ──────────────────────────────────────────

    def _on_contents_change(self, position, removed, added):
        """Keep _active_commands offsets in sync as text is edited."""
        if self._suppress_change:
            return

        raw = self.toPlainText()
        updated = []
        for cmd in self._active_commands:
            s, l = cmd["start"], cmd["length"]
            end = s + l

            if removed > 0 or added > 0:
                # If the edit touched inside the command span → invalidate it
                edit_end = position + max(removed, added)
                if position < end and edit_end > s:
                    # Edit overlaps span — drop this command
                    continue
                # Shift spans that come after the edit position
                if position <= s:
                    delta = added - removed
                    s += delta
                    cmd = {**cmd, "start": s}

            # Final guard: verify text still matches
            if s >= 0 and s + l <= len(raw) and raw[s:s+l] == "/" + cmd["name"]:
                updated.append(cmd)

        self._active_commands = updated
        self._apply_highlights()

        # Also filter dropdown results if it's open
        if self._dropdown and self._dropdown.isVisible():
            slash_pos = self._dropdown_slash_pos
            cur_pos = self.textCursor().position()
            if slash_pos >= 0 and cur_pos > slash_pos:
                partial = raw[slash_pos + 1 : cur_pos]
                self._dropdown.filter(partial)
            else:
                self._close_dropdown()

    # ── keyboard events ──────────────────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()

        # Ctrl+Enter → send
        if key in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            self.send_requested.emit()
            return

        # Forward Up/Down/Enter/Escape to dropdown when visible
        if self._dropdown and self._dropdown.isVisible():
            if key == Qt.Key_Escape:
                self._on_dropdown_cancelled()
                return
            if key in (Qt.Key_Up, Qt.Key_Down):
                self._dropdown.move_selection(key == Qt.Key_Down)
                return
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._dropdown.confirm_selection()
                return

        super().keyPressEvent(event)

        # After typing, check if we just typed '/'
        if key == Qt.Key_Slash:
            pos = self.textCursor().position()
            self._open_dropdown(pos - 1)


# ---------------------------------------------------------------------------
# Command-picker dropdown  (frameless popup list)
# ---------------------------------------------------------------------------
class _CommandDropdown(QFrame):
    """Floating dropdown that lists available slash commands."""

    command_selected = Signal(str)   # emits command name (without '/')
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setStyleSheet(
            "QFrame { background: #1e2a1e; border: 1px solid #3a5a3a; "
            "border-radius: 4px; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: transparent; border: none; "
            "color: #d0d0d0; font-size: 9pt; }"
            "QListWidget::item { padding: 2px 6px; border-radius: 2px; }"
            "QListWidget::item:selected { background: #2a4a2a; color: #b8e090; }"
            "QListWidget::item:hover { background: #243424; }"
        )
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setFixedWidth(336)
        self._list.itemClicked.connect(self._on_item_click)
        lay.addWidget(self._list)
        self._all_commands = []
        self._all_builtins = []

    def populate(self, commands, builtin_commands=None):
        self._all_commands = commands
        self._all_builtins = builtin_commands or []
        self._fill(commands, self._all_builtins)

    def filter(self, partial):
        """Show only commands whose name starts with `partial`."""
        filtered = [c for c in self._all_commands
                    if c["name"].startswith(partial.lower())]
        filtered_b = [b for b in self._all_builtins
                      if b["name"].startswith(partial.lower())]
        self._fill(filtered, filtered_b)
        if not filtered and not filtered_b:
            self.hide()

    def _fill(self, commands, builtins=None):
        self._list.clear()
        builtins = builtins or []

        # — User commands —
        for cmd in commands:
            desc = self._short_desc(cmd["prompt"])
            item = QListWidgetItem(f"/{cmd['name']}   —   {desc}")
            item.setData(Qt.UserRole, cmd["name"])
            item.setData(Qt.UserRole + 1, False)  # is_builtin = False
            self._list.addItem(item)

        # — Built-in section (if any) —
        if builtins:
            if commands:
                sep = QListWidgetItem("── 内置命令 ──")
                sep.setFlags(Qt.NoItemFlags)
                sep.setForeground(QColor("#555"))
                _f = QFont()
                _f.setPointSize(8)
                _f.setItalic(True)
                sep.setFont(_f)
                self._list.addItem(sep)
            for b in builtins:
                item = QListWidgetItem(f"⚡ /{b['name']}   —   {b['description']}")
                item.setData(Qt.UserRole, b["name"])
                item.setData(Qt.UserRole + 1, True)  # is_builtin = True
                item.setForeground(QColor("#8888cc"))  # muted blue-purple
                self._list.addItem(item)

        # Auto-select first selectable row
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.flags() & Qt.ItemIsSelectable:
                self._list.setCurrentRow(i)
                break

        # Resize to content
        rows = min(self._list.count(), 8)
        item_h = self._list.sizeHintForRow(0) if self._list.count() else 28
        self._list.setFixedHeight(rows * item_h + 6)
        self.adjustSize()

    @staticmethod
    def _short_desc(prompt, max_chars=40):
        words = prompt.split()
        out = ""
        for w in words:
            if len(out) + len(w) + 1 > max_chars:
                return out.rstrip() + "…"
            out += w + " "
        return out.strip()

    def move_selection(self, down: bool):
        row = self._list.currentRow()
        n = self._list.count()
        for _ in range(n):
            row = (row + 1) % n if down else (row - 1) % n
            it = self._list.item(row)
            if it and (it.flags() & Qt.ItemIsSelectable):
                break
        self._list.setCurrentRow(row)

    def confirm_selection(self):
        item = self._list.currentItem()
        if item and (item.flags() & Qt.ItemIsSelectable):
            self.command_selected.emit(item.data(Qt.UserRole))

    def _on_item_click(self, item):
        if item and (item.flags() & Qt.ItemIsSelectable):
            self.command_selected.emit(item.data(Qt.UserRole))


# ---------------------------------------------------------------------------
# Flow layout — wraps child widgets onto multiple rows like CSS flex-wrap
# ---------------------------------------------------------------------------
from qtpy.QtWidgets import QLayout
from qtpy.QtCore import QRect, QPoint, QSize

class _FlowLayout(QLayout):
    """Simple flow layout that wraps widgets to the next row when the row is full."""

    def __init__(self, parent=None, h_spacing=4, v_spacing=4):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(),
                      margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        line_height = 0
        right_edge = rect.right() - margins.right()

        for item in self._items:
            w = item.widget()
            hint = item.sizeHint()
            next_x = x + hint.width()
            if next_x > right_edge and line_height > 0:
                x = rect.x() + margins.left()
                y += line_height + self._v_spacing
                next_x = x + hint.width()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x + self._h_spacing
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


# ---------------------------------------------------------------------------
# Hover-warmup button: stays disabled/gray until the pointer rests on it,
# then animates gray→red over `warmup_ms` ms and becomes clickable.
# Moving the pointer off while still warming up reverses back to gray/disabled.
# ---------------------------------------------------------------------------
class _WarmupButton(QPushButton):
    """QPushButton that activates only after the cursor hovers for `warmup_ms` ms."""

    STEPS = 20  # animation ticks

    def __init__(self, text, warmup_ms=2000, parent=None):
        super().__init__(text, parent)
        self._warmup_ms = warmup_ms
        self._warmup_step = 0
        self._warmup_timer = None
        self._apply_style(0)
        self.setEnabled(False)

    # ── hover enter: start / resume animation ────────────────────────
    def enterEvent(self, event):
        super().enterEvent(event)
        if self._warmup_timer is None:
            interval = self._warmup_ms // self.STEPS
            self._warmup_timer = QTimer(self)
            self._warmup_timer.setInterval(interval)
            self._warmup_timer.timeout.connect(self._tick)
        self._warmup_timer.start()

    # ── hover leave: stop and reverse ────────────────────────────────
    def leaveEvent(self, event):
        super().leaveEvent(event)
        # Always reset -- button is only clickable while cursor is hovering
        self.reset()

    def _tick(self):
        self._warmup_step += 1
        if self._warmup_step >= self.STEPS:
            self._warmup_timer.stop()
            self._warmup_step = self.STEPS
            self.setEnabled(True)   # clickable only while cursor is here
            self._apply_style(self.STEPS)
        else:
            self._apply_style(self._warmup_step)

    def _apply_style(self, step):
        t = step / self.STEPS
        # gray #888 → red #f44
        r = int(0x88 + (0xff - 0x88) * t)
        g = int(0x88 + (0x44 - 0x88) * t)
        b = int(0x88 + (0x44 - 0x88) * t)
        col = f"#{r:02x}{g:02x}{b:02x}"
        bg_r = max(0x28, int(0x28 + 0x18 * t))
        dim = f"#{bg_r:02x}2828"
        self.setStyleSheet(
            f"QPushButton {{ color: {col}; font-size: 9px; padding: 1px 8px; "
            f"border: 1px solid {col}; border-radius: 3px; background: {dim}; }}"
            f"QPushButton:hover {{ color: #fcc; border-color: #fcc; background: {dim}; }}"
            f"QPushButton:disabled {{ color: {col}; border-color: {col}; background: {dim}; }}")

    def reset(self):
        """Call when popup is shown to put button back to initial gray state."""
        if self._warmup_timer:
            self._warmup_timer.stop()
        self._warmup_step = 0
        self.setEnabled(False)
        self._apply_style(0)


# ---------------------------------------------------------------------------
# Clickable QLabel — proper Qt subclass that emits clicked() and calls super()
# so hover/stylesheet/accessibility events are not suppressed.
# Replaces the anti-pattern of assigning a plain function to mousePressEvent.
# ---------------------------------------------------------------------------
class _ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()


class _ClickEventFilter(QObject):
    """Event filter that calls `callback()` on left-click of the watched widget.

    Keeps its own reference alive by parenting to `parent_widget`, so the
    filter is automatically destroyed when the widget is destroyed.
    Used to add click handling to QFrame/QWidget without replacing
    mousePressEvent (which would bypass Qt's event chain).
    """

    def __init__(self, callback, parent_widget):
        super().__init__(parent_widget)
        self._callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._callback()
            return False   # don't consume — let normal press processing continue
        return False


# ---------------------------------------------------------------------------
# Context-size button — shows a custom popup tooltip above itself
# ---------------------------------------------------------------------------
class _CtxTooltipPopup(QFrame):
    """Floating HTML panel shown above the context-size button.

    Created as a Qt.Tool | Qt.FramelessWindowHint top-level window so it
    floats freely above the IDE without stealing focus or being clipped by
    parent widget geometry.  Mouse events pass through so hover-leave on the
    button is not disturbed by the popup overlapping the cursor path.
    """

    def __init__(self):
        super().__init__(None,
                         Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._apply_theme()
        vl = QVBoxLayout(self)
        vl.setContentsMargins(8, 8, 8, 8)
        self._lbl = QLabel()
        self._lbl.setTextFormat(Qt.RichText)
        vl.addWidget(self._lbl)

    def _apply_theme(self):
        """(Re-)apply stylesheet to match the current Spyder theme."""
        if _is_dark_theme():
            self.setStyleSheet(
                "QFrame { background: #1e2a1e; border: 1px solid #4a6a4a; "
                "border-radius: 3px; }"
                "QLabel { color: #d0d0d0; font-size: 10px; border: none; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background: #f0f8f0; border: 1px solid #80a880; "
                "border-radius: 3px; }"
                "QLabel { color: #222222; font-size: 10px; border: none; }"
            )

    def show_above(self, anchor_widget, html):
        """Render `html` and position the popup just above `anchor_widget`."""
        self._apply_theme()   # re-check theme each time popup is shown
        self._lbl.setText(html)
        self.adjustSize()

        btn_global = anchor_widget.mapToGlobal(QPoint(0, 0))
        # Right-align popup to button's right edge; sit 4 px above its top edge
        x = btn_global.x() + anchor_widget.width() - self.width()
        y = btn_global.y() - self.height() - 4

        # Clamp so the popup stays fully on screen
        try:
            sg = anchor_widget.screen().availableGeometry()
        except AttributeError:
            sg = QApplication.primaryScreen().availableGeometry()
        x = max(sg.left() + 4, min(x, sg.right() - self.width() - 4))
        y = max(sg.top() + 4, y)

        self.move(x, y)
        self.show()
        self.raise_()

    def show_at_cursor(self, html):
        """Render `html` and position the popup to the right of the cursor.

        Used by _TipHoverFilter for button/label tooltips — mimics the
        standard OS tooltip placement (just right of and at the cursor).
        """
        from qtpy.QtGui import QCursor
        self._apply_theme()
        self._lbl.setText(html)
        self.adjustSize()

        pos = QCursor.pos()
        x = pos.x() + 14    # 14 px right of cursor tip
        y = pos.y()          # vertically aligned with cursor

        try:
            screen = QApplication.screenAt(pos)
            sg = (screen.availableGeometry() if screen
                  else QApplication.primaryScreen().availableGeometry())
        except AttributeError:
            sg = QApplication.primaryScreen().availableGeometry()

        # Flip left if popup overflows right edge
        if x + self.width() > sg.right() - 4:
            x = pos.x() - self.width() - 4
        # Flip up if popup overflows bottom edge
        if y + self.height() > sg.bottom() - 4:
            y = sg.bottom() - self.height() - 4
        x = max(sg.left() + 4, x)
        y = max(sg.top() + 4, y)

        self.move(x, y)
        self.show()
        self.raise_()


class _CtxSizeButton(QPushButton):
    """QPushButton that shows a custom-positioned tooltip above itself on hover.

    Uses _CtxTooltipPopup (a floating Qt.Tool window) instead of the system
    QToolTip so the popup is guaranteed to appear above the button regardless
    of whether the IDE window happens to be near the physical screen edge.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tip_popup = None

    def _get_tip_popup(self):
        if self._tip_popup is None:
            self._tip_popup = _CtxTooltipPopup()
        return self._tip_popup

    def event(self, ev):
        # Suppress the system QToolTip — our enterEvent popup replaces it
        if ev.type() == QEvent.ToolTip:
            return True
        return super().event(ev)

    def enterEvent(self, ev):
        super().enterEvent(ev)
        html = self.toolTip()
        if html:
            self._get_tip_popup().show_above(self, html)

    def leaveEvent(self, ev):
        super().leaveEvent(ev)
        if self._tip_popup:
            self._tip_popup.hide()

    def hideEvent(self, ev):
        super().hideEvent(ev)
        if self._tip_popup:
            self._tip_popup.hide()


# ---------------------------------------------------------------------------
# Read-batch summary widget  (replaces N individual read/ls/grep blocks)
# ---------------------------------------------------------------------------
def _group_read_frames_in_layout(layout):
    """Scan a QVBoxLayout and group any read/ls/grep action frames into one summary.

    Works purely from Qt properties set on each action block frame by
    build_action_block — no exec registry needed, so it works for both live
    responses and history reloads.  Only groups when 2+ read-type frames exist.
    """
    _READ_ONLY = {"read", "ls", "grep"}
    read_items = []   # (layout_index, widget, action_type, target)

    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is None:
            continue
        w = item.widget()
        if w is None:
            continue
        at = w.property("agentic_action_type")
        if at and at in _READ_ONLY:
            tgt = w.property("agentic_action_target") or ""
            read_items.append((i, w, at, tgt))

    if len(read_items) < 2:
        return

    entries = [{"action_type": at, "target": tgt, "widget": w}
               for (_, w, at, tgt) in read_items]

    insert_pos = read_items[0][0]
    summary    = _build_read_group_widget(entries)

    for (_, w, _, _) in read_items:
        w.hide()

    layout.insertWidget(insert_pos, summary)


def _build_read_group_widget(entries):
    """Build a single compact block that represents a batch of read/ls/grep fences.

    Called after the fences have already been executed; the widget is purely
    informational (no run button) and shows the list of targets with a toggle.
    Uses the same green colour palette as individual read action blocks.
    """
    # Classify by action type
    type_counts = {}
    for e in entries:
        t = e["action_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    n = len(entries)
    if len(type_counts) == 1:
        at = next(iter(type_counts))
        if at == "read":
            icon  = "📄"
            noun  = f"读取 \u2192 {n} 个文件"
        elif at == "ls":
            icon  = "📁"
            noun  = f"列出 \u2192 {n} 个目录"
        elif at == "grep":
            icon  = "🔍"
            noun  = f"搜索 \u2192 {n} 个模式"
        else:
            icon  = "📄"
            noun  = f"读取 \u2192 {n} 个操作"
    else:
        icon = "📄"
        noun = f"Read \u2192 {n} actions"

    color = "#4ec9b0"   # same green as individual read blocks
    bg    = "#0a1f0a"

    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background: {bg}; border: 1px solid {color}; "
        f"border-radius: 4px; margin: 2px 8px; }}")
    frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    vl = QVBoxLayout(frame)
    vl.setContentsMargins(0, 0, 0, 0)
    vl.setSpacing(0)

    # ── Header row ───────────────────────────────────────────────────────
    header = QWidget()
    header.setStyleSheet(
        f"background: {color}22; border-bottom: 1px solid {color}; "
        "border-radius: 0px;")
    hl = QHBoxLayout(header)
    hl.setContentsMargins(8, 4, 8, 4)
    hl.setSpacing(6)

    toggle_lbl = QLabel("▼")
    toggle_lbl.setStyleSheet(
        f"color: {color}; font-size: 9px; background: transparent; border: none;")

    header_lbl = QLabel(f"{icon} {noun}")
    header_lbl.setStyleSheet(
        f"color: {color}; font-size: 10px; font-weight: bold; "
        "background: transparent; border: none;")

    done_lbl = QLabel("✓ 完成")
    done_lbl.setStyleSheet(
        f"color: {color}; font-size: 9px; padding: 1px 6px; "
        "background: transparent; border: none;")

    hl.addWidget(toggle_lbl)
    hl.addWidget(header_lbl)
    hl.addStretch()
    hl.addWidget(done_lbl)
    vl.addWidget(header)

    # ── Path list (collapsible) ──────────────────────────────────────────
    list_w = QWidget()
    list_w.setStyleSheet("background: transparent; border: none;")
    ll = QVBoxLayout(list_w)
    ll.setContentsMargins(28, 4, 8, 6)
    ll.setSpacing(1)

    for e in entries:
        lbl = QLabel(e["target"])
        lbl.setStyleSheet(
            "color: #88cc88; font-size: 9px; background: transparent; border: none;")
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ll.addWidget(lbl)

    # Start collapsed — path list hidden, arrow pointing right
    list_w.setVisible(False)
    toggle_lbl.setText("▶")

    vl.addWidget(list_w)

    # ── Toggle collapse on header click ─────────────────────────────────
    def _toggle():
        vis = not list_w.isVisible()
        list_w.setVisible(vis)
        toggle_lbl.setText("▼" if vis else "▶")

    # Install only on the header container — child QLabels do not accept mouse
    # events so clicks on toggle_lbl / header_lbl / done_lbl propagate up to
    # header automatically.  Installing on both header and a child would cause
    # _toggle() to fire twice (child filter + parent's propagated-event filter),
    # toggling on and immediately off with no visible change.
    _ef_hdr = _ClickEventFilter(_toggle, header)
    header.installEventFilter(_ef_hdr)
    header.setCursor(Qt.PointingHandCursor)

    return frame


# ---------------------------------------------------------------------------
# Agentic-output scrollable hover popup
# ---------------------------------------------------------------------------
class _AgenticTooltipPopup(QFrame):
    """Scrollable floating popup shown when hovering the 'Agentic output' header.

    Unlike the system QToolTip this panel has a capped height with a real
    vertical scrollbar, so arbitrarily long fence content (file reads, grep
    results, …) does not fill the whole screen.  Mouse events are NOT
    suppressed so the user can scroll inside the panel.

    Hiding uses a short grace-period timer: moving the mouse from the header
    bar into the popup cancels the timer so the panel stays visible.
    """

    _MAX_H = 420   # px — scrollbar appears above this
    _WIDTH  = 580  # px

    def __init__(self):
        super().__init__(None,
                         Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(self._WIDTH)
        self._apply_theme()
        from qtpy.QtWidgets import QPlainTextEdit
        vl = QVBoxLayout(self)
        vl.setContentsMargins(4, 4, 4, 4)
        self._edit = QPlainTextEdit()
        self._edit.setReadOnly(True)
        self._edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        vl.addWidget(self._edit)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(200)
        self._hide_timer.timeout.connect(self.hide)

    def set_content(self, text):
        self._edit.setPlainText(text)
        # Compute a height that fits the content up to _MAX_H
        fm   = self._edit.fontMetrics()
        n_lines = text.count("\n") + 1
        content_h = n_lines * fm.lineSpacing() + 16
        self._edit.setFixedHeight(min(content_h, self._MAX_H))
        self.adjustSize()

    def _apply_theme(self):
        """(Re-)apply the stylesheet matching the current Spyder theme."""
        if _is_dark_theme():
            self.setStyleSheet(
                "QFrame { background: #0d1a2e; border: 1px solid #44446a; "
                "border-radius: 3px; }"
                "QPlainTextEdit { background: #0d1a2e; color: #c8c8d0; "
                "border: none; font-size: 10px; }"
                "QScrollBar:vertical { background: #0a1525; width: 10px; }"
                "QScrollBar::handle:vertical { background: #2a4a7a; "
                "min-height: 20px; border-radius: 4px; }"
                "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical "
                "{ height: 0; }"
                "QScrollBar:horizontal { background: #0a1525; height: 10px; }"
                "QScrollBar::handle:horizontal { background: #2a4a7a; "
                "min-width: 20px; border-radius: 4px; }"
                "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal "
                "{ width: 0; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background: #f0f0ff; border: 1px solid #8888cc; "
                "border-radius: 3px; }"
                "QPlainTextEdit { background: #f0f0ff; color: #222244; "
                "border: none; font-size: 10px; }"
                "QScrollBar:vertical { background: #e0e0f0; width: 10px; }"
                "QScrollBar::handle:vertical { background: #9999cc; "
                "min-height: 20px; border-radius: 4px; }"
                "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical "
                "{ height: 0; }"
                "QScrollBar:horizontal { background: #e0e0f0; height: 10px; }"
                "QScrollBar::handle:horizontal { background: #9999cc; "
                "min-width: 20px; border-radius: 4px; }"
                "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal "
                "{ width: 0; }"
            )

    def show_near(self, anchor_widget):
        """Position just below (or above if near screen bottom) `anchor_widget`."""
        self._apply_theme()   # re-check theme each time popup is shown
        anchor_tl = anchor_widget.mapToGlobal(QPoint(0, 0))
        x = anchor_tl.x()
        y = anchor_tl.y() + anchor_widget.height() + 2

        try:
            sg = anchor_widget.screen().availableGeometry()
        except AttributeError:
            sg = QApplication.primaryScreen().availableGeometry()

        # Flip above header if popup would overflow the screen bottom
        if y + self.height() > sg.bottom() - 4:
            y = anchor_tl.y() - self.height() - 2

        x = max(sg.left() + 4, min(x, sg.right() - self.width() - 4))
        y = max(sg.top() + 4, y)

        self._hide_timer.stop()
        self.move(x, y)
        self.show()
        self.raise_()

    def schedule_hide(self):
        self._hide_timer.start()

    def cancel_hide(self):
        self._hide_timer.stop()

    def enterEvent(self, ev):
        self._hide_timer.stop()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hide_timer.start()
        super().leaveEvent(ev)


class _AgenticHoverFilter(QObject):
    """Event filter installed on the agentic-output header bar (a QFrame).

    Shows the shared _AgenticTooltipPopup on mouse-enter and schedules
    its hiding on mouse-leave.  Parented to `parent_widget` so it is
    automatically destroyed when the header bar is destroyed.
    """

    def __init__(self, popup, text, parent_widget):
        super().__init__(parent_widget)
        self._popup = popup
        self._text  = text

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.Enter:
            self._popup.set_content(self._text)
            self._popup.show_near(obj)
        elif t == QEvent.Leave:
            self._popup.schedule_hide()
        return False   # never consume — let normal event processing continue


class _TipHoverFilter(QObject):
    """Event filter that replaces the OS system QToolTip with a themed popup.

    The OS tooltip follows the *system* dark/light mode, which may clash with
    Spyder's theme (e.g. OS in dark mode, Spyder in light mode).  This filter:
    - Suppresses QEvent.ToolTip so the OS tooltip never appears.
    - On QEvent.Enter: shows _CtxTooltipPopup (compact, auto-sized) above the
      widget — suitable for short button labels (1–3 lines).
    - On QEvent.Leave: hides the popup.

    Parent the filter to the target widget so it is destroyed automatically.
    Use _install_themed_tip(widget, text) as the public entry point.

    A single _CtxTooltipPopup is shared as a class-level singleton.
    """
    _shared = None   # shared _CtxTooltipPopup singleton

    def __init__(self, text, parent):
        super().__init__(parent)
        self._text = text

    @classmethod
    def _get_popup(cls):
        if cls._shared is None:
            cls._shared = _CtxTooltipPopup()
        return cls._shared

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.ToolTip:
            return True           # suppress OS tooltip
        if t == QEvent.Enter:
            import html as _html
            p = self._get_popup()
            rich = _html.escape(self._text).replace('\n', '<br>')
            p.show_at_cursor(rich)
        elif t == QEvent.Leave:
            p = self.__class__._shared
            if p:
                p.hide()
        return False


def _install_themed_tip(widget, text):
    """Replace the OS system tooltip on *widget* with a compact themed popup.

    Call instead of widget.setToolTip(text) for any widget inside the chat
    panel where the system QToolTip may appear dark regardless of Spyder's theme.
    Best suited for short 1–3 line labels (buttons, combo boxes, labels).
    For multi-line scrollable content use _AgenticHoverFilter directly.
    """
    widget.setToolTip("")          # clear system tooltip (accessibility: blank)
    f = _TipHoverFilter(text, widget)   # parent=widget → auto-destroyed
    widget.installEventFilter(f)


# ---------------------------------------------------------------------------
# Project Context Dialog
# ---------------------------------------------------------------------------
class _ProjectContextDialog(QDialog):
    """
    Folder-selection dialog shown when enabling project context.
    Scans the project root, shows top-level folder checkboxes with file counts,
    and reports an estimated token count.
    """

    def __init__(self, root, max_file_kb=256, max_files=500,
                 extra_patterns=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("启用项目上下文")
        self.setMinimumWidth(420)

        from .project_context import (
            collect_project_files, collect_unsaved_files,
            get_top_level_folders, estimate_tokens,
        )

        self._root = root
        self._max_file_kb = max_file_kb
        self._max_files = max_files
        self._extra_patterns = extra_patterns

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        # Header
        proj_name = root.split("/")[-1].split("\\")[-1] if root else ""
        hdr = QLabel(f"<b>项目:</b> {proj_name}<br>"
                     f"<small style='color:gray'>{root}</small>")
        hdr.setTextFormat(Qt.RichText)
        hdr.setWordWrap(True)
        lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #444;")
        lay.addWidget(sep)

        lay.addWidget(QLabel("包含顶级文件夹："))

        # Collect all files once for counts
        self._all_files = collect_project_files(
            root, included_folders=None,
            extra_patterns=extra_patterns,
            max_file_kb=max_file_kb, max_files=max_files,
        )

        # Group by top-level folder
        self._folder_files = {}
        top_folders = get_top_level_folders(root)
        root_files_count = 0
        for f in self._all_files:
            parts = f["path"].split("/")
            folder = parts[0] if len(parts) > 1 else ""
            if folder in top_folders:
                self._folder_files.setdefault(folder, []).append(f)
            else:
                root_files_count += 1

        # Scroll area for checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMaximumHeight(200)
        inner = QWidget()
        cb_lay = QVBoxLayout(inner)
        cb_lay.setContentsMargins(0, 0, 0, 0)
        cb_lay.setSpacing(2)

        self._checkboxes = {}
        for folder in top_folders:
            count = len(self._folder_files.get(folder, []))
            cb = QCheckBox(f"{folder}/  ({count} files)")
            cb.setChecked(True)
            cb.toggled.connect(self._update_estimate)
            self._checkboxes[folder] = cb
            cb_lay.addWidget(cb)

        if root_files_count:
            cb = QCheckBox(f"[root files]  ({root_files_count} files)")
            cb.setChecked(True)
            cb.toggled.connect(self._update_estimate)
            self._checkboxes[""] = cb
            cb_lay.addWidget(cb)

        cb_lay.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll)

        # Estimate label
        self._est_lbl = QLabel()
        self._est_lbl.setStyleSheet("font-size: 9pt; color: gray;")
        lay.addWidget(self._est_lbl)

        self._warn_lbl = QLabel(
            "⚠ 上下文过大 — 可能超出模型的 token 限制。")
        self._warn_lbl.setStyleSheet("color: #c8a000; font-size: 9pt;")
        self._warn_lbl.setVisible(False)
        lay.addWidget(self._warn_lbl)

        usage_warn = QLabel(
            "⚠  <b>高 Token 消耗：</b>项目上下文会将整个项目随每条消息一起发送。"
            "如果您的模型支持，请优先使用代理模式的 <b>read / ls / grep</b> 操作。"
        )
        usage_warn.setWordWrap(True)
        usage_warn.setTextFormat(Qt.RichText)
        usage_warn.setStyleSheet(
            "color: #e8a050; font-size: 8pt; "
            "background: #1e1200; border: 1px solid #7a4a00; "
            "border-radius: 3px; padding: 5px 7px;")
        lay.addWidget(usage_warn)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("启用项目上下文")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._update_estimate()

    def _update_estimate(self):
        from .project_context import estimate_tokens
        selected = self._selected_files()
        n = len(selected)
        tok = estimate_tokens(selected)
        self._est_lbl.setText(f"{n} 个文件 · 约 {tok:,} tokens")
        self._warn_lbl.setVisible(tok > 100_000)

    def _selected_files(self):
        selected_folders = {
            folder for folder, cb in self._checkboxes.items()
            if cb.isChecked()
        }
        return [
            f for f in self._all_files
            if (f["path"].split("/")[0]
                if "/" in f["path"] else "") in selected_folders
        ]

    def selected_folders(self):
        """Return list of checked top-level folder names (including '' for root)."""
        return [
            folder for folder, cb in self._checkboxes.items()
            if cb.isChecked()
        ]

    def selected_files(self):
        return self._selected_files()

    def estimate_tokens(self):
        from .project_context import estimate_tokens
        return estimate_tokens(self._selected_files())


# ---------------------------------------------------------------------------
# Chat reference encoding (collection + filename)
# ---------------------------------------------------------------------------

def _encode_chat_ref(collection, filename):
    """Encode collection + filename into a single string reference.
    Default collection ('' or None) → bare "filename.json" (backward compat).
    Named collection → "CollectionName/filename.json".
    """
    if collection and collection != "__all__":
        return f"{collection}/{filename}"
    return filename


def _decode_chat_ref(ref):
    """Decode a chat reference into (collection, filename).
    Bare "filename.json" → ('', 'filename.json')  — Default collection.
    "Collection/file.json" → ('Collection', 'file.json').
    """
    if ref and "/" in ref:
        collection, filename = ref.split("/", 1)
        return collection, filename
    return "", ref  # Default collection (backward compat with bare filenames)


# ---------------------------------------------------------------------------
# Chat History Popup
# ---------------------------------------------------------------------------
class _ChatHistoryPopup(QFrame):
    """Popup listing saved chats with collection selector.

    Signals:
      load_chat(ref)  — ref is encoded as "Collection/filename.json" or bare
                        "filename.json" for the Default collection.
      del_chat(ref)   — same encoding.
      del_all()       — all chats in the current (non-'__all__') collection deleted.
    """
    load_chat = Signal(str)
    del_chat  = Signal(str)
    del_all   = Signal()

    _ALL = "__all__"

    def __init__(self, save_state_fn, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(430)
        self.setMinimumHeight(440)
        self.setMaximumHeight(620)

        self._save_state_fn   = save_state_fn   # callable(current_collection=str)
        self._current_collection = ""           # '' = Default
        self._current_file    = None            # currently open chat filename
        self._current_file_collection = ""     # collection of the currently open chat

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # ── row 1: title ──────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)
        hdr_lbl = QLabel("聊天历史")
        hdr_lbl.setStyleSheet("font-weight: bold; font-size: 11px; padding: 2px 4px;")
        hdr_row.addWidget(hdr_lbl, 1)
        lay.addLayout(hdr_row)

        sep_top = QFrame()
        sep_top.setFrameShape(QFrame.HLine)
        sep_top.setStyleSheet("color: #444;")
        lay.addWidget(sep_top)

        # ── row 2: collection selector + manage button ────────────────
        coll_row = QHBoxLayout()
        coll_row.setContentsMargins(0, 0, 0, 0)
        coll_row.setSpacing(4)

        coll_lbl = QLabel("集合：")
        coll_lbl.setStyleSheet("font-size: 11px;")
        coll_row.addWidget(coll_lbl)

        self._coll_combo = QComboBox()
        self._coll_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _install_themed_tip(self._coll_combo, "选择一个集合浏览，或选择'全部'在所有集合中搜索")
        coll_row.addWidget(self._coll_combo, 1)

        self._coll_mgr_btn = QPushButton("\u2699\uFE0E")
        self._coll_mgr_btn.setFixedSize(26, 26)
        _install_themed_tip(self._coll_mgr_btn, "管理集合…")
        if _is_dark_theme():
            self._coll_mgr_btn.setStyleSheet(
                "QPushButton { font-size: 14px; color: #ccc; "
                "border: 1px solid #555; border-radius: 3px; padding: 0px; }"
                "QPushButton:hover { color: #eee; border-color: #aaa; }")
        else:
            self._coll_mgr_btn.setStyleSheet(
                "QPushButton { font-size: 14px; color: #444; "
                "border: 1px solid #aaa; border-radius: 3px; padding: 0px; }"
                "QPushButton:hover { color: #000; border-color: #666; }")
        self._coll_mgr_btn.clicked.connect(self._open_manager)
        coll_row.addWidget(self._coll_mgr_btn)
        lay.addLayout(coll_row)

        # ── search field ──────────────────────────────────────────────
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索聊天记录…")
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(
            "QLineEdit { border: 1px solid #444; border-radius: 3px; "
            "padding: 3px 6px; font-size: 11px; }")
        self._search.textChanged.connect(self._on_search)
        lay.addWidget(self._search)

        # ── chat list ─────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._container = QWidget()
        self._list_lay = QVBoxLayout(self._container)
        self._list_lay.setContentsMargins(0, 4, 0, 4)
        self._list_lay.setSpacing(2)
        self._list_lay.setAlignment(Qt.AlignTop)

        self._empty_lbl = QLabel("暂无保存的聊天记录。")
        self._empty_lbl.setStyleSheet("color: gray; padding: 12px 8px;")
        self._empty_lbl.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self._list_lay.addWidget(self._empty_lbl)

        self._scroll.setWidget(self._container)
        lay.addWidget(self._scroll, stretch=1)

        # ── bottom row: Delete All ────────────────────────────────────
        sep_bot = QFrame()
        sep_bot.setFrameShape(QFrame.HLine)
        sep_bot.setStyleSheet("color: #444;")
        lay.addWidget(sep_bot)

        bot_row = QHBoxLayout()
        bot_row.setContentsMargins(0, 0, 0, 0)
        bot_row.addStretch(1)

        self._del_all_btn = _WarmupButton("🗑 删除全部", warmup_ms=1000)
        self._del_all_btn.setFlat(True)
        _install_themed_tip(self._del_all_btn,
            "删除当前选定集合中的所有聊天记录（按住 1 秒解锁）")
        self._del_all_btn.setFixedHeight(24)

        self._del_all_cancel = QPushButton("↩ 取消 (3)")
        self._del_all_cancel.setFlat(True)
        self._del_all_cancel.setFixedHeight(24)
        self._del_all_cancel.setStyleSheet(
            "QPushButton { color: #f88; font-size: 9px; padding: 1px 8px; "
            "border: 1px solid #f88; border-radius: 3px; }"
            "QPushButton:hover { color: #fcc; border-color: #fcc; }")
        self._del_all_cancel.setVisible(False)
        self._del_all_timer = None
        self._del_all_remaining = [3]

        self._del_all_btn.clicked.connect(self._arm_delete_all)
        self._del_all_cancel.clicked.connect(self._cancel_delete_all)
        bot_row.addWidget(self._del_all_cancel)
        bot_row.addWidget(self._del_all_btn)
        lay.addLayout(bot_row)

        # Wire combo AFTER widgets are created
        self._coll_combo.currentIndexChanged.connect(self._on_collection_changed)

    # ── collection combo ──────────────────────────────────────────────
    def _populate_collection_combo(self):
        """Rebuild the collection dropdown preserving the current selection."""
        self._coll_combo.blockSignals(True)
        self._coll_combo.clear()
        self._coll_combo.addItem("⊕ 所有集合", self._ALL)
        self._coll_combo.addItem("默认", "")
        for name in list_collections():
            self._coll_combo.addItem(name, name)
        # Restore selection
        idx = self._coll_combo.findData(self._current_collection)
        self._coll_combo.setCurrentIndex(max(idx, 0))
        self._coll_combo.blockSignals(False)

    def _on_collection_changed(self, _idx):
        self._current_collection = self._coll_combo.currentData() or ""
        # "Delete All" is hidden in All-Collections mode (too destructive)
        is_all = (self._current_collection == self._ALL)
        self._del_all_btn.setVisible(not is_all)
        self._del_all_cancel.setVisible(False)
        self._cancel_delete_all()
        self._save_state_fn(self._current_collection)
        self._refresh(self._search.text().strip())

    def set_collection(self, name):
        """Externally switch the active collection and refresh."""
        self._current_collection = name or ""
        idx = self._coll_combo.findData(self._current_collection)
        if idx >= 0:
            self._coll_combo.setCurrentIndex(idx)
        else:
            self._refresh()

    # ── manager ──────────────────────────────────────────────────────
    def _open_manager(self):
        main_win = _find_main_window()
        dlg = ChatCollectionManagerDialog(
            current_collection=self._current_collection, parent=main_win)
        dlg.collections_changed.connect(self._on_manager_changed)
        # Keep popup visible behind manager (it's a Popup window)
        self.hide()
        dlg.exec_()
        # Sync active collection in case a rename/delete changed it
        resulting = dlg.resulting_collection()
        self._current_collection = resulting
        self._save_state_fn(self._current_collection)
        self._populate_collection_combo()
        self._refresh()
        self.show()
        self.raise_()

    def _on_manager_changed(self):
        self._populate_collection_combo()
        self._refresh()

    # ── delete-all countdown ──────────────────────────────────────────
    def _arm_delete_all(self):
        if self._del_all_timer:
            self._del_all_timer.stop()
        self._del_all_remaining[0] = 3
        self._del_all_btn.setVisible(False)
        self._del_all_cancel.setText("\u21a9 取消 (3)")
        self._del_all_cancel.setVisible(True)

        def _tick():
            self._del_all_remaining[0] -= 1
            if self._del_all_remaining[0] > 0:
                self._del_all_cancel.setText(
                    f"\u21a9 Cancel ({self._del_all_remaining[0]})")
            else:
                self._del_all_timer.stop()
                self._del_all_timer = None
                self._del_all_cancel.setVisible(False)
                self._del_all_btn.setVisible(True)
                self._execute_delete_all()

        self._del_all_timer = QTimer(self)
        self._del_all_timer.setInterval(1000)
        self._del_all_timer.timeout.connect(_tick)
        self._del_all_timer.start()

    def _cancel_delete_all(self):
        if self._del_all_timer:
            self._del_all_timer.stop()
            self._del_all_timer = None
        self._del_all_cancel.setVisible(False)
        if hasattr(self._del_all_btn, 'reset'):
            self._del_all_btn.reset()
        self._del_all_btn.setVisible(True)

    def _execute_delete_all(self):
        # Only delete within the currently visible collection
        coll = self._current_collection
        if coll == self._ALL:
            return
        for chat in list_chats(collection=coll):
            delete_chat(chat["filename"], collection=coll)
        self.del_all.emit()
        self._refresh()

    # ── search + refresh ──────────────────────────────────────────────
    def _on_search(self, text):
        self._refresh(text.strip())

    def show_below(self, btn, current_file=None, current_collection="",
                   current_file_collection=""):
        self._current_file            = current_file
        self._current_file_collection = current_file_collection or ""
        self._current_collection      = current_collection or ""
        self._cancel_delete_all()
        if hasattr(self._del_all_btn, 'reset'):
            self._del_all_btn.reset()
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        self._populate_collection_combo()
        self._refresh()
        self.adjustSize()

        try:
            btn_bottom_right = btn.mapToGlobal(btn.rect().bottomRight())
            popup_x = btn_bottom_right.x() - self.width()
            popup_y = btn_bottom_right.y()
            from qtpy.QtWidgets import QApplication
            screen = QApplication.primaryScreen().availableGeometry()
            popup_x = max(screen.left(), popup_x)
        except Exception:
            pos = btn.mapToGlobal(btn.rect().bottomLeft())
            popup_x, popup_y = pos.x(), pos.y()

        self.move(popup_x, popup_y)
        self.show()
        self.raise_()

    def _refresh(self, query=""):
        # Clear chat rows but keep empty_lbl (index 0)
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        is_all  = (self._current_collection == self._ALL)
        coll    = None if is_all else (self._current_collection or None)

        if query:
            chats = search_chats(query, collection=coll, all_collections=is_all)
        else:
            chats = list_chats(collection=coll, all_collections=is_all)

        no_results = len(chats) == 0
        self._empty_lbl.setText(
            "未找到匹配的聊天记录。" if (query and no_results) else "暂无保存的聊天记录。")
        self._empty_lbl.setVisible(no_results)
        self._del_all_btn.setVisible(not no_results and not is_all)

        for chat in chats:
            self._add_row(chat)

    def _add_row(self, chat):
        fname      = chat["filename"]
        chat_coll  = chat.get("collection", "")   # '' = Default
        preview    = chat["preview"] or "（空）"
        label      = preview[:55] + ("…" if len(preview) > 55 else "")
        try:
            dt = chat["saved_at"][:16].replace("T", " ")
        except Exception:
            dt = ""

        # Show collection badge when browsing All Collections
        if self._current_collection == self._ALL and chat_coll:
            dt = f"[{chat_coll}]  {dt}"

        is_active = (fname == self._current_file and
                     chat_coll == self._current_file_collection)

        row = QFrame()
        row.setObjectName("chatrow")
        if is_active:
            if _is_dark_theme():
                row.setStyleSheet(
                    "QFrame#chatrow { border-radius: 3px; background: #1a3a1a; "
                    "border: 1px solid #3a7a3a; }"
                    "QFrame#chatrow:hover { background: #244a24; }")
            else:
                row.setStyleSheet(
                    "QFrame#chatrow { border-radius: 3px; background: #cce8cc; "
                    "border: 1px solid #6aaa6a; }"
                    "QFrame#chatrow:hover { background: #b8ddb8; }")
        else:
            row.setStyleSheet(
                "QFrame#chatrow { border-radius: 3px; }"
                "QFrame#chatrow:hover { background: palette(highlight); }")

        # Right-click context menu for "Move to"
        row.setContextMenuPolicy(Qt.CustomContextMenu)
        row.customContextMenuRequested.connect(
            lambda pos, f=fname, c=chat_coll: self._show_row_menu(f, c, pos))

        rl = QHBoxLayout(row)
        rl.setContentsMargins(7, 3, 4, 3)
        rl.setSpacing(6)

        txt_btn = QPushButton(f"{label}\n{dt}")
        txt_btn.setFlat(True)
        if is_active:
            if _is_dark_theme():
                txt_btn.setStyleSheet(
                    "QPushButton { text-align: left; border: none; padding: 2px 0 2px 6px; "
                    "font-size: 11px; color: #7ec87e; }"
                    "QPushButton:hover { color: #aeeaae; }")
            else:
                txt_btn.setStyleSheet(
                    "QPushButton { text-align: left; border: none; padding: 2px 0 2px 6px; "
                    "font-size: 11px; color: #1a5a1a; }"
                    "QPushButton:hover { color: #0a3a0a; }")
        else:
            txt_btn.setStyleSheet(
                "QPushButton { text-align: left; border: none; padding: 2px 0 2px 6px; "
                "font-size: 11px; }"
                "QPushButton:hover { color: palette(highlighted-text); }")
        ref = _encode_chat_ref(chat_coll, fname)
        txt_btn.clicked.connect(lambda checked=False, r=ref: self._on_load(r))
        rl.addWidget(txt_btn, stretch=1)

        # Per-row delete with countdown/cancel
        del_btn    = QPushButton("✕")
        del_btn.setFixedSize(28, 28)
        del_btn.setFlat(True)
        _install_themed_tip(del_btn, "删除此聊天")
        del_btn.setStyleSheet(
            "QPushButton { color: #888; border: none; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { color: #f88; }")

        cancel_btn = QPushButton("↩ 3")
        cancel_btn.setFixedSize(44, 28)
        cancel_btn.setFlat(True)
        _install_themed_tip(cancel_btn, "取消删除")
        cancel_btn.setStyleSheet(
            "QPushButton { color: #f88; border: 1px solid #f88; "
            "border-radius: 3px; font-size: 10px; font-weight: bold; }"
            "QPushButton:hover { color: #fcc; border-color: #fcc; }")
        cancel_btn.setVisible(False)

        rl.addWidget(del_btn)
        rl.addWidget(cancel_btn)

        row_state = {"timer": None, "remaining": [3]}

        def _arm(fn=fname, fc=chat_coll):
            if row_state["timer"]:
                row_state["timer"].stop()
            row_state["remaining"][0] = 3
            del_btn.setVisible(False)
            cancel_btn.setText("↩ 3")
            cancel_btn.setVisible(True)

            def _tick():
                row_state["remaining"][0] -= 1
                r = row_state["remaining"][0]
                if r > 0:
                    cancel_btn.setText(f"↩ {r}")
                else:
                    row_state["timer"].stop()
                    row_state["timer"] = None
                    self._on_delete(fn, fc)

            t = QTimer(row)
            t.setInterval(1000)
            t.timeout.connect(_tick)
            t.start()
            row_state["timer"] = t

        def _cancel():
            if row_state["timer"]:
                row_state["timer"].stop()
                row_state["timer"] = None
            cancel_btn.setVisible(False)
            del_btn.setVisible(True)

        del_btn.clicked.connect(lambda checked=False: _arm())
        cancel_btn.clicked.connect(lambda checked=False: _cancel())

        self._list_lay.addWidget(row)

    # ── row context menu ──────────────────────────────────────────────
    def _show_row_menu(self, filename, chat_collection, pos):
        from qtpy.QtWidgets import QMenu
        menu = QMenu(self)
        move_menu = menu.addMenu("移动到 \u2192")
        # Default
        if chat_collection != "":
            act = move_menu.addAction("默认")
            act.triggered.connect(
                lambda checked=False, f=filename, fc=chat_collection:
                    self._move_chat(f, fc, ""))
        for coll in list_collections():
            if coll == chat_collection:
                continue
            act = move_menu.addAction(coll)
            act.triggered.connect(
                lambda checked=False, f=filename, fc=chat_collection, tc=coll:
                    self._move_chat(f, fc, tc))
        if move_menu.isEmpty():
            move_menu.addAction("（无其他集合）").setEnabled(False)
        # Map local pos to global using the widget that emitted the signal
        sender = self.sender()
        global_pos = sender.mapToGlobal(pos) if sender else pos
        menu.exec_(global_pos)

    def _move_chat(self, filename, from_collection, to_collection):
        ok = move_chat(filename, from_collection, to_collection)
        if ok:
            # If the moved chat is the currently open one, update tracking
            if (filename == self._current_file and
                    from_collection == self._current_file_collection):
                self._current_file_collection = to_collection
                ref = _encode_chat_ref(to_collection, filename)
                self.load_chat.emit(ref)   # re-emit so panel updates _current_collection
            self._refresh(self._search.text().strip())

    def _on_load(self, ref):
        self.hide()
        self.load_chat.emit(ref)

    def _on_delete(self, filename, collection):
        delete_chat(filename, collection=collection)
        ref = _encode_chat_ref(collection, filename)
        self.del_chat.emit(ref)
        self._refresh(self._search.text().strip())





# ---------------------------------------------------------------------------
# Chat API worker
# ---------------------------------------------------------------------------
class _ChatWorker(QObject):
    chunk_ready = Signal(str)
    finished    = Signal()
    error       = Signal(str)

    def __init__(self, api_url, api_key, model, messages, extra_params=None):
        super().__init__()
        self._url          = api_url.rstrip("/")
        self._key          = api_key
        self._model        = model
        self._messages     = messages
        self._extra_params = extra_params or {}
        self._stop         = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import urllib.request
            import urllib.error
            body = {
                "model": self._model,
                "messages": self._messages,
                "stream": True,
            }
            body.update(self._extra_params)
            payload = json.dumps(body).encode()
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "spyder-ai-chat/0.1.2",
            }
            if self._key:
                headers["Authorization"] = f"Bearer {self._key}"
            req = urllib.request.Request(
                f"{self._url}/chat/completions",
                data=payload, headers=headers, method="POST")
            try:
                resp_cm = urllib.request.urlopen(req, timeout=120)
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode(errors="replace")[:300]
                except Exception:
                    body = ""
                self.error.emit(f"HTTP {e.code} {e.reason}: {body}")
                return
            with resp_cm as resp:
                for raw in resp:
                    if self._stop:
                        break
                    line = raw.decode().strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    try:
                        d = json.loads(line)
                        t = d["choices"][0]["delta"].get("content", "")
                        if t:
                            self.chunk_ready.emit(t)
                    except Exception:
                        logger.debug("Failed to parse SSE chunk: %r", line,
                                     exc_info=True)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


# ---------------------------------------------------------------------------
# Inference Parameters Popup
# ---------------------------------------------------------------------------
class _InferParamsPopup(QFrame):
    """
    Popup for configuring per-chat inference hyperparameters.
    Shows all params supported by the current provider as a flat form.
    No scroll bar — the popup expands to fit its content naturally.
    Anchors ABOVE the button that opens it.
    Changes apply immediately to the parent panel's _infer_params dict.
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)

        self._panel = None
        self._provider_id = "custom"

        # Outer layout — no scroll area; just a plain VBox that sizes to content
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(8, 8, 8, 8)
        self._outer.setSpacing(4)

        # Header row
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 2)
        hdr_lbl = QLabel("推理参数")
        hdr_lbl.setStyleSheet("font-weight: bold; font-size: 11px;")
        hdr.addWidget(hdr_lbl, 1)
        self._reset_btn = QPushButton("恢复默认")
        self._reset_btn.setFlat(True)
        self._reset_btn.setStyleSheet(
            "QPushButton { color: #888; font-size: 9px; padding: 1px 6px; "
            "border: 1px solid #555; border-radius: 3px; }"
            "QPushButton:hover { color: #f88; border-color: #f88; }")
        self._reset_btn.clicked.connect(self._on_reset)
        hdr.addWidget(self._reset_btn)
        self._outer.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #444;")
        self._outer.addWidget(sep)

        # Placeholder — will be replaced by _rebuild_controls()
        self._form_widget = QWidget()
        self._outer.addWidget(self._form_widget)

        # Notes label (provider-specific warnings)
        self._notes_lbl = QLabel()
        self._notes_lbl.setWordWrap(True)
        self._notes_lbl.setStyleSheet(
            "color: #c8a000; font-size: 9pt; padding: 4px 2px 0 2px;")
        self._notes_lbl.setVisible(False)
        self._outer.addWidget(self._notes_lbl)

    # ── public API ────────────────────────────────────────────────────

    def show_above(self, btn, panel):
        """Build controls for panel's current provider and show above btn."""
        self._panel = panel
        state = panel._load_state()
        self._provider_id = state.get("provider_type", "custom")
        self._rebuild_controls()

        # Let Qt compute the natural size before positioning
        self.adjustSize()

        # Anchor: bottom-right of popup aligns to top-right of button
        btn_top_right = btn.mapToGlobal(btn.rect().topRight())
        popup_x = btn_top_right.x() - self.width()
        popup_y = btn_top_right.y() - self.height()

        # Clamp to screen
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            popup_x = max(screen.left(), min(popup_x, screen.right() - self.width()))
            popup_y = max(screen.top(), popup_y)
        except Exception:
            pass

        self.move(popup_x, popup_y)
        self.show()
        self.raise_()

    # ── control building ──────────────────────────────────────────────

    def _rebuild_controls(self):
        """Replace form widget with fresh controls for the current provider."""
        # Detach old form widget and schedule deletion
        old = self._form_widget
        old.setParent(None)
        old.deleteLater()

        pdef      = PROVIDERS.get(self._provider_id, PROVIDERS["custom"])
        supported = pdef["supported_params"]
        temp_max  = pdef.get("temperature_max", 2.0)
        params    = self._panel._infer_params if self._panel else {}

        # All params in display order (basic first, then advanced — no toggle)
        all_params = [
            "temperature", "max_tokens", "top_p",
            "presence_penalty", "frequency_penalty",
            "top_k", "min_p", "repetition_penalty",
            "seed", "num_ctx",
        ]

        self._form_widget = QWidget()
        form_lay = QVBoxLayout(self._form_widget)
        form_lay.setContentsMargins(0, 4, 0, 0)
        form_lay.setSpacing(4)

        self._ctrl_widgets = {}

        for pid in all_params:
            if pid not in supported:
                continue
            pinfo = PARAM_DEFS[pid]
            t_max = temp_max if pid == "temperature" else None
            row   = self._make_param_row(pid, pinfo, params, t_max)
            form_lay.addWidget(row)

        # Insert before notes label (which is the last item in outer)
        # outer layout: hdr(0), sep(1), form(2-old→removed), notes(last)
        # After removing old form we insert at position 2
        self._outer.insertWidget(2, self._form_widget)

        # Notes
        notes = pdef.get("notes", "")
        self._notes_lbl.setText(notes)
        self._notes_lbl.setVisible(bool(notes))

    def _make_param_row(self, pid, pinfo, current_params, temp_max=None):
        """Create a single label + spinbox row."""
        label_text, ptype, prange, tooltip = pinfo

        row = QWidget()
        rl  = QHBoxLayout(row)
        rl.setContentsMargins(2, 1, 2, 1)
        rl.setSpacing(8)

        lbl = QLabel(label_text + ":")
        lbl.setFixedWidth(140)
        lbl.setStyleSheet("font-size: 9pt;")
        lbl.setToolTip(tooltip)
        rl.addWidget(lbl)

        current_val = current_params.get(pid)

        if ptype == "float":
            lo, hi = prange
            if temp_max is not None:
                hi = temp_max

            sp = QDoubleSpinBox()
            sp.setRange(lo, hi)
            sp.setSingleStep(0.05)
            sp.setDecimals(2)
            sp.setFixedWidth(90)
            # 0.0 as minimum → special "default" text
            sp.setSpecialValueText("default")
            sp.setValue(float(current_val) if current_val is not None else 0.0)

            def _on_float(val, p=pid, s=sp):
                if not self._panel:
                    return
                if val == s.minimum():
                    self._panel._infer_params.pop(p, None)
                else:
                    self._panel._infer_params[p] = val
                self._panel._update_summary_bar()

            sp.valueChanged.connect(_on_float)
            rl.addWidget(sp)
            self._ctrl_widgets[pid] = sp

        elif ptype == "int":
            _, hi = prange
            sp = QSpinBox()
            sp.setRange(0, hi)   # 0 = "default"
            sp.setFixedWidth(100)
            sp.setSpecialValueText("default")
            sp.setValue(int(current_val) if current_val is not None else 0)

            def _on_int(val, p=pid):
                if not self._panel:
                    return
                if val == 0:
                    self._panel._infer_params.pop(p, None)
                else:
                    self._panel._infer_params[p] = val
                self._panel._update_summary_bar()

            sp.valueChanged.connect(_on_int)
            rl.addWidget(sp)
            self._ctrl_widgets[pid] = sp

        rl.addStretch()
        return row

    def _on_reset(self):
        if self._panel:
            self._panel._infer_params.clear()
            self._panel._update_summary_bar()
        self._rebuild_controls()
        self.adjustSize()


# ---------------------------------------------------------------------------
# Model dropdown popup
# ---------------------------------------------------------------------------
class _ModelPopup(QFrame):
    selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)
        self._lw = QListWidget()
        self._lw.setFrameShape(QFrame.NoFrame)
        self._lw.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._lw.itemClicked.connect(
            lambda item: (self.selected.emit(item.text()), self.hide()))
        lay.addWidget(self._lw)

    def _apply_theme(self):
        """Inherit application theme — no custom stylesheet needed."""
        self.setStyleSheet("")
        self._lw.setStyleSheet("")

    def show_below(self, btn, models, current):
        self._apply_theme()
        self._lw.clear()
        for m in models:
            item = QListWidgetItem(m)
            if m == current:
                f = item.font(); f.setBold(True); item.setFont(f)
            self._lw.addItem(item)
        row_h = max(self._lw.sizeHintForRow(0), 24)
        self._lw.setFixedHeight(min(row_h * len(models) + 4, 350))
        self.setFixedWidth(max(btn.width(), 200))
        self.adjustSize()
        self.move(btn.mapToGlobal(btn.rect().bottomLeft()))
        self.show()
        self.raise_()


from .markdown_renderer import (
    render_markdown, parse_blocks,
    build_heading, build_paragraph, build_code_block, build_hr,
    build_blockquote, build_list, build_table, build_think,
    build_action_block,
)
from .settings_dialog import (
    SettingsDialog, EDITOR_DEFAULTS, HISTORY_DEFAULTS, AGENTIC_DEFAULTS,
    PROVIDERS, PROVIDER_ORDER, PARAM_DEFS,
)
from .system_prompts import load_prompts, get_prompt, CUSTOM_ID


# ---------------------------------------------------------------------------
# Helper: assemble LLM message content from structured storage
# ---------------------------------------------------------------------------
def _build_llm_content(msg):
    """
    Build the content string to send to the LLM from a stored message dict.
    New format: {"role": "user", "content": "user text",
                 "content_llm": "expanded command text (if commands were used)",
                 "command_spans": [[start, length], ...],
                 "attachments": [{"name": "file.py", "content": "..."}]}
    Old format: {"role": "user", "content": "File: ...\n```\n...\n```\n\ntext"}
                 — returned as-is for backwards compatibility.
    content_llm is used when present so the original expansion is preserved
    even if the command is later edited or deleted in Settings.
    """
    import os
    text        = msg.get("content_llm") or msg.get("content", "")
    attachments = msg.get("attachments", [])
    proj_block  = msg.get("project_context_block", "")

    parts = []
    if proj_block:
        parts.append(proj_block)

    if not attachments and not parts:
        return text  # no attachments, or legacy format

    for att in attachments:
        name    = att.get("name", "")
        content = att.get("content", "")
        ext  = os.path.splitext(name)[1].lower()
        lang = {".py": "python", ".js": "javascript", ".ts": "typescript",
                ".html": "html", ".css": "css", ".json": "json",
                ".md": "markdown", ".txt": ""}.get(ext, "")
        fence = f"```{lang}" if lang else "```"
        parts.append(f"File: {name}\n{fence}\n{content}\n```")
    all_blocks = "\n\n".join(parts)
    return f"{all_blocks}\n\n{text}" if text else all_blocks


# ---------------------------------------------------------------------------
# The chat history display
# ---------------------------------------------------------------------------
class _ChatHistory(QWidget):

    insert_to_editor = Signal(str)
    action_blocks_ready = Signal(dict)   # emitted after finalize_assistant when actions present

    _SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(4, 4, 4, 4)
        self._lay.setSpacing(6)
        self._lay.setAlignment(Qt.AlignTop)
        # Expand horizontally to fill scroll area width (needed for word-wrap),
        # but only take as much vertical space as the content actually needs
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._blocks = []
        self._stream_container = None
        self._stream_lbl       = None
        self._spinner_lbl      = None
        self._spinner_timer    = None
        self._spinner_frame    = 0
        self._rendered_zone          = None  # QVBoxLayout for incrementally rendered blocks
        self._rendered_block_count   = 0     # blocks already pushed to _rendered_zone
        self._scroll_to_bottom_cb = None  # callable, fired once after next resize
        self._action_env             = None  # passed from AIChatPanel when agentic ON
        self._current_executed_blocks = set()  # block indices already executed (history)
        self._bulk_loading = False  # True while loading from file — skips per-message layout ops
        self._agentic_tip_popup      = None  # shared _AgenticTooltipPopup (lazy)

    # Signal(block_index, delete_before_too, role)
    # Signal(block_index, delete_before_too)
    delete_exchange = Signal(int, bool)
    # Signal() — regenerate the last assistant response
    regenerate = Signal()

    def _get_agentic_popup(self):
        """Return (and lazily create) the shared _AgenticTooltipPopup."""
        if self._agentic_tip_popup is None:
            self._agentic_tip_popup = _AgenticTooltipPopup()
        return self._agentic_tip_popup

    def _make_delete_bar(self, block_idx_fn):
        """
        Return a QWidget containing the delete action buttons for one message.
        block_idx_fn: callable returning the current block index at click time.
        """
        bar = QWidget()
        bar.setStyleSheet("background: transparent;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)
        bl.addStretch()

        btn_this   = QPushButton("🗑 此条")
        btn_before = QPushButton("⏫ 之前全部")
        _install_themed_tip(
            btn_this,
            "从聊天中删除此轮对话（你的消息 + AI 回复）")
        _install_themed_tip(
            btn_before,
            "删除此条之前的所有对话（保留本条）")
        for btn in (btn_this, btn_before):
            btn.setFlat(True)
            btn.setStyleSheet(
                "QPushButton { color: #888; font-size: 9px; padding: 1px 5px; "
                "border: 1px solid #555; border-radius: 3px; background: transparent; }"
                "QPushButton:hover { color: #f88; border-color: #f88; }")
        bl.addWidget(btn_before)
        bl.addWidget(btn_this)

        _state = {"timer": None, "pending": None}

        def _arm(delete_before):
            if _state["timer"] is not None:
                _state["timer"].stop()
            _state["pending"] = delete_before
            btn_this.setVisible(False)
            btn_before.setVisible(False)
            cancel_btn.setText("↩ 取消 (3)")
            cancel_btn.setVisible(True)
            remaining = [3]

            def _tick():
                remaining[0] -= 1
                if remaining[0] > 0:
                    cancel_btn.setText(f"↩ Cancel ({remaining[0]})")
                else:
                    _state["timer"].stop()
                    cancel_btn.setVisible(False)
                    btn_this.setVisible(True)
                    btn_before.setVisible(True)
                    self.delete_exchange.emit(block_idx_fn(), _state["pending"])

            t = QTimer(bar)
            t.setInterval(1000)
            t.timeout.connect(_tick)
            t.start()
            _state["timer"] = t

        def _cancel():
            if _state["timer"]:
                _state["timer"].stop()
                _state["timer"] = None
            cancel_btn.setVisible(False)
            btn_this.setVisible(True)
            btn_before.setVisible(True)

        cancel_btn = QPushButton("↩ 取消 (3)")
        cancel_btn.setFlat(True)
        cancel_btn.setStyleSheet(
            "QPushButton { color: #f88; font-size: 9px; padding: 1px 5px; "
            "border: 1px solid #f88; border-radius: 3px; background: transparent; }"
            "QPushButton:hover { color: #fcc; border-color: #fcc; }")
        cancel_btn.setVisible(False)
        cancel_btn.clicked.connect(_cancel)
        bl.addWidget(cancel_btn)

        btn_this.clicked.connect(lambda: _arm(False))
        btn_before.clicked.connect(lambda: _arm(True))

        return bar

    def _make_regenerate_btn(self):
        """Return a small Regenerate button that emits self.regenerate."""
        btn = QPushButton("🔄 重新生成")
        btn.setFlat(True)
        _install_themed_tip(btn, "放弃此回复并让模型重新回答")
        btn.setStyleSheet(
            "QPushButton { color: #888; font-size: 9px; padding: 1px 5px; "
            "border: 1px solid #555; border-radius: 3px; background: transparent; }"
            "QPushButton:hover { color: #4ec9b0; border-color: #4ec9b0; }")
        btn.clicked.connect(self.regenerate.emit)
        return btn

    def _update_regenerate_button(self):
        """
        Ensure only the last assistant block has a Regenerate button.
        Scans all blocks, removes any existing regenerate buttons,
        then injects one into the last assistant block's title row.
        """
        # Remove existing regenerate buttons from all title rows
        for role, container in self._blocks:
            lay = container.layout()
            if lay and lay.count() > 0:
                first_item = lay.itemAt(0)
                if first_item and first_item.layout():
                    title_row = first_item.layout()
                    for i in range(title_row.count() - 1, -1, -1):
                        item = title_row.itemAt(i)
                        if item and item.widget():
                            w = item.widget()
                            if (isinstance(w, QPushButton) and
                                    "Regenerate" in w.text()):
                                title_row.removeWidget(w)
                                w.deleteLater()

        # Find last assistant or error block and inject regenerate button
        last_asst = None
        for role, container in reversed(self._blocks):
            if role in ("assistant", "assistant_error"):
                last_asst = container
                break
        if last_asst is None:
            return
        lay = last_asst.layout()
        if lay and lay.count() > 0:
            first_item = lay.itemAt(0)
            if first_item and first_item.layout():
                title_row = first_item.layout()
                # Insert before the delete bar (last widget)
                regen_btn = self._make_regenerate_btn()
                title_row.insertWidget(title_row.count() - 1, regen_btn)

    def request_scroll_to_bottom(self, callback):
        """Ask to fire callback once after the next resize (layout settled)."""
        self._scroll_to_bottom_cb = callback

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._scroll_to_bottom_cb is not None:
            cb = self._scroll_to_bottom_cb
            self._scroll_to_bottom_cb = None
            cb()

    # ── user bubble ───────────────────────────────────────────────────
    def add_user(self, text, attachments=None, command_spans=None,
                 agentic_response=False, agentic_tooltip=None):
        """
        Add a user message bubble.
        attachments:      optional list of attachment name strings (locked badges).
        command_spans:    optional list of (start, length) tuples marking active
                          command tokens — rendered with a green highlight.
        agentic_response: if True the block is wrapped in a collapsible frame
                          collapsed by default (used for auto-sent action results).
        agentic_tooltip:  optional str shown as a tooltip on the agentic header bar.
                          When set, clicking the header does NOT expand the content.
        """
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(2)

        # outer is the widget actually added to the layout / _blocks list.
        # For agentic_response it is a wrapper frame; otherwise it is container.
        # We use a list so the lambda closes over a mutable reference.
        _outer_ref = [None]
        block_idx_fn = lambda: next(
            (i for i, b in enumerate(self._blocks) if b[1] is _outer_ref[0]), -1)

        # Title row: "You:" on left, delete buttons on right
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        if not agentic_response:
            title = QLabel("<b>你：</b>")
            title.setStyleSheet("color: #569cd6;")
            title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self._make_delete_bar(block_idx_fn))
        cl.addLayout(title_row)

        # Build label content — highlight command spans if present
        if command_spans:
            # Build rich-text with highlighted command tokens
            import html as _html
            spans = sorted(command_spans, key=lambda s: s[0])
            result = ""
            prev = 0
            for (s, l) in spans:
                result += _html.escape(text[prev:s])
                result += (
                    f'<span style="background:#2a3a1a; color:#b8e090; '
                    f'border-radius:3px; padding:0 2px;">'
                    f'{_html.escape(text[s:s+l])}</span>'
                )
                prev = s + l
            result += _html.escape(text[prev:])
            # Preserve newlines
            result = result.replace("\n", "<br>")
            w = QLabel(result)
            w.setTextFormat(Qt.RichText)
        else:
            w = QLabel(text)
            w.setTextFormat(Qt.PlainText)

        w.setWordWrap(True)
        w.setFont(QFont("Monospace", 10))
        w.setStyleSheet(
            "background: transparent; border-left: 3px solid #569cd6; "
            "padding: 4px 8px;")
        w.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        cl.addWidget(w)

        # Locked attachment badges (no X button — already sent)
        # Each entry may be a plain name string or {"name": ..., "content": ...}.
        if attachments:
            badge_row = QWidget()
            badge_row.setStyleSheet("background: transparent;")
            bl = QHBoxLayout(badge_row)
            bl.setContentsMargins(8, 2, 0, 0)
            bl.setSpacing(4)
            for att in attachments:
                if isinstance(att, dict):
                    name    = att.get("name", "")
                    content = att.get("content", "")
                else:
                    name    = att
                    content = ""
                icon = "✂" if " selection" in name else "📎"
                tag = QFrame()
                if _is_dark_theme():
                    _att_bg, _att_bd, _att_fg = "#1e3a1e", "#3a6a3a", "#7ec87e"
                else:
                    _att_bg, _att_bd, _att_fg = "#e8f5e8", "#5a9a5a", "#1a5a1a"
                tag.setStyleSheet(
                    f"QFrame {{ background: {_att_bg}; border: 1px solid {_att_bd}; "
                    "border-radius: 3px; }")
                tl = QHBoxLayout(tag)
                tl.setContentsMargins(5, 1, 5, 1)
                tl.setSpacing(3)
                lbl = QLabel(f"{icon} {name}")
                lbl.setStyleSheet(
                    f"color: {_att_fg}; font-size: 9px; border: none; "
                    "background: transparent;")
                tl.addWidget(lbl)
                # Hover popup: first 25 lines of content via scrollable themed popup
                if content:
                    _lines = content.split("\n")
                    _preview = "\n".join(_lines[:25])
                    if len(_lines) > 25:
                        _preview += f"\n… ({len(_lines) - 25} more lines)"
                    _hf = _AgenticHoverFilter(self._get_agentic_popup(), _preview, tag)
                    tag.installEventFilter(_hf)
                bl.addWidget(tag)
            bl.addStretch()
            cl.addWidget(badge_row)

        if agentic_response:
            outer = QFrame()
            outer.setObjectName("agOuter")
            outer.setStyleSheet(
                "QFrame#agOuter { border-left: 3px solid #569cd6; "
                "border-radius: 0px; background: transparent; }")
            outer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            ol = QVBoxLayout(outer)
            ol.setContentsMargins(6, 2, 0, 2)
            ol.setSpacing(0)

            # Header bar — clickable only when there is no tooltip (no hidden content)
            hdr = QFrame()
            if _is_dark_theme():
                hdr.setStyleSheet(
                    "QFrame { background: #1a1a2a; border: 1px solid #44446a; "
                    "border-radius: 3px; padding: 2px; }")
                _ag_icon_color = "#6666aa"
                _ag_text_color = "#8888bb"
            else:
                hdr.setStyleSheet(
                    "QFrame { background: #eeeeff; border: 1px solid #8888cc; "
                    "border-radius: 3px; padding: 2px; }")
                _ag_icon_color = "#5555aa"
                _ag_text_color = "#3333aa"
            hl = QHBoxLayout(hdr)
            hl.setContentsMargins(6, 3, 6, 3)
            hl.setSpacing(6)
            toggle_lbl = QLabel("⚙")
            toggle_lbl.setStyleSheet(
                f"color: {_ag_icon_color}; font-size: 9px; background: transparent;")
            hdr_lbl = QLabel("代理输出")
            hdr_lbl.setStyleSheet(
                f"color: {_ag_text_color}; font-size: 10px; background: transparent;")
            hl.addWidget(toggle_lbl)
            hl.addWidget(hdr_lbl)
            hl.addStretch()
            ol.addWidget(hdr)

            if agentic_tooltip:
                # Hover popup mode: show full sent content in a scrollable panel.
                # Filter is installed only on hdr_lbl ("Agentic output" text) so
                # the popup appears only when hovering that label — not when the
                # mouse passes over the rest of the header bar unintentionally.
                hdr.setCursor(Qt.ArrowCursor)
                _hover_ef = _AgenticHoverFilter(
                    self._get_agentic_popup(), agentic_tooltip, hdr_lbl)
                hdr_lbl.installEventFilter(_hover_ef)
                hdr_lbl.setCursor(Qt.WhatsThisCursor)  # hint that hover does something
                # Content hidden and non-expandable
                container.setVisible(False)
                ol.addWidget(container)
            else:
                # Legacy: clickable toggle (no tooltip content available)
                hdr.setCursor(Qt.PointingHandCursor)
                container.setVisible(False)
                ol.addWidget(container)

                def _toggle():
                    vis = not container.isVisible()
                    container.setVisible(vis)
                    toggle_lbl.setText("▼" if vis else "⚙")

                # Use an event filter to intercept mouse-press without
                # replacing mousePressEvent (which bypasses Qt's event chain).
                _ef = _ClickEventFilter(_toggle, hdr)
                hdr.installEventFilter(_ef)
        else:
            outer = container

        _outer_ref[0] = outer
        self._lay.addWidget(outer)
        self._blocks.append(("user", outer))
        if not self._bulk_loading:
            self._lay.activate()
            if outer.layout():
                outer.layout().activate()
            self._lay.invalidate()

    # ── assistant: streaming placeholder ─────────────────────────────
    def add_assistant_start(self):
        """Create a plain streaming label. Returns the QLabel to write into."""
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(2)

        # Title row: "AI:" on left, delete buttons on right
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title = QLabel("<b>AI：</b>")
        title.setStyleSheet("color: #4ec9b0;")
        title_row.addWidget(title)
        title_row.addStretch()
        block_idx_fn = lambda: next(
            (i for i, b in enumerate(self._blocks) if b[1] is container), -1)
        title_row.addWidget(self._make_delete_bar(block_idx_fn))
        cl.addLayout(title_row)
        # Spinner shown while waiting for the first response token
        spinner = QLabel(self._SPINNER_FRAMES[0])
        spinner.setStyleSheet(
            "color: #4ec9b0; font-size: 14px; padding: 4px 8px;")
        cl.addWidget(spinner)
        self._spinner_lbl   = spinner
        self._spinner_frame = 0
        timer = QTimer(self)
        timer.timeout.connect(self._spinner_tick)
        timer.start(80)
        self._spinner_timer = timer

        # Rendered zone: completed blocks are added here incrementally
        rz_widget = QWidget()
        rz_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._rendered_zone = QVBoxLayout(rz_widget)
        self._rendered_zone.setContentsMargins(0, 0, 0, 0)
        self._rendered_zone.setSpacing(3)
        self._rendered_block_count = 0
        cl.addWidget(rz_widget)

        # Tail label: shows the current (potentially incomplete) block as plain text
        lbl = QLabel()
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.PlainText)
        lbl.setFont(QFont("Monospace", 10))
        lbl.setStyleSheet(
            "background: transparent; border-left: 3px solid #4ec9b0; "
            "padding: 4px 8px;")
        lbl.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        lbl.hide()   # shown only after first response token arrives
        cl.addWidget(lbl)
        self._lay.addWidget(container)
        self._blocks.append(("assistant_streaming", container))
        self._stream_container = container
        self._stream_lbl       = lbl
        if not self._bulk_loading:
            self._lay.activate()
            if container.layout():
                container.layout().activate()
            self._lay.invalidate()
        return lbl

    def _spinner_tick(self):
        if self._spinner_lbl is None:
            return
        self._spinner_frame = (self._spinner_frame + 1) % len(self._SPINNER_FRAMES)
        self._spinner_lbl.setText(self._SPINNER_FRAMES[self._spinner_frame])

    def hide_spinner(self):
        """Stop and remove the waiting spinner (called on first chunk or error)."""
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        if self._spinner_lbl is not None:
            self._spinner_lbl.setParent(None)
            self._spinner_lbl.deleteLater()
            self._spinner_lbl = None

    def remove_streaming_block(self):
        """Remove the in-progress streaming block without finalising it.

        Called when the user stops a response before any tokens have arrived.
        Leaves self._blocks and the widget tree in a clean state that matches
        self._messages exactly — no orphaned empty assistant block."""
        self.hide_spinner()
        container = self._stream_container
        if container is not None:
            self._blocks = [b for b in self._blocks if b[1] is not container]
            container.setParent(None)
            container.deleteLater()
        if self._stream_lbl is not None:
            self._stream_lbl.setParent(None)
            self._stream_lbl.deleteLater()
            self._stream_lbl = None
        self._stream_container     = None
        self._rendered_zone        = None
        self._rendered_block_count = 0

    def push_rendered_widget(self, widget):
        """Append a pre-built widget to the rendered zone (no block parsing)."""
        if self._rendered_zone is None:
            return
        self._rendered_zone.addWidget(widget)
        self._rendered_block_count += 1

    def push_rendered_block(self, block):
        """Build one block widget and append it to the rendered zone."""
        if self._rendered_zone is None:
            return
        from .settings_dialog import EDITOR_DEFAULTS
        cfg = {**EDITOR_DEFAULTS, **(getattr(self, "_font_cfg", None) or {})}
        try:
            from spyder.config.gui import is_dark_interface
            text_color = "#d4d4d4" if is_dark_interface() else "#1a1a1a"
        except Exception:
            text_color = "#d4d4d4"
        t = block["type"]
        if   t == "heading":    w = build_heading(block, cfg["fs_heading"])
        elif t == "paragraph":  w = build_paragraph(block, text_color, cfg["fs_base"])
        elif t == "code":       w = build_code_block(block, self.insert_to_editor, cfg["fs_code"])
        elif t == "action":
            # Augment action_env with per-block index and executed set for persistence
            aenv = dict(self._action_env) if self._action_env else {}
            aenv["_block_idx"]      = self._rendered_block_count
            aenv["_executed_blocks"] = getattr(self, "_current_executed_blocks", set())
            w = build_action_block(block, aenv, cfg["fs_code"])
        elif t == "hr":         w = build_hr()
        elif t == "blockquote": w = build_blockquote(block, text_color, cfg["fs_base"])
        elif t == "list":       w = build_list(block, text_color, cfg["fs_list"])
        elif t == "table":      w = build_table(block, cfg["fs_table"])
        elif t == "think":      w = build_think(block, cfg["fs_think"])
        else:                   return
        self._rendered_zone.addWidget(w)
        self._rendered_block_count += 1

    def show_error(self, msg):
        """Display an error response in a dark-red styled box. No Regenerate button."""
        self.hide_spinner()
        if self._stream_container is None:
            container = QWidget()
            container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            cl = QVBoxLayout(container)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(2)
            title_row = QHBoxLayout()
            title_row.setContentsMargins(0, 0, 0, 0)
            title = QLabel("<b>AI：</b>")
            title.setStyleSheet("color: #4ec9b0;")
            title_row.addWidget(title)
            title_row.addStretch()
            block_idx_fn = lambda c=container: next(
                (i for i, b in enumerate(self._blocks) if b[1] is c), -1)
            title_row.addWidget(self._make_delete_bar(block_idx_fn))
            cl.addLayout(title_row)
            self._lay.addWidget(container)
            self._blocks.append(("assistant_streaming", container))
            self._stream_container = container
            self._stream_lbl = None

        container = self._stream_container
        cl = container.layout()

        if self._stream_lbl is not None:
            self._stream_lbl.setParent(None)
            self._stream_lbl.deleteLater()
            self._stream_lbl = None

        header = QLabel("⚠ 发生响应错误")
        header.setStyleSheet(
            "color: #ff6b6b; font-weight: bold; background: #3d1515; "
            "border-radius: 3px; padding: 4px 8px;")
        cl.addWidget(header)

        err_lbl = QLabel(msg)
        err_lbl.setWordWrap(True)
        err_lbl.setTextFormat(Qt.PlainText)
        err_lbl.setStyleSheet(
            "color: #ffaaaa; background: #2a0d0d; "
            "border-left: 3px solid #8b2020; padding: 6px 10px;")
        err_lbl.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        cl.addWidget(err_lbl)

        for i, b in enumerate(self._blocks):
            if b[0] == "assistant_streaming" and b[1] is container:
                self._blocks[i] = ("assistant_error", container)
                break

        self._stream_container = None
        self._update_regenerate_button()

    # ── assistant: finalize with parsed code blocks ───────────────────
    def finalize_assistant(self, full_text):
        """
        Finalize a streaming response: render any not-yet-rendered blocks,
        remove the tail label, and add the 'Copy to editor' button if needed.
        Works both after streaming (container exists) and when loading from file.
        """
        self.hide_spinner()
        # Track whether this is a history load (no active streaming container).
        # Used below to trigger read-batch grouping, which is otherwise handled
        # by _on_action_blocks_ready for live responses.
        _is_history_load = (self._stream_container is None)
        # If no streaming container exists (e.g. loading from file), create one now
        if self._stream_container is None:
            container = QWidget()
            container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            cl = QVBoxLayout(container)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(2)
            title_row = QHBoxLayout()
            title_row.setContentsMargins(0, 0, 0, 0)
            title = QLabel("<b>AI：</b>")
            title.setStyleSheet("color: #4ec9b0;")
            title_row.addWidget(title)
            title_row.addStretch()
            block_idx_fn = lambda c=container: next(
                (i for i, b in enumerate(self._blocks) if b[1] is c), -1)
            title_row.addWidget(self._make_delete_bar(block_idx_fn))
            cl.addLayout(title_row)
            # Rendered zone for this (file-load) container
            rz_widget = QWidget()
            rz_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self._rendered_zone = QVBoxLayout(rz_widget)
            self._rendered_zone.setContentsMargins(0, 0, 0, 0)
            self._rendered_zone.setSpacing(3)
            self._rendered_block_count = 0
            cl.addWidget(rz_widget)
            self._lay.addWidget(container)
            self._blocks.append(("assistant_streaming", container))
            self._stream_container = container
            self._stream_lbl = None

        container = self._stream_container

        # Remove the tail (plain-text streaming) label
        if self._stream_lbl is not None:
            self._stream_lbl.setParent(None)
            self._stream_lbl.deleteLater()
            self._stream_lbl = None

        # Render any blocks not yet pushed during streaming
        blocks = parse_blocks(full_text)
        has_code = any(b["type"] == "code" for b in blocks)
        for block in blocks[self._rendered_block_count:]:
            self.push_rendered_block(block)

        # Update block record
        for i, b in enumerate(self._blocks):
            if b[0] == "assistant_streaming" and b[1] is container:
                self._blocks[i] = ("assistant", container)
                break

        # For history loads, group any batch read/ls/grep blocks now.
        # Live responses are grouped later by _on_action_blocks_ready (which also
        # runs _batch_execute), so we skip this path to avoid double-grouping.
        if _is_history_load and self._rendered_zone is not None:
            _group_read_frames_in_layout(self._rendered_zone)

        self._stream_container     = None
        self._rendered_zone        = None
        self._rendered_block_count = 0
        # During bulk history load these per-message layout recalculations would be
        # O(N²) — each sizeHint() traversal covers ALL previously-rendered messages.
        # They are skipped here and done once in _finish_load() instead.
        if not self._bulk_loading:
            # Force the container to recalculate its height now that the streaming
            # label (which may have been much taller than the rendered widgets) is gone.
            container.layout().activate()
            # _lay caches its sizeHint; invalidate it so the recomputed value reflects
            # the rendered widgets rather than the (now-removed) streaming label.
            self._lay.invalidate()
            # Synchronously resize _ChatHistory to the correct sizeHint height.
            # Without this the QScrollArea keeps the old (inflated) content height
            # until it processes the LayoutRequest asynchronously — leaving visible
            # empty space at the bottom of the chat that persists until the next
            # resize event.  Preserving self.width() ensures the scroll area's
            # viewport-width constraint is not disturbed.
            _correct_h = max(1, self._lay.sizeHint().height())
            if self.height() != _correct_h:
                self.resize(self.width(), _correct_h)
            self.updateGeometry()   # belt-and-suspenders: notify parent scroll area
            # _update_regenerate_button() scans all blocks (O(N)) — skip during bulk
            # load to avoid O(N²) total; called once from _finish_load() instead.
            self._update_regenerate_button()

        # action_blocks_ready is intentionally NOT emitted here.
        # It is emitted by AIChatPanel._on_done after the chat thread is cleared,
        # so it only fires for fresh LLM responses (not chat loads or re-renders).

    def add_compaction_block(self, summary_text):
        """Render a collapsible 📦 Compaction summary block (purple, collapsed by default)."""
        outer = QWidget()
        outer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        vl = QVBoxLayout(outer)
        vl.setContentsMargins(0, 4, 0, 4)
        vl.setSpacing(0)

        # Header bar (always visible, clickable to toggle body)
        hdr = _ClickableLabel("📦  压缩总结  ·  点击展开/折叠")
        if _is_dark_theme():
            hdr.setStyleSheet(
                "background: #2a1a4a; color: #c0a0f0; padding: 4px 8px; "
                "border-radius: 3px; font-size: 8pt; font-weight: bold;")
            _comp_body_color = "#c0a0f0"
        else:
            hdr.setStyleSheet(
                "background: #e8e0f8; color: #5a2aaa; padding: 4px 8px; "
                "border-radius: 3px; font-size: 8pt; font-weight: bold; "
                "border: 1px solid #b090e0;")
            _comp_body_color = "#4a1a8a"
        hdr.setFixedHeight(24)

        # Body (hidden by default)
        body_w = QWidget()
        body_v = QVBoxLayout(body_w)
        body_v.setContentsMargins(8, 4, 0, 4)
        body_lbl = QLabel(summary_text)
        body_lbl.setWordWrap(True)
        body_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body_lbl.setStyleSheet(f"color: {_comp_body_color}; font-size: 8pt;")
        body_v.addWidget(body_lbl)
        body_w.setVisible(False)

        hdr.clicked.connect(lambda: body_w.setVisible(not body_w.isVisible()))
        hdr.setCursor(Qt.PointingHandCursor)

        vl.addWidget(hdr)
        vl.addWidget(body_w)
        self._lay.addWidget(outer)
        self._blocks.append(("compaction", outer))

    def promote_last_to_compaction(self):
        """
        Replace the last assistant block with a compaction block.
        Called immediately after _on_done() marks the last message as compaction_summary.
        """
        if not self._blocks:
            return
        role, widget = self._blocks[-1]
        if role not in ("assistant", "assistant_streaming"):
            return
        # Find the summary text from the live _messages reference
        msgs_ref = getattr(self, "_messages_ref", [])
        summary_text = ""
        for m in reversed(msgs_ref):
            if m.get("compaction_summary"):
                summary_text = m.get("content", "")
                break
        # Remove the old assistant widget from layout and block list
        widget.setParent(None)
        widget.deleteLater()
        self._blocks.pop()
        # Render the compaction block in its place
        self.add_compaction_block(summary_text)

    def clear_all(self):
        for _, container in self._blocks:
            container.deleteLater()
        self._blocks.clear()
        self._stream_container     = None
        self._stream_lbl           = None
        self._rendered_zone        = None
        self._rendered_block_count = 0
        self.hide_spinner()


# ---------------------------------------------------------------------------
# Git status bar helpers
# ---------------------------------------------------------------------------
import re as _re

def _parse_porcelain_stat(porcelain):
    """
    Parse `git status --porcelain` output into a display string like
    '+N −N in N files  +U untracked' or '' when the working tree is clean.

    Porcelain line format: XY filename
      X = index (staged) status
      Y = worktree status
      '??' = untracked
    We count:
      - modified/deleted/renamed tracked files (any XY except '??' and '!!')
      - untracked files ('??')
    For tracked changes we also run --shortstat to get insertion/deletion counts.
    """
    if not porcelain.strip():
        return ""
    lines = porcelain.splitlines()
    tracked   = [l for l in lines if l[:2] not in ("??", "!!") and len(l) > 2]
    untracked = [l for l in lines if l.startswith("??")]
    parts = []
    if tracked:
        parts.append(f"{len(tracked)} changed")
    if untracked:
        parts.append(f"{len(untracked)} untracked")
    return "  ".join(parts) if parts else ""


class _GitStatusWorker(QObject):
    """Runs git queries off the UI thread. Emits result or failed."""
    result = Signal(str, str, bool)   # branch, diff_stat, is_dirty
    failed = Signal()

    def __init__(self, cwd):
        super().__init__()
        self._cwd = cwd

    # Timeout passed to every git subprocess — must be shorter than the poll
    # interval so a hung git process doesn't block more than one timer tick.
    _GIT_TIMEOUT = 8  # seconds

    def run(self):
        try:
            self._run()
        except Exception:
            self.failed.emit()

    def _run(self):
        from .agentic_actions import find_git
        import subprocess, sys
        git = find_git()
        if not git:
            self.failed.emit()
            return

        _flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        def _git(*args):
            r = subprocess.run(
                [git] + list(args),
                cwd=self._cwd,
                capture_output=True,
                text=True,
                timeout=self._GIT_TIMEOUT,
                creationflags=_flags,
            )
            return r.stdout, r.returncode

        _, rc = _git("rev-parse", "--git-dir")
        if rc != 0:
            self.failed.emit()
            return
        branch_out, _ = _git("rev-parse", "--abbrev-ref", "HEAD")
        branch = branch_out.strip() or "HEAD"
        if branch == "HEAD":
            branch = "(分离 HEAD)"
        # Use --porcelain so untracked files are included (git diff --shortstat
        # only covers tracked files with changes, missing brand-new files).
        porcelain_out, _ = _git("status", "--porcelain")
        diff_stat = _parse_porcelain_stat(porcelain_out)
        is_dirty  = bool(diff_stat)
        self.result.emit(branch, diff_stat, is_dirty)


class _GitActionWorker(QObject):
    """Gathers git data for Commit / PR desc / Changes buttons off the UI thread."""
    ready  = Signal(str)   # enriched prompt text ready to send
    failed = Signal(str)   # error message

    def __init__(self, cwd, action, branch=""):
        super().__init__()
        self._cwd    = cwd
        self._action = action
        self._branch = branch

    def run(self):
        from .agentic_actions import find_git, run_git_command

        def _g(*args):
            out, err, rc = run_git_command(list(args), cwd=self._cwd)
            if rc == 0:
                return out.strip()
            return f"(error: {err.strip() or ('rc=%d' % rc)})"

        if not find_git():
            self.failed.emit("git not found on PATH")
            return

        action = self._action

        if action == "commit":
            status   = _g("status", "--short") or "(clean)"
            cached   = _g("diff", "--cached")   or "(nothing staged)"
            unstaged = _g("diff")               or "(no unstaged changes)"
            # Truncate very large diffs so we don't blow the context window
            if len(cached)   > 6000: cached   = cached[:6000]   + "\n… (truncated)"
            if len(unstaged) > 6000: unstaged = unstaged[:6000] + "\n… (truncated)"
            prompt = (
                "以下是当前的 git 状态。\n\n"
                f"$ git status --short\n{status}\n\n"
                f"$ git diff --cached\n{cached}\n\n"
                f"$ git diff\n{unstaged}\n\n"
                "如果需要，请暂存未暂存的更改（run:git add），然后编写 "
                "合适的提交信息并提交（run:git commit）。"
                "每个命令使用单独的 run:git 代码围栏。"
            )

        elif action == "pr":
            branch = self._branch or "current branch"
            # Detect base branch
            _, _, rc = run_git_command(["rev-parse", "--verify", "main"],
                                        cwd=self._cwd)
            base = "main" if rc == 0 else "master"
            log  = _g("log",  f"{base}..HEAD", "--oneline") or "(no commits ahead)"
            stat = _g("diff", f"{base}..HEAD", "--stat")    or "(no changes)"
            diff = _g("diff", f"{base}..HEAD")
            if len(diff) > 8000:
                diff = diff[:8000] + "\n… (truncated)"
            prompt = (
                f"为分支 `{branch}`（与 `{base}` 对比）编写 GitHub Pull Request 描述。\n\n"
                f"$ git log {base}..HEAD --oneline\n{log}\n\n"
                f"$ git diff {base}..HEAD --stat\n{stat}\n\n"
                f"$ git diff {base}..HEAD\n{diff or '(无差异)'}"
            )

        else:  # changes
            status = _g("status", "--short") or "(clean)"
            stat   = _g("diff", "HEAD", "--stat") or "(no changes)"
            diff   = _g("diff", "HEAD")
            if len(diff) > 8000:
                diff = diff[:8000] + "\n… (truncated)"
            prompt = (
                "以下是当前未提交的 git 更改摘要：\n\n"
                f"$ git status --short\n{status}\n\n"
                f"$ git diff HEAD --stat\n{stat}\n\n"
                f"$ git diff HEAD\n{diff or '(无差异)'}\n\n"
                "请总结这些更改。"
            )

        self.ready.emit(prompt)


class _GitStatusBar(QWidget):
    """Compact bar: ⎇ branch  ●  +N −N in N files  [Commit] [PR desc] [Changes]"""
    action_requested = Signal(str)   # action key: "commit" | "pr" | "changes"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 1, 6, 1)
        lay.setSpacing(8)

        _branch_col = "#80c8f0" if _is_dark_theme() else "#1a5a8a"
        _stats_col  = "#a0c890" if _is_dark_theme() else "#2a6a2a"
        self._branch_lbl = QLabel("⎇ …")
        self._branch_lbl.setStyleSheet(
            f"color: {_branch_col}; font-size: 10px; background: transparent;")
        lay.addWidget(self._branch_lbl)

        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet(
            f"color: {_stats_col}; font-size: 10px; background: transparent;")
        lay.addWidget(self._stats_lbl)

        lay.addStretch(1)

        if _is_dark_theme():
            _btn_style = (
                "QPushButton { font-size: 9px; padding: 1px 7px; "
                "border: 1px solid #555; border-radius: 3px; "
                "color: #aaa; background: transparent; }"
                "QPushButton:hover { color: #eee; border-color: #888; }"
                "QPushButton:disabled { color: #484848; border-color: #3a3a3a; }"
            )
        else:
            _btn_style = (
                "QPushButton { font-size: 9px; padding: 1px 7px; "
                "border: 1px solid #aaa; border-radius: 3px; "
                "color: #333; background: transparent; }"
                "QPushButton:hover { color: #000; border-color: #666; }"
                "QPushButton:disabled { color: #bbb; border-color: #ccc; }"
            )
        self._commit_btn  = QPushButton("⎇ 提交")
        self._pr_btn      = QPushButton("⎇ PR 描述")
        self._changes_btn = QPushButton("? 更改")
        for btn in (self._commit_btn, self._pr_btn, self._changes_btn):
            btn.setFixedHeight(20)
            btn.setStyleSheet(_btn_style)
            lay.addWidget(btn)

        self._branch = ""
        self._commit_btn.clicked.connect(self._on_commit)
        self._pr_btn.clicked.connect(self._on_pr)
        self._changes_btn.clicked.connect(self._on_changes)

    def update_status(self, branch, diff_stat, is_dirty):
        self._branch = branch
        dot = "  \u25cf" if is_dirty else ""
        self._branch_lbl.setText(f"\u239b {branch}{dot}")
        self._stats_lbl.setText(diff_stat)

    def set_commit_enabled(self, enabled):
        self._commit_btn.setEnabled(enabled)
        _install_themed_tip(self._commit_btn,
            "Review diff and commit (requires Agentic mode + Allow git)"
            if not enabled else "Review diff and write a commit message")

    def _on_commit(self):
        self.action_requested.emit("commit")

    def _on_pr(self):
        self.action_requested.emit("pr")

    def _on_changes(self):
        self.action_requested.emit("changes")


# ---------------------------------------------------------------------------
# Page navigation bar — shown below the chat scroll area when total pages > 1
# ---------------------------------------------------------------------------
class _PageBar(QWidget):
    """Navigation bar with « ‹ [page numbers] › » buttons for multi-page chats."""

    page_requested = Signal(int)   # emits 0-indexed page number

    @staticmethod
    def _make_styles():
        """Return (nav, page_inactive, page_current) stylesheets for current theme."""
        if _is_dark_theme():
            nav = (
                "QPushButton { background: transparent; color: #bbb; "
                "border: 1px solid #555; border-radius: 3px; "
                "font-size: 10px; font-weight: bold; padding: 0px; }"
                "QPushButton:hover:enabled { color: #eee; border-color: #999; }"
                "QPushButton:disabled { color: #444; border-color: #3a3a3a; }"
            )
            inactive = (
                "QPushButton { background: transparent; color: #ccc; "
                "border: 1px solid #555; border-radius: 3px; "
                "font-size: 10px; padding: 0px; }"
                "QPushButton:hover:enabled { color: #eee; border-color: #999; }"
                "QPushButton:disabled { color: #444; border-color: #333; }"
            )
            current = (
                "QPushButton { background: #2d5a9e; color: #ffffff; "
                "border: 1px solid #4a80d4; border-radius: 3px; "
                "font-size: 10px; font-weight: bold; padding: 0px; }"
                "QPushButton:disabled { background: #2d5a9e; color: #ffffff; "
                "border: 1px solid #4a80d4; }"
            )
        else:
            nav = (
                "QPushButton { background: transparent; color: #444; "
                "border: 1px solid #aaa; border-radius: 3px; "
                "font-size: 10px; font-weight: bold; padding: 0px; }"
                "QPushButton:hover:enabled { color: #000; border-color: #666; }"
                "QPushButton:disabled { color: #bbb; border-color: #ccc; }"
            )
            inactive = (
                "QPushButton { background: transparent; color: #444; "
                "border: 1px solid #aaa; border-radius: 3px; "
                "font-size: 10px; padding: 0px; }"
                "QPushButton:hover:enabled { color: #000; border-color: #666; }"
                "QPushButton:disabled { color: #bbb; border-color: #ccc; }"
            )
            current = (
                "QPushButton { background: #2d5a9e; color: #ffffff; "
                "border: 1px solid #4a80d4; border-radius: 3px; "
                "font-size: 10px; font-weight: bold; padding: 0px; }"
                "QPushButton:disabled { background: #2d5a9e; color: #ffffff; "
                "border: 1px solid #4a80d4; }"
            )
        return nav, inactive, current

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 2, 3, 2)
        lay.setSpacing(2)
        self._first_btn = QPushButton("<<")
        self._prev_btn  = QPushButton("<")
        self._page_btns = [QPushButton() for _ in range(5)]
        self._next_btn  = QPushButton(">")
        self._last_btn  = QPushButton(">>")
        # Center the buttons by flanking with stretches
        lay.addStretch()
        for btn in (self._first_btn, self._prev_btn,
                    *self._page_btns, self._next_btn, self._last_btn):
            btn.setFixedHeight(22)
            btn.setFixedWidth(30)
            lay.addWidget(btn)
        lay.addStretch()
        # Apply nav-button style to << < > >> (theme-aware)
        _s_nav, _s_inactive, _s_current = self._make_styles()
        self._style_nav      = _s_nav
        self._style_inactive = _s_inactive
        self._style_current  = _s_current
        for btn in (self._first_btn, self._prev_btn,
                    self._next_btn, self._last_btn):
            btn.setStyleSheet(_s_nav)
        self._current = 0
        self._total   = 1
        self._first_btn.clicked.connect(lambda: self.page_requested.emit(0))
        self._prev_btn.clicked.connect(
            lambda: self.page_requested.emit(max(0, self._current - 1)))
        self._next_btn.clicked.connect(
            lambda: self.page_requested.emit(min(self._total - 1, self._current + 1)))
        self._last_btn.clicked.connect(
            lambda: self.page_requested.emit(self._total - 1))
        for i, btn in enumerate(self._page_btns):
            btn.clicked.connect(lambda _checked, idx=i: self._on_page_btn(idx))

    def update_state(self, current: int, total: int):
        self._current, self._total = current, total
        self._first_btn.setEnabled(current > 0)
        self._prev_btn.setEnabled(current > 0)
        self._next_btn.setEnabled(current < total - 1)
        self._last_btn.setEnabled(current < total - 1)
        # 5-number window centered on current (1-indexed), clamped so start >= 1
        cp1   = current + 1
        start = max(1, cp1 - 2)
        for i, btn in enumerate(self._page_btns):
            num    = start + i
            is_cur = (num == cp1)
            exists = num <= total
            btn.setText(str(num))
            btn.setEnabled(exists and not is_cur)
            btn.setStyleSheet(
                self._style_current if is_cur else self._style_inactive)

    def _on_page_btn(self, btn_idx: int):
        start  = max(1, self._current + 1 - 2)
        target = start + btn_idx - 1            # convert to 0-indexed
        if 0 <= target < self._total:
            self.page_requested.emit(target)


# ---------------------------------------------------------------------------
# Main chat panel — pure QWidget, no PluginMainWidget inheritance
# ---------------------------------------------------------------------------
class AIChatPanel(QWidget):

    _sig_models_ok  = Signal(list)
    _sig_models_err = Signal(str)

    def __init__(self, get_conf, set_conf, get_editor_cursor, parent=None):
        super().__init__(parent)
        self._get_editor_cursor = get_editor_cursor
        self._messages         = []
        self._assistant_buf    = ""
        self._model_list       = list(DEFAULT_MODELS)
        self._current_model    = DEFAULT_MODELS[0]
        self._fetching         = False
        self._chat_thread      = None
        self._chat_worker      = None
        self._current_lbl      = None
        self._context_files    = []   # list of (name, content, source) added as context
        self._selection_counters = {}  # filename -> selection count
        self._current_chat_file = None        # filename of currently saved chat
        self._current_collection = ""         # active collection ('' = Default)
        self._auto_scroll = True
        self._sp_selected_id = CUSTOM_ID  # currently selected system prompt id
        self._hist_popup = None           # created lazily
        self._params_popup = None         # created lazily
        # Per-chat inference params: only explicitly-set values (empty = use defaults)
        self._infer_params: dict = {}
        # Provider type active when this chat was opened (used to detect provider change)
        self._chat_provider: str = ""
        self._worker_had_error  = False
        self._rendered_char_end = 0   # chars of _assistant_buf already in rendered zone
        # Live streaming code/think block: QPlainTextEdit inside the in-progress widget
        self._streaming_code_edit  = None
        self._streaming_think_edit = None

        # ── Incremental chat-load state ────────────────────────────────
        self._load_seq            = 0    # monotonic; incremented per load to cancel stale batches
        self._load_pending_msgs   = []   # messages still to be rendered in current batch load
        self._load_total_msgs     = 0    # total messages in the current load (for progress %)
        self._load_ref_filename   = ""   # filename of the chat being loaded
        self._load_ref_collection = ""   # collection of the chat being loaded
        self._load_ref_data       = {}   # full data dict of the chat being loaded

        # ── Paging state ───────────────────────────────────────────────
        self._current_page   = 0     # 0-indexed currently rendered page
        self._page_rendering = False  # True when re-rendering a page (not a fresh file load)
        self._msgs_preloaded = False  # True when self._messages already has all msgs (suppress append)

        # ── Agentic actions state ─────────────────────────────────────
        self._console_execute_fn    = None    # callable(code:str) → None
        self._load_file_fn          = None    # callable(path:str) → None
        self._reload_file_fn        = None    # callable(path:str) → None  (patch reload)

        # ── Project context state ─────────────────────────────────────
        self._proj_enabled              = False   # toggle on/off
        self._proj_root                 = None    # project root path
        self._proj_included_folders     = []      # top-level folders selected in dialog
        self._proj_hashes               = {}      # {path: hash} at time of last send
        self._proj_all_sent             = False   # True once full context sent in this chat
        self._proj_changed_count        = 0       # stale files detected by watcher
        self._proj_ctx_token_estimate   = 0       # token estimate from folder selector
        # Plugin-provided callables (set via set_project_fns)
        self._get_project_root_fn   = None
        self._get_editor_widget_fn  = None

        # ── Git status bar state ──────────────────────────────────────
        self._git_branch    = ""
        self._git_diff_stat = ""
        self._git_dirty     = False
        self._git_thread    = None
        self._git_worker    = None
        self._git_pending_branch_change = False
        self._git_action_thread = None
        self._git_fail_count = 0   # retry counter — reset on success or project change
        self._git_action_worker = None
        self._pending_agentic_response   = False
        self._pending_compaction_request = False
        self._ag_groups: dict = {}   # id(first_asst_widget) → group-state dict

        # Periodic git refresh — catches working-tree edits that don't touch
        # .git/HEAD or .git/index (QFileSystemWatcher only fires for those).
        self._git_poll_timer = QTimer(self)
        _poll_secs = self._history_cfg().get("git_poll_interval", 10)
        self._git_poll_timer.setInterval(_poll_secs * 1000)
        self._git_poll_timer.timeout.connect(self._refresh_git_status)
        self._git_poll_timer.start()

        self._sig_models_ok.connect(self._on_models_ok)
        self._sig_models_err.connect(self._on_models_err)

        # Load persisted state from local JSON file (reliable across restarts)
        self._state = self._load_state()
        self._current_collection = self._state.get("current_collection", "")
        saved_models = self._state.get("model_list", [])
        if saved_models:
            self._model_list = saved_models
        saved_sel = self._state.get("selected_model", "")
        if saved_sel and saved_sel in self._model_list:
            self._current_model = saved_sel
        elif self._model_list:
            self._current_model = self._model_list[0]

        self._popup = None  # created lazily on first use

        self._build_ui()

        # Initialise chat_provider from global state (before any chat is loaded)
        self._chat_provider = self._load_state().get("provider_type", "openai")

        # Restore last open chat after the widget is first shown
        self._last_chat_restored = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._last_chat_restored:
            self._last_chat_restored = True
            last = self._load_state().get("last_chat_file")
            if last:
                from .chat_history_manager import load_chat as _lc
                _coll, _fname = _decode_chat_ref(last)
                if _lc(_fname, collection=_coll) is not None:  # file still exists
                    QTimer.singleShot(100, lambda: self._load_chat_from_file(last))

    # ── persistent state helpers ──────────────────────────────────────
    @staticmethod
    def _state_path():
        import os
        home = os.path.expanduser("~")
        d = os.path.join(home, ".spyder_ai_chat")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "state.json")

    def _load_state(self):
        try:
            with open(self._state_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_state(self, **kwargs):
        state = self._load_state()
        state.update(kwargs)
        try:
            with open(self._state_path(), "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _build_ui(self):
        # ── Override OS system QToolTip to match the current Spyder theme ──
        # Qt looks up the closest ancestor's stylesheet for QToolTip rules,
        # so setting it here covers all child widgets in the panel.
        if _is_dark_theme():
            self.setStyleSheet(
                "QToolTip { background: #1e2a2e; color: #d0d8d0; "
                "border: 1px solid #4a6a5a; padding: 2px 6px; }")
        else:
            self.setStyleSheet(
                "QToolTip { background: #f5f8f5; color: #111111; "
                "border: 1px solid #8aaa8a; padding: 2px 6px; }")

        # ── top bar ───────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setContentsMargins(4, 4, 4, 2)
        top.setSpacing(4)

        self._model_btn = QPushButton(self._current_model + " ▾")
        self._model_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _install_themed_tip(self._model_btn, "Select model")
        self._model_btn.clicked.connect(self._toggle_popup)
        top.addWidget(self._model_btn)

        self._reload_btn = QPushButton("⟳")
        _install_themed_tip(self._reload_btn, "Reload model list from API")
        self._reload_btn.setFixedWidth(36)
        self._reload_btn.setStyleSheet(
            "QPushButton { font-size: 16px; font-weight: bold; padding: 0px; }")
        self._reload_btn.clicked.connect(self._reload_models)
        top.addWidget(self._reload_btn)

        self._new_btn = QPushButton("+ 新聊天")
        _install_themed_tip(self._new_btn, "Clear conversation and start fresh")
        self._new_btn.clicked.connect(self._new_chat)
        top.addWidget(self._new_btn)

        self._cfg_btn = QPushButton("\u2699\uFE0E 设置")
        self._cfg_btn.clicked.connect(self._open_settings)
        top.addWidget(self._cfg_btn)

        self._hist_btn = QPushButton()
        _install_themed_tip(self._hist_btn, "Chat history")
        self._hist_btn.setFixedSize(28, 24)
        self._hist_btn.setStyleSheet("QPushButton { padding: 1px; border: none; }")
        # Inline SVG: document with checkmark lines
        _svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <path d="M6 2h9l4 4v16H5V2z" fill="none" stroke="currentColor" stroke-width="1.5"/>
  <path d="M14 2v5h5" fill="none" stroke="currentColor" stroke-width="1.5"/>
  <path d="M7 10l1.5 1.5L11 9" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  <line x1="12.5" y1="10" x2="17" y2="10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  <path d="M7 14l1.5 1.5L11 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  <line x1="12.5" y1="14" x2="17" y2="14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  <path d="M7 18l1.5 1.5L11 17" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  <line x1="12.5" y1="18" x2="17" y2="18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
</svg>"""
        from qtpy.QtSvg import QSvgRenderer
        from qtpy.QtGui import QPixmap, QPainter, QColor
        from qtpy.QtCore import QByteArray
        try:
            # Try to get foreground color from theme
            from spyder.config.gui import is_dark_interface
            icon_color = "#d4d4d4" if is_dark_interface() else "#333333"
        except Exception:
            icon_color = "#d4d4d4"
        svg_colored = _svg.replace(b"currentColor", icon_color.encode())
        renderer = QSvgRenderer(QByteArray(svg_colored))
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        from qtpy.QtGui import QIcon
        self._hist_btn.setIcon(QIcon(pixmap))
        self._hist_btn.setIconSize(pixmap.size())
        self._hist_btn.clicked.connect(self._toggle_history_popup)
        top.addWidget(self._hist_btn)

        # ── scrollable chat history ───────────────────────────────────
        from qtpy.QtWidgets import QScrollArea
        self._history = _ChatHistory()
        self._history._font_cfg = self._editor_cfg()
        self._apply_ui_font()
        self._history._messages_ref = self._messages   # live reference for compaction blocks
        self._history.setMinimumWidth(400)
        self._history.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        scroll = QScrollArea()
        scroll.setWidget(self._history)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        self._scroll = scroll
        self._auto_scroll = True
        scroll.verticalScrollBar().rangeChanged.connect(self._on_scroll_range_changed)

        # ── page navigation bar ───────────────────────────────────────
        self._page_bar = _PageBar()
        self._page_bar.setVisible(False)
        self._page_bar.page_requested.connect(self._navigate_to_page)

        # ── file context bar ──────────────────────────────────────────
        # Left column: wrapping flow of attachment tags (expands).
        # Right column: project toggle button (fixed, always visible).
        self._ctx_bar = QWidget()
        self._ctx_bar.setVisible(True)
        ctx_bar_outer = QHBoxLayout(self._ctx_bar)
        ctx_bar_outer.setContentsMargins(4, 2, 4, 2)
        ctx_bar_outer.setSpacing(6)

        # Left: flow layout for tags
        self._ctx_tags_widget = QWidget()
        self._ctx_tags_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._ctx_bar_layout = _FlowLayout(self._ctx_tags_widget, h_spacing=4, v_spacing=3)
        self._ctx_bar_layout.setContentsMargins(0, 0, 0, 0)
        ctx_bar_outer.addWidget(self._ctx_tags_widget, 1)

        # Right: project context toggle (fixed width, always visible)
        self._proj_toggle_btn = QPushButton("📁 项目上下文  ○")
        self._proj_toggle_btn.setCheckable(True)
        self._proj_toggle_btn.setFixedHeight(22)
        _install_themed_tip(self._proj_toggle_btn,
            "Enable project-wide context — attach all project files to the chat")
        if _is_dark_theme():
            self._proj_toggle_btn.setStyleSheet(
                "QPushButton { font-size: 9px; padding: 1px 8px; border: 1px solid #555; "
                "border-radius: 3px; color: #aaa; background: transparent; }"
                "QPushButton:hover { color: #eee; border-color: #888; }"
                "QPushButton:checked { color: #c8a000; border-color: #c8a000; "
                "background: #3a2a00; }"
                "QPushButton:checked:hover { color: #ffe080; }")
        else:
            self._proj_toggle_btn.setStyleSheet(
                "QPushButton { font-size: 9px; padding: 1px 8px; border: 1px solid #aaa; "
                "border-radius: 3px; color: #444; background: transparent; }"
                "QPushButton:hover { color: #000; border-color: #666; }"
                "QPushButton:checked { color: #7a5000; border-color: #c8a000; "
                "background: #fff3e0; }"
                "QPushButton:checked:hover { color: #4a3000; }")
        self._proj_toggle_btn.clicked.connect(self._on_proj_toggle)
        ctx_bar_outer.addWidget(self._proj_toggle_btn, 0)

        # File watcher for project directory and git file changes
        self._proj_watcher = QFileSystemWatcher(self)
        self._proj_watcher.directoryChanged.connect(self._on_proj_dir_changed)
        self._proj_watcher.fileChanged.connect(self._on_git_file_changed)

        # Git status bar
        self._git_bar = _GitStatusBar(self)
        self._git_bar.setVisible(False)
        self._git_bar.action_requested.connect(self._on_git_action)

        # ══════════════════════════════════════════════════════════════
        # ROW 1: Inference params summary (always visible) + config btn
        # ══════════════════════════════════════════════════════════════
        params_row = QHBoxLayout()
        params_row.setContentsMargins(2, 1, 2, 1)
        params_row.setSpacing(4)

        # Summary label — always shown, clickable, opens params popup
        self._params_bar_lbl = QPushButton("点击设置推理参数")
        self._params_bar_lbl.setFlat(True)
        self._params_bar_lbl.setStyleSheet(_params_bar_idle_style())
        _install_themed_tip(self._params_bar_lbl, "Click to configure inference parameters (temperature, max tokens…)")
        self._params_bar_lbl.clicked.connect(self._toggle_params_popup)
        self._params_bar_lbl.setFixedHeight(24)
        params_row.addWidget(self._params_bar_lbl, 1)

        # Context size estimate — right-aligned, always visible, hover for breakdown
        self._ctx_size_lbl = _CtxSizeButton()
        self._ctx_size_lbl.setFlat(True)
        self._ctx_size_lbl.setStyleSheet(_ctx_size_style("normal"))
        self._ctx_size_lbl.setFixedHeight(24)
        self._ctx_size_lbl.setFocusPolicy(Qt.NoFocus)
        params_row.addWidget(self._ctx_size_lbl)

        # Wrap in a widget
        params_bar_w = QWidget()
        params_bar_w.setLayout(params_row)
        self._params_bar = params_bar_w

        # ══════════════════════════════════════════════════════════════
        # ROW 2: System prompts selector + ↓ Copy to field button
        # ══════════════════════════════════════════════════════════════
        sp_bar = QWidget()
        sp_bar_lay = QHBoxLayout(sp_bar)
        sp_bar_lay.setContentsMargins(0, 0, 0, 0)
        sp_bar_lay.setSpacing(4)

        sp_lbl = QLabel("System prompts:")
        sp_lbl.setStyleSheet("font-size: 9pt; color: gray;")
        sp_lbl.setFixedWidth(100)
        sp_bar_lay.addWidget(sp_lbl)

        self._sp_combo = QComboBox()
        self._sp_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._sp_combo.setStyleSheet("font-size: 9pt;")
        sp_bar_lay.addWidget(self._sp_combo, 1)

        # ⚙ Settings button → opens Settings on the System Prompts tab
        self._sp_settings_btn = QPushButton("⚙")
        self._sp_settings_btn.setFixedSize(24, 24)
        _install_themed_tip(self._sp_settings_btn, "Manage system prompts in Settings")
        if _is_dark_theme():
            self._sp_settings_btn.setStyleSheet(
                "QPushButton { font-size: 12px; padding: 0; border: 1px solid #555; "
                "border-radius: 3px; color: #aaa; }"
                "QPushButton:hover { color: #eee; border-color: #aaa; }"
                "QPushButton:pressed { color: #c8a000; border-color: #c8a000; }")
        else:
            self._sp_settings_btn.setStyleSheet(
                "QPushButton { font-size: 12px; padding: 0; border: 1px solid #aaa; "
                "border-radius: 3px; color: #444; }"
                "QPushButton:hover { color: #000; border-color: #666; }"
                "QPushButton:pressed { color: #7a5000; border-color: #c8a000; }")
        self._sp_settings_btn.clicked.connect(self._open_settings_sp_tab)
        sp_bar_lay.addWidget(self._sp_settings_btn)

        self._sp_copy_btn = QPushButton("↓📋 复制并编辑")
        self._sp_copy_btn.setFixedHeight(24)
        self._sp_copy_btn.setFixedWidth(125)
        self._sp_copy_btn.setStyleSheet("font-size: 9pt;")
        _install_themed_tip(self._sp_copy_btn, "Copy selected prompt text into the field below for editing")
        self._sp_copy_btn.setVisible(False)
        sp_bar_lay.addWidget(self._sp_copy_btn)

        # ══════════════════════════════════════════════════════════════
        # ROW 3: System prompt field (full width)
        # ══════════════════════════════════════════════════════════════
        self._sys_prompt = QPlainTextEdit()
        self._sys_prompt.setPlaceholderText("System prompt (optional)")
        self._sys_prompt.setMaximumHeight(48)
        self._sys_prompt.setFont(QFont("Monospace", 9))

        # ══════════════════════════════════════════════════════════════
        # ROW 4: User input + Send (tall) / Stop (short) stacked right
        # ══════════════════════════════════════════════════════════════
        self._input = _CommandInput()
        self._input.set_commands(load_commands(), builtin_factory=self._get_active_builtins)
        self._input.send_requested.connect(self._send)
        self._input.builtin_action_requested.connect(self._on_builtin_action)
        self._input.setPlaceholderText("Type message… (Ctrl+Enter to send, / for commands)")
        self._input.setMinimumHeight(60)
        self._input.setFont(QFont("Monospace", 10))
        self._input.installEventFilter(self)

        self._send_btn = QPushButton("发送")
        self._send_btn.setMinimumWidth(64)
        self._send_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._send_btn.clicked.connect(self._send)

        self._stop_btn = QPushButton("停止")
        self._stop_btn.setMinimumWidth(64)
        self._stop_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)

        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(4)
        btn_col.addWidget(self._send_btn, 2)   # Send: ~2/3 of available height
        btn_col.addWidget(self._stop_btn, 1)   # Stop: ~1/3

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(2)
        input_row.addWidget(self._input, 1)
        input_row.addLayout(btn_col)

        # Wrap input_row in a widget so QSplitter can manage it
        input_w = QWidget()
        input_w_lay = QVBoxLayout(input_w)
        input_w_lay.setContentsMargins(2, 2, 2, 2)
        input_w_lay.setSpacing(0)
        input_w_lay.addLayout(input_row)
        input_w.setMinimumHeight(72)

        # ── status ────────────────────────────────────────────────────
        n = len(self._model_list)
        src = "saved" if self._state.get("model_list") else "defaults"
        self._status = QLabel(f"Ready. {n} model(s) from {src}. Click ⟳ to refresh.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size:10px; padding:2px 4px;")

        # ── assemble ──────────────────────────────────────────────────
        # Upper panel: chat history + all info bars
        upper_w = QWidget()
        upper_lay = QVBoxLayout(upper_w)
        upper_lay.setContentsMargins(0, 0, 0, 0)
        upper_lay.setSpacing(2)
        upper_lay.addWidget(scroll, stretch=1)
        upper_lay.addWidget(self._page_bar)
        upper_lay.addWidget(self._ctx_bar)
        upper_lay.addWidget(self._git_bar)
        upper_lay.addWidget(params_bar_w)
        upper_lay.addWidget(sp_bar)
        upper_lay.addWidget(self._sys_prompt)
        upper_w.setMinimumHeight(80)

        # Vertical splitter — drag the handle to resize the input field
        self._input_splitter = QSplitter(Qt.Vertical)
        self._input_splitter.setChildrenCollapsible(False)
        self._input_splitter.setHandleWidth(5)
        self._input_splitter.addWidget(upper_w)
        self._input_splitter.addWidget(input_w)
        self._input_splitter.setStretchFactor(0, 1)   # upper grows with window
        self._input_splitter.setStretchFactor(1, 0)   # input stays at chosen size
        # Restore saved height; default 90 px ≈ 3 lines at font size 10
        self._input_splitter.setSizes([10000, self._state.get("input_height", 90)])
        # Persist whenever the user drags the handle
        self._input_splitter.splitterMoved.connect(
            lambda _pos, _idx: self._save_state(
                input_height=self._input_splitter.sizes()[1]))
        if _is_dark_theme():
            _sash_normal = ("qlineargradient(x1:0,y1:0, x2:0,y2:1,"
                            " stop:0 #2a2a2a, stop:0.4 #505050,"
                            " stop:0.6 #505050, stop:1 #2a2a2a)")
        else:
            _sash_normal = ("qlineargradient(x1:0,y1:0, x2:0,y2:1,"
                            " stop:0 #cccccc, stop:0.4 #aaaaaa,"
                            " stop:0.6 #aaaaaa, stop:1 #cccccc)")
        self._input_splitter.setStyleSheet(
            "QSplitter::handle:vertical {"
            f"  background: {_sash_normal};"
            "  height: 5px; margin: 0 2px; border-radius: 2px;"
            "}"
            "QSplitter::handle:vertical:hover,"
            "QSplitter::handle:vertical:pressed {"
            "  background: #4a9eff;"
            "}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addLayout(top)
        lay.addWidget(self._input_splitter, stretch=1)
        lay.addWidget(self._status)

        # Wire up copy-to-editor from history
        self._history.insert_to_editor.connect(self._insert_to_editor)
        # Wire up delete exchange
        self._history.delete_exchange.connect(self._on_delete_exchange)
        # Wire up regenerate
        self._history.regenerate.connect(self._on_regenerate)
        # Wire up agentic batch confirm
        self._history.action_blocks_ready.connect(self._on_action_blocks_ready)

        # Wire up system prompt selector
        self._sp_populate_combo()
        self._sp_combo.currentIndexChanged.connect(self._sp_on_select)
        self._sp_copy_btn.clicked.connect(self._sp_on_copy)

    # ── file context ─────────────────────────────────────────────────
    # ── project context ───────────────────────────────────────────────

    def set_project_fns(self, get_project_root_fn, get_editor_widget_fn):
        """Called by plugin.py to wire up project/editor access."""
        self._get_project_root_fn  = get_project_root_fn
        self._get_editor_widget_fn = get_editor_widget_fn

    def on_project_loaded(self, path):
        """Called by plugin.py when Spyder loads a project."""
        prev_root = self._proj_root
        # Always track the current project root (git bar and system-prompt injection
        # both need it regardless of whether project context toggle is on).
        self._proj_root      = path
        self._git_fail_count = 0   # new project — allow fresh retries
        if self._proj_enabled and prev_root != path:
            # Different project loaded while project context was active — reset state
            self._proj_hashes = {}
            self._proj_all_sent = False
            self._proj_changed_count = 0
        self._update_proj_watcher()
        self._proj_toggle_btn.setEnabled(True)
        self._rebuild_ctx_bar()
        self._refresh_git_status()

    def on_project_closed(self):
        """Called by plugin.py when Spyder closes the active project."""
        self._proj_root = None   # no project is open — do not inject stale path
        self._proj_toggle_btn.setEnabled(False)
        self._git_bar.setVisible(False)
        self._git_branch    = ""
        self._git_diff_stat = ""
        self._git_dirty     = False
        if self._proj_enabled:
            self._proj_changed_count = 0
            self._rebuild_ctx_bar()

    def _on_proj_toggle(self, checked):
        if checked:
            self._try_enable_project_context()
        else:
            self._disable_project_context()

    def _try_enable_project_context(self):
        root = (self._get_project_root_fn()
                if self._get_project_root_fn else None)
        if not root:
            self._proj_toggle_btn.setChecked(False)
            self._status.setText("⚠ 当前没有打开 Spyder 项目。")
            return

        cfg = self._history_cfg()
        dlg = _ProjectContextDialog(
            root,
            max_file_kb=cfg.get("proj_max_file_kb", 256),
            max_files=cfg.get("proj_max_files", 500),
            extra_patterns=cfg.get("proj_extra_exclusions", "").splitlines(),
            parent=self,
        )
        if dlg.exec_() != QDialog.Accepted:
            self._proj_toggle_btn.setChecked(False)
            return

        self._proj_enabled              = True
        self._proj_root                 = root
        self._proj_included_folders     = dlg.selected_folders()
        self._proj_hashes               = {}
        self._proj_all_sent             = False
        self._proj_changed_count        = 0
        self._proj_ctx_token_estimate   = dlg.estimate_tokens()
        # Remove any manually attached files — project context replaces them
        self._context_files.clear()
        self._selection_counters.clear()
        self._update_proj_watcher()
        self._rebuild_ctx_bar()
        self._status.setText(
            f"Project context enabled: {len(dlg.selected_files())} files queued.")

    def _disable_project_context(self):
        from qtpy.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Disable project context",
            "Project context will be detached from this chat.\n"
            "Future messages will not include project files.\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self._proj_toggle_btn.setChecked(True)
            return
        self._proj_enabled              = False
        self._proj_hashes               = {}
        self._proj_all_sent             = False
        self._proj_changed_count        = 0
        self._proj_ctx_token_estimate   = 0
        self._update_proj_watcher()
        self._rebuild_ctx_bar()
        self._status.setText("项目上下文已禁用。")

    def _update_proj_watcher(self):
        import os as _os
        # Remove old watched dirs and files
        old_dirs  = self._proj_watcher.directories()
        old_files = self._proj_watcher.files()
        if old_dirs:
            self._proj_watcher.removePaths(old_dirs)
        if old_files:
            self._proj_watcher.removePaths(old_files)
        if self._proj_enabled and self._proj_root:
            self._proj_watcher.addPath(self._proj_root)
        # Always watch .git/HEAD + .git/index when a project root is known,
        # so the git bar detects branch switches and staging changes.
        if self._proj_root:
            for fname in ("HEAD", "index"):
                p = _os.path.join(self._proj_root, ".git", fname)
                if _os.path.isfile(p):
                    self._proj_watcher.addPath(p)

    def _on_proj_dir_changed(self, _path):
        if not self._proj_enabled:
            return
        self._proj_changed_count = self._count_proj_changes()
        self._rebuild_ctx_bar()

    def _count_proj_changes(self):
        """Count files whose disk state differs from stored hash, and refresh
        the project context token estimate in the same pass.

        collect_project_files reads full file content regardless, so calling
        estimate_tokens here adds no extra I/O.
        """
        if not self._proj_root or not self._proj_hashes:
            return 0
        from .project_context import (
            collect_project_files, collect_unsaved_files,
            get_effective_files, diff_files, estimate_tokens,
        )
        try:
            cfg = self._history_cfg()
            disk_files = collect_project_files(
                self._proj_root,
                included_folders=self._proj_included_folders or None,
                extra_patterns=cfg.get("proj_extra_exclusions", "").splitlines(),
                max_file_kb=cfg.get("proj_max_file_kb", 256),
                max_files=cfg.get("proj_max_files", 500),
            )
            editor_widget = (self._get_editor_widget_fn()
                             if self._get_editor_widget_fn else None)
            disk_files = get_effective_files(disk_files, editor_widget)
            unsaved    = collect_unsaved_files(editor_widget)
            all_files  = disk_files + unsaved
            # Refresh token estimate while we have the live file list
            self._proj_ctx_token_estimate = estimate_tokens(all_files)
            changed, added, removed = diff_files(self._proj_hashes, all_files)
            return len(changed) + len(added) + len(removed)
        except Exception:
            return 0

    # ── Git status bar ────────────────────────────────────────────────────

    def _on_git_file_changed(self, path):
        """Called when .git/HEAD or .git/index changes."""
        import os as _os
        # QFileSystemWatcher drops the watch on atomic replace (Windows/Linux)
        if _os.path.isfile(path):
            self._proj_watcher.addPath(path)
        if not self._proj_root:
            return
        if path.endswith("HEAD"):
            self._git_pending_branch_change = True
        self._refresh_git_status()

    def _git_cwd_fallback(self):
        """Return a working directory for git queries when no project is active.

        Tries, in order:
        1. The current Python working directory (os.getcwd()) — Spyder typically
           sets this to the active project root or the user's home folder.
        2. None (caller must handle the None case).
        """
        import os as _os
        cwd = _os.getcwd()
        return cwd if _os.path.isdir(cwd) else None

    def _refresh_git_status(self):
        """Launch a background thread to query git branch + shortstat."""
        if not self._history_cfg().get("show_git_bar", True):
            self._git_bar.setVisible(False)
            return
        # Use the project root when available; fall back to cwd so the bar
        # works even without Project Context enabled.
        if not self._proj_root and not self._git_cwd_fallback():
            self._git_bar.setVisible(False)
            return
        if self._git_thread and self._git_thread.isRunning():
            return   # already in flight
        cwd = self._proj_root or self._git_cwd_fallback()
        worker = _GitStatusWorker(cwd)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._on_git_result)
        worker.failed.connect(self._on_git_failed)
        worker.result.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._git_worker = worker
        self._git_thread = thread
        thread.start()

    @Slot(str, str, bool)
    def _on_git_result(self, branch, diff_stat, is_dirty):
        self._git_thread     = None
        self._git_worker     = None
        self._git_fail_count = 0   # successful query — reset retry counter
        self._git_branch    = branch
        self._git_diff_stat = diff_stat
        self._git_dirty     = is_dirty
        self._git_bar.update_status(branch, diff_stat, is_dirty)
        agentic = self._agentic_cfg()
        commit_ok = agentic.get("enabled") and agentic.get("allow_git", True)
        self._git_bar.set_commit_enabled(bool(commit_ok))
        self._git_bar.setVisible(True)

    @Slot()
    def _on_git_failed(self):
        self._git_thread = None
        self._git_worker = None
        # On startup git can be slow (cold DLL / credential-manager init on Windows),
        # causing the first query to time out even though git is present.
        # Retry up to 3 times with increasing delays (5 s, 10 s, 15 s) before giving up.
        _MAX_RETRIES = 3
        if self._git_fail_count < _MAX_RETRIES:
            self._git_fail_count += 1
            delay_ms = self._git_fail_count * 5000
            QTimer.singleShot(delay_ms, self._refresh_git_status)
        else:
            self._git_bar.setVisible(False)

    @Slot(str)
    def _on_git_action(self, action):
        """Gather live git data for the action, then auto-send enriched prompt."""
        if self._chat_thread and self._chat_thread.isRunning():
            self._status.setText("⚠ 请等待当前回复完成。")
            return
        if self._git_action_thread and self._git_action_thread.isRunning():
            return   # already gathering
        cwd = self._proj_root or self._git_cwd_fallback()
        if not cwd:
            self._status.setText("⚠ 没有打开项目 — 无法确定 git 根目录。")
            return
        self._status.setText("⏳ 正在收集 git 数据…")
        self._git_bar.setEnabled(False)
        worker = _GitActionWorker(cwd, action, self._git_branch)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.ready.connect(self._on_git_action_ready)
        worker.failed.connect(self._on_git_action_failed)
        worker.ready.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        self._git_action_worker = worker
        self._git_action_thread = thread
        thread.start()

    @Slot(str)
    def _on_git_action_ready(self, prompt):
        self._git_action_thread = None
        self._git_action_worker = None
        self._git_bar.setEnabled(True)
        self._status.setText("")
        self._input.setPlainText(prompt)
        self._pending_agentic_response = True
        self._send()

    @Slot(str)
    def _on_git_action_failed(self, error):
        self._git_action_thread = None
        self._git_action_worker = None
        self._git_bar.setEnabled(True)
        self._status.setText(f"⚠ Git action failed: {error}")

    @Slot(dict)
    def _on_action_blocks_ready(self, registry):
        """Handle agentic actions based on the current autonomous mode setting."""
        if not registry:
            return
        cfg  = self._agentic_cfg()
        mode = cfg.get("autonomous_mode", "semi")

        _READ_ONLY = {"read", "ls", "grep"}

        if mode == "off":
            # Manual mode: show the batch confirmation dialog for ALL actions
            # (reads and modifying alike).  The key difference from Semi is that
            # results are NOT automatically forwarded to the LLM after execution —
            # the user stays in full control of the follow-up context.
            import os as _os
            _base_dir_off = (
                (self._get_project_root_fn() if self._get_project_root_fn else None)
                or self._proj_root
                or _os.path.expanduser("~")
            )
            from .agentic_actions import show_batch_confirm_dialog
            approved = show_batch_confirm_dialog(self, registry, base_dir=_base_dir_off)
            if not approved:
                return
            self._batch_execute(registry, approved, auto_send=False)
            # Do NOT call _group_read_batch in off mode: each inspection block
            # shows its own output panel ("📤 Send to LLM" / "✕ Dismiss") after
            # execution, so individual blocks must stay visible and unmerged.
            return

        import os as _os
        base_dir = (
            (self._get_project_root_fn() if self._get_project_root_fn else None)
            or self._proj_root
            or _os.path.expanduser("~")
        )

        if mode == "semi":
            # Show dialog listing all actions; user picks which to run
            from .agentic_actions import show_batch_confirm_dialog
            approved = show_batch_confirm_dialog(self, registry, base_dir=base_dir)
            if not approved:
                return
            self._batch_execute(registry, approved, auto_send=True)
            # Group any read-only fences that were approved into a single summary block
            approved_readonly = [i for i in approved if registry[i]["action_type"] in _READ_ONLY]
            self._group_read_batch(registry, approved_readonly)

        elif mode == "full":
            confirm_modifying = cfg.get("full_auto_confirm_modifying", True)
            if not confirm_modifying:
                # Execute every action silently — no dialog at all
                self._batch_execute(registry, list(registry.keys()), auto_send=True)
                readonly_idx = [i for i, e in registry.items()
                                if e["action_type"] in _READ_ONLY]
                self._group_read_batch(registry, readonly_idx)
            else:
                # Read-only actions (read/ls/grep) execute silently;
                # modifying actions (file/patch/run/install/git) go through the dialog.
                readonly_idx  = [i for i, e in registry.items()
                                 if e["action_type"] in _READ_ONLY]
                modifying_idx = [i for i, e in registry.items()
                                 if e["action_type"] not in _READ_ONLY]

                approved_mod = []
                if modifying_idx:
                    from .agentic_actions import show_batch_confirm_dialog
                    modifying_reg = {i: registry[i] for i in modifying_idx}
                    approved_mod  = show_batch_confirm_dialog(
                        self, modifying_reg, base_dir=base_dir)

                all_approved = sorted(readonly_idx + list(approved_mod))
                if all_approved:
                    self._batch_execute(registry, all_approved, auto_send=True)
                self._group_read_batch(registry, readonly_idx)

    def _group_read_batch(self, registry, indices):
        """Replace multiple read/ls/grep action blocks with one compact summary block.

        Called after batch execution so all individual frames already show ✓ Done.
        We hide them and insert a single grouped widget at the position of the first
        one.  Only groups when 2+ fences are involved (a single fence stays as-is).
        """
        if len(indices) < 2:
            return

        entries = [registry[i] for i in sorted(indices) if i in registry]
        widgets = [e["widget"] for e in entries if "widget" in e]
        if len(widgets) < 2:
            return

        first = widgets[0]
        parent_w = first.parentWidget()
        if parent_w is None:
            return
        lay = parent_w.layout()
        if lay is None:
            return

        # Find insertion position (index of first read block in layout)
        insert_pos = -1
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item and item.widget() is first:
                insert_pos = i
                break
        if insert_pos < 0:
            return

        # Hide individual blocks (keep alive — their closures hold state)
        for w in widgets:
            w.hide()

        # Insert summary at the position of the first hidden block
        summary = _build_read_group_widget(entries)
        lay.insertWidget(insert_pos, summary)

    def _batch_execute(self, registry, approved_indices, auto_send=False):
        """Execute approved actions sequentially; collect outputs for auto-send."""
        queue   = [registry[i] for i in sorted(approved_indices) if i in registry]
        outputs = []  # list of (label, text, kind)

        def _next(idx=0):
            if idx >= len(queue):
                # Send all collected outputs to the LLM.
                # In semi/full mode (auto_send=True) this includes everything.
                # In off mode (auto_send=False) inspection results are diverted
                # to per-block output panels (show_output_fn), so `outputs` here
                # contains only non-inspection confirmations (file written, patch
                # applied, deleted, renamed, git output, etc.).  We always send
                # these so the LLM learns which actions completed and how.
                if outputs:
                    self._auto_send_results(outputs)
                return
            entry = queue[idx]
            atype = entry["action_type"]
            if atype == "git" and entry.get("run_direct_chained"):
                if auto_send:
                    # Semi / full mode: chain so the output is collected and
                    # auto-sent to the LLM after all actions complete.
                    def _on_done(stdout, stderr, rc, _e=entry):
                        cmd_lbl = _e["content"].strip().split("\n")[0][:60]
                        out = (stdout + stderr).strip() or "(no output)"
                        outputs.append((f"git {cmd_lbl}", out, "git"))
                        _next(idx + 1)
                    entry["run_direct_chained"](_on_done)
                else:
                    # Off (manual) mode: run without a chaining callback so
                    # on_git_done_extra stays None inside _run_action.  With
                    # auto_send_results also False, _auto_dismiss becomes False
                    # and the git output panel shows normally — the user can
                    # click "📤 Send to LLM" or "✕ Dismiss" themselves.
                    entry["run_direct"]()
                    _next(idx + 1)   # git is async; continue the batch immediately
            else:
                result = entry["run_direct"]()
                if result:
                    _kind = (atype if atype in ("read", "ls", "grep") else "result")
                    if not auto_send and atype in ("read", "ls", "grep"):
                        # Off (manual) mode: show the output panel in the action
                        # block so the user can decide whether to send the result
                        # to the LLM or dismiss it.  Each block manages its own
                        # "📤 Send to LLM" / "✕ Dismiss" buttons independently.
                        show_fn = entry.get("show_output_fn")
                        if show_fn:
                            show_fn(result)
                    else:
                        outputs.append((entry["target"], result, _kind))
                _next(idx + 1)

        _next()

    def _auto_send_results(self, outputs):
        """Inject all execution outputs as context tags and send follow-up to LLM."""
        if self._chat_thread and self._chat_thread.isRunning():
            return
        for label, text, kind in outputs:
            if kind == "git":
                first_line = label.split("\n")[0][:60]
                tag_name = f"⎇ {first_line}"
                if len(tag_name) > 60:
                    tag_name = tag_name[:57] + "…"
                body = f"[Git command: {label}]\n{text}"
            else:
                tag_name = f"✓ {label[:50]}"
                body = f"[Action result: {label}]\n{text}"
            # Bypass the duplicate-name guard in add_file_context_content —
            # multiple git commands in a batch would all get the same "⎇ git …"
            # name and only the first would be added. Instead, append directly
            # and make the tag name unique by appending a counter if needed.
            existing_names = {n for n, *_ in self._context_files}
            unique_name = tag_name
            counter = 2
            while unique_name in existing_names:
                unique_name = f"{tag_name} ({counter})"
                counter += 1
            self._context_files.append((unique_name, body, kind if kind == "git" else "result"))
            self._rebuild_ctx_bar()
        self._input.setPlainText("Here are the results of the executed actions.")
        self._pending_agentic_response = True
        self._send()

    def _proj_ctx_for_save(self):
        """Build project_context dict for saving to chat JSON."""
        if not self._proj_enabled or not self._proj_root:
            return None
        return {
            "enabled":          True,
            "root":             self._proj_root,
            "included_folders": self._proj_included_folders,
            "files": [
                {"path": p, "hash": h}
                for p, h in self._proj_hashes.items()
            ],
        }

    def _collect_project_context(self):
        """
        Collect all current project files and compute full/delta context text.
        Returns context text string (empty string if nothing to send).
        Updates self._proj_hashes and self._proj_all_sent.
        """
        from .project_context import (
            collect_project_files, collect_unsaved_files, get_effective_files,
            build_full_context_text, build_delta_text, diff_files, estimate_tokens,
        )
        cfg = self._history_cfg()
        editor_widget = (self._get_editor_widget_fn()
                         if self._get_editor_widget_fn else None)

        disk_files = collect_project_files(
            self._proj_root,
            included_folders=self._proj_included_folders or None,
            extra_patterns=cfg.get("proj_extra_exclusions", "").splitlines(),
            max_file_kb=cfg.get("proj_max_file_kb", 256),
            max_files=cfg.get("proj_max_files", 500),
        )
        disk_files = get_effective_files(disk_files, editor_widget)
        unsaved    = collect_unsaved_files(editor_widget)
        all_files  = disk_files + unsaved

        # Update token estimate from the live file list — estimate_tokens is
        # free here because all_files already carries loaded content.
        self._proj_ctx_token_estimate = estimate_tokens(all_files)

        # Pass git info when the git bar is active (setting controls both)
        show_git = cfg.get("show_git_bar", True)
        git_branch    = self._git_branch    or None if show_git else None
        git_diff_stat = self._git_diff_stat or None if show_git else None

        if not self._proj_all_sent:
            text = build_full_context_text(
                self._proj_root, all_files,
                branch=git_branch, diff_stat=git_diff_stat)
            self._proj_hashes   = {f["path"]: f["hash"] for f in all_files}
            self._proj_all_sent = True
        else:
            changed, added, removed = diff_files(self._proj_hashes, all_files)
            # Inject branch-change note even when no files changed
            if not changed and not added and not removed:
                if self._git_pending_branch_change and self._git_branch and show_git:
                    self._git_pending_branch_change = False
                    return (f"[Branch switched]\nBranch: {self._git_branch}\n"
                            f"Uncommitted: {self._git_diff_stat or 'clean'}")
                return ""
            inject_branch = self._git_pending_branch_change
            self._git_pending_branch_change = False
            text = build_delta_text(
                changed, added, removed, root=self._proj_root,
                branch=git_branch if inject_branch else None,
                diff_stat=git_diff_stat if inject_branch else None)
            for f in changed + added:
                self._proj_hashes[f["path"]] = f["hash"]
            for p in removed:
                self._proj_hashes.pop(p, None)

        self._proj_changed_count = 0
        self._rebuild_ctx_bar()
        return text

    # ── file context ──────────────────────────────────────────────────

    def add_file_context(self, path):
        """Add a saved file by path — reads content from disk."""
        import os
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            self._status.setText(f"⚠ Could not read file: {e}")
            return
        # Use full absolute path as the name so the LLM knows the exact location
        self.add_file_context_content(os.path.normpath(os.path.abspath(path)), content)

    def add_file_context_content(self, name, content, source="file"):
        """Add file context by name + content directly (works for unsaved files).
        source: "file" for whole-file editor attachments (blocked when project ON),
                "selection" for editor selections (always allowed),
                "console" for IPython console (always allowed)."""
        if self._proj_enabled and source == "file":
            self._status.setText(
                "⚠ Disable project context to attach individual files.")
            return
        # Don't add duplicates by name
        if any(n == name for n, *_ in self._context_files):
            self._status.setText(f"Already in context: {name}")
            return
        self._context_files.append((name, content, source))
        self._rebuild_ctx_bar()
        name_short = name.split("\n")[0][:60]
        self._status.setText(f"Added to context: {name_short} ({len(content)} chars)")

    def next_selection_id(self, filename):
        """Return and increment the selection counter for this filename."""
        key = filename
        count = self._selection_counters.get(key, 0) + 1
        self._selection_counters[key] = count
        return count

    def _remove_file_context(self, name):
        self._context_files = [(n, c, s) for n, c, s in self._context_files if n != name]
        self._rebuild_ctx_bar()

    def _rebuild_ctx_bar(self):
        import os as _os
        # Clear all items from the flow layout
        while self._ctx_bar_layout.count() > 0:
            item = self._ctx_bar_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        # Project badge (no ✕ button, amber/gold)
        _dark = _is_dark_theme()
        if self._proj_enabled:
            badge_text = f"📁 {self._proj_badge_text()}"
            badge = QFrame()
            _pbg, _pbd, _pfg = (
                ("#3a2a00", "#c8a000", "#c8a000") if _dark
                else ("#fff8e0", "#c8a000", "#7a5a00"))
            badge.setStyleSheet(
                f"QFrame {{ background: {_pbg}; border: 1px solid {_pbd}; "
                "border-radius: 3px; padding: 1px; }")
            bl = QHBoxLayout(badge)
            bl.setContentsMargins(5, 1, 5, 1)
            bl.setSpacing(0)
            lbl = QLabel(badge_text)
            lbl.setStyleSheet(
                f"color: {_pfg}; font-size: 10px; border: none; "
                "background: transparent;")
            bl.addWidget(lbl)
            self._ctx_bar_layout.addWidget(badge)

        # Regular attachment tags (editor/console/git)
        for name, _, source in self._context_files:
            if source == "console":
                bg, border_col, text_col = (
                    ("#1e3a2a", "#3a7a5a", "#80c8a0") if _dark
                    else ("#e8f5ee", "#4a9a6a", "#1a5a2a"))
            elif source == "git":
                bg, border_col, text_col = (
                    ("#2a1a00", "#e8a050", "#f0c080") if _dark
                    else ("#fff3e0", "#c87a20", "#7a4a00"))
            elif source == "result":
                bg, border_col, text_col = (
                    ("#1a2a1a", "#3a6a3a", "#70b870") if _dark
                    else ("#eaf5ea", "#4a8a4a", "#1a4a1a"))
            else:
                bg, border_col, text_col = (
                    ("#2d4a6e", "#4a7ab5", "#9ec8f0") if _dark
                    else ("#e8f0fb", "#4a6aaa", "#1a3a7a"))
            tag = QFrame()
            tag.setStyleSheet(
                f"QFrame {{ background: {bg}; border: 1px solid {border_col}; "
                "border-radius: 3px; padding: 1px; }")
            tl = QHBoxLayout(tag)
            tl.setContentsMargins(5, 1, 3, 1)
            tl.setSpacing(3)
            display_name = _os.path.basename(name) if (_os.path.sep in name or "/" in name) else name
            # Always show single-line tag — strip newlines, cap length
            display_name = display_name.split("\n")[0]
            if len(display_name) > 60:
                display_name = display_name[:57] + "…"
            lbl = QLabel(display_name)
            _install_themed_tip(lbl, name)
            lbl.setStyleSheet(
                f"color: {text_col}; font-size: 10px; border: none; "
                "background: transparent;")
            tl.addWidget(lbl)
            x_btn = QPushButton("×")
            x_btn.setFixedSize(14, 14)
            x_btn.setFlat(True)
            _x_hover = "#fff" if _dark else "#cc0000"
            x_btn.setStyleSheet(
                "QPushButton { color: #888; font-size: 11px; border: none; "
                "background: transparent; padding: 0; }"
                f"QPushButton:hover {{ color: {_x_hover}; }}")
            x_btn.clicked.connect(
                lambda checked=False, n=name: self._remove_file_context(n))
            tl.addWidget(x_btn)
            self._ctx_bar_layout.addWidget(tag)

        self._ctx_tags_widget.setVisible(True)

        # ctx_bar is always visible (toggle button always shown)
        self._ctx_bar.setVisible(True)

        # Refresh context size estimate whenever the context bar changes
        self._update_ctx_size_label()

        # Update toggle button label and tooltip to reflect current state
        if self._proj_enabled:
            self._proj_toggle_btn.setText("📁 项目上下文  ●")
            _install_themed_tip(self._proj_toggle_btn,
                "Project context is ON — click to disable")
        else:
            self._proj_toggle_btn.setText("📁 项目上下文  ○")
            _install_themed_tip(self._proj_toggle_btn,
                "Enable project-wide context — attach all project files to the chat")

    def _proj_badge_text(self):
        root = self._proj_root or ""
        name = root.split("/")[-1].split("\\")[-1] if root else "Project"
        n_files = len(self._proj_hashes)
        if not self._proj_all_sent:
            return f"{name} (pending first send)"
        if self._proj_changed_count:
            return f"{name} · {self._proj_changed_count} changed ⚠"
        return f"{name} · {n_files} files"

    # ── event filter ─────────────────────────────────────────────────
    def eventFilter(self, obj, event):
        # _CommandInput handles Ctrl+Enter and slash-dropdown natively;
        # keep this filter for any future obj-level overrides.
        return super().eventFilter(obj, event)

    # ── model popup ───────────────────────────────────────────────────
    def _toggle_popup(self):
        if self._popup is None:
            # Create lazily so main window is visible and stylesheet is applied
            main_win = _find_main_window()
            self._popup = _ModelPopup(main_win)
            self._popup.selected.connect(self._select_model)

        if self._popup.isVisible():
            self._popup.hide()
        else:
            self._popup.show_below(
                self._model_btn, self._model_list, self._current_model)

    def _select_model(self, name):
        self._current_model = name
        self._model_btn.setText(name + " ▾")
        self._status.setText(f"Model: {name}")
        self._save_state(selected_model=name)

    def _reload_models(self):
        """Manually triggered model list refresh from API."""
        self._fetching = False   # force re-fetch even if previous attempt failed
        self._reload_btn.setEnabled(False)
        self._reload_btn.setText("…")
        self._fetch_models()

    # ── model fetching ────────────────────────────────────────────────
    def _fetch_models(self):
        if self._fetching:
            return
        self._fetching = True
        url = self._api_url()
        key = self._api_key()
        sig_ok  = self._sig_models_ok
        sig_err = self._sig_models_err

        def _work():
            try:
                import urllib.request
                import urllib.error
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "spyder-ai-chat/0.1.2",
                }
                if key:
                    headers["Authorization"] = f"Bearer {key}"
                req = urllib.request.Request(
                    url.rstrip("/") + "/models", headers=headers)
                with urllib.request.urlopen(req, timeout=8) as r:
                    data  = json.loads(r.read().decode())
                    items = data.get("data", data.get("models", []))
                    models = sorted(
                        m["id"] for m in items
                        if isinstance(m, dict) and "id" in m)
                    sig_ok.emit(models if models else [])
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode(errors="replace")[:200]
                except Exception:
                    body = ""
                sig_err.emit(f"HTTP {e.code} {e.reason}: {body}")
            except Exception as e:
                sig_err.emit(f"{type(e).__name__}: {e}")

        threading.Thread(target=_work, daemon=True).start()

    @Slot(list)
    def _on_models_ok(self, models):
        self._fetching = False
        self._reload_btn.setEnabled(True)
        self._reload_btn.setText("⟳")
        if models:
            self._model_list = models
            if self._current_model not in models:
                self._current_model = models[0]
                self._model_btn.setText(self._current_model + " ▾")
            self._save_state(model_list=models, selected_model=self._current_model)
            preview = ", ".join(models[:3]) + (" …" if len(models) > 3 else "")
            self._status.setText(f"✓ {len(models)} model(s): {preview}")
        else:
            self._status.setText("⚠ 没有返回模型。")

    @Slot(str)
    def _on_models_err(self, err):
        self._fetching = False
        self._reload_btn.setEnabled(True)
        self._reload_btn.setText("⟳")
        self._status.setText(f"⚠ Model fetch failed: {err}")

    # ── config ────────────────────────────────────────────────────────
    def _api_url(self):
        return self._load_state().get("api_url", "https://api.openai.com/v1")

    def _api_key(self):
        return self._load_state().get("api_key", "")

    def _history_cfg(self):
        return {**HISTORY_DEFAULTS, **self._load_state().get("history", {})}

    def _editor_cfg(self):
        return {**EDITOR_DEFAULTS, **self._load_state().get("editor", {})}

    def _apply_ui_font(self):
        """Apply the UI font size setting to the entire chat panel."""
        from qtpy.QtGui import QFont
        cfg = self._editor_cfg()
        pt = cfg.get("fs_ui", 9)
        font = QFont()
        font.setPointSize(pt)
        self.setFont(font)

    def _agentic_cfg(self):
        raw = dict(self._load_state().get("agentic", {}))
        # Migrate from pre-0.8.4 auto_confirm bool → autonomous_mode string
        if "autonomous_mode" not in raw:
            raw["autonomous_mode"] = "semi" if raw.get("auto_confirm") else "off"
        return {**AGENTIC_DEFAULTS, **raw}

    def _estimate_msg_tokens(self, m):
        """Rough token estimate for one _messages entry (4 chars ≈ 1 token)."""
        n = len(m.get("content", "")) + len(m.get("content_llm", ""))
        for att in m.get("attachments", []):
            n += len(att.get("content", ""))
        return n // 4

    def _get_token_limit(self):
        """Return the configured token limit for the current provider+model."""
        cfg     = self._history_cfg()
        provider = (self._chat_provider or "").lower()
        model    = (self._current_model  or "").lower()
        for row in cfg.get("compaction_model_limits", []):
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                continue
            row_prov  = str(row[0]).lower()
            row_model = str(row[1]).lower()
            if (row_prov in provider or provider in row_prov) and \
               (row_model in model   or model   in row_model):
                try:
                    return int(row[2])
                except (ValueError, TypeError):
                    logger.debug("Invalid token limit value %r in row %r", row[2], row)
        return cfg.get("compaction_default_limit", 100_000)

    # ── Context size estimation ──────────────────────────────────────────────

    def _compute_context_stats(self):
        """Compute a token breakdown of the context that would be sent on the next
        message (excluding the new user message itself).  Mirrors _send() slicing.
        Returns a dict with per-category token counts and summary totals."""
        cfg_h      = self._history_cfg()
        limit      = self._get_token_limit()
        thresh_pct = cfg_h.get("compaction_threshold_pct", 80)
        thresh     = limit * thresh_pct // 100
        strategy   = cfg_h.get("compaction_strategy", "cutoff")
        compact_on = cfg_h.get("compaction_enabled", False) and not self._proj_enabled

        # — Determine effective history window (mirrors _send() logic exactly) —
        hist_msgs = self._messages
        compact_summary_text = ""

        if compact_on:
            last_compact_idx = next(
                (i for i in range(len(self._messages) - 1, -1, -1)
                 if self._messages[i].get("compaction_summary")),
                None)
            if last_compact_idx is not None:
                hist_msgs = self._messages[last_compact_idx + 1:]
                compact_summary_text = self._messages[last_compact_idx].get("content", "")
            else:
                hist_msgs = list(self._messages)

            if strategy == "cutoff":
                hist_msgs = list(hist_msgs)
                while len(hist_msgs) >= 2:
                    if sum(self._estimate_msg_tokens(m) for m in hist_msgs) <= thresh:
                        break
                    hist_msgs = hist_msgs[2:]

        # — Count tokens by category —
        history_tokens    = 0
        attachment_tokens = 0
        for m in hist_msgs:
            if m.get("role") not in ("user", "assistant"):
                continue
            history_tokens += (
                len(m.get("content", "")) + len(m.get("content_llm", ""))) // 4
            for att in m.get("attachments", []):
                attachment_tokens += len(att.get("content", "")) // 4

        # — System prompt (base system prompt + agentic prompt + project root note) —
        system_tokens  = 0
        agentic_tokens = 0
        sys_p = self._sp_get_active_prompt()
        if sys_p:
            system_tokens += len(sys_p) // 4
        ag_cfg = self._agentic_cfg()
        if ag_cfg.get("enabled"):
            try:
                from .agentic_actions import build_agentic_system_prompt
                agentic_tokens = len(build_agentic_system_prompt(ag_cfg)) // 4
                system_tokens += agentic_tokens
            except Exception:
                pass
        if self._proj_root:
            system_tokens += 30   # project root path note is tiny

        # — Compaction summary injected as system note —
        compact_summary_tokens = len(compact_summary_text) // 4 if compact_summary_text else 0

        # — Project context files (cached estimate from folder selector) —
        proj_ctx_tokens = self._proj_ctx_token_estimate if self._proj_enabled else 0

        total = (history_tokens + attachment_tokens
                 + system_tokens + compact_summary_tokens + proj_ctx_tokens)

        return {
            "history":         history_tokens,
            "attachments":     attachment_tokens,
            "system":          system_tokens,
            "agentic":         agentic_tokens,
            "compact_summary": compact_summary_tokens,
            "proj_ctx":        proj_ctx_tokens,
            "total":           total,
            "limit":           limit,
            "threshold":       thresh,
            "threshold_pct":   thresh_pct,
            "compact_on":      compact_on,
            "strategy":        strategy,
        }

    def _update_ctx_size_label(self):
        """Refresh the context-size label (and its tooltip) in the params bar."""
        try:
            s = self._compute_context_stats()
        except Exception:
            return

        total = s["total"]
        limit = s["limit"]
        thresh = s["threshold"]

        def _fmt(n):
            """Format token count: ≥1 000 → 'X.Xk', else plain int."""
            return f"{n / 1000:.1f}k" if n >= 1000 else str(n)

        pct = int(total * 100 / limit) if limit > 0 else 0

        # — Label text and style —
        label_text = f"~{_fmt(total)} / {_fmt(limit)} ({pct}%)"
        if total >= limit:
            self._ctx_size_lbl.setStyleSheet(_ctx_size_style("error"))
        elif total >= thresh:
            self._ctx_size_lbl.setStyleSheet(_ctx_size_style("warn"))
        else:
            self._ctx_size_lbl.setStyleSheet(_ctx_size_style("normal"))
        self._ctx_size_lbl.setText(label_text)

        # — Tooltip HTML breakdown —
        bar_pct = min(100, pct)
        bar_color = ("#ff5555" if total >= limit
                     else "#c8a000" if total >= thresh
                     else "#4a8a4a")
        free = max(0, limit - total)

        def _pct_of_limit(n):
            return f"{int(n * 100 / limit)}%" if limit > 0 else "—"

        # Theme-aware colours for the tooltip HTML
        _dark = _is_dark_theme()
        _c_title    = "#ffffff" if _dark else "#111111"
        _c_summary  = "#b0c8b0" if _dark else "#2a5a2a"
        _c_div      = "#d0d0d0" if _dark else "#222222"
        _c_name_n   = "#c8d8c8" if _dark else "#333333"
        _c_val_n    = "#d8d8d8" if _dark else "#222222"
        _c_pct_n    = "#a0b8a0" if _dark else "#555555"
        _c_name_b   = "#ffffff" if _dark else "#000000"
        _c_val_b    = "#ffffff" if _dark else "#000000"
        _c_pct_b    = "#c0d0c0" if _dark else "#444444"
        _c_sep      = "#6a9a6a" if _dark else "#88aa88"
        _c_bar_empty = "#2a3a2a" if _dark else "#dddddd"
        _c_note     = "#789878" if _dark else "#446644"

        def _tr(label, tokens, bold=False):
            if tokens <= 0:
                return ""
            nc = _c_name_b if bold else _c_name_n
            vc = _c_val_b  if bold else _c_val_n
            pc = _c_pct_b  if bold else _c_pct_n
            return (
                f"<tr>"
                f"<td style='padding:2px 12px 2px 0; color:{nc}'>"
                f"{'<b>' if bold else ''}{label}{'</b>' if bold else ''}</td>"
                f"<td style='padding:2px 10px 2px 0; text-align:right; color:{vc}'>"
                f"{'<b>' if bold else ''}{_fmt(tokens)}{'</b>' if bold else ''}</td>"
                f"<td style='padding:2px 0; text-align:right; color:{pc}'>"
                f"{'<b>' if bold else ''}{_pct_of_limit(tokens)}{'</b>' if bold else ''}</td>"
                f"</tr>")

        # separator row
        sep = (f"<tr><td colspan='3' bgcolor='{_c_sep}' height='2' "
               f"style='font-size:1pt; line-height:1px; padding:0;'></td></tr>")

        if s["compact_on"]:
            strat = "LLM summary" if s["strategy"] == "llm" else "Cut-off"
            compact_note = (
                f"Compaction: {strat}"
                f" · Threshold: {_fmt(thresh)} ({s['threshold_pct']}%)")
        else:
            compact_note = "Compaction: off (showing full history)"

        rows = "".join(filter(None, [
            _tr("History messages",    s["history"]),
            _tr("System prompt",       s["system"])          if s["system"] > 0          else "",
            _tr("Action results & files", s["attachments"]) if s["attachments"] > 0     else "",
            _tr("Project context",     s["proj_ctx"])        if s["proj_ctx"] > 0        else "",
            _tr("Compaction buffer",   s["compact_summary"]) if s["compact_summary"] > 0 else "",
            sep,
            _tr("Total (estimated)",   total, bold=True),
            _tr("Free space",          free),
        ]))

        tooltip = (
            # No min-width on the outer div — let the stats table determine width.
            f"<div style='font-size:11px; color:{_c_div}'>"
            f"<b style='color:{_c_title}'>Used context estimation in tokens</b><br>"
            # Token summary sits above the table as plain inline text so it
            # does not force the table (and therefore the bar) to be wider.
            f"<span style='color:{_c_summary}'>"
            f"{_fmt(total)} / {_fmt(limit)} tokens ({pct}%)"
            f"</span>"
            # Single table: bar as a colspan first row, then the stats rows.
            # The bar inherits the table width (= stats content width) so it
            # is exactly as wide as the statistics below — no wider.
            f"<table cellpadding='0' cellspacing='0' style='margin:3px 0 4px 0'>"
            f"<tr>"
            f"<td colspan='3' style='padding:0 0 3px 0;'>"
            f"<table width='100%' cellpadding='0' cellspacing='0'>"
            f"<tr>"
            f"<td width='{bar_pct}%' bgcolor='{bar_color}' height='6'>&nbsp;</td>"
            f"<td bgcolor='{_c_bar_empty}' height='6'>&nbsp;</td>"
            f"</tr>"
            f"</table>"
            f"</td>"
            f"</tr>"
            f"{rows}"
            f"</table>"
            f"<span style='color:{_c_note}; font-size:10px'>{compact_note}</span>"
            f"</div>"
        )
        self._ctx_size_lbl.setToolTip(tooltip)

    def set_console_execute_fn(self, fn):
        """Called by plugin to provide IPython console execute function."""
        self._console_execute_fn = fn

    def set_load_file_fn(self, fn):
        """Called by plugin to provide editor load-file function."""
        self._load_file_fn = fn

    def set_reload_file_fn(self, fn):
        """Called by plugin to provide editor reload-file function (for patch actions)."""
        self._reload_file_fn = fn

    def _build_action_env(self):
        """Build the action_env dict passed to build_action_block."""
        import os as _os
        from .agentic_actions import execute_create_file, execute_patch_file
        cfg = self._agentic_cfg()

        # Lazy base-dir resolver — called at execution time, not at build time,
        # so it always reflects the current Spyder project even when the action
        # env was built during startup before the project finished loading.
        cfg_base = cfg.get("base_path", "").strip()

        def _get_base_dir():
            if cfg_base and _os.path.isdir(cfg_base):
                return cfg_base
            live = (self._get_project_root_fn()
                    if self._get_project_root_fn else None)
            if live and _os.path.isdir(live):
                return live
            if self._proj_root and _os.path.isdir(self._proj_root):
                return self._proj_root
            return _os.path.expanduser("~")

        def _proj_root_live():
            """Return the currently-open Spyder project root, or None if no project is open.

            Distinct from _get_base_dir(): this returns None as a security sentinel when no
            project is open, whereas _get_base_dir() always falls back to home dir for
            operational use.  Used by _proj_security_check() in markdown_renderer.py.
            """
            live = (self._get_project_root_fn()
                    if self._get_project_root_fn else None)
            if live and _os.path.isdir(live):
                return live
            if self._proj_enabled and self._proj_root and _os.path.isdir(self._proj_root):
                return self._proj_root
            return None   # no open project — security check will block the operation

        # Static snapshot used for display labels at render time (best-effort).
        base_dir = _get_base_dir()

        load_fn   = getattr(self, "_load_file_fn", None)
        reload_fn = getattr(self, "_reload_file_fn", None)

        def _create_file(path, content, bd=None):
            return execute_create_file(path, content, bd or _get_base_dir())

        def _patch_file(path, diff, bd=None):
            return execute_patch_file(path, diff, bd or _get_base_dir())

        def _run_console(code):
            if not self._console_execute_fn:
                return None
            agentic_cfg_local = self._agentic_cfg()
            auto_send = agentic_cfg_local.get("autonomous_mode") in ("semi", "full")
            if auto_send:
                def _on_output(output_text):
                    body = (f"[Console output]\n{output_text}"
                            if output_text
                            else "[Console output: (no visible output)]")
                    self.add_file_context_content("▶ Console output", body, source="result")
                    if not (self._chat_thread and self._chat_thread.isRunning()):
                        self._input.setPlainText(
                            "Here are the results of the executed actions.")
                        self._pending_agentic_response = True
                        self._send()
                try:
                    async_ok = self._console_execute_fn(code, on_output=_on_output)
                except TypeError:
                    async_ok = False
                    self._console_execute_fn(code)
                if async_ok:
                    return None   # async capture set up; callback will auto-send
                return ("Code sent to the IPython console. "
                        "Note: console output could not be captured — "
                        "it is visible in the Spyder IPython Console pane.")
            else:
                self._console_execute_fn(code)
                return None

        def _install(spec):
            if self._console_execute_fn:
                self._console_execute_fn(f"%pip install {spec.strip()}")

        def _read_file(path, bd=None, line_from=None, line_to=None):
            from .agentic_actions import read_file
            return read_file(path, bd or _get_base_dir(), line_from, line_to)

        def _ls_dir(path, bd=None):
            from .agentic_actions import ls_dir
            return ls_dir(path, bd or _get_base_dir())

        def _grep_files(pattern, scope="", bd=None):
            from .agentic_actions import grep_files
            return grep_files(pattern, bd or _get_base_dir(), scope)

        def _on_executed(block_idx, action_type, target):
            """Store execution record in the last assistant message and autosave."""
            for msg in reversed(self._messages):
                if msg.get("role") == "assistant":
                    executed = msg.setdefault("agentic_executed", [])
                    if not any(e.get("block_idx") == block_idx for e in executed):
                        executed.append({
                            "type":      action_type,
                            "target":    target,
                            "block_idx": block_idx,
                        })
                    break
            self._autosave()

        def _auto_send_single(label, output, kind="result"):
            """Called by action blocks when auto_send_results is True (single manual execute)."""
            first_line = label.split("\n")[0][:60]
            if kind == "git":
                src      = "git"
                tag_name = first_line
                body     = f"[Git command: {label}]\n{output}"
            elif kind == "read":
                src      = "result"   # "file" would be silently dropped when proj context enabled
                tag_name = f"📄 {first_line}"
                body     = f"[File: {label}]\n{output}"
            elif kind == "ls":
                src      = "result"   # "file" would be silently dropped when proj context enabled
                tag_name = f"📁 {first_line}"
                body     = f"[Directory: {label}]\n{output}"
            elif kind == "grep":
                src      = "result"   # "file" would be silently dropped when proj context enabled
                tag_name = f"🔍 {first_line}"
                body     = f"[Search: {label}]\n{output}"
            else:
                src      = "result"
                tag_name = f"✓ {first_line}"
                body     = f"[Action result: {label}]\n{output}"
            self.add_file_context_content(tag_name, body, source=src)
            # Only auto-send if not currently streaming
            if not (self._chat_thread and self._chat_thread.isRunning()):
                self._input.setPlainText(
                    "Here are the results of the executed actions.")
                self._send()

        def _delete_file(path, bd=None):
            from .agentic_actions import execute_delete_file
            return execute_delete_file(path, bd or _get_base_dir())

        def _delete_dir(path, bd=None):
            from .agentic_actions import execute_delete_dir
            return execute_delete_dir(path, bd or _get_base_dir())

        def _rename(old_path, new_path, bd=None):
            from .agentic_actions import execute_rename
            return execute_rename(old_path, new_path, bd or _get_base_dir())

        return {
            "create_file_fn":    _create_file,
            "patch_file_fn":     _patch_file,
            "run_console_fn":    _run_console,
            "install_fn":        _install,
            "delete_file_fn":    _delete_file,
            "delete_dir_fn":     _delete_dir,
            "rename_fn":         _rename,
            "load_file_fn":      load_fn,
            "reload_file_fn":    reload_fn,
            "on_executed":       _on_executed,
            "base_dir":          base_dir,
            "base_dir_fn":       _get_base_dir,
            "proj_root_fn":      _proj_root_live,
            "confirm_each":      True,
            "allow_create_file": cfg.get("allow_create_file", True),
            "allow_run_console": cfg.get("allow_run_console", True),
            "allow_install":     cfg.get("allow_install",     False),
            "allow_patch":       cfg.get("allow_patch",       True),
            "allow_git":         cfg.get("allow_git",         True),
            "allow_read":        cfg.get("allow_read",        True),
            "allow_ls":          cfg.get("allow_ls",          True),
            "allow_grep":        cfg.get("allow_grep",        True),
            "allow_delete":      cfg.get("allow_delete",      False),
            "allow_delete_dir":  cfg.get("allow_delete_dir",  False),
            "allow_rename":      cfg.get("allow_rename",      False),
            "allow_rename_dir":  cfg.get("allow_rename_dir",  False),
            "read_file_fn":          _read_file,
            "ls_dir_fn":             _ls_dir,
            "grep_files_fn":         _grep_files,
            "_exec_registry":        {},
            "auto_send_results":     cfg.get("autonomous_mode") in ("semi", "full"),
            "auto_send_fn":          _auto_send_single,
        }

    # ── copy to editor ────────────────────────────────────────────────
    def _insert_to_editor(self, text):
        result = self._get_editor_cursor()
        cursor, editor_or_diag = result

        if cursor is not None:
            try:
                cursor.insertText(text)
                editor_or_diag.setTextCursor(cursor)
                self._status.setText("✓ 已插入到编辑器光标位置。")
                return
            except Exception as e:
                editor_or_diag = str(e)

        # Fallback: clipboard
        QApplication.clipboard().setText(text)
        # Show diagnostic info so we can debug
        self._status.setText(f"Clipboard copy. Diag: {editor_or_diag}")

    # ── new chat ──────────────────────────────────────────────────────
    def _on_history_deleted(self, ref):
        """Called when a chat is deleted from the history popup."""
        collection, filename = _decode_chat_ref(ref)
        if filename == self._current_chat_file and collection == self._current_collection:
            # The currently displayed chat was deleted — clear the window
            self._current_chat_file = None
            self._messages.clear()
            self._history.clear_all()
            self._current_page = 0
            self._update_page_bar()
            self._context_files.clear()
            self._selection_counters.clear()
            self._rebuild_ctx_bar()
            self._sys_prompt.clear()
            self._sp_selected_id = CUSTOM_ID
            self._sp_populate_combo(select_id=CUSTOM_ID)
            self._status.setText("当前聊天已删除。")

    def _on_history_deleted_all(self):
        """Called when all chats are deleted via the Delete All button."""
        self._current_chat_file = None
        self._messages.clear()
        self._history.clear_all()
        self._current_page = 0
        self._update_page_bar()
        self._context_files.clear()
        self._selection_counters.clear()
        self._rebuild_ctx_bar()
        self._sys_prompt.clear()
        self._sp_selected_id = CUSTOM_ID
        self._sp_populate_combo(select_id=CUSTOM_ID)
        self._save_state(last_chat_file=None)
        self._status.setText("所有聊天已删除。")

    def _new_chat(self):
        # Save current chat to history before clearing (if enabled)
        if self._messages and self._history_cfg().get("save_on_new", True):
            self._current_chat_file = save_chat(
                self._messages,
                system_prompt=self._sp_get_active_prompt(), prompt_id=self._sp_selected_id,
                model=self._current_model,
                filename=self._current_chat_file,
                collection=self._current_collection,
                provider=self._chat_provider,
                infer_params=self._infer_params,
                project_context=self._proj_ctx_for_save(),
            )
        self._current_chat_file = None
        self._messages.clear()
        self._ag_groups.clear()
        self._history.clear_all()
        self._current_page = 0
        self._update_page_bar()
        self._context_files.clear()
        self._selection_counters.clear()
        # Optionally disable project context for new chats (configurable in settings)
        if self._history_cfg().get("proj_reset_on_new_chat", True):
            self._proj_enabled              = False
            self._proj_included_folders     = []
            self._proj_hashes               = {}
            self._proj_all_sent             = False
            self._proj_changed_count        = 0
            self._proj_ctx_token_estimate   = 0
            self._proj_toggle_btn.setChecked(False)
            self._update_proj_watcher()
        self._rebuild_ctx_bar()
        default_id = self._load_state().get("default_system_prompt_id")
        if default_id:
            p = get_prompt(default_id)
            if p:
                self._sp_selected_id = default_id
                self._sp_populate_combo(select_id=default_id)
                self._sys_prompt.setPlainText(p["content"])
            else:
                self._sp_selected_id = CUSTOM_ID
                self._sp_populate_combo(select_id=CUSTOM_ID)
                self._sys_prompt.clear()
        else:
            self._sp_selected_id = CUSTOM_ID
            self._sp_populate_combo(select_id=CUSTOM_ID)
            self._sys_prompt.clear()
        self._infer_params = {}
        self._update_summary_bar()
        self._save_state(last_chat_file=None)
        self._status.setText("新对话已开始。")

    def _clear_chat(self):
        """Clear all messages (including compactions) but keep every setting.

        Unlike '+ New Chat' this does NOT reset the system prompt, inference
        parameters, project context, or collection — everything the user has
        configured for the current conversation is left untouched.  Only the
        message history and attached context files are wiped.
        """
        if not self._messages:
            self._status.setText("没有可清除的内容。")
            return

        from qtpy.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Clear conversation",
            "Delete all messages in this conversation?\n\n"
            "Model, system prompt, and all other settings will be kept.\n"
            "The cleared chat will be saved to history first.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Always save to history before wiping — the user explicitly asked for
        # the record to be kept regardless of the 'save_on_new' autosave setting.
        saved_file = save_chat(
            self._messages,
            system_prompt=self._sp_get_active_prompt(),
            prompt_id=self._sp_selected_id,
            model=self._current_model,
            filename=self._current_chat_file,
            collection=self._current_collection,
            provider=self._chat_provider,
            infer_params=self._infer_params,
            project_context=self._proj_ctx_for_save(),
        )

        # Wipe messages and UI — keep everything else as-is.
        # Use a fresh filename so the next message starts a new history entry
        # instead of overwriting the just-saved record.
        self._current_chat_file = None
        self._messages.clear()
        self._history.clear_all()
        self._current_page = 0
        self._update_page_bar()
        self._context_files.clear()
        self._selection_counters.clear()
        self._rebuild_ctx_bar()
        self._update_ctx_size_label()
        self._save_state(last_chat_file=None)
        _saved_note = " Saved to history." if saved_file else ""
        self._status.setText(f"Conversation cleared. Settings preserved.{_saved_note}")

    def _toggle_history_popup(self):
        if self._hist_popup is None:
            main_win = _find_main_window()
            self._hist_popup = _ChatHistoryPopup(
                save_state_fn=lambda coll: self._save_state(current_collection=coll),
                parent=main_win,
            )
            self._hist_popup.load_chat.connect(self._load_chat_from_file)
            self._hist_popup.del_chat.connect(self._on_history_deleted)
            self._hist_popup.del_all.connect(self._on_history_deleted_all)

        if self._hist_popup.isVisible():
            self._hist_popup.hide()
        else:
            self._hist_popup.show_below(
                self._hist_btn,
                current_file=self._current_chat_file,
                current_collection=self._current_collection,
                current_file_collection=self._current_collection,
            )

    # ── Loading overlay ───────────────────────────────────────────────
    def _show_loading_overlay(self, text="Loading chat…"):
        """Show a centred loading label over the scroll area."""
        self._loading_base_text = text   # preserved for progress updates
        if not hasattr(self, "_loading_overlay") or self._loading_overlay is None:
            self._loading_overlay = QLabel(text, self._scroll)
            self._loading_overlay.setAlignment(Qt.AlignCenter)
            if _is_dark_theme():
                self._loading_overlay.setStyleSheet(
                    "QLabel { color: #888888; font-size: 13pt; "
                    "background: #1e1e1e; border: none; }")
            else:
                self._loading_overlay.setStyleSheet(
                    "QLabel { color: #666666; font-size: 13pt; "
                    "background: #f5f5f5; border: none; }")
        else:
            self._loading_overlay.setText(text)
        self._loading_overlay.setGeometry(self._scroll.rect())
        self._loading_overlay.show()
        self._loading_overlay.raise_()
        QApplication.processEvents()

    def _update_loading_progress(self, done, total):
        """Update the loading overlay with a percentage (called after each batch)."""
        if getattr(self, "_loading_overlay", None) is None:
            return
        base = getattr(self, "_loading_base_text", "Loading chat…")
        pct = int(done / total * 100) if total else 100
        self._loading_overlay.setText(f"{base} {pct}%")
        self._loading_overlay.repaint()

    def _hide_loading_overlay(self):
        if getattr(self, "_loading_overlay", None) is not None:
            self._loading_overlay.hide()

    def _load_chat_from_file(self, ref):
        """Load a saved chat into the current view.
        ref: encoded chat reference ("Collection/filename.json" or bare "filename.json").
        """
        collection, filename = _decode_chat_ref(ref)
        data = load_chat(filename, collection=collection)
        if data is None:
            self._status.setText("⚠ 无法加载聊天。")
            self._hide_loading_overlay()
            return
        # Save current chat first if it has content and saving is enabled
        if self._messages and self._history_cfg().get("autosave", True):
            save_chat(
                self._messages,
                system_prompt=self._sp_get_active_prompt(), prompt_id=self._sp_selected_id,
                model=self._current_model,
                filename=self._current_chat_file,
                collection=self._current_collection,
                provider=self._chat_provider,
                infer_params=self._infer_params,
                project_context=self._proj_ctx_for_save(),
            )
        # Restore state
        self._history.clear_all()
        self._show_loading_overlay()
        self._context_files.clear()
        self._selection_counters.clear()
        self._rebuild_ctx_bar()

        sys_p     = data.get("system_prompt", "")
        prompt_id = data.get("prompt_id", CUSTOM_ID) or CUSTOM_ID

        # If saved prompt no longer exists, fall back to custom
        if prompt_id != CUSTOM_ID and get_prompt(prompt_id) is None:
            prompt_id = CUSTOM_ID

        # Restore prompt selector first (it may overwrite sys_p via _sp_on_select)
        self._sp_selected_id = prompt_id
        self._sp_populate_combo(select_id=prompt_id)

        # For custom prompts, restore the text; saved prompts are set by combo
        if prompt_id == CUSTOM_ID:
            self._sys_prompt.setPlainText(sys_p)

        model = data.get("model", "")
        if model and model in self._model_list:
            self._current_model = model
            self._model_btn.setText(model + " ▾")

        # Restore project context first so _proj_root is set before
        # _build_action_env() runs — needed for base_dir and overwrite detection.
        import os as _os
        saved_proj = data.get("project_context")
        self._proj_enabled              = False
        self._proj_root                 = None
        self._proj_included_folders     = []
        self._proj_hashes               = {}
        self._proj_all_sent             = False
        self._proj_changed_count        = 0
        self._proj_ctx_token_estimate   = 0
        if saved_proj and saved_proj.get("enabled"):
            root = saved_proj.get("root", "")
            if root and _os.path.isdir(root):
                self._proj_enabled          = True
                self._proj_root             = root
                self._proj_included_folders = saved_proj.get("included_folders", [])
                self._proj_hashes           = {
                    f["path"]: f["hash"]
                    for f in saved_proj.get("files", [])
                }
                self._proj_all_sent = True
                self._proj_changed_count = self._count_proj_changes()
            else:
                self._status.setText("⚠ 项目上下文：未找到根文件夹。")
        self._proj_toggle_btn.setChecked(self._proj_enabled)
        self._update_proj_watcher()
        self._rebuild_ctx_bar()

        # Build action_env now that _proj_root is available, so action blocks
        # rendered during finalize_assistant() get correct base_dir,
        # run_console_fn, and overwrite detection from the first render.
        if self._agentic_cfg().get("enabled"):
            self._history._action_env = self._build_action_env()
        else:
            self._history._action_env = None

        # ── Incremental batch rendering ──────────────────────────────────────
        # Store the complete message list immediately (source of truth) and
        # render only the last page.  _page_rendering=True suppresses the
        # self._messages.append() calls inside _process_load_batch so the list
        # is not double-populated.
        all_msgs = list(data.get("messages", []))
        self._messages.clear()
        self._messages.extend(all_msgs)
        total = self._total_pages()
        self._current_page   = total - 1                    # open on last page
        self._msgs_preloaded = True                         # suppress appends in _process_load_batch
        # NOTE: _page_rendering stays False — _finish_load_p2 must restore file-load state

        self._load_pending_msgs   = self._page_slice(self._current_page)
        self._load_total_msgs     = len(self._load_pending_msgs)
        self._load_ref_filename   = filename
        self._load_ref_collection = collection
        self._load_ref_data       = data     # accessed by _finish_load_p2()
        self._load_seq           += 1        # cancel any stale in-progress batch load
        self._history._bulk_loading = True
        self._history.setUpdatesEnabled(False)
        self._process_load_batch(self._load_seq)

    _LOAD_BATCH = 12     # messages rendered per QTimer tick during history load
    _LOAD_BATCH_ENABLED = True   # False = load all messages synchronously (no UI updates until done)
    _PAGE_SIZE = 120     # max messages rendered per page; change this one line to tune

    def _render_one_msg(self, msg: dict):
        """Render one message dict into _ChatHistory. Does NOT touch self._messages."""
        role    = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            attachments = msg.get("attachments", [])
            # New format: content is plain user text, attachments are separate.
            # Legacy format: file blocks embedded in content — strip them.
            display = content
            if not attachments and "```" in content and content.startswith("File: "):
                parts = content.rsplit("```", 2)
                if len(parts) >= 2:
                    display = parts[-1].strip()
            spans  = msg.get("command_spans")
            _is_ag = msg.get("agentic_response", False)
            _ag_tip = None
            if _is_ag:
                _tip_parts = [display]
                for _a in attachments:
                    if isinstance(_a, dict):
                        _tip_parts.append(
                            f"\n── {_a['name']} ──\n{_a.get('content','')}")
                _ag_tip = "\n".join(_tip_parts)
            self._history.add_user(
                display,
                attachments=attachments or None,
                command_spans=[(s[0], s[1]) for s in spans] if spans else None,
                agentic_response=_is_ag,
                agentic_tooltip=_ag_tip,
            )
        elif role == "assistant" and msg.get("compaction_summary"):
            self._history.add_compaction_block(content)
        elif role == "assistant":
            executed_list = msg.get("agentic_executed", [])
            self._history._current_executed_blocks = {
                e["block_idx"] for e in executed_list
                if isinstance(e.get("block_idx"), int)
            }
            self._history.finalize_assistant(content)
            self._history._current_executed_blocks = set()
        elif role == "assistant_error":
            self._history.show_error(content)

    def _process_load_batch(self, seq):
        """Render the next batch of messages during a history load.

        *seq* is the load-sequence number captured when this load started.
        If self._load_seq no longer matches, a newer load has started and
        this batch is silently abandoned.
        """
        if self._load_seq != seq:
            return  # superseded by a newer _load_chat_from_file call

        # When batching is disabled consume all remaining messages at once so
        # the entire load runs synchronously in this single call.
        size = self._LOAD_BATCH if self._LOAD_BATCH_ENABLED else len(self._load_pending_msgs)
        batch = self._load_pending_msgs[:size]
        self._load_pending_msgs = self._load_pending_msgs[size:]

        for msg in batch:
            self._render_one_msg(msg)
            if not self._msgs_preloaded:
                self._messages.append(msg)

        done = self._load_total_msgs - len(self._load_pending_msgs)
        self._update_loading_progress(done, self._load_total_msgs)

        if self._load_pending_msgs:
            # Yield to event loop before next batch so the UI stays responsive
            QTimer.singleShot(0, lambda: self._process_load_batch(seq))
        else:
            self._finish_load(seq)

    # ── Paging helpers ────────────────────────────────────────────────────

    def _total_pages(self) -> int:
        """Return total page count (always at least 1)."""
        return max(1, -(-len(self._messages) // self._PAGE_SIZE))

    def _page_slice(self, page_idx: int) -> list:
        """Return the message slice for the given 0-indexed page."""
        start = page_idx * self._PAGE_SIZE
        return self._messages[start : start + self._PAGE_SIZE]

    def _update_page_bar(self):
        """Show/hide and update the page bar to reflect current state."""
        total = self._total_pages()
        self._page_bar.setVisible(total > 1)
        self._page_bar.update_state(self._current_page, total)

    def _navigate_to_page(self, page_idx: int):
        """Navigate to a different page (called by page bar signal)."""
        page_idx = max(0, min(page_idx, self._total_pages() - 1))
        if page_idx == self._current_page:
            return
        self._current_page = page_idx
        self._reload_current_page()

    def _reload_current_page(self):
        """Re-render _ChatHistory for self._current_page using the full batched pipeline.

        Reuses _process_load_batch → _finish_load → _finish_load_p2 so that:
        - The loading overlay shows "Page N loading…" with a progress bar.
        - Batched QTimer.singleShot(0) yields keep the UI responsive.
        - The single event-loop tick before _finish_load_p2 avoids sizeHint staleness.
        Does NOT modify self._messages.
        """
        self._page_rendering  = True   # signals _finish_load_p2 to skip state restoration
        self._msgs_preloaded  = True   # suppresses append in _process_load_batch
        self._load_seq       += 1                           # cancels any in-progress batch
        self._load_pending_msgs = self._page_slice(self._current_page)
        self._load_total_msgs   = len(self._load_pending_msgs)
        self._history._bulk_loading = True
        self._history.setUpdatesEnabled(False)
        self._history.clear_all()
        self._show_loading_overlay(f"Page {self._current_page + 1} loading…")
        self._process_load_batch(self._load_seq)

    # ── Agentic pair collapsing ───────────────────────────────────────────

    def _wrap_agentic_pairs(self):
        """Scan the currently-rendered _blocks for consecutive
        (assistant-with-fences, user-agentic_response) pairs and collapse them.

        Consecutive pairs are grouped into a single collapsible header so that
        e.g. two sequential git-command pairs show as one
        "Agentic: Git command ×2 ▶" line rather than two separate lines.

        *_blocks* is NEVER modified — every existing entry keeps its original
        index, so the block_idx → msg_idx mapping used by _on_delete_exchange
        stays valid.

        Groups are tracked in self._ag_groups (keyed by id(first_asst_widget)).
        On each call the method PRUNES stale entries (widgets from previous page
        renders that no longer exist in _blocks), then for each detected run:
          • No existing group → fresh collapse via _insert_*_collapse_header
          • Existing group, same size → no-op (already correct)
          • Existing group, smaller than new run → surgical extension via
            _extend_agentic_group (no undo/redo, no visual artifact)
        This makes the method idempotent for history loads (always fresh after
        clear_all) and flicker-free for live streaming (groups only grow).
        """
        # ── Prune stale group entries from previous page renders ─────────────
        current_ids = {id(bw) for _, bw in self._history._blocks}
        for k in list(self._ag_groups):
            if k not in current_ids:
                del self._ag_groups[k]

        # ── Detect runs and apply / extend / no-op ───────────────────────────
        page_start = self._current_page * self._PAGE_SIZE
        blocks     = self._history._blocks

        i = 0
        while i < len(blocks):
            # Collect a run of consecutive agentic pairs starting at i
            run = []   # [(block_idx_asst, block_idx_user, assistant_msg), ...]
            j = i
            while j + 1 < len(blocks):
                mj = page_start + j
                if mj + 1 >= len(self._messages):
                    break
                msg      = self._messages[mj]
                next_msg = self._messages[mj + 1]
                if (msg.get("role") == "assistant"
                        and bool(msg.get("agentic_executed"))
                        and next_msg.get("role") == "user"
                        and next_msg.get("agentic_response", False)):
                    run.append((j, j + 1, msg))
                    j += 2
                else:
                    break

            if run:
                first_asst = blocks[run[0][0]][1]
                key        = id(first_asst)
                existing   = self._ag_groups.get(key)
                if existing is None:
                    # Fresh: create collapse for the whole run
                    if len(run) >= 2:
                        self._insert_grouped_collapse_header(run, blocks)
                    else:
                        self._insert_agentic_collapse_header(
                            blocks[run[0][0]][1], blocks[run[0][1]][1],
                            run[0][2], run[0])
                elif len(existing["run"]) < len(run):
                    # Grow: surgically extend — zero visual artifact
                    new_pairs = run[len(existing["run"]):]
                    self._extend_agentic_group(existing, new_pairs, blocks)
                # else: sizes match → no-op (already correctly grouped)
                i = j
            else:
                i += 1

    def _insert_agentic_collapse_header(self, asst_widget, user_widget,
                                        assistant_msg, run_entry):
        """Collapse a single agentic (assistant + user) pair into the title row.

        The "Assistant:" title row gets a clickable summary label
        ("Agentic: Read file ▶") inserted at position 1.  The label is VISIBLE
        when collapsed, shows "▼" when expanded.

        Uses mutable containers (_all_hidden, _all_db, _label_info) captured by
        the toggle closure so that _extend_agentic_group() can surgically grow
        the group later — no undo/redo needed, no visual artifact.

        Registers the group state in self._ag_groups[id(asst_widget)].
        *_blocks* is never modified — block_idx mappings stay valid.
        """
        executed  = assistant_msg.get("agentic_executed", [])
        labels    = _agentic_action_labels(executed)
        label_counts = {}
        for lbl in labels:
            label_counts[lbl] = label_counts.get(lbl, 0) + 1
        label_str = ", ".join(labels) if labels else "Agentic action"

        cl = asst_widget.layout()
        if cl is None or cl.count() < 2:
            return  # unexpected container structure — bail out safely

        # The title row is the first item — a QHBoxLayout
        title_item = cl.itemAt(0)
        if title_item is None:
            return
        title_row = title_item.layout()
        if title_row is None:
            return

        # Collect content widgets (everything after the title row) so we can
        # hide/show them together with the user agentic block.
        content_widgets = []
        for k in range(1, cl.count()):
            item = cl.itemAt(k)
            if item and item.widget():
                content_widgets.append(item.widget())

        # Find the delete bar (last widget in title row); hidden when collapsed.
        delete_bar = None
        for k in range(title_row.count() - 1, -1, -1):
            item = title_row.itemAt(k)
            if item and item.widget():
                delete_bar = item.widget()
                break

        # Mutable containers captured by the toggle closure — _extend_agentic_group
        # appends new widgets to these lists so the closure automatically
        # shows/hides them on future toggle calls.
        _all_hidden = list(content_widgets) + [user_widget]  # grows on extension
        _all_db     = [delete_bar] if delete_bar else []
        _label_info = {"str": label_str}                     # updated on extension

        # Summary label inserted at pos 1 in the title row.
        summary_lbl = QLabel(f"Agentic: {label_str} ▶")
        summary_lbl.setStyleSheet(
            "color: #c8a000; font-size: 10px; background: transparent;")
        summary_lbl.setCursor(Qt.PointingHandCursor)
        title_row.insertWidget(1, summary_lbl)

        # Initial collapsed state
        for w in _all_hidden:
            w.setVisible(False)
        for db in _all_db:
            db.setVisible(False)

        def _toggle():
            # Use the first user widget as the expand/collapse indicator
            vis = not user_widget.isVisible()
            for w in _all_hidden:
                w.setVisible(vis)
            for db in _all_db:
                db.setVisible(vis)
            summary_lbl.setText("▼" if vis else f"代理：{_label_info['str']} ▶")

        _ef = _ClickEventFilter(_toggle, summary_lbl)
        summary_lbl.installEventFilter(_ef)

        # Register group state so _wrap_agentic_pairs() can extend it later
        self._ag_groups[id(asst_widget)] = {
            "summary_lbl":  summary_lbl,
            "label_info":   _label_info,
            "hidden":       _all_hidden,
            "db_list":      _all_db,
            "label_counts": label_counts,
            "run":          [run_entry],
            "indicator":    user_widget,   # visibility indicator for toggle state
        }

    def _insert_grouped_collapse_header(self, run, blocks):
        """Collapse a run of ≥2 consecutive agentic pairs into a single header.

        *run* is a list of (block_idx_asst, block_idx_user, assistant_msg)
        tuples.  The summary label is injected into the FIRST assistant block's
        title row; all other blocks in the run are hidden.

        Uses the same mutable-container pattern as _insert_agentic_collapse_header
        so that _extend_agentic_group() can grow the group without any undo step.

        Registers the group state in self._ag_groups[id(first_asst)].
        *_blocks* is never modified — block_idx mappings stay valid.
        """
        first_i, first_j, _ = run[0]
        first_asst  = blocks[first_i][1]
        first_user  = blocks[first_j][1]

        # ── Build summary label text ──────────────────────────────────────
        label_counts: dict = {}
        for (_, _, asst_msg) in run:
            for lbl in _agentic_action_labels(asst_msg.get("agentic_executed", [])):
                label_counts[lbl] = label_counts.get(lbl, 0) + 1
        label_parts = [
            (f"{lbl} ×{n}" if n > 1 else lbl)
            for lbl, n in label_counts.items()
        ]
        label_str   = ", ".join(label_parts) if label_parts else "Agentic actions"
        _label_info = {"str": label_str}

        # ── Access the first assistant container's title row ──────────────
        cl = first_asst.layout()
        if cl is None or cl.count() < 2:
            return
        title_item = cl.itemAt(0)
        if title_item is None:
            return
        title_row = title_item.layout()
        if title_row is None:
            return

        # Delete bar of the first assistant
        delete_bar_first = None
        for k in range(title_row.count() - 1, -1, -1):
            item = title_row.itemAt(k)
            if item and item.widget():
                delete_bar_first = item.widget()
                break

        # Content widgets inside the first assistant container
        first_content = []
        for k in range(1, cl.count()):
            item = cl.itemAt(k)
            if item and item.widget():
                first_content.append(item.widget())

        # Mutable lists captured by the toggle closure
        # _all_hidden holds: first asst content + all user widgets +
        #                    subsequent asst containers (grows on extension).
        # Subsequent asst containers are hidden wholesale (children follow).
        _all_hidden = (list(first_content)
                       + [blocks[bj][1] for (_, bj, _) in run]
                       + [blocks[bi][1] for (bi, _, _) in run[1:]])
        _all_db     = [delete_bar_first] if delete_bar_first else []

        # ── Toggle label in first title row ───────────────────────────────
        summary_lbl = QLabel(f"代理：{label_str} ▶")
        summary_lbl.setStyleSheet(
            "color: #c8a000; font-size: 10px; background: transparent;")
        summary_lbl.setCursor(Qt.PointingHandCursor)
        title_row.insertWidget(1, summary_lbl)

        # ── Initial collapsed state ───────────────────────────────────────
        for w in _all_hidden:
            w.setVisible(False)
        for db in _all_db:
            db.setVisible(False)

        def _toggle():
            vis = not first_user.isVisible()
            for w in _all_hidden:
                w.setVisible(vis)
            for db in _all_db:
                db.setVisible(vis)
            summary_lbl.setText("▼" if vis else f"代理：{_label_info['str']} ▶")

        _ef = _ClickEventFilter(_toggle, summary_lbl)
        summary_lbl.installEventFilter(_ef)

        # Register group state
        self._ag_groups[id(first_asst)] = {
            "summary_lbl":  summary_lbl,
            "label_info":   _label_info,
            "hidden":       _all_hidden,
            "db_list":      _all_db,
            "label_counts": label_counts,
            "run":          list(run),
            "indicator":    first_user,   # visibility indicator for toggle state
        }

    def _extend_agentic_group(self, group, new_pairs, blocks):
        """Surgically extend an existing collapse group with new (asst, user) pairs.

        Appends new widgets to the SAME mutable lists already captured by the
        toggle closure — no undo, no remove+reinsert, zero visual artifact.
        The summary label text is updated in-place via setText().

        Respects the current expanded/collapsed state: if the group is expanded
        (user is reading), new pair widgets appear visible; if collapsed, hidden.
        """
        is_collapsed = "▶" in group["summary_lbl"].text()

        for (bi, bj, msg) in new_pairs:
            asst_w = blocks[bi][1]
            user_w = blocks[bj][1]
            # Subsequent asst containers are hidden wholesale.
            # The first asst (group header) stays visible — not added here.
            new_widgets = [user_w, asst_w]
            # Update label counts
            for lbl in _agentic_action_labels(msg.get("agentic_executed", [])):
                group["label_counts"][lbl] = group["label_counts"].get(lbl, 0) + 1
            # Extend mutable hidden list (toggle closure iterates this)
            group["hidden"].extend(new_widgets)
            # Respect expanded/collapsed state
            for w in new_widgets:
                w.setVisible(not is_collapsed)
            group["run"].append((bi, bj, msg))

        # Rebuild label string and update in-place (no remove/reinsert of label)
        new_label_str = ", ".join(
            f"{lbl} ×{n}" if n > 1 else lbl
            for lbl, n in group["label_counts"].items()
        )
        group["label_info"]["str"] = new_label_str
        if is_collapsed:
            group["summary_lbl"].setText(f"代理：{new_label_str} ▶")
        # If expanded ("▼"), leave the arrow; text refreshes next time user collapses

    # ─────────────────────────────────────────────────────────────────────────

    def _finish_load(self, seq):
        """Finalise a history load after all message batches have been rendered.

        Phase 1 (this method): exit bulk mode, re-enable widget updates, and
        add the regenerate button to the last assistant block — all BEFORE any
        sizeHint computation.  Then yield one event-loop tick via
        QTimer.singleShot(0) so Qt can process the pending LayoutRequest events
        for items in the final batch (which had no event-loop yield before
        _finish_load was called).  Without this yield those items' word-wrapped
        QLabel sizeHints are computed at width=0, producing a massively inflated
        total layout height that causes the visible empty-space jump.

        Phase 2 (_finish_load_p2): runs after the event-loop tick; by then all
        children have been sized at their correct widths and sizeHint() is
        accurate.  Performs the single layout/resize pass and restores state.
        """
        if self._load_seq != seq:
            return  # superseded

        self._history._bulk_loading = False
        self._history.setUpdatesEnabled(True)
        # Regenerate button only belongs on the last assistant block;
        # deferred from finalize_assistant() to avoid O(N²) scans during bulk load.
        # Must happen BEFORE the layout/sizeHint pass so item state is finalised.
        self._history._update_regenerate_button()

        # Yield to the event loop so Qt processes pending LayoutRequest events
        # for all items (especially the last batch that had no prior yield).
        # _finish_load_p2 will run once those events have been dispatched.
        QTimer.singleShot(0, lambda: self._finish_load_p2(seq))

    def _finish_load_p2(self, seq):
        """Phase 2 of chat-load finalisation — runs after one event-loop tick.

        The singleShot(0) in _finish_load gives Qt one event-loop cycle to
        process pending LayoutRequest events before we do the final resize.

        Handles two cases:
        - was_page_render=True  → page navigation / post-deletion re-render;
          scroll to top, update page bar, no state restoration.
        - was_page_render=False → initial file load; restore all state and
          scroll to bottom (existing behaviour).
        """
        if self._load_seq != seq:
            return  # superseded by a later load

        was_page_render      = self._page_rendering
        self._page_rendering = False
        self._msgs_preloaded = False

        # Collapse consecutive agentic (assistant+user) pairs into a single
        # expandable header widget.  Must run BEFORE invalidate()/sizeHint()
        # so hidden inner widgets contribute 0 px to the measured height.
        self._wrap_agentic_pairs()

        self._history._lay.invalidate()
        _h = max(1, self._history._lay.sizeHint().height())
        self._history.resize(self._history.width(), _h)
        self._history.updateGeometry()

        self._update_page_bar()

        if was_page_render:
            # Page navigation or post-deletion re-render — no state restore.
            # Last page → scroll to bottom so new messages are visible;
            # any other page → scroll to top.
            self._hide_loading_overlay()
            if self._current_page >= self._total_pages() - 1:
                self._deferred_scroll_to_bottom()
            else:
                self._scroll.verticalScrollBar().setValue(0)
            return

        # ── Initial file load — restore provider/params/state, scroll to bottom ──
        filename   = self._load_ref_filename
        collection = self._load_ref_collection
        data       = self._load_ref_data

        self._hide_loading_overlay()
        self._current_chat_file  = filename
        self._current_collection = collection
        self._save_state(
            last_chat_file=_encode_chat_ref(collection, filename),
            current_collection=collection,
        )

        # Restore per-chat provider and inference params
        current_provider = self._load_state().get("provider_type", "custom")
        saved_provider   = data.get("provider") or ""
        if saved_provider and saved_provider != current_provider:
            # Chat was saved under a different provider — reset params
            self._infer_params  = {}
            self._chat_provider = current_provider
        else:
            self._infer_params  = dict(data.get("infer_params") or {})
            self._chat_provider = current_provider
        self._update_summary_bar()
        self._update_ctx_size_label()

        self._status.setText(f"Loaded: {data.get('preview', filename)[:40]}")
        self._deferred_scroll_to_bottom()

    # ── settings ──────────────────────────────────────────────────────
    def _open_settings_sp_tab(self):
        """Open Settings dialog with the System Prompts tab pre-selected."""
        self._open_settings(initial_tab=5)

    def _open_settings(self, initial_tab=0):
        state = self._load_state()
        old_provider = state.get("provider_type", "custom")
        # Parent dialog to the top-level window (Spyder main window) rather
        # than this docked ChatPanel. Parenting to a deeply-nested child
        # widget can cause Qt on Windows to briefly flash a top-level HWND
        # with the application name ("Spyder") before the dialog is fully
        # parented. Top-level-as-parent avoids this transient window.
        dlg_parent = self.window() or self
        dlg = SettingsDialog(
            dlg_parent,
            provider_type    = state.get("provider_type", "openai"),
            api_url          = state.get("api_url", "https://api.openai.com/v1"),
            api_key          = state.get("api_key", ""),
            default_system_prompt_id = state.get("default_system_prompt_id"),
            editor_cfg       = state.get("editor", {}),
            history_cfg      = state.get("history", {}),
            azure_deployment = state.get("azure_deployment", ""),
            azure_api_version= state.get("azure_api_version", "2024-02-01"),
            commands         = load_commands(),
            fim_cfg          = state.get("fim", {}),
            agentic_cfg      = state.get("agentic", {}),
            model_list       = list(self._model_list),
            initial_tab      = initial_tab,
        )
        if dlg.exec_() == QDialog.Accepted:
            v = dlg.values()
            self._save_state(
                provider_type            = v["provider_type"],
                agentic                  = v.get("agentic", {}),
                api_url                  = v["api_url"],
                api_key                  = v["api_key"],
                azure_deployment         = v["azure_deployment"],
                azure_api_version        = v["azure_api_version"],
                editor                   = v["editor"],
                history                  = v["history"],
                fim                      = v["fim"],
                default_system_prompt_id = v["default_system_prompt_id"],
            )
            self._history._font_cfg = self._editor_cfg()
            self._apply_ui_font()
            self._fetching = False
            self._status.setText("设置已保存。")
            self._fetch_models()
            # Refresh prompt combo in case prompts were added/deleted
            self._sp_populate_combo()
            # Reload commands into the input widget
            self._input.set_commands(load_commands(), builtin_factory=self._get_active_builtins)
            # If provider changed, reset per-chat inference params
            if v["provider_type"] != old_provider:
                self._on_provider_changed(v["provider_type"])
            # Update git poll timer interval from settings
            _poll_secs = self._history_cfg().get("git_poll_interval", 10)
            self._git_poll_timer.setInterval(_poll_secs * 1000)
            # Refresh git bar based on updated show_git_bar setting.
            # Call _refresh_git_status() unconditionally — it already handles
            # all guards internally (show_git_bar flag, proj_root/cwd fallback,
            # and in-flight thread check).  The old extra `and self._proj_root`
            # guard was wrong: it hid the bar when git was working via the cwd
            # fallback and no project was explicitly open.
            self._refresh_git_status()
            # Refresh context size bar — token limits may have changed
            self._update_ctx_size_label()

    # ── send / stop ───────────────────────────────────────────────────
    def _send(self):
        # Snapshot active commands BEFORE clearing the input (clear() resets them)
        active_commands_snapshot = list(self._input._active_commands)
        display_text = self._input.toPlainText().strip()
        if not display_text:
            return
        if self._chat_thread is not None and self._chat_thread.isRunning():
            return
        self._input.clear()

        # Snapshot and clear pending context files
        pending_attachments = list(self._context_files)
        if pending_attachments:
            self._context_files.clear()
            self._rebuild_ctx_bar()

        # Build structured message — content = display text for UI / history.
        # content_llm = expanded text frozen at send time so history replay is
        # correct even if the command is later edited or deleted in Settings.
        user_msg = {
            "role": "user",
            "content": display_text,
        }
        if active_commands_snapshot:
            # Expand spans against the display_text to produce the full LLM prompt
            chars = list(display_text)
            for c in sorted(active_commands_snapshot,
                            key=lambda x: x["start"], reverse=True):
                s, l = c["start"], c["length"]
                prompt = get_command_prompt(c["name"], self._input._commands)
                if prompt:
                    chars[s:s+l] = list(prompt)
            user_msg["content_llm"] = "".join(chars)
            user_msg["command_spans"] = [
                [c["start"], c["length"]] for c in active_commands_snapshot
            ]
        if pending_attachments:
            user_msg["attachments"] = [
                {"name": name, "content": content}
                for name, content, *_ in pending_attachments
            ]
        if self._pending_agentic_response:
            user_msg["agentic_response"] = True
            self._pending_agentic_response = False

        # Inject project context (full on first send, delta on subsequent)
        if self._proj_enabled and self._proj_root:
            try:
                proj_block = self._collect_project_context()
                if proj_block:
                    user_msg["project_context_block"] = proj_block
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(
                    "Project context collection failed: %s", e)

        llm_content = _build_llm_content(user_msg)

        # Update action_env so streaming blocks get correct callbacks/config
        agentic_cfg = self._agentic_cfg()
        if agentic_cfg.get("enabled"):
            self._history._action_env = self._build_action_env()
        else:
            self._history._action_env = None

        # Build full message list for LLM (system prompt + history + new)
        cfg_h     = self._history_cfg()
        # Constraint B: no compaction when project context is active
        compact_on = cfg_h.get("compaction_enabled", False) and not self._proj_enabled

        # Determine the effective history window
        hist_msgs          = self._messages   # default: full list
        compact_summary_text = None

        if compact_on:
            # Find last compaction summary — it anchors the new window start
            last_compact_idx = next(
                (i for i in range(len(self._messages) - 1, -1, -1)
                 if self._messages[i].get("compaction_summary")),
                None)
            if last_compact_idx is not None:
                hist_msgs            = self._messages[last_compact_idx + 1:]
                compact_summary_text = self._messages[last_compact_idx].get("content", "")
            else:
                hist_msgs = list(self._messages)

            # Trim history window to fit within token budget
            if cfg_h.get("compaction_strategy", "cutoff") == "cutoff":
                # Cut-off: trim to threshold (80 % of limit by default)
                limit  = self._get_token_limit()
                thresh = limit * cfg_h.get("compaction_threshold_pct", 80) // 100
                while len(hist_msgs) >= 2:
                    total = sum(self._estimate_msg_tokens(m) for m in hist_msgs)
                    if total <= thresh:
                        break
                    # Drop oldest pair (user + following assistant)
                    hist_msgs = hist_msgs[2:]
            else:
                # LLM Summary: cap to the hard token limit so the API does not
                # reject the compaction request on very long histories (e.g. when
                # a user switches from cut-off to LLM Summary on an accumulated
                # chat that is many times over the limit).
                hard_limit = self._get_token_limit()
                while len(hist_msgs) >= 2:
                    total = sum(self._estimate_msg_tokens(m) for m in hist_msgs)
                    if total <= hard_limit:
                        break
                    hist_msgs = hist_msgs[2:]

        messages = []
        sys_p = self._sp_get_active_prompt()
        if sys_p:
            messages.append({"role": "system", "content": sys_p})

        # Inject agentic system prompt when enabled — dynamically built from
        # enabled fence flags so the LLM only sees fences it is allowed to use.
        if agentic_cfg.get("enabled"):
            from .agentic_actions import build_agentic_system_prompt
            agentic_sys = build_agentic_system_prompt(agentic_cfg)
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] += "\n\n" + agentic_sys
            else:
                messages.insert(0, {"role": "system", "content": agentic_sys})

        # Inject project root path so the LLM knows the base directory for file ops.
        # Added whenever a Spyder project is open, regardless of project-context toggle.
        # Use the live root from the plugin fn so the value is always current; fall back
        # to the cached _proj_root only if the live call returns nothing.
        import os as _os_pr
        _live_proj_root = (
            (self._get_project_root_fn() if self._get_project_root_fn else None)
            or self._proj_root
        )
        if _live_proj_root and _os_pr.path.isdir(_live_proj_root):
            # Keep cached value in sync so git bar / watcher stay correct.
            if _live_proj_root != self._proj_root:
                self._proj_root = _live_proj_root
            _proj_note = (
                f"Active project root: {_live_proj_root}\n"
                "Use this as the base directory for all file operations "
                "(read, ls, grep, create, patch) unless the user specifies "
                "an absolute path."
            )
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] += "\n\n" + _proj_note
            else:
                messages.insert(0, {"role": "system", "content": _proj_note})

        # Inject compaction summary as a system-level context note when present
        if compact_summary_text:
            note = (
                "The following is a summary of the earlier portion of this conversation "
                "that has been compacted to save context space:\n\n" + compact_summary_text)
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] += "\n\n" + note
            else:
                messages.insert(0, {"role": "system", "content": note})

        for m in hist_msgs:
            if m.get("role") not in ("user", "assistant"):
                continue
            messages.append({"role": m["role"],
                             "content": _build_llm_content(m)})
        messages.append({"role": "user", "content": llm_content})

        _attachments = user_msg.get("attachments", [])

        # Build tooltip for agentic output blocks — shows full text + attachment content
        _is_agentic = user_msg.get("agentic_response", False)
        if _is_agentic:
            _tip_parts = [display_text]
            for _att in _attachments:
                _tip_parts.append(f"\n── {_att['name']} ──\n{_att['content']}")
            _agentic_tooltip = "\n".join(_tip_parts)
        else:
            _agentic_tooltip = None

        # Update UI — if the new message would land on a different page, navigate there first
        expected_idx = len(self._messages)
        target_page  = expected_idx // self._PAGE_SIZE
        if target_page != self._current_page:
            self._current_page = target_page
            self._history.clear_all()
            for _pm in self._page_slice(target_page):
                self._render_one_msg(_pm)
            self._history._update_regenerate_button()
            self._update_page_bar()
            # Collapse any agentic pairs that exist on the re-rendered page
            self._wrap_agentic_pairs()

        # Show display_text with command highlights in chat bubble
        self._history.add_user(
            display_text,
            attachments=_attachments or None,
            command_spans=[
                (c["start"], c["length"])
                for c in active_commands_snapshot
            ] or None,
            agentic_response=_is_agentic,
            agentic_tooltip=_agentic_tooltip,
        )
        self._messages.append(user_msg)
        # When this send is the agentic-response half of an action pair, collapse
        # the completed (assistant-fences + this user) pair into a header widget.
        # Must be done BEFORE add_assistant_start() creates the next streaming block.
        if _is_agentic:
            self._wrap_agentic_pairs()
        self._current_lbl = self._history.add_assistant_start()
        self._assistant_buf    = ""
        self._rendered_char_end = 0
        self._streaming_code_edit  = None
        self._streaming_think_edit = None
        self._auto_scroll = True   # re-enable auto-scroll for this new exchange

        worker = _ChatWorker(
            self._api_url(), self._api_key(),
            self._current_model, messages,
            extra_params=self._build_extra_params())
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.chunk_ready.connect(self._on_chunk)
        worker.finished.connect(self._on_done)
        worker.error.connect(self._on_err)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._chat_worker = worker
        self._chat_thread = thread

        self._page_bar.setEnabled(False)
        self._send_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status.setText(f"Generating with {self._current_model}…")
        thread.start()

    def _stop(self):
        if self._chat_worker:
            self._chat_worker.stop()
        self._status.setText("已停止。")

    @Slot(str)
    def _on_chunk(self, text):
        if not self._assistant_buf:          # first token — hide spinner, show tail bar
            self._history.hide_spinner()
            if self._current_lbl:
                self._current_lbl.show()
        self._assistant_buf += text
        # Skip raw tail-label update when a live code widget is active — the
        # widget owns the display; writing raw code into the label and then
        # immediately clearing it in _try_render_complete_blocks causes flicker.
        if (self._current_lbl
                and self._streaming_code_edit  is None
                and self._streaming_think_edit is None):
            self._current_lbl.setText(
                self._current_lbl.text() + text)
        # On every newline, promote any newly completed blocks to rendered widgets
        if '\n' in text:
            self._try_render_complete_blocks()
        # Scrolling is handled automatically by rangeChanged signal

    def _try_render_complete_blocks(self):
        """Parse _assistant_buf, render complete blocks into the rendered zone,
        and update the tail label with only the current incomplete block text."""
        import re as _re
        from qtpy.QtWidgets import QPlainTextEdit as _PTE
        from qtpy.QtGui import QFont as _QFont

        buf = self._assistant_buf
        buf_lower = buf.lower()

        # ── Finalize live think widget when </think> just arrived ─────────
        # The chunk that delivered </think> is now in buf but the live-think
        # branch below won't run (its guard requires </think> to be absent).
        # Update the widget content to the final stripped value, then fall
        # through to standard promotion so post-think text is handled.
        if self._streaming_think_edit is not None and '</think>' in buf_lower:
            think_start = buf_lower.index('<think>') + len('<think>')
            think_end   = buf_lower.index('</think>')
            self._streaming_think_edit.setPlainText(
                buf[think_start:think_end].strip())
            self._streaming_think_edit = None
            # _rendered_char_end will be corrected by standard promotion below

        # ── Live-update streaming think block ────────────────────────────
        # While <think> is open (no </think> yet), build/update the widget
        # in place on every newline instead of suppressing all rendering.
        elif '<think>' in buf_lower and '</think>' not in buf_lower:
            think_tag_start = buf_lower.index('<think>')
            think_content   = buf[think_tag_start + len('<think>'):]

            # Promote any blocks that appear before <think> (uncommon but
            # possible if the model emits a preamble before its think tag).
            pre_buf = buf[:think_tag_start]
            if pre_buf.strip():
                pre_blocks = parse_blocks(pre_buf)
                new_pre = pre_blocks[self._history._rendered_block_count:]
                for blk in new_pre:
                    self._history.push_rendered_block(blk)

            # Create the widget on the first newline inside <think>
            if self._streaming_think_edit is None:
                cfg = {**EDITOR_DEFAULTS,
                       **(getattr(self._history, "_font_cfg", None) or {})}
                dummy = {"type": "think", "content": think_content}
                w = build_think(dummy, cfg.get("fs_think", 9))
                self._streaming_think_edit = w.findChild(_PTE)
                self._history.push_rendered_widget(w)
            else:
                self._streaming_think_edit.setPlainText(think_content)

            # Auto-scroll to bottom so the latest thinking is always visible
            vsb = self._streaming_think_edit.verticalScrollBar()
            vsb.setValue(vsb.maximum())

            # Whole buffer is accounted for by the widget — blank the tail label
            self._rendered_char_end = len(buf)
            if self._current_lbl is not None:
                self._current_lbl.setText("")
                self._current_lbl.updateGeometry()
            return

        blocks = parse_blocks(buf)
        if not blocks:
            return

        # ── Live-update streaming code block ─────────────────────────────
        # The parser always emits a code block from an opening ``` even without
        # a closing ```, so we can't tell if it's complete from its mere presence.
        # When the LAST parsed block is a code block (regardless of how many
        # preceding blocks there are), we promote all preceding blocks first,
        # then live-update a QPlainTextEdit widget in place on every newline.
        # This works for both code-only messages and text-then-code messages.
        if blocks[-1]["type"] == "code":
            code_block = blocks[-1]

            # Promote any preceding blocks not yet rendered
            preceding = blocks[:-1]
            new_preceding = preceding[self._history._rendered_block_count:]
            if new_preceding:
                for blk in new_preceding:
                    self._history.push_rendered_block(blk)
                self._rendered_char_end = preceding[-1]["_char_end"]
                if self._current_lbl is not None:
                    self._current_lbl.setText(buf[self._rendered_char_end:])
                    self._current_lbl.updateGeometry()

            # Detect closing fence via parser flag (avoids false positives from
            # prior completed code blocks already in the buffer)
            fence_closed = code_block.get("_closed", False)

            cfg = {**EDITOR_DEFAULTS,
                   **(getattr(self._history, "_font_cfg", None) or {})}
            fs_code = cfg.get("fs_code", 10)

            if self._streaming_code_edit is None:
                # Opening ``` seen — create the widget
                w = build_code_block(code_block, self._history.insert_to_editor,
                                     fs_code)
                self._streaming_code_edit = w.findChild(_PTE)
                self._history.push_rendered_widget(w)

            # Update content and height in-place
            code = code_block["content"]
            self._streaming_code_edit.setPlainText(code)
            fm   = self._streaming_code_edit.fontMetrics()
            sb_h = self._streaming_code_edit.horizontalScrollBar().sizeHint().height()
            n_lines = max(code.count("\n") + 1, 1)
            self._streaming_code_edit.setFixedHeight(
                n_lines * fm.lineSpacing() + 24 + sb_h)
            self._streaming_code_edit.updateGeometry()

            # All buffer content is now in the widget — hide the tail label
            self._rendered_char_end = len(buf)
            if self._current_lbl is not None:
                self._current_lbl.setText("")
                self._current_lbl.updateGeometry()

            if fence_closed:
                # Closing ``` received — stop live-updating
                self._streaming_code_edit = None
            return

        # If we were live-updating a code block but now there are more blocks
        # (content appeared after the closing ```), stop tracking the live edit.
        if self._streaming_code_edit is not None:
            self._streaming_code_edit = None

        # ── Standard block promotion ──────────────────────────────────────
        # Think blocks are self-contained: parse_blocks only creates them when
        # </think> has been matched, so a lone think block is definitively complete.
        # All other single-block responses stay in the tail until a second block
        # confirms they are complete.
        if len(blocks) == 1 and blocks[0]["type"] != "think":
            return   # single non-self-closing block — tail may still be incomplete
        # All blocks except the last are complete (something follows them).
        # For a lone think block, treat the whole list as complete.
        complete = blocks[:-1] if len(blocks) >= 2 else blocks
        new_blocks = complete[self._history._rendered_block_count:]
        if not new_blocks:
            return
        for block in new_blocks:
            self._history.push_rendered_block(block)
        # Update char position of rendered content
        self._rendered_char_end = complete[-1]["_char_end"]
        # Trim the tail label to show only the unrendered suffix.
        # updateGeometry() tells the parent layout that the preferred size changed
        # so the label shrinks immediately when a large block (e.g. code) is promoted.
        tail = self._assistant_buf[self._rendered_char_end:]
        if self._current_lbl is not None:
            self._current_lbl.setText(tail)
            self._current_lbl.updateGeometry()

    @Slot()
    def _on_done(self):
        if self._worker_had_error:
            # _on_err already finalized — skip to avoid creating a second empty block
            self._worker_had_error = False
            return

        has_content = bool(self._assistant_buf)

        if has_content:
            self._messages.append(
                {"role": "assistant", "content": self._assistant_buf})
            # Replace streaming label with parsed markdown view
            self._history.finalize_assistant(self._assistant_buf)
        else:
            # Stopped before any tokens arrived — tear down the orphaned streaming
            # block so the UI stays in sync with self._messages (no empty block,
            # no non-functional Regenerate / Delete buttons).
            self._history.remove_streaming_block()

        self._page_bar.setEnabled(True)
        self._update_page_bar()
        self._send_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status.setText("完成。" if has_content else "已停止 — 未收到回复。")
        self._chat_thread = None
        self._chat_worker = None
        self._current_lbl          = None
        self._streaming_code_edit  = None
        self._streaming_think_edit = None

        if not has_content:
            # Nothing to compact, no action blocks, nothing to save.
            # Reset any pending compaction so it doesn't mis-fire on next response.
            self._pending_compaction_request = False
            self._update_ctx_size_label()
            # Refresh the Regenerate button so it lands on the last real
            # assistant block (the streaming placeholder was just removed).
            self._history._update_regenerate_button()
            return

        # LLM-driven compaction: if this response IS the compaction summary,
        # mark it and replace the assistant block with a compaction block.
        if self._pending_compaction_request:
            self._pending_compaction_request = False
            if self._messages and self._messages[-1].get("role") == "assistant":
                self._messages[-1]["compaction_summary"] = True
            self._history.promote_last_to_compaction()
            self._update_ctx_size_label()
            self._deferred_scroll_to_bottom()
            self._autosave()
            return   # skip action-block check for the compaction summary response

        # LLM-driven compaction trigger check (before action blocks, so compaction
        # fires cleanly before the next agentic round-trip).
        self._maybe_trigger_compaction()

        # Auto-confirm: only for fresh LLM responses, after thread is cleared
        # (so _send() inside _auto_send_results is not blocked by isRunning()).
        _reg = (self._history._action_env or {}).get("_exec_registry", {})
        if _reg:
            self._on_action_blocks_ready(dict(_reg))
        # Fire multiple deferred scrolls to catch all layout passes.
        # Rendered markdown is often shorter than raw streamed text, so the
        # scroll range shrinks and we must re-anchor to the new bottom.
        self._update_ctx_size_label()
        self._deferred_scroll_to_bottom()
        self._autosave()

    def _maybe_trigger_compaction(self):
        """
        Check whether LLM-driven compaction should fire after the current response.
        Only runs when: compaction_enabled, strategy=llm, autonomous_mode=full,
        project context is NOT active, and the history window is at/over threshold.
        """
        cfg_h = self._history_cfg()
        if not cfg_h.get("compaction_enabled", False):
            return
        if cfg_h.get("compaction_strategy", "cutoff") != "llm":
            return
        if self._agentic_cfg().get("autonomous_mode") != "full":
            return
        # Constraint B: skip when project context is active
        if self._proj_enabled:
            return
        # Don't compact if the last message is already a compaction summary
        if self._messages and self._messages[-1].get("compaction_summary"):
            return

        limit  = self._get_token_limit()
        thresh = limit * cfg_h.get("compaction_threshold_pct", 80) // 100

        # Measure only the window since the last compaction summary
        last_compact_idx = next(
            (i for i in range(len(self._messages) - 1, -1, -1)
             if self._messages[i].get("compaction_summary")),
            None)
        window = (self._messages[last_compact_idx + 1:]
                  if last_compact_idx is not None else self._messages)

        total_tokens = sum(self._estimate_msg_tokens(m) for m in window)
        if total_tokens < thresh:
            return   # still under threshold — nothing to do

        # Fire compaction: auto-send summary request to LLM
        compaction_prompt = (
            "Please write a concise but complete summary of our conversation so far. "
            "Include: the main goals discussed, key decisions made, important code or "
            "file changes, and any open questions or next steps. "
            "This summary will replace the earlier portion of the chat history to free "
            "up context space. Be thorough — this is the only record of that earlier work.")
        self._input.setPlainText(compaction_prompt)
        self._pending_compaction_request = True
        self._send()

    # ── Built-in command handlers ────────────────────────────────────────────

    def _get_active_builtins(self):
        """Return currently-visible built-in commands based on live config.
        Called each time the dropdown opens so visibility reflects current state."""
        from .commands import get_active_builtins
        return get_active_builtins(
            history_cfg=self._history_cfg(),
            proj_enabled=self._proj_enabled,
            agentic_cfg=self._agentic_cfg(),
        )

    def _on_builtin_action(self, action):
        """Dispatch a built-in command action triggered from the input dropdown."""
        if action == "compact":
            self._force_compact()
        elif action == "clear":
            self._clear_chat()

    def _force_compact(self):
        """Manually trigger LLM compaction — ignores the token threshold only.
        All four visibility conditions are re-validated as a safety guard so
        that nothing fires even if conditions changed since the dropdown opened,
        or if this method were somehow called outside the normal dropdown flow."""
        cfg_h = self._history_cfg()

        # — Re-validate all four visibility conditions —
        if not cfg_h.get("compaction_enabled", False):
            self._status.setText("⚠ 上下文历史压缩未启用。")
            return
        if cfg_h.get("compaction_strategy", "cutoff") != "llm":
            self._status.setText("⚠ /compact 需要 LLM 总结压缩策略。")
            return
        if self._agentic_cfg().get("autonomous_mode") != "full":
            self._status.setText("⚠ /compact 需要完全自主模式。")
            return
        if self._proj_enabled:
            self._status.setText("⚠ 项目上下文激活时 /compact 被禁用。")
            return

        # — Structural guards —
        if self._messages and self._messages[-1].get("compaction_summary"):
            self._status.setText("⚠ 此时已压缩过。")
            return
        if self._chat_thread and self._chat_thread.isRunning():
            self._status.setText("⚠ 回复进行中无法压缩。")
            return

        compaction_prompt = (
            "Please write a concise but complete summary of our conversation so far. "
            "Include: the main goals discussed, key decisions made, important code or "
            "file changes, and any open questions or next steps. "
            "This summary will replace the earlier portion of the chat history to free "
            "up context space. Be thorough — this is the only record of that earlier work.")
        self._input.setPlainText(compaction_prompt)
        self._pending_compaction_request = True
        self._send()

    @Slot(str)
    def _on_err(self, msg):
        self._worker_had_error = True
        if self._assistant_buf:
            # Partial response received before error — finalize what we have
            self._messages.append({"role": "assistant", "content": self._assistant_buf})
            self._history.finalize_assistant(self._assistant_buf)
        else:
            # No content received — show styled error block
            self._messages.append({"role": "assistant_error", "content": msg})
            self._history.show_error(msg)
        self._status.setText(f"⚠ {msg}")
        self._page_bar.setEnabled(True)
        self._update_page_bar()
        self._send_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._chat_thread = None
        self._chat_worker = None
        self._current_lbl = None
        self._update_ctx_size_label()
        self._deferred_scroll_to_bottom()
        self._autosave()

    def _deferred_scroll_to_bottom(self):
        """Schedule scroll-to-bottom attempts at 0 ms, 100 ms and 300 ms.
        Multiple passes are needed because Qt may take several layout rounds
        to settle (especially on history reload or when content shrinks after
        the streaming label is replaced with rendered markdown)."""
        for delay in (0, 100, 300):
            QTimer.singleShot(delay, self._scroll_to_bottom)

    def _on_scroll_range_changed(self, min_, max_):
        """Called whenever the vertical scroll range changes.
        Only auto-scrolls during active streaming; post-stream UI interactions
        (think block show/hide, window resize) must not cause jumps."""
        if self._auto_scroll and max_ > 0 and self._chat_worker is not None:
            self._scroll.verticalScrollBar().setValue(max_)

    def _scroll_to_bottom(self, _retry: int = 0):
        """Scroll to the true bottom of content.

        Uses the layout's sizeHint() as the authoritative content height so
        we can detect when sb.maximum() is stale (scroll area hasn't processed
        the latest layout change yet).  Retries with exponential back-off
        until the scroll position sticks or the maximum stabilises.
        """
        self._auto_scroll = True
        sb = self._scroll.verticalScrollBar()
        # sizeHint gives the intended content height; sb.maximum() may lag
        # behind (still 0, or an old inflated value) until the scroll area
        # processes the LayoutRequest posted by finalize_assistant.
        content_h  = self._history.layout().sizeHint().height()
        viewport_h = self._scroll.viewport().height()
        true_max   = max(0, content_h - viewport_h)
        actual_max = sb.maximum()
        # Use whichever is larger so we always reach the real visual bottom,
        # whether the layout has grown (true_max > actual_max) or shrunk
        # (actual_max > true_max — scroll area hasn't shrunk yet).
        target = max(true_max, actual_max)
        if target > 0:
            sb.setValue(target)
            # Retry only when sb.maximum() hasn't yet caught up to the layout
            # height, i.e. the scroll area still needs to settle.  We check
            # actual_max < true_max - 4 (layout grew but scrollbar didn't) or
            # sb.value() < actual_max - 4 (couldn't reach even the current max).
            needs_retry = (
                (actual_max < true_max - 4) or   # layout grew, max not updated
                (sb.value() < actual_max - 4)     # couldn't reach existing max
            )
            if _retry < 4 and needs_retry:
                delay = 150 * (2 ** _retry)
                QTimer.singleShot(delay,
                                  lambda r=_retry + 1: self._scroll_to_bottom(r))
        else:
            sb.setValue(sb.maximum())

    # ── system prompt selector ────────────────────────────────────────

    def _sp_populate_combo(self, select_id=None):
        """Reload combo from saved prompts. Preserves current selection."""
        if select_id is None:
            select_id = self._sp_selected_id
        self._sp_combo.blockSignals(True)
        self._sp_combo.clear()
        self._sp_combo.addItem("Use custom", userData=CUSTOM_ID)
        prompts = load_prompts()
        target_idx = 0
        for i, p in enumerate(prompts):
            self._sp_combo.addItem(p["title"], userData=p["id"])
            if p["id"] == select_id:
                target_idx = i + 1
        self._sp_combo.blockSignals(False)
        self._sp_combo.setCurrentIndex(target_idx)
        self._sp_on_select(target_idx)

    def _sp_on_select(self, idx):
        prompt_id = self._sp_combo.currentData()
        self._sp_selected_id = prompt_id
        if prompt_id == CUSTOM_ID:
            # Custom: enable the text field, hide copy button
            self._sys_prompt.setEnabled(True)
            self._sys_prompt.setPlaceholderText("System prompt (optional)")
            self._sp_copy_btn.setVisible(False)
        else:
            # Saved prompt selected: show content read-only, show copy button
            p = get_prompt(prompt_id)
            if p:
                self._sys_prompt.setPlainText(p["content"])
            self._sys_prompt.setEnabled(False)
            self._sp_copy_btn.setVisible(True)

    def _sp_on_copy(self):
        """Copy selected saved prompt into the field for editing, switch to custom."""
        p = get_prompt(self._sp_selected_id)
        if p:
            self._sys_prompt.setPlainText(p["content"])
        # Switch combo to "Use custom" without triggering _sp_on_select clear
        self._sp_combo.blockSignals(True)
        self._sp_combo.setCurrentIndex(0)
        self._sp_combo.blockSignals(False)
        self._sp_selected_id = CUSTOM_ID
        self._sys_prompt.setEnabled(True)
        self._sp_copy_btn.setVisible(False)
        self._sys_prompt.setFocus()

    def _sp_get_active_prompt(self):
        """Return the effective system prompt text for sending."""
        if self._sp_selected_id != CUSTOM_ID:
            p = get_prompt(self._sp_selected_id)
            if p:
                return p["content"]
        return self._sys_prompt.toPlainText().strip()

    def _on_delete_exchange(self, block_idx, delete_before):
        """
        Delete one exchange (user+assistant pair) or all exchanges before it.
        '🗑 This'      → delete this user+assistant pair.
        '⏫ All before' → delete all exchanges before (and including) this one.

        block_idx is page-relative (0-indexed within current page).
        Mapped to the global _messages index via: actual_idx = page_start + block_idx.
        """
        page_start = self._current_page * self._PAGE_SIZE
        actual_idx = page_start + block_idx
        if actual_idx < 0 or actual_idx >= len(self._messages):
            return

        # Step back to paired user message if an assistant block was clicked
        idx = actual_idx
        if idx % 2 == 1:
            idx -= 1

        if delete_before:
            del self._messages[: idx + 2]
            self._current_page = 0   # all before is gone → go to page 0
        else:
            del self._messages[idx : idx + 2]
            # Clamp in case current page no longer exists
            self._current_page = min(self._current_page, self._total_pages() - 1)

        self._reload_current_page()   # batched re-render with "Page N loading…" overlay
        self._autosave()
        self._update_ctx_size_label()
        self._status.setText("对话已删除。")

    def _on_regenerate(self):
        """Remove the last assistant reply and re-send the last user message."""
        if self._chat_thread is not None and self._chat_thread.isRunning():
            return
        if not self._messages:
            return

        last_role = self._messages[-1].get("role")

        if last_role in ("assistant", "assistant_error"):
            # Normal path: drop the last assistant reply and rebuild the UI without it.
            self._messages.pop()
            _need_ui_rebuild = True
        elif last_role == "user":
            # Stopped before the first token — no assistant reply was ever stored.
            # The last message is already the user message we want to re-send;
            # nothing to pop and the UI is already in the correct state.
            if len(self._messages) < 1:
                return
            _need_ui_rebuild = False
        else:
            return

        if _need_ui_rebuild:
            # Rebuild UI without the last assistant block.
            # Clamp current page in case the removed message was the only one on it.
            self._current_page = min(self._current_page, self._total_pages() - 1)
            self._history.clear_all()
            for msg in self._page_slice(self._current_page):
                self._render_one_msg(msg)
            self._update_page_bar()

        # Build LLM messages from current history (last entry is the user message)
        messages = []
        sys_p = self._sp_get_active_prompt()
        if sys_p:
            messages.append({"role": "system", "content": sys_p})

        # Inject agentic system prompt and set action_env — same as _send()
        agentic_cfg = self._agentic_cfg()
        if agentic_cfg.get("enabled"):
            self._history._action_env = self._build_action_env()
            from .agentic_actions import build_agentic_system_prompt
            agentic_sys = build_agentic_system_prompt(agentic_cfg)
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] += "\n\n" + agentic_sys
            else:
                messages.insert(0, {"role": "system", "content": agentic_sys})
        else:
            self._history._action_env = None

        for m in self._messages:
            if m.get("role") not in ("user", "assistant"):
                continue
            messages.append({"role": m["role"],
                             "content": _build_llm_content(m)})

        # Add streaming placeholder for the new response
        self._current_lbl = self._history.add_assistant_start()
        self._assistant_buf    = ""
        self._rendered_char_end = 0
        self._streaming_code_edit  = None
        self._streaming_think_edit = None
        self._auto_scroll = True

        worker = _ChatWorker(
            self._api_url(), self._api_key(),
            self._current_model, messages,
            extra_params=self._build_extra_params())
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.chunk_ready.connect(self._on_chunk)
        worker.finished.connect(self._on_done)
        worker.error.connect(self._on_err)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._chat_worker = worker
        self._chat_thread = thread

        self._page_bar.setEnabled(False)
        self._send_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status.setText(f"Regenerating with {self._current_model}…")
        thread.start()

    # ── inference parameters ──────────────────────────────────────────

    def _build_extra_params(self) -> dict:
        """
        Build the dict of inference params to send to the API.
        Filters to only params supported by the current provider,
        and renames max_tokens → max_completion_tokens for Groq.
        Returns empty dict if no params are set.
        """
        if not self._infer_params:
            return {}
        state = self._load_state()
        pid   = state.get("provider_type", "custom")
        pdef  = PROVIDERS.get(pid, PROVIDERS["custom"])
        supported = set(pdef["supported_params"])
        result = {k: v for k, v in self._infer_params.items() if k in supported}
        # Groq uses max_completion_tokens, not max_tokens
        if pid == "groq" and "max_tokens" in result:
            result["max_completion_tokens"] = result.pop("max_tokens")
        return result

    def _update_summary_bar(self):
        """Update the params summary label. Bar is always visible."""
        if not self._infer_params:
            self._params_bar_lbl.setText("点击设置推理参数")
            self._params_bar_lbl.setStyleSheet(_params_bar_idle_style())
            return
        # Build compact summary text
        parts = []
        label_map = {
            "temperature": "temp", "max_tokens": "max", "top_p": "top_p",
            "top_k": "top_k", "min_p": "min_p",
            "presence_penalty": "pres", "frequency_penalty": "freq",
            "repetition_penalty": "rep", "seed": "seed", "num_ctx": "ctx",
        }
        for k, v in self._infer_params.items():
            short = label_map.get(k, k)
            if isinstance(v, float):
                parts.append(f"{short}: {v:.2f}")
            else:
                parts.append(f"{short}: {v}")
        self._params_bar_lbl.setText("⚙ " + " · ".join(parts))
        self._params_bar_lbl.setStyleSheet(_params_bar_active_style())

    def _toggle_params_popup(self):
        """Open or close the inference params popup anchored above the ⚙ button."""
        if self._params_popup is None:
            main_win = _find_main_window()
            self._params_popup = _InferParamsPopup(main_win)

        if self._params_popup.isVisible():
            self._params_popup.hide()
        else:
            self._params_popup.show_above(self._params_bar_lbl, self)

    def _on_provider_changed(self, new_provider_id: str):
        """
        Called when the user switches provider in Settings.
        Resets per-chat inference params and updates chat_provider.
        """
        self._infer_params  = {}
        self._chat_provider = new_provider_id
        self._update_summary_bar()
        # Close popup if open so it rebuilds with new provider next time
        if self._params_popup and self._params_popup.isVisible():
            self._params_popup.hide()
        self._status.setText(
            f"Provider changed to {PROVIDERS.get(new_provider_id, {}).get('label', new_provider_id)}"
            f" — inference parameters reset.")

    def _autosave(self):
        """Save current chat to disk after each exchange (if enabled)."""
        if self._messages and self._history_cfg().get("autosave", True):
            self._current_chat_file = save_chat(
                self._messages,
                system_prompt=self._sp_get_active_prompt(), prompt_id=self._sp_selected_id,
                model=self._current_model,
                filename=self._current_chat_file,
                collection=self._current_collection,
                provider=self._chat_provider,
                infer_params=self._infer_params,
                project_context=self._proj_ctx_for_save(),
            )
            if self._current_chat_file:
                self._save_state(
                    last_chat_file=_encode_chat_ref(
                        self._current_collection, self._current_chat_file)
                )


# ---------------------------------------------------------------------------
# PluginMainWidget — proper Spyder 6 integration
# Spyder calls setup() to build content inside its managed central area.
# get_main_layout() returns the QVBoxLayout of the central content widget,
# which sits BELOW the toolbars and title bar — so toolbars stay intact.
# ---------------------------------------------------------------------------
from spyder.api.widgets.main_widget import PluginMainWidget

class AIChatWidget(PluginMainWidget):

    DEFAULT_OPTIONS = {}

    def get_title(self):
        return "AI Chat"

    def setup(self, options=None):
        self._panel = AIChatPanel(
            get_conf=lambda k, d="": d,
            set_conf=lambda k, v: None,
            get_editor_cursor=lambda: (None, "not set yet"),
            parent=self,
        )
        # set_content_widget() is the correct Spyder 6 API —
        # places our panel in the central area below the toolbars
        self.set_content_widget(self._panel)

    def set_editor_cursor_fn(self, fn):
        """Called by plugin.py after Spyder wires up the editor plugin."""
        if hasattr(self, '_panel'):
            self._panel._get_editor_cursor = fn

    def set_project_fns(self, get_project_root_fn, get_editor_widget_fn):
        """Called by plugin.py to wire up project/editor widget access."""
        if hasattr(self, '_panel'):
            self._panel.set_project_fns(get_project_root_fn, get_editor_widget_fn)

    def is_project_context_enabled(self):
        """Return True when the current chat has project context active."""
        return bool(getattr(getattr(self, '_panel', None), '_proj_enabled', False))

    def set_console_execute_fn(self, fn):
        """Called by plugin.py to provide IPython console execute function."""
        if hasattr(self, '_panel'):
            self._panel.set_console_execute_fn(fn)

    def set_load_file_fn(self, fn):
        """Called by plugin.py to provide editor load-file function."""
        if hasattr(self, '_panel'):
            self._panel.set_load_file_fn(fn)

    def set_reload_file_fn(self, fn):
        """Called by plugin.py to provide editor reload-file function (patch)."""
        if hasattr(self, '_panel'):
            self._panel.set_reload_file_fn(fn)

    def on_project_loaded(self, path):
        if hasattr(self, '_panel'):
            self._panel.on_project_loaded(path)

    def on_project_closed(self):
        if hasattr(self, '_panel'):
            self._panel.on_project_closed()

    def add_file_context(self, path):
        """Called by plugin.py when user picks 'Add to AI Chat context'."""
        if hasattr(self, '_panel'):
            self._panel.add_file_context(path)

    def add_file_context_content(self, name, content, source="file"):
        """Called by plugin.py with already-read content (supports unsaved files)."""
        if hasattr(self, '_panel'):
            self._panel.add_file_context_content(name, content, source)

    def next_selection_id(self, filename):
        """Return next selection counter for this filename."""
        if hasattr(self, '_panel'):
            return self._panel.next_selection_id(filename)
        return 1

    def update_actions(self):
        pass
