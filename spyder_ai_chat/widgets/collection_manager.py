# -*- coding: utf-8 -*-
"""
Chat Collection Manager dialog.  (C) 2026 by Maciej Piecko

Allows the user to create, rename, delete, and move chats between collections.
"""

from qtpy.QtCore    import Qt, Signal
from qtpy.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QLabel, QPushButton,
    QComboBox, QInputDialog, QMessageBox, QRadioButton,
    QButtonGroup, QGroupBox, QWidget, QFrame, QSizePolicy,
    QAbstractItemView,
)

from .chat_history_manager import (
    list_collections, list_chats, create_collection, rename_collection,
    move_chat, delete_collection, validate_collection_name,
)

_DEFAULT_LABEL = "Default"
_DEFAULT_VALUE = ""


class _DeleteCollectionDialog(QDialog):
    """Modal: choose what to do with chats when deleting a collection."""

    def __init__(self, collection_name, other_collections, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"删除集合 '{collection_name}'")
        self.setMinimumWidth(380)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        info = QLabel(
            f"集合 <b>{collection_name}</b> 将被永久删除。\n"
            "其中的聊天记录应如何处理？"
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #444;")
        lay.addWidget(sep)

        self._bg = QButtonGroup(self)

        self._rb_delete = QRadioButton("删除此集合中的所有聊天记录")
        self._bg.addButton(self._rb_delete, 0)
        lay.addWidget(self._rb_delete)

        move_row = QHBoxLayout()
        self._rb_move = QRadioButton("将聊天记录移动到：")
        self._bg.addButton(self._rb_move, 1)
        move_row.addWidget(self._rb_move)

        self._move_combo = QComboBox()
        self._move_combo.addItem(_DEFAULT_LABEL, _DEFAULT_VALUE)
        for c in other_collections:
            self._move_combo.addItem(c, c)
        self._move_combo.setEnabled(False)
        move_row.addWidget(self._move_combo, 1)
        lay.addLayout(move_row)

        self._rb_move.toggled.connect(self._move_combo.setEnabled)
        self._rb_delete.setChecked(True)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._ok_btn = QPushButton("删除")
        self._ok_btn.setStyleSheet(
            "QPushButton { color: #f66; border: 1px solid #f66; "
            "border-radius: 3px; padding: 4px 12px; }"
            "QPushButton:hover { color: #faa; border-color: #faa; }")
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        self._ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._ok_btn)
        lay.addLayout(btn_row)

    def move_to(self):
        """Returns the target collection ('' = Default) or None if delete-all chosen."""
        if self._rb_move.isChecked():
            return self._move_combo.currentData()
        return None  # delete all


class ChatCollectionManagerDialog(QDialog):
    """
    Side-by-side panel:
      Left  — list of collections (Default + user-named)
      Right — chats in the selected collection (multi-select)
    Buttons: + New, Rename, Delete | Move selected to [combo]

    Emits `collections_changed` when the user makes any structural change.
    """
    collections_changed = Signal()

    def __init__(self, current_collection="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("管理聊天集合")
        self.setMinimumSize(640, 400)

        self._current_collection = current_collection  # track externally active coll

        main_lay = QVBoxLayout(self)
        main_lay.setSpacing(8)

        # ── splitter: left = collections, right = chats ─────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left panel
        left_w = QWidget()
        left_lay = QVBoxLayout(left_w)
        left_lay.setContentsMargins(0, 0, 4, 0)
        left_lay.setSpacing(4)

        left_hdr = QLabel("集合")
        left_hdr.setStyleSheet("font-weight: bold; font-size: 10pt;")
        left_lay.addWidget(left_hdr)

        self._coll_list = QListWidget()
        self._coll_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._coll_list.currentRowChanged.connect(self._on_coll_selected)
        left_lay.addWidget(self._coll_list, 1)

        # Collection action buttons
        coll_btn_row = QHBoxLayout()
        self._new_btn    = QPushButton("+ 新建")
        self._rename_btn = QPushButton("重命名")
        self._delete_btn = QPushButton("删除")
        self._delete_btn.setStyleSheet(
            "QPushButton { color: #f88; } QPushButton:hover { color: #fcc; }")
        for b in (self._new_btn, self._rename_btn, self._delete_btn):
            b.setFixedHeight(26)
            coll_btn_row.addWidget(b)
        left_lay.addLayout(coll_btn_row)
        splitter.addWidget(left_w)

        # Right panel
        right_w = QWidget()
        right_lay = QVBoxLayout(right_w)
        right_lay.setContentsMargins(4, 0, 0, 0)
        right_lay.setSpacing(4)

        self._right_hdr = QLabel("聊天记录")
        self._right_hdr.setStyleSheet("font-weight: bold; font-size: 10pt;")
        right_lay.addWidget(self._right_hdr)

        self._chat_list = QListWidget()
        self._chat_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        right_lay.addWidget(self._chat_list, 1)

        # Move row
        move_row = QHBoxLayout()
        move_lbl = QLabel("将选中的移动到：")
        self._move_combo = QComboBox()
        self._move_btn = QPushButton("移动")
        self._move_btn.setFixedHeight(26)
        move_row.addWidget(move_lbl)
        move_row.addWidget(self._move_combo, 1)
        move_row.addWidget(self._move_btn)
        right_lay.addLayout(move_row)
        splitter.addWidget(right_w)

        splitter.setSizes([200, 420])
        main_lay.addWidget(splitter, 1)

        # ── Close button ─────────────────────────────────────────────────
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        main_lay.addLayout(close_row)

        # Wire signals
        self._new_btn.clicked.connect(self._on_new)
        self._rename_btn.clicked.connect(self._on_rename)
        self._delete_btn.clicked.connect(self._on_delete)
        self._move_btn.clicked.connect(self._on_move)

        self._populate_collections()

    # ── collection list ───────────────────────────────────────────────────

    def _populate_collections(self, select_name=None):
        """Rebuild the left collection list."""
        self._coll_list.blockSignals(True)
        self._coll_list.clear()

        # Default always first
        default_item = QListWidgetItem(_DEFAULT_LABEL)
        default_item.setData(Qt.UserRole, _DEFAULT_VALUE)
        default_item.setToolTip("默认集合（聊天根文件夹）")
        self._coll_list.addItem(default_item)

        for name in list_collections():
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            self._coll_list.addItem(item)

        self._coll_list.blockSignals(False)

        # Select the desired row
        target = select_name if select_name is not None else self._current_collection
        for i in range(self._coll_list.count()):
            if self._coll_list.item(i).data(Qt.UserRole) == target:
                self._coll_list.setCurrentRow(i)
                break
        else:
            self._coll_list.setCurrentRow(0)

        self._on_coll_selected(self._coll_list.currentRow())

    def _selected_collection(self):
        """Returns the currently selected collection name ('' = Default)."""
        item = self._coll_list.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def _on_coll_selected(self, row):
        if row < 0:
            return
        coll = self._selected_collection()
        is_default = (coll == _DEFAULT_VALUE)

        # Default can't be renamed or deleted
        self._rename_btn.setEnabled(not is_default)
        self._delete_btn.setEnabled(not is_default)

        # Update right header
        label = _DEFAULT_LABEL if is_default else coll
        self._right_hdr.setText(f"'{label}' 中的聊天记录")

        self._populate_chats(coll)
        self._populate_move_combo(coll)

    def _populate_chats(self, collection):
        """Rebuild the right chat list for the selected collection."""
        self._chat_list.clear()
        chats = list_chats(collection=collection, all_collections=False)
        for chat in chats:
            try:
                dt = chat["saved_at"][:16].replace("T", " ")
            except Exception:
                dt = ""
            preview = (chat.get("preview") or "(empty)")[:60]
            item = QListWidgetItem(f"{dt}  {preview}")
            item.setData(Qt.UserRole, chat["filename"])
            self._chat_list.addItem(item)

    def _populate_move_combo(self, current_collection):
        """Rebuild the 'move to' combo excluding the current collection."""
        self._move_combo.blockSignals(True)
        self._move_combo.clear()
        # Always include Default
        if current_collection != _DEFAULT_VALUE:
            self._move_combo.addItem(_DEFAULT_LABEL, _DEFAULT_VALUE)
        for name in list_collections():
            if name != current_collection:
                self._move_combo.addItem(name, name)
        self._move_combo.blockSignals(False)

    # ── collection actions ────────────────────────────────────────────────

    def _on_new(self):
        name, ok = QInputDialog.getText(
            self, "新建集合", "集合名称：")
        if not ok or not name.strip():
            return
        name = name.strip()
        ok2, err = create_collection(name)
        if not ok2:
            QMessageBox.warning(self, "无法创建集合", err)
            return
        self._populate_collections(select_name=name)
        self.collections_changed.emit()

    def _on_rename(self):
        old_name = self._selected_collection()
        if not old_name:
            return  # Default — should not happen (button disabled)
        new_name, ok = QInputDialog.getText(
            self, "重命名集合", "新名称：", text=old_name)
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name == old_name:
            return
        ok2, err = rename_collection(old_name, new_name)
        if not ok2:
            QMessageBox.warning(self, "无法重命名", err)
            return
        # If the renamed collection was the externally-active one, update that ref
        if self._current_collection == old_name:
            self._current_collection = new_name
        self._populate_collections(select_name=new_name)
        self.collections_changed.emit()

    def _on_delete(self):
        coll = self._selected_collection()
        if not coll:
            return  # Default — should not happen
        others = [c for c in list_collections() if c != coll]
        dlg = _DeleteCollectionDialog(coll, others, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        move_to = dlg.move_to()   # None = delete all, str = target collection
        ok, err = delete_collection(coll, move_to=move_to)
        if not ok:
            QMessageBox.warning(self, "无法删除集合", err)
            return
        # If deleted collection was active externally, switch to Default
        if self._current_collection == coll:
            self._current_collection = _DEFAULT_VALUE
        self._populate_collections(select_name=_DEFAULT_VALUE)
        self.collections_changed.emit()

    def _on_move(self):
        selected_items = self._chat_list.selectedItems()
        if not selected_items:
            return
        from_coll = self._selected_collection()
        to_coll   = self._move_combo.currentData()
        if from_coll == to_coll:
            return
        for item in selected_items:
            fname = item.data(Qt.UserRole)
            move_chat(fname, from_coll, to_coll)
        self._populate_chats(from_coll)
        self.collections_changed.emit()

    def resulting_collection(self):
        """Return the collection that should be active after the dialog closes.
        May differ from the original if a rename or delete changed things.
        """
        return self._current_collection
