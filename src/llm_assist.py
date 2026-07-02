"""
LLM-assisted template recognition & file matching.

Provides a silent fallback when rule-based template parameter detection
or sheet-file matching yields low confidence.  All public methods log
activity (if a logger is given) but never raise — every failure degrades
to an empty result, so the caller's pipeline is never blocked.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

Logger = Optional[Callable[[str], None]]


@dataclass
class LLMSettings:
    """LLM 辅助识别设置 — 独立于 RAG 问答的设置。"""

    enabled: bool = False
    mode: str = "cloud"  # "cloud" | "local"
    api_base: str = "https://api.anthropic.com/v1/messages"
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    local_endpoint: str = "http://localhost:11434"

    @classmethod
    def from_qsettings(cls) -> LLMSettings:
        """从统一配置文件加载 LLM 设置。"""
        from src.config_manager import get_config_manager
        mgr = get_config_manager()
        cfg = mgr.config.ai
        return cls(
            enabled=cfg.enabled,
            mode=cfg.mode,
            api_base=cfg.api_base,
            api_key=mgr.get_api_key("ai"),
            model=cfg.model,
            local_endpoint=cfg.local_endpoint,
        )

    def save(self) -> None:
        """保存 LLM 设置到统一配置文件。"""
        from src.config_manager import get_config_manager
        mgr = get_config_manager()
        mgr.config.ai.enabled = self.enabled
        mgr.config.ai.mode = self.mode
        mgr.config.ai.api_base = self.api_base
        mgr.set_api_key("ai", self.api_key)
        mgr.config.ai.model = self.model
        mgr.config.ai.local_endpoint = self.local_endpoint
        mgr.save()


# ---------------------------------------------------------------------------
# LLM 辅助识别 — 兜底规则匹配失败时调用 LLM 提供建议
# ---------------------------------------------------------------------------


class LLMAssist:
    """静默的 LLM 辅助识别。

    所有公开方法均遵从以下合约:
      * 仅在 ``LLMSettings.from_qsettings().enabled is True`` 时执行。
      * 通过 ``logger`` 参数输出活动记录 (可选的 ``self._log`` 兼容)。
      * 失败时返回空结果, 不抛出异常, 不阻塞调用方。
    """

    # ── 模板参数补全 ──────────────────────────────────────────────

    @staticmethod
    def suggest_template_params(template_path: str, logger: Logger = None) -> set:
        """模板规则匹配检测到 <2 类型时, 调用 LLM 辅助识别。

        Args:
            template_path: 模板 Excel 文件路径。
            logger: 可选日志回调 (如 ``self._log``)。

        Returns:
            LLM 建议的参数 key 集合 (可能为空)。
        """
        settings = LLMSettings.from_qsettings()
        if not settings.enabled:
            return set()

        try:
            if logger:
                logger(
                    f"🤖 LLM 辅助: 正在分析模板参数… (model={settings.model})"
                )
            # ── 预留 LLM 调用点 ──
            # 可在此处调用 help_engine / anthropic / ollama SDK
            if logger:
                logger("🤖 LLM 辅助: 模板参数分析完成 (占位)")
            return set()
        except Exception as e:
            if logger:
                logger(f"🤖 LLM 辅助失败（静默降级）: {e}")
            return set()

    # ── 工作表 ↔ 文件匹配补全 ──────────────────────────────────────

    @staticmethod
    def suggest_file_matches(
        sheet_names: list,
        data_files: list,
        current_matches: dict | None = None,
        logger: Logger = None,
    ) -> dict:
        """对自动匹配后仍未匹配的工作表/文件, 使用 LLM 给出建议。

        Args:
            sheet_names: 模板中的所有工作表名。
            data_files: 所有数据文件路径。
            current_matches: 已有的 ``{sheet_name: file_path}`` 匹配。
            logger: 可选日志回调。

        Returns:
            补充的匹配建议 ``{sheet_name: file_path}`` (可能为空)。
        """
        settings = LLMSettings.from_qsettings()
        if not settings.enabled:
            return {}

        current = current_matches or {}
        unmatched_sheets = [s for s in sheet_names if s not in current]
        unmatched_files = [
            f for f in data_files if f not in current.values()
        ]
        if not unmatched_sheets or not unmatched_files:
            return {}

        try:
            if logger:
                logger(
                    f"🤖 LLM 辅助: 尝试匹配 {len(unmatched_sheets)} 个工作表 ↔ "
                    f"{len(unmatched_files)} 个文件… (model={settings.model})"
                )
            # ── 预留 LLM 调用点 ──
            if logger:
                logger("🤖 LLM 辅助: 文件匹配分析完成 (占位)")
            return {}
        except Exception as e:
            if logger:
                logger(f"🤖 LLM 辅助失败（静默降级）: {e}")
            return {}
