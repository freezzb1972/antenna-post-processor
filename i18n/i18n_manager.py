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

import json
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

    # 反查表索引 (由 _load_table 惰性构建; None = 尚未加载)
    _table: Optional[dict] = None      # {context: {源串: 英文}}
    _reverse: dict = {}                # {context: {英文: 源串}} — 精确, 无歧义
    _reverse_flat: dict = {}           # {英文: [源串...]}       — 跨 context 兜底
    _forward_flat: dict = {}           # {源串: 英文}            — 跨 context 兜底

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

    # ==================================================================
    # 反查表 (运行时语言切换用)
    # ==================================================================

    @classmethod
    def _load_table(cls) -> bool:
        """惰性加载 trans_table.json 并建索引。

        缺文件/解析失败时降级返回 False 并置空表 —— 运行时切换退化为单向,
        但绝不因为一个数据文件缺失而崩溃 (开发环境未跑生成脚本是常见情形)。
        """
        if cls._table is not None:
            return bool(cls._table)
        path = cls._translations_dir / "trans_table.json"
        try:
            cls._table = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("反查表不可用, 运行时切换将只能单向刷新: %s", e)
            cls._table = {}
            return False

        rev: dict = {}
        rev_flat: dict = {}
        fwd_flat: dict = {}
        for ctx, entries in cls._table.items():
            per_ctx: dict = {}
            for src, en in entries.items():
                # 同 context 内若两源串译成同一英文, 反查有歧义 (实测当前为 0,
                # 这里是未来译文改动引入碰撞时的告警哨兵)
                if en in per_ctx and per_ctx[en] != src:
                    log.warning("同 context 内反向碰撞, 反查可能失准: [%s] %r <- %r / %r",
                                ctx, en, per_ctx[en], src)
                per_ctx.setdefault(en, src)
                fwd_flat.setdefault(src, en)
                bucket = rev_flat.setdefault(en, [])
                if src not in bucket:
                    bucket.append(src)
            rev[ctx] = per_ctx
        cls._reverse, cls._reverse_flat, cls._forward_flat = rev, rev_flat, fwd_flat
        return True

    @classmethod
    def to_source(cls, text: str, context: str, from_lang: str):
        """把「当前语言下的文本」还原成源串。无法唯一确定时返回 None。

        消解顺序 (实测有效): ① zh_CN 恒等 → 文本即源串, 永不碰撞;
        ② context 内反查 (实测同 context 无碰撞, 精确); ③ 跨 context 兜底,
        仅当候选唯一才采用, ≥2 则放弃并 debug (宁可不动, 不可乱写)。
        """
        if not text:
            return None
        if from_lang == "zh_CN":       # 恒等翻译: 文本就是源串
            return text
        if not cls._load_table():
            return None
        hit = cls._reverse.get(context, {}).get(text)
        if hit is not None:
            return hit
        cands = cls._reverse_flat.get(text)
        if cands and len(cands) == 1:
            return cands[0]
        if cands:
            log.debug("反查歧义, 跳过该控件: %r (候选 %s)", text, cands)
        return None

    @classmethod
    def from_source(cls, source: str, context: str, to_lang: str) -> str:
        """源串 → 目标语言文本。查不到回退源串 (zh_CN 下源串即译文)。"""
        if not source or to_lang == "zh_CN":
            return source
        if not cls._load_table():
            return source
        return (cls._table.get(context, {}).get(source)
                or cls._forward_flat.get(source)
                or source)
