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
    def render_azimuth_rect(
        self,
        phi_deg: np.ndarray,
        values: np.ndarray,
        freq_mhz: float,
        *,
        ylabel: str = "Gain (dBi)",
        dpi: int = 150,
        antenna_name: str = "",
        cut_label: str = "",
    ) -> io.BytesIO:
        """2D 直角坐标方位面切面图 (Theta 切 — 固定 θ, 扫描 φ)。

        Args:
            phi_deg: Phi 角度数组 (°)，作为 X 轴。
            values: 每个 phi 角度对应的参数值。
            freq_mhz: 频率 (MHz)。
            ylabel: Y 轴标签。
            dpi: 图像分辨率。
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
        ylabel: str = "Gain (dBi)",
        mirror_angles_deg: np.ndarray | None = None,
        mirror_gain_dbi: np.ndarray | None = None,
        curves: list[tuple[str, np.ndarray, np.ndarray]] | None = None,
    ) -> io.BytesIO:
        """2D 极坐标切面图。

        支持单曲线模式 (angles_deg + gain_dbi) 或多曲线模式 (curves)。
        若提供 mirror_*, 则绘制 φ+180° 镜像于左侧 (负 theta 半区)。
        """
        theta_rad = np.deg2rad(angles_deg)
        fig, ax = plt.subplots(subplot_kw={"projection": "polar"},
                               dpi=dpi, figsize=(7, 6))

        colors = ["#2196F3", "#F44336", "#4CAF50", "#FF9800"]
        if curves:
            for i, (label, c_angles, c_values) in enumerate(curves):
                color = colors[i % len(colors)]
                rad = np.deg2rad(c_angles)
                ax.plot(rad, c_values, "-", linewidth=1.2, color=color, label=label)
                # mirror (左侧)
                mirror_rad = -rad  # 负角度 = 左半平面
                ax.plot(mirror_rad, c_values, "-", linewidth=1.2, color=color)
            if curves:
                ax.legend(fontsize=8, loc="upper right")
        else:
            ax.plot(theta_rad, gain_dbi, "-", linewidth=1.2, color="#2196F3", label=cut_label)
            if mirror_angles_deg is not None and mirror_gain_dbi is not None:
                mirror_rad = -np.deg2rad(mirror_angles_deg)  # 负角度 = 左半平面
                ax.plot(mirror_rad, mirror_gain_dbi, "-", linewidth=1.2,
                        color="#2196F3")

        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_thetagrids(range(0, 360, 30),
                          labels=[f"{d}°" for d in range(0, 360, 30)],
                          fontsize=10)

        title_parts = []
        if antenna_name:
            title_parts.append(antenna_name)
        title_parts.append(f"{freq_mhz:.0f} MHz")
        title_parts.append(ylabel)
        ax.set_title(" — ".join(title_parts), fontsize=12, pad=18)

        _setup_polar_radial_ticks(ax)
        ax.set_ylabel(ylabel, fontsize=10, labelpad=20)
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
        ylabel: str = "Gain (dBi)",
    ) -> io.BytesIO:
        """2D 直角坐标切面图。"""
        fig, ax = plt.subplots(dpi=dpi, figsize=(8, 5))

        ax.plot(angles_deg, gain_dbi, "-", linewidth=1.2, color="#2196F3")

        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
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

    def render_azimuth_rect(
        self,
        phi_deg: np.ndarray,
        values: np.ndarray,
        freq_mhz: float,
        *,
        ylabel: str = "Gain (dBi)",
        dpi: int = 150,
        antenna_name: str = "",
        cut_label: str = "",
    ) -> io.BytesIO:
        """2D 直角坐标方位面切面图 (Theta 切 — 固定 θ, 扫描 φ)。"""
        fig, ax = plt.subplots(dpi=dpi, figsize=(8, 5))

        ax.plot(phi_deg, values, "-", linewidth=1.2, color="#2196F3")

        ax.set_xlabel("Phi (deg)", fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
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
        ticks_override: list = None,  # 共享刻度时传入
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
        ax.autoscale_view()       # 先完成自动缩放
        ax.margins(y=0.05)         # 收紧径向边距

        if ticks_override is not None:
            # 共享刻度: 使用预计算值
            ax.set_ylim(ticks_override[0], ticks_override[-1])
            ax.set_yticks(ticks_override)
            ax.set_yticklabels([_tick_label(v) for v in ticks_override], fontsize=10)
            ax.set_rlabel_position(15)
            ax.annotate(_tick_label(ticks_override[0]),
                        xy=(np.deg2rad(15), ticks_override[0]),
                        fontsize=10, ha='center', va='center', color='#555555')
        else:
            _setup_polar_radial_ticks(ax)

        if len(sorted_curves) > 1:
            # 官方极坐标图例: 用极角偏移放到图外 (45° 方向 = 右上角)
            angle = np.deg2rad(45)
            ax.legend(loc="lower left", fontsize=9, framealpha=0.6,
                      bbox_to_anchor=(.5 + np.cos(angle)/2, .5 + np.sin(angle)/2))

        fig.subplots_adjust(left=0.08, right=0.92, top=0.92, bottom=0.08)
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
        x = []; xt = []; xl = []; off = 0.0; off_prev = 0.0
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
        # 分段绘制双Y轴, 段间不连线; twinx 只创建一次
        ax1 = ax
        ax2 = ax1.twinx()
        seg_i2 = 0; seg_start2 = 0
        for i2 in range(1, len(freqs) + 1):
            if i2 == len(freqs) or freqs[i2] - freqs[i2-1] > (gap_mhz if gap_mhz > 0 else 999999):
                sx = x[seg_start2:i2]; sv1 = v1[seg_start2:i2]; sv2 = v2[seg_start2:i2]
                ax1.plot(sx, sv1, "o-", markersize=4, color="#1f77b4")
                ax2.plot(sx, sv2, "s--", markersize=4, color="#d62728")
                seg_i2 += 1; seg_start2 = i2
        ax1.set_ylabel(label1, color="#1f77b4")
        ax1.tick_params(axis="y", labelcolor="#1f77b4")
        _set_cartesian_y_ticks(ax1, min(v1), max(v1))
        ax2.set_ylabel(label2, color="#d62728")
        ax2.tick_params(axis="y", labelcolor="#d62728")
        _set_cartesian_y_ticks(ax2, min(v2), max(v2))
        ax1.grid(True, alpha=0.3)
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
        x = []; xt = []; xl = []; off = 0.0; off_prev = 0.0
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
def _set_cartesian_y_ticks(ax, vmin: float, vmax: float, fontsize: int = 10):
    """Cartesian Y 轴 nice-step 刻度 (供 B 类曲线双Y轴)。"""
    span = vmax - vmin
    if span <= 0: span = 10
    best_ticks = None
    best_gap = float('inf')
    for step in [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000,
                 10000, 20000, 50000, 100000]:
        outer = int(np.ceil(vmax / step)) * step
        inner = int(np.floor(vmin / step)) * step
        n = (outer - inner) // step + 1
        if 4 <= n <= 8:
            gap = outer - vmax
            if gap < best_gap:
                best_gap = gap
                best_ticks = list(range(inner, outer + step, step))
    if best_ticks is None:
        step = max(1, int(round(span / 5)))
        inner = int(np.floor(vmin))
        outer = int(np.ceil(vmax / step)) * step
        best_ticks = list(range(inner, outer + step, step))
    ax.set_yticks(best_ticks)
    ax.set_yticklabels([f"{v}" for v in best_ticks], fontsize=fontsize)


def _render_dual_y_axes(ax, freqs, v1, label1, v2, label2):
    """在给定 axes 上绘制双Y轴频点曲线。

    左轴 (蓝色实线): v1, 右轴 (红色虚线): v2.
    供 MatplotlibRenderer.render_freq_curve_dual 和 GraphViewer 共用。
    """
    import matplotlib.ticker as ticker
    ax1 = ax
    ax1.plot(freqs, v1, "o-", markersize=4, color="#1f77b4")
    ax1.set_ylabel(label1, color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    _set_cartesian_y_ticks(ax1, min(v1), max(v1))
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(freqs, v2, "s--", markersize=4, color="#d62728")
    ax2.set_ylabel(label2, color="#d62728")
    ax2.tick_params(axis="y", labelcolor="#d62728")
    _set_cartesian_y_ticks(ax2, min(v2), max(v2))
    return ax1, ax2



def _tick_label(v: float) -> str:
    """格式化刻度标签: 整数用 int, 小数保留 1 位。"""
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v))}"
    return f"{v:.1f}"

def _setup_polar_radial_ticks(ax):
    """极坐标径向刻度 — 纯 Heckbert 算法。

    nice_step(span/5) → inner/outer 各自独立对齐步长 (step 可为小数)。
    每圈标注 + 字体 10pt + 标签 @15°。
    """
    yl = ax.get_ylim()
    vmin, vmax = yl[0], yl[1]
    if vmax - vmin <= 0:
        vmax = vmin + 10

    raw_step = (vmax - vmin) / 5.0
    if raw_step <= 0:
        raw_step = 2
    mag = 10 ** int(np.floor(np.log10(raw_step))) if raw_step > 0 else 1
    r = raw_step / mag
    if r <= 1: step = mag
    elif r <= 2: step = 2 * mag
    elif r <= 5: step = 5 * mag
    else: step = 10 * mag

    # 动态内缩: max(span×5%, step) 防止低值曲线贴中心
    span = vmax - vmin
    pad = max(span * 0.05, step)
    inner = int(np.floor((vmin - pad) / step)) * step
    outer = int(np.ceil(vmax / step)) * step

    ticks = [inner]
    while ticks[-1] + step <= outer + 1e-9:
        ticks.append(ticks[-1] + step)
    ticks = [round(t, 6) for t in ticks]


    ax.set_ylim(ticks[0], ticks[-1])
    import matplotlib.ticker as _ticker
    ax.yaxis.set_major_locator(_ticker.FixedLocator(ticks))
    ax.yaxis.set_minor_locator(_ticker.NullLocator())
    ax.set_yticks(ticks)
    ax.set_yticklabels([_tick_label(v) for v in ticks], fontsize=10)
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
                        *, cut_label="", dpi=150, antenna_name="",
                        mirror_angles_deg=None, mirror_gain_dbi=None):
        kwargs = {"cut_label": cut_label, "dpi": dpi, "antenna_name": antenna_name}
        fallback_args = (angles_deg, gain_dbi, freq_mhz)
        if mirror_angles_deg is not None:
            kwargs["mirror_angles_deg"] = mirror_angles_deg
            kwargs["mirror_gain_dbi"] = mirror_gain_dbi
            fallback_args = (angles_deg, gain_dbi, freq_mhz,
                             mirror_angles_deg, mirror_gain_dbi)
        return self._render_remote_or_fallback(
            "render_2d_polar", "/api/v1/render/2d/polar",
            {"angles": angles_deg.tolist(), "gain": gain_dbi.tolist(),
             "freq_mhz": freq_mhz, "cut_label": cut_label, "dpi": dpi,
             "antenna_name": antenna_name},
            fallback_args,
            kwargs)

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

    def render_azimuth_rect(self, phi_deg, values, freq_mhz, *,
                             ylabel="Gain (dBi)", dpi=150,
                             antenna_name="", cut_label=""):
        return self._render_remote_or_fallback(
            "render_azimuth_rect", "/api/v1/render/2d/azimuth_rect",
            {"phi": phi_deg.tolist(), "values": values.tolist(),
             "freq_mhz": freq_mhz, "antenna_name": antenna_name,
             "dpi": dpi, "ylabel": ylabel, "cut_label": cut_label},
            (phi_deg, values, freq_mhz),
            {"ylabel": ylabel, "dpi": dpi, "antenna_name": antenna_name,
             "cut_label": cut_label})

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
