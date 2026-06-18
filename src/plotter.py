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

    Returns:
        {"3d_gain": buf, "2d_polar_phi0": buf, "2d_rect_phi0": buf, ...}
    """
    images: Dict[str, io.BytesIO] = {}

    # ── A 类: 3D 方向图 ──
    if chart_config.pattern_3d_gain:
        images["3d_gain"] = _renderer.render_3d_pattern(
            theta_deg, phi_deg, gain_dbi, freq_mhz,
            elev=chart_config.elev, azim=chart_config.azim,
            dpi=chart_config.dpi,
            title="3D Gain Pattern", antenna_name=antenna_name,
            colormap="emquest",
        )

    if chart_config.pattern_3d_eirp:
        images["3d_eirp"] = _renderer.render_3d_pattern(
            theta_deg, phi_deg, gain_dbi, freq_mhz,
            elev=chart_config.elev, azim=chart_config.azim,
            dpi=chart_config.dpi,
            title="3D EIRP Pattern", antenna_name=antenna_name,
            colormap="emquest",
        )

    if chart_config.pattern_3d_ar and ar_linear is not None:
        ar_db = 20.0 * np.log10(np.maximum(ar_linear, 1e-15))
        images["3d_ar"] = _renderer.render_3d_pattern(
            theta_deg, phi_deg, ar_db, freq_mhz,
            elev=chart_config.elev, azim=chart_config.azim,
            dpi=chart_config.dpi,
            title="3D Axial Ratio", antenna_name=antenna_name,
            colormap="emquest",
        )

    # ── C 类: 2D 切面图 ──
    if chart_config.cut_2d_polar or chart_config.cut_2d_rect:
        n_phi = len(phi_deg)
        if n_phi > 0:
            # φ=0° 切面
            phi0_idx = 0
            cut_gain = gain_dbi[phi0_idx, :]

            if chart_config.cut_2d_polar:
                images["2d_polar_phi0"] = _renderer.render_2d_polar(
                    theta_deg, cut_gain, freq_mhz,
                    cut_label="φ=0°", dpi=chart_config.dpi,
                    antenna_name=antenna_name,
                )

            if chart_config.cut_2d_rect:
                images["2d_rect_phi0"] = _renderer.render_2d_rect(
                    theta_deg, cut_gain, freq_mhz,
                    xlabel="Theta (deg)", cut_label="φ=0°",
                    dpi=chart_config.dpi, antenna_name=antenna_name,
                )

            # φ=90° 切面
            phi90_idx = min(n_phi // 4, n_phi - 1)
            if n_phi >= 4:
                cut_gain_90 = gain_dbi[phi90_idx, :]

                if chart_config.cut_2d_polar:
                    images["2d_polar_phi90"] = _renderer.render_2d_polar(
                        theta_deg, cut_gain_90, freq_mhz,
                        cut_label="φ=90°", dpi=chart_config.dpi,
                        antenna_name=antenna_name,
                    )

                if chart_config.cut_2d_rect:
                    images["2d_rect_phi90"] = _renderer.render_2d_rect(
                        theta_deg, cut_gain_90, freq_mhz,
                        xlabel="Theta (deg)", cut_label="φ=90°",
                        dpi=chart_config.dpi, antenna_name=antenna_name,
                    )

    return images
