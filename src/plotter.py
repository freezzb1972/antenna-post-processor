"""
辐射方向图生成器
================
封装 renderer 模块，提供向后兼容的绘图函数 + 批量生成。
"""

from __future__ import annotations

import io
from typing import Dict, Optional, Tuple

import numpy as np

from .chart_config import ChartConfig
from .renderer import BaseRenderer, MatplotlibRenderer, CloudRenderer
from .azimuth_config import AzimuthReportConfig

# 模块级默认渲染器（可通过 set_renderer 切换）
_renderer: BaseRenderer = MatplotlibRenderer()


def set_renderer(renderer: BaseRenderer):
    """切换渲染引擎。"""
    global _renderer
    _renderer = renderer


def get_renderer() -> BaseRenderer:
    return _renderer


# ---------------------------------------------------------------------------
# 向后兼容的独立绘图函数
# ---------------------------------------------------------------------------

def generate_3d_pattern(
    theta_deg: np.ndarray,
    phi_deg: np.ndarray,
    gain_dbi: np.ndarray,
    freq_mhz: float,
    *,
    elev: float = 30.0,
    azim: float = -60.0,
    dpi: int = 150,
    figsize: Tuple[float, float] = (9, 7),
    title: Optional[str] = None,
    antenna_name: str = "",
) -> io.BytesIO:
    """生成 3D 球面辐射方向图 PNG。委托给当前渲染器。"""
    return _renderer.render_3d_pattern(
        theta_deg, phi_deg, gain_dbi, freq_mhz,
        elev=elev, azim=azim, dpi=dpi,
        title=title or "", antenna_name=antenna_name,
    )


def generate_2d_polar_cut(
    angles_deg: np.ndarray,
    gain_dbi: np.ndarray,
    freq_mhz: float,
    *,
    cut_label: str = "",
    dpi: int = 150,
    antenna_name: str = "",
) -> io.BytesIO:
    """生成 2D 极坐标切面图。"""
    return _renderer.render_2d_polar(
        angles_deg, gain_dbi, freq_mhz,
        cut_label=cut_label, dpi=dpi, antenna_name=antenna_name,
    )


def generate_2d_rectangular_cut(
    angles_deg: np.ndarray,
    gain_dbi: np.ndarray,
    freq_mhz: float,
    *,
    xlabel: str = "Theta (deg)",
    cut_label: str = "",
    dpi: int = 150,
    antenna_name: str = "",
) -> io.BytesIO:
    """生成 2D 直角坐标切面图。"""
    return _renderer.render_2d_rect(
        angles_deg, gain_dbi, freq_mhz,
        xlabel=xlabel, cut_label=cut_label, dpi=dpi,
        antenna_name=antenna_name,
    )


def _match_theta_indices(
    theta_deg: np.ndarray,
    target_angles: "List[float]",
    tolerance_deg: float = 2.0,
) -> "List[int]":
    """将目标 Theta 角度映射为最近的 theta 数组索引。

    Args:
        theta_deg: 数据中的 theta 角度数组 (°), (n_theta,)
        target_angles: 用户选定的 theta 角度 (°)
        tolerance_deg: 容差 (°)，超出此值仅 log warning

    Returns:
        索引列表。
    """
    indices = []
    for angle in sorted(set(target_angles)):
        idx = int(np.argmin(np.abs(theta_deg - angle)))
        nearest = theta_deg[idx]
        if abs(nearest - angle) > tolerance_deg:
            import logging
            logging.warning(
                f"方位面切图: Theta {angle}° 在数据中未找到 "
                f"(最近匹配: {nearest:.1f}°, 容差: {tolerance_deg}°)"
            )
        indices.append(idx)
    return indices


def generate_azimuth_polar_cut(
    phi_deg: np.ndarray,
    curves: "List[Tuple[float, np.ndarray]]",
    freq_mhz: float,
    *,
    antenna_name: str = "",
    dpi: int = 150,
    ylabel: str = "Gain (dBi)",
) -> io.BytesIO:
    """生成方位面极坐标切面图（多条 Theta 曲线叠加）。"""
    return _renderer.render_azimuth_polar(
        phi_deg, curves, freq_mhz,
        antenna_name=antenna_name, dpi=dpi, ylabel=ylabel,
    )


# ---------------------------------------------------------------------------
# 批量生成
# ---------------------------------------------------------------------------

def generate_all_for_frequency(
    theta_deg: np.ndarray,
    phi_deg: np.ndarray,
    gain_dbi: np.ndarray,
    freq_mhz: float,
    chart_config: ChartConfig,
    *,
    ar_linear: Optional[np.ndarray] = None,
    antenna_name: str = "",
    azimuth_config: Optional[AzimuthReportConfig] = None,
    extra_patterns: Dict[str, np.ndarray] = None,
) -> Dict[str, io.BytesIO]:
    """根据 ChartConfig 为一个频点生成所有需要的图形。

    Args:
        theta_deg:    θ 角度数组 (°)，(n_theta,)
        phi_deg:      φ 角度数组 (°)，(n_phi,)
        gain_dbi:     总增益 (dB)，(n_phi, n_theta)
        freq_mhz:     频率 (MHz)
        chart_config: 图形配置
        ar_linear:    轴比线性值，(n_phi, n_theta)，3D AR 需要
        antenna_name: 天线名称
        azimuth_config: 方位面报告配置
        extra_patterns: 额外数据源映射，如 {"3d_etheta": theta_logmag_db, "3d_ephi": phi_logmag_db}

    Returns:
        {"3d_gain": buf, "2d_polar_phi0": buf, "2d_rect_phi0": buf, ...}
    """
    images: Dict[str, io.BytesIO] = {}
    extra = extra_patterns or {}

    # ── A 类: 3D 方向图 ──
    # 多视角支持: 若有 view_angle_pairs 则循环，否则用单个 elev/azim
    view_pairs = list(chart_config.view_angle_pairs) if chart_config.view_angle_pairs else [
        (getattr(chart_config, 'elev', None) or 30.0,
         getattr(chart_config, 'azim', None) or -60.0)
    ]

    if chart_config.pattern_3d_gain:
        for vi, (el, az) in enumerate(view_pairs):
            suffix = f"_v{vi}" if len(view_pairs) > 1 else ""
            images[f"3d_gain{suffix}"] = _renderer.render_3d_pattern(
                theta_deg, phi_deg, gain_dbi, freq_mhz,
                elev=el, azim=az,
                dpi=chart_config.dpi,
                title="3D Gain Pattern", antenna_name=antenna_name,
                colormap="emquest",
            )

    if chart_config.pattern_3d_eirp:
        for vi, (el, az) in enumerate(view_pairs):
            suffix = f"_v{vi}" if len(view_pairs) > 1 else ""
            images[f"3d_eirp{suffix}"] = _renderer.render_3d_pattern(
                theta_deg, phi_deg, gain_dbi, freq_mhz,
                elev=el, azim=az,
                dpi=chart_config.dpi,
                title="3D EIRP Pattern", antenna_name=antenna_name,
                colormap="emquest",
            )

    if chart_config.pattern_3d_ar and ar_linear is not None:
        ar_db = 20.0 * np.log10(np.maximum(ar_linear, 1e-15))
        for vi, (el, az) in enumerate(view_pairs):
            suffix = f"_v{vi}" if len(view_pairs) > 1 else ""
            images[f"3d_ar{suffix}"] = _renderer.render_3d_pattern(
                theta_deg, phi_deg, ar_db, freq_mhz,
                elev=el, azim=az,
                dpi=chart_config.dpi,
                title="3D Axial Ratio", antenna_name=antenna_name,
                colormap="emquest",
            )

    # ── A 类: E_θ / E_φ 分量（extra_patterns 提供数据） ──
    if chart_config.pattern_3d_etheta and "3d_etheta" in extra:
        for vi, (el, az) in enumerate(view_pairs):
            suffix = f"_v{vi}" if len(view_pairs) > 1 else ""
            images[f"3d_etheta{suffix}"] = _renderer.render_3d_pattern(
                theta_deg, phi_deg, extra["3d_etheta"], freq_mhz,
                elev=el, azim=az,
                dpi=chart_config.dpi,
                title="3D E_θ Pattern", antenna_name=antenna_name,
                colormap="emquest",
            )

    if chart_config.pattern_3d_ephi and "3d_ephi" in extra:
        for vi, (el, az) in enumerate(view_pairs):
            suffix = f"_v{vi}" if len(view_pairs) > 1 else ""
            images[f"3d_ephi{suffix}"] = _renderer.render_3d_pattern(
                theta_deg, phi_deg, extra["3d_ephi"], freq_mhz,
                elev=el, azim=az,
                dpi=chart_config.dpi,
                title="3D E_φ Pattern", antenna_name=antenna_name,
                colormap="emquest",
            )

    # ── C 类: 俯仰面切面图 ──
    if chart_config.cut_2d_polar or chart_config.cut_2d_rect:
        n_phi = len(phi_deg)
        if n_phi > 0:
            # 选定 Phi 角度（默认 0° 和 90°）
            phi_angles = list(chart_config.cut_2d_phi_angles) if chart_config.cut_2d_phi_angles else [0.0, 90.0]

            for phi_deg_target in sorted(set(phi_angles)):
                # 找最近 phi 索引
                phi_idx = int(np.argmin(np.abs(phi_deg - phi_deg_target)))
                nearest_phi = float(phi_deg[phi_idx])
                cut_label = f"φ={nearest_phi:.0f}°"
                cut_gain = gain_dbi[phi_idx, :]

                if chart_config.cut_2d_polar:
                    key = f"2d_polar_phi{nearest_phi:.0f}"
                    images[key] = _renderer.render_2d_polar(
                        theta_deg, cut_gain, freq_mhz,
                        cut_label=cut_label, dpi=chart_config.dpi,
                        antenna_name=antenna_name,
                    )

                if chart_config.cut_2d_rect:
                    key = f"2d_rect_phi{nearest_phi:.0f}"
                    images[key] = _renderer.render_2d_rect(
                        theta_deg, cut_gain, freq_mhz,
                        xlabel="Theta (deg)", cut_label=cut_label,
                        dpi=chart_config.dpi, antenna_name=antenna_name,
                    )

    # ── 方位面极坐标切面图 (Gain + AR) ──
    if azimuth_config is not None and azimuth_config.has_any_azimuth:
        az_antenna = azimuth_config.antenna_name or antenna_name
        az_dpi = azimuth_config.dpi or getattr(chart_config, 'dpi', 150)

        if azimuth_config.cut_azimuth_polar:
            _az_angles = azimuth_config.angles_sorted
            if _az_angles and len(phi_deg) > 0:
                theta_indices = _match_theta_indices(theta_deg, _az_angles)
                curves = [
                    (float(theta_deg[i]), gain_dbi[:, i])
                    for i in theta_indices
                ]
                if curves:
                    images["azimuth_polar"] = _renderer.render_azimuth_polar(
                        phi_deg, curves, freq_mhz,
                        antenna_name=az_antenna, dpi=az_dpi,
                        ylabel="Gain (dBi)",
                    )

        if azimuth_config.cut_azimuth_polar_ar and ar_linear is not None:
            _az_ar_angles = azimuth_config.angles_ar_sorted
            if _az_ar_angles and len(phi_deg) > 0:
                theta_indices = _match_theta_indices(theta_deg, _az_ar_angles)
                ar_db = 20.0 * np.log10(np.maximum(ar_linear, 1e-15))
                curves = [
                    (float(theta_deg[i]), ar_db[:, i])
                    for i in theta_indices
                ]
                if curves:
                    images["azimuth_polar_ar"] = _renderer.render_azimuth_polar(
                        phi_deg, curves, freq_mhz,
                        antenna_name=az_antenna, dpi=az_dpi,
                        ylabel="AR (dB)",
                    )

    return images
