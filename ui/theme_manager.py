"""
主题管理器
=========
使用 qt-material 提供 Material Design 主题，支持深色/浅色切换。
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication


class ThemeManager:
    """qt-material 主题包装器。"""

    # 可用主题列表
    DARK_THEMES = [
        "dark_teal",
        "dark_blue",
        "dark_cyan",
        "dark_amber",
        "dark_pink",
    ]
    LIGHT_THEMES = [
        "light_teal",
        "light_blue",
        "light_cyan",
        "light_amber",
    ]

    _current_theme: str = "dark_teal"

    @classmethod
    def apply(cls, theme_name: str = "dark_teal"):
        """应用 qt-material 主题。"""
        try:
            from qt_material import apply_stylesheet

            app = QApplication.instance()
            if app is None:
                return
            apply_stylesheet(app, theme=theme_name + ".xml")
            cls._current_theme = theme_name
        except ImportError:
            # qt-material 不可用时回退到 Fusion
            app = QApplication.instance()
            if app:
                app.setStyle("Fusion")

    @classmethod
    def toggle_dark_light(cls):
        """在深色/浅色之间切换。"""
        if cls._current_theme.startswith("dark_"):
            # 切换到对应的浅色主题
            suffix = cls._current_theme.replace("dark_", "")
            if suffix in [t.replace("light_", "") for t in cls.LIGHT_THEMES]:
                cls.apply("light_" + suffix)
            else:
                cls.apply("light_teal")
        else:
            suffix = cls._current_theme.replace("light_", "")
            if suffix in [t.replace("dark_", "") for t in cls.DARK_THEMES]:
                cls.apply("dark_" + suffix)
            else:
                cls.apply("dark_teal")
