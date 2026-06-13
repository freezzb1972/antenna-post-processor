"""
3D 辐射方向图生成器
====================
仿 EMQuest 风格的球面 3D 辐射方向图。

特性:
  - 3D 球面曲面图（plot_surface + wireframe）
  - jet/rainbow colormap（蓝→青→绿→黄→红）
  - 标题含频率、θ 角度/范围信息
  - 可设仰角/方位角视角
  - colorbar 含 dB 标尺
  - 输出 PNG buffer → 可直接嵌入 Excel
"""

from __future__ import annotations

import io
from typing import Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # 非交互式后端（PyInstaller 兼容）
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm
from matplotlib.ticker import LinearLocator


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _fig_to_png_buffer(fig, dpi: int) -> io.BytesIO:
    """将 matplotlib figure 渲染为 PNG buffer，关闭 figure 释放内存。"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    buf.seek(0)
    plt.close(fig)
    return buf


# ---------------------------------------------------------------------------
# 主绘图函数
# ---------------------------------------------------------------------------

def generate_3d_pattern(
    theta_deg: np.ndarray,         # (n_theta,)  0-110°
    phi_deg: np.ndarray,            # (n_phi,)    0-359°
    gain_dbi: np.ndarray,           # (n_phi, n_theta)  总增益 dB
    freq_mhz: float,
    *,
    elev: float = 30.0,
    azim: float = -60.0,
    dpi: int = 150,
    figsize: Tuple[float, float] = (9, 7),
    title: Optional[str] = None,
    cmap: str = "jet",
    alpha: float = 0.85,
    show_colorbar: bool = True,
    show_grid: bool = True,
    antenna_name: str = "",
) -> io.BytesIO:
    """生成一张 3D 球面辐射方向图（EMQuest 风格）。

    Args:
        theta_deg:    θ 角度 (度)，形状 (n_theta,)。
        phi_deg:      φ 角度 (度)，形状 (n_phi,)。
        gain_dbi:     总增益 (dBi)，形状 (n_phi, n_theta)。
        freq_mhz:     频率 (MHz)，用于标题。
        elev:         3D 视角仰角 (度)。
        azim:         3D 视角方位角 (度)。
        dpi:          输出分辨率。
        figsize:      画布尺寸 (inch)。
        title:        自定义标题，None=自动生成。
        cmap:         colormap 名称。
        alpha:        曲面透明度。
        show_colorbar: 是否显示颜色条。
        show_grid:    是否显示网格。
        antenna_name: 天线名称（可选）。

    Returns:
        PNG image buffer (io.BytesIO)，可直接用 openpyxl 嵌入 Excel。
    """
    # ---- 球坐标 → 笛卡尔坐标 ----
    THETA, PHI = np.meshgrid(
        np.deg2rad(theta_deg),
        np.deg2rad(phi_deg),
    )  # 均为 (n_phi, n_theta)

    # 将 dB 增益偏移到正值以便渲染半径（保持相对关系）
    g = gain_dbi.copy()
    g_min = np.nanmin(g)
    # 以最低值为基准偏移，确保半径为正
    r_offset = max(0.0, -g_min + 1.0)
    R = g + r_offset

    X = R * np.sin(THETA) * np.cos(PHI)
    Y = R * np.sin(THETA) * np.sin(PHI)
    Z = R * np.cos(THETA)

    # ---- 创建图形 ----
    fig = plt.figure(figsize=figsize, dpi=dpi)
    ax = fig.add_subplot(111, projection="3d", computed_zorder=False)

    # ---- 曲面 + 伪线框 ----
    norm = matplotlib.colors.Normalize(vmin=np.nanmin(g), vmax=np.nanmax(g))
    surf = ax.plot_surface(
        X, Y, Z,
        facecolors=plt.get_cmap(cmap)(norm(g)),
        rstride=2, cstride=2,
        alpha=alpha,
        linewidth=0,
        antialiased=True,
        shade=True,
    )

    # 伪线框（稀疏网格线）
    if show_grid:
        stride = max(len(phi_deg) // 18, 1)
        ax.plot_wireframe(
            X, Y, Z,
            rstride=stride, cstride=max(len(theta_deg) // 12, 1),
            color="black", linewidth=0.15, alpha=0.25,
        )

    # ---- 视角 ----
    ax.view_init(elev=elev, azim=azim)

    # ---- 坐标轴 ----
    # 等比例
    max_range = np.nanmax([np.nanmax(np.abs(X)), np.nanmax(np.abs(Y)), np.nanmax(np.abs(Z))]) * 0.9
    ax.set_xlim(-max_range, max_range)
    ax.set_ylim(-max_range, max_range)
    ax.set_zlim(-max_range, max_range)

    ax.set_xlabel("X", fontsize=9, labelpad=2)
    ax.set_ylabel("Y", fontsize=9, labelpad=2)
    ax.set_zlabel("Z", fontsize=9, labelpad=2)

    # 隐藏 pane 背景
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor("gray")
    ax.yaxis.pane.set_edgecolor("gray")
    ax.zaxis.pane.set_edgecolor("gray")

    # 轻量刻度
    ax.tick_params(labelsize=7, pad=1)

    # ---- 标题 ----
    if title is None:
        title = f"Frequency: {freq_mhz} MHz"
        if antenna_name:
            title = f"{antenna_name}  —  {title}"
    ax.set_title(title, fontsize=11, fontweight="bold", pad=12)

    # ---- Colorbar ----
    if show_colorbar:
        mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
        cbar = fig.colorbar(
            mappable, ax=ax, shrink=0.55, aspect=18, pad=0.06,
        )
        cbar.set_label("Gain (dBi)", fontsize=8, labelpad=6)
        cbar.ax.tick_params(labelsize=7)

    # ---- 布局 ----
    fig.tight_layout(pad=0.5)

    # ---- 输出到 buffer ----
    return _fig_to_png_buffer(fig, dpi)


def generate_2d_polar_cut(
    angles_deg: np.ndarray,   # (n_angles,)  方位角或俯仰角
    gain_dbi: np.ndarray,      # (n_angles,)  增益 dB
    freq_mhz: float,
    *,
    cut_label: str = "φ",      # 切面标签，如 "φ=0°" 或 "θ=60°"
    dpi: int = 150,
    figsize: Tuple[float, float] = (7, 7),
    antenna_name: str = "",
) -> io.BytesIO:
    """生成 2D 极坐标切面图（EMQuest 风格）。

    Args:
        angles_deg: 扫描角度 (度)。
        gain_dbi:   对应增益 (dBi)。
        freq_mhz:   频率 (MHz)。
        cut_label:  切面描述。
        dpi:        分辨率。
        figsize:    画布尺寸。
        antenna_name: 天线名称。

    Returns:
        PNG image buffer。
    """
    fig, ax = plt.subplots(1, 1, figsize=figsize, subplot_kw={"projection": "polar"})
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    theta_rad = np.deg2rad(angles_deg)
    ax.plot(theta_rad, gain_dbi, linewidth=1.5, color="#2962ff")
    ax.fill(theta_rad, gain_dbi, alpha=0.08, color="#2962ff")

    ax.set_ylim(np.nanmin(gain_dbi) - 5, np.nanmax(gain_dbi) + 3)
    ax.tick_params(labelsize=8)

    title = f"Frequency: {freq_mhz} MHz  |  {cut_label}"
    if antenna_name:
        title = f"{antenna_name}  —  {title}"
    ax.set_title(title, fontsize=11, fontweight="bold", pad=18)
    ax.set_ylabel("Gain (dBi)", fontsize=8, labelpad=25)
    ax.grid(True, alpha=0.4)

    fig.tight_layout()
    return _fig_to_png_buffer(fig, dpi)


def generate_2d_rectangular_cut(
    angles_deg: np.ndarray,
    gain_dbi: np.ndarray,
    freq_mhz: float,
    *,
    xlabel: str = "Theta (deg)",
    cut_label: str = "",
    dpi: int = 150,
    figsize: Tuple[float, float] = (8, 5),
    antenna_name: str = "",
) -> io.BytesIO:
    """生成 2D 直角坐标切面图。

    Args:
        angles_deg: X 轴角度 (度)。
        gain_dbi:   Y 轴增益 (dBi)。
        freq_mhz:   频率 (MHz)。
        xlabel:     X 轴标签。
        cut_label:  切面描述。
        dpi:        分辨率。
        figsize:    画布尺寸。
        antenna_name: 天线名称。

    Returns:
        PNG image buffer。
    """
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    ax.plot(angles_deg, gain_dbi, linewidth=1.5, color="#2962ff")
    ax.fill_between(angles_deg, gain_dbi, alpha=0.08, color="#2962ff")
    ax.grid(True, alpha=0.4)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel("Gain (dBi)", fontsize=9)
    ax.tick_params(labelsize=8)

    title = f"Frequency: {freq_mhz} MHz"
    if cut_label:
        title += f"  |  {cut_label}"
    if antenna_name:
        title = f"{antenna_name}  —  {title}"
    ax.set_title(title, fontsize=11, fontweight="bold", pad=10)

    fig.tight_layout()
    return _fig_to_png_buffer(fig, dpi)
