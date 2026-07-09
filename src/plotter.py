"""
辐射方向图生成器
================
封装 renderer 模块，提供向后兼容的绘图函数 + 批量生成。
"""

from __future__ import annotations

import io

import numpy as np

from .output_config import OutputConfig
from .chart_config import ChartConfig
from .renderer import BaseRenderer, MatplotlibRenderer

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
    figsize: tuple[float, float] = (9, 7),
    title: str | None = None,
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
    target_angles: list[float],
    tolerance_deg: float = 2.0,
) -> list[int]:
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


def generate_gain_vs_theta(
    theta_deg: np.ndarray,
    gain_dbi: np.ndarray,
    freq_mhz: float,
    *,
    antenna_name: str = "",
    dpi: int = 150,
    theta_max: float = 70.0,
) -> io.BytesIO:
    """生成 Gain vs Theta 2D Cartesian 线图 (θ=0-70° 峰值增益)。

    取每个 theta 角度的 phi 方向峰值增益，绘制 Theta-Gain 曲线。
    """
    # 限制 theta 范围 0-70°
    mask = theta_deg <= theta_max + 0.1
    t = theta_deg[mask]
    pk_gain = np.max(gain_dbi[:, mask], axis=0)
    return _renderer.render_gain_vs_theta(
        t, pk_gain, freq_mhz,
        antenna_name=antenna_name, dpi=dpi,
    )


def generate_azimuth_polar_cut(
    phi_deg: np.ndarray,
    curves: list[tuple[float, np.ndarray]],
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

def _build_azimuth_curves(
    theta_deg: np.ndarray, data_db: np.ndarray,
    angles: list[float], phi_count: int,
) -> list[tuple[float, np.ndarray]]:
    """从数据矩阵提取选定 Theta 角度的 phi 切片，构建方位图曲线列表。"""
    if not angles or phi_count == 0:
        return []
    indices = _match_theta_indices(theta_deg, angles)
    return [(float(theta_deg[i]), data_db[:, i]) for i in indices]


def generate_all_for_frequency(
    theta_deg: np.ndarray,
    phi_deg: np.ndarray,
    gain_dbi: np.ndarray,
    freq_mhz: float,
    chart_config: ChartConfig,
    *,
    ar_linear: np.ndarray | None = None,
    rhcp_db: np.ndarray | None = None,
    lhcp_db: np.ndarray | None = None,
    cpxpi_db: np.ndarray | None = None,
    antenna_name: str = "",
    output_config: OutputConfig | None = None,
    extra_patterns: dict[str, np.ndarray] = None,
) -> dict[str, io.BytesIO]:
    """根据 ChartConfig 为一个频点生成所有需要的图形。

    Args:
        theta_deg:    θ 角度数组 (°)，(n_theta,)
        phi_deg:      φ 角度数组 (°)，(n_phi,)
        gain_dbi:     总增益 (dB)，(n_phi, n_theta)
        freq_mhz:     频率 (MHz)
        chart_config: 图形配置
        rhcp_db:      RHCP 增益 (dB)，(n_phi, n_theta) [可选]
        lhcp_db:      LHCP 增益 (dB)，(n_phi, n_theta) [可选]
        ar_linear:    轴比线性值，(n_phi, n_theta)，3D AR 需要
        antenna_name: 天线名称
        output_config: 方位面报告配置
        extra_patterns: 额外数据源映射，如 {"3d_etheta": theta_logmag_db, "3d_ephi": phi_logmag_db}

    Returns:
        {"3d_gain": buf, "2d_polar_phi0": buf, "2d_rect_phi0": buf, ...}
    """
    images: dict[str, io.BytesIO] = {}
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

    # ── C 类: 2D 切面图 (俯仰面 + 方位面, 统一使用 cut_param) ──
    from .cut_param import (build_cut_params, build_cut_params_from_entries,
                             render_phi_cuts, render_theta_cuts, CutChartEntry)

    # 构建数据映射
    ar_db_vals = (20.0 * np.log10(np.maximum(ar_linear, 1e-15))
                  if ar_linear is not None else None)
    data_map = {
        "gain_dbi": gain_dbi,
        "ar_db": ar_db_vals,
        "rhcp_db": rhcp_db,
        "lhcp_db": lhcp_db,
        "cp_xpi": cpxpi_db,
    }

    # 优先使用 4 组独立图表列表, 回退到旧字段
    phi_entries = (getattr(chart_config, 'cut_2d_polar_entries', None) or []) + \
                  (getattr(chart_config, 'cut_2d_rect_entries', None) or [])
    theta_entries = []  # 方位面 entries 由 output_config 独立管理
    if not phi_entries and not theta_entries:
        params = []  # 没有配置条目 → 不生成 2D 切面图
    else:
        from .cut_param import CutChartEntry as _CE
        all_entries = []
        for param, angles in phi_entries:
            all_entries.append(_CE(param=param, direction="phi", angles=angles))
        for param, angles in theta_entries:
            all_entries.append(_CE(param=param, direction="theta", angles=angles))
        params = build_cut_params_from_entries(all_entries, data_map)
    images.update(render_phi_cuts(params, theta_deg, phi_deg, freq_mhz,
                                  chart_config, _renderer))
    images.update(render_theta_cuts(params, theta_deg, phi_deg, freq_mhz,
                                    chart_config, output_config, _renderer))

    # ── PK Theta 范围峰值 (旧方位面路径已移除, 统一走 cut_param) ──
    if output_config and output_config.pk_theta_ranges:
        for t_max in output_config.pk_theta_ranges:
            try:
                mask = theta_deg <= t_max + 0.1
                pk_vals = np.max(gain_dbi[:, mask], axis=1)
                key = f"azimuth_polar_pk_{int(t_max)}"
                images[key] = _renderer.render_azimuth_polar(
                    phi_deg, [(t_max, pk_vals)], freq_mhz,
                    ylabel="Gain (dBi)", dpi=output_config.dpi,
                    title=f"{freq_mhz:.0f}MHz - Gain (dBi) θ=0°-{int(t_max)}°",
                )
            except Exception:
                pass

    return images
