"""2D 切面图 — 统一数据模型与渲染函数

所有 2D 切面图 (俯仰面/方位面 × 极坐标/直角坐标 × 多参数) 共用此模块。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class CutChartEntry:
    """单个 2D 切面图条目 — 参数 + 方向 + 角度。"""
    param: str = "gain"                  # "gain" | "ar" | "rhcp" | "lhcp"
    direction: str = "phi"               # "phi"=俯仰面(固定φ扫θ), "theta"=方位面(固定θ扫φ)
    angles: list[float] = field(default_factory=lambda: [0.0])

    @property
    def label(self) -> str:
        """用户可读标签。"""
        pname = _PARAM_REGISTRY.get(self.param, {}).get("ylabel", self.param)
        dname = "俯仰面 φ" if self.direction == "phi" else "方位面 θ"
        ang = ", ".join(f"{a:.0f}°" for a in self.angles)
        return f"{pname}  {dname}={ang}"


@dataclass
class CutParam:
    """单个切面参数定义 — 俯仰面/方位面共用（运行时）。"""
    key: str = ""                        # "gain" | "ar" | "rhcp" | "lhcp" | "cpxpi"
    data: np.ndarray | None = None       # (n_phi, n_theta) 矩阵
    ylabel: str = ""                     # "Gain (dBi)" | "AR (dB)" | ...
    enabled: bool = False
    phi_angles: list[float] = field(default_factory=lambda: [0.0, 90.0])
    theta_angles: list[float] = field(default_factory=lambda: [30.0, 60.0])


# 已知参数注册表: key → ylabel + 数据属性名
_PARAM_REGISTRY = {
    "gain":  {"ylabel": "Gain (dBi)",  "attr": "gain_dbi"},
    "ar":    {"ylabel": "AR (dB)",     "attr": "ar_db"},
    "rhcp":  {"ylabel": "RHCP (dBi)",  "attr": "rhcp_db"},
    "lhcp":  {"ylabel": "LHCP (dBi)",  "attr": "lhcp_db"},
    "cpxpi": {"ylabel": "CP-XPI (dB)", "attr": "cp_xpi"},
}


def build_cut_params_from_entries(
    entries: list[CutChartEntry], data_map: dict,
) -> list[CutParam]:
    """从图表条目列表 + 数据字典构建 CutParam 列表。"""
    params = []
    for entry in entries:
        defn = _PARAM_REGISTRY.get(entry.param)
        if defn is None:
            continue
        data = data_map.get(defn["attr"])
        if data is None:
            continue
        p = CutParam(
            key=entry.param, data=data, ylabel=defn["ylabel"], enabled=True,
            phi_angles=[], theta_angles=[],  # 清空默认值
        )
        if entry.direction == "phi":
            p.phi_angles = list(entry.angles)
        else:
            p.theta_angles = list(entry.angles)
        params.append(p)
    return params


def build_cut_params(enabled_keys: set[str], data_map: dict,
                     phi_angles: list[float] | None = None,
                     theta_angles: list[float] | None = None,
                     ) -> list[CutParam]:
    """从启用的 key 集合 + 数据字典构建 CutParam 列表。"""
    params = []
    for key, defn in _PARAM_REGISTRY.items():
        data = data_map.get(defn["attr"])
        if data is None:
            continue
        p = CutParam(
            key=key, data=data, ylabel=defn["ylabel"],
            enabled=(key in enabled_keys),
        )
        if phi_angles:
            p.phi_angles = list(phi_angles)
        if theta_angles:
            p.theta_angles = list(theta_angles)
        params.append(p)
    return params


# ═══════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════

def _nearest_index(axis: np.ndarray, target: float) -> int:
    """找最近索引。"""
    return int(np.argmin(np.abs(axis - target)))


# ═══════════════════════════════════════════════════════════════
# 统一渲染函数
# ═══════════════════════════════════════════════════════════════

def render_phi_cuts(
    params: list[CutParam],
    theta_deg: np.ndarray,
    phi_deg: np.ndarray,
    freq_mhz: float,
    chart_config,
    renderer,
) -> dict[str, any]:
    """俯仰面切面: 固定 φ, 扫描 θ (Theta 轴) — 极坐标 + 直角坐标。

    每个启用的参数 → 一张图 (多个 Phi 角度 = 多条曲线)。
    极坐标图自动包含 φ+180° mirror (标准做法)。
    """
    images = {}
    n_phi = len(phi_deg)
    if n_phi < 2:
        return images

    polar_enabled = getattr(chart_config, 'cut_2d_polar', False)
    rect_enabled = getattr(chart_config, 'cut_2d_rect', False)
    if not polar_enabled and not rect_enabled:
        return images

    dpi = getattr(chart_config, 'dpi', 150)

    for p in params:
        if not p.enabled or p.data is None:
            continue
        # 收集所有角度的曲线
        curves = []
        for phi_target in sorted(set(p.phi_angles)):
            idx = _nearest_index(phi_deg, phi_target)
            nearest_phi = float(phi_deg[idx])
            label = f"φ={nearest_phi:.0f}°"
            curves.append((label, theta_deg, p.data[idx, :]))

        if not curves:
            continue

        if polar_enabled:
            key = f"2d_polar_{p.key}"
            images[key] = renderer.render_2d_polar(
                theta_deg, curves[0][2], freq_mhz,
                ylabel=p.ylabel, dpi=dpi, antenna_name="",
                curves=curves,
            )

        if rect_enabled:
            for label, a_deg, vals in curves:
                key = f"2d_rect_{p.key}_phi{label.replace('φ=', '').replace('°', '')}"
                images[key] = renderer.render_2d_rect(
                    a_deg, vals, freq_mhz,
                    cut_label=f"{label} {p.ylabel}",
                    ylabel=p.ylabel, dpi=dpi, antenna_name="",
                )

    return images


def render_theta_cuts(
    params: list[CutParam],
    theta_deg: np.ndarray,
    phi_deg: np.ndarray,
    freq_mhz: float,
    chart_config,
    azimuth_config,
    renderer,
) -> dict[str, any]:
    """方位面切面: 固定 θ, 扫描 φ (Phi 轴) — 极坐标 + 直角坐标。

    每个启用的参数 × 每个 Theta 角度 → 极坐标图和直角坐标图。
    """
    images = {}
    n_theta = len(theta_deg)
    if n_theta < 1:
        return images

    # 方位面开关只在 AzimuthReportConfig
    polar_enabled = getattr(azimuth_config, 'cut_azimuth_polar', False) if azimuth_config else False
    rect_enabled = getattr(azimuth_config, 'cut_azimuth_rect', False) if azimuth_config else False
    if not polar_enabled and not rect_enabled:
        return images

    az_dpi = azimuth_config.dpi if azimuth_config is not None and azimuth_config.dpi else 150

    for p in params:
        if not p.enabled or p.data is None:
            continue
        for theta_target in sorted(set(p.theta_angles)):
            idx = _nearest_index(theta_deg, theta_target)
            nearest_t = float(theta_deg[idx])
            d = p.data[:, idx]                             # 全 φ 方向的数据

            if polar_enabled:
                curves = [(nearest_t, d)]
                key = f"azimuth_polar_{p.key}_t{nearest_t:.0f}"
                images[key] = renderer.render_azimuth_polar(
                    phi_deg, curves, freq_mhz,
                    ylabel=p.ylabel, dpi=az_dpi, antenna_name="",
                )

            if rect_enabled:
                key = f"azimuth_rect_{p.key}_t{nearest_t:.0f}"
                images[key] = renderer.render_azimuth_rect(
                    phi_deg, d, freq_mhz,
                    ylabel=p.ylabel, dpi=az_dpi, antenna_name="",
                )

    return images
