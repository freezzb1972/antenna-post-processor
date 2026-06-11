"""
天线参数后处理工具 — 应用程序入口
=================================
双击运行此文件或打包后的 .exe 启动。
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from i18n.i18n_manager import I18nManager
from ui.main_window import MainWindow
from ui.theme_manager import ThemeManager


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AntennaPostProcessor")
    app.setOrganizationName("AntennaPP")

    # 主题
    ThemeManager.apply("dark_teal")

    # 国际化
    I18nManager.init(app)

    # 主窗口
    window = MainWindow(app)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
