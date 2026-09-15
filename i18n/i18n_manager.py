"""
国际化管理器 (i18n)
====================
基于 Qt Linguist 的翻译系统，支持中英文运行时切换。

使用方式：
  - 标记字符串: self.tr("Hello")
  - 切换语言: I18nManager.switch(app, "zh_CN")
  - 刷新由 switch() 内部同步完成 (见 _refresh_all)，无需各类自行实现 changeEvent

为何是 switch() 内同步刷新而非依赖 changeEvent:
  installTranslator 投递 LanguageChange 是**异步**的，要跑过事件循环才到达；
  若只靠 changeEvent，"切换已完成"与"界面已刷新"之间存在窗口期，调用方
  返回时界面可能还是旧语言 (曾导致测试只断言 current_language 字段就误判通过)。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QLocale, QTranslator
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)


class I18nManager:
    _translator: Optional[QTranslator] = None
    _current_lang: str = "zh_CN"
    _translations_dir: Path = Path(__file__).parent.parent / "i18n"

    @classmethod
    def init(cls, app: QApplication, language: Optional[str] = None):
        """初始化翻译。

        语言来源优先级:
          1. 显式传入的 language (来自 antenna_config.json 的用户设定)
          2. 系统 locale (仅当未传入或传入值无对应 .qm 时)

        传入值没有对应翻译文件时回退系统 locale — 配置文件被改成
        非法值时界面仍能拿到合理翻译，而不是退化成无翻译状态。
        """
        if language and not (cls._translations_dir / f"app_{language}.qm").exists():
            language = None

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
        """切换语言并同步刷新界面文字。

        必须先校验 .qm 存在再动现状: 若先 removeTranslator 才发现文件缺失,
        旧翻译器已卸、新的没装, 界面会静默退化为「无翻译」, 而 _current_lang
        仍报旧值 —— 调用方以为一切正常。
        """
        qm_path = cls._translations_dir / f"app_{language}.qm"
        if not qm_path.exists():
            log.warning("翻译文件缺失, 保持当前语言 %s: %s",
                        cls._current_lang, qm_path)
            return

        # 移除旧翻译器。QTranslator 不设 parent → 置 None 后由 Python GC
        # 回收其 C++ 对象。不要用 deleteLater(): 那会留下「Python 包装器仍在、
        # C++ 对象已删」的悬垂引用, 正是本类要避免的崩溃模式。
        if cls._translator is not None:
            app.removeTranslator(cls._translator)
            cls._translator = None

        # 不再 QTranslator(app): 以 app 为 parent 会让每次切换都留下一个
        # C++ 子对象不销毁 (持续泄漏)。
        translator = QTranslator()
        translator.load(str(qm_path))
        app.installTranslator(translator)
        cls._translator = translator
        cls._current_lang = language

    @classmethod
    def current_language(cls) -> str:
        return cls._current_lang
