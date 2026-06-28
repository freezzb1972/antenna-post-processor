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

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from i18n.i18n_manager import I18nManager
from ui.main_window import MainWindow
from ui.splash_screen import SplashScreen
from ui.theme_manager import ThemeManager


def _check_license(cfg_mgr) -> bool:
    """启动时检查许可。先检查配置文件，再回退到独立许可文件，
    首次启动自动开启 30 天试用。

    返回 True 表示通过，False 表示需要激活。
    """
    # 1. 优先检查配置文件中的许可
    if cfg_mgr.is_license_valid():
        lic = cfg_mgr.get_license_info()
        _print_license_ok(lic)
        _migrate_license_to_config(cfg_mgr)
        return True

    # 2. 回退: 搜索独立许可文件（兼容旧版）
    import json
    from src.license import LicenseManager
    mgr = LicenseManager()
    if mgr.auto_load() and mgr.license_info:
        info = mgr.license_info
        data = info.to_dict()
        data['signature'] = info.signature
        cfg_mgr.set_license(json.dumps(data))
        _print_license_ok(cfg_mgr.get_license_info())
        return True

    # 3. 首次启动 — 自动开启 30 天试用
    if cfg_mgr.start_trial():
        lic = cfg_mgr.get_license_info()
        print(f"[许可] 🧪 试用模式 — 剩余 {lic.trial_remaining} 天 (共 {lic.trial_days} 天)")
        return True

    # 4. 试用已过期 → 要求激活
    lic = cfg_mgr.get_license_info()
    if lic.is_trial_expired:
        print(f"[许可] ✗ 试用已过期 (试用期 {lic.trial_days} 天)", file=sys.stderr)
    else:
        print(f"[许可] ✗ {mgr.error_message or '未找到有效许可'}", file=sys.stderr)
    return False


def _print_license_ok(lic):
    """输出许可状态。"""
    from datetime import date
    if lic.is_trial:
        print(f"[许可] 🧪 试用模式 — {lic.licensee or '新用户'} — 剩余 {lic.trial_remaining} 天")
    elif hasattr(lic, 'expiry') and lic.expiry.upper() == "PERMANENT":
        print(f"[许可] ✓ 永久许可 — {lic.licensee}")
    elif hasattr(lic, 'expiry'):
        try:
            from datetime import datetime
            exp = datetime.strptime(lic.expiry, "%Y-%m-%d").date()
            days = (exp - date.today()).days
            print(f"[许可] ✓ {lic.licensee} — 剩余 {days} 天")
        except Exception:
            print(f"[许可] ✓ {lic.licensee} — {lic.expiry}")


def _migrate_license_to_config(cfg_mgr):
    """将独立许可文件迁移到配置文件。"""
    import json
    from src.license import LicenseManager
    mgr = LicenseManager()
    if mgr.auto_load() and mgr.license_info:
        info = mgr.license_info
        data = info.to_dict()
        data['signature'] = info.signature
        cfg_mgr.set_license(json.dumps(data))


def _show_activation() -> bool:
    """显示激活对话框。返回 True 表示激活成功。"""
    from ui.dialogs import ActivationDialog
    dlg = ActivationDialog()
    dlg.exec()
    return dlg.is_activated


def main():
    import json

    app = QApplication(sys.argv)
    app.setApplicationName("AntennaPostProcessor")
    app.setOrganizationName("AntennaPP")

    # 闪屏 — 立即显示, 告知用户程序正在加载
    splash = SplashScreen(app)
    splash.advance("正在初始化...", 5)

    # 加载用户配置 (antenna_config.json) — 包含许可
    from src.config_manager import get_config_manager
    cfg_mgr = get_config_manager()
    cfg_mgr.load()
    splash.advance("配置已加载", 10)

    # 许可检查 + 激活流程
    if not _check_license(cfg_mgr):
        splash.close()
        # 弹出激活对话框
        activated = _show_activation()
        if not activated:
            sys.exit(1)
        # 重新检查许可（激活后许可应已保存在配置文件中）
        if not cfg_mgr.is_license_valid():
            QMessageBox.critical(
                None, "许可验证失败",
                "激活后许可仍然无效，请联系管理员。"
            )
            sys.exit(1)

    splash.advance("正在加载主题...", 30)

    # 主题（从上次保存恢复，首次使用默认 dark_teal）
    ThemeManager.load_and_apply()
    splash.advance("正在配置语言...", 60)

    # 国际化
    I18nManager.init(app)
    splash.advance("正在创建主窗口...", 80)

    # 主窗口
    app.setQuitOnLastWindowClosed(False)
    from ui.window_manager import WindowManager
    wm = WindowManager.instance()
    window = MainWindow(app)
    splash.advance("启动完成", 100)

    splash.finish(window)
    window.show()

    # 事件循环
    exit_code = app.exec()

    # 退出时保存配置（含许可）
    cfg_mgr.save()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
