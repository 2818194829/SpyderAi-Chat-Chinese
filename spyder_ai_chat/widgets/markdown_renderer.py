# -*- coding: utf-8 -*-
"""
Markdown → Qt widgets renderer for AI Chat responses. (C) 2026 by Maciej Piecko

Supported elements:
  - Headings (#, ##, ###)
  - Bold (**text** or __text__)
  - Italic (*text* or _text_)
  - Bold+Italic (***text***)
  - Inline code (`code`)
  - Fenced code blocks (```lang ... ```)
  - Bullet lists (-, *, +)
  - Numbered lists (1. 2. etc.)
  - Blockquotes (> text)
  - Horizontal rules (--- or ***)
  - Tables (| col | col |)
  - Strikethrough (~~text~~)
  - Links ([text](url))
  - Plain paragraphs
"""

import re
from qtpy.QtCore import Qt, Signal, QPoint, QTimer, QThread, QEvent, QObject
from qtpy.QtGui import QFont, QColor
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QSizePolicy, QGridLayout, QScrollArea, QTextBrowser,
    QApplication,
)


# ---------------------------------------------------------------------------
# Theme helpers — all render functions call _is_dark_theme() / _tc() at
# widget-build time (QApplication is always available then) so styles adapt
# automatically when the user switches between Spyder's dark / light themes.
# ---------------------------------------------------------------------------
def _is_dark_theme():
    """Return True when Spyder (or the Qt app) is running in a dark theme."""
    try:                                    # prefer Spyder's own API
        from spyder.config.gui import is_dark_interface
        return is_dark_interface()
    except Exception:
        pass
    try:                                    # fall back to QPalette luminance
        from qtpy.QtWidgets import QApplication
        from qtpy.QtGui import QPalette
        bg = QApplication.instance().palette().color(QPalette.Window)
        lum = (bg.red() * 299 + bg.green() * 587 + bg.blue() * 114) // 1000
        return lum < 128
    except Exception:
        return True                         # safe default: dark colours


# Two complete palettes — pick at render time via _tc()
_DARK_PALETTE = {
    "code_bg":        "#1e1e1e",  "code_hdr":       "#2d2d2d",
    "code_border":    "#444444",  "code_fg":        "#d4d4d4",
    "inline_bg":      "#1e1e1e",  "inline_fg":      "#d4d4d4",
    "think_bg":       "#1a2a1a",  "think_border":   "#2a3d2a",
    "think_hdr":      "#243824",  "think_fg":       "#8abf8a",
    "think_title":    "#7ec87e",
    "out_bg":         "#111111",  "out_border":     "#333333",
    "out_fg":         "#d4d4d4",
    "diff_gut_bg":    "#161616",  "diff_gut_fg":    "#555555",
    "diff_hunk_bg":   "#111111",  "diff_hunk_bd":   "#2e2e2e",
    "diff_hunk_fg":   "#555555",  "diff_del_bg":    "#2d0000",
    "diff_add_bg":    "#002d00",  "diff_ctx_fg":    "#d4d4d4",
    "tbl_hdr_bg":     "#2d2d2d",  "tbl_hdr_fg":     "#4ec9b0",
    "tbl_border":     "#444444",  "tbl_row0":       "#1e1e1e",
    "tbl_row1":       "#252525",  "tbl_row_fg":     "#d4d4d4",
    # action block bg per type (dark)
    "abg_file_new":   "#09182a",  "abg_file_ow":    "#1e1500",
    "abg_run":        "#091e10",  "abg_install":    "#001e1e",
    "abg_git":        "#1e1000",  "abg_read":       "#0d1e2e",
    "abg_delete":     "#1e0000",  "abg_delete_dir": "#1a0000",
    "abg_rename":     "#1e1000",  "abg_patch":      "#0c1a06",
    # blockquote
    "quote_border":   "#4a90d9",  "quote_fg":       "#9cdcfe",
}
_LIGHT_PALETTE = {
    "code_bg":        "#f5f5f5",  "code_hdr":       "#e8e8e8",
    "code_border":    "#cccccc",  "code_fg":        "#333333",
    "inline_bg":      "#ebebeb",  "inline_fg":      "#333333",
    "think_bg":       "#f0f8f0",  "think_border":   "#aacfaa",
    "think_hdr":      "#d4ecd4",  "think_fg":       "#2d5a2d",
    "think_title":    "#3a703a",
    "out_bg":         "#f5f5f5",  "out_border":     "#cccccc",
    "out_fg":         "#333333",
    "diff_gut_bg":    "#f0f0f0",  "diff_gut_fg":    "#999999",
    "diff_hunk_bg":   "#f8f8f8",  "diff_hunk_bd":   "#dddddd",
    "diff_hunk_fg":   "#999999",  "diff_del_bg":    "#ffe0e0",
    "diff_add_bg":    "#dfffdf",  "diff_ctx_fg":    "#333333",
    "tbl_hdr_bg":     "#e8e8e8",  "tbl_hdr_fg":     "#2a8070",
    "tbl_border":     "#cccccc",  "tbl_row0":       "#ffffff",
    "tbl_row1":       "#f5f5f5",  "tbl_row_fg":     "#333333",
    # action block bg per type (light — very subtle tint of accent colour)
    "abg_file_new":   "#eef4ff",  "abg_file_ow":    "#fffbee",
    "abg_run":        "#f0fff5",  "abg_install":    "#eefafa",
    "abg_git":        "#fffaee",  "abg_read":       "#eef8ff",
    "abg_delete":     "#fff0f0",  "abg_delete_dir": "#fff0f0",
    "abg_rename":     "#fffaee",  "abg_patch":      "#f5fff0",
    # blockquote
    "quote_border":   "#3578c8",  "quote_fg":       "#1a5fa8",
}


def _tc():
    """Return the active theme colour palette dict."""
    return _DARK_PALETTE if _is_dark_theme() else _LIGHT_PALETTE


# ---------------------------------------------------------------------------
# Themed tooltip helpers — replaces OS system QToolTip (which follows the OS
# dark/light mode rather than Spyder's theme) with a custom themed popup.
# ---------------------------------------------------------------------------
class _MrTipPopup(QFrame):
    """Compact themed label popup used instead of the OS QToolTip.

    Auto-sizes to content width/height — suitable for short 1-2 line labels.
    """
    _instance = None   # module-level singleton

    def __init__(self):
        super().__init__(None,
                         Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._lbl = QLabel()
        self._lbl.setTextFormat(Qt.RichText)
        self._lbl.setWordWrap(True)
        vl = QVBoxLayout(self)
        vl.setContentsMargins(8, 6, 8, 6)
        vl.addWidget(self._lbl)

    def _apply_theme(self):
        if _is_dark_theme():
            self.setStyleSheet(
                "QFrame { background: #1e2a1e; border: 1px solid #4a6a4a; "
                "border-radius: 3px; }"
                "QLabel { color: #d0d8d0; font-size: 10px; border: none; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background: #f0f8f0; border: 1px solid #80a880; "
                "border-radius: 3px; }"
                "QLabel { color: #222222; font-size: 10px; border: none; }"
            )

    def show_near(self, widget, text):
        """Show popup to the right of the current cursor (standard tooltip placement)."""
        from qtpy.QtGui import QCursor
        self._apply_theme()
        import html as _html
        self._lbl.setText(_html.escape(text).replace('\n', '<br>'))
        self.adjustSize()

        pos = QCursor.pos()
        x = pos.x() + 14
        y = pos.y()

        try:
            screen = QApplication.screenAt(pos)
            sg = (screen.availableGeometry() if screen
                  else QApplication.primaryScreen().availableGeometry())
        except AttributeError:
            sg = QApplication.primaryScreen().availableGeometry()

        if x + self.width() > sg.right() - 4:
            x = pos.x() - self.width() - 4
        if y + self.height() > sg.bottom() - 4:
            y = sg.bottom() - self.height() - 4
        x = max(sg.left() + 4, x)
        y = max(sg.top() + 4, y)
        self.move(x, y)
        self.show()
        self.raise_()


class _MrTipFilter(QObject):
    """Event filter: replaces OS QToolTip with a themed _MrTipPopup."""

    def __init__(self, text, parent):
        super().__init__(parent)
        self._text = text

    @classmethod
    def _popup(cls):
        if _MrTipPopup._instance is None:
            _MrTipPopup._instance = _MrTipPopup()
        return _MrTipPopup._instance

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.ToolTip:
            return True           # suppress OS tooltip
        if t == QEvent.Enter:
            self._popup().show_near(obj, self._text)
        elif t == QEvent.Leave:
            p = _MrTipPopup._instance
            if p:
                p.hide()
        return False


def _mr_install_themed_tip(widget, text):
    """Replace OS system tooltip on *widget* with a compact themed popup."""
    widget.setToolTip("")
    f = _MrTipFilter(text, widget)
    widget.installEventFilter(f)


# ---------------------------------------------------------------------------
# Inline markdown → HTML  (used inside QLabel with RichText)
# ---------------------------------------------------------------------------
def _inline_to_html(text):
    """Convert inline markdown to HTML for use in a QLabel."""
    # Preserve <br> tags before escaping, then restore them after
    text = re.sub(r'<br\s*/?>', '\x00BR\x00', text, flags=re.IGNORECASE)
    # Escape HTML special chars first (except we'll add our own tags)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace('\x00BR\x00', '<br>')

    # Bold + Italic: ***text*** or ___text___
    text = re.sub(r'\*{3}(.+?)\*{3}', r'<b><i>\1</i></b>', text)
    text = re.sub(r'_{3}(.+?)_{3}',   r'<b><i>\1</i></b>', text)

    # Bold: **text** or __text__
    text = re.sub(r'\*{2}(.+?)\*{2}', r'<b>\1</b>', text)
    text = re.sub(r'_{2}(.+?)_{2}',   r'<b>\1</b>', text)

    # Italic: *text* or _text_  (not inside words)
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)',   r'<i>\1</i>', text)

    # Strikethrough: ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    # Inline code: ``code`` (double backtick) — must come before single
    _ibg = _tc()["inline_bg"]; _ifg = _tc()["inline_fg"]
    text = re.sub(r'``([^`]+?)``',
                  fr'<code style="background:{_ibg};color:{_ifg};'
                  r'padding:1px 4px;border-radius:3px;">\1</code>', text)
    # Inline code: `code` (single backtick)
    text = re.sub(r'`([^`]+)`',
                  fr'<code style="background:{_ibg};color:{_ifg};'
                  r'padding:1px 4px;border-radius:3px;">\1</code>', text)

    # Links: [text](url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                  r'<a href="\2" style="color:#4ec9b0;">\1</a>', text)

    return text


# ---------------------------------------------------------------------------
# Block-level parser — splits raw markdown into block tokens
# ---------------------------------------------------------------------------
def parse_blocks(text):
    """
    Parse markdown text into a list of block tokens.
    Each token is a dict with a 'type' key and type-specific fields.
    Each block also carries '_char_end': the absolute character offset in
    *text* immediately after this block (used for incremental streaming render).
    """
    # ── pre-pass: extract <think>...</think> blocks ───────────────────
    # Split text into think/non-think segments before line parsing.
    # Track each segment's start offset in the original text so we can
    # convert relative _char_end values to absolute positions.
    raw_blocks = []   # (seg_type, seg_text, seg_offset_in_text)
    think_pattern = re.compile(r'<think>(.*?)</think>', re.DOTALL | re.IGNORECASE)
    last = 0
    for m in think_pattern.finditer(text):
        if m.start() > last:
            raw_blocks.append(("text", text[last:m.start()], last))
        # Think block ends at m.end() (right after </think>)
        raw_blocks.append(("think", m.group(1).strip(), m.end()))
        last = m.end()
    if last < len(text):
        raw_blocks.append(("text", text[last:], last))

    blocks = []
    for seg_type, seg_text, seg_offset in raw_blocks:
        if seg_type == "think":
            # seg_offset is the absolute position of the end of </think>
            blocks.append({"type": "think", "content": seg_text,
                           "_char_end": seg_offset})
        else:
            seg_blocks = _parse_text_blocks(seg_text)
            for b in seg_blocks:
                b["_char_end"] = seg_offset + b.get("_char_end", len(seg_text))
            blocks.extend(seg_blocks)
    return blocks


def _parse_list_items(lines, base_indent):
    """
    Recursively parse a list of raw lines into a tree of list items.

    Each item is a dict:
        {
            "ordered": bool,
            "num":     int | None,   # None for bullet items
            "content": str,
            "children": [ ... ]      # nested items at deeper indent
        }

    Items at exactly `base_indent` spaces are siblings.
    Lines with greater indent become children of the preceding item.
    """
    items  = []
    i      = 0

    while i < len(lines):
        l = lines[i]
        if not l.strip():          # skip blank lines inside list
            i += 1
            continue

        indent = len(l) - len(l.lstrip())
        if indent < base_indent:   # de-dented past our level — stop
            break

        if indent > base_indent:   # deeper than expected — attach to last item
            if items:
                items[-1]["children"] += _parse_list_items(lines[i:], indent)
            i += 1
            continue

        # Match bullet or numbered marker at this indent level
        bm = re.match(r'^(\s*)([-*+•·‣⁃])\s+(.*)', l)
        nm = re.match(r'^(\s*)(\d+)\.\s+(.*)', l)

        if bm:
            content = bm.group(3).rstrip()
            items.append({"ordered": False, "num": None,
                          "content": content, "children": []})
            i += 1
        elif nm:
            content = nm.group(3).rstrip()
            items.append({"ordered": True, "num": int(nm.group(2)),
                          "content": content, "children": []})
            i += 1
        else:
            i += 1   # unrecognised line — skip

        # Collect immediately following deeper-indented lines as children
        child_lines = []
        while i < len(lines):
            nl = lines[i]
            if not nl.strip():
                # Blank line: peek ahead — if next non-blank is deeper, include
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    next_indent = len(lines[j]) - len(lines[j].lstrip())
                    if next_indent > base_indent:
                        i += 1
                        continue
                break
            next_indent = len(nl) - len(nl.lstrip())
            if next_indent > base_indent:
                child_lines.append(nl)
                i += 1
            else:
                break

        if child_lines and items:
            child_base = len(child_lines[0]) - len(child_lines[0].lstrip())
            items[-1]["children"] += _parse_list_items(child_lines, child_base)

    return items


def _parse_text_blocks(text):
    """Parse a plain text segment into markdown blocks (no think tags).
    Each block dict includes '_char_end': the character offset in *text*
    immediately after the block's last character (used for incremental rendering).
    """
    # Use keepends=True so we can compute exact character positions per line.
    lines_with_nl = text.splitlines(keepends=True)
    lines = [l.rstrip('\r\n') for l in lines_with_nl]

    # _line_starts[i] = char offset in text where line i begins.
    # _line_starts[len(lines)] = len(text).
    _line_starts = [0]
    for l in lines_with_nl:
        _line_starts.append(_line_starts[-1] + len(l))

    def _ce(line_idx):
        """Char offset right after line (line_idx-1), i.e. start of line_idx."""
        return _line_starts[min(line_idx, len(lines))]

    blocks = []
    i      = 0

    while i < len(lines):
        line = lines[i]

        # ── fenced code block (including action fences) ──────────────
        # Use (\S[^\n]*?|) instead of (\S*) so that action fence tags with
        # spaces — e.g. ```grep:SHOW TABLES or ```file:path/with spaces.py —
        # are recognized correctly.  The old \S* stopped at the first space,
        # causing the paragraph collector to immediately break on the same
        # line (^``` guard), leaving i unadvanced → infinite loop → Spyder hang.
        m = re.match(r'^\s*```(\S[^\n]*?|)\s*$', line)
        if m:
            lang  = m.group(1)
            code_lines = []
            i += 1
            while i < len(lines) and not re.match(r'\s*```', lines[i]):
                code_lines.append(lines[i])
                i += 1
            fence_found = i < len(lines)  # True = closing ``` found; False = buffer exhausted
            i += 1  # skip closing ``` (or step past end)
            _ACTION_PREFIXES = ("file:", "run:", "install:", "patch:", "read:", "ls:", "grep:",
                                "delete:", "delete_dir:", "rename:", "rename_dir:")
            block_type = "action" if any(lang.startswith(p) for p in _ACTION_PREFIXES) else "code"
            blocks.append({"type": block_type, "lang": lang,
                           "content": "\n".join(code_lines),
                           "_char_end": _ce(i),
                           "_closed": fence_found})
            continue

        # ── heading ──────────────────────────────────────────────────
        m = re.match(r'^(#{1,6})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            i += 1
            blocks.append({"type": "heading", "level": level,
                           "content": m.group(2).strip(),
                           "_char_end": _ce(i)})
            continue

        # ── horizontal rule ──────────────────────────────────────────
        if re.match(r'^(---+|\*\*\*+|___+)\s*$', line):
            i += 1
            blocks.append({"type": "hr", "_char_end": _ce(i)})
            continue

        # ── blockquote ───────────────────────────────────────────────
        if line.startswith("> ") or line == ">":
            quote_lines = []
            while i < len(lines) and (lines[i].startswith("> ") or
                                       lines[i] == ">"):
                quote_lines.append(lines[i][2:] if lines[i].startswith("> ")
                                   else lines[i][1:])
                i += 1
            blocks.append({"type": "blockquote",
                           "content": "\n".join(quote_lines),
                           "_char_end": _ce(i)})
            continue

        # ── table ────────────────────────────────────────────────────
        if "|" in line and i + 1 < len(lines) and re.match(
                r'^\s*\|?[\s\-:|]+\|', lines[i + 1]):
            rows = []
            while i < len(lines) and "|" in lines[i]:
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            ce = _ce(i)
            # rows[0] = header, rows[1] = separator, rows[2:] = data
            if len(rows) >= 2:
                header = rows[0]
                data   = rows[2:] if len(rows) > 2 else []
                blocks.append({"type": "table", "header": header,
                               "rows": data, "_char_end": ce})
                continue
            # Fallback: treat as paragraph
            for r in rows:
                blocks.append({"type": "paragraph",
                               "content": " | ".join(r),
                               "_char_end": ce})
            continue

        # ── list (bullet or numbered, arbitrary nesting) ─────────────
        if re.match(r'^(\s*)([-*+•·‣⁃]|\d+\.)\s+', line):
            # Collect all consecutive list lines (including blank lines
            # between items) into a raw block, then parse recursively.
            raw = []
            while i < len(lines):
                l = lines[i]
                if re.match(r'^\s*([-*+•·‣⁃]|\d+\.)\s+', l):
                    raw.append(l)
                    i += 1
                elif l.strip() == "":
                    # Keep blank only if next non-blank is still a list item
                    j = i + 1
                    while j < len(lines) and lines[j].strip() == "":
                        j += 1
                    if j < len(lines) and re.match(
                            r'^\s*([-*+•·‣⁃]|\d+\.)\s+', lines[j]):
                        i += 1   # skip blank, stay in list
                    else:
                        break    # end of list
                else:
                    break
            blocks.append({"type": "list",
                           "items": _parse_list_items(raw, 0),
                           "_char_end": _ce(i)})
            continue

        # ── blank line ───────────────────────────────────────────────
        if line.strip() == "":
            i += 1
            continue

        # ── paragraph (collect until blank line or block element) ────
        para_lines = []
        while i < len(lines):
            l = lines[i]
            if (l.strip() == "" or
                    re.match(r'^#{1,6}\s', l) or
                    re.match(r'^```', l) or
                    re.match(r'^(---+|\*\*\*+|___+)\s*$', l) or
                    re.match(r'^>\s?', l) or
                    re.match(r'^\s*[-*+•·‣⁃]\s+', l) or
                    re.match(r'^\d+\.\s+', l) or
                    ("|" in l and i + 1 < len(lines) and
                     re.match(r'^\s*\|?[\s\-:|]+\|', lines[i + 1]
                              if i + 1 < len(lines) else ""))):
                break
            para_lines.append(l)
            i += 1
        if para_lines:
            blocks.append({"type": "paragraph",
                           "content": " ".join(para_lines),
                           "_char_end": _ce(i)})
        elif i < len(lines) and re.match(r'^```', lines[i]):
            # Paragraph guard broke immediately on a ``` line that the fence
            # regex above also rejected (e.g. "``` lang" with a leading space).
            # Skip the line to prevent the outer loop from spinning on it.
            # This should only be reached with malformed LLM output.
            i += 1

    return blocks


# ---------------------------------------------------------------------------
# Qt widget builders for each block type
# ---------------------------------------------------------------------------

def _make_label(html, selectable=True, word_wrap=True, text_color="#d4d4d4",
                font_size=10):
    lbl = QLabel()
    lbl.setTextFormat(Qt.RichText)
    lbl.setWordWrap(word_wrap)
    lbl.setText(html)
    lbl.setOpenExternalLinks(True)
    lbl.setStyleSheet(
        f"background: transparent; padding: 1px 8px; "
        f"color: {text_color}; font-size: {font_size}pt;")
    if selectable:
        lbl.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard |
            Qt.LinksAccessibleByMouse)
    return lbl


def build_heading(block, base_size=14):
    level   = block["level"]
    content = _inline_to_html(block["content"])
    # Scale heading levels relative to base_size
    sizes   = {1: base_size, 2: base_size - 2, 3: base_size - 4,
               4: base_size - 5, 5: base_size - 6, 6: base_size - 7}
    size    = max(sizes.get(level, base_size - 4), 8)
    colors  = {1: "#4ec9b0", 2: "#4ec9b0", 3: "#9cdcfe"}
    color   = colors.get(level, "#d4d4d4")
    # Wrap in a block element so Qt rich-text gives the glyph room
    # Use emoji-capable font family so keycap sequences (1⃣ etc.) render cleanly
    emoji_fonts = "'Segoe UI Emoji', 'Apple Color Emoji', 'Noto Color Emoji', 'Noto Emoji', 'Twemoji Mozilla', sans-serif"
    html    = (f'<p style="margin-top:4px; margin-bottom:0; padding-left:4px;">'
               f'<span style="font-size:{size}pt; font-weight:bold; color:{color};'
               f'font-family:{emoji_fonts};">{content}</span></p>')
    w = _make_label(html, text_color=color, font_size=size)
    w.setStyleSheet(
        f"background: transparent; padding: 6px 8px 4px 10px; "
        f"color: {color}; font-size: {size}pt;")
    return w


def build_paragraph(block, text_color="#d4d4d4", font_size=10):
    html = _inline_to_html(block["content"])
    return _make_label(
        f'<span style="color:{text_color};">{html}</span>',
        text_color=text_color, font_size=font_size)


def build_hr():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setStyleSheet("color: #555; margin: 4px 8px;")
    return line


def build_think(block, font_size=9):
    """Collapsible thinking block with distinct background."""
    p = _tc()
    outer = QFrame()
    # Expanding horizontally so the frame fills the scroll-area width.
    # Labels inside inherit this width, which makes setWordWrap(True) work correctly.
    outer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    outer.setStyleSheet(
        f"QFrame {{ background: {p['think_bg']}; border: 1px solid {p['think_border']}; "
        "border-radius: 4px; margin: 2px 8px; }")
    lay = QVBoxLayout(outer)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    # Header row with toggle button
    header = QWidget()
    header.setStyleSheet(
        f"background: {p['think_hdr']}; border-bottom: 1px solid {p['think_border']}; "
        "border-radius: 4px 4px 0 0;")
    hl = QHBoxLayout(header)
    hl.setContentsMargins(8, 3, 8, 3)
    icon_lbl = QLabel("🧠")
    icon_lbl.setStyleSheet("background: transparent; border: none; font-size: 11px;")
    hl.addWidget(icon_lbl)
    title_lbl = QLabel("思考中…")
    title_lbl.setStyleSheet(
        f"color: {p['think_title']}; font-size: {font_size}pt; "
        "background: transparent; border: none;")
    hl.addWidget(title_lbl)
    hl.addStretch()
    toggle_btn = QPushButton("▾ 隐藏")
    toggle_btn.setFlat(True)
    toggle_btn.setStyleSheet(
        f"QPushButton {{ color: {p['think_title']}; font-size: {font_size}pt; border: none; "
        "background: transparent; padding: 0 4px; }"
        f"QPushButton:hover {{ color: {p['think_fg']}; }}")
    hl.addWidget(toggle_btn)
    lay.addWidget(header)

    # Content area — QPlainTextEdit with vertical scrollbar.
    # Fixed max-height avoids all the dynamic sizing complexity.
    from qtpy.QtWidgets import QPlainTextEdit

    content_w = QPlainTextEdit()
    content_w.setReadOnly(True)
    content_w.setFrameShape(QFrame.NoFrame)
    content_w.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    content_w.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    content_w.setLineWrapMode(QPlainTextEdit.WidgetWidth)
    content_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    content_w.setStyleSheet(
        f"QPlainTextEdit {{ background: transparent; border: none; "
        f"color: {p['think_fg']}; font-size: {font_size}pt; "
        f"padding: 6px 10px; }}")
    content_w.setPlainText(block["content"])
    content_w.setMaximumHeight(200)

    lay.addWidget(content_w)

    # Wire toggle — preserves the viewport position of the think block header
    def _toggle():
        # Walk up the widget tree to find the enclosing QScrollArea so we can
        # restore the on-screen position of this block after the layout reflows.
        scroll_area = None
        p = outer.parent()
        while p is not None:
            if isinstance(p, QScrollArea):
                scroll_area = p
                break
            p = p.parent()

        if scroll_area is not None:
            vsb      = scroll_area.verticalScrollBar()
            outer_y  = outer.mapTo(scroll_area.widget(), QPoint(0, 0)).y()
            screen_y = outer_y - vsb.value()   # current visual offset from viewport top

        visible = content_w.isVisible()
        content_w.setVisible(not visible)
        toggle_btn.setText("▸ 显示" if visible else "▾ 隐藏")

        if scroll_area is not None:
            # Restore after Qt reflows the layout (rangeChanged fires synchronously
            # during setVisible and may have already moved the scrollbar).
            def _restore():
                new_outer_y = outer.mapTo(scroll_area.widget(), QPoint(0, 0)).y()
                vsb.setValue(max(0, new_outer_y - screen_y))
            QTimer.singleShot(0, _restore)

    toggle_btn.clicked.connect(_toggle)
    return outer


def build_blockquote(block, text_color="#d4d4d4", font_size=10):
    """Render a blockquote (> ...) block.

    Handles nested fenced code blocks (```lang ... ```) inside the quote:
    they are rendered as real code widgets rather than raw italic text.
    Consecutive text lines are joined into paragraphs so inline formatting
    (bold, links, etc.) works across line breaks.
    """
    p = _tc()
    _QUOTE_BORDER = p["quote_border"]
    _QUOTE_COLOR  = p["quote_fg"]

    # Use QWidget (not QFrame) to avoid Qt's built-in frame border engine
    # which can add a second line even when only border-left is specified.
    # The coloured left accent is a narrow fixed-width child widget placed
    # in an HBoxLayout beside the content area.
    w = QWidget()
    w_lay = QHBoxLayout(w)
    w_lay.setContentsMargins(0, 2, 0, 2)
    w_lay.setSpacing(0)

    accent = QWidget()
    accent.setFixedWidth(3)
    accent.setStyleSheet(f"background: {_QUOTE_BORDER};")
    w_lay.addWidget(accent)

    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(12, 3, 4, 3)
    lay.setSpacing(3)

    def _flush_text(text_lines):
        """Render accumulated plain/inline-formatted lines as one label."""
        paragraph = "\n".join(text_lines).strip()
        if not paragraph:
            return
        lbl = _make_label(
            f'<span style="color:{_QUOTE_COLOR};">{_inline_to_html(paragraph)}</span>',
            text_color=_QUOTE_COLOR, font_size=font_size)
        lbl.setStyleSheet(
            f"background: transparent; padding: 0; "
            f"color: {_QUOTE_COLOR}; font-size: {font_size}pt;")
        lay.addWidget(lbl)

    lines = block["content"].splitlines()
    i = 0
    text_buf = []
    while i < len(lines):
        line = lines[i]
        # Detect start of a fenced code block (``` or ~~~)
        if len(line) >= 3 and (line.startswith("```") or line.startswith("~~~")):
            _flush_text(text_buf)
            text_buf = []
            fence = line[:3]
            lang  = line[3:].strip()
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].startswith(fence):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # consume closing fence
            code_block = {"type": "code", "lang": lang,
                          "content": "\n".join(code_lines)}
            lay.addWidget(build_code_block(code_block, font_size=font_size))
        else:
            text_buf.append(line)
            i += 1
    _flush_text(text_buf)
    w_lay.addWidget(inner, stretch=1)
    return w


def _build_list_widget(items, text_color, font_size, depth=0):
    """Recursively build a QWidget for a list tree at the given depth."""
    w   = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(depth * 16, 0, 0, 0)
    lay.setSpacing(1)

    for item in items:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # Marker: number or bullet symbol, cycling through styles by depth
        if item["ordered"]:
            marker_text = f"{item['num']}."
            marker_w    = 28
        else:
            symbols     = ["•", "◦", "▪", "▸"]
            marker_text = symbols[min(depth, len(symbols) - 1)]
            marker_w    = 14

        marker = QLabel(marker_text)
        marker.setStyleSheet(
            f"color: #4ec9b0; padding: 0 6px 0 0; background: transparent; "
            f"font-size: {font_size}pt;"
            + (" font-weight: bold;" if item["ordered"] and depth == 0 else ""))
        marker.setFixedWidth(marker_w)
        row.addWidget(marker, 0, Qt.AlignTop)

        # Item text
        lbl = _make_label(
            f'<span style="color:{text_color};">'
            f'{_inline_to_html(item["content"])}</span>',
            text_color=text_color, font_size=font_size)
        lbl.setStyleSheet(
            f"background: transparent; padding: 0; color: {text_color}; "
            f"font-size: {font_size}pt;")
        row.addWidget(lbl, 1)
        lay.addLayout(row)

        # Recurse into children
        if item.get("children"):
            lay.addWidget(
                _build_list_widget(item["children"], text_color,
                                   font_size, depth + 1))
    return w


def build_list(block, text_color="#d4d4d4", font_size=10):
    """Build a recursively nested list widget."""
    return _build_list_widget(block["items"], text_color, font_size, depth=0)


class _AutoHeightTextBrowser(QTextBrowser):
    """QTextBrowser that auto-adjusts its height to fit content on resize."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # QTextBrowser inherits QTextEdit's Expanding/Expanding size policy.
        # Changing the vertical half to Preferred prevents the layout from
        # stretching this widget to fill spare space when the chat is short
        # (no scrollbar visible) — the actual height is set by setFixedHeight()
        # once the correct viewport width is known.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_height()

    def showEvent(self, event):
        super().showEvent(event)
        self._adjust_height()

    def wheelEvent(self, event):
        # Pass wheel events to the parent so the chat window scrolls instead
        event.ignore()

    def _adjust_height(self):
        w = self.viewport().width()
        if w <= 0:
            # Widget not yet laid out — resizeEvent will call again once the
            # layout assigns a real width.  Skipping here avoids setTextWidth(0)
            # which would make the document collapse to a single-pixel column
            # and compute a spuriously huge height.
            return
        doc = self.document()
        doc.setTextWidth(w)
        h = int(doc.size().height())
        self.setFixedHeight(max(h + 4, 20))


def build_table(block, font_size=10):
    p = _tc()
    header_cells = "".join(
        f'<th style="background-color:{p["tbl_hdr_bg"]}; color:{p["tbl_hdr_fg"]}; font-weight:bold;'
        f' padding:4px 8px; border:1px solid {p["tbl_border"]};">'
        f'{_inline_to_html(cell)}</th>'
        for cell in block["header"]
    )
    body_rows = ""
    for row_i, row in enumerate(block["rows"]):
        bg = p["tbl_row0"] if row_i % 2 == 0 else p["tbl_row1"]
        cells = "".join(
            f'<td style="background-color:{bg}; color:{p["tbl_row_fg"]};'
            f' padding:3px 8px; border:1px solid {p["tbl_border"]};">'
            f'{_inline_to_html(row[col] if col < len(row) else "")}</td>'
            for col in range(len(block["header"]))
        )
        body_rows += f"<tr>{cells}</tr>"

    html = (
        f'<table style="border-collapse:collapse; width:100%;'
        f' font-size:{font_size}pt;">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{body_rows}</tbody>'
        f'</table>'
    )

    browser = _AutoHeightTextBrowser()
    browser.setHtml(html)
    browser.setOpenExternalLinks(True)
    browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    browser.setStyleSheet(
        "QTextBrowser { background-color: transparent; border: none;"
        " margin: 4px 8px; padding: 0; }"
    )
    return browser


def build_code_block(block, insert_signal=None, font_size=10):
    """Build a code block frame with header bar and copy button."""
    p    = _tc()
    lang = block["lang"]
    code = block["content"]

    frame = QFrame()
    frame.setFrameShape(QFrame.StyledPanel)
    frame.setStyleSheet(
        f"QFrame {{ background: {p['code_bg']}; border: 1px solid {p['code_border']}; "
        "border-radius: 4px; margin: 2px 8px; }")
    fl = QVBoxLayout(frame)
    fl.setContentsMargins(0, 0, 0, 0)
    fl.setSpacing(0)

    # Code text — created first so the header's copy button can capture it
    from qtpy.QtWidgets import QPlainTextEdit as _PTE
    code_lbl = _PTE()
    code_lbl.setReadOnly(True)
    code_lbl.setFrameShape(QFrame.NoFrame)
    code_lbl.setLineWrapMode(_PTE.NoWrap)
    code_lbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    code_lbl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    code_lbl.setFont(QFont("Monospace", font_size))
    code_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    code_lbl.setStyleSheet(
        f"QPlainTextEdit {{ color: {p['code_fg']}; background: transparent; "
        "padding: 8px 10px; border: none; }")
    code_lbl.setPlainText(code)
    # Height = text lines + vertical padding + horizontal scrollbar.
    # fontMetrics().lineSpacing() is the real per-line pixel height for this font/DPI.
    # 24 px = CSS padding (8 top + 8 bottom = 16 px) + QTextDocument document margin
    #         (4 px × 2 sides = 8 px).
    # horizontalScrollBar().sizeHint().height() reserves space for the scrollbar so
    # it never overlaps the last code line(s) when wide content triggers it.
    n_lines = code.count("\n") + 1
    sb_h = code_lbl.horizontalScrollBar().sizeHint().height()
    code_lbl.setFixedHeight(n_lines * code_lbl.fontMetrics().lineSpacing() + 24 + sb_h)

    # Header — built after code_lbl so the copy button lambda can capture it
    header = QWidget()
    header.setStyleSheet(
        f"background: {p['code_hdr']}; border-bottom: 1px solid {p['code_border']};")
    hl = QHBoxLayout(header)
    hl.setContentsMargins(8, 2, 4, 2)
    lang_lbl = QLabel(lang if lang else "代码")
    lang_lbl.setStyleSheet(
        "color: #888; font-size: 10px; background: transparent; border: none;")
    hl.addWidget(lang_lbl)
    hl.addStretch()
    if insert_signal is not None:
        copy_btn = QPushButton("📋 复制到编辑器")
        copy_btn.setFlat(True)
        copy_btn.setStyleSheet(
            "QPushButton { color: #4ec9b0; font-size: 10px; "
            "padding: 1px 6px; border: none; background: transparent; }"
            "QPushButton:hover { color: #fff; }")
        _mr_install_themed_tip(copy_btn, "在光标处插入此代码到当前编辑器")
        copy_btn.clicked.connect(
            lambda checked=False, pte=code_lbl: insert_signal.emit(pte.toPlainText()))
        hl.addWidget(copy_btn)
    fl.addWidget(header)
    fl.addWidget(code_lbl)
    return frame


# ---------------------------------------------------------------------------
# Done-badge widget with hover ↺ Re-run transition
# ---------------------------------------------------------------------------

class _DoneBadge(QPushButton):
    """
    Green '✓ 完成' badge that transitions to '↺ 重新运行' (action colour) on hover.
    Clicking always triggers re-run (same as original action button).
    """

    def __init__(self, rerun_color="#5a9a4a", parent=None):
        super().__init__("✓ 完成", parent)
        self._rerun_color = rerun_color
        self._done_style = (
            "QPushButton { color: #5a9a5a; font-size: 10px; "
            "border: 1px solid #5a9a5a; border-radius: 3px; padding: 2px 12px; "
            "background: transparent; }")
        self._rerun_style = (
            f"QPushButton {{ color: {rerun_color}; font-size: 10px; "
            f"border: 1px solid {rerun_color}; border-radius: 3px; padding: 2px 12px; "
            "background: transparent; }")
        self.setStyleSheet(self._done_style)

    def set_static_mode(self):
        """Disable hover transition — badge shows ✓ Done permanently (no re-run)."""
        self._static = True

    def enterEvent(self, event):
        super().enterEvent(event)
        if not getattr(self, "_static", False):
            self.setText("↺ 重新运行")
            self.setStyleSheet(self._rerun_style)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if not getattr(self, "_static", False):
            self.setText("✓ 完成")
            self.setStyleSheet(self._done_style)


# ---------------------------------------------------------------------------
# Action block widget (file:, run:, install:, patch: fences)
# ---------------------------------------------------------------------------

def _diff_to_html(content, font_size):
    """Convert unified diff text to HTML with line numbers and coloured lines.

    Renders a 3-column table: old-line-number | new-line-number | diff code.
    Line numbers are parsed from @@ hunk headers so they reflect true file
    positions rather than diff-relative offsets.
    """
    import html as _html
    import re   as _re

    lines = content.split("\n")

    # ── Pre-scan: find the highest line number so the gutter is wide enough ──
    _hunk_re = r"@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@"
    max_ln = 1
    for ln in lines:
        m = _re.match(_hunk_re, ln)
        if m:
            try:
                old_end = int(m.group(1)) + int(m.group(2) or 1)
                new_end = int(m.group(3)) + int(m.group(4) or 1)
                max_ln = max(max_ln, old_end, new_end)
            except (ValueError, TypeError):
                pass
    gutter_w = max(2, len(str(max_ln)))  # at least 2 chars wide

    # ── Cell styles ──────────────────────────────────────────────────────────
    _p   = _tc()
    _LN = (                              # line-number gutter (filled)
        f"color:{_p['diff_gut_fg']};"
        f"background:{_p['diff_gut_bg']};"
        "text-align:right;"
        "padding:0 5px;"
        "white-space:pre;"
        f"border-right:1px solid {_p['diff_hunk_bd']};"
    )
    _LN_EMPTY = (                        # line-number gutter (empty slot)
        f"color:{_p['diff_hunk_bg']};"
        f"background:{_p['diff_gut_bg']};"
        "text-align:right;"
        "padding:0 5px;"
        "white-space:pre;"
        f"border-right:1px solid {_p['diff_hunk_bd']};"
    )
    _CODE = "padding:0 8px;white-space:pre;"   # code content column

    def _gutter(num, empty=False):
        """Return a <td> for one gutter slot."""
        if empty:
            text = "&nbsp;" * gutter_w
        else:
            # rjust pads with spaces; replace them with &nbsp; so Qt's HTML
            # renderer doesn't collapse the leading whitespace even without
            # white-space:pre support on individual table cells.
            text = _html.escape(str(num).rjust(gutter_w)).replace(" ", "&nbsp;")
        st = _LN_EMPTY if empty else _LN
        return f'<td style="{st}">{text}</td>'

    parts = [
        f'<table cellspacing="0" cellpadding="0" '
        f'style="font-family:\'Courier New\',monospace;'
        f'font-size:{font_size}pt;'
        f'border-collapse:collapse;width:100%;">'
    ]

    old_ln = 1
    new_ln = 1

    for line in lines:
        # Skip file-header lines (filename already shown in the block header)
        if line.startswith("---") or line.startswith("+++"):
            continue

        if line.startswith("@@"):
            # Parse starting line numbers from the hunk header
            m = _re.match(_hunk_re, line)
            if m:
                try:
                    old_ln = int(m.group(1))
                    new_ln = int(m.group(3))
                except (ValueError, TypeError):
                    pass
            hdr_esc = _html.escape(line)
            parts.append(
                f'<tr>'
                f'<td colspan="3" '
                f'style="color:{_p["diff_hunk_fg"]};background:{_p["diff_hunk_bg"]};'
                f'border-top:1px solid {_p["diff_hunk_bd"]};'
                f'border-bottom:1px solid {_p["diff_hunk_bd"]};'
                f'padding:1px 8px;'
                f'white-space:pre;">{hdr_esc}</td>'
                f'</tr>'
            )
            continue

        if line.startswith("-"):
            code_esc = _html.escape(line[1:]) if len(line) > 1 else "&nbsp;"
            parts.append(
                f'<tr>'
                f'{_gutter(old_ln)}'
                f'{_gutter(0, empty=True)}'
                f'<td style="{_CODE}color:#f97583;background:{_p["diff_del_bg"]};">'
                f'-{code_esc}</td>'
                f'</tr>'
            )
            old_ln += 1

        elif line.startswith("+"):
            code_esc = _html.escape(line[1:]) if len(line) > 1 else "&nbsp;"
            parts.append(
                f'<tr>'
                f'{_gutter(0, empty=True)}'
                f'{_gutter(new_ln)}'
                f'<td style="{_CODE}color:#28a745;background:{_p["diff_add_bg"]};">'
                f'+{code_esc}</td>'
                f'</tr>'
            )
            new_ln += 1

        else:
            # Context line (starts with " ") or a bare empty line
            code_raw  = line[1:] if line.startswith(" ") else line
            code_esc  = _html.escape(code_raw) if code_raw else "&nbsp;"
            parts.append(
                f'<tr>'
                f'{_gutter(old_ln)}'
                f'{_gutter(new_ln)}'
                f'<td style="{_CODE}color:{_p["diff_ctx_fg"]};"> {code_esc}</td>'
                f'</tr>'
            )
            old_ln += 1
            new_ln += 1

    parts.append("</table>")
    return "".join(parts)


class _GitWorker(QThread):
    """Runs a git command off the UI thread."""
    done = Signal(str, str, int)   # stdout, stderr, returncode

    def __init__(self, args, cwd):
        super().__init__()
        self._args = args
        self._cwd  = cwd

    def run(self):
        from .agentic_actions import run_git_command
        stdout, stderr, rc = run_git_command(self._args, cwd=self._cwd)
        self.done.emit(stdout or "", stderr or "", rc)


def _proj_security_check(path, env, bd, status_lbl, op_name):
    """Verify *path* lies within the currently-open Spyder project root.

    Returns an error string (and updates *status_lbl*) if the operation should
    be blocked, or ``None`` if the path is safe to proceed with.

    This is a defense-in-depth check: the LLM already receives the project root
    in its system message, so it is expected to generate in-project paths.  This
    guard prevents accidental or adversarial out-of-bounds paths from reaching the
    filesystem even after the user has confirmed the action dialog.
    """
    import os as _os

    proj_root_fn = env.get("proj_root_fn")
    proj_root = proj_root_fn() if proj_root_fn else None

    if proj_root is None:
        msg = (f"⚠ Cannot execute action. Security: no Spyder project is currently open. "
               f"The '{op_name}' operation was cancelled.")
        status_lbl.setText(msg)
        return msg

    # Resolve relative paths the same way the execute_* helpers would.
    if bd and not _os.path.isabs(path):
        path = _os.path.join(bd, path)
    abs_path  = _os.path.normpath(_os.path.abspath(path))
    norm_root = _os.path.normpath(_os.path.abspath(proj_root))

    if abs_path != norm_root and not abs_path.startswith(norm_root + _os.sep):
        msg = (f"⚠ Cannot execute action. Security: '{abs_path}' is outside the current project "
               f"({norm_root}). The '{op_name}' operation was cancelled.")
        status_lbl.setText(msg)
        return msg

    return None   # check passed


def build_action_block(block, action_env=None, font_size=10):
    """
    Build a widget for an agentic action fence.

    block:      dict with 'lang' (e.g. "file:path/foo.py") and 'content'
    action_env: dict with keys:
        create_file_fn(path, content, base_dir) -> str (written path) or raises
        patch_file_fn(path, diff, base_dir) -> str or raises
        run_console_fn(code) -> None
        install_fn(spec) -> None
        load_file_fn(path) -> None  (opens file in editor after creation)
        base_dir: str or None
        confirm_each: bool
        allow_create_file / allow_run_console / allow_install / allow_patch: bool
    If action_env is None (agentic mode off) the block renders as a plain code block.
    """
    import os as _os

    lang    = block.get("lang", "")
    content = block.get("content", "")

    # ── Allow-flag check — render as plain code if action type is disabled ──
    _ALLOW_KEYS = {
        "file":       "allow_create_file",
        "run":        "allow_run_console",
        "install":    "allow_install",
        "patch":      "allow_patch",
        "git":        "allow_git",
        "read":       "allow_read",
        "ls":         "allow_ls",
        "grep":       "allow_grep",
        "delete":     "allow_delete",
        "delete_dir": "allow_delete_dir",
        "rename":     "allow_rename",
        "rename_dir": "allow_rename_dir",
    }

    # Helper: parse "path/to/file.py:100-150" → (path, from, to) or (path, None, None)
    import re as _re_mod
    _RANGE_RE = _re_mod.compile(r"^(\d+)-(\d+)$")

    def _parse_read_target(raw):
        parts = raw.rsplit(":", 1)
        if len(parts) == 2 and _RANGE_RE.match(parts[1]):
            m = _RANGE_RE.match(parts[1])
            return parts[0], int(m.group(1)), int(m.group(2))
        return raw, None, None

    # Determine action type and target
    if lang.startswith("file:"):
        action_type = "file"
        target = lang[5:]
    elif lang == "run:git" or lang.startswith("run:git "):
        action_type = "git"
        target = ""
    elif lang.startswith("run:"):
        action_type = "run"
        target = lang[4:]
    elif lang.startswith("install:"):
        action_type = "install"
        target = lang[8:]
    elif lang.startswith("patch:"):
        action_type = "patch"
        target = lang[6:]
    elif lang.startswith("read:"):
        action_type = "read"
        target = lang[5:]   # "path/to/file.py" or "path/to/file.py:100-150"
    elif lang.startswith("ls:"):
        action_type = "ls"
        target = lang[3:]   # "some/dir/"
    elif lang.startswith("grep:"):
        action_type = "grep"
        target = lang[5:]   # "pattern" or "pattern:scope/"
    elif lang.startswith("delete_dir:"):
        action_type = "delete_dir"
        target = lang[11:]  # "path/to/dir"
    elif lang.startswith("delete:"):
        action_type = "delete"
        target = lang[7:]   # "path/to/file"
    elif lang.startswith("rename_dir:"):
        action_type = "rename_dir"
        target = lang[11:]  # "path/to/old_dir"
    elif lang.startswith("rename:"):
        action_type = "rename"
        target = lang[7:]   # "path/to/old_file"
    else:
        return build_code_block(block, font_size=font_size)

    env = action_env or {}
    block_idx = env.get("_block_idx", -1)

    # If agentic env not provided or action type disabled → plain code block
    allow_key = _ALLOW_KEYS.get(action_type)
    if not env or not env.get(allow_key, True):
        return build_code_block(block, font_size=font_size)

    # Pre-executed check (for blocks restored from chat history)
    already_executed = block_idx in env.get("_executed_blocks", set())

    # ── Resolve absolute path for file existence check ────────────────────
    base_dir = env.get("base_dir")
    abs_target = None
    if action_type in ("file", "patch", "delete", "delete_dir", "rename", "rename_dir") and target:
        if _os.path.isabs(target):
            abs_target = _os.path.normpath(target)
        elif base_dir:
            abs_target = _os.path.normpath(_os.path.join(base_dir, target))

    # ── Per-action-type styling ───────────────────────────────────────────
    _abg = _tc()   # action bg palette (picked once per block render)
    if action_type == "file":
        file_exists = abs_target and _os.path.exists(abs_target)
        if file_exists:
            header_icon  = "📄"
            header_label = f"📄 Overwrite File  →  {target}"
            header_color = "#c8a000"   # amber
            bg_color     = _abg["abg_file_ow"]
            btn_text     = "⚠ Overwrite file"
        else:
            header_icon  = "📄"
            header_label = f"📄 Create File  →  {target}"
            header_color = "#3a80cc"   # blue
            bg_color     = _abg["abg_file_new"]
            btn_text     = "✓ Create file"
    elif action_type == "run":
        header_label = f"▶ Run in console  ({target})"
        header_color = "#3a9a5a"       # green
        bg_color     = _abg["abg_run"]
        btn_text     = "▶ Run in console"
    elif action_type == "install":
        header_label = f"⬇ Install package  ({target})"
        header_color = "#2a8a8a"       # teal
        bg_color     = _abg["abg_install"]
        btn_text     = "⬇ Install"
    elif action_type == "git":
        cmd_preview = content.strip().split("\n")[0][:60]
        header_label = f"⎇  $ git {cmd_preview}"
        header_color = "#e8a050"       # orange
        bg_color     = _abg["abg_git"]
        btn_text     = "⎇ Run git command"
    elif action_type == "read":
        _fp, _lf, _lt = _parse_read_target(target)
        _range_sfx   = f"  :{_lf}-{_lt}" if _lf is not None else ""
        header_label = f"📄 Read  →  {_fp}{_range_sfx}"
        header_color = "#80c8f0"       # light blue
        bg_color     = _abg["abg_read"]
        btn_text     = "📄 Read file"
    elif action_type == "ls":
        header_label = f"📁 List  →  {target}"
        header_color = "#80c8f0"
        bg_color     = _abg["abg_read"]
        btn_text     = "📁 List directory"
    elif action_type == "grep":
        _gparts  = target.split(":", 1)
        _gpat    = _gparts[0]
        _gscope  = f"  in  {_gparts[1]}" if len(_gparts) > 1 else ""
        header_label = f"🔍 Search  →  {_gpat}{_gscope}"
        header_color = "#80c8f0"
        bg_color     = _abg["abg_read"]
        btn_text     = "🔍 Search files"
    elif action_type == "delete":
        target_exists = abs_target and _os.path.isfile(abs_target)
        header_label = f"🗑 Delete File  →  {target}"
        header_color = "#e05050"       # red
        bg_color     = _abg["abg_delete"]
        btn_text     = "🗑 Delete file" if target_exists else "🗑 Delete file (not found)"
    elif action_type == "delete_dir":
        target_exists = abs_target and _os.path.isdir(abs_target)
        header_label = f"🗑 Delete Directory  →  {target}"
        header_color = "#c03030"       # dark red
        bg_color     = _abg["abg_delete_dir"]
        btn_text     = "🗑 Delete directory" if target_exists else "🗑 Delete dir (not found)"
    elif action_type == "rename":
        new_path = content.strip().split("\n")[0]
        header_label = f"↪ Rename File  →  {target}  →  {new_path}"
        header_color = "#e8a050"       # orange
        bg_color     = _abg["abg_rename"]
        btn_text     = "↪ Rename file"
    elif action_type == "rename_dir":
        new_path = content.strip().split("\n")[0]
        header_label = f"↪ Rename Directory  →  {target}  →  {new_path}"
        header_color = "#e8a050"       # orange
        bg_color     = _abg["abg_rename"]
        btn_text     = "↪ Rename directory"
    else:  # patch
        header_label = f"✎ Apply patch  →  {target}"
        header_color = "#80c040"       # lime green
        bg_color     = _abg["abg_patch"]
        btn_text     = "✎ Apply patch"

    frame = QFrame()
    frame.setFrameShape(QFrame.StyledPanel)
    frame.setStyleSheet(
        f"QFrame {{ background: {bg_color}; border: 1px solid {header_color}; "
        f"border-radius: 4px; margin: 2px 8px; }}")
    fl = QVBoxLayout(frame)
    fl.setContentsMargins(0, 0, 0, 0)
    fl.setSpacing(0)

    # ── Header ───────────────────────────────────────────────────────────
    header = QWidget()
    header.setStyleSheet(
        f"background: {header_color}22; border-bottom: 1px solid {header_color};")
    hl = QHBoxLayout(header)
    hl.setContentsMargins(8, 3, 8, 3)
    header_lbl = QLabel(header_label)
    header_lbl.setStyleSheet(
        f"color: {header_color}; font-size: 10px; font-weight: bold; "
        "background: transparent; border: none;")
    hl.addWidget(header_lbl, 1)

    # For read/ls/grep the done indicator lives in the header (right side) as a
    # plain label — no button border, matches the batch-summary style.
    # For all other action types it is a _DoneBadge in the button row below.
    _header_done_badge = None
    if action_type in ("read", "ls", "grep"):
        _header_done_badge = QLabel("✓ Done")
        _header_done_badge.setStyleSheet(
            f"color: {header_color}; font-size: 9px; padding: 1px 6px; "
            "background: transparent; border: none;")
        hl.addWidget(_header_done_badge)
        _header_done_badge.setVisible(already_executed)

    fl.addWidget(header)

    # ── Code content (hidden for git/read/ls/grep/delete/delete_dir/rename/rename_dir — spec is in the header) ─
    if action_type not in ("git", "read", "ls", "grep", "delete", "delete_dir", "rename", "rename_dir"):
        if action_type == "patch":
            from qtpy.QtWidgets import QTextEdit as _QTE
            from qtpy.QtGui import QTextOption as _QTO
            code_lbl = _QTE()
            code_lbl.setReadOnly(True)
            code_lbl.setFrameShape(QFrame.NoFrame)
            code_lbl.setWordWrapMode(_QTO.NoWrap)
            code_lbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            code_lbl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            code_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            code_lbl.setStyleSheet(
                "QTextEdit { background: transparent; border: none; padding: 0; }")
            code_lbl.setHtml(_diff_to_html(content, font_size))
        else:
            from qtpy.QtWidgets import QPlainTextEdit as _PTE
            code_lbl = _PTE()
            code_lbl.setReadOnly(True)
            code_lbl.setFrameShape(QFrame.NoFrame)
            code_lbl.setLineWrapMode(_PTE.NoWrap)
            code_lbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            code_lbl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            code_lbl.setFont(QFont("Monospace", font_size))
            code_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            code_lbl.setStyleSheet(
                f"QPlainTextEdit {{ color: {_abg['code_fg']}; background: transparent; "
                "padding: 6px 10px; border: none; }")
            code_lbl.setPlainText(content)
        if action_type == "patch":
            visible_lines = [l for l in content.split("\n")
                             if not (l.startswith("---") or l.startswith("+++"))]
            n_lines = max(len(visible_lines), 1)
        else:
            n_lines = max(content.count("\n") + 1, 1)
        sb_h = code_lbl.horizontalScrollBar().sizeHint().height()
        code_lbl.setFixedHeight(n_lines * code_lbl.fontMetrics().lineSpacing() + 20 + sb_h)
        fl.addWidget(code_lbl)

    # ── Action button row ─────────────────────────────────────────────────
    btn_row = QWidget()
    btn_row.setStyleSheet("background: transparent;")
    brl = QHBoxLayout(btn_row)
    brl.setContentsMargins(8, 4, 8, 6)
    brl.setSpacing(6)
    brl.addStretch()

    exec_btn = QPushButton(btn_text)
    exec_btn.setStyleSheet(
        f"QPushButton {{ color: {header_color}; font-size: 10px; "
        f"border: 1px solid {header_color}; border-radius: 3px; padding: 2px 12px; "
        "background: transparent; }"
        f"QPushButton:hover {{ color: #fff; border-color: #fff; "
        f"background: {header_color}44; }}")
    brl.addWidget(exec_btn)
    exec_btn.setVisible(not already_executed)   # after addWidget — avoids parentless flash

    # Done badge: for read/ls/grep it was placed in the header above; for all
    # other action types it lives here in the button row.
    if _header_done_badge is not None:
        done_badge = _header_done_badge   # alias — closures below reference done_badge
    else:
        done_badge = _DoneBadge(rerun_color=header_color)
        # Git commands must not be re-run — side effects (commit, push, etc.)
        # are irreversible; show a static ✓ Done with no hover transition.
        if action_type == "git":
            done_badge.set_static_mode()
        brl.addWidget(done_badge)
        done_badge.setVisible(already_executed)  # after addWidget — avoids parentless flash

    # ── Status label ─────────────────────────────────────────────────────
    status_lbl = QLabel("")
    status_lbl.setStyleSheet(
        "color: #888; font-size: 9px; background: transparent; border: none;")
    status_lbl.setWordWrap(True)
    brl.addWidget(status_lbl, 1)

    fl.addWidget(btn_row)
    # For read/ls/grep the done badge is in the header; hide the button row
    # when already executed so no empty space appears below the header.
    if _header_done_badge is not None and already_executed:
        btn_row.setVisible(False)

    # ── Git output panel (hidden until command runs) ──────────────────────
    git_output_panel = None
    insp_output_panel = None   # for read/ls/grep manual-send mode
    insp_out_edit     = None
    if action_type == "git":
        git_output_panel = QWidget()
        git_output_panel.setStyleSheet("background: transparent;")
        git_output_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        git_out_lay = QVBoxLayout(git_output_panel)
        git_out_lay.setContentsMargins(8, 0, 8, 6)
        git_out_lay.setSpacing(4)

        from qtpy.QtWidgets import QPlainTextEdit as _PTE2
        git_out_edit = _PTE2()
        git_out_edit.setReadOnly(True)
        git_out_edit.setFrameShape(QFrame.NoFrame)
        git_out_edit.setLineWrapMode(_PTE2.WidgetWidth)   # no horizontal scrollbar eating height
        git_out_edit.setFont(QFont("Monospace", font_size - 1))
        git_out_edit.setStyleSheet(
            f"QPlainTextEdit {{ color: {_abg['out_fg']}; background: {_abg['out_bg']}; "
            f"border: 1px solid {_abg['out_border']}; border-radius: 3px; padding: 4px; }}")
        git_out_lay.addWidget(git_out_edit)

        git_btn_row = QHBoxLayout()
        git_btn_row.setSpacing(6)
        git_btn_row.addStretch()

        git_attach_btn = QPushButton("📤 发送给 LLM")
        git_attach_btn.setStyleSheet(
            f"QPushButton {{ color: {header_color}; font-size: 10px; "
            f"border: 1px solid {header_color}; border-radius: 3px; padding: 2px 10px; "
            "background: transparent; }"
            f"QPushButton:hover {{ color: #fff; border-color: #fff; "
            f"background: {header_color}44; }}")

        git_dismiss_btn = QPushButton("✕ 忽略")
        git_dismiss_btn.setStyleSheet(
            "QPushButton { color: #888; font-size: 10px; "
            "border: 1px solid #555; border-radius: 3px; padding: 2px 10px; "
            "background: transparent; }"
            "QPushButton:hover { color: #fff; border-color: #aaa; }")

        git_btn_row.addWidget(git_attach_btn)
        git_btn_row.addWidget(git_dismiss_btn)
        git_out_lay.addLayout(git_btn_row)

        git_output_panel.setVisible(False)
        fl.addWidget(git_output_panel)

        def _on_git_dismiss():
            git_output_panel.setVisible(False)
            exec_btn.setVisible(False)
            done_badge.setVisible(True)   # command ran — show done, re-run on click

        def _on_git_attach():
            out_text  = git_out_edit.toPlainText()
            cmd_text  = content.strip().split("\n")[0][:60]
            auto_fn   = env.get("auto_send_fn")
            if auto_fn:
                auto_fn(f"git {cmd_text}", out_text, "git")
            git_output_panel.setVisible(False)
            exec_btn.setVisible(False)
            done_badge.setVisible(True)

        git_dismiss_btn.clicked.connect(_on_git_dismiss)
        git_attach_btn.clicked.connect(_on_git_attach)

    # ── Inspection output panel (read/ls/grep — manual-send mode) ─────────
    elif action_type in ("read", "ls", "grep"):
        insp_output_panel = QWidget()
        insp_output_panel.setStyleSheet("background: transparent;")
        insp_output_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        insp_out_lay = QVBoxLayout(insp_output_panel)
        insp_out_lay.setContentsMargins(8, 0, 8, 6)
        insp_out_lay.setSpacing(4)

        from qtpy.QtWidgets import QPlainTextEdit as _PTE3
        insp_out_edit = _PTE3()
        insp_out_edit.setReadOnly(True)
        insp_out_edit.setFrameShape(QFrame.NoFrame)
        insp_out_edit.setLineWrapMode(_PTE3.NoWrap)
        insp_out_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        insp_out_edit.setFont(QFont("Monospace", font_size - 1))
        insp_out_edit.setStyleSheet(
            f"QPlainTextEdit {{ color: {_abg['out_fg']}; background: {_abg['out_bg']}; "
            f"border: 1px solid {_abg['out_border']}; border-radius: 3px; padding: 4px; }}")
        insp_out_edit.setMaximumHeight(180)
        insp_out_lay.addWidget(insp_out_edit)

        insp_btn_row = QHBoxLayout()
        insp_btn_row.setSpacing(6)
        insp_btn_row.addStretch()

        insp_attach_btn = QPushButton("📤 发送给 LLM")
        insp_attach_btn.setStyleSheet(
            f"QPushButton {{ color: {header_color}; font-size: 10px; "
            f"border: 1px solid {header_color}; border-radius: 3px; padding: 2px 10px; "
            "background: transparent; }"
            f"QPushButton:hover {{ color: #fff; border-color: #fff; "
            f"background: {header_color}44; }}")

        insp_dismiss_btn = QPushButton("✕ 忽略")
        insp_dismiss_btn.setStyleSheet(
            "QPushButton { color: #888; font-size: 10px; "
            "border: 1px solid #555; border-radius: 3px; padding: 2px 10px; "
            "background: transparent; }"
            "QPushButton:hover { color: #fff; border-color: #aaa; }")

        insp_btn_row.addWidget(insp_attach_btn)
        insp_btn_row.addWidget(insp_dismiss_btn)
        insp_out_lay.addLayout(insp_btn_row)

        insp_output_panel.setVisible(False)
        fl.addWidget(insp_output_panel)

        def _on_insp_dismiss():
            insp_output_panel.setVisible(False)
            done_badge.setVisible(True)   # exec_btn already hidden by _run_action

        def _on_insp_attach():
            out_text = insp_out_edit.toPlainText()
            auto_fn = env.get("auto_send_fn")
            if auto_fn:
                auto_fn(target, out_text, action_type)
            insp_output_panel.setVisible(False)
            done_badge.setVisible(True)   # exec_btn already hidden by _run_action

        insp_dismiss_btn.clicked.connect(_on_insp_dismiss)
        insp_attach_btn.clicked.connect(_on_insp_attach)

    # ── Execute logic ─────────────────────────────────────────────────────
    def _run_action(final_target, live_base_dir=None, on_git_done_extra=None):
        """Execute the action — called after confirmation."""
        bd = live_base_dir or base_dir
        try:
            if action_type == "file":
                fn = env.get("create_file_fn")
                written = fn(final_target, content, bd) if fn else None
                if written is None:
                    from .agentic_actions import execute_create_file
                    written = execute_create_file(final_target, content, bd)
                result_text = f"✓ Written: {written}"
                status_lbl.setText(f"✓ 已写入：{written}")
                # Switch block appearance to "Overwrite" state immediately
                _ow = "#c8a000"   # amber
                _ow_bg = _tc()["abg_file_ow"]
                frame.setStyleSheet(
                    f"QFrame {{ background: {_ow_bg}; border: 1px solid {_ow}; "
                    f"border-radius: 4px; margin: 2px 8px; }}")
                header.setStyleSheet(
                    f"background: {_ow}22; border-bottom: 1px solid {_ow};")
                header_lbl.setText(f"📄 Overwrite File  →  {target}")
                header_lbl.setStyleSheet(
                    f"color: {_ow}; font-size: 10px; font-weight: bold; "
                    "background: transparent; border: none;")
                exec_btn.setText("⚠ 覆盖文件")
                exec_btn.setStyleSheet(
                    f"QPushButton {{ color: {_ow}; font-size: 10px; "
                    f"border: 1px solid {_ow}; border-radius: 3px; padding: 2px 12px; "
                    "background: transparent; }"
                    f"QPushButton:hover {{ color: #fff; border-color: #fff; "
                    f"background: {_ow}44; }}")
                done_badge._rerun_color = _ow
                done_badge._rerun_style = (
                    f"QPushButton {{ color: {_ow}; font-size: 10px; "
                    f"border: 1px solid {_ow}; border-radius: 3px; padding: 2px 12px; "
                    f"background: transparent; }}")
                # Open in editor if available
                load_fn = env.get("load_file_fn")
                if load_fn:
                    try:
                        load_fn(written)
                    except Exception:
                        pass
            elif action_type == "run":
                fn = env.get("run_console_fn")
                if not fn:
                    status_lbl.setText("⚠ 没有可用的控制台")
                    return None
                result_text = fn(content)   # None = async capture; str = fallback message
                status_lbl.setText("✓ 已发送到控制台")
            elif action_type == "install":
                spec = content.strip() or final_target
                fn = env.get("install_fn")
                if not fn:
                    status_lbl.setText("⚠ 没有可用的控制台")
                    return None
                fn(spec)
                result_text = f"✓ 正在安装：{spec}"
                status_lbl.setText(f"✓ 正在安装：{spec}")
            elif action_type == "patch":
                fn = env.get("patch_file_fn")
                written = fn(final_target, content, bd) if fn else None
                if written is None:
                    from .agentic_actions import execute_patch_file
                    written = execute_patch_file(final_target, content, bd)
                result_text = f"✓ Patched: {written}"
                status_lbl.setText(f"✓ 已修补：{written}")
                # Reload the file in the editor if it is already open
                reload_fn = env.get("reload_file_fn")
                if reload_fn and written:
                    try:
                        reload_fn(written)
                    except Exception:
                        pass
            elif action_type == "read":
                fn = env.get("read_file_fn")
                if not fn:
                    status_lbl.setText("⚠ read_file_fn 不可用")
                    return None
                _fp, _lf, _lt = _parse_read_target(target)
                content_out, err, rc = fn(_fp, bd, _lf, _lt)
                if rc != 0:
                    status_lbl.setText(f"⚠ {err}")
                    result_text = f"[read: error — {err}]"   # send error to LLM
                else:
                    result_text = content_out
                    _sfx = f"  lines {_lf}-{_lt}" if _lf is not None else ""
                    status_lbl.setText(f"✓ Read: {_fp}{_sfx}")
            elif action_type == "ls":
                fn = env.get("ls_dir_fn")
                if not fn:
                    status_lbl.setText("⚠ ls_dir_fn 不可用")
                    return None
                listing, err, rc = fn(target, bd)
                if rc != 0:
                    status_lbl.setText(f"⚠ {err}")
                    result_text = f"[ls: error — {err}]"     # send error to LLM
                else:
                    result_text = listing
                    status_lbl.setText(f"✓ Listed: {target}")
            elif action_type == "grep":
                fn = env.get("grep_files_fn")
                if not fn:
                    status_lbl.setText("⚠ grep_files_fn 不可用")
                    return None
                _gparts  = target.split(":", 1)
                _pattern = _gparts[0]
                _scope   = _gparts[1] if len(_gparts) > 1 else ""
                results, err, rc = fn(_pattern, _scope, bd)
                if rc != 0:
                    status_lbl.setText(f"⚠ {err}")
                    result_text = f"[grep: error — {err}]"   # send error to LLM
                else:
                    result_text = results
                    status_lbl.setText(f"✓ Search: {_pattern}")
            elif action_type == "delete":
                err = _proj_security_check(final_target, env, bd, status_lbl, "delete")
                if err:
                    result_text = err
                else:
                    fn = env.get("delete_file_fn")
                    deleted = fn(final_target, bd) if fn else None
                    if deleted is None:
                        from .agentic_actions import execute_delete_file
                        deleted = execute_delete_file(final_target, bd)
                    result_text = f"✓ Deleted: {deleted}"
                    status_lbl.setText(f"✓ 已删除：{deleted}")
            elif action_type == "delete_dir":
                err = _proj_security_check(final_target, env, bd, status_lbl, "delete_dir")
                if err:
                    result_text = err
                else:
                    fn = env.get("delete_dir_fn")
                    deleted = fn(final_target, bd) if fn else None
                    if deleted is None:
                        from .agentic_actions import execute_delete_dir
                        deleted = execute_delete_dir(final_target, bd)
                    result_text = f"✓ Deleted directory: {deleted}"
                    status_lbl.setText(f"✓ 已删除：{deleted}")
            elif action_type in ("rename", "rename_dir"):
                new_path = content.strip().split("\n")[0]
                err = _proj_security_check(final_target, env, bd, status_lbl, action_type)
                if err is None:
                    err = _proj_security_check(new_path, env, bd, status_lbl, action_type)
                if err:
                    result_text = err
                else:
                    fn = env.get("rename_fn")
                    paths = fn(final_target, new_path, bd) if fn else None
                    if paths is None:
                        from .agentic_actions import execute_rename
                        paths = execute_rename(final_target, new_path, bd)
                    old_abs, new_abs = paths
                    result_text = f"✓ Renamed: {old_abs} → {new_abs}"
                    status_lbl.setText(f"✓ 已重命名为：{new_abs}")
            elif action_type == "git":
                import shlex as _shlex
                args = _shlex.split(content.strip())
                exec_btn.setEnabled(False)
                exec_btn.setText("⏳ 运行中…")
                status_lbl.setText("")

                worker = _GitWorker(args, bd)

                def _on_git_done(stdout, stderr, rc, _w=worker):
                    output = (stdout + stderr).strip() or "(no output)"
                    _auto_dismiss = (on_git_done_extra is not None
                                     or env.get("auto_send_results", False))
                    git_out_edit.setPlainText(output)
                    exec_btn.setEnabled(True)
                    exec_btn.setText(btn_text)
                    if _auto_dismiss:
                        # Output will be sent to LLM automatically — no need for
                        # the manual output panel; show done badge instead.
                        exec_btn.setVisible(False)
                        done_badge.setVisible(True)
                        if rc != 0:
                            status_lbl.setText(f"⚠ git exited with code {rc}")
                    else:
                        n      = max(output.count("\n") + 1, 1)
                        lh     = max(git_out_edit.fontMetrics().lineSpacing(), 14)
                        # With WidgetWidth wrap a long line may occupy extra visual
                        # rows; the floor of 52px (≈3 lines) prevents the widget
                        # from collapsing to zero when the font metrics aren't yet
                        # fully resolved on a hidden widget.
                        edit_h = max(min(n * lh + 16, 180), 52)
                        git_out_edit.setFixedHeight(edit_h)
                        git_output_panel.setFixedHeight(edit_h + 42)
                        git_output_panel.setVisible(True)
                        exec_btn.setVisible(False)
                        if rc != 0:
                            status_lbl.setText(f"⚠ git exited with code {rc}")
                    # Persist execution record so done badge survives history reload
                    on_exec = env.get("on_executed")
                    if on_exec:
                        try:
                            on_exec(block_idx, action_type, content.strip())
                        except Exception:
                            pass
                    _w.deleteLater()
                    if on_git_done_extra:
                        on_git_done_extra(stdout, stderr, rc)
                    elif env.get("auto_send_results", False):
                        auto_fn = env.get("auto_send_fn")
                        if auto_fn:
                            _cmd_lbl = content.strip().split("\n")[0]
                            auto_fn(f"git {_cmd_lbl}", (stdout + stderr).strip() or "(no output)", "git")

                worker.done.connect(_on_git_done)
                worker.start()
                return   # buttons handled by git_attach/dismiss — skip done_badge here
        except Exception as exc:
            status_lbl.setText(f"⚠ {exc}")
            return None
        exec_btn.setVisible(False)
        done_badge.setVisible(True)
        # For read/ls/grep the done indicator is in the header; hide the now-empty
        # button row so no blank space is left beneath the header.
        if _header_done_badge is not None:
            btn_row.setVisible(False)
        # Notify parent to persist this execution in message history
        on_exec = env.get("on_executed")
        if on_exec:
            try:
                on_exec(block_idx, action_type, target)
            except Exception:
                pass
        return result_text

    def _on_execute():
        final_target = target
        # Resolve base_dir lazily so it reflects the current project root
        # even when this block was rendered at startup before the project loaded.
        live_base_dir = env.get("base_dir_fn", lambda: base_dir)()
        confirm = env.get("confirm_each", True)

        if confirm:
            from .agentic_actions import show_confirm_dialog
            parent_widget = frame.window()
            confirmed, final_target = show_confirm_dialog(
                parent_widget, action_type, target, content,
                base_dir=live_base_dir)
            if not confirmed:
                return

        result = _run_action(final_target, live_base_dir)
        # Auto-send for sync actions (git handles it inside _on_git_done)
        if result and action_type != "git":
            if env.get("auto_send_results", False):
                auto_fn = env.get("auto_send_fn")
                if auto_fn:
                    kind = action_type if action_type in ("read", "ls", "grep") else "result"
                    auto_fn(target, result, kind)
            elif action_type in ("read", "ls", "grep") and insp_output_panel is not None:
                # Manual mode: show output panel so the user can add to chat or dismiss
                insp_out_edit.setPlainText(result)
                n      = max(result.count("\n") + 1, 1)
                lh     = insp_out_edit.fontMetrics().lineSpacing()
                edit_h = min(n * lh + 16, 180)
                insp_out_edit.setFixedHeight(edit_h)
                insp_output_panel.setFixedHeight(edit_h + 42)
                insp_output_panel.setVisible(True)
                done_badge.setVisible(False)  # panel takes over; badge reappears on dismiss

    exec_btn.clicked.connect(_on_execute)
    # read/ls/grep/delete/rename: re-running makes no sense (inspection results
    # are stale; delete/rename are irreversible). Leave badge as static indicator.
    if action_type not in ("read", "ls", "grep", "delete", "delete_dir",
                           "rename", "rename_dir"):
        done_badge.clicked.connect(_on_execute)   # re-run on Done badge click
    elif _header_done_badge is None:
        # btn_row-based badge (fallback): disable hover transition
        done_badge.set_static_mode()
    # QLabel header badge has no hover/re-run behaviour to disable

    # Register for batch/auto-confirm
    _exec_reg = env.get("_exec_registry")
    if _exec_reg is not None:
        _bidx = env.get("_block_idx", -1)
        if _bidx >= 0 and _bidx not in env.get("_executed_blocks", set()):
            def _run_direct(_t=target):
                _bd = env.get("base_dir_fn", lambda: base_dir)()
                return _run_action(_t, _bd)
            def _run_chained(_cb, _t=target):
                _bd = env.get("base_dir_fn", lambda: base_dir)()
                _run_action(_t, _bd, on_git_done_extra=_cb)

            # For inspection actions (read/ls/grep) in off (manual) mode,
            # _batch_execute calls run_direct() and receives the result but
            # auto_send=False — the result would be discarded.  This closure
            # lets _batch_execute show the output panel so the user can choose
            # to send the result to the LLM or dismiss it.
            # For non-inspection action types insp_output_panel is None, so
            # the function returns immediately and is effectively a no-op.
            def _show_insp_output(result_text,
                                  _p=insp_output_panel,
                                  _e=insp_out_edit,
                                  _d=done_badge):
                if _p is None or not result_text:
                    return
                _e.setPlainText(result_text)
                n      = max(result_text.count("\n") + 1, 1)
                lh     = _e.fontMetrics().lineSpacing()
                edit_h = min(n * lh + 16, 180)
                _e.setFixedHeight(edit_h)
                _p.setFixedHeight(edit_h + 42)
                _p.setVisible(True)
                _d.setVisible(False)   # panel takes over; badge reappears on dismiss

            _exec_reg[_bidx] = {
                "action_type":        action_type,
                "target":             target,
                "content":            content,
                "run_direct":         _run_direct,
                "run_direct_chained": _run_chained if action_type == "git" else None,
                "widget":             frame,   # reference used by grouping logic
                "show_output_fn":     _show_insp_output,
            }

    # Mark the frame so the history-reload grouping code can identify it
    # without needing the exec registry (which is only populated for new blocks).
    frame.setProperty("agentic_action_type",   action_type)
    frame.setProperty("agentic_action_target", target)

    return frame


# ---------------------------------------------------------------------------
# Main entry point: render markdown text into a QWidget
# ---------------------------------------------------------------------------
def render_markdown(text, insert_signal=None, font_cfg=None, action_env=None):
    """
    Parse markdown text and return a QWidget containing all rendered blocks.
    insert_signal: optional Signal(str) emitted when user clicks "Copy to editor"
    font_cfg: optional dict with keys fs_base, fs_code, fs_heading, fs_list,
              fs_table, fs_think (all in pt). Falls back to defaults if absent.
    """
    from .settings_dialog import EDITOR_DEFAULTS
    cfg = {**EDITOR_DEFAULTS, **(font_cfg or {})}

    try:
        from spyder.config.gui import is_dark_interface
        text_color = "#d4d4d4" if is_dark_interface() else "#1a1a1a"
    except Exception:
        text_color = "#d4d4d4"

    container = QWidget()
    container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    lay = QVBoxLayout(container)
    lay.setContentsMargins(0, 2, 0, 2)
    lay.setSpacing(3)

    blocks = parse_blocks(text)
    has_code = any(b["type"] == "code" for b in blocks)

    for block in blocks:
        t = block["type"]
        if t == "think":
            lay.addWidget(build_think(block, cfg["fs_think"]))
        elif t == "heading":
            lay.addWidget(build_heading(block, cfg["fs_heading"]))
        elif t == "paragraph":
            lay.addWidget(build_paragraph(block, text_color, cfg["fs_base"]))
        elif t == "code":
            lay.addWidget(build_code_block(block, insert_signal, cfg["fs_code"]))
        elif t == "action":
            lay.addWidget(build_action_block(block, action_env, cfg["fs_code"]))
        elif t == "hr":
            lay.addWidget(build_hr())
        elif t == "blockquote":
            lay.addWidget(build_blockquote(block, text_color, cfg["fs_base"]))
        elif t == "list":
            lay.addWidget(build_list(block, text_color, cfg["fs_list"]))
        elif t == "table":
            lay.addWidget(build_table(block, cfg["fs_table"]))

    if not has_code and insert_signal is not None:
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_all = QPushButton("📋 复制到编辑器")
        copy_all.setFlat(True)
        copy_all.setStyleSheet(
            "QPushButton { color: #888; font-size: 10px; padding: 1px 4px; "
            "border: none; background: transparent; }"
            "QPushButton:hover { color: #ccc; }")
        _mr_install_themed_tip(copy_all, "在光标处插入完整回复到当前编辑器")
        copy_all.clicked.connect(
            lambda checked=False, t=text: insert_signal.emit(t))
        btn_row.addWidget(copy_all)
        lay.addLayout(btn_row)

    return container
