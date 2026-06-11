"""
批处理管线
===========
协调 parser → calculator → plotter → exporter 的完整数据处理流程。

支持：
  - 单 CSV → 多 Sheet 批处理
  - 模板驱动自动 LAG 检测
  - 用户 LAG 配置覆盖
  - 3D 方向图生成
"""

from __future__ import annotations

import io
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .calculator import (
    compute_directivity,
    compute_efficiency,
    compute_lag_at_angles,
    compute_lag_ranges,
    compute_total_gain_linear,
)
from .excel_reader import SheetInfo, read_template
from .exporter import export_results
from .lag_config import LagConfig
from .parser import MergedCSVParser
from .plotter import generate_3d_pattern


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

class PlotConfig:
    """3D 方向图生成配置。"""
    elev: float = 30.0
    azim: float = -60.0
    dpi: int = 150
    embed_in_excel: bool = True
    save_png_folder: Optional[str] = None

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# 主处理函数
# ---------------------------------------------------------------------------

def run_batch_pipeline(
    csv_path: str,
    template_path: str,
    output_path: str,
    *,
    lag_config_override: Optional[LagConfig] = None,
    plot_config: Optional[PlotConfig] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[float, io.BytesIO]]]:
    """执行完整批处理管线。

    Args:
        csv_path:             输入 EMQuest merged CSV 路径。
        template_path:        输出模板 Excel 路径。
        output_path:          最终输出 Excel 路径。
        lag_config_override:  覆盖模板自动检测的 LAG 配置（None=自动）。
        plot_config:          3D 图配置（None=默认）。
        progress_callback:    (current, total, message)。
        log_callback:         (message)。

    Returns:
        (sheet_results, pattern_images)
    """
    if plot_config is None:
        plot_config = PlotConfig()

    t0 = time.time()

    # ---- 1. 初始化解析器 ----
    _log(log_callback, f"加载 CSV: {csv_path}")
    _report(progress_callback, 0, 100, "初始化解析器...")

    parser = MergedCSVParser(csv_path)
    csv_freqs = parser.frequencies
    theta_deg = np.array(parser.theta_angles)  # (111,) 0-110
    theta_rad = np.deg2rad(theta_deg)
    phi_deg = np.array(parser.phi_angles)      # (360,) 0-359

    _log(log_callback, f"  → 解析完成: {len(csv_freqs)} 频点, "
                       f"{len(theta_deg)} Theta × {len(phi_deg)} Phi")

    # ---- 2. 读取模板 ----
    _log(log_callback, f"读取模板: {template_path}")
    _report(progress_callback, 1, 100, "读取模板...")

    sheets_info = read_template(template_path)
    _log(log_callback, f"  → 检测到 {len(sheets_info)} 个天线工作表")
    for si in sheets_info:
        _log(log_callback, f"     {si.name}: {len(si.frequencies)} 频点, "
                           f"LAG 单角度={si.lag_config.singles_sorted}, "
                           f"LAG 范围={si.lag_config.ranges_sorted}")

    # ---- 3. 合并 LAG 配置 ----
    if lag_config_override is not None and not lag_config_override.is_empty():
        _log(log_callback, "使用用户指定的 LAG 配置（覆盖模板自动检测）")
        for si in sheets_info:
            si.lag_config = lag_config_override

    # ---- 4. 构建频点-CSV索引映射 ----
    csv_freq_to_idx = {f: i for i, f in enumerate(csv_freqs)}

    # 计算总步数
    total_steps = sum(len(si.frequencies) for si in sheets_info)
    step = 0

    # ---- 5. 逐 Sheet 处理 ----
    all_sheet_results: Dict[str, List[Dict[str, Any]]] = {}
    all_pattern_images: Dict[str, Dict[float, io.BytesIO]] = {}

    for si in sheets_info:
        _log(log_callback, f"\n开始处理 {si.name} ({len(si.frequencies)} 频点)...")
        sheet_results: List[Dict[str, Any]] = []
        sheet_images: Dict[float, io.BytesIO] = {}

        for freq in si.frequencies:
            step += 1
            msg = f"{si.name} · {freq} MHz ({step}/{total_steps})"
            _report(progress_callback, step, total_steps, msg)

            # 找 CSV 中最接近的频点
            csv_idx = _find_closest_freq(csv_freqs, csv_freq_to_idx, freq)
            if csv_idx is None:
                _log(log_callback, f"  ⚠ {freq} MHz: CSV 中无匹配频点，跳过")
                continue

            actual_freq = csv_freqs[csv_idx]

            try:
                row = _process_one_frequency(
                    parser, csv_idx, actual_freq,
                    theta_deg, theta_rad, phi_deg,
                    si.lag_config, plot_config,
                )
                sheet_results.append(row)

                # 生成 3D 方向图
                if plot_config.embed_in_excel or plot_config.save_png_folder:
                    png_buf = _generate_pattern_image(
                        parser, csv_idx, actual_freq,
                        theta_deg, phi_deg,
                        plot_config, si.name,
                    )
                    if png_buf:
                        sheet_images[actual_freq] = png_buf

            except Exception as e:
                _log(log_callback, f"  ✗ {freq} MHz: 处理失败 — {e}")
                # 填入空行
                sheet_results.append({"frequency": freq, "_error": str(e)})

        all_sheet_results[si.name] = sheet_results
        all_pattern_images[si.name] = sheet_images
        _log(log_callback, f"  ✓ {si.name} 完成 ({len(sheet_results)} 行)")

    # ---- 6. 写入 Excel ----
    _log(log_callback, f"\n写入输出 Excel: {output_path}")
    _report(progress_callback, total_steps, total_steps + 10, "写入 Excel...")

    export_results(
        template_path=template_path,
        output_path=output_path,
        sheet_results=all_sheet_results,
        pattern_images=all_pattern_images if plot_config.embed_in_excel else None,
        progress_callback=(
            lambda c, t, m: _report(progress_callback, total_steps + c, total_steps + t, m)
            if progress_callback else None
        ),
    )

    elapsed = time.time() - t0
    _log(log_callback, f"\n✓ 全部完成! 耗时 {elapsed:.1f}s")
    _log(log_callback, f"  输出: {output_path}")
    _report(progress_callback, total_steps + 10, total_steps + 10, "完成")

    return all_sheet_results, all_pattern_images


# ---------------------------------------------------------------------------
# 单频点处理
# ---------------------------------------------------------------------------

def _process_one_frequency(
    parser: MergedCSVParser,
    csv_idx: int,
    freq: float,
    theta_deg: np.ndarray,
    theta_rad: np.ndarray,
    phi_deg: np.ndarray,
    lag_config: LagConfig,
    plot_config: PlotConfig,
) -> Dict[str, Any]:
    """处理单个频点，返回一行结果 dict。"""
    data = parser.read_all_sections_for_freq(csv_idx)

    theta_lm = np.array(data["theta_logmag"], dtype=np.float64)   # (360, 111)
    theta_ph = np.array(data["theta_phase"], dtype=np.float64)
    phi_lm = np.array(data["phi_logmag"], dtype=np.float64)
    phi_ph = np.array(data["phi_phase"], dtype=np.float64)

    # Gain
    gain_linear, peak_dbi = compute_total_gain_linear(theta_lm, phi_lm)

    # Directivity
    directivity_dbi = compute_directivity(gain_linear, theta_rad)

    # Efficiency
    eff_pct, eff_db = compute_efficiency(peak_dbi, directivity_dbi)

    row: Dict[str, Any] = {
        "frequency": freq,
        "directivity": round(directivity_dbi, 2),
        "efficiency_pct": round(eff_pct, 2),
        "efficiency_db": round(eff_db, 2),
        "gain": round(peak_dbi, 2),
    }

    # LAG 单角度
    singles = lag_config.singles_sorted
    if singles:
        lag_singles = compute_lag_at_angles(gain_linear, theta_deg, singles)
        for angle, val in lag_singles.items():
            row[f"lag_single_{angle}"] = round(val, 2)

    # LAG 范围
    ranges = lag_config.ranges_sorted
    if ranges:
        lag_ranges = compute_lag_ranges(gain_linear, theta_deg, ranges)
        for (lo, hi), val in lag_ranges.items():
            row[f"lag_range_{lo}_{hi}"] = round(val, 2)

    return row


def _generate_pattern_image(
    parser: MergedCSVParser,
    csv_idx: int,
    freq: float,
    theta_deg: np.ndarray,
    phi_deg: np.ndarray,
    plot_config: PlotConfig,
    antenna_name: str,
) -> Optional[io.BytesIO]:
    """生成单频点 3D 方向图 PNG buffer。"""
    try:
        data = parser.read_all_sections_for_freq(csv_idx)
        theta_lm = np.array(data["theta_logmag"], dtype=np.float64)
        phi_lm = np.array(data["phi_logmag"], dtype=np.float64)

        g_theta = np.power(10.0, theta_lm / 10.0)
        g_phi = np.power(10.0, phi_lm / 10.0)
        total_lin = g_theta + g_phi
        gain_dbi = 10.0 * np.log10(np.maximum(total_lin, 1e-30))

        return generate_3d_pattern(
            theta_deg=theta_deg,
            phi_deg=phi_deg,
            gain_dbi=gain_dbi,
            freq_mhz=freq,
            elev=plot_config.elev,
            azim=plot_config.azim,
            dpi=plot_config.dpi,
            antenna_name=antenna_name,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _find_closest_freq(
    csv_freqs: List[float],
    freq_map: Dict[float, int],
    target: float,
    tolerance: float = 5.0,
) -> Optional[int]:
    """在 CSV 频点列表中找最接近的频点索引。"""
    # 精确匹配
    if target in freq_map:
        return freq_map[target]
    # 最近邻
    best_idx = int(np.argmin([abs(f - target) for f in csv_freqs]))
    if abs(csv_freqs[best_idx] - target) <= tolerance:
        return best_idx
    return None


def _log(cb, msg: str):
    if cb:
        cb(msg)


def _report(cb, current: int, total: int, msg: str):
    if cb:
        cb(current, total, msg)
