"""
3D 方向图几何 (纯逻辑, 无 Qt / 无 matplotlib)
===============================================
标准半径归一化 + 3D 曲面坐标构建。导出渲染 (renderer) 与 应用内交互查看器
(graph_viewer) **共用同一算法** → 所见即所得 (WYSIWYG)。

半径映射用天线方向图行业标准 (min-max 归一 + 动态范围地板)，替代旧的
`R=abs(gain_dbi)` (零点反外鼓、形状失真成偏心球) 与 `r=max(data,eps)`。
"""

from __future__ import annotations

import numpy as np

DEFAULT_DYN_DB = 40.0     # 默认动态范围 (峰值往下 dB), 可由 GUI 覆盖


def pattern_radius(values_db: np.ndarray, dyn: float | None = None) -> np.ndarray:
    """标准半径归一化: dB 值 → [0,1] 半径。

    峰值 → 1 (最外), 地板 → 0 (收缩到中心)。

    Args:
        values_db: (n_phi, n_theta) dB 矩阵。
        dyn:       动态范围 (dB)。None = 自动自适应 (地板=数据最小值, 用完整范围);
                   数值 = 固定窗口 (地板=峰值−dyn, 削去以下)。
    Returns:
        同形状 [0,1] 数组。
    """
    v = np.asarray(values_db, dtype=float)
    peak = float(np.nanmax(v))
    floor = float(np.nanmin(v)) if dyn is None else peak - float(dyn)
    span = max(peak - floor, 1e-9)
    return (np.clip(v, floor, peak) - floor) / span


def build_3d_surface(
    theta_deg: np.ndarray,
    phi_deg: np.ndarray,
    values: np.ndarray,
    *,
    kind: str = "magnitude",
    dyn: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    """构建 3D 球面曲面的坐标与着色值。

    调用方 (renderer/graph_viewer) 用自己的 cmap 上色:
        norm = Normalize(vmin, vmax); facecolors = cmap(norm(color_values))

    Args:
        theta_deg: (n_theta,) 极角 (°)。
        phi_deg:   (n_phi,) 方位角 (°)。
        values:    (n_phi, n_theta) 数据矩阵 (magnitude→dB; phase→度)。
        kind:      "magnitude" (半径=归一化 dB) | "phase" (常数球面, 色=相位)。
        dyn:       magnitude 的动态范围 (dB); None = 自动自适应 (用数据实际范围)。
    Returns:
        (X, Y, Z, color_values, vmin, vmax) —— 均 (n_phi, n_theta)/标量。
    """
    theta = np.deg2rad(np.asarray(theta_deg, dtype=float))
    phi = np.deg2rad(np.asarray(phi_deg, dtype=float))
    TH, PH = np.meshgrid(theta, phi)          # (n_phi, n_theta)
    vals = np.asarray(values, dtype=float)

    if kind == "phase":
        # 相位无"大小"概念 → 半径取常数球面, 颜色表相位 (−180~180°)
        R = np.ones_like(vals)
        color_values = vals
        vmin, vmax = -180.0, 180.0
    else:
        peak = float(np.nanmax(vals))
        floor = float(np.nanmin(vals)) if dyn is None else peak - float(dyn)
        R = pattern_radius(vals, dyn)
        color_values = np.clip(vals, floor, peak)
        vmin, vmax = floor, peak

    X = R * np.sin(TH) * np.cos(PH)
    Y = R * np.sin(TH) * np.sin(PH)
    Z = R * np.cos(TH)
    return X, Y, Z, color_values, vmin, vmax
