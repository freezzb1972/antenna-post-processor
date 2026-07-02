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
import re
import sys
from dataclasses import dataclass, field

import openpyxl

from .lag_config import (
    _RE_LAG_RANGE,
    _RE_LAG_RANGE_NO_PREFIX,
    _RE_LAG_SINGLE,
    _RE_LAG_SINGLE_NO_PREFIX,
    LagConfig,
    normalize_header,
)

# ---------------------------------------------------------------------------
# 列头规范化 & 分类 (从 lag_config.py 移入 — 它们只被模板解析使用)
# ---------------------------------------------------------------------------

def _normalize_key(name: str) -> str:
    """将列头转成小写无空格键，用于固定列匹配。"""
    return re.sub(r"[^a-z%％()db]+", "", name.lower())


# ═══════════════════════════════════════════════════════════════
# JSON 列头模式加载器 — 用户可编辑的外部配置
# ═══════════════════════════════════════════════════════════════

_COLUMN_PATTERNS: list[dict] | None = None


def _load_column_patterns() -> list[dict]:
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
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                _COLUMN_PATTERNS = data.get("patterns", [])
                return _COLUMN_PATTERNS
            except (json.JSONDecodeError, OSError):
                pass

    _COLUMN_PATTERNS = []
    return _COLUMN_PATTERNS


def _classify_by_json_patterns(raw_header: str) -> str | None:
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


# ═══════════════════════════════════════════════════════════════
# 列类型分类注册表 — 所有 is_xxx_column 函数的单一数据源
#
# 新增列类型时只需:
#   1. 向 _COLUMN_CLASSIFIERS 添加一条规则
#   2. 向 _CLASSIFY_ORDER 添加 (col_type, 优先级)
#   3. 自动获得 classify_column() 聚合函数 + is_xxx_column() 包装器
# ═══════════════════════════════════════════════════════════════

def _col_classifier(must_contain: str = "", must_not_contain: str = "",
                    exact_words: tuple = (), keywords: tuple = (),
                    extra_checks: tuple = ()) -> callable:
    """生成列头匹配器。模式: (must_contain OR exact_words) AND keywords - must_not_contain。"""
    def _match(header: str) -> bool:
        lo = header.lower()
        # must_contain: 主关键词必须在 header 中出现
        if must_contain and must_contain not in lo:
            # 备选: exact_words 精确匹配整个 header (如 "freq"→frequency)
            if not (exact_words and lo in exact_words):
                return False
        # must_not_contain: 排除词 (如 gain 列排除 "average", "theta")
        if must_not_contain:
            for w in must_not_contain.split():
                if w in lo:
                    return False
        # keywords: 所有关键词必须 AND 出现
        if keywords and not all(k in lo for k in keywords):
            return False
        # extra_checks: 额外自定义条件 (lambda header, header_lower → bool)
        if extra_checks:
            return all(check(header, lo) for check in extra_checks)
        return True
    return _match


# 分类规则注册表: col_type → (match_fn, is_ratio_subtype)
_COLUMN_CLASSIFIERS: dict[str, tuple[callable, bool]] = {}

def _reg(col_type: str, **kw) -> None:
    _COLUMN_CLASSIFIERS[col_type] = (_col_classifier(**kw), False)

def _reg_fn(col_type: str, fn: callable, is_ratio: bool = False) -> None:
    _COLUMN_CLASSIFIERS[col_type] = (fn, is_ratio)


# ── 基础列类型 ──
_reg("frequency",     must_contain="frequency", exact_words=("freq", "f", "f(mhz)", "freq(mhz)"))
_reg("directivity",   must_contain="directivity", exact_words=("dir", "d(dbi)"))
_reg("efficiency_pct", must_contain="efficiency", must_not_contain="total")
_reg("total_efficiency", must_contain="total", keywords=("efficiency",))

# ── Gain (需排除 LAG/Peak 变体) ──
def _match_gain(header: str) -> bool:
    h = _normalize_key(header)
    if any(w in h for w in ("average", "theta", "pkgain", "peakgain", "peakeirp")):
        return False
    return h.startswith("gain") or h in ("g(dbi)", "pk")
_reg_fn("gain", _match_gain)

# ── TRP / NHPRP ──
def _match_trp(header: str) -> bool:
    h = header.lower()
    return ("trp" in h and "nhprp" not in h) or "total radiated power" in h or "tot. rad. pwr." in h
_reg_fn("trp", _match_trp)

_reg("nhprp_45",  must_contain="nhprp", keywords=("45",))
_reg("nhprp_30",  must_contain="nhprp", keywords=("30",))
_reg("nhprp_225", must_contain="nhprp", must_not_contain="45 30",
      extra_checks=(lambda h, lo: any(x in lo for x in ("22.5", "pi/8", "π/8")),))

# ── Peak EIRP ──
_reg("peak_eirp", must_contain="peakeirp", exact_words=("eirppeak", "pkgain", "peakgain"))

# ── AR ──
_reg("ar_single", must_contain="theta", extra_checks=(lambda h, lo: ("ar" in lo or "axial" in lo) and "~" not in lo,))
_reg("ar_range",  extra_checks=(lambda h, lo: ("ar" in lo or "axial" in lo) and "~" in lo,))

# ── PRP ──
_reg("uh_prp", keywords=("upper", "hem", "prp"))
_reg("lh_prp", keywords=("lower", "hem", "prp"))

# ── Power 统计 (min/max/avg 都含 "power") ──
_reg("max_power", must_contain="power", extra_checks=(lambda h, lo: ("maximum" in lo or "max" in lo) and "average" not in lo,))
_reg("min_power", must_contain="power", extra_checks=(lambda h, lo: ("minimum" in lo or "min" in lo) and "average" not in lo,))
_reg("avg_power", must_contain="power", extra_checks=(lambda h, lo: ("average" in lo or "avg" in lo),))

# ── Average Gain ──
_reg("avg_gain", must_contain="gain", extra_checks=(lambda h, lo: ("average" in lo or "avg" in lo) and "at" not in lo,))

# ── Boresight ──
_reg("boresight_phi",   keywords=("boresight", "phi"))
_reg("boresight_theta", must_contain="boresight", extra_checks=(lambda h, lo: any(x in lo for x in ("theta", "th.", "θ")),))

# ── XPI ──
_reg("xpi_boresight", keywords=("xpi", "boresight"))
_reg("xpi_mean",      keywords=("xpi", "mean"))
_reg("xpi_min",       keywords=("xpi", "min"), must_not_contain="mean")

# ── Total Efficiency / Mismatch ──
_reg("mismatch_loss", keywords=("mismatch", "loss"))

# ── Phase Center ──
_reg("pc_theta", extra_checks=(lambda h, lo: ("pc" in lo or "phase center" in lo) and ("theta" in lo or "θ" in lo),))
_reg("pc_phi",   extra_checks=(lambda h, lo: ("pc" in lo or "phase center" in lo) and "phi" in lo,))


# ═══════════════════════════════════════════════════════════════
# 公开 API: 聚合分类器 + 向后兼容包装器
# ═══════════════════════════════════════════════════════════════

def classify_column(header: str) -> str | None:
    """统一列头分类入口。按优先级匹配所有已注册列类型。"""
    for col_type, (matcher, _is_ratio) in _COLUMN_CLASSIFIERS.items():
        try:
            if matcher(header):
                return col_type
        except Exception:
            continue
    return detect_ratio_column_type(header)


# ── 向后兼容的 is_xxx_column 函数 (委托给注册表) ──
def _make_is_fn(col_type: str):
    """为指定 col_type 生成 is_xxx_column() 包装器。"""
    matcher, _ = _COLUMN_CLASSIFIERS.get(col_type, (lambda h: False, False))
    return lambda header: matcher(header)

is_frequency_column          = _make_is_fn("frequency")
is_directivity_column        = _make_is_fn("directivity")
is_efficiency_column         = _make_is_fn("efficiency_pct")
is_gain_column               = _make_is_fn("gain")
is_trp_column                = _make_is_fn("trp")
is_nhprp_45_column           = _make_is_fn("nhprp_45")
is_nhprp_30_column           = _make_is_fn("nhprp_30")
is_nhprp_225_column          = _make_is_fn("nhprp_225")
is_peak_eirp_column          = _make_is_fn("peak_eirp")
is_ar_single_column          = _make_is_fn("ar_single")
is_ar_range_column           = _make_is_fn("ar_range")
is_uh_prp_column             = _make_is_fn("uh_prp")
is_lh_prp_column             = _make_is_fn("lh_prp")
is_max_power_column          = _make_is_fn("max_power")
is_min_power_column          = _make_is_fn("min_power")
is_avg_gain_column           = _make_is_fn("avg_gain")
is_avg_power_column          = _make_is_fn("avg_power")
is_boresight_phi_column      = _make_is_fn("boresight_phi")
is_boresight_theta_column    = _make_is_fn("boresight_theta")
is_xpi_boresight_column      = _make_is_fn("xpi_boresight")
is_xpi_mean_column           = _make_is_fn("xpi_mean")
is_xpi_min_column            = _make_is_fn("xpi_min")
is_total_efficiency_column   = _make_is_fn("total_efficiency")
is_mismatch_loss_column      = _make_is_fn("mismatch_loss")
is_pc_theta_column           = _make_is_fn("pc_theta")
is_pc_phi_column             = _make_is_fn("pc_phi")


def detect_ratio_column_type(header: str) -> str | None:
    """检测比率列类型，返回带 db/pct 后缀的 column type。

    Returns:
        None (非比率列) 或 column type 如 "nhprp45_ratio", "uh_ratio" 等。
    """
    h = header.lower()
    if "ratio" not in h:
        return None
    # 比率基点 → base type 映射
    ratio_bases = [
        (("nhprp4", "nhprp45", "nhprp+/-45", "nhprp+-45"), "nhprp45_ratio"),
        (("nhprp3", "nhprp30", "nhprp+/-30", "nhprp+-30"), "nhprp30_ratio"),
        (("nhprp2", "nhprp225", "nhprp22.5", "nhprp+/-22.5"), "nhprp225_ratio"),
        (("upper", "hem"), "uh_ratio"),
        (("lower", "hem"), "lh_ratio"),
    ]
    for keywords, base in ratio_bases:
        if all(k in h for k in keywords):
            if "%" in header or "pct" in h:
                return base + "_pct"
            if "db" in h:
                return base + "_db"
            return base
    return None


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
    columns: list[ColumnInfo] = field(default_factory=list)
    frequencies: list[float] = field(default_factory=list)
    lag_config: LagConfig = field(default_factory=LagConfig)
    ar_config: LagConfig = field(default_factory=LagConfig)  # AR 角度配置
    theta_range: str | None = None  # e.g., "0-110°"


def read_template(template_path: str) -> list[SheetInfo]:
    """读取输出模板，返回所有工作表信息。

    会自动跳过纯元数据的 Sheet（无 Frequency 列）。
    """
    wb = openpyxl.load_workbook(template_path, data_only=True)
    sheets: list[SheetInfo] = []

    for ws in wb.worksheets:
        info = _parse_sheet(ws)
        if info is not None:
            sheets.append(info)

    wb.close()
    return sheets


def _classify_by_builtin(raw: str, norm: str) -> str | None:
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
    # LAG/AR 正则 (非 is_* 函数, 内置检测链必须包含)
    import re
    if _RE_LAG_RANGE.search(norm) or _RE_LAG_RANGE_NO_PREFIX.search(norm):
        return "lag_range"
    if _RE_LAG_SINGLE.search(norm) or _RE_LAG_SINGLE_NO_PREFIX.search(norm):
        return "lag_single"
    if "average" in norm.lower() and "gain" in norm.lower():
        _avg_range = re.search(r"(\d+)\s*[-–—~]\s*(\d+)\s*deg", norm)
        return "lag_range" if _avg_range else "gain_avg"
    if "gain" in norm.lower() and "theta" in norm.lower():
        _t_range = re.search(r"(\d+)\s*[-–—~]\s*(\d+)", norm)
        if _t_range:
            return "lag_range"
        if re.search(r"theta[= ]*(\d+)", norm, re.IGNORECASE):
            return "lag_single"
    return None


def _parse_sheet(ws) -> SheetInfo | None:
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
    columns: list[ColumnInfo] = []
    lag_headers: list[str] = []
    ar_headers: list[str] = []

    for c in range(1, max_col + 1):
        raw = _cell_str(ws.cell(header_row, c))
        if not raw:
            continue
        norm = normalize_header(raw)
        col_letter = openpyxl.utils.get_column_letter(c)

        # 分类 — 内置函数优先，JSON 仅补充，最后比率列 + unknown
        builtin_type = _classify_by_builtin(raw, norm)
        if builtin_type is not None:
            ctype = builtin_type
        else:
            json_type = _classify_by_json_patterns(raw)
            if json_type is not None:
                ctype = json_type
            else:
                ratio_type = detect_ratio_column_type(raw)
                if ratio_type is not None:
                    ctype = ratio_type
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
    frequencies: list[float] = []
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
