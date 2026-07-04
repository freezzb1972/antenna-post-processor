"""
LLM Tag 推荐器
==============
调用已配置的大模型 API，为模板中的文本位置推荐最佳 SDT tag。

用法:
    from src.llm_tagger import suggest_tags_with_llm
    suggestions = suggest_tags_with_llm(positions, registry)
"""

from __future__ import annotations

import json
from typing import Any


# ═══════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一个天线测试报告模板分析助手。你的任务是:
1. 阅读模板中某个位置的示例文本
2. 从给定的 SDT Tag 注册表中选择最匹配的 tag
3. 如果注册表中没有合适的，建议一个新的 tag 名称

## SDT Tag 命名规范
- meta_xxx: 元数据 (客户/项目/日期等)
- data_xxx: 单值数据参数
- table_xxx: 数据表格
- img_xxx: 图片/图表
- chart_xxx: 曲线/图形

## 输出格式
严格输出 JSON 数组，每个元素:
{
  "index": <position index, 整数>,
  "tag": "<建议的 SDT tag>",
  "confidence": <0.0-1.0>,
  "reason": "<简短理由>"
}
只输出 JSON，不要任何其他文字。"""


def build_tag_prompt(positions: list, registry_snippet: str) -> str:
    """构建单次 LLM 调用的 prompt。"""
    items = []
    for p in positions[:20]:  # 一次最多 20 个
        items.append({
            "index": p.index,
            "type": p.pos_type,
            "location": p.location,
            "sample_text": p.sample_text[:150],
        })
    return f"""## SDT Tag 注册表 (部分)
{registry_snippet}

## 需要匹配的位置
{json.dumps(items, ensure_ascii=False, indent=2)}

请为每个位置推荐最合适的 SDT tag。"""


# ═══════════════════════════════════════════════════════════════
# 规则匹配 (优先，不用 LLM)
# ═══════════════════════════════════════════════════════════════

def rule_based_suggest(positions: list) -> int:
    """用内置规则自动匹配 tag。返回成功匹配的数量。"""
    from src.docx_exporter import DocxTemplateFiller
    registry = DocxTemplateFiller.load_registry()

    matched = 0
    for p in positions:
        tag = _match_by_rules(p, registry)
        if tag:
            p.suggested_tag = tag
            matched += 1
    return matched


def _match_by_rules(p, registry: dict) -> str:
    """单条规则匹配。"""
    text = p.sample_text.lower()

    # Table matching
    if p.pos_type.startswith("table"):
        if "frequency" in text or "频率" in text or "mhz" in text:
            if any(w in text for w in ["gain", "增益", "lag", "pkgain"]):
                return "table_gain"
            if any(w in text for w in ["ar", "axial", "轴比"]):
                return "table_ar"
            if any(w in text for w in ["efficiency", "效率"]):
                return "table_efficiency"
            if "directivity" in text or "方向性" in text:
                return "table_directivity"
            if "trp" in text or "nhprp" in text:
                return "table_trp"
        if p.row_count <= 8:
            # Small table → likely metadata
            for kw, tag in [("合同", "meta_contract_no"), ("客户", "meta_customer"),
                            ("项目", "meta_project"), ("天线", "meta_antenna_model"),
                            ("测试", "meta_test_standard"), ("批准", "meta_contract_no"),
                            ("编撰", "meta_test_engineer"), ("审阅", "meta_reviewer")]:
                if kw in text:
                    return tag

    # Image matching
    if p.pos_type == "image":
        for kw, tag in [("3d", "img_3d_gain"), ("gain", "img_3d_gain"),
                        ("ar", "img_3d_ar"), ("polar", "img_azimuth_gain"),
                        ("azimuth", "img_azimuth_gain"), ("方向图", "img_3d_gain")]:
            if kw in text:
                return tag
        return "img_3d_gain"

    return ""


# ═══════════════════════════════════════════════════════════════
# LLM API 调用 (兜底)
# ═══════════════════════════════════════════════════════════════

def suggest_tags_with_llm(positions: list, api_base: str = "",
                          api_key: str = "", model: str = "") -> int:
    """用 LLM 为未匹配的位置推荐 tag。返回成功匹配的数量。"""
    unmatched = [p for p in positions if not p.suggested_tag]
    if not unmatched:
        return 0

    from src.docx_exporter import DocxTemplateFiller
    registry = DocxTemplateFiller.load_registry()
    registry_snippet = json.dumps(dict(list(registry.items())[:30]),
                                  ensure_ascii=False, indent=2)

    if not api_base:
        from src.config_manager import get_config_manager
        cfg = get_config_manager()
        llm = getattr(cfg.config, 'llm', None)
        if llm:
            api_base = llm.api_base
            api_key = getattr(llm, '_api_key', '')
            model = llm.model

    if not api_base or not api_key:
        return 0

    prompt = build_tag_prompt(unmatched, registry_snippet)

    try:
        import urllib.request
        req = urllib.request.Request(
            api_base.rstrip('/') + '/v1/messages',
            data=json.dumps({
                "model": model or "claude-sonnet-4-6",
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
        )
        resp = urllib.request.urlopen(req, timeout=30)
        body = json.loads(resp.read())
        content = body.get("content", [{}])[0].get("text", "")
        # Parse JSON from response
        import re
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            suggestions = json.loads(json_match.group())
            for s in suggestions:
                idx = s.get("index")
                tag = s.get("tag", "")
                if idx is not None and tag:
                    for p in positions:
                        if p.index == idx:
                            p.suggested_tag = tag
                            break
            return len(suggestions)
    except Exception:
        pass

    return 0
