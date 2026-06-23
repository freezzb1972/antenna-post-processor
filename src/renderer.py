"""
渲染器抽象层
============
提供统一的 3D/2D 图形渲染接口。默认 Matplotlib CPU 渲染，
预留 Cloud GPU 渲染接口，可选 PyVista GPU 渲染。
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple

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
        cbar.set_label("Total Gain (dBi)", fontsize=9, labelpad=8)
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


# ═══════════════════════════════════════════════════════════════
# Cloud GPU 渲染器（预留接口）
# ═══════════════════════════════════════════════════════════════

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

    def _post_render(self, path: str, payload: dict) -> io.BytesIO:
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

    def render_3d_pattern(self, theta_deg, phi_deg, gain_dbi, freq_mhz,
                          *, elev=30.0, azim=-60.0, dpi=150,
                          title="", antenna_name="", colormap="emquest"):
        if not self._is_available():
            return self._fallback.render_3d_pattern(
                theta_deg, phi_deg, gain_dbi, freq_mhz,
                elev=elev, azim=azim, dpi=dpi,
                title=title, antenna_name=antenna_name, colormap=colormap)

        try:
            return self._post_render("/api/v1/render/3d", {
                "theta": theta_deg.tolist(),
                "phi": phi_deg.tolist(),
                "gain": gain_dbi.tolist(),
                "freq_mhz": freq_mhz,
                "elev": elev, "azim": azim, "dpi": dpi,
                "title": title, "antenna_name": antenna_name,
                "colormap": colormap,
            })
        except Exception:
            return self._fallback.render_3d_pattern(
                theta_deg, phi_deg, gain_dbi, freq_mhz,
                elev=elev, azim=azim, dpi=dpi,
                title=title, antenna_name=antenna_name, colormap=colormap)

    def render_2d_polar(self, angles_deg, gain_dbi, freq_mhz,
                        *, cut_label="", dpi=150, antenna_name=""):
        if not self._is_available():
            return self._fallback.render_2d_polar(
                angles_deg, gain_dbi, freq_mhz,
                cut_label=cut_label, dpi=dpi, antenna_name=antenna_name)
        try:
            return self._post_render("/api/v1/render/2d/polar", {
                "angles": angles_deg.tolist(),
                "gain": gain_dbi.tolist(),
                "freq_mhz": freq_mhz,
                "cut_label": cut_label, "dpi": dpi,
                "antenna_name": antenna_name,
            })
        except Exception:
            return self._fallback.render_2d_polar(
                angles_deg, gain_dbi, freq_mhz,
                cut_label=cut_label, dpi=dpi, antenna_name=antenna_name)

    def render_2d_rect(self, angles_deg, gain_dbi, freq_mhz,
                       *, xlabel="Theta (deg)", cut_label="", dpi=150,
                       antenna_name=""):
        if not self._is_available():
            return self._fallback.render_2d_rect(
                angles_deg, gain_dbi, freq_mhz,
                xlabel=xlabel, cut_label=cut_label, dpi=dpi,
                antenna_name=antenna_name)
        try:
            return self._post_render("/api/v1/render/2d/rect", {
                "angles": angles_deg.tolist(),
                "gain": gain_dbi.tolist(),
                "freq_mhz": freq_mhz,
                "xlabel": xlabel, "cut_label": cut_label, "dpi": dpi,
                "antenna_name": antenna_name,
            })
        except Exception:
            return self._fallback.render_2d_rect(
                angles_deg, gain_dbi, freq_mhz,
                xlabel=xlabel, cut_label=cut_label, dpi=dpi,
                antenna_name=antenna_name)


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

    ax.set_xlabel("X", fontsize=8, labelpad=4)
    ax.set_ylabel("Y", fontsize=8, labelpad=4)
    ax.set_zlabel("Z (θ=0°)", fontsize=8, labelpad=4)

    # θ=0° 方向箭头
    arrow_len = max_r * 1.15
    ax.quiver(0, 0, 0, 0, 0, arrow_len,
              color="red", linewidth=1.2, arrow_length_ratio=0.08,
              label="θ=0°")
