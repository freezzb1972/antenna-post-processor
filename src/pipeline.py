"""
批处理管线 (v2)
================
协调 datasource → extrapolate → calculator → plotter → exporter。

支持:
  - 任意 DataSource (MergedCSV / FinalSummary)
  - 内存中 Theta 外推 (无中间文件)
  - 逐频点处理 (峰值内存 ~2MB/频点)
  - 可选多进程并行
"""

from __future__ import annotations

import copy
import io
import math
import os
import re
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np

from .output_config import OutputConfig
from .calculator import (
    compute_ar_at_angles,
    compute_ar_range,
    compute_average_gain_db,
    compute_average_power_dbm,
    compute_axial_ratio,
    compute_beamwidth,
    compute_boresight,
    compute_directivity,
    compute_efficiency,
    compute_lag_at_angles,
    compute_lag_ranges,
    compute_lower_hemisphere_prp,
    compute_min_power_dbm,
    compute_nhprp,
    compute_nhprp_flex,
    compute_partial_prp,
    compute_peak_eirp,
    compute_phase_center,
    compute_power_ratios,
    compute_prp_trp_ratio,
    compute_total_efficiency,
    compute_total_gain_linear,
    compute_trp,
    compute_upper_hemisphere_prp,
    compute_xpi,
)
from .chart_config import ChartConfig
from .datasource import DataSource
from .excel_reader import ColumnInfo, SheetInfo, read_template
from .exporter import export_results
from .lag_config import LagConfig
from .parser import MergedCSVParser
from .plot_config import PlotConfig
from .report_exporter import export_full_report

# ---------------------------------------------------------------------------
# Theta 外推 (pipeline 层)
# ---------------------------------------------------------------------------

def extrapolate_theta(
    theta_deg: np.ndarray,
    data: np.ndarray,  # (n_phi, n_theta)
    method: str = "linear",
) -> tuple[np.ndarray, np.ndarray]:
    """将 Theta 范围外推到 0-180°。

    Args:
        theta_deg: 原始 Theta 角度 (°)。
        data:      数据矩阵 (n_phi, n_theta)。
        method:    'linear' | 'constant' | 'mirror'。

    Returns:
        (new_theta_deg, new_data)，new_data 形状 (n_phi, n_new)。
    """
    max_t = theta_deg[-1]
    if max_t >= 179:
        return theta_deg.copy(), data.copy()

    n_phi, n_theta = data.shape
    dtheta = theta_deg[1] - theta_deg[0] if len(theta_deg) > 1 else 1.0

    new_theta = list(theta_deg)
    t = max_t + dtheta
    while t <= 180.01:
        new_theta.append(round(t, 6))
        t += dtheta

    n_new = len(new_theta)
    new_data = np.zeros((n_phi, n_new), dtype=np.float64)
    new_data[:, :n_theta] = data

    if method == "constant":
        tail_avg = np.mean(data[:, -10:], axis=1)
        new_data[:, n_theta:] = tail_avg[:, np.newaxis]

    elif method == "mirror":
        for i in range(n_new - n_theta):
            mirror_idx = n_theta - 2 - i
            idx = mirror_idx if mirror_idx >= 0 else 0
            new_data[:, n_theta + i] = data[:, idx]

    elif method == "linear":
        tail_n = min(10, n_theta)
        xv = theta_deg[-tail_n:]
        n = len(xv)
        sx = float(np.sum(xv))
        sxx = float(np.sum(xv * xv))
        denom_ok = n > 1 and sxx * n - sx * sx != 0
        for pi in range(n_phi):
            yv = data[pi, -tail_n:]
            sy = float(np.sum(yv))
            sxy = float(np.sum(xv * yv))
            if denom_ok:
                slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
                intercept = (sy - slope * sx) / n
                if slope > 0:
                    slope = 0; intercept = sy / n
                peak = float(np.max(yv))
                floor = peak - 40
                for i in range(n_theta, n_new):
                    val = slope * new_theta[i] + intercept
                    val = min(val, yv[-1])
                    new_data[pi, i] = max(val, floor)

    return np.array(new_theta), new_data


# ---------------------------------------------------------------------------
# 单频点处理
# ---------------------------------------------------------------------------

def _process_one_frequency(
    raw: dict[str, np.ndarray | None],
    freq: float,
    theta_deg: np.ndarray,
    lag_config: LagConfig,
    *,
    theta_extrap_method: str | None = None,
    robust_peak: bool = False,
    needed_params: set = None,
    extra_params: set = None,
    chart_config: ChartConfig = None,
    ar_lag_config: LagConfig = None,
    rhcp_lag_config: LagConfig = None,
    cpxpi_lag_config: LagConfig = None,
    output_config: OutputConfig = None,
    nh_custom_angles: list[float] | None = None,
    ar_output_db: bool = True,
    dir_extrap_method: str = "none",
    compute_only: bool = False,
    store_matrices: bool = False,
    chart_instances: list | None = None,
    log_cb=None,
) -> dict[str, Any]:
    """处理单个频点。按 needed_params（模板列）+ extra_params（用户额外）计算。"""
    theta_lm = raw["theta_logmag"]
    phi_lm = raw["phi_logmag"]
    need = needed_params or set()
    extra = extra_params or set()
    compute_set = need | extra  # 实际计算: 模板需求 + 用户额外

    # 角度域标准化: phi∈[0,360), theta∈[0,180]
    _pa = raw.get("_phi_angles")
    if _pa is not None:
        _pa = np.asarray(_pa, dtype=np.float64)
        phi_mask = _pa < 360.0
        if not np.all(phi_mask):
            theta_lm = theta_lm[phi_mask, :]
            phi_lm = phi_lm[phi_mask, :]
            for _k in ("theta_phase", "phi_phase"):
                if _k in raw and raw[_k] is not None:
                    raw[_k] = raw[_k][phi_mask, :]
            _pa = _pa[phi_mask]
            raw["_phi_angles"] = _pa
    theta_mask = theta_deg <= 180.0
    if not np.all(theta_mask):
        theta_lm = theta_lm[:, theta_mask]
        phi_lm = phi_lm[:, theta_mask]
        for _k in ("theta_phase", "phi_phase"):
            if _k in raw and raw[_k] is not None:
                raw[_k] = raw[_k][:, theta_mask]
        theta_deg = theta_deg[theta_mask]

    # 保存原始数据 (Directivity 独立外推用; 通用 Theta 外推不影响 Directivity, 见 tooltip"除Directivity外")
    orig_theta_deg = theta_deg.copy()
    orig_theta_lm = theta_lm
    orig_phi_lm = phi_lm

    need_extrap = theta_extrap_method is not None and theta_deg[-1] < 175
    if need_extrap:
        theta_orig = theta_deg.copy()
        new_theta, theta_lm = extrapolate_theta(theta_deg, theta_lm, theta_extrap_method)
        _, phi_lm = extrapolate_theta(theta_deg, phi_lm, theta_extrap_method)
        theta_deg = new_theta

    theta_rad = np.deg2rad(theta_deg)
    gain_linear, peak_dbi = compute_total_gain_linear(theta_lm, phi_lm, robust=robust_peak)
    row: dict[str, Any] = {"frequency": freq}

    # Gain (always include if template has it)
    if "gain" in need or "peak_eirp" in compute_set or not need:
        row["gain"] = round(peak_dbi, 6)

    # Directivity (需全球面积分)。独立用 dir_extrap_method 外推**原始**数据,
    # 不受通用 theta_extrap_method 影响 (dir_extrap="none" 即用原始截断数据积分)。
    directivity_dbi = None
    need_dir_or_eff = ("directivity" in compute_set or "efficiency_pct" in need
                       or "efficiency_db" in compute_set or not need)
    if need_dir_or_eff:
        if orig_theta_deg[-1] < 175 and dir_extrap_method != "none":
            # 外推原始 LogMag 到 180° 仅用于 Directivity, 不覆盖其它参数
            ext_th, ext_tl = extrapolate_theta(orig_theta_deg, orig_theta_lm, dir_extrap_method)
            _, ext_pl = extrapolate_theta(orig_theta_deg, orig_phi_lm, dir_extrap_method)
            ext_gl, _ = compute_total_gain_linear(ext_tl, ext_pl)
            dir_gl = ext_gl
            dir_theta = np.deg2rad(ext_th)
        else:
            # 不外推: 用原始截断数据 (θ 仅到 80/110° 等) 直接积分
            dir_gl, _ = compute_total_gain_linear(orig_theta_lm, orig_phi_lm)
            dir_theta = np.deg2rad(orig_theta_deg)
        directivity_dbi = compute_directivity(dir_gl, dir_theta)
        if "directivity" in compute_set or not need:
            row["directivity"] = round(directivity_dbi, 6)

    # Efficiency
    if "efficiency_pct" in need or "efficiency_db" in compute_set or not need:
        if directivity_dbi is None:
            directivity_dbi = compute_directivity(dir_gl, dir_theta)
        eff_pct, eff_db = compute_efficiency(peak_dbi, directivity_dbi)
        if "efficiency_pct" in compute_set or not need:
            row["efficiency_pct"] = round(eff_pct, 6)
        if "efficiency_db" in compute_set or not need:
            row["efficiency_db"] = round(eff_db, 6)

    # TRP / NHPRP / Peak EIRP
    for ct, fn in [("trp", lambda: compute_trp(gain_linear, theta_rad)),
                   ("nhprp_45", lambda: compute_nhprp(gain_linear, theta_rad, 45.0)),
                   ("nhprp_30", lambda: compute_nhprp(gain_linear, theta_rad, 30.0)),
                   ("peak_eirp", lambda: compute_peak_eirp(gain_linear))]:
        if ct in compute_set or not need:
            row[ct] = round(fn(), 2)

    # ---- Extended antenna parameters (NHPRP flex, PRP, ratios, boresight, averages) ----
    n_phi = phi_lm.shape[0]
    phi_angles_deg = np.linspace(0, 360, n_phi, endpoint=False)

    nhprp_225 = compute_nhprp_flex(gain_linear, theta_rad, 22.5)
    nhprp_45_flex = compute_nhprp_flex(gain_linear, theta_rad, 45.0)
    nhprp_30_flex = compute_nhprp_flex(gain_linear, theta_rad, 30.0)
    if "nhprp_225" in compute_set or not need: row["nhprp_225"] = round(nhprp_225, 2)

    # TIS = TRP (同公式, 不同测量模式)
    if "tis" in compute_set or not need: row["tis"] = round(compute_trp(gain_linear, theta_rad), 2)
    # NHPIS = NHPRP (同公式, 不同测量模式)
    for label, edge in [("nhpis_45", 45.0), ("nhpis_30", 30.0), ("nhpis_225", 22.5)]:
        if label in compute_set or not need: row[label] = round(compute_nhprp_flex(gain_linear, theta_rad, edge), 2)
    # Custom NHPRP/NHPIS angle
    _nh_angles = nh_custom_angles if nh_custom_angles else [45.0]  # default: 45°
    if "nhprp_custom" in compute_set or not need:
        for edge in _nh_angles:
            row[f"nhprp_custom_{int(edge)}"] = round(compute_nhprp_flex(gain_linear, theta_rad, edge), 2)
        # 向后兼容: 保留第一个角度键
        row["nhprp_custom"] = round(compute_nhprp_flex(gain_linear, theta_rad, _nh_angles[0]), 2)
    if "nhpis_custom" in compute_set or not need:
        for edge in _nh_angles:
            row[f"nhpis_custom_{int(edge)}"] = round(compute_nhprp_flex(gain_linear, theta_rad, edge), 2)
        row["nhpis_custom"] = round(compute_nhprp_flex(gain_linear, theta_rad, _nh_angles[0]), 2)

    uh_prp = compute_upper_hemisphere_prp(gain_linear, theta_rad)
    lh_prp = compute_lower_hemisphere_prp(gain_linear, theta_rad)
    if "uh_prp" in compute_set or not need: row["uh_prp"] = round(uh_prp, 2)
    if "lh_prp" in compute_set or not need: row["lh_prp"] = round(lh_prp, 2)
    if "uh_pis" in compute_set or not need: row["uh_pis"] = round(uh_prp, 2)
    if "lh_pis" in compute_set or not need: row["lh_pis"] = round(lh_prp, 2)

    prp_120 = compute_partial_prp(gain_linear, theta_rad, 0, 120)
    if "prp_120" in compute_set or not need: row["prp_120"] = round(prp_120, 2)
    if "pis_120" in compute_set or not need: row["pis_120"] = round(prp_120, 2)

    ratio_need = compute_set & {"nhprp45_ratio", "nhprp30_ratio", "nhprp225_ratio", "nhpis45_ratio",
                                  "nhpis30_ratio", "nhpis225_ratio", "uh_ratio", "lh_ratio"}
    if ratio_need or not need:
        trp_val = compute_trp(gain_linear, theta_rad)
        tis_val = trp_val  # same formula
        for ratio_key, prp_val, ref_val in [
            ("nhprp45", nhprp_45_flex, trp_val), ("nhprp30", nhprp_30_flex, trp_val),
            ("nhprp225", nhprp_225, trp_val), ("nhpis45", nhprp_45_flex, tis_val),
            ("nhpis30", nhprp_30_flex, tis_val), ("nhpis225", nhprp_225, tis_val),
            ("uh", uh_prp, trp_val), ("lh", lh_prp, trp_val)]:
            rdb, rpct = compute_prp_trp_ratio(prp_val, ref_val)
            if f"{ratio_key}_ratio_db" in compute_set or not need: row[f"{ratio_key}_ratio_db"] = round(rdb, 2)
            if f"{ratio_key}_ratio_pct" in compute_set or not need: row[f"{ratio_key}_ratio_pct"] = round(rpct, 2)

    bs_need = compute_set & {"boresight_phi", "boresight_theta"}
    if bs_need or not need:
        bs_theta, bs_phi = compute_boresight(gain_linear, theta_deg, phi_angles_deg)
        if "boresight_theta" in compute_set or not need: row["boresight_theta"] = round(bs_theta, 1)
        if "boresight_phi" in compute_set or not need: row["boresight_phi"] = round(bs_phi, 1)

    if "max_power" in compute_set or not need: row["max_power"] = round(compute_peak_eirp(gain_linear), 2)
    if "min_power" in compute_set or not need: row["min_power"] = round(compute_min_power_dbm(gain_linear), 2)
    if "avg_gain" in compute_set or not need: row["avg_gain"] = round(compute_average_gain_db(gain_linear), 2)
    if "avg_power" in compute_set or not need: row["avg_power"] = round(compute_average_power_dbm(gain_linear), 2)

    # Power ratios + Beamwidth
    if any(c in compute_set for c in ("max_min_ratio", "max_avg_ratio", "min_avg_ratio",
                                 "theta_bw", "phi_bw", "front_back_ratio")) or not need:
        max_p = float(np.max(gain_linear)); min_p = float(np.min(gain_linear[gain_linear>1e-15]) if np.any(gain_linear>1e-15) else 1e-15)
        avg_p = float(np.mean(gain_linear))
        ratios = compute_power_ratios(10*np.log10(max(max_p,1e-15)), 10*np.log10(max(min_p,1e-15)), 10*np.log10(max(avg_p,1e-15)))
        for k, v in ratios.items(): row[k] = v
        bw = compute_beamwidth(gain_linear, theta_deg, phi_angles_deg)
        for k, v in bw.items(): row[k] = v if v is not None else 0

    # Axial Ratio (仅当有 Phase 数据且需要 AR 列)
    # 若 output_config 要求 AR 方位面图，强制计算 AR
    ar_need = compute_set & {"axial_ratio", "ar_single", "ar_range"}
    az_force_ar = (output_config is not None and False)
    if ar_need or az_force_ar or not need:
        tp = raw.get("theta_phase"); pp = raw.get("phi_phase")
        if tp is not None and pp is not None:
            try:
                if need_extrap:
                    _, tp = extrapolate_theta(theta_orig, tp, "constant")
                    _, pp = extrapolate_theta(theta_orig, pp, "constant")
                ar_result = compute_axial_ratio(theta_lm, tp, phi_lm, pp)
                if ar_result is not None and ar_result[0].size > 0:
                    ar, _, _ = ar_result
                    # AR 使用独立的 ar_lag_config 或 fallback 到 lag_config
                    ar_cfg = ar_lag_config if ar_lag_config is not None and not ar_lag_config.is_empty() else lag_config
                    ar_singles = ar_cfg.singles_sorted
                    if ar_singles:
                        for angle, val in compute_ar_at_angles(ar, theta_deg, ar_singles).items():
                            if ar_output_db:
                                val = 20.0 * math.log10(max(val, 1e-15))
                            row[f"ar_single_{angle}"] = round(val, 6)
                    # AR 范围
                    ar_ranges = ar_cfg.ranges_sorted
                    if ar_ranges:
                        for (lo, hi), val in [(r, compute_ar_range(ar, theta_deg, r[0], r[1])) for r in ar_ranges]:
                            if ar_output_db:
                                val = 20.0 * math.log10(max(val, 1e-15))
                            row[f"ar_range_{lo}_{hi}"] = round(val, 6)
                    # 向后兼容的 axial_ratio 字段
                    if "axial_ratio" in compute_set or not need:
                        legacy_ar = float(np.mean(ar[0, :5]))  # ar is set above from ar_result
                        if ar_output_db:
                            legacy_ar = 10.0 * math.log10(max(legacy_ar, 1e-15))
                        row["axial_ratio"] = round(legacy_ar, 6)
            except Exception as e:
                row["axial_ratio_error"] = str(e)

    # Cross-Polarization Isolation (XPI)
    xpi_need = compute_set & {"xpi_boresight", "xpi_mean", "xpi_min"}
    if xpi_need or not need:
        xpi_result = compute_xpi(theta_lm, phi_lm)
        if "xpi_boresight" in compute_set or not need:
            row["xpi_boresight"] = round(xpi_result["xpi_boresight"], 6)
        if "xpi_mean" in compute_set or not need:
            row["xpi_mean"] = round(xpi_result["xpi_mean"], 6)
        if "xpi_min" in compute_set or not need:
            row["xpi_min"] = round(xpi_result["xpi_min"], 6)

    # Total Efficiency (含 S11 反射损耗 — S11 当前不可用, 标记为 None)
    te_need = compute_set & {"total_efficiency_pct", "mismatch_loss_db"}
    if te_need or not need:
        if directivity_dbi is None:
            directivity_dbi = compute_directivity(gain_linear, theta_rad)
        te_eff_pct, _ = compute_efficiency(peak_dbi, directivity_dbi)
        te_result = compute_total_efficiency(te_eff_pct)
        if te_result and ("total_efficiency_pct" in compute_set or not need):
            if te_result.get("total_efficiency_pct") is not None:
                row["total_efficiency_pct"] = round(te_result["total_efficiency_pct"], 6)
        if te_result and ("mismatch_loss_db" in compute_set or not need):
            if te_result.get("mismatch_loss_db") is not None:
                row["mismatch_loss_db"] = round(te_result["mismatch_loss_db"], 6)
        # total_efficiency_pct 为 None 说明 S11 数据未提供
        if te_result["total_efficiency_pct"] is None and log_cb:
            _log(log_cb,
                 f"  ℹ {freq} MHz: Total Efficiency 需 S11 (回波损耗) 数据，当前标记为 None")

    # Phase Center (仅当有 Phase 数据)
    pc_need = compute_set & {"pc_theta_mm", "pc_phi_mm"}
    if pc_need or not need:
        tp_r = raw.get("theta_phase"); pp_r = raw.get("phi_phase")
        if tp_r is not None and pp_r is not None:
            pc_result = compute_phase_center(tp_r, pp_r, theta_deg, freq)
            if "pc_theta_mm" in compute_set or not need:
                row["pc_theta_mm"] = round(pc_result["pc_theta_mm"], 6)
            if "pc_phi_mm" in compute_set or not need:
                row["pc_phi_mm"] = round(pc_result["pc_phi_mm"], 6)

    # LAG
    singles = lag_config.singles_sorted
    if singles:
        for angle, val in compute_lag_at_angles(gain_linear, theta_deg, singles).items():
            row[f"lag_single_{angle}"] = round(val, 6)
    ranges = lag_config.ranges_sorted
    if ranges:
        for (lo, hi), val in compute_lag_ranges(gain_linear, theta_deg, ranges).items():
            row[f"lag_range_{lo}_{hi}"] = round(val, 6)

    # ── RHCP/LHCP Gain + CP-XPI (始终计算, 查看器需要 + 轻量公式) ──
    always_compute_rhcp = True
    if always_compute_rhcp:
        tp = raw.get("theta_phase"); pp = raw.get("phi_phase")
        if tp is not None and pp is not None:
            try:
                from .calculator import compute_cp_xpi, compute_rhcp_lhcp_gain
                if need_extrap:
                    _, tp = extrapolate_theta(theta_orig, tp, "constant")
                    _, pp = extrapolate_theta(theta_orig, pp, "constant")
                rhcp_g, lhcp_g = compute_rhcp_lhcp_gain(theta_lm, tp, phi_lm, pp)
                cp_xpi = compute_cp_xpi(rhcp_g, lhcp_g)

                if True:  # RHCP single always computed — 与 AR 一致取 φ 最大值
                    singles = (rhcp_lag_config if rhcp_lag_config and not rhcp_lag_config.is_empty() else lag_config).singles_sorted
                    for angle in singles:
                        idx = int(np.argmin(np.abs(theta_deg - angle)))
                        val = float(np.max(rhcp_g[:, idx]))  # max over φ, same as AR
                        row[f"rhcp_single_{angle}"] = round(val, 6)
                if (rhcp_lag_config if rhcp_lag_config and not rhcp_lag_config.is_empty() else lag_config).ranges_sorted:
                    for (lo, hi), val in compute_lag_ranges(
                        rhcp_g, theta_deg,
                        (rhcp_lag_config if rhcp_lag_config and not rhcp_lag_config.is_empty() else lag_config).ranges_sorted
                    ).items():
                        row[f"rhcp_range_{lo}_{hi}"] = round(val, 6)

                cp_cfg = cpxpi_lag_config if cpxpi_lag_config and not cpxpi_lag_config.is_empty() else lag_config
                if cp_cfg.singles_sorted:
                    cp_linear = 10.0 ** (cp_xpi / 10.0)  # dB → linear
                    for angle, val in compute_lag_at_angles(
                        cp_linear, theta_deg, cp_cfg.singles_sorted
                    ).items():
                        row[f"cp_xpi_single_{angle}"] = round(val, 6)
                if cp_cfg.ranges_sorted:
                    for (lo, hi), val in compute_lag_ranges(
                        cp_xpi, theta_deg, cp_cfg.ranges_sorted
                    ).items():
                        row[f"cp_xpi_range_{lo}_{hi}"] = round(val, 6)
            except Exception as e:
                row["rhcp_error"] = str(e)

        # RHCP/LHCP 矩阵存储供查看器使用
        if tp is not None and pp is not None and "_rhcp_gain" not in row:
            try:
                from .calculator import compute_rhcp_lhcp_gain
                rhcp_g, lhcp_g = compute_rhcp_lhcp_gain(theta_lm, tp, phi_lm, pp)
                row["_rhcp_gain"] = rhcp_g
                row["_lhcp_gain"] = lhcp_g
                row["_cp_xpi"] = rhcp_g - lhcp_g
            except Exception:
                pass

    # 计算总增益 dB 矩阵 (供图形和 2D Cuts 使用)
    gain_dbi = 10.0 * np.log10(np.maximum(gain_linear, 1e-15))

    az_need = (output_config is not None and output_config.has_any_azimuth)
    want_render = (chart_config is not None and chart_config.has_any_pattern_or_cut) or az_need

    n_phi = phi_lm.shape[0]
    _pa = raw.get("_phi_angles")
    phi_angles = np.array(_pa, dtype=np.float64) if _pa is not None and len(_pa) else np.arange(n_phi, dtype=np.float64)
    ar_lin = None

    # ── 图形生成 (仅图表/方位面驱动; matplotlib 仅非 compute_only) ──
    if want_render:
        try:
            from .plotter import generate_all_for_frequency
            ccfg = chart_config if chart_config is not None else ChartConfig()
            need_ar_for_graphics = (
                ccfg.pattern_3d_ar or
                any("ar" in str(e[0]) for e in getattr(ccfg, 'cut_2d_polar_entries', []))
                or any("ar" in str(e[0]) for e in getattr(ccfg, 'cut_2d_rect_entries', []))
                or any("ar" in str(e[0]) for e in getattr(ccfg, 'cut_azimuth_polar_entries', []))
                or any("ar" in str(e[0]) for e in getattr(ccfg, 'cut_azimuth_rect_entries', []))
            )
            if need_ar_for_graphics and "axial_ratio" not in str(row.get("axial_ratio_error", "")):
                tp = raw.get("theta_phase"); pp = raw.get("phi_phase")
                if tp is not None and pp is not None:
                    ar_result = compute_axial_ratio(theta_lm, tp, phi_lm, pp)
                    if ar_result is not None:
                        ar_lin = ar_result[0]
            if not compute_only:
                extra_patterns = {}
                if ccfg.pattern_3d_etheta:
                    extra_patterns["3d_etheta"] = theta_lm
                if ccfg.pattern_3d_ephi:
                    extra_patterns["3d_ephi"] = phi_lm
                extra_patterns = extra_patterns if extra_patterns else None
                rhcp_db = row.get("_rhcp_gain")
                lhcp_db = row.get("_lhcp_gain")
                cpxpi_db = row.get("_cp_xpi")
                # 每图标题: 类别默认模板 (用户可逐实例覆盖 inst.title)
                _antenna = output_config.antenna_name if output_config is not None else ""
                _title_lang = output_config.title_lang if output_config is not None else "en"
                _titles = None
                if chart_instances:
                    from .chart_titles import build_title
                    _titles = {ci.image_key: build_title(ci, freq, _antenna, lang=_title_lang)
                               for ci in chart_instances if ci.enabled}
                # 按分类频点选择过滤: A类仅 selected_frequencies_a, C类仅 _c, B类全保留
                _fa = set(getattr(ccfg, 'selected_frequencies_a', [])) if ccfg else set()
                _fc = set(getattr(ccfg, 'selected_frequencies_c', [])) if ccfg else set()
                _filt_instances = None
                _saved_a = {}; _saved_c = {}      # 必须在 if 外初始化, finally 引用
                if _fa or _fc:
                    if chart_instances:
                        _filt_instances = [ci for ci in chart_instances
                            if not (getattr(ci.category, "value", ci.category) if hasattr(ci, 'category') else "") in ("A","C")
                            or (cat := getattr(ci.category, "value", ci.category) if hasattr(ci, 'category') else "",
                                (cat == "A" and freq in _fa) or (cat == "C" and freq in _fc) or cat not in ("A","C"))[1]]
                    # fallback: 无 instances 时临时关掉不在选中频点内的 ccfg bools
                    _saved_a = {}; _saved_c = {}
                    for _k in ('pattern_3d_gain','pattern_3d_eirp','pattern_3d_ar','pattern_3d_etheta','pattern_3d_ephi'):
                        if _fa and freq not in _fa and getattr(ccfg, _k, False):
                            _saved_a[_k] = True; setattr(ccfg, _k, False)
                    for _k in ('cut_2d_polar','cut_2d_rect','cut_azimuth_polar','cut_azimuth_rect'):
                        if _fc and freq not in _fc and getattr(ccfg, _k, False):
                            _saved_c[_k] = True; setattr(ccfg, _k, False)
                try:
                    images = generate_all_for_frequency(
                    theta_deg, phi_angles, gain_dbi,
                    freq, ccfg, ar_linear=ar_lin,
                    rhcp_db=rhcp_db, lhcp_db=lhcp_db,
                    cpxpi_db=cpxpi_db,
                    antenna_name=_antenna,
                    output_config=output_config,
                    extra_patterns=extra_patterns,
                    titles=_titles,
                    chart_instances=_filt_instances if _filt_instances is not None else chart_instances,
                )
                finally:
                    # 恢复 fallback 路径中被临时关闭的 ccfg bools
                    for _k, _ in _saved_a.items(): setattr(ccfg, _k, True)
                    for _k, _ in _saved_c.items(): setattr(ccfg, _k, True)
                if images:
                    row["_images"] = images
                if "_azimuth_theta_deg" not in row:
                    row["_azimuth_theta_deg"] = theta_deg.copy()
        except Exception as e:
            row["_graph_error"] = str(e)  # 图形生成失败不阻塞数据处理

    # ── 中间数据矩阵存储 (out_data 或 有图表时都存; 不触发 matplotlib 渲染) ──
    if store_matrices or want_render:
        try:
            row["_chart_gain_dbi"] = gain_dbi.copy()
            row["_chart_theta_deg"] = theta_deg.copy()
            row["_chart_phi_deg"] = phi_angles.copy()
            # AR 矩阵: 复用渲染算的 ar_lin, 否则从相位数据补算
            if ar_lin is None:
                _tp = raw.get("theta_phase"); _pp = raw.get("phi_phase")
                if _tp is not None and _pp is not None:
                    _arr = compute_axial_ratio(theta_lm, _tp, phi_lm, _pp)
                    if _arr is not None:
                        ar_lin = _arr[0]
            if ar_lin is not None and "_chart_ar_db" not in row:
                row["_chart_ar_db"] = 20.0 * np.log10(np.maximum(ar_lin, 1e-15))
            # Theta 范围峰值 (θ≤N 的 φ 向峰值)
            if output_config and output_config.pk_theta_ranges:
                for t_max in output_config.pk_theta_ranges:
                    mask = theta_deg <= t_max + 0.1
                    key_suffix = str(int(t_max))
                    row[f"_gain_pk_{key_suffix}_deg"] = theta_deg[mask].copy()
                    row[f"_gain_pk_{key_suffix}_db"] = np.max(gain_dbi[:, mask], axis=1)
        except Exception as e:
            row["_data_matrix_error"] = str(e)

    # 角度数组 (小, 始终存储)
    row["_theta_angles"] = list(theta_deg)
    row["_phi_angles"] = [float(i) for i in np.linspace(0, 360, phi_lm.shape[0], endpoint=False)]
    # 全分辨率矩阵: 仅 3D 查看器 / 中间数据导出需要, 报告生成不存储
    if store_matrices:
        row["_raw_data"] = {k: v for k, v in raw.items() if v is not None}
        row["theta_db"] = theta_lm
        row["phi_db"] = phi_lm
        row["gain_db"] = gain_dbi

    return row


# ---------------------------------------------------------------------------
# 查找最近频点
# ---------------------------------------------------------------------------

def _find_closest_freq(csv_freqs: list[float], target: float, tol=5.0) -> int | None:
    if not csv_freqs:
        return None
    best_idx = int(np.argmin([abs(f - target) for f in csv_freqs]))
    return best_idx if abs(csv_freqs[best_idx] - target) <= tol else None


# ---------------------------------------------------------------------------
# 模板工作表自动扩增
# ---------------------------------------------------------------------------

def _derive_sheet_name(reference_name: str, target_key: str) -> str:
    """从参考工作表名推导新工作表名。

    "5G1" + key="G2" → "5G2"
    "Antenna_G1" + key="G3" → "Antenna_G3"
    """
    m = re.search(r'G\d+', reference_name, re.IGNORECASE)
    tk = re.search(r'G\d+', target_key, re.IGNORECASE)
    if m and tk:
        return reference_name[:m.start()] + tk.group(0).upper() + reference_name[m.end():]
    return target_key


def _expand_template_sheets(
    sheets_info: list[SheetInfo],
    datasource_map: dict[str, DataSource],
    freq_source: str = "datasource",
    use_raw_name: bool = False,
) -> list[SheetInfo]:
    """当模板工作表数少于数据源数时，用第一个 sheet 为模板克隆其余 sheet。

    Args:
        sheets_info:    read_template() 返回的原始列表。
        datasource_map: {sheet_name: DataSource}。
        freq_source:    "datasource" → 新 sheet 用数据源频点；
                        "template" → 新 sheet 用模板最近邻匹配。
        use_raw_name:   True → 直接用 datasource_map 的键作工作表名，
                        丢弃旧工作表名，为每个数据源创建新工作表；
                        False → 从键名推导工作表名。

    Returns:
        扩展后的 SheetInfo 列表。
    """
    ref = sheets_info[0]

    if use_raw_name:
        # 文件名模式：丢弃旧工作表名，为每个数据源创建新工作表
        expanded: list[SheetInfo] = []
        matched_names: set = set()
    else:
        if len(sheets_info) >= len(datasource_map):
            return list(sheets_info)
        expanded = list(sheets_info)
        matched_names = {si.name for si in sheets_info}

    existing_ds_names = set(datasource_map.keys())

    # 找出有 datasource 但没对应 sheet 的名称
    unmatched = existing_ds_names - matched_names
    if not unmatched:
        return list(sheets_info)

    from .sheet_file_matcher import sanitize_sheet_name

    for ds_name in sorted(unmatched):
        if use_raw_name:
            new_name = sanitize_sheet_name(ds_name)
        else:
            from .sheet_file_matcher import extract_key
            key = extract_key(ds_name)
            new_name = sanitize_sheet_name(_derive_sheet_name(ref.name, key))

        # 深拷贝列头结构
        new_columns = [
            ColumnInfo(
                col_letter=c.col_letter,
                col_index=c.col_index,
                raw_header=c.raw_header,
                normalized_header=c.normalized_header,
                col_type=c.col_type,
            )
            for c in ref.columns
        ]

        ds = datasource_map[ds_name]
        if freq_source == "template":
            frequencies = list(ref.frequencies)
        else:
            frequencies = list(ds.frequencies)

        new_si = SheetInfo(
            name=new_name,
            header_row=ref.header_row,
            data_start_row=ref.data_start_row,
            data_end_row=ref.data_start_row + len(frequencies) - 1,
            columns=new_columns,
            frequencies=frequencies,
            lag_config=copy.deepcopy(ref.lag_config),
            theta_range=ref.theta_range,
        )
        expanded.append(new_si)

    return expanded


# ---------------------------------------------------------------------------
# 管线助手 — 任务收集 / 数据加载+计算
# ---------------------------------------------------------------------------

def _collect_tasks(
    sheets_info: list[Any],
    datasource: DataSource | None,
    datasource_map: dict[str, DataSource] | None,
    freq_source: str = "datasource",
    trim_start: int = 0,
    trim_end: int = 0,
    sheet_mode_map: dict[str, int] | None = None,
    log_cb=None,
) -> list[tuple[str, float, int, Any, DataSource]]:
    """收集所有 (sheet_name, freq, csv_idx, lag_cfg, ds) 任务。"""
    use_multi = datasource_map is not None
    tasks: list[tuple[str, float, int, Any, DataSource]] = []

    if use_multi:
        original_sheets = {si.name for si in sheets_info}
        all_ds_names = set(datasource_map.keys())
        expanded_names = all_ds_names - original_sheets
    else:
        expanded_names = set()

    for si in sheets_info:
        ds: DataSource | None = datasource_map.get(si.name) if use_multi else datasource
        if ds is None:
            if use_multi:
                _log(log_cb, f"  ⚠ {si.name}: 无匹配数据源 — 跳过")
            continue

        # 提取模板需要的参数类型
        needed_params = {c.col_type for c in si.columns}

        # 混合批处理: 记录 sheet 对应的测试模式
        smap = sheet_mode_map or {}
        sheet_mode = smap.get(si.name, 0)
        mode_label = {0: "无源", 1: "TRP", 2: "TIS"}.get(sheet_mode, "?")

        is_expanded = si.name in expanded_names if use_multi else False
        use_ds_freqs = (is_expanded and freq_source == "datasource")

        # 调试: 记录本 sheet 的频点来源信息
        ds_freq_count = len(ds.frequencies) if ds else 0
        tmpl_freq_count = len(si.frequencies) if si.frequencies else 0
        _log(log_cb, f"  [{si.name}] 数据源={ds_freq_count}频点, 模板={tmpl_freq_count}频点, expanded={is_expanded}")

        if not use_ds_freqs:
            dsfreqs = ds.frequencies
            match_count = 0
            for freq in si.frequencies:
                idx = _find_closest_freq(dsfreqs, freq)
                if idx is not None:
                    tasks.append((si.name, freq, idx, si.lag_config, ds, needed_params))
                    match_count += 1
            if match_count == 0 and dsfreqs:
                _log(log_cb, f"  ↻ {si.name}: 模板频点无匹配 → 使用数据源全部 {len(dsfreqs)} 个频点")
                use_ds_freqs = True
            elif match_count > 0:
                _log(log_cb, f"  ✓ {si.name}: 模板匹配 {match_count}/{tmpl_freq_count} 个频点")

        if use_ds_freqs:
            dsfreqs = ds.frequencies
            for idx, freq in enumerate(dsfreqs):
                tasks.append((si.name, freq, idx, si.lag_config, ds, needed_params))

    # ---- 频点裁剪 (trim_start/trim_end) ----
    if trim_start > 0 or trim_end > 0:
        # 按 sheet 分组、按 freq 排序后裁剪首尾
        from collections import OrderedDict
        grouped: dict[str, list] = OrderedDict()
        for t in tasks:
            grouped.setdefault(t[0], []).append(t)
        tasks = []
        for sn, group in grouped.items():
            group.sort(key=lambda x: x[1])  # 按 freq 排序
            end = len(group) - trim_end if trim_end > 0 else len(group)
            trimmed = group[trim_start:end]
            if trimmed:
                tasks.extend(trimmed)
            if trim_start > 0 or trim_end > 0:
                removed = len(group) - len(trimmed)
                if removed > 0:
                    _log(log_cb, f"  ✂ {sn}: 去除 {removed} 个频点 (前{trim_start}后{trim_end})")

    _log(log_cb, f"共 {len(tasks)} 个待处理频点")
    return tasks


def _load_and_compute(
    tasks: list[tuple[str, float, int, Any, DataSource]],
    sheets_info: list[Any],
    theta_extrap_method: str | None,
    robust_peak: bool,
    parallel: int,
    extra_params: set = None,
    chart_config: ChartConfig = None,
    ar_lag_config: LagConfig = None,
    sheet_ar_configs: dict[str, LagConfig] = None,
    output_config: OutputConfig = None,
    nh_custom_angles: list[float] | None = None,
    ar_output_db: bool = True,
    dir_extrap_method: str = "none",
    compute_only: bool = False,
    store_matrices: bool = False,
    chart_instances: list | None = None,
    antenna_freq_selection: list[float] | None = None,
    cancel_callback=None,
    progress_callback=None,
    log_callback=None,
) -> dict[str, list[dict[str, Any]]]:
    """加载原始数据并执行计算，返回 sheet_results。"""
    total = len(tasks)
    sheet_results: dict[str, list[dict[str, Any]]] = {si.name: [] for si in sheets_info}
    if total == 0:
        return sheet_results

    if sheet_ar_configs is None:
        sheet_ar_configs = {}

    # 统一进度条: 权重在频点过滤后重新计算

    # 频点过滤 — 天线参数与图表独立
    #   天线频点: 空列表=全部频点, 非空=只计算指定频点
    #   图表频点: per-instance 层(lines 510-544)独立处理, 不参与全局任务过滤
    #   仅当天线参数有特定频点选择时, 才限制任务(并集图表频点以确保图表也渲染)
    if chart_config and antenna_freq_selection:
        ant_sel = set(antenna_freq_selection)
        chart_sel = (set(getattr(chart_config, 'selected_frequencies_a', []))
                     | set(getattr(chart_config, 'selected_frequencies_b', []))
                     | set(getattr(chart_config, 'selected_frequencies_c', [])))
        sel = ant_sel | chart_sel
        if sel:
            orig_total = len(tasks)
            tasks = [t for t in tasks if t[1] in sel]
            _log(log_callback, f"🎯 频点过滤: {len(tasks)}/{orig_total} 个频点 (天线={len(ant_sel)} + 图表={len(chart_sel)})")

    # 重新计算权重 (total 可能因过滤减少)
    total = len(tasks)
    _load_w = max(total, 1)
    _calc_w = max(total, 1)            # 计算很快, 占1x
    _render_w = max(total * 5, 1)      # 渲染慢, 占5x
    _compute_w = _calc_w + _render_w
    _export_w = 10
    _word_w = 10
    progress_max = _load_w + _compute_w + _export_w + _word_w

    # ── 阶段 1: 读取源文件 ──
    _log(log_callback, f"📂 读取 {total} 个频点数据...")
    _report(progress_callback, 0, progress_max, f"[📂] 读取源文件 0/{len(tasks)}")
    compute_tasks = []
    _phi_warned = False
    for i, (sheet_name, freq, csv_idx, lag_cfg, task_ds, needed_params) in enumerate(tasks):
        if cancel_callback and cancel_callback():
            break
        raw = task_ds.read_sections(csv_idx)
        theta_list = list(task_ds.theta_angles)
        phi_list = list(task_ds.phi_angles) if hasattr(task_ds, 'phi_angles') else []
        raw["_phi_angles"] = phi_list if phi_list else None
        # 检测 phi 轴完整性 (仅警告一次)
        if not _phi_warned and len(phi_list) >= 2:
            _phi_warned = True
            _over = [p for p in phi_list if p >= 360.0]
            _valid = [p for p in phi_list if p < 360.0]
            _dphi = phi_list[1] - phi_list[0]
            if _over:
                _log(log_callback,
                     f"⚠ phi 轴超出 360°: {len(_over)} 个冗余点 ({_over[0]:.1f}~{_over[-1]:.1f}°), "
                     f"已自动裁剪, 保留 {len(_valid)} 点")
            if _valid:
                _expect = _valid[-1] + _dphi  # 最后角 + 步进 应≈360
                if abs(_expect - 360.0) > _dphi * 0.5:
                    _log(log_callback,
                         f"⚠ phi 轴不完整: {len(_valid)} 点, "
                         f"最后角={_valid[-1]:.1f}° + 步进={_dphi:.1f}° = {_expect:.1f}° "
                         f"(应≈360°), Directivity/AR/LAG 可能偏小")
        ar_cfg = ar_lag_config if ar_lag_config is not None and not ar_lag_config.is_empty() else sheet_ar_configs.get(sheet_name, LagConfig())
        compute_tasks.append((sheet_name, freq, raw, lag_cfg, theta_list, theta_extrap_method, robust_peak, needed_params, extra_params, chart_config, ar_cfg, nh_custom_angles, ar_output_db, output_config, compute_only, store_matrices, chart_instances, dir_extrap_method))
        _report(progress_callback, i + 1, progress_max, f"[📂] 读取源文件 {i+1}/{total}")

    data_done = _load_w
    _report(progress_callback, data_done, progress_max, f"[🧮] 计算参数 0/{len(compute_tasks)}")

    # ── 阶段 2: 计算天线参数 ──
    # 是否真的会渲染图表 (与 _process_one_frequency 的渲染门保持一致)。
    # 无图表配置且无方位面时不渲染，进度也不应显示"渲染图表"步骤。
    _will_render = (
        ((chart_config is not None and chart_config.has_any_pattern_or_cut)
         or (output_config is not None and output_config.has_any_azimuth))
        and not compute_only
    )
    if parallel > 1 and len(compute_tasks) > 1:
        _log(log_callback, f"并行计算: {parallel} 进程 × {len(compute_tasks)} 频点")
        _report(progress_callback, data_done, progress_max, "[🧮] 启动并行引擎...")
        chunks = [compute_tasks[i:i + 1] for i in range(0, len(compute_tasks), 1)]
        try:
            with ProcessPoolExecutor(max_workers=parallel) as executor:
                futures = [executor.submit(_compute_chunk, chunk) for chunk in chunks]
                completed = 0
                for fut in futures:
                    if cancel_callback and cancel_callback():
                        for f in futures:
                            f.cancel()
                        break
                    for sheet_name, row in fut.result(timeout=300):
                        sheet_results[sheet_name].append(row)
                        completed += 1
                    step = data_done + int(_calc_w * completed / len(compute_tasks))
                    _report(progress_callback, step, progress_max,
                            f"[🧮] 计算参数 {completed}/{len(compute_tasks)}")
                    if _will_render:
                        rstep = data_done + _calc_w + int(_render_w * completed / len(compute_tasks))
                        _report(progress_callback, rstep, progress_max,
                                f"[🎨] 渲染图表 {completed}/{len(compute_tasks)}")
        except (PermissionError, OSError, RuntimeError) as e:
            _log(log_callback, f"⚠ 并行引擎启动失败: {e} → 自动降级为串行")
            _run_compute_serial(compute_tasks, sheet_results, data_done, progress_max,
                                cancel_callback, progress_callback, log_cb=log_callback,
                                output_config=output_config,
                                dir_extrap_method=dir_extrap_method,
                                calc_w=_calc_w, render_w=_render_w,
                                compute_total=len(compute_tasks))
    else:
        _run_compute_serial(compute_tasks, sheet_results, data_done, progress_max,
                            cancel_callback, progress_callback, log_cb=log_callback,
                            output_config=output_config,
                            dir_extrap_method=dir_extrap_method,
                            calc_w=_calc_w, render_w=_render_w,
                            compute_total=len(compute_tasks))

    return sheet_results


def _run_compute_serial(
    compute_tasks, sheet_results, data_done, progress_max,
    cancel_callback, progress_callback, log_cb=None, output_config=None,
    dir_extrap_method="none",
    calc_w=None, render_w=None, compute_total=None,
):
    """串行逐频点计算（单进程或 parallel=1）。"""
    total_tasks = compute_total or len(compute_tasks)
    cw = calc_w or max(total_tasks * 4, 1)
    rw = render_w or max(total_tasks * 2, 1)
    for i, (sheet_name, freq, raw, lag_cfg, theta_list, do_extrap, rpk, nparams, xparams, ccfg, ar_cfg, nh_angles, ar_out_db, az_cfg, co, sm, cinst, de) in enumerate(compute_tasks):
        if cancel_callback and cancel_callback():
            break
        try:
            theta_arr = np.array(theta_list)
            row = _process_one_frequency(raw, freq, theta_arr, lag_cfg, theta_extrap_method=do_extrap, robust_peak=rpk, needed_params=nparams, extra_params=xparams, chart_config=ccfg, ar_lag_config=ar_cfg, rhcp_lag_config=None, cpxpi_lag_config=None, output_config=az_cfg, nh_custom_angles=nh_angles, ar_output_db=ar_out_db, dir_extrap_method=de, compute_only=co, store_matrices=sm, chart_instances=cinst, log_cb=log_cb)
            sheet_results[sheet_name].append(row)
        except Exception as e:
            sheet_results[sheet_name].append({"frequency": freq, "_error": str(e)})
        if (i + 1) % 3 == 0 or (i + 1) == total_tasks:
            step = int(cw * (i + 1) / total_tasks)
            _report(progress_callback, data_done + step, progress_max,
                    f"[🧮] 计算参数 {i+1}/{total_tasks}")
            # 渲染进度 (calc 完成后进入 render)
            # 用最后追加的结果 (含异常 stub), 避免所有频点异常时 row 未绑定 → UnboundLocalError 掩盖真错
            _last = sheet_results[sheet_name][-1] if sheet_results.get(sheet_name) else {}
            has_imgs = bool(_last.get("_images")) or bool(_last.get("_graph_error"))
            if has_imgs:
                rstep = data_done + cw + int(rw * (i + 1) / total_tasks)
                _report(progress_callback, rstep, progress_max,
                        f"[🎨] 渲染图表 {i+1}/{total_tasks}")


def _close_datasources(
    use_multi: bool,
    datasource: DataSource | None,
    datasource_map: dict[str, DataSource] | None,
):
    """安全关闭所有数据源。"""
    if use_multi and datasource_map:
        for ds in datasource_map.values():
            try:
                ds.close()
            except Exception:
                pass
    elif datasource:
        datasource.close()


# ---------------------------------------------------------------------------
# 无模板时的数据源推导
# ---------------------------------------------------------------------------

def _build_sheets_from_datasource(
    datasource_map: dict[str, DataSource],
) -> list[SheetInfo]:
    """无模板时从数据源构建最小 SheetInfo 列表。"""
    from .excel_reader import SheetInfo
    sheets = []
    for name, ds in datasource_map.items():
        freqs = sorted(set(ds.frequencies))
        sheets.append(SheetInfo(
            name=name, header_row=0, data_start_row=0, data_end_row=0,
            frequencies=freqs))
    return sheets


# ---------------------------------------------------------------------------
# 主管线
# ---------------------------------------------------------------------------

def run_pipeline(
    datasource: DataSource | None = None,
    template_path: str = "",
    output_path: str = "",
    *,
    datasource_map: dict[str, DataSource] | None = None,
    sheet_mode_map: dict[str, int] | None = None,
    lag_config_override: LagConfig | None = None,
    ar_lag_config_override: LagConfig | None = None,
    plot_config: PlotConfig | None = None,
    full_report_path: str | None = None,
    compute_only: bool = False,  # True → 只计算不导出 (预览模式)
    theta_extrap_method: str | None = None,
    freq_source: str = "datasource",
    trim_start: int = 0,
    trim_end: int = 0,
    chart_config_obj: ChartConfig | None = None,
    output_config: OutputConfig | None = None,
    out_excel: bool = True,
    out_word: bool = False,
    out_data: bool = False,
    word_template_path: str | None = None,  # Word 模板路径 (为空则自动生成)
    dir_extrap_method: str = "none",  # Directivity 外推: none|linear|constant|mirror
    robust_peak: bool = False,
    extra_params: set | None = None,
    nh_custom_angles: list[float] | None = None,
    ar_output_db: bool = True,
    worksheet_naming_mode: int = 0,  # 0=保留模板工作表名, 1=用数据源名
    chart_instances: list | None = None,  # ChartInstance 列表, 为空则使用旧行为
    antenna_freq_selection: list[float] | None = None,  # 天线参数频点选择 (空=全频点)
    parallel: int = 1,
    cancel_callback: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """执行完整处理管线。

    Args:
        datasource:          数据源 (单源模式，向后兼容)。
        template_path:       模板 Excel 路径。
        output_path:         输出 Excel 路径。
        datasource_map:      工作表名→DataSource 映射 (多源模式)。
                             为 None 时使用 datasource 参数 (单源模式)。
        lag_config_override: LAG 配置覆盖。
        plot_config:         3D 图配置 (默认: 不生成图)。
        full_report_path:    完整报告路径。
        theta_extrap_method: Theta 外推算法 (None=不外推, linear/constant/mirror)。
        freq_source:         "datasource" 或 "template"。
                             当模板 sheet 数<数据源数时，新 sheet 的频点来源。
        parallel:            (保留参数，当前仅串行)。
        cancel_callback / progress_callback / log_callback: 同旧版。

    Returns:
        {sheet_name: [row_dict, ...]}
    """
    if plot_config is None:
        plot_config = PlotConfig(embed_in_excel=False)

    t0 = time.time()

    # ---- 0. 参数校验 ----
    _log(log_callback, f"AR 输出: {'dB (20·log₁₀)' if ar_output_db else '线性比值'}")
    if datasource_map is not None and datasource is not None:
        raise ValueError("datasource 和 datasource_map 互斥，只能提供一个")
    if datasource_map is None and datasource is None:
        raise ValueError("必须提供 datasource 或 datasource_map")
    use_multi_ds = datasource_map is not None

    # ---- 1. 读取模板 (无模板时从数据源推导) ----
    if template_path and os.path.exists(template_path):
        _log(log_callback, f"读取模板: {template_path}")
        sheets_info = read_template(template_path)
        for si in sheets_info:
            _log(log_callback, f"  {si.name}: {len(si.frequencies)} 频点")
    else:
        _log(log_callback, "无模板 — 从数据源推导频点")
        sheets_info = _build_sheets_from_datasource(datasource_map or {"default": datasource})
        for si in sheets_info:
            _log(log_callback, f"  {si.name}: {len(si.frequencies)} 频点")

    # ---- 1.5: 自动扩增工作表 (模板 sheet 数 < 数据源数, 或文件名模式) ----
    template_sheet_names_to_remove: list[str] | None = None
    if use_multi_ds:
        template_names = {si.name for si in sheets_info}
        ds_names = set(datasource_map.keys())
        matched_count = len(template_names & ds_names)
        if worksheet_naming_mode == 1:
            # 文件名模式: 用第一个 sheet 做模板, datasource_map 键直接作工作表名
            _log(log_callback, f"文件名模式: {len(datasource_map)} 个数据源 → 创建 {len(datasource_map)} 个工作表...")
            template_sheet_names_to_remove = [si.name for si in sheets_info]
            ref_sheet = sheets_info[0:1]
            sheets_info = _expand_template_sheets(ref_sheet, datasource_map, freq_source, use_raw_name=True)
            for si in sheets_info:
                _log(log_callback, f"  {si.name}: {len(si.frequencies)} 频点")
        elif len(sheets_info) < len(datasource_map):
            _log(log_callback, f"模板 {len(sheets_info)} 个工作表 → {len(datasource_map)} 个数据源，自动扩增...")
            sheets_info = _expand_template_sheets(sheets_info, datasource_map, freq_source)
            for si in sheets_info:
                _log(log_callback, f"  {si.name}: {len(si.frequencies)} 频点 (来源: {'数据源' if freq_source == 'datasource' else '模板'})")

    if lag_config_override is not None and not lag_config_override.is_empty():
        for si in sheets_info:
            si.lag_config = lag_config_override
        _log(log_callback, "使用用户指定的 LAG 配置")

    # ---- 构建 sheet→AR 配置映射 (自动检测或使用覆盖) ----
    sheet_ar_configs: dict[str, LagConfig] = {}
    if ar_lag_config_override is not None and not ar_lag_config_override.is_empty():
        # 用户覆盖: 所有 sheet 用同一个 AR 配置
        for si in sheets_info:
            sheet_ar_configs[si.name] = ar_lag_config_override
        _log(log_callback, "使用用户指定的 AR 配置")
    else:
        # 自动检测: 从模板列头解析 AR 角度
        for si in sheets_info:
            if si.ar_config is not None and not si.ar_config.is_empty():
                sheet_ar_configs[si.name] = si.ar_config
        if sheet_ar_configs:
            total_angles = sum(len(c.singles_sorted) + len(c.ranges_sorted) for c in sheet_ar_configs.values())
            _log(log_callback, f"自动检测到 {total_angles} 个 AR 角度 (来自 {len(sheet_ar_configs)} 个 sheet)")

    # ---- 2. 预览缓存: 仅纯 Excel 导出可用 ----
    # 缓存 (_save_preview_cache) 剥掉了 row["_images"] 等 "_" 开头字段, 所以图表/Word/完整报告
    # 导出必须重新计算+渲染, 不能走缓存跳过 (否则 image_groups 为空 → Word 静默不生成)。
    _need_charts = out_word or out_data or bool(full_report_path)
    if not compute_only and not _need_charts:
        cached = _load_preview_cache(output_config, output_path, template_path)
        if cached is not None:
            _log(log_callback, "📦 复用预览缓存数据, 跳过计算 (纯 Excel)")
            sheet_results = cached
            _close_datasources(use_multi_ds, datasource, datasource_map)
            # 直接跳到导出阶段
            skip_to_export = True
        else:
            skip_to_export = False
    else:
        skip_to_export = False

    # ---- 3. 收集任务 + 加载数据 + 计算 ----
    if not skip_to_export:
        tasks = _collect_tasks(sheets_info, datasource, datasource_map, freq_source, trim_start, trim_end, sheet_mode_map, log_callback)
        try:
            sheet_results = _load_and_compute(
                tasks, sheets_info, theta_extrap_method, robust_peak, parallel,
                extra_params=extra_params, chart_config=chart_config_obj,
                ar_lag_config=ar_lag_config_override,
                sheet_ar_configs=sheet_ar_configs,
                output_config=output_config,
                nh_custom_angles=nh_custom_angles,
                ar_output_db=ar_output_db,
                dir_extrap_method=dir_extrap_method,
                compute_only=compute_only,
                store_matrices=out_data,
                chart_instances=chart_instances,
                antenna_freq_selection=antenna_freq_selection,
                cancel_callback=cancel_callback, progress_callback=progress_callback, log_callback=log_callback,
            )
        finally:
            _close_datasources(use_multi_ds, datasource, datasource_map)

    # ── compute_only 模式下跳过所有导出步骤 ──
    if compute_only:
        # 保存预览缓存（不含图片 bytes，供下次导出复用）
        _save_preview_cache(sheet_results, output_config, output_path, template_path)
        _log(log_callback, "⏭ 预览模式 — 跳过 Excel/Word/报告导出")
        elapsed = time.time() - t0
        total_rows = sum(len(v) for v in sheet_results.values())
        _log(log_callback, f"✓ 计算完成: {total_rows} 行, {elapsed:.1f}s")
        _report(progress_callback, 1, 1, "✅ 预览就绪")
        return sheet_results

    # ── 阶段 4: 输出 Excel 天线参数 (统一 progress_max) ──
    # skip_to_export(命中预览缓存)时无 tasks, 用缓存行数估进度权重
    total = len(tasks) if not skip_to_export else sum(len(v) for v in sheet_results.values())
    _load_w = max(total, 1)
    _calc_w = max(total, 1); _render_w = max(total * 5, 1)
    _compute_w = _calc_w + _render_w
    _base = _load_w + _compute_w
    _export_w = 10  # Excel 导出权重
    _word_w = 10    # Word 导出权重
    progress_max = _base + _export_w + _word_w

    if out_excel and output_path:
        _log(log_callback, f"📊 写入 Excel: {output_path}")
        _report(progress_callback, _base, progress_max, "[📊] 输出 Excel 天线参数...")
        export_results(
            template_path=template_path,
            output_path=output_path,
            sheet_results=sheet_results,
            pattern_images=None,
            sheets_info=sheets_info,
            chart_config=chart_config_obj,
            log_callback=log_callback,
            remove_template_sheets=template_sheet_names_to_remove,
        )
        _report(progress_callback, _base + _export_w, progress_max, "[📊] Excel 写入完成")
    elif not out_excel:
        _log(log_callback, "⏭ 跳过天线参数 Excel 输出")
        _report(progress_callback, _base + _export_w, progress_max, "[📊] 跳过 Excel")

    # ---- 4. 完整报告 (可选) ----
    if full_report_path:
        _log(log_callback, f"生成完整报告: {full_report_path}")
        imgs_3d, imgs_2d_polar, imgs_2d_rect = _collect_report_images(sheet_results)
        export_full_report(
            output_path=full_report_path,
            sheet_results=sheet_results,
            pattern_images_3d=imgs_3d if imgs_3d else None,
            pattern_images_2d_polar=imgs_2d_polar if imgs_2d_polar else None,
            pattern_images_2d_rect=imgs_2d_rect if imgs_2d_rect else None,
        )

    # ── 阶段 5: 输出 Word 图表报告 ──
    _export_ok = True  # 跟踪导出是否全部成功
    if out_word or out_data:
        _report(progress_callback, _base + _export_w, progress_max, "[📄] 输出 Word 图表报告...")
        _export_ok = _export_azimuth(sheet_results, output_config, log_callback,
                        out_word=out_word, out_data=out_data,
                        word_template_path=word_template_path,
                        chart_instances=chart_instances,
                        chart_config_obj=chart_config_obj)
        _report(progress_callback, progress_max, progress_max, "[✅] 完成")
    else:
        _report(progress_callback, progress_max, progress_max, "[✅] 完成")

    elapsed = time.time() - t0
    total_rows = sum(len(v) for v in sheet_results.values())
    _log(log_callback, f"✓ 完成: {total_rows} 行, {elapsed:.1f}s")

    # 导出成功后清除预览缓存（失败时保留供重试）
    if _export_ok:
        _delete_preview_cache(output_config, output_path)

    return sheet_results

# ---------------------------------------------------------------------------
# 报告图片收集
# ---------------------------------------------------------------------------

def _collect_report_images(
    sheet_results: dict[str, list[dict[str, Any]]],
) -> tuple:
    """从处理结果收集图片，按 3D/2D Polar/2D Rect 分类。

    图片在 _process_one_frequency 中已渲染为 PNG BytesIO，
    存入 row["_images"]。此函数按 report_exporter 期望的格式重组。

    Returns:
        (images_3d, images_2d_polar, images_2d_rect)
        - images_3d:        {sheet_name: {freq: BytesIO}}
        - images_2d_polar:  {sheet_name: {freq: {cut_label: BytesIO}}}
        - images_2d_rect:   {sheet_name: {freq: {cut_label: BytesIO}}}
    """
    images_3d: dict[str, dict[float, io.BytesIO]] = {}
    images_2d_polar: dict[str, dict[float, dict[str, io.BytesIO]]] = {}
    images_2d_rect: dict[str, dict[float, dict[str, io.BytesIO]]] = {}

    for sheet_name, rows in sheet_results.items():
        for row in rows:
            freq = row.get("frequency")
            if freq is None:
                continue
            imgs = row.get("_images", {})
            if not imgs:
                continue
            for img_key, buf in imgs.items():
                if buf is None:
                    continue
                if img_key.startswith("3d_"):
                    images_3d.setdefault(sheet_name, {})[freq] = buf
                elif img_key.startswith("2d_polar_"):
                    cut_label = img_key[len("2d_polar_"):]
                    images_2d_polar.setdefault(sheet_name, {}).setdefault(freq, {})[cut_label] = buf
                elif img_key.startswith("2d_rect_"):
                    cut_label = img_key[len("2d_rect_"):]
                    images_2d_rect.setdefault(sheet_name, {}).setdefault(freq, {})[cut_label] = buf

    return images_3d, images_2d_polar, images_2d_rect


# ---------------------------------------------------------------------------
# 方位面报告导出
# ---------------------------------------------------------------------------

def _export_azimuth(
    sheet_results: dict[str, list[dict[str, Any]]],
    output_config: OutputConfig,
    log_callback=None,
    out_word: bool = True,
    out_data: bool = True,
    word_template_path: str | None = None,
    chart_instances: list | None = None,
    chart_config_obj: ChartConfig | None = None,
):
    """从处理结果中收集方位面图片和中间数据，写入 Word 和 Excel。

    当 word_template_path 不为空时，使用 WordReporter 填充模板；
    否则使用 chart_word_writer 自动生成 Word 报告。

    chart_instances: 若提供, 仅收集 enabled=True 的实例, 按 sort_order 排序。
    """
    from pathlib import Path

    from .azimuth_data_writer import write_azimuth_data
    from .chart_word_writer import write_chart_word_report

    # ── 收集所有图片和中间数据 ──
    _word_ok = True   # Word 导出是否成功（供调用方决定是否清理缓存）
    _data_ok = True   # 中间数据导出是否成功
    image_groups: dict[str, dict[float, io.BytesIO]] = {}


    # ── 从 chart_instances 构建 image_key → label 映射 (主数据源) ──
    # chart_plan.py 已为每个 ChartInstance 生成了正确的 label 和 image_key,
    # 此处直接使用, 避免在 pipeline 中重复硬编码标签逻辑.
    _image_key_to_label: dict[str, str] = {}
    if chart_instances:
        for ci in chart_instances:
            if ci.enabled and ci.image_key:
                _image_key_to_label[ci.image_key] = ci.label

    # 图片类型 → 用户可读组名 (仅作回退, 主数据源是 _image_key_to_label)
    def _label_for_image_key(img_key: str) -> str:
        """将 image key 映射为 Word 标题。

        优先使用 chart_instances 中的 label (由 chart_plan 生成, 非硬编码),
        回退逻辑仅处理无 instance 的图片 (如 PK theta 范围峰值).
        """
        # 主数据源: chart_instances
        if img_key in _image_key_to_label:
            return _image_key_to_label[img_key]

        # ── 回退: 无 instance 的图片 ──
        import re

        # PK theta 范围峰值: azimuth_polar_pk_70 → "PK Gain (θ=0°-70°)"
        m = re.match(r'azimuth_polar_pk_(\d+)', img_key)
        if m:
            t_max = m.group(1)
            return f"PK Gain (θ=0°-{t_max}°)"

        # 3D 多视角: 3d_gain_v0, 3d_eirp_v1 等
        from .chart_config import ChartConfig
        _LABELS = ChartConfig.chart_labels()
        if "_v" in img_key:
            base = img_key.rsplit("_v", 1)[0]
            for ck in ("pattern_3d_gain", "pattern_3d_eirp", "pattern_3d_ar"):
                if img_key.startswith(ck):
                    return _LABELS.get(ck, img_key)

        # 精确匹配 chart_labels
        for ck in _LABELS:
            if img_key == ck or img_key.startswith(ck):
                return _LABELS[ck]

        return img_key

    # 若提供实例列表，构建允许的 image_key 集合
    _enabled_keys: set | None = None
    if chart_instances:
        _enabled_keys = {ci.image_key for ci in chart_instances if ci.enabled}
    # cut_param 生成的新格式 key (含参数名), 豁免 chart_instances 过滤
    # 旧 key: 2d_polar_phi0, azimuth_polar
    # 新 key: 2d_polar_gain_phi0, azimuth_polar_gain_t30
    def _is_new_cut_key(k: str) -> bool:
        if k.startswith("2d_polar_") or k.startswith("2d_rect_"):
            return True
        if k.startswith("azimuth_polar_"):
            rest = k[len("azimuth_polar_"):]
            return bool(rest)  # 有后缀 → 新格式 (azimuth_polar 无后缀=旧)
        if k.startswith("azimuth_rect_"):
            return True
        return False

    _total_imgs = 0
    for sheet_name, rows in sheet_results.items():
        for row in rows:
            freq = row.get("frequency")
            if freq is None:
                continue
            images = row.get("_images", {})
            for img_key, buf in images.items():
                if buf is None:
                    continue
                if _enabled_keys is not None and img_key not in _enabled_keys:
                    if not _is_new_cut_key(img_key):
                        continue
                label = _label_for_image_key(img_key)
                if label not in image_groups:
                    image_groups[label] = {}
                if freq in image_groups[label]:
                    v = image_groups[label][freq]
                    image_groups[label][freq] = v if isinstance(v, list) else [v]
                    image_groups[label][freq].append(buf)
                else:
                    image_groups[label][freq] = buf
                _total_imgs += 1
    if _total_imgs == 0:
        # 诊断: 检查第一行看 _images 是否存在
        _sample_row = None
        for _sn, _rows in sheet_results.items():
            if _rows:
                _sample_row = _rows[0]; break
        _has_images_key = "_images" in (_sample_row or {})
        _imgs_val = _sample_row.get("_images", "N/A") if _sample_row else "N/A"
        _has_error = _sample_row.get("_error", "") if _sample_row else ""
        _log(log_callback,
             f"  ⚠ 未收集到图片 — _images_key={_has_images_key}, "
             f"imgs_count={len(_imgs_val) if isinstance(_imgs_val, dict) else _imgs_val}, "
             f"chart_has_c={getattr(chart_config_obj, 'has_any_c_class', '?') if chart_config_obj else '?'}, "
             f"error={_has_error}")

    # ── B 类: 频点曲线 PNG (Word 报告), 按 ChartInstance 驱动 ──
    _B_CHART_TO_PARAM = {
        "chart_eff_freq": ("efficiency_pct", "Efficiency (%)"),
        "chart_gain_freq": ("gain", "Peak Gain (dBi)"),
        "chart_dir_freq": ("directivity", "Directivity (dBi)"),
        "chart_trp_freq": ("trp", "TRP (dBm)"),
        "chart_lag_freq": ("lag_single", "LAG (dBi)"),
        "chart_ar_freq": ("ar_single", "AR (dB)"),
        "chart_trp_nhprp": ("nhprp_45", "NHPRP ±45°"),
    }
    # 当模板无 Efficiency 列但有 Gain+Directivity 时, 推导效率
    _flat = [r for rows in sheet_results.values() for r in rows]
    if _flat and "efficiency_pct" not in _flat[0] and "gain" in _flat[0] and "directivity" in _flat[0]:
        for r in _flat:
            g = r.get("gain"); d = r.get("directivity")
            if g is not None and d is not None:
                r["efficiency_pct"] = 10 ** ((g - d) / 10) * 100

    # 按 ChartInstance 渲染 B 类曲线: 仅生成 enabled 的实例
    _b_instances = [ci for ci in (chart_instances or [])
                    if ci.category.value == "B" and ci.enabled] if chart_instances else None
    from .plotter import _renderer as _freq_renderer
    for sheet_name, rows in sheet_results.items():
        for ci in (_b_instances or []):
            param_info = _B_CHART_TO_PARAM.get(ci.parent_type)
            if not param_info:
                continue
            param_key, param_label = param_info
            freqs = []; values = []
            for row in rows:
                v = row.get(param_key)
                if v is not None and row.get("frequency") is not None:
                    freqs.append(row["frequency"]); values.append(v)
            if len(freqs) > 1:
                try:
                    gap = getattr(output_config, 'freq_gap_mhz', 10) if output_config else 10
                    png = _freq_renderer.render_freq_curve(
                        freqs, values, ylabel=param_label,
                        title=f"{ci.label}",
                        gap_mhz=gap)
                    # 使用 ChartInstance.label 做 key
                    if ci.label not in image_groups:
                        image_groups[ci.label] = {}
                    image_groups[ci.label][0.0] = png
                    _log(log_callback, f"  B类 {ci.label}: {len(freqs)} 频点")
                except Exception as e:
                    _log(log_callback, f"  B类 {ci.label} 渲染失败: {e}")

    # ── 双Y轴配对 (B 类) ──
    _dual_y = getattr(output_config, 'dual_y_enabled', False) if output_config else False
    if _dual_y and _flat:
        # 预定义配对: (%类, dB类) → 双Y轴
        _DUAL_PAIRS = [
            (("efficiency_pct", "Efficiency (%)"), ("gain", "Peak Gain (dBi)")),
            (("directivity", "Directivity (dBi)"), ("trp", "TRP (dBm)")),
        ]
        gap = getattr(output_config, 'freq_gap_mhz', 10) if output_config else 10
        for (k1, l1), (k2, l2) in _DUAL_PAIRS:
            if k1 not in _flat[0] or k2 not in _flat[0]:
                continue
            freqs = []; v1 = []; v2 = []
            for row in _flat:
                f = row.get("frequency")
                a = row.get(k1); b = row.get(k2)
                if f is not None and a is not None and b is not None:
                    freqs.append(f); v1.append(a); v2.append(b)
            if len(freqs) > 1:
                try:
                    png = _freq_renderer.render_freq_curve_dual(
                        freqs, v1, l1, v2, l2, gap_mhz=gap,
                        title=f"{l1} + {l2} vs Frequency")
                    group = f"B: {l1} + {l2} vs Freq"
                    if group not in image_groups:
                        image_groups[group] = {}
                    image_groups[group][0.0] = png
                except Exception:
                    pass

    # ── Write Word: 统一输出所有图表到 Word ──
    def _count_images(v: dict) -> int:
        """统计一组图片的实际张数（值可能是 BytesIO 或 list[BytesIO]）."""
        n = 0
        for buf in v.values():
            n += len(buf) if isinstance(buf, list) else 1
        return n
    _log(log_callback, f"  📊 收集到 {len(image_groups)} 组图片"
         + (f" ({sum(_count_images(v) for v in image_groups.values())} 张)" if image_groups else ""))
    if not out_word:
        pass  # 用户未请求 Word 输出
    elif not image_groups:
        _log(log_callback, "  ⚠ image_groups 为空 — 无图片可输出到 Word")
    else:
        az = output_config or None
        word_path = az.chart_output_path if az else ""
        if not word_path:
            _log(log_callback, "  ⚠ 未设置 Word 输出路径, 跳过图表报告")
        elif word_template_path and os.path.exists(word_template_path):
            pass  # 模板模式 — 后续实现
        else:
            from .chart_word_writer import write_chart_word_report
            _log(log_callback, f"生成图表报告: {word_path}")
            _log(log_callback, f"  布局模式: {az.word_layout_mode if az else 'default'}, 标题: {getattr(az, 'show_caption', True) if az else True}")
            try:
                # 按 ChartInstance.sort_order 排序 image_groups 的 key 顺序
                if chart_instances:
                    _label_order = [ci.label for ci in sorted(chart_instances, key=lambda x: x.sort_order) if ci.enabled]
                else:
                    _label_order = list(image_groups.keys())
                saved_path = write_chart_word_report(
                    image_groups, word_path,
                    antenna_name=az.antenna_name if az else "",
                    label_order=_label_order,
                    layout_mode=az.word_layout_mode if az else "side_by_side",
                    layout_columns=az.word_columns if az else 2,
                    image_width_pct=az.word_image_width_pct if az else 90,
                    show_heading=getattr(az, 'show_heading', False) if az else False,
                    show_caption=getattr(az, 'show_caption', False) if az else False,
                )
                total_imgs = sum(_count_images(v) for v in image_groups.values())
                _log(log_callback, f"  ✓ Word 报告已保存: {saved_path} ({len(image_groups)} 组, {total_imgs} 张图)")
            except Exception as e:
                _log(log_callback, f"  ✗ Word 报告生成失败: {e}")
                _word_ok = False


    # ── 中间数据: 泛化导出 (注册表驱动, 见 src/intermediate_data.py) ──
    #   Gain/AR/RHCP/LHCP/CP-XPI 矩阵 + PkGain + LAG/AR/RHCP/CP-XPI@θ 切片, 自动按 row 字段裁剪。
    if out_data:
        data_path = output_config.data_output_path if output_config else ""
        if not data_path:
            gdir = getattr(output_config, 'data_output_dir', '') if output_config else ''
            gfn = getattr(output_config, 'data_output_filename', '') if output_config else ''
            if gdir and gfn:
                data_path = str(Path(gdir) / gfn)
        if data_path:
            _log(log_callback, f"中间数据: {data_path}")
            from .intermediate_data import write_intermediate_data
            if not write_intermediate_data(sheet_results, data_path, log_callback):
                _data_ok = False

    # 返回导出是否全部成功（供调用方决定是否清理缓存）
    return _word_ok and _data_ok


# ---------------------------------------------------------------------------
# 向后兼容: 保留旧版 run_batch_pipeline
# ---------------------------------------------------------------------------

def run_batch_pipeline(
    csv_path: str,
    template_path: str,
    output_path: str,
    *,
    lag_config_override=None,
    plot_config=None,
    full_report_path=None,
    theta_extrap_method: str | None = None,
    cancel_callback=None,
    progress_callback=None,
    log_callback=None,
    antenna_freq_selection: list[float] | None = None,
    **_ignored,  # 接受但不使用 worker 可能传入的额外参数
):
    """旧版 pipeline: 接受 CSV 路径，内部创建 MergedCSVParser。"""
    ds = MergedCSVParser(csv_path)
    return run_pipeline(
        datasource=ds,
        template_path=template_path,
        output_path=output_path,
        lag_config_override=lag_config_override,
        plot_config=plot_config,
        full_report_path=full_report_path,
        theta_extrap_method=theta_extrap_method,
        cancel_callback=cancel_callback,
        progress_callback=progress_callback,
        log_callback=log_callback,
        antenna_freq_selection=antenna_freq_selection,
    )


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _log(cb, msg):
    if cb: cb(msg)


def _report(cb, cur, tot, msg):
    if cb: cb(cur, tot, msg)


# ---------------------------------------------------------------------------
# 并行计算 worker（模块级，可 pickle，纯 numpy 数学）
# ---------------------------------------------------------------------------

def _compute_chunk(
    compute_tasks: list[tuple[str, float, dict[str, Any], Any, list[float], bool]],
) -> list[tuple[str, dict[str, Any]]]:
    """子进程中处理一批频点的纯计算任务。不读文件。

    每个任务 18 元组: (..., chart_instances, dir_extrap_method)。
    """
    import numpy as np
    results = []
    for sheet_name, freq, raw, lag_cfg, theta_list, do_extrap, rpk, nparams, xparams, ccfg, ar_cfg, nh_angles, ar_out_db, az_cfg, co, sm, cinst, de in compute_tasks:
        try:
            theta_raw = np.array(theta_list)
            row = _process_one_frequency(raw, freq, theta_raw, lag_cfg,
                                         theta_extrap_method=do_extrap, robust_peak=rpk, needed_params=nparams, extra_params=xparams, chart_config=ccfg, ar_lag_config=ar_cfg, rhcp_lag_config=None, cpxpi_lag_config=None, output_config=az_cfg, nh_custom_angles=nh_angles, ar_output_db=ar_out_db, dir_extrap_method=de, compute_only=co, store_matrices=sm, chart_instances=cinst,
                                         log_cb=None)
            results.append((sheet_name, row))
        except Exception as e:
            results.append((sheet_name, {"frequency": freq, "_error": str(e)}))
    return results


# ═══════════════════════════════════════════════════════════════
# 预览缓存: compute_only 时保存 → 导出时复用
# ═══════════════════════════════════════════════════════════════
# 预览缓存 (预览时保存 → 导出时复用 → 导出后自动删除)
# ═══════════════════════════════════════════════════════════════

def _cache_path(output_config, output_path: str) -> str | None:
    """预览缓存文件路径。优先用 Excel 输出路径, 其次 Word 输出路径。"""
    if output_path:
        return output_path.replace(".xlsx", "") + ".preview_cache.pkl"
    if output_config and output_config.chart_output_path:
        return output_config.chart_output_path + ".preview_cache.pkl"
    return None


def _save_preview_cache(sheet_results, output_config, output_path, template_path):
    """保存预览缓存 (不含图片 bytes, 不含渲染结果)。"""
    import pickle
    cache_file = _cache_path(output_config, output_path)
    if not cache_file:
        return
    try:
        # 只保存数值数据, 去掉 _images (bytes 无法 pickle 或太大)
        clean = {}
        for name, rows in sheet_results.items():
            clean_rows = []
            for r in rows:
                clean_row = {k: v for k, v in r.items()
                             if not k.startswith('_') and not isinstance(v, io.BytesIO)}
                clean_rows.append(clean_row)
            clean[name] = clean_rows
        data = {
            "template_path": template_path,
            "sheet_results": clean,
        }
        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)
    except Exception:
        pass  # 缓存保存失败不阻塞


def _load_preview_cache(output_config, output_path, template_path):
    """加载预览缓存, 验证模板未变, 返回 sheet_results 或 None。"""
    import pickle
    cache_file = _cache_path(output_config, output_path)
    if not cache_file or not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, 'rb') as f:
            data = pickle.load(f)
        if data.get("template_path") != template_path:
            return None
        return data.get("sheet_results", {})
    except Exception:
        return None


def _delete_preview_cache(output_config, output_path):
    """导出完成后删除预览缓存。"""
    cache_file = _cache_path(output_config, output_path)
    if cache_file and os.path.exists(cache_file):
        try:
            os.remove(cache_file)
        except Exception:
            pass


def _write_matrix_block(wb, sheet_name: str, freq_label: str,
                        matrix: np.ndarray, phi_deg: np.ndarray,
                        theta_deg: np.ndarray) -> None:
    """向 workbook 写入一个频点的数据矩阵 (phi × theta)。

    格式:
      Frequency: 1154 MHz
              Theta:  -180.0  -178.0  ...  179.0
      Phi   0:         val     val   ...   val
      Phi   1:         val     val   ...   val
    """
    truncated = sheet_name[:31]
    if truncated in wb.sheetnames:
        ws = wb[truncated]
        # 检测截断碰撞: 若已有 sheet 来自不同的完整名称, 追加序号避免数据混淆
        _existing_full = getattr(ws, '_full_sheet_name', '')
        if _existing_full and _existing_full != sheet_name:
            n = 2
            while f"{truncated}_{n}" in wb.sheetnames:
                n += 1
            truncated = f"{truncated}_{n}"
            ws = wb.create_sheet(truncated)
    else:
        ws = wb.create_sheet(truncated)
    ws._full_sheet_name = sheet_name  # 标记完整名称供碰撞检测
    # 找到下一个可用行: 在已有数据后面追加
    next_row = ws.max_row + 1
    if ws.max_row == 1 and ws.cell(1, 1).value is None:
        next_row = 1
    # 空行分隔
    if next_row > 1:
        next_row += 1
    ws.cell(row=next_row, column=1, value=f"Frequency: {freq_label}")
    next_row += 1
    # 表头行: Theta 角度
    ws.cell(row=next_row, column=1, value="Phi \\ Theta (°)")
    for ci, tv in enumerate(theta_deg):
        ws.cell(row=next_row, column=ci + 2, value=round(float(tv), 1))
    next_row += 1
    # 数据行: 每行一个 phi
    n_phi, n_theta = matrix.shape
    for pi in range(min(n_phi, len(phi_deg))):
        ws.cell(row=next_row + pi, column=1, value=round(float(phi_deg[pi]), 1))
        for ti in range(min(n_theta, len(theta_deg))):
            ws.cell(row=next_row + pi, column=ti + 2,
                    value=round(float(matrix[pi, ti]), 6))
