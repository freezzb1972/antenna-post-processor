"""
RSP 路径损耗校准模块
====================
EMQuest 响应文件 (.rsp) 的解析、插值、校准应用和频率覆盖检查。

核心公式:
  LogMag_cal = LogMag_raw - Response(freq)     [dB]
  Phase_cal  = Phase_raw  - RSP_Phase(freq)   [°]

极化对应: V-pol → Theta, H-pol → Phi
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field

import numpy as np

# ═══════════════════════════════════════════════════════════
# RSP 文件解析
# ═══════════════════════════════════════════════════════════

def _parse_rsp_file(path: str, col_idx: int) -> dict[float, float]:
    """从 RSP 文件读取指定列 (CSV 或 Excel 格式)。

    Args:
        path: RSP 文件路径。
        col_idx: 0-based 列索引 (1 = Response dB, 2 = Response Phase deg)。

    Returns:
        {frequency_mhz: value} 读取到的频率-值映射。
    """
    result: dict[float, float] = {}
    ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''

    if ext in ('xlsx', 'xls'):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            in_data = False
            for row in ws.iter_rows(min_col=1, max_col=col_idx + 1, values_only=True):
                r0 = str(row[0]).strip() if row[0] is not None else ''
                if 'Frequency' in r0 and 'MHz' in r0:
                    in_data = True; continue
                if in_data:
                    try:
                        freq = float(r0)
                        val = float(row[col_idx]) if row[col_idx] is not None else 0.0
                        if 300 < freq < 10000:
                            result[freq] = val
                    except (ValueError, TypeError):
                        if result: in_data = False
            wb.close()
        except Exception: pass
    else:
        try:
            with open(path, encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                in_data = False
                for row in reader:
                    if not row: continue
                    r0 = row[0].strip() if row[0] else ''
                    if 'Frequency' in r0 and 'MHz' in r0:
                        in_data = True; continue
                    if in_data:
                        try:
                            freq = float(r0)
                            val = float(row[col_idx].strip()) if len(row) > col_idx else 0.0
                            if 300 < freq < 10000:
                                result[freq] = val
                        except (ValueError, IndexError):
                            if result: in_data = False
        except Exception: pass

    return result


def parse_rsp_csv(path: str) -> dict[float, float]:
    """解析 EMQuest 导出的 .rsp 文件第2列 (Response dB)。

    公式: Gain(dBi) = S21(dB) - Response(dB)
    响应值通常为负数。
    """
    return _parse_rsp_file(path, col_idx=1)


def parse_rsp_phase(path: str) -> dict[float, float]:
    """解析 RSP 文件的 Phase 列 (Response Phase, 第3列)。

    Returns:
        {frequency_mhz: phase_deg}
    """
    return _parse_rsp_file(path, col_idx=2)


# ═══════════════════════════════════════════════════════════
# RSP 校准应用
# ═══════════════════════════════════════════════════════════

def _apply_rsp_to_logmag(data, freqs, rsp_data):
    """对 LogMag 数据应用 RSP 路径损耗校准: data[dB] -= Response(freq)."""
    if data is None or not rsp_data:
        return data
    rsp_freqs = np.array(sorted(rsp_data.keys()))
    rsp_values = np.array([rsp_data[f] for f in rsp_freqs])
    rsp_interp = np.interp(freqs, rsp_freqs, rsp_values,
                           left=rsp_values[0], right=rsp_values[-1])
    if not np.any(rsp_interp != 0.0):
        return data
    return np.asarray(data, dtype=np.float32) - rsp_interp[:, np.newaxis, np.newaxis].astype(np.float32)


def _apply_rsp_phase(data, freqs, rsp_phase_data):
    """对 Phase 数据应用 RSP 相位校准: Phase(°) -= RSP_Phase(freq)."""
    if data is None or not rsp_phase_data:
        return data
    rsp_freqs = np.array(sorted(rsp_phase_data.keys()))
    rsp_values = np.array([rsp_phase_data[f] for f in rsp_freqs])
    rsp_interp = np.interp(freqs, rsp_freqs, rsp_values,
                           left=rsp_values[0], right=rsp_values[-1])
    if not np.any(rsp_interp != 0.0):
        return data
    # 相位修正用复数旋转避免 wrap 问题
    corrected = np.degrees(np.angle(
        np.exp(1j * np.radians(np.asarray(data, dtype=np.float32)))
        * np.exp(-1j * np.radians(rsp_interp[:, np.newaxis, np.newaxis].astype(np.float32)))
    ))
    return corrected.astype(np.float32)


def _apply_rsp_calibration(
    tl: np.ndarray, tp: np.ndarray,
    pl: np.ndarray, pp: np.ndarray,
    freqs: list[float],
    rsp_h: dict[float, float], rsp_v: dict[float, float],
    rsp_h_phase: dict[float, float], rsp_v_phase: dict[float, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """RSP 路径损耗校准 (幅度 + 相位)，统一入口。

    公式:
      LogMag_cal = LogMag_raw - Response(freq)     [dB]
      Phase_cal  = Phase_raw  - RSP_Phase(freq)   [deg]

    极化对应: V-pol → Theta, H-pol → Phi

    Returns:
        (tl, tp, pl, pp) 校准后的 4 个 3D 数组。
    """
    tl = _apply_rsp_to_logmag(tl, freqs, rsp_v)
    pl = _apply_rsp_to_logmag(pl, freqs, rsp_h)
    if rsp_v_phase:
        tp = _apply_rsp_phase(tp, freqs, rsp_v_phase)
    if rsp_h_phase:
        pp = _apply_rsp_phase(pp, freqs, rsp_h_phase)
    return tl, tp, pl, pp


# ═══════════════════════════════════════════════════════════
# 频率覆盖检查
# ═══════════════════════════════════════════════════════════

def check_rsp_coverage(
    rsp_data: dict[float, float],
    file_freqs: list[float],
    tolerance_mhz: float = 1.0,
) -> list[str]:
    """检查 RSP 校准数据是否覆盖文件的频率范围。

    Args:
        rsp_data: {freq_mhz: response_db} 校准数据。
        file_freqs: 文件中的频点列表。
        tolerance_mhz: 容差 (MHz), 边界小幅超出不报警。

    Returns:
        警告信息列表。空列表表示覆盖完整。
    """
    if not rsp_data or not file_freqs:
        return []
    rsp_freqs = sorted(rsp_data.keys())
    rsp_min, rsp_max = rsp_freqs[0], rsp_freqs[-1]
    file_min, file_max = min(file_freqs), max(file_freqs)
    warnings = []
    if file_min < rsp_min - tolerance_mhz:
        warnings.append(
            f"最低频率 {file_min:.1f} MHz 低于 RSP 最低 {rsp_min:.1f} MHz"
        )
    if file_max > rsp_max + tolerance_mhz:
        warnings.append(
            f"最高频率 {file_max:.1f} MHz 高于 RSP 最高 {rsp_max:.1f} MHz"
        )
    return warnings


def _rsp_freq_bounds(rsp_data: dict[float, float]) -> tuple[float, float]:
    """返回 RSP 数据的频率边界 (min, max)。"""
    rsp_freqs = sorted(rsp_data.keys())
    return (rsp_freqs[0], rsp_freqs[-1])


@dataclass
class RspCoverageResult:
    """RSP 频率覆盖检查结果。"""
    ok: bool = True                              # True = 全部覆盖
    rsp_h_bounds: str = ""                        # "400 - 6000 MHz"
    rsp_v_bounds: str = ""
    warnings: list[str] = field(default_factory=list)  # 警告信息列表
