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

注意: 当前 pipeline 未调用绘图函数（通过 PlotConfig 控制），
      函数保留供后续启用。不要当作死代码删除。
"""

from __future__ import annotations

import io
from typing import Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # 非交互式后端（PyInstaller 兼容）
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm


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
    antenna_name: str = "",
) -> io.BytesIO:
    """生成 3D 球面辐射方向图 PNG。

    仿 EMQuest 风格 — 球面坐标系下绘制 Total Gain 曲面。
    Theta 为极角 (0°=天顶)，Phi 为方位角。

    Returns:
        PNG buffer (BytesIO)，可直接嵌入 Excel。
    """
    # ---- 球面 → 直角坐标 ----
    theta = np.deg2rad(theta_deg)
    phi = np.deg2rad(phi_deg)
    TH, PH = np.meshgrid(theta, phi)  # (n_phi, n_theta)

    # 坐标转换: θ=极角, φ=方位角
    # x = sinθ·cosφ, y = sinθ·sinφ, z = cosθ
    R = np.abs(gain_dbi)
    X = R * np.sin(TH) * np.cos(PH)
    Y = R * np.sin(TH) * np.sin(PH)
    Z = R * np.cos(TH)

    # ---- 创建图形 ----
    fig = plt.figure(figsize=figsize, dpi=dpi)
    ax = fig.add_subplot(111, projection="3d")

    # ---- 曲面 ----
    norm = plt.Normalize(gain_dbi.min(), gain_dbi.max())
    surf = ax.plot_surface(
        X, Y, Z,
        facecolors=cm.jet(norm(gain_dbi)),
        rstride=1, cstride=1,
        alpha=0.85, shade=True,
        linewidth=0, antialiased=True,
    )

    # ---- wireframe 叠加 (增强立体感) ----
    # 稀疏采样避免过于密集
    stride = max(1, min(len(phi_deg), len(theta_deg)) // 30)
    ax.plot_wireframe(X, Y, Z, rstride=stride, cstride=stride,
                      color="black", linewidth=0.3, alpha=0.3)

    # ---- colorbar ----
    mappable = cm.ScalarMappable(norm=norm, cmap=cm.jet)
    mappable.set_array(gain_dbi)
    cbar = fig.colorbar(mappable, ax=ax, shrink=0.6, aspect=20, pad=0.08)
    cbar.set_label("Gain (dBi)", fontsize=8, labelpad=6)
    cbar.ax.tick_params(labelsize=7)

    # ---- 布局 ----
    fig.tight_layout(pad=0.5)

    # ---- 输出到 buffer ----
    return _fig_to_png_buffer(fig, dpi)


def generate_2d_polar_cut(
    angles_deg: np.ndarray,
    gain_dbi: np.ndarray,
    freq_mhz: float,
    *,
    cut_label: str = "",
    dpi: int = 150,
    antenna_name: str = "",
) -> io.BytesIO:
    """生成 2D 极坐标切面图。

    Args:
        angles_deg: 角度数组 (°)，通常为 theta。
        gain_dbi:   增益 (dBi)，shape 与 angles_deg 相同。
        freq_mhz:   频率 (MHz)。
        cut_label:  切面标签（如 "φ=0°"）。
        dpi:        输出分辨率。
        antenna_name: 天线名称。

    Returns:
        PNG buffer。
    """
    theta_rad = np.deg2rad(angles_deg)
    fig, ax = plt.subplots(subplot_kw={"projection": "polar"}, dpi=dpi, figsize=(7, 6))

    ax.plot(theta_rad, gain_dbi, "b-", linewidth=1.2)
    ax.fill(theta_rad, gain_dbi, alpha=0.1, color="blue")

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_thetagrids(range(0, 360, 30))

    title_parts = []
    if antenna_name:
        title_parts.append(antenna_name)
    title_parts.append(f"{freq_mhz:.0f} MHz")
    if cut_label:
        title_parts.append(cut_label)
    ax.set_title(" — ".join(title_parts), fontsize=12, pad=18)

    ax.set_ylabel("Gain (dBi)", fontsize=9, labelpad=20)
    ax.grid(True, alpha=0.4)

    fig.tight_layout(pad=1.5)
    return _fig_to_png_buffer(fig, dpi)


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
    """生成 2D 直角坐标切面图。

    Returns:
        PNG buffer。
    """
    fig, ax = plt.subplots(dpi=dpi, figsize=(8, 5))

    ax.plot(angles_deg, gain_dbi, "b-", linewidth=1.2)
    ax.fill_between(angles_deg, gain_dbi, gain_dbi.min() - 5, alpha=0.08, color="blue")

    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel("Gain (dBi)", fontsize=10)
    ax.grid(True, alpha=0.3)

    title_parts = []
    if antenna_name:
        title_parts.append(antenna_name)
    title_parts.append(f"{freq_mhz:.0f} MHz")
    if cut_label:
        title_parts.append(cut_label)
    ax.set_title(" — ".join(title_parts), fontsize=12)

    fig.tight_layout(pad=1.2)
    return _fig_to_png_buffer(fig, dpi)
