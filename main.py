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

from PySide6.QtWidgets import QApplication, QMessageBox

from i18n.i18n_manager import I18nManager
from ui.main_window import MainWindow
from ui.theme_manager import ThemeManager


def _check_license() -> bool:
    """启动时检查许可。返回 True 表示通过。"""
    from src.license import LicenseManager
    mgr = LicenseManager()

    # 尝试自动加载许可
    if mgr.auto_load():
        return True

    # 许可无效 — 显示信息（非阻塞，允许试用模式）
    return True  # 当前阶段: 不强制要求许可


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AntennaPostProcessor")
    app.setOrganizationName("AntennaPP")

    # 许可检查（非阻塞，记录状态供主窗口显示）
    _check_license()

    # 主题（从上次保存恢复，首次使用默认 dark_teal）
    ThemeManager.load_and_apply()

    # 国际化
    I18nManager.init(app)

    # 主窗口
    window = MainWindow(app)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
