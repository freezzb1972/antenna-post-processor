"""
渲染器抽象层
============
提供统一的 3D/2D 图形渲染接口。默认 Matplotlib CPU 渲染，
预留 Cloud GPU 渲染接口，可选 PyVista GPU 渲染。
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm
from matplotlib.colors import LinearSegmentedColormap

# ═══════════════════════════════════════════════════════════════
# EMQuest 风格色彩映射
# ═══════════════════════════════════════════════════════════════

_EMQUEST_COLORS = [
    (0.0,   (0.0, 0.0, 0.55)),     # deep navy
    (0.12,  (0.0, 0.2, 0.75)),     # blue
    (0.25,  (0.0, 0.55, 0.9)),     # light blue
    (0.4,   (0.0, 0.75, 0.85)),    # cyan
    (0.55,  (0.0, 0.8, 0.25)),     # green
    (0.7,   (0.85, 0.9, 0.0)),     # yellow
    (0.85,  (0.95, 0.45, 0.0)),    # orange
    (1.0,   (0.85, 0.0, 0.0)),     # red
]

EMQUEST_CMAP = LinearSegmentedColormap.from_list("emquest", _EMQUEST_COLORS)


# ═══════════════════════════════════════════════════════════════
# 抽象基类
# ═══════════════════════════════════════════════════════════════

class BaseRenderer(ABC):
    """渲染器抽象基类。"""

    @abstractmethod
    def render_3d_pattern(
        self,
        theta_deg: np.ndarray,
        phi_deg: np.ndarray,
        gain_dbi: np.ndarray,
        freq_mhz: float,
        *,
        elev: float = 30.0,
        azim: float = -60.0,
        dpi: int = 150,
        title: str = "",
        antenna_name: str = "",
        colormap: str = "emquest",
    ) -> io.BytesIO:
        """渲染 3D 球面方向图。"""
        ...

    @abstractmethod
    def render_2d_polar(
        self,
        angles_deg: np.ndarray,
        gain_dbi: np.ndarray,
        freq_mhz: float,
        *,
        cut_label: str = "",
        dpi: int = 150,
        antenna_name: str = "",
    ) -> io.BytesIO:
        """渲染 2D 极坐标切面图。"""
        ...

    @abstractmethod
    def render_2d_rect(
        self,
        angles_deg: np.ndarray,
        gain_dbi: np.ndarray,
        freq_mhz: float,
        *,
        xlabel: str = "Theta (deg)",
        cut_label: str = "",
        dpi: int = 150,
        antenna_name: str = "",
    ) -> io.BytesIO:
        """渲染 2D 直角坐标切面图。"""
        ...

    @abstractmethod
    def render_azimuth_polar(
        self,
        phi_deg: np.ndarray,
        curves: list[tuple[float, np.ndarray]],
        freq_mhz: float,
        *,
        antenna_name: str = "",
        dpi: int = 150,
        ylabel: str = "Gain (dBi)",
    ) -> io.BytesIO:
        """渲染方位面极坐标切面图。

        Args:
            phi_deg: Phi 角度数组 (°)，作为极坐标角度轴。
            curves: [(theta_deg, values_over_phi), ...]，每个 tuple
                    是一条 Theta 曲线在 Phi 上的取值。
            freq_mhz: 频率 (MHz)。
            antenna_name: 天线名（标题用）。
            dpi: 图像分辨率。
            ylabel: 径向轴标签 ("Gain (dBi)" 或 "AR (dB)")。
        """
        ...

    @abstractmethod
    def render_gain_vs_theta(
        self,
        theta_deg: np.ndarray,
        values: np.ndarray,
        freq_mhz: float,
        *,
        antenna_name: str = "",
        dpi: int = 150,
        ylabel: str = "Gain (dBi)",
    ) -> io.BytesIO:
        """渲染 Gain vs Theta 2D Cartesian 线图 (θ=0-70° 峰值增益)。

        Args:
            theta_deg: Theta 角度数组 (°)
            values: 每个 theta 角度对应的增益值 (dBi)
            freq_mhz: 频率 (MHz)
        """
        ...

    def close(self):
        """释放渲染器资源（可选覆盖）。"""
        pass


# ═══════════════════════════════════════════════════════════════
# Matplotlib CPU 渲染器（默认）
# ═══════════════════════════════════════════════════════════════

class MatplotlibRenderer(BaseRenderer):
    """基于 Matplotlib 的 CPU 渲染器。零额外依赖。"""

    def render_3d_pattern(
        self,
        theta_deg: np.ndarray,
        phi_deg: np.ndarray,
        gain_dbi: np.ndarray,
        freq_mhz: float,
        *,
        elev: float = 30.0,
        azim: float = -60.0,
        dpi: int = 150,
        title: str = "",
        antenna_name: str = "",
        colormap: str = "emquest",
    ) -> io.BytesIO:
        """EMQuest 风格 3D 球面方向图。

        特性:
          - 自定义蓝→红渐变色彩
          - 灰色半透明参考球 (0 dBi)
          - Theta 纬线环 (30°, 60°, 90°)
          - 轴标注 + θ=0° 方向箭头
          - colorbar + 标题
        """
        theta = np.deg2rad(theta_deg)
        phi = np.deg2rad(phi_deg)
        TH, PH = np.meshgrid(theta, phi)

        R = np.abs(gain_dbi)
        X = R * np.sin(TH) * np.cos(PH)
        Y = R * np.sin(TH) * np.sin(PH)
        Z = R * np.cos(TH)

        fig = plt.figure(figsize=(9, 7), dpi=dpi)
        ax = fig.add_subplot(111, projection="3d")

        # 选择 colormap
        cmap = EMQUEST_CMAP if colormap == "emquest" else plt.get_cmap(colormap)

        # 曲面着色
        norm = plt.Normalize(gain_dbi.min(), gain_dbi.max())
        surf = ax.plot_surface(
            X, Y, Z,
            facecolors=cmap(norm(gain_dbi)),
            rstride=1, cstride=1,
            alpha=0.88, shade=True,
            linewidth=0, antialiased=True,
        )

        # wireframe 叠加
        stride = max(1, min(len(phi_deg), len(theta_deg)) // 25)
        ax.plot_wireframe(X, Y, Z, rstride=stride, cstride=stride,
                          color="gray", linewidth=0.25, alpha=0.25)

        # 参考球 (0 dBi)
        _add_reference_sphere(ax, theta_deg, phi_deg)

        # Theta 环
        _add_theta_rings(ax, theta_deg, phi_deg)

        # 轴标注
        _add_axis_labels_3d(ax, R.max())

        # colorbar
        mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
        mappable.set_array(gain_dbi)
        cbar = fig.colorbar(mappable, ax=ax, shrink=0.55, aspect=20, pad=0.06)
        cbar.set_label("Total Gain (dBi)", fontsize=10, labelpad=8)
        cbar.ax.tick_params(labelsize=7)

        # 标题
        title_parts = []
        if antenna_name:
            title_parts.append(antenna_name)
        title_parts.append(f"{freq_mhz:.0f} MHz")
        if title:
            title_parts.append(title)
        ax.set_title(" — ".join(title_parts), fontsize=12, pad=10)

        # 关闭轴线框
        ax.xaxis.pane.fill = False
        ax.yaxis.pane.fill = False
        ax.zaxis.pane.fill = False
        ax.grid(False)

        fig.tight_layout(pad=0.5)
        buf = _fig_to_png_buffer(fig, dpi)
        return buf

    def render_2d_polar(
        self,
        angles_deg: np.ndarray,
        gain_dbi: np.ndarray,
        freq_mhz: float,
        *,
        cut_label: str = "",
        dpi: int = 150,
        antenna_name: str = "",
    ) -> io.BytesIO:
        """2D 极坐标切面图。"""
        theta_rad = np.deg2rad(angles_deg)
        fig, ax = plt.subplots(subplot_kw={"projection": "polar"},
                               dpi=dpi, figsize=(7, 6))

        ax.plot(theta_rad, gain_dbi, "b-", linewidth=1.2)
        ax.fill(theta_rad, gain_dbi, alpha=0.1, color="blue")

        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_thetagrids(range(0, 360, 30),
                          labels=[f"{d}°" for d in range(0, 360, 30)],
                          fontsize=10)

        title_parts = []
        if antenna_name:
            title_parts.append(antenna_name)
        title_parts.append(f"{freq_mhz:.0f} MHz")
        if cut_label:
            title_parts.append(cut_label)
        ax.set_title(" — ".join(title_parts), fontsize=12, pad=18)

        _setup_polar_radial_ticks(ax)

        ax.set_ylabel("Gain (dBi)", fontsize=10, labelpad=20)
        ax.grid(True, alpha=0.4)

        fig.tight_layout(pad=1.5)
        return _fig_to_png_buffer(fig, dpi)

    def render_2d_rect(
        self,
        angles_deg: np.ndarray,
        gain_dbi: np.ndarray,
        freq_mhz: float,
        *,
        xlabel: str = "Theta (deg)",
        cut_label: str = "",
        dpi: int = 150,
        antenna_name: str = "",
    ) -> io.BytesIO:
        """2D 直角坐标切面图。"""
        fig, ax = plt.subplots(dpi=dpi, figsize=(8, 5))

        ax.plot(angles_deg, gain_dbi, "b-", linewidth=1.2)
        ax.fill_between(angles_deg, gain_dbi, gain_dbi.min() - 5,
                        alpha=0.08, color="blue")

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

    def render_azimuth_polar(
        self,
        phi_deg: np.ndarray,
        curves: list[tuple[float, np.ndarray]],
        freq_mhz: float,
        *,
        antenna_name: str = "",
        dpi: int = 150,
        ylabel: str = "Gain (dBi)",
        title: str = "",
    ) -> io.BytesIO:
        """方位面极坐标切面图：Phi 角轴 + 多条 Theta 曲线。"""
        phi_rad = np.deg2rad(phi_deg)

        colors = ["#E74C3C", "#2980B9", "#27AE60", "#F39C12",
                  "#8E44AD", "#1ABC9C", "#E67E22", "#2C3E50"]
        linestyles = ["-", "--", "-.", ":"]

        fig, ax = plt.subplots(subplot_kw={"projection": "polar"},
                               dpi=dpi, figsize=(7, 7))

        sorted_curves = sorted(curves, key=lambda x: x[0])

        phi_close = np.empty(len(phi_rad) + 1)
        phi_close[:-1] = phi_rad
        phi_close[-1] = phi_rad[0] + 2 * np.pi

        for i, (theta_angle, gain_1d) in enumerate(sorted_curves):
            color = colors[i % len(colors)]
            ls = linestyles[(i // len(colors)) % len(linestyles)]
            label = f"θ={theta_angle:.0f}°"
            gain_close = np.empty(len(gain_1d) + 1)
            gain_close[:-1] = gain_1d
            gain_close[-1] = gain_1d[0]
            ax.plot(phi_close, gain_close, color=color, linestyle=ls,
                    linewidth=1.2, label=label)

        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_thetagrids(range(0, 360, 30),
                          labels=[f"{d}°" for d in range(0, 360, 30)],
                          fontsize=10)

        # 标题: 频率+ylabel 合一 (由 title 参数控制)
        if title:
            ax.set_title(title, fontsize=12, pad=12)
        else:
            ax.set_title(f"{freq_mhz:.0f}MHz - {ylabel}", fontsize=12, pad=12)

        ax.grid(True, alpha=0.4)

        _setup_polar_radial_ticks(ax)

        if len(sorted_curves) > 1:
            ax.legend(loc="upper right", fontsize=10, framealpha=0.7)

        fig.tight_layout(pad=1.0)
        return _fig_to_png_buffer(fig, dpi)

    def render_gain_vs_theta(
        self,
        theta_deg: np.ndarray,
        values: np.ndarray,
        freq_mhz: float,
        *,
        antenna_name: str = "",
        dpi: int = 150,
        ylabel: str = "Gain (dBi)",
    ) -> io.BytesIO:
        """渲染 Gain vs Theta 2D Cartesian 线图 (θ=0-70° 峰值增益)。"""
        fig, ax = plt.subplots(figsize=(6, 4), dpi=dpi)
        ax.plot(theta_deg, values, "o-", linewidth=1.5, markersize=3, color="#1f77b4")
        ax.set_xlabel("Theta (°)")
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(theta_deg[0] - 1, theta_deg[-1] + 1)

        lo, hi = np.min(values), np.max(values)
        margin = max((hi - lo) * 0.1, 0.5)
        ax.set_ylim(lo - margin, hi + margin)
        ax.set_title(f"{freq_mhz:.0f} MHz" + (f" — {antenna_name}" if antenna_name else ""),
                     fontsize=10)

        fig.tight_layout()
        return _fig_to_png_buffer(fig, dpi)

    def render_freq_curve_dual(self, freqs: list,
                                v1: list, label1: str,
                                v2: list, label2: str, *,
                                title: str = "", dpi: int = 150,
                                gap_mhz: int = 10) -> io.BytesIO:
        """双Y轴频点曲线: 压缩多段单轴, 线连续。"""
        threshold = gap_mhz if gap_mhz > 0 else 999999
        gap_vis = 10.0
        x = []; xt = []; xl = []; off = 0.0
        seg_i = 0; seg_start = 0
        for i in range(1, len(freqs) + 1):
            if i == len(freqs) or freqs[i] - freqs[i-1] > threshold:
                ei = i; sf = freqs[seg_start:ei]
                if seg_i > 0:
                    off += (freqs[seg_start] - freqs[seg_start-1]) - gap_vis
                    xt.append(freqs[seg_start-1] - off_prev)
                    xl.append(f"{freqs[seg_start-1]:.0f}")
                    xt.append(freqs[seg_start] - off)
                    xl.append(f"{freqs[seg_start]:.0f}")
                off_prev = off
                for f in sf:
                    x.append(f - off)
                lo, hi = int(np.ceil(sf[0])), int(np.floor(sf[-1]))
                span = hi - lo
                # Nice step: 10, 20, 50, 100...
                raw = span / 4.0
                mag = 10 ** int(np.floor(np.log10(raw))) if raw > 0 else 1
                r = raw / mag
                if r < 1.5:       ival = mag
                elif r < 3:        ival = 2 * mag
                elif r < 7:        ival = 5 * mag
                else:              ival = 10 * mag
                ival = max(10, int(ival))
                # Round lo up to next multiple of ival
                t0 = ((lo + ival - 1) // ival) * ival
                for t in range(t0, hi, ival):
                    if min(t - sf[0], sf[-1] - t) < ival * 0.8:
                        continue
                    xt.append(t - off)
                    xl.append(f"{t}")
                seg_i += 1; seg_start = i
        # 首尾频率标注
        xt.insert(0, x[0]); xl.insert(0, f"{freqs[0]:.0f}")
        xt.append(x[-1]); xl.append(f"{freqs[-1]:.0f}")

        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=dpi)
        # 分段绘制双Y轴, 段间不连线
        seg_i2 = 0; seg_start2 = 0
        for i2 in range(1, len(freqs) + 1):
            if i2 == len(freqs) or freqs[i2] - freqs[i2-1] > (gap_mhz if gap_mhz > 0 else 999999):
                _render_dual_y_axes(ax, x[seg_start2:i2], v1[seg_start2:i2],
                                    label1 if seg_i2 == 0 else "", v2[seg_start2:i2],
                                    label2 if seg_i2 == 0 else "")
                seg_i2 += 1; seg_start2 = i2
        ax.grid(True, alpha=0.3)
        ax.set_xticks(xt)
        ax.set_xticklabels(xl, fontsize=10)
        ax.tick_params(axis='x', rotation=0)
        return _fig_to_png_buffer(fig, dpi)
    def render_freq_curve(self, freqs: list, values: list, *,
                          label: str = "", ylabel: str = "",
                          title: str = "", dpi: int = 150,
                          gap_mhz: int = 10) -> io.BytesIO:
        """B 类频点曲线: 压缩多段到单轴, 线连续, 端点+等差整数刻度。"""
        threshold = gap_mhz if gap_mhz > 0 else 999999
        gap_vis = 10.0  # 段间视觉间距
        x = []; xt = []; xl = []; off = 0.0
        seg_i = 0; seg_start = 0
        for i in range(1, len(freqs) + 1):
            if i == len(freqs) or freqs[i] - freqs[i-1] > threshold:
                ei = i; sf = freqs[seg_start:ei]
                if seg_i > 0:
                    off += (freqs[seg_start] - freqs[seg_start-1]) - gap_vis
                    # 段边界频率
                    xt.append(freqs[seg_start-1] - off_prev)
                    xl.append(f"{freqs[seg_start-1]:.0f}")
                    xt.append(freqs[seg_start] - off)
                    xl.append(f"{freqs[seg_start]:.0f}")
                off_prev = off
                for f in sf:
                    x.append(f - off)
                # 段内整数等差刻度, 跳过距边界 < 半步的
                lo, hi = int(np.ceil(sf[0])), int(np.floor(sf[-1]))
                span = hi - lo
                # Nice step: 10, 20, 50, 100...
                raw = span / 4.0
                mag = 10 ** int(np.floor(np.log10(raw))) if raw > 0 else 1
                r = raw / mag
                if r < 1.5:       ival = mag
                elif r < 3:        ival = 2 * mag
                elif r < 7:        ival = 5 * mag
                else:              ival = 10 * mag
                ival = max(10, int(ival))
                # Round lo up to next multiple of ival
                t0 = ((lo + ival - 1) // ival) * ival
                for t in range(t0, hi, ival):
                    if min(t - sf[0], sf[-1] - t) < ival * 0.8:
                        continue
                    xt.append(t - off)
                    xl.append(f"{t}")
                seg_i += 1; seg_start = i
        # 首尾频率标注
        xt.insert(0, x[0]); xl.insert(0, f"{freqs[0]:.0f}")
        xt.append(x[-1]); xl.append(f"{freqs[-1]:.0f}")

        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=dpi)
        # 分段绘制, 段间不连线
        seg_i2 = 0; seg_start2 = 0
        for i2 in range(1, len(freqs) + 1):
            if i2 == len(freqs) or freqs[i2] - freqs[i2-1] > (gap_mhz if gap_mhz > 0 else 999999):
                ax.plot(x[seg_start2:i2], values[seg_start2:i2], "o-",
                        linewidth=1.5, markersize=4, label=(label or ylabel) if seg_i2 == 0 else "")
                seg_i2 += 1; seg_start2 = i2
        ax.set_ylabel(ylabel or label)
        ax.grid(True, alpha=0.3)
        ax.set_xticks(xt)
        ax.set_xticklabels(xl, fontsize=10)
        ax.tick_params(axis='x', rotation=0)
        if values:
            lo, hi = min(values), max(values)
            m = (hi - lo) * 0.1 if hi != lo else 1.0
            ax.set_ylim(lo - m, hi + m)
        if label:
            ax.legend(fontsize=10)
        fig.tight_layout()
        return _fig_to_png_buffer(fig, dpi)
# Cloud GPU 渲染器（预留接口）
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 公共双Y轴渲染 (供 viewer + Word 报告共用)
# ═══════════════════════════════════════════════════════════════

def _render_dual_y_axes(ax, freqs, v1, label1, v2, label2):
    """在给定 axes 上绘制双Y轴频点曲线。

    左轴 (蓝色实线): v1, 右轴 (红色虚线): v2.
    供 MatplotlibRenderer.render_freq_curve_dual 和 GraphViewer 共用。
    """
    ax1 = ax
    ax1.plot(freqs, v1, "o-", markersize=4, color="#1f77b4")
    ax1.set_ylabel(label1, color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(freqs, v2, "s--", markersize=4, color="#d62728")
    ax2.set_ylabel(label2, color="#d62728")
    ax2.tick_params(axis="y", labelcolor="#d62728")
    return ax1, ax2


def _setup_polar_radial_ticks(ax):
    """极坐标径向刻度: 动态范围, 整数等差, 外圈紧贴数据, 标签@15°。

    遍历 nice steps (1,2,5,10,20,50,100...), 选 4-8 圈且外圈最贴近 max 的方案。
    中心 = 最低数据向下取整 (可为负数)。
    """
    yl = ax.get_ylim()
    vmin, vmax = yl[0], yl[1]
    if vmax - vmin <= 0:
        vmax = vmin + 10

    best_ticks = None
    best_outer_gap = float('inf')
    for step in [1, 2, 5, 10, 20, 50, 100, 200, 500]:
        outer = int(np.ceil(vmax / step)) * step
        inner = int(np.floor(vmin / step)) * step
        n = (outer - inner) // step + 1
        if 4 <= n <= 8:  # 4-8 圈理想
            gap = outer - vmax
            if gap < best_outer_gap:
                best_outer_gap = gap
                best_ticks = list(range(inner, outer + step, step))
    if best_ticks is None:  # fallback
        step = max(1, int(round((vmax - vmin) / 5)))
        inner = int(np.floor(vmin))
        outer = int(np.ceil(vmax / step)) * step
        best_ticks = list(range(inner, outer + step, step))

    ax.set_ylim(best_ticks[0], best_ticks[-1])
    ax.set_yticks(best_ticks)
    ax.set_yticklabels([f"{v}" for v in best_ticks], fontsize=10)
    # 确保中心点刻度也显示
    for t in ax.yaxis.get_major_ticks():
        t.label1.set_visible(True)
    ax.set_rlabel_position(15)


def _detect_freq_gaps(freqs: list, gap_mhz: int = 10) -> list[tuple[int, int]]:
    """检测频段间隙 (>gap_mhz), 返回 [(start, end), ...] 段索引列表。"""
    threshold = gap_mhz if gap_mhz > 0 else 999999
    segments = []
    seg_start = 0
    for i in range(1, len(freqs)):
        if freqs[i] - freqs[i-1] > threshold:
            segments.append((seg_start, i))
            seg_start = i
    segments.append((seg_start, len(freqs)))
    return segments


class CloudRenderer(BaseRenderer):
    """云端渲染器 — REST API 调用远程 GPU 渲染服务。

    接口约定:
      POST /api/v1/render/3d
        Body: {"theta": [...], "phi": [...], "gain": [[...]],
               "freq_mhz": 900, "elev": 30, "azim": -60, "dpi": 150,
               "title": "", "antenna_name": ""}
        Response: image/png bytes

      POST /api/v1/render/2d/polar
      POST /api/v1/render/2d/rect

    若云端不可达或未配置，自动 fallback 到 MatplotlibRenderer。
    """

    def __init__(self, endpoint: str = "", api_key: str = "",
                 max_workers: int = 4, timeout: float = 30.0):
        self._endpoint = endpoint.rstrip("/") if endpoint else ""
        self._api_key = api_key
        self._max_workers = max_workers
        self._timeout = timeout
        self._fallback = MatplotlibRenderer()

    @property
    def is_configured(self) -> bool:
        return bool(self._endpoint)

    def _is_available(self) -> bool:
        if not self._endpoint:
            return False
        try:
            try:
                import requests
            except ImportError:
                raise ImportError(
                    "CloudRenderer requires the 'requests' library. "
                    "Install it with: pip install requests")
            resp = requests.get(f"{self._endpoint}/api/v1/health",
                              timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    # ── 核心分流逻辑: try-remote-or-fallback ──

    def _post_render(self, path: str, payload: dict) -> io.BytesIO:
        """POST 到云端渲染服务，返回 PNG 字节流。"""
        try:
            import requests
        except ImportError:
            raise ImportError(
                "CloudRenderer requires the 'requests' library. "
                "Install it with: pip install requests")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        resp = requests.post(
            f"{self._endpoint}{path}",
            json=payload,
            headers=headers,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        buf = io.BytesIO(resp.content)
        buf.seek(0)
        return buf

    def _render_remote_or_fallback(self, method_name: str, path: str,
                                    payload: dict, args: tuple, kwargs: dict) -> io.BytesIO:
        """统一的 try-remote-or-fallback 分流器。

        Args:
            method_name: BaseRenderer 方法名 (如 "render_3d_pattern")
            path: REST API 路径
            payload: JSON 请求体
            args: 位置参数 (传给 fallback)
            kwargs: 关键字参数 (传给 fallback)
        """
        if not self._is_available():
            return getattr(self._fallback, method_name)(*args, **kwargs)
        try:
            return self._post_render(path, payload)
        except Exception:
            return getattr(self._fallback, method_name)(*args, **kwargs)

    # ── 渲染方法: 全部委托给 _render_remote_or_fallback ──

    def render_3d_pattern(self, theta_deg, phi_deg, gain_dbi, freq_mhz,
                          *, elev=30.0, azim=-60.0, dpi=150,
                          title="", antenna_name="", colormap="emquest"):
        return self._render_remote_or_fallback(
            "render_3d_pattern", "/api/v1/render/3d",
            {"theta": theta_deg.tolist(), "phi": phi_deg.tolist(),
             "gain": gain_dbi.tolist(), "freq_mhz": freq_mhz,
             "elev": elev, "azim": azim, "dpi": dpi,
             "title": title, "antenna_name": antenna_name, "colormap": colormap},
            (theta_deg, phi_deg, gain_dbi, freq_mhz),
            {"elev": elev, "azim": azim, "dpi": dpi,
             "title": title, "antenna_name": antenna_name, "colormap": colormap})

    def render_2d_polar(self, angles_deg, gain_dbi, freq_mhz,
                        *, cut_label="", dpi=150, antenna_name=""):
        return self._render_remote_or_fallback(
            "render_2d_polar", "/api/v1/render/2d/polar",
            {"angles": angles_deg.tolist(), "gain": gain_dbi.tolist(),
             "freq_mhz": freq_mhz, "cut_label": cut_label, "dpi": dpi,
             "antenna_name": antenna_name},
            (angles_deg, gain_dbi, freq_mhz),
            {"cut_label": cut_label, "dpi": dpi, "antenna_name": antenna_name})

    def render_2d_rect(self, angles_deg, gain_dbi, freq_mhz,
                       *, xlabel="Theta (deg)", cut_label="", dpi=150,
                       antenna_name=""):
        return self._render_remote_or_fallback(
            "render_2d_rect", "/api/v1/render/2d/rect",
            {"angles": angles_deg.tolist(), "gain": gain_dbi.tolist(),
             "freq_mhz": freq_mhz, "xlabel": xlabel, "cut_label": cut_label,
             "dpi": dpi, "antenna_name": antenna_name},
            (angles_deg, gain_dbi, freq_mhz),
            {"xlabel": xlabel, "cut_label": cut_label, "dpi": dpi,
             "antenna_name": antenna_name})

    def render_azimuth_polar(self, phi_deg, curves, freq_mhz,
                             *, antenna_name="", dpi=150,
                             ylabel="Gain (dBi)"):
        return self._render_remote_or_fallback(
            "render_azimuth_polar", "/api/v1/render/2d/azimuth_polar",
            {"phi": phi_deg.tolist(),
             "curves": [(float(k), v.tolist()) for k, v in curves],
             "freq_mhz": freq_mhz, "antenna_name": antenna_name,
             "dpi": dpi, "ylabel": ylabel},
            (phi_deg, curves, freq_mhz),
            {"antenna_name": antenna_name, "dpi": dpi, "ylabel": ylabel})

    def render_gain_vs_theta(self, theta_deg, values, freq_mhz, *,
                              antenna_name="", dpi=150, ylabel="Gain (dBi)"):
        return self._render_remote_or_fallback(
            "render_gain_vs_theta", "/api/v1/render/2d/gain_vs_theta",
            {"theta": theta_deg.tolist(), "values": values.tolist(),
             "freq_mhz": freq_mhz, "antenna_name": antenna_name,
             "dpi": dpi, "ylabel": ylabel},
            (theta_deg, values, freq_mhz),
            {"antenna_name": antenna_name, "dpi": dpi, "ylabel": ylabel})


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def detect_available_renderers() -> dict:
    """检测当前环境可用的渲染器。"""
    result = {"matplotlib": True, "pyvista": False, "cloud": False}
    try:
        import pyvista as pv
        pl = pv.Plotter(off_screen=True, window_size=[100, 100])
        pl.close()
        result["pyvista"] = True
    except (ImportError, Exception):
        pass
    return result


def _fig_to_png_buffer(fig, dpi: int) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    buf.seek(0)
    plt.close(fig)
    return buf


# ═══════════════════════════════════════════════════════════════
# 3D 视觉增强 — 参考球 / Theta 环 / 轴标注
# ═══════════════════════════════════════════════════════════════

def _add_reference_sphere(ax, theta_deg, phi_deg):
    """在 gain=0 dBi 处画灰色虚线参考球。"""
    r = 1.0
    theta = np.deg2rad(theta_deg)
    phi = np.deg2rad(phi_deg)
    TH, PH = np.meshgrid(theta, phi)

    X = r * np.sin(TH) * np.cos(PH)
    Y = r * np.sin(TH) * np.sin(PH)
    Z = r * np.cos(TH)

    stride = max(1, min(len(phi_deg), len(theta_deg)) // 15)
    ax.plot_wireframe(X, Y, Z, rstride=stride, cstride=stride,
                      color="gray", linewidth=0.3, alpha=0.4,
                      linestyle="dotted")


def _add_theta_rings(ax, theta_deg, phi_deg):
    """在关键 theta 角处画纬线环。"""
    rt = 2.5
    phi = np.linspace(0, 2 * np.pi, 180)
    for t_deg in [30, 60, 90, 120, 150]:
        t = np.deg2rad(t_deg)
        x = rt * np.sin(t) * np.cos(phi)
        y = rt * np.sin(t) * np.sin(phi)
        z = rt * np.cos(t) * np.ones_like(phi)
        # 只在 Z ≥ 0 部分画（上半球）
        ax.plot(x, y, z, color="gray", linewidth=0.4, alpha=0.3,
                linestyle="dashed")


def _add_axis_labels_3d(ax, max_r: float):
    """添加轴标签和 θ=0° 方向箭头。"""
    lim = max_r * 1.3
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim, lim)

    ax.set_xlabel("X", fontsize=10, labelpad=4)
    ax.set_ylabel("Y", fontsize=10, labelpad=4)
    ax.set_zlabel("Z (θ=0°)", fontsize=10, labelpad=4)

    # θ=0° 方向箭头
    arrow_len = max_r * 1.15
    ax.quiver(0, 0, 0, 0, 0, arrow_len,
              color="red", linewidth=1.2, arrow_length_ratio=0.08,
              label="θ=0°")
