"""
图表标题 (泛化, 类别驱动 + 用户可覆盖)
=====================================
标题由 ChartInstance 的 category + params 驱动, 默认模板按类别(A/B/C/Z)。
占位符从实例通用提取, 缺失优雅降级(SafeDict)。用户可:
  (a) 逐实例覆盖 inst.title (Word 布局清单编辑)
  (b) 全局改类别默认模板 (config/chart_titles.json)

占位符: {antenna} {freq} {param} {cut} {angles} {angle_axis} {unit} {N} {angle_suffix}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── (b) 全局默认: 类别 → 英文模板 ──
DEFAULT_TITLE_BY_CATEGORY: dict[str, str] = {
    "A": "{antenna} {freq} — {param} 3D Pattern",
    "B": "{antenna} — {param} vs Frequency{angle_suffix}",
    "C": "{antenna} {freq} — Elevation {param}{angle_suffix}",
    "Z": "{antenna} {freq} — Azimuth {param}{angle_suffix}",
}

PLACEHOLDERS = ["antenna", "freq", "param", "cut", "angles",
                "angle_axis", "unit", "N", "angle_suffix"]

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "chart_titles.json"

# param 关键词 → 英文标签 (从 parent_type/image_key/params 推断)
_PARAM_LABELS: dict[str, str] = {
    "gain": "Gain", "eirp": "EIRP", "ar": "AR", "etheta": "Eθ", "ephi": "Eφ",
    "rhcp": "RHCP", "lhcp": "LHCP", "cp_xpi": "CP-XPI", "cpxpi": "CP-XPI",
    "eff": "Efficiency", "dir": "Directivity", "lag": "LAG", "trp": "TRP",
    "nhprp": "NHPRP",
}


class _SafeDict(dict):
    """format_map 用: 缺失占位符返回空串, 模板不崩。"""
    def __missing__(self, key):
        return ""


# ── (b) 默认模板读写 (GUI 可编辑, config/chart_titles.json 覆盖内置默认) ──
def load_default_templates() -> dict[str, str]:
    d = dict(DEFAULT_TITLE_BY_CATEGORY)
    try:
        if _CONFIG_PATH.exists():
            user = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            for k, v in user.items():
                if k in d and isinstance(v, str) and v.strip():
                    d[k] = v
    except Exception:
        pass
    return d


def save_default_templates(templates: dict[str, str]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in templates.items() if k in DEFAULT_TITLE_BY_CATEGORY}
    _CONFIG_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2),
                            encoding="utf-8")


def _cat_value(inst) -> str:
    c = getattr(inst, "category", "")
    return c.value if hasattr(c, "value") else str(c)


def _param_label(inst) -> str:
    """从 params['param'] / parent_type / image_key 推断英文参数名。"""
    p = getattr(inst, "params", None) or {}
    raw = str(p.get("param", "")).lower()
    src = raw or str(getattr(inst, "parent_type", "")).lower() or str(getattr(inst, "image_key", "")).lower()
    for kw, label in _PARAM_LABELS.items():
        if kw in src:
            return label
    return raw.upper() if raw else "Gain"


def _angles_str(inst) -> str:
    p = getattr(inst, "params", None) or {}
    angles = p.get("angles")
    if not angles:
        return ""
    return "/".join(f"{float(a):g}" for a in angles)


def title_context(inst, freq: float | None, antenna: str) -> dict[str, Any]:
    """从实例 + 频率通用提取占位符 (能算多少给多少)。"""
    cat = _cat_value(inst)
    p = getattr(inst, "params", None) or {}
    cut = {"A": "3D", "C": "Elevation", "Z": "Azimuth"}.get(cat, "")
    # 方位面(Z): 沿 φ 画, 曲线按 θ 分 → 切面角度是 θ; 俯仰面(C): 沿 θ 画, 切面角度是 φ
    angle_axis = "θ" if cat == "Z" else ("φ" if cat == "C" else "")
    angles = _angles_str(inst)
    angle_suffix = f" ({angle_axis}={angles}°)" if angles and angle_axis else ""
    ctx = {
        "antenna": antenna or "",
        "freq": f"{freq:.0f} MHz" if freq is not None else "",
        "param": _param_label(inst),
        "cut": cut,
        "angles": angles,
        "angle_axis": angle_axis,
        "unit": str(p.get("unit", "")),
        "N": str(p.get("N", "")),
        "angle_suffix": angle_suffix,
    }
    return ctx


def _clean(text: str) -> str:
    """清理空占位符留下的多余空格/破折号。"""
    import re
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*—\s*$", "", text)           # 结尾孤立破折号
    text = re.sub(r"^\s*—\s*", "", text)           # 开头孤立破折号
    text = re.sub(r"—\s*—", "—", text)             # 连续破折号
    return text.strip(" —")


def build_title(inst, freq: float | None = None, antenna: str = "",
                defaults: dict[str, str] | None = None) -> str:
    """构建一张图的标题。inst.title(用户覆盖)优先, 否则用类别默认模板。"""
    tpl = (getattr(inst, "title", "") or "").strip()
    if not tpl:
        d = defaults if defaults is not None else load_default_templates()
        tpl = d.get(_cat_value(inst), "{antenna} {freq} — {param}")
    return _clean(tpl.format_map(_SafeDict(title_context(inst, freq, antenna))))
