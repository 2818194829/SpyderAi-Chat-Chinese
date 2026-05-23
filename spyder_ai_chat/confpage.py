# -*- coding: utf-8 -*-
"""
AI Chat – Preferences page stub.
FIM and chat settings are configured via the ⚙ button in the AI Chat pane.
This file is kept so CONF_WIDGET_CLASS in plugin.py has a valid import.
"""
from qtpy.QtWidgets import QVBoxLayout, QLabel
from spyder.api.preferences import PluginConfigPage


class AIChatConfigPage(PluginConfigPage):
    def setup_page(self):
        lbl = QLabel(
            "AI 聊天设置通过 AI 聊天面板内的 ⚙ 按钮进行配置\n"
            "（包括 FIM 代码补全设置）。"
        )
        lay = QVBoxLayout()
        lay.addWidget(lbl)
        lay.addStretch(1)
        self.setLayout(lay)
