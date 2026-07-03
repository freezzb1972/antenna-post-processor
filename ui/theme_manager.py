"""
主题管理器
==========
使用 Qt Fusion 风格 + QPalette 自定义调色板，
无需外部依赖，文字颜色自动适配暗/亮主题。
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


class ThemeManager:
    """Fusion 风格 + 自定义调色板（精选 4 主题）。"""

    ALL_THEMES = [
        ("dark_teal",       "暗色 青绿 ★"),
        ("dark_blue",       "暗色 蓝色"),
        ("dark_amber",      "暗色 琥珀"),
        ("dark_gruvbox",    "暗色 复古暖"),
        ("dark_mono",       "暗色 白框白字"),
        ("light_blue",      "亮色 蓝色"),
        ("light_teal",      "亮色 青绿"),
    ]

    DEFAULT_THEME = "dark_teal"
    _current_theme: str = DEFAULT_THEME

    @classmethod
    def current_theme(cls) -> str:
        return cls._current_theme

    # 暗色主题强调色映射 — 用于 QCheckBox/QRadioButton 指示器着色
    _ACCENT_COLORS = {
        "dark_teal": "#2dd4bf",
        "dark_blue": "#60a5fa",
        "dark_amber": "#f59e0b",
        "dark_gruvbox": "#d79921",
        "dark_mono": "#ffffff",
    }

    @classmethod
    def apply(cls, theme_name: str = DEFAULT_THEME):
        app = QApplication.instance()
        if app is None:
            return

        app.setStyle(QStyleFactory.create("Fusion"))
        palette = cls._make_palette(theme_name)
        app.setPalette(palette)

        # 暗色主题: 为复选框/单选框指示器注入可见边框 + 勾选色
        if theme_name.startswith("dark"):
            accent = cls._ACCENT_COLORS.get(theme_name)
            if accent is None:
                print(f"[theme] WARNING: no accent color for '{theme_name}', using teal as fallback", file=sys.stderr)
                accent = "#2dd4bf"
            app.setStyleSheet(f"""
                QCheckBox::indicator, QRadioButton::indicator {{
                    border: 1px solid #666;
                    background: #2a2a2a;
                    width: 14px; height: 14px;
                    border-radius: 2px;
                }}
                QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
                    background: {accent};
                    border-color: {accent};
                }}
                QGroupBox::indicator {{
                    border: 1px solid #666;
                    background: #2a2a2a;
                    width: 14px; height: 14px;
                    border-radius: 2px;
                }}
                QGroupBox::indicator:checked {{
                    background: {accent};
                    border-color: {accent};
                }}
                QMenu::separator {{
                    height: 2px;
                    background: #555;
                    margin: 4px 8px;
                }}
            """)
        else:
            app.setStyleSheet("")  # 亮色主题使用系统原生指示器

        cls._current_theme = theme_name

    @classmethod
    def _make_palette(cls, theme: str) -> QPalette:
        """根据主题名创建 QPalette。"""
        p = QPalette()

        if theme == "dark_teal":
            bg = QColor("#1e1e2e"); fg = QColor("#cdd6f4")
            base = QColor("#181825"); sel = QColor("#2dd4bf")
            btn = QColor("#313244")
            return cls._build(p, bg, fg, base, sel, btn, "#a6adc8")

        elif theme == "dark_blue":
            bg = QColor("#1a1a2e"); fg = QColor("#e0e0ff")
            base = QColor("#16162a"); sel = QColor("#60a5fa")
            btn = QColor("#2a2a4a")
            return cls._build(p, bg, fg, base, sel, btn, "#9090c0")

        elif theme == "dark_amber":
            bg = QColor("#1e1e1e"); fg = QColor("#e8e0d0")
            base = QColor("#181818"); sel = QColor("#f59e0b")
            btn = QColor("#2d2d2d")
            return cls._build(p, bg, fg, base, sel, btn, "#887766")

        elif theme == "dark_gruvbox":
            bg = QColor("#282828"); fg = QColor("#ebdbb2")
            base = QColor("#1d2021"); sel = QColor("#d79921")
            btn = QColor("#3c3836")
            return cls._build(p, bg, fg, base, sel, btn, "#a89984")

        elif theme == "dark_mono":
            bg = QColor("#1a1a1a"); fg = QColor("#ffffff")
            base = QColor("#111111"); sel = QColor("#ffffff")
            btn = QColor("#2a2a2a")
            return cls._build(p, bg, fg, base, sel, btn, "#888888")

        elif theme == "light_blue":
            bg = QColor("#f8f9fa"); fg = QColor("#1a1a2e")
            base = QColor("#ffffff"); sel = QColor("#3b82f6")
            btn = QColor("#e2e8f0")
            return cls._build(p, bg, fg, base, sel, btn, "#64748b")

        else:  # light_teal
            bg = QColor("#f0fdfa"); fg = QColor("#0f172a")
            base = QColor("#ffffff"); sel = QColor("#14b8a6")
            btn = QColor("#ccfbf1")
            return cls._build(p, bg, fg, base, sel, btn, "#64748b")

    @staticmethod
    def _build(p: QPalette, bg: QColor, fg: QColor, base: QColor,
               sel: QColor, btn: QColor, disabled_fg: QColor) -> QPalette:
        p.setColor(QPalette.Window, bg)
        p.setColor(QPalette.WindowText, fg)
        p.setColor(QPalette.Base, base)
        p.setColor(QPalette.AlternateBase, bg)
        p.setColor(QPalette.Text, fg)
        p.setColor(QPalette.Button, btn)
        p.setColor(QPalette.ButtonText, fg)
        p.setColor(QPalette.Highlight, sel)
        p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        p.setColor(QPalette.ToolTipBase, QColor("#2d2d2d"))
        p.setColor(QPalette.ToolTipText, fg)
        p.setColor(QPalette.Link, sel)
        # Disabled colors
        p.setColor(QPalette.Disabled, QPalette.WindowText, disabled_fg)
        p.setColor(QPalette.Disabled, QPalette.Text, disabled_fg)
        p.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_fg)
        return p

    @classmethod
    def load_and_apply(cls):
        """从配置文件恢复主题或使用默认值。"""
        try:
            from src.config_manager import get_config
            cfg = get_config()
            theme = cfg.theme if hasattr(cfg, 'theme') and cfg.theme else cls.DEFAULT_THEME
        except Exception:
            theme = cls.DEFAULT_THEME
        cls.apply(theme)

    @classmethod
    def save_theme(cls, theme_name: str):
        """保存主题到配置文件 + QSettings。"""
        try:
            from src.config_manager import get_config_manager
            get_config_manager().config.theme = theme_name
            get_config_manager().save()
        except Exception:
            pass
        settings = QSettings()
        settings.setValue("theme/name", theme_name)
