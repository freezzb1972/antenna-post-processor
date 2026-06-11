"""
应用程序入口
============
QApplication 初始化：主题、翻译、主窗口。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .i18n.i18n_manager import I18nManager
from .ui.main_window import MainWindow
from .ui.theme_manager import ThemeManager


def main():
    """应用程序主入口。"""
    app = QApplication(sys.argv)
    app.setApplicationName("AntennaPostProcessor")
    app.setApplicationDisplayName("天线参数后处理工具 — Antenna Post-Processor")
    app.setOrganizationName("AntennaPP")

    # 主题
    ThemeManager.apply("dark_teal")

    # 翻译
    I18nManager.init(app)

    # 主窗口
    window = MainWindow(app)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
