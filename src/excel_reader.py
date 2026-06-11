"""
Excel 模板读取器
================
读取输出模板 Excel，解析所有 Sheet 的结构信息：
  - 列头定义（Frequency / Directivity / LAG 角度等）
  - 频点列表
  - 自动检测 LAG 需求
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import openpyxl

from .lag_config import (
    LagConfig,
    is_directivity_column,
    is_efficiency_column,
    is_frequency_column,
    is_gain_column,
    normalize_header,
)


@dataclass
class ColumnInfo:
    """单列信息。"""
    col_letter: str          # 列字母，如 "B"
    col_index: int           # 1-based 列号
    raw_header: str          # 原始列头文本
    normalized_header: str   # 规范化列头
    col_type: str            # "frequency" | "directivity" | "efficiency_pct"
                             # | "efficiency_db" | "gain" | "lag_single"
                             # | "lag_range" | "unknown"


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

    for c in range(1, max_col + 1):
        raw = _cell_str(ws.cell(header_row, c))
        if not raw:
            continue
        norm = normalize_header(raw)
        col_letter = openpyxl.utils.get_column_letter(c)

        # 分类
        if is_frequency_column(raw):
            ctype = "frequency"
        elif is_directivity_column(raw):
            ctype = "directivity"
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
        else:
            # 可能是 LAG 列
            from .lag_config import _RE_LAG_RANGE, _RE_LAG_SINGLE

            if _RE_LAG_RANGE.search(norm):
                ctype = "lag_range"
            elif _RE_LAG_SINGLE.search(norm):
                ctype = "lag_single"
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

        # 收集 LAG 列头用于解析
        if ctype in ("lag_single", "lag_range"):
            lag_headers.append(raw)

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

    # ---- 解析 LAG 配置 ----
    lag_config = LagConfig.from_template_headers(lag_headers)

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
        theta_range=theta_range,
    )


def _cell_str(cell) -> str:
    """单元格值 → 字符串。"""
    v = cell.value
    if v is None:
        return ""
    return str(v).strip()
