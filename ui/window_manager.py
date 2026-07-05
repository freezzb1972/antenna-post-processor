"""
窗口管理器
==========
管理所有 WorkWindow 实例的生命周期，提供新建/关闭/切换窗口功能。
每个窗口菜单栏中的「窗口」项目由 WindowManager 统一更新。
"""
from __future__ import annotations

from __future__ import annotations
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ui.main_window import MainWindow as WorkWindow  # noqa: F401
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QWidgetAction


class WindowManager:
    """单例窗口管理器。"""

    _instance: "WindowManager | None" = None

    def __init__(self):
        if WindowManager._instance is not None:
            raise RuntimeError("WindowManager is a singleton")
        WindowManager._instance = self
        self._windows: List["WorkWindow"] = []  # type: ignore[name-defined]

    @classmethod
    def instance(cls) -> "WindowManager":
        if cls._instance is None:
            cls._instance = WindowManager()
        return cls._instance

    # ── 窗口管理 ──

    def register(self, window: "WorkWindow") -> None:  # type: ignore[name-defined]
        """注册新窗口并更新所有窗口菜单。"""
        self._windows.append(window)
        window.destroyed.connect(lambda: self._on_window_destroyed(window))
        self._update_all_window_menus()

    def create_window(self, app=None) -> "WorkWindow":  # type: ignore[name-defined]
        """创建新的 WorkWindow。"""
        from ui.main_window import MainWindow
        win = MainWindow(app or self._first_app())
        self._windows.append(win)
        win.destroyed.connect(lambda: self._on_window_destroyed(win))
        win.show()
        self._update_all_window_menus()
        return win

    def close_window(self, window: "WorkWindow") -> None:  # type: ignore[name-defined]
        """关闭指定窗口。"""
        if window in self._windows:
            window.close()

    def focus_window(self, window: "WorkWindow") -> None:
        """聚焦指定窗口。"""
        window.show()
        window.raise_()
        window.activateWindow()

    def _on_window_destroyed(self, window: "WorkWindow") -> None:  # type: ignore[name-defined]
        """窗口关闭后从列表移除并更新菜单。"""
        if window in self._windows:
            self._windows.remove(window)
        self._update_all_window_menus()

    # ── 菜单更新 ──

    def _update_all_window_menus(self) -> None:
        """同步所有窗口的「窗口」菜单内容。"""
        for win in self._windows:
            self._refresh_window_menu(win)

    def _refresh_window_menu(self, window: "WorkWindow") -> None:  # type: ignore[name-defined]
        """重建某个窗口的「窗口」菜单（窗口列表部分）。"""
        menu = getattr(window, '_menu_window', None)
        if menu is None:
            return

        # 清除现有的窗口列表项（保留"新建窗口"和分隔线）
        # 找到第一个分隔线，清除其后的所有 action
        actions = menu.actions()
        sep_index = -1
        for i, action in enumerate(actions):
            if action.isSeparator():
                sep_index = i
                break

        if sep_index >= 0:
            # 清除分隔线后的所有项目
            for action in actions[sep_index + 1:]:
                menu.removeAction(action)

        # 重新添加窗口列表（每个带关闭按钮）
        for win in self._windows:
            title = win.window_title()
            wa = QWidgetAction(menu)
            wgt = QWidget()
            hl = QHBoxLayout(wgt)
            hl.setContentsMargins(4, 2, 4, 2)
            hl.setSpacing(8)
            lbl = QPushButton(title)
            lbl.setFlat(True)
            lbl.setCheckable(True)
            lbl.setChecked(win is window)
            lbl.setStyleSheet("text-align:left; border:none;")
            lbl.clicked.connect(lambda checked, w=win: self.focus_window(w))
            hl.addWidget(lbl, 1)
            btn_close = QPushButton("✕")
            btn_close.setFixedSize(20, 20)
            btn_close.setStyleSheet("border:none; color:#999;")
            btn_close.clicked.connect(lambda checked, w=win: self.close_window(w))
            hl.addWidget(btn_close)
            wa.setDefaultWidget(wgt)
            menu.addAction(wa)

    # ── 工具 ──

    def window_count(self) -> int:
        return len(self._windows)

    def _first_app(self):
        """返回第一个 QApplication 实例。"""
        from PySide6.QtWidgets import QApplication
        return QApplication.instance()

    @classmethod
    def reset(cls):
        """测试用：重置单例。"""
        cls._instance = None
