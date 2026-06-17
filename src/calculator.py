"""
天线参数计算引擎
=================
Pure NumPy 向量化实现。所有函数无副作用。

计算项：
  - Peak Gain (dBi)       — 全空间峰值增益
  - Directivity (dBi)     — 球面积分方向性系数
  - Efficiency (%) / (dB) — 辐射效率
  - LAG (dB)              — 固定俯仰角方位面平均增益
  - Axial Ratio (dB)      — 极化椭圆轴比
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np


# ======================================================================
# 增益计算
# ======================================================================

def compute_total_gain_linear(
    theta_logmag: np.ndarray,  # (n_phi, n_theta)  dB
    phi_logmag: np.ndarray,    # (n_phi, n_theta)  dB
    *,
    robust: bool = False,
) -> Tuple[np.ndarray, float]:
    """计算总增益（Theta + Phi 极化合成）。

    Args:
        theta_logmag: Theta 极化 LogMag，单位 dB，形状 (n_phi, n_theta)。
        phi_logmag:   Phi   极化 LogMag，单位 dB，形状 (n_phi, n_theta)。
        robust:       True → 鲁棒峰值检测（排除 null 伪影）；
                      False → IEEE 149 标准 np.max（默认）。

    Returns:
        (gain_linear, peak_gain_dbi)
        gain_linear:  总增益线性值，形状 (n_phi, n_theta)。
        peak_gain_dbi: 峰值增益 (dBi)。
    """
    g_theta = np.power(10.0, theta_logmag / 10.0)
    g_phi = np.power(10.0, phi_logmag / 10.0)
    total = g_theta + g_phi

    if robust:
        n_phi, n_theta = total.shape
        main_lobe_cols = min(n_theta, max(1, int(n_theta * 0.4)))
        lobe = total[:, :main_lobe_cols]
        cut_peaks = np.max(lobe, axis=1)
        peak = float(np.median(cut_peaks)) * 1.05
    else:
        peak = float(np.max(total))

    peak_dbi = 10.0 * np.log10(peak) if peak > 0 else -999.0
    return total, peak_dbi


# ======================================================================
# 方向性系数
# ======================================================================

def compute_directivity(
    gain_linear: np.ndarray,  # (n_phi, n_theta)
    theta_rad: np.ndarray,    # (n_theta,) 弧度
) -> float:
    """球面积分计算方向性系数。

    D = 4π · U_max / P_rad

    P_rad = ∫∫ U(θ,φ) sinθ dθ dφ
           ≈ Σ Σ gain_linear[φ,θ] · sin(θ) · dθ · dφ

    Args:
        gain_linear: 总增益线性值。
        theta_rad:   theta 角度 (弧度)，需均匀步进。

    Returns:
        Directivity (dBi)。
    """
    n_phi, n_theta = gain_linear.shape
    dtheta = theta_rad[1] - theta_rad[0] if n_theta > 1 else np.pi
    dphi = 2.0 * np.pi / n_phi

    sin_theta = np.sin(theta_rad)  # (n_theta,)
    # 球面积分: Σ_φ Σ_θ gain · sinθ · dθ · dφ
    # gain_linear: (n_phi, n_theta), sin_theta: (n_theta,) → broadcast
    p_rad = np.sum(gain_linear * sin_theta[np.newaxis, :]) * dtheta * dphi

    u_max = float(np.max(gain_linear))
    if p_rad <= 0:
        return 0.0

    d_linear = 4.0 * np.pi * u_max / p_rad
    d_dbi = 10.0 * np.log10(d_linear)
    return float(d_dbi)


# ======================================================================
# 效率
# ======================================================================

def compute_efficiency(
    peak_gain_dbi: float,
    directivity_dbi: float,
) -> Tuple[float, float]:
    """从增益和方向性推算辐射效率。

    η = 10^((G - D) / 10) × 100%

    Args:
        peak_gain_dbi:  峰值增益 (dBi)。
        directivity_dbi: 方向性 (dBi)。

    Returns:
        (efficiency_pct, efficiency_db)
    """
    eff_db = peak_gain_dbi - directivity_dbi
    eff_pct = 10.0 ** (eff_db / 10.0) * 100.0
    return float(eff_pct), float(eff_db)


# ======================================================================
# LAG — 方位面平均增益
# ======================================================================

def compute_lag_single(
    gain_linear: np.ndarray,  # (n_phi, n_theta)
    theta_idx: int,
) -> float:
    """固定俯仰角 θ 上的方位面平均增益。

    LAG(θ) = 10 · log₁₀( mean_{φ} [ G_lin(φ, θ) ] )

    Args:
        gain_linear: 总增益线性值。
        theta_idx:   θ 索引 (0-based)。

    Returns:
        LAG 值 (dB)。
    """
    cut = gain_linear[:, theta_idx]  # (n_phi,)
    mean_lin = _kahan_mean(cut)
    if mean_lin <= 0:
        return -999.0
    return float(10.0 * np.log10(mean_lin))


def compute_lag_at_angles(
    gain_linear: np.ndarray,  # (n_phi, n_theta)
    theta_angles_deg: np.ndarray,  # (n_theta,) 度
    target_angles_deg: List[float],
) -> Dict[float, float]:
    """批量计算多个 θ 角的 LAG。

    Returns:
        {theta_deg: lag_db, ...}
    """
    results: Dict[float, float] = {}
    for target in target_angles_deg:
        # 找最近索引
        idx = int(np.argmin(np.abs(theta_angles_deg - target)))
        results[target] = compute_lag_single(gain_linear, idx)
    return results


def compute_lag_range(
    gain_linear: np.ndarray,  # (n_phi, n_theta)
    theta_angles_deg: np.ndarray,  # (n_theta,) 度
    theta_start: float,
    theta_end: float,
) -> float:
    """指定 θ 范围内的方位面平均增益的均值。

    LAG(θ₁→θ₂) = mean_{θ∈[θ₁,θ₂]} [ LAG(θ) ]

    Args:
        gain_linear:      总增益线性值。
        theta_angles_deg: θ 角度 (度)。
        theta_start:      起始 θ (度，含)。
        theta_end:        结束 θ (度，含)。

    Returns:
        范围平均 LAG (dB)。
    """
    mask = (theta_angles_deg >= theta_start) & (theta_angles_deg <= theta_end + 1e-9)
    indices = np.where(mask)[0]
    if len(indices) == 0:
        return -999.0

    # 正确: 所有 θ×φ 在线性域取均值, 一次性转 dB
    subset = gain_linear[:, indices]  # (n_phi, n_theta_in_range)
    mean_lin = _kahan_mean(subset)
    if mean_lin <= 0:
        return -999.0
    return float(10.0 * np.log10(mean_lin))


def compute_lag_ranges(
    gain_linear: np.ndarray,
    theta_angles_deg: np.ndarray,
    ranges: List[Tuple[float, float]],
) -> Dict[Tuple[float, float], float]:
    """批量计算多个 θ 范围的 LAG。

    Returns:
        {(start, end): lag_db, ...}
    """
    results: Dict[Tuple[float, float], float] = {}
    for start, end in ranges:
        results[(start, end)] = compute_lag_range(
            gain_linear, theta_angles_deg, start, end
        )
    return results


# ======================================================================
# TRP — 全向辐射功率 (CTIA 01.90 Section 3.3)
# ======================================================================

def _clenshaw_curtis_weights(n: int) -> np.ndarray:
    """CTIA Clenshaw-Curtis 权重系数。

    w_i = c_i / N,  c_i = { 1, i=0 或 i=N-1; 2, 其他 }
    """
    c = np.full(n, 2.0)
    c[0] = 1.0
    c[-1] = 1.0
    return c / n


def _weighted_prp(gain_sub: np.ndarray, theta_sub: np.ndarray) -> float:
    """计算 sin(θ) 加权 + Clenshaw-Curtis 积分的部分辐射功率 (线性值)。

    PRP_lin = ½ Σ w_i · mean_φ(gain) · sin(θ_i)
    """
    n_theta = len(theta_sub)
    w = _clenshaw_curtis_weights(n_theta)
    cut = np.mean(gain_sub, axis=0) * np.sin(theta_sub)
    prp_lin = 0.5 * np.sum(w * cut)
    return max(prp_lin, 1e-15)


def compute_trp(
    eirp_linear: np.ndarray,  # (n_phi, n_theta)  mW
    theta_rad: np.ndarray,    # (n_theta,) 弧度
) -> float:
    """CTIA 全向辐射功率 (TRP)。

    TRP ≈ ½ Σ w_i · (1/M) Σ [EIRP_θ(θ_i,φ_j) + EIRP_φ(θ_i,φ_j)]

    Args:
        eirp_linear: 总 EIRP 线性值 (mW)，已含 θ+φ 极化合成。
        theta_rad:   θ 角度 (弧度)，需均匀步进。

    Returns:
        TRP (dBm)。
    """
    trp_lin = _weighted_prp(eirp_linear, theta_rad)
    return float(10.0 * np.log10(trp_lin))


def compute_nhprp(
    gain_linear: np.ndarray,  # (n_phi, n_theta)  mW
    theta_rad: np.ndarray,    # (n_theta,) 弧度
    edge_deg: float = 45.0,   # 边界角度（度），默认 45°
) -> float:
    """CTIA 近地平线部分辐射功率 (NHPRP)，默认 ±45°。

    委托给 `compute_nhprp_flex`，保留旧签名以向后兼容。

    Args:
        gain_linear: 总增益线性值 (mW)。
        theta_rad:   θ 角度 (弧度)。
        edge_deg:    地平线边界角度（度），默认 45°。

    Returns:
        NHPRP (dBm)。
    """
    return compute_nhprp_flex(gain_linear, theta_rad, edge_deg)


def compute_nhprp_flex(
    gain_linear: np.ndarray,  # (n_phi, n_theta)  mW
    theta_rad: np.ndarray,    # (n_theta,) 弧度
    edge_deg: float,          # 边界角度（度）
) -> float:
    """近地平线部分辐射功率 (NHPRP)，可指定任意边界角度。

    theta ∈ [90-edge, 90+edge] 区间内的 PRP。

    Args:
        gain_linear: 总增益线性值 (mW)。
        theta_rad:   θ 角度 (弧度)。
        edge_deg:    地平线边界角度（度），如 45 表示 ±45°。

    Returns:
        NHPRP (dBm)。
    """
    return compute_partial_prp(gain_linear, theta_rad, 90.0 - edge_deg, 90.0 + edge_deg)


def compute_peak_eirp(
    eirp_linear: np.ndarray,  # (n_phi, n_theta)  mW
) -> float:
    """峰值 EIRP (dBm)。

    Args:
        eirp_linear: 总 EIRP 线性值 (mW)。

    Returns:
        Peak EIRP (dBm)。
    """
    peak = float(np.max(eirp_linear))
    if peak <= 1e-15:
        return -999.0
    return float(10.0 * np.log10(peak))


# ======================================================================
# PRP — 部分辐射功率（Clenshaw-Curtis 加权积分）
# ======================================================================

def compute_upper_hemisphere_prp(
    gain_linear: np.ndarray,  # (n_phi, n_theta)  mW
    theta_rad: np.ndarray,    # (n_theta,) 弧度
) -> float:
    """上半球部分辐射功率 (Upper Hemisphere PRP)。

    theta ∈ [0°, 90°] 区间内的 PRP，复用 Clenshaw-Curtis 加权积分。

    Args:
        gain_linear: 总增益线性值 (mW)。
        theta_rad:   θ 角度 (弧度)。

    Returns:
        Upper Hemisphere PRP (dBm)。
    """
    return compute_partial_prp(gain_linear, theta_rad, 0.0, 90.0)


def compute_lower_hemisphere_prp(
    gain_linear: np.ndarray,  # (n_phi, n_theta)  mW
    theta_rad: np.ndarray,    # (n_theta,) 弧度
) -> float:
    """下半球部分辐射功率 (Lower Hemisphere PRP)。

    theta ∈ [90°, 180°] 区间内的 PRP，委托 compute_partial_prp。

    Args:
        gain_linear: 总增益线性值 (mW)。
        theta_rad:   θ 角度 (弧度)。

    Returns:
        Lower Hemisphere PRP (dBm)。
    """
    return compute_partial_prp(gain_linear, theta_rad, 90.0, 180.0)


def compute_partial_prp(
    gain_linear: np.ndarray,   # (n_phi, n_theta)  mW
    theta_rad: np.ndarray,     # (n_theta,) 弧度
    theta_start_deg: float,
    theta_end_deg: float,
) -> float:
    """指定 θ 范围内的部分辐射功率 (Partial PRP)。

    复用 Clenshaw-Curtis 加权积分方法。
    上层函数（如 `compute_nhprp_flex`）可通过此函数实现。

    Args:
        gain_linear:     总增益线性值 (mW)。
        theta_rad:       θ 角度 (弧度)。
        theta_start_deg: 起始 θ 角度（度）。
        theta_end_deg:   结束 θ 角度（度）。

    Returns:
        Partial PRP (dBm)。
    """
    theta_deg = np.rad2deg(theta_rad)
    mask = (theta_deg >= theta_start_deg) & (theta_deg < theta_end_deg + 1e-9)  # [start, end)
    indices = np.where(mask)[0]
    if len(indices) == 0:
        return -999.0

    gain_sub = gain_linear[:, indices]
    prp_lin = _weighted_prp(gain_sub, theta_rad[indices])
    return float(10.0 * np.log10(prp_lin))


def compute_prp_trp_ratio(
    prp_dbm: float,
    trp_dbm: float,
) -> Tuple[float, float]:
    """PRP 与 TRP 之比。

    Args:
        prp_dbm: PRP 值 (dBm)。
        trp_dbm: TRP 值 (dBm)。

    Returns:
        (ratio_db, ratio_pct)
        ratio_db:   PRP - TRP (dB)。
        ratio_pct:  10^(ratio_db/10) × 100 (%)。
    """
    ratio_db = prp_dbm - trp_dbm
    ratio_pct = 10.0 ** (ratio_db / 10.0) * 100.0
    return ratio_db, ratio_pct


# ======================================================================
# 波束指向与统计
# ======================================================================

def compute_boresight(
    gain_linear: np.ndarray,        # (n_phi, n_theta)  mW
    theta_angles_deg: np.ndarray,   # (n_theta,) 度
    phi_angles_deg: np.ndarray,     # (n_phi,) 度
) -> Tuple[float, float]:
    """查找主波束指向（最大增益方向）。

    Args:
        gain_linear:      总增益线性值 (mW)。
        theta_angles_deg: θ 角度数组 (度)。
        phi_angles_deg:   φ 角度数组 (度)。

    Returns:
        (boresight_theta_deg, boresight_phi_deg)
    """
    flat_idx = int(np.argmax(gain_linear))
    phi_idx, theta_idx = np.unravel_index(flat_idx, gain_linear.shape)
    return (float(theta_angles_deg[theta_idx]), float(phi_angles_deg[phi_idx]))


def compute_min_power_dbm(
    gain_linear: np.ndarray,  # (n_phi, n_theta)  mW
) -> float:
    """方向图中非零功率最小值。

    Args:
        gain_linear: 总增益线性值 (mW)。

    Returns:
        最小功率 (dBm)，仅考虑非零值 (>1e-15)。
    """
    mask = gain_linear > 1e-15
    if not np.any(mask):
        return -999.0
    min_val = float(np.min(gain_linear[mask]))
    return float(10.0 * np.log10(min_val))


def compute_average_gain_db(
    gain_linear: np.ndarray,  # (n_phi, n_theta)  mW
) -> float:
    """平均增益（线性域均值转 dB）。

    Args:
        gain_linear: 总增益线性值 (mW)。

    Returns:
        平均增益 (dB)。
    """
    mean_lin = float(np.mean(gain_linear))
    if mean_lin <= 1e-15:
        return -999.0
    return float(10.0 * np.log10(mean_lin))


def compute_average_power_dbm(
    gain_linear: np.ndarray,  # (n_phi, n_theta)  mW
) -> float:
    """平均功率（线性域均值转 dBm）。

    与 `compute_average_gain_db` 公式相同（功率/增益在 dB 标度一致）。

    Args:
        gain_linear: 总增益线性值 (mW)。

    Returns:
        平均功率 (dBm)。
    """
    return compute_average_gain_db(gain_linear)


# ======================================================================
# Axial Ratio（复电场合成）
# ======================================================================

def compute_axial_ratio(
    theta_logmag: np.ndarray,  # (n_phi, n_theta)  dB
    theta_phase: np.ndarray,   # (n_phi, n_theta)  deg
    phi_logmag: np.ndarray,    # (n_phi, n_theta)  dB
    phi_phase: np.ndarray,     # (n_phi, n_theta)  deg
) -> Optional[np.ndarray]:
    """计算轴比 AR (dB)，基于极化椭圆。

    AR = 20·log₁₀( |E_major| / |E_minor| )

    步骤：
      1. 幅度 dB → 线性, 相位 deg → rad
      2. 复电场: E_θ = mag_θ · exp(j·phase_θ)
                E_φ = mag_φ · exp(j·phase_φ)
      3. 对每个方向 (φ,θ):
         - 构建极化矢量 [E_θ, E_φ]
         - 计算极化椭圆主轴/短轴
         - AR = |E_major| / |E_minor|

    参考：IEEE Std 149-2021, C.2 Polarization Ellipse

    Returns:
        AR 数组 (n_phi, n_theta)，单位 dB；或 None（数据不完整时）。
    """
    if theta_phase is None or phi_phase is None:
        return None

    # 幅度 → 线性
    mag_theta = np.power(10.0, theta_logmag / 20.0)  # field magnitude
    mag_phi = np.power(10.0, phi_logmag / 20.0)

    # 相位 → 弧度
    ph_theta = np.deg2rad(theta_phase)
    ph_phi = np.deg2rad(phi_phase)

    # 复电场
    e_theta = mag_theta * np.exp(1j * ph_theta)  # (n_phi, n_theta)
    e_phi = mag_phi * np.exp(1j * ph_phi)

    # 极化椭圆参数（IEEE 149）
    # 参见: "IEEE Standard for Antenna Measurements"
    # AR = |E_RHC + E_LHC| / |E_RHC - E_LHC| 的绝对值
    # 或通过 Stokes 参数计算

    # 圆极化分量法（EMQuest 同款，数值稳定）
    # E_RHCP = (E_θ - j·E_φ) / √2
    # E_LHCP = (E_θ + j·E_φ) / √2
    # AR = (|E_RHCP| + |E_LHCP|) / ||E_RHCP| - |E_LHCP||
    e_rhcp = (e_theta - 1j * e_phi) / np.sqrt(2.0)
    e_lhcp = (e_theta + 1j * e_phi) / np.sqrt(2.0)

    abs_rhcp = np.abs(e_rhcp)
    abs_lhcp = np.abs(e_lhcp)

    # 避免除零：|RHCP| ≈ |LHCP| 时 AR → ∞
    denom = np.abs(abs_rhcp - abs_lhcp)
    denom = np.maximum(denom, 1e-15)

    ar_linear = (abs_rhcp + abs_lhcp) / denom
    # EMQuest AxR 输出线性值（不是 dB），保持线性；调用方可自行转换
    return ar_linear  # (n_phi, n_theta) AR 线性值


def compute_ar_at_angles(
    ar_linear: np.ndarray,
    theta_angles_deg: np.ndarray,
    target_angles_deg: List[float],
) -> Dict[float, float]:
    """批量计算多个 θ 角的 AR（取 phi 均值）。

    Returns:
        {theta_deg: ar_linear, ...}
    """
    results: Dict[float, float] = {}
    for target in target_angles_deg:
        idx = int(np.argmin(np.abs(theta_angles_deg - target)))
        results[target] = float(np.mean(ar_linear[:, idx]))
    return results


def compute_ar_range(
    ar_linear: np.ndarray,
    theta_angles_deg: np.ndarray,
    theta_start: float,
    theta_end: float,
) -> float:
    """指定 θ 范围内的 AR 均值（线性域平均）。

    Args:
        ar_linear: AR 线性值，形状 (n_phi, n_theta)。
        theta_angles_deg: θ 角度 (度)。
        theta_start, theta_end: 范围 (度)。

    Returns:
        范围平均 AR (线性值)。
    """
    mask = (theta_angles_deg >= theta_start) & (theta_angles_deg <= theta_end + 1e-9)
    indices = np.where(mask)[0]
    if len(indices) == 0:
        return 1.0
    subset = ar_linear[:, indices]
    return float(np.mean(subset))


# ======================================================================
# 高精度求和
# ======================================================================

def compute_power_ratios(
    max_power_dbm: float, min_power_dbm: float, avg_power_dbm: float,
) -> Dict[str, float]:
    """计算功率比: Max/Min, Max/Avg, Min/Avg (dB)。"""
    return {
        "max_min_ratio_db": round(max_power_dbm - min_power_dbm, 2),
        "max_avg_ratio_db": round(max_power_dbm - avg_power_dbm, 2),
        "min_avg_ratio_db": round(min_power_dbm - avg_power_dbm, 2),
    }


def compute_beamwidth(
    gain_linear: np.ndarray, theta_deg: np.ndarray, phi_deg: np.ndarray
) -> Dict[str, float]:
    """计算3dB波束宽度 (theta 和 phi 方向)。

    Returns:
        {"theta_bw_deg": ..., "phi_bw_deg": ..., "front_back_ratio_db": ...}
    """
    peak = np.max(gain_linear)
    if peak <= 0: return {"theta_bw_deg": 0, "phi_bw_deg": 0, "front_back_ratio_db": 0}
    threshold_lin = peak / 2.0  # -3 dB

    # Theta BW: 在 phi=boresight_phi 的 cut 上
    bs_phi_idx = np.argmax(np.max(gain_linear, axis=1))
    theta_cut = gain_linear[bs_phi_idx, :]
    above = theta_cut >= threshold_lin
    theta_bw = 0.0
    if np.any(above):
        indices = np.where(above)[0]
        theta_bw = abs(theta_deg[indices[-1]] - theta_deg[indices[0]])

    # Phi BW: 在 theta=boresight_theta 的 cut 上
    bs_theta_idx = np.argmax(np.max(gain_linear, axis=0))
    phi_cut = gain_linear[:, bs_theta_idx]
    above_p = phi_cut >= threshold_lin
    phi_bw = 0.0
    if np.any(above_p):
        indices_p = np.where(above_p)[0]
        phi_bw = abs(phi_deg[indices_p[-1]] - phi_deg[indices_p[0]])

    # Front/Back ratio: max(0-90°) / max(90-180°)
    front_mask = (theta_deg >= 0) & (theta_deg <= 90)
    back_mask = (theta_deg >= 90) & (theta_deg <= 180)
    front_max = np.max(gain_linear[:, front_mask]) if np.any(front_mask) else peak
    back_max = np.max(gain_linear[:, back_mask]) if np.any(back_mask) else 1e-15
    fb_ratio = float(10 * np.log10(front_max / max(back_max, 1e-15)))

    return {"theta_bw_deg": round(theta_bw, 1), "phi_bw_deg": round(phi_bw, 1),
            "front_back_ratio_db": round(fb_ratio, 2)}


def _kahan_mean(arr: np.ndarray) -> float:
    """Kahan 补偿求和的均值——消除浮点累加误差。

    对 N 个浮点数求和：朴素累加 O(N·ε)，pairwise O(log N·ε)，
    Kahan 算法 O(ε)，其中 ε≈2.2×10⁻¹⁶（float64）。

    应用于 LAG 计算中 32,760 个点的均值，精度提升约 3 个数量级。
    """
    s = 0.0
    c = 0.0  # 累积的舍入误差补偿
    for i in range(arr.size):
        item = arr.flat[i]
        y = item - c
        t = s + y
        c = (t - s) - y
        s = t
    return s / arr.size if arr.size > 0 else 0.0
