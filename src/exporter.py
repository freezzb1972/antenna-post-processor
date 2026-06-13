"""
Excel 输出模块
==============
基于模板填充天线参数数据 + 嵌入 3D 辐射方向图。

使用 openpyxl 复制模板并写入结果，保留原始格式。
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter

from .excel_reader import ColumnInfo, SheetInfo, read_template


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def export_results(
    template_path: str,
    output_path: str,
    sheet_results: Dict[str, List[Dict[str, Any]]],
    *,
    pattern_images: Optional[Dict[str, Dict[float, io.BytesIO]]] = None,
    sheets_info: Optional[List[SheetInfo]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """基于模板填充数据 + 嵌入图片。

    Args:
        template_path:  模板 Excel 路径。
        output_path:    输出 Excel 路径。
        sheet_results:  {sheet_name: [row_dict, ...]}，
                        row_dict key = column type ("directivity", "lag_single_60.0", ...)。
        pattern_images: {sheet_name: {freq_mhz: PNG_buffer}}（可选）。
        sheets_info:    预解析的 Sheet 信息（可选，避免重复读模板）。
        progress_callback: (current, total, message)。
        log_callback:   (message)。

    Returns:
        输出文件路径。
    """
    # 读取模板（仅当调用方未提供 sheets_info 时）
    if sheets_info is None:
        sheets_info = read_template(template_path)
    info_map = {s.name: s for s in sheets_info}

    # 复制模板
    wb = openpyxl.load_workbook(template_path)

    total_ops = sum(len(rows) for rows in sheet_results.values()) + len(sheets_info)
    current = 0

    for sheet_name, rows in sheet_results.items():
        if sheet_name not in wb.sheetnames:
            continue
        if sheet_name not in info_map:
            continue

        ws = wb[sheet_name]
        info = info_map[sheet_name]

        # 构建列映射: col_type → ColumnInfo
        col_map = _build_col_map(info)

        for row_idx_offset, row_data in enumerate(rows):
            excel_row = info.data_start_row + row_idx_offset

            # 匹配频点
            freq = row_data.get("frequency")
            if freq is None:
                continue

            # 填入各列
            for key, value in row_data.items():
                if key == "frequency":
                    _write_cell(ws, excel_row, col_map, "frequency", freq)
                elif key == "directivity":
                    _write_cell(ws, excel_row, col_map, "directivity", value)
                elif key == "efficiency_pct":
                    _write_cell(ws, excel_row, col_map, "efficiency_pct", value)
                elif key == "efficiency_db":
                    _write_cell(ws, excel_row, col_map, "efficiency_db", value)
                elif key == "gain":
                    # 可能有多个 Gain 列 (5G4)
                    _write_cell(ws, excel_row, col_map, "gain", value)
                elif key.startswith("lag_single_"):
                    # key: "lag_single_60.0" → 匹配 theta=60 的 LAG 列
                    angle_str = key[len("lag_single_"):]
                    _write_lag_single(ws, excel_row, col_map, float(angle_str), value)
                elif key.startswith("lag_range_"):
                    # key: "lag_range_0.0_90.0" → 匹配 (0, 90) 范围 LAG 列
                    parts = key[len("lag_range_"):].split("_")
                    if len(parts) == 2:
                        lo, hi = float(parts[0]), float(parts[1])
                        _write_lag_range(ws, excel_row, col_map, lo, hi, value)

            current += 1
            if progress_callback:
                progress_callback(current, total_ops, f"写入 {sheet_name} Row {excel_row}")

        # ---- 嵌入 3D 方向图 ----
        if pattern_images and sheet_name in pattern_images:
            _embed_images(ws, info, pattern_images[sheet_name], log_callback)

        current += 1
        if progress_callback:
            progress_callback(current, total_ops, f"完成 {sheet_name}")

    # 保存
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    wb.save(output_path)
    wb.close()
    return output_path


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _build_col_map(info: SheetInfo) -> Dict[str, List[ColumnInfo]]:
    """构建 col_type → [ColumnInfo, ...] 映射（可能有重复类型列，如 5G4 的两个 Gain 列）。"""
    m: Dict[str, List[ColumnInfo]] = {}
    for cinfo in info.columns:
        m.setdefault(cinfo.col_type, []).append(cinfo)
    return m


def _find_col_by_type(
    col_map: Dict[str, List[ColumnInfo]], ctype: str, index: int = 0
) -> Optional[ColumnInfo]:
    """查找第 index 个指定类型的列。"""
    cols = col_map.get(ctype, [])
    if index < len(cols):
        return cols[index]
    return None


def _write_cell(
    ws,
    row: int,
    col_map: Dict[str, List[ColumnInfo]],
    ctype: str,
    value: Any,
):
    """写入一个单元格。"""
    cols = col_map.get(ctype, [])
    if not cols:
        return
    for cinfo in cols:
        cell = ws.cell(row, cinfo.col_index)
        if value is not None:
            # 保留 2 位小数（科学计算常用）
            if isinstance(value, float):
                cell.value = round(value, 2)
            else:
                cell.value = value


def _write_lag_single(
    ws, row: int, col_map: Dict[str, List[ColumnInfo]],
    angle: float, value: Any,
):
    """写入单角度 LAG 到匹配的列。"""
    for cinfo in col_map.get("lag_single", []):
        # 从列头中提取角度
        from .lag_config import _RE_LAG_SINGLE, normalize_header
        m = _RE_LAG_SINGLE.search(normalize_header(cinfo.raw_header))
        if m and abs(float(m.group(1)) - angle) < 0.01:
            cell = ws.cell(row, cinfo.col_index)
            if isinstance(value, float):
                cell.value = round(value, 2)
            else:
                cell.value = value
            return


def _write_lag_range(
    ws, row: int, col_map: Dict[str, List[ColumnInfo]],
    lo: float, hi: float, value: Any,
):
    """写入范围 LAG 到匹配的列。"""
    for cinfo in col_map.get("lag_range", []):
        from .lag_config import _RE_LAG_RANGE, normalize_header
        m = _RE_LAG_RANGE.search(normalize_header(cinfo.raw_header))
        if m:
            clo, chi = float(m.group(1)), float(m.group(2))
            if abs(clo - lo) < 0.01 and abs(chi - hi) < 0.01:
                cell = ws.cell(row, cinfo.col_index)
                if isinstance(value, float):
                    cell.value = round(value, 2)
                else:
                    cell.value = value
                return


def _embed_images(
    ws,
    info: SheetInfo,
    images: Dict[float, io.BytesIO],
    log_callback=None,
    *,
    col_offset: int = 3,
    row_step: int = 22,
    img_width: int = 280,
    img_height: int = 210,
):
    """在数据区域右侧嵌入 3D 方向图。

    图片布局：从数据区域右侧 col_offset 列开始，每 row_step 行放一张图。

    Args:
        ws:         工作表对象。
        info:       工作表结构信息。
        images:     {freq_mhz: PNG_buffer}。
        log_callback: 日志回调。
        col_offset: 图片列相对数据区域右侧的偏移（列数）。
        row_step:   每张图占用的行高。
        img_width:  图片宽度 (px)。
        img_height: 图片高度 (px)。
    """
    if not images:
        return

    max_col = max((c.col_index for c in info.columns), default=10)
    image_col = max_col + col_offset
    image_row = info.data_start_row

    for idx, (freq, buf) in enumerate(sorted(images.items())):
        try:
            buf.seek(0)
            img = XLImage(buf)
            img.width = img_width
            img.height = img_height
            cell = f"{get_column_letter(image_col)}{image_row}"
            ws.add_image(img, cell)
            image_row += row_step
        except Exception as e:
            # 图片嵌入失败不阻塞数据输出，但记录日志
            if log_callback:
                log_callback(f"  ⚠ {freq} MHz: 图片嵌入失败 — {e}")
