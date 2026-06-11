"""
国际化管理器 (i18n)
====================
基于 Qt Linguist 的翻译系统，支持中英文运行时切换。

使用方式：
  - 标记字符串: self.tr("Hello")
  - 切换语言: I18nManager.switch("zh_CN")
  - 每个窗口需实现 changeEvent() → ui.retranslateUi(self)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QLocale, QTranslator
from PySide6.QtWidgets import QApplication


class I18nManager:
    _translator: Optional[QTranslator] = None
    _current_lang: str = "zh_CN"
    _translations_dir: Path = Path(__file__).parent.parent / "i18n"

    @classmethod
    def init(cls, app: QApplication, language: Optional[str] = None):
        """初始化翻译。如未指定语言，跟随系统 locale。"""
        if language is None:
            sys_locale = QLocale.system().name()  # e.g., "zh_CN"
            # 只支持 zh_CN 和 en_US
            if sys_locale.startswith("zh"):
                language = "zh_CN"
            else:
                language = "en_US"

        cls.switch(app, language)

    @classmethod
    def switch(cls, app: QApplication, language: str):
        """切换语言。"""
        # 移除旧翻译
        if cls._translator:
            app.removeTranslator(cls._translator)

        # 加载新翻译
        cls._translator = QTranslator(app)
        qm_path = cls._translations_dir / f"app_{language}.qm"

        if qm_path.exists():
            cls._translator.load(str(qm_path))
            app.installTranslator(cls._translator)
            cls._current_lang = language

    @classmethod
    def current_language(cls) -> str:
        return cls._current_lang

    @classmethod
    def toggle(cls, app: QApplication):
        """中英切换。"""
        new_lang = "en_US" if cls._current_lang == "zh_CN" else "zh_CN"
        cls.switch(app, new_lang)
