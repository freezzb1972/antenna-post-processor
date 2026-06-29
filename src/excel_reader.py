"""
Excel 模板读取器
================
读取输出模板 Excel，解析所有 Sheet 的结构信息：
  - 列头定义（Frequency / Directivity / LAG 角度等）
  - 频点列表
  - 自动检测 LAG 需求
"""

from __future__ import annotations

import json
import os
import sys
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import openpyxl

from .lag_config import (LagConfig, normalize_header,
                         _RE_LAG_RANGE, _RE_LAG_RANGE_NO_PREFIX,
                         _RE_LAG_SINGLE, _RE_LAG_SINGLE_NO_PREFIX)


# ---------------------------------------------------------------------------
# 列头规范化 & 分类 (从 lag_config.py 移入 — 它们只被模板解析使用)
# ---------------------------------------------------------------------------

def _normalize_key(name: str) -> str:
    """将列头转成小写无空格键，用于固定列匹配。"""
    return re.sub(r"[^a-z%％()db]+", "", name.lower())


# ═══════════════════════════════════════════════════════════════
# JSON 列头模式加载器 — 用户可编辑的外部配置
# ═══════════════════════════════════════════════════════════════

_COLUMN_PATTERNS: Optional[List[dict]] = None


def _load_column_patterns() -> List[dict]:
    """加载 config/column_patterns.json，若文件不存在则返回空列表。"""
    global _COLUMN_PATTERNS
    if _COLUMN_PATTERNS is not None:
        return _COLUMN_PATTERNS

    candidates = []
    # 打包模式: EXE 同目录 config/ 优先（用户外部编辑，可写入）
    if getattr(sys, 'frozen', False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), "config", "column_patterns.json"))
    # 内嵌默认值 (MEIPASS) 或开发模式项目根目录
    candidates.append(os.path.join(os.path.dirname(__file__), "..", "config", "column_patterns.json"))
    # 当前工作目录 fallback
    candidates.append(os.path.join(os.getcwd(), "config", "column_patterns.json"))
    for candidate in candidates:
        path = os.path.normpath(candidate)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _COLUMN_PATTERNS = data.get("patterns", [])
                return _COLUMN_PATTERNS
            except (json.JSONDecodeError, OSError):
                pass

    _COLUMN_PATTERNS = []
    return _COLUMN_PATTERNS


def _classify_by_json_patterns(raw_header: str) -> Optional[str]:
    """用 config/column_patterns.json 中的规则匹配列头（唯一分类器）。

    匹配优先级（按 JSON 顺序，先匹配者胜）：
      1. "regex" — 正则匹配
      2. "exact" — 精确匹配 compact form
      3. "keywords" — 所有关键词都出现 (AND)
      4. "negate" — 排除规则 (任一匹配则跳过)
    """
    patterns = _load_column_patterns()
    if not patterns:
        return None

    norm = normalize_header(raw_header).lower()
    compact = _normalize_key(raw_header)

    for entry in patterns:
        keywords = entry.get("keywords", [])
        exact_list = entry.get("exact", [])
        negate_words = entry.get("negate", [])
        regex_str = entry.get("regex", "")

        matched = False

        # ── Regex ──
        if regex_str:
            if re.search(regex_str, norm, re.IGNORECASE):
                matched = True

        # ── 精确匹配 ──
        if not matched and exact_list:
            for ex in exact_list:
                if ex.lower() == compact:
                    matched = True
                    break

        # ── 关键词 AND 匹配 ──
        if not matched and keywords:
            matched = True
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower not in norm and kw_lower not in compact:
                    matched = False
                    break

        if not matched:
            continue

        # ── 排除词 ──
        blocked = False
        for nkw in negate_words:
            if nkw.lower() in norm or nkw.lower() in compact:
                blocked = True
                break
        if blocked:
            continue

        return entry["col_type"]

    return None


def reload_column_patterns():
    """强制重新加载 JSON 模式（对话框保存后调用）。"""
    global _COLUMN_PATTERNS
    _COLUMN_PATTERNS = None
    _load_column_patterns()


def is_frequency_column(header: str) -> bool:
    h = _normalize_key(header)
    return "frequency" in h or h in ("freq", "f", "f(mhz)", "freq(mhz)")


def is_directivity_column(header: str) -> bool:
    h = _normalize_key(header)
    return "directivity" in h or h in ("dir", "d(dbi)")


def is_efficiency_column(header: str) -> bool:
    h = _normalize_key(header)
    return "efficiency" in h


def is_gain_column(header: str) -> bool:
    """峰值增益列（不是 LAG / Average Gain / Gain at Theta / Peak EIRP / PKGain）。

    注意: PKGain / Peak Gain / Peak EIRP 由 is_peak_eirp_column() 处理。
    """
    h = _normalize_key(header)
    if "average" in h:
        return False
    if "theta" in h:
        return False
    if "pkgain" in h or "peakgain" in h or "peakeirp" in h:
        return False  # 交由 is_peak_eirp_column() 检测
    return h.startswith("gain") or h in ("g(dbi)", "pk")


def is_trp_column(header: str) -> bool:
    """TRP 列 (含 'Tot. Rad. Pwr.' 别名)."""
    h = header.lower()
    if "trp" in h and "nhprp" not in h:
        return True
    return "total radiated power" in h or "tot. rad. pwr." in h


def is_nhprp_45_column(header: str) -> bool:
    """NHPRP +/-45 列。"""
    h = header.lower()
    return ("nhprp" in h or "nhprp" in h) and "45" in h


def is_nhprp_30_column(header: str) -> bool:
    """NHPRP +/-30 列。"""
    h = header.lower()
    return ("nhprp" in h or "nhprp" in h) and "30" in h


def is_peak_eirp_column(header: str) -> bool:
    """Peak EIRP / PKGain / Peak Gain 列。"""
    h = _normalize_key(header)
    return "peakeirp" in h or "eirppeak" in h or "pkgain" in h or "peakgain" in h


def is_ar_single_column(header: str) -> bool:
    """AR 单角度列: 'AR at Theta=30' → ar_single_30"""
    h = header.lower()
    return ("ar" in h and "theta" in h and "~" not in h) or ("axial" in h and "theta" in h and "~" not in h)


def is_ar_range_column(header: str) -> bool:
    """AR 范围列: 'AR at Theta=0~70' → ar_range_0_70"""
    h = header.lower()
    return ("ar" in h and "~" in h) or ("axial" in h and "~" in h)


def is_nhprp_225_column(header: str) -> bool:
    """NHPRP +/-22.5 列 (Pi/8)."""
    h = header.lower()
    if "nhprp" not in h:
        return False
    return "22.5" in h or "pi/8" in h or "π/8" in h


def is_uh_prp_column(header: str) -> bool:
    """Upper Hemisphere PRP."""
    h = header.lower()
    return "upper" in h and "hem" in h and "prp" in h


def is_lh_prp_column(header: str) -> bool:
    """Lower Hemisphere PRP."""
    h = header.lower()
    return "lower" in h and "hem" in h and "prp" in h


def detect_ratio_column_type(header: str) -> Optional[str]:
    """检测比率列类型，返回带 db/pct 后缀的 column type。

    Returns:
        None (非比率列) 或 column type 如 "nhprp45_ratio", "uh_ratio" 等。
    """
    h = header.lower()
    if "ratio" not in h:
        return None
    base = None
    if "nhprp4" in h or "nhprp45" in h or "nhprp+/-45" in h or "nhprp+-45" in h:
        base = "nhprp45_ratio"
    elif "nhprp3" in h or "nhprp30" in h or "nhprp+/-30" in h or "nhprp+-30" in h:
        base = "nhprp30_ratio"
    elif "nhprp2" in h or "nhprp225" in h or "nhprp22.5" in h or "nhprp+/-22.5" in h:
        base = "nhprp225_ratio"
    elif "upper" in h and "hem" in h:
        base = "uh_ratio"
    elif "lower" in h and "hem" in h:
        base = "lh_ratio"
    if base:
        # 检测 dB/pct 后缀
        if "%" in header or "pct" in h:
            return base + "_pct"
        elif "db" in h:
            return base + "_db"
        return base
    return None


def is_boresight_phi_column(header: str) -> bool:
    """Boresight Phi 列。"""
    h = header.lower()
    return "boresight" in h and "phi" in h


def is_boresight_theta_column(header: str) -> bool:
    """Boresight Theta 列。"""
    h = header.lower()
    return "boresight" in h and ("theta" in h or "th." in h or "θ" in h)


def is_max_power_column(header: str) -> bool:
    """Maximum Power 列。"""
    h = header.lower()
    return ("maximum" in h or "max" in h) and "power" in h and "average" not in h


def is_min_power_column(header: str) -> bool:
    """Minimum Power 列。"""
    h = header.lower()
    return ("minimum" in h or "min" in h) and "power" in h and "average" not in h


def is_avg_gain_column(header: str) -> bool:
    """Average Gain 列。"""
    h = header.lower()
    return ("average" in h or "avg" in h) and "gain" in h and "at" not in h


def is_avg_power_column(header: str) -> bool:
    """Average Power 列。"""
    h = header.lower()
    return ("average" in h or "avg" in h) and "power" in h


def is_xpi_boresight_column(header: str) -> bool:
    """XPI Boresight 列。"""
    h = header.lower()
    return "xpi" in h and "boresight" in h


def is_xpi_mean_column(header: str) -> bool:
    """XPI Mean 列。"""
    h = header.lower()
    return "xpi" in h and "mean" in h


def is_xpi_min_column(header: str) -> bool:
    """XPI Min 列。"""
    h = header.lower()
    return "xpi" in h and "min" in h and "mean" not in h


def is_total_efficiency_column(header: str) -> bool:
    """Total Efficiency 列。"""
    h = header.lower()
    return "total" in h and "efficiency" in h


def is_mismatch_loss_column(header: str) -> bool:
    """Mismatch Loss 列。"""
    h = header.lower()
    return "mismatch" in h and "loss" in h


def is_pc_theta_column(header: str) -> bool:
    """Phase Center Theta 列。"""
    h = header.lower()
    return ("pc" in h or "phase center" in h) and ("theta" in h or "θ" in h)


def is_pc_phi_column(header: str) -> bool:
    """Phase Center Phi 列。"""
    h = header.lower()
    return ("pc" in h or "phase center" in h) and "phi" in h


@dataclass
class ColumnInfo:
    """单列信息。"""
    col_letter: str          # 列字母，如 "B"
    col_index: int           # 1-based 列号
    raw_header: str          # 原始列头文本
    normalized_header: str   # 规范化列头
    col_type: str            # "frequency" | "directivity" | "efficiency_pct"
                             # | "efficiency_db" | "total_efficiency_pct"
                             # | "total_efficiency_db" | "gain" | "lag_single"
                             # | "lag_range" | "xpi_boresight" | "xpi_mean"
                             # | "xpi_min" | "mismatch_loss_db"
                             # | "pc_theta_mm" | "pc_phi_mm" | "unknown"


@dataclass
class SheetInfo:
    """一个工作表的完整结构信息。"""
    name: str
    header_row: int                    # 列头所在行号
    data_start_row: int                # 数据起始行号
    data_end_row: int                  # 数据结束行号
    columns: List[ColumnInfo] = field(default_factory=list)
    frequencies: List[float] = field(default_factory=list)
    lag_config: LagConfig = field(default_factory=LagConfig)
    ar_config: LagConfig = field(default_factory=LagConfig)  # AR 角度配置
    theta_range: Optional[str] = None  # e.g., "0-110°"


def read_template(template_path: str) -> List[SheetInfo]:
    """读取输出模板，返回所有工作表信息。

    会自动跳过纯元数据的 Sheet（无 Frequency 列）。
    """
    wb = openpyxl.load_workbook(template_path, data_only=True)
    sheets: List[SheetInfo] = []

    for ws in wb.worksheets:
        info = _parse_sheet(ws)
        if info is not None:
            sheets.append(info)

    wb.close()
    return sheets


def _classify_by_builtin(raw: str, norm: str) -> Optional[str]:
    """内置函数检测链（不含 JSON 匹配），用于 JSON 冲突校验。"""
    if is_frequency_column(raw):        return "frequency"
    if is_directivity_column(raw):      return "directivity"
    if is_total_efficiency_column(raw):
        if "%" in norm or "％" in norm or "pct" in norm.lower():
            return "total_efficiency_pct"
        if "db" in norm.lower():
            return "total_efficiency_db"
        return "total_efficiency_pct"
    if is_efficiency_column(raw):
        if "%" in norm or "％" in norm or "pct" in norm.lower():
            return "efficiency_pct"
        if "db" in norm.lower():
            return "efficiency_db"
        return "efficiency_pct"
    if is_gain_column(raw):             return "gain"
    if is_trp_column(raw):              return "trp"
    if is_nhprp_45_column(raw):         return "nhprp_45"
    if is_nhprp_30_column(raw):         return "nhprp_30"
    if is_peak_eirp_column(raw):        return "peak_eirp"
    if is_ar_single_column(raw):        return "ar_single"
    if is_ar_range_column(raw):         return "ar_range"
    if is_nhprp_225_column(raw):        return "nhprp_225"
    if is_uh_prp_column(raw):           return "uh_prp"
    if is_lh_prp_column(raw):           return "lh_prp"
    if is_boresight_phi_column(raw):    return "boresight_phi"
    if is_boresight_theta_column(raw):  return "boresight_theta"
    if is_max_power_column(raw):        return "max_power"
    if is_min_power_column(raw):        return "min_power"
    if is_avg_gain_column(raw):         return "avg_gain"
    if is_avg_power_column(raw):        return "avg_power"
    if is_xpi_boresight_column(raw):    return "xpi_boresight"
    if is_xpi_mean_column(raw):         return "xpi_mean"
    if is_xpi_min_column(raw):          return "xpi_min"
    if is_mismatch_loss_column(raw):    return "mismatch_loss_db"
    if is_pc_theta_column(raw):         return "pc_theta_mm"
    if is_pc_phi_column(raw):           return "pc_phi_mm"
    return None


def _parse_sheet(ws) -> Optional[SheetInfo]:
    """解析单个 Sheet。返回 None 表示非天线数据 Sheet（无 Frequency 列）。"""
    name = ws.title
    max_row = ws.max_row or 100
    max_col = ws.max_column or 20

    # ---- 扫描行 ----
    header_row = None
    data_start_row = None
    data_end_row = max_row

    for row_idx in range(1, min(max_row + 1, 200)):
        row_values = [_cell_str(ws.cell(row_idx, c)) for c in range(1, max_col + 1)]

        # 寻找 Frequency 列所在行 → 列头行
        for c, val in enumerate(row_values):
            if is_frequency_column(val):
                header_row = row_idx
                break

        if header_row is not None:
            break

    if header_row is None:
        # 无 Frequency 列 → 不是天线数据 Sheet
        return None

    # ---- 解析列头 ----
    columns: List[ColumnInfo] = []
    lag_headers: List[str] = []
    ar_headers: List[str] = []

    for c in range(1, max_col + 1):
        raw = _cell_str(ws.cell(header_row, c))
        if not raw:
            continue
        norm = normalize_header(raw)
        col_letter = openpyxl.utils.get_column_letter(c)

        # 分类 — 内置函数检测优先，JSON 仅做补充覆盖
        builtin_type = _classify_by_builtin(raw, norm)
        json_type = _classify_by_json_patterns(raw)
        if json_type is not None:
            # JSON 覆盖内置 → 检测冲突并警告
            if builtin_type is not None and json_type != builtin_type:
                import sys
                print(f"[WARNING] column_patterns.json '{json_type}' overrides "
                      f"builtin '{builtin_type}' for header '{raw}' — "
                      f"fix JSON to match or remove the rule", file=sys.stderr)
            ctype = json_type
        elif builtin_type is not None:
            ctype = builtin_type
        elif is_frequency_column(raw):
            ctype = "frequency"
        elif is_directivity_column(raw):
            ctype = "directivity"
        elif is_total_efficiency_column(raw):
            # 区分 Total Efficiency(%) 和 Total Efficiency(dB)
            if "%" in norm or "％" in norm or "pct" in norm.lower():
                ctype = "total_efficiency_pct"
            elif "db" in norm.lower():
                ctype = "total_efficiency_db"
            else:
                ctype = "total_efficiency_pct"  # 默认当作 %
        elif is_efficiency_column(raw):
            # 区分 Efficiency(%) 和 Efficiency(dB)
            if "%" in norm or "％" in norm or "pct" in norm.lower():
                ctype = "efficiency_pct"
            elif "db" in norm.lower():
                ctype = "efficiency_db"
            else:
                ctype = "efficiency_pct"  # 默认当作 %
        elif is_gain_column(raw):
            ctype = "gain"
        elif is_trp_column(raw):
            ctype = "trp"
        elif is_nhprp_45_column(raw):
            ctype = "nhprp_45"
        elif is_nhprp_30_column(raw):
            ctype = "nhprp_30"
        elif is_peak_eirp_column(raw):
            ctype = "peak_eirp"
        elif is_ar_single_column(raw):
            ctype = "ar_single"
        elif is_ar_range_column(raw):
            ctype = "ar_range"
        elif is_nhprp_225_column(raw):
            ctype = "nhprp_225"
        elif is_uh_prp_column(raw):
            ctype = "uh_prp"
        elif is_lh_prp_column(raw):
            ctype = "lh_prp"
        else:
            # 比率列 (NHPRP4 / TRP Ratio → nhprp45_ratio_db 等)
            ratio_type = detect_ratio_column_type(raw)
            if ratio_type is not None:
                ctype = ratio_type
            elif is_boresight_phi_column(raw):
                ctype = "boresight_phi"
            elif is_boresight_theta_column(raw):
                ctype = "boresight_theta"
            elif is_max_power_column(raw):
                ctype = "max_power"
            elif is_min_power_column(raw):
                ctype = "min_power"
            elif is_avg_gain_column(raw):
                ctype = "avg_gain"
            elif is_avg_power_column(raw):
                ctype = "avg_power"
            elif is_xpi_boresight_column(raw):
                ctype = "xpi_boresight"
            elif is_xpi_mean_column(raw):
                ctype = "xpi_mean"
            elif is_xpi_min_column(raw):
                ctype = "xpi_min"
            elif is_mismatch_loss_column(raw):
                ctype = "mismatch_loss_db"
            elif is_pc_theta_column(raw):
                ctype = "pc_theta_mm"
            elif is_pc_phi_column(raw):
                ctype = "pc_phi_mm"
            elif _RE_LAG_RANGE.search(norm) or _RE_LAG_RANGE_NO_PREFIX.search(norm):
                ctype = "lag_range"
            elif _RE_LAG_SINGLE.search(norm) or _RE_LAG_SINGLE_NO_PREFIX.search(norm):
                ctype = "lag_single"
            elif "average" in norm.lower() and "gain" in norm.lower():
                # "Average Gain (dB)" ≈ LAG — 从列头尝试提取角度范围
                _avg_range = re.search(r"(\d+)\s*[-–—~]\s*(\d+)\s*deg", norm)
                if _avg_range:
                    ctype = "lag_range"
                else:
                    ctype = "gain_avg"
            elif "gain" in norm.lower() and "theta" in norm.lower():
                # "Gain at Theta=0~70 (dB)" → LAG range
                _t_range = re.search(r"(\d+)\s*[-–—~]\s*(\d+)", norm)
                if _t_range:
                    ctype = "lag_range"
                # "Gain at Theta=30\nLAG" → LAG single angle
                elif re.search(r"theta[= ]*(\d+)", norm, re.IGNORECASE):
                    ctype = "lag_single"
                else:
                    ctype = "unknown"
            else:
                ctype = "unknown"

        cinfo = ColumnInfo(
            col_letter=col_letter,
            col_index=c,
            raw_header=raw,
            normalized_header=norm,
            col_type=ctype,
        )
        columns.append(cinfo)

        # 收集 LAG / AR 列头用于解析
        if ctype in ("lag_single", "lag_range"):
            lag_headers.append(raw)
        if ctype in ("ar_single", "ar_range"):
            ar_headers.append(raw)

    # ---- 解析频点列表 ----
    data_start_row = header_row + 1
    frequencies: List[float] = []
    freq_col = None
    for cinfo in columns:
        if cinfo.col_type == "frequency":
            freq_col = cinfo.col_index
            break

    if freq_col:
        for r in range(data_start_row, max_row + 1):
            val = ws.cell(r, freq_col).value
            if val is None or str(val).strip() == "" or str(val).strip() == "-":
                data_end_row = r - 1
                break
            try:
                frequencies.append(float(val))
            except (ValueError, TypeError):
                data_end_row = r - 1
                break

    # ---- 解析 LAG / AR 配置 ----
    lag_config = LagConfig.from_template_headers(lag_headers)
    ar_config = LagConfig.from_ar_headers(ar_headers)

    # ---- 读取 θ 范围 ----
    theta_range = None
    # 在 header_row 前几行搜索 "θ Range"
    for r in range(1, header_row):
        for c in range(1, max_col + 1):
            v = _cell_str(ws.cell(r, c))
            if "θ" in v and ("range" in v.lower() or "step" in v.lower()):
                # 尝试读同一行后续值
                theta_range = _cell_str(ws.cell(r, c + 1))
                break

    return SheetInfo(
        name=name,
        header_row=header_row,
        data_start_row=data_start_row,
        data_end_row=data_end_row,
        columns=columns,
        frequencies=frequencies,
        lag_config=lag_config,
        ar_config=ar_config,
        theta_range=theta_range,
    )


def _cell_str(cell) -> str:
    """单元格值 → 字符串。"""
    v = cell.value
    if v is None:
        return ""
    return str(v).strip()
