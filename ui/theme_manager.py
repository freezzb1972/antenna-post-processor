"""
主题管理器
==========
使用 qt-material 提供 Material Design 主题，支持 30+ 主题即时切换。
"""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


class ThemeManager:
    """qt-material 主题包装器 — 全量主题 + 持久化到 QSettings。"""

    # 完整主题列表（共 28 个）
    ALL_THEMES = [
        # ---- Dark ----
        ("dark_amber",      "Dark Amber"),
        ("dark_blue",       "Dark Blue"),
        ("dark_cyan",       "Dark Cyan"),
        ("dark_lightgreen", "Dark Light Green"),
        ("dark_medical",    "Dark Medical"),
        ("dark_pink",       "Dark Pink"),
        ("dark_purple",     "Dark Purple"),
        ("dark_red",        "Dark Red"),
        ("dark_teal",       "Dark Teal ★"),
        ("dark_yellow",     "Dark Yellow"),
        # ---- Light ----
        ("light_amber",        "Light Amber"),
        ("light_blue",         "Light Blue"),
        ("light_blue_500",     "Light Blue 500"),
        ("light_cyan",         "Light Cyan"),
        ("light_cyan_500",     "Light Cyan 500"),
        ("light_lightgreen",   "Light Light Green"),
        ("light_lightgreen_500","Light Light Green 500"),
        ("light_orange",       "Light Orange"),
        ("light_pink",         "Light Pink"),
        ("light_pink_500",     "Light Pink 500"),
        ("light_purple",       "Light Purple"),
        ("light_purple_500",   "Light Purple 500"),
        ("light_red",          "Light Red"),
        ("light_red_500",      "Light Red 500"),
        ("light_teal",         "Light Teal"),
        ("light_teal_500",     "Light Teal 500"),
        ("light_yellow",       "Light Yellow"),
    ]

    DEFAULT_THEME = "dark_teal"
    _current_theme: str = DEFAULT_THEME

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @classmethod
    def theme_names(cls) -> list[str]:
        """返回所有主题 ID 列表。"""
        return [t[0] for t in cls.ALL_THEMES]

    @classmethod
    def theme_display_names(cls) -> list[str]:
        """返回所有主题显示名称列表。"""
        return [t[1] for t in cls.ALL_THEMES]

    @classmethod
    def current_theme(cls) -> str:
        return cls._current_theme

    # ------------------------------------------------------------------
    # 应用
    # ------------------------------------------------------------------

    @classmethod
    def apply(cls, theme_name: str = DEFAULT_THEME):
        """应用 qt-material 主题。"""
        app = QApplication.instance()
        if app is None:
            return

        try:
            from qt_material import apply_stylesheet
            apply_stylesheet(app, theme=theme_name + ".xml")
        except (ImportError, FileNotFoundError):
            app.setStyle("Fusion")

        cls._current_theme = theme_name

    @classmethod
    def load_and_apply(cls):
        """从 QSettings 恢复主题或使用默认值。"""
        settings = QSettings()
        theme = settings.value("theme/name", cls.DEFAULT_THEME)
        cls.apply(theme)

    @classmethod
    def save_theme(cls, theme_name: str):
        """保存主题到 QSettings。"""
        settings = QSettings()
        settings.setValue("theme/name", theme_name)
