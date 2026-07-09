"""
ChartInstance 图表实例模型 — 唯一数据源
========================================
从 ChartConfig + OutputConfig 展开为扁平的图表实例列表。
每个 ChartInstance = 一张输出图。驱动 Word 布局 + Pipeline 生成。

设计原则:
  - 图表名字 = 类型名 + 参数详情, 合成唯一名
  - Config 对象不变, ChartInstance 是派生视图
  - sort_order 和 enabled 是用户可编辑的运行时状态
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChartCategory(str, Enum):
    """图表类别, 对应 ChartConfig 中 A/B/C 三类。"""
    A_3D = "A"       # 3D 方向图: 每频点 per view_angle
    B_FREQ = "B"     # 频点-参数曲线: 所有频点一张
    C_2D = "C"       # 2D 俯仰面切面: 每频点 per phi
    Z_AZIMUTH = "Z"  # 方位面极坐标: 每频点 per chart


# 标准标签库: config_key → 中文标签
_CHART_LABELS: dict[str, str] = {
    # A 类
    "pattern_3d_gain": "3D Gain 方向图",
    "pattern_3d_eirp": "3D EIRP 方向图",
    "pattern_3d_ar": "3D AR 方向图",
    "pattern_3d_etheta": "3D Eθ 方向图",
    "pattern_3d_ephi": "3D Eφ 方向图",
    # B 类
    "chart_eff_freq": "Efficiency vs 频率",
    "chart_gain_freq": "Gain vs 频率",
    "chart_dir_freq": "Directivity vs 频率",
    "chart_lag_freq": "LAG vs 频率",
    "chart_trp_freq": "TRP vs 频率",
    "chart_trp_nhprp": "NHPRP vs 频率",
    "chart_ar_freq": "AR vs 频率",
    # C 类 2D
    "cut_2d_polar": "极坐标俯仰面切面图",
    "cut_2d_rect": "直角坐标俯仰面切面图",
    # C 类 azimuth
}


@dataclass
class ChartInstance:
    """单张输出图 — 最小单位。"""

    instance_id: str          # "azimuth_polar_0", "3d_gain_v0", "2d_polar_phi90"
    parent_type: str          # ChartConfig/OutputConfig 字段名
    category: ChartCategory   # A / B / C / Z
    label: str                # 唯一显示名: "Gain 极坐标方位面 (θ=0°,30°)"
    image_key: str            # 对应 plotter 的 image key: "azimuth_polar_0"
    per_freq: bool            # True=A/C/Z 每频点, False=B 全局
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    sort_order: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.instance_id, "parent": self.parent_type,
            "cat": self.category.value, "label": self.label,
            "key": self.image_key, "per_freq": self.per_freq,
            "params": self.params, "enabled": self.enabled,
            "order": self.sort_order,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ChartInstance:
        return cls(
            instance_id=d["id"], parent_type=d["parent"],
            category=ChartCategory(d["cat"]), label=d["label"],
            image_key=d["key"], per_freq=d.get("per_freq", True),
            params=d.get("params", {}), enabled=d.get("enabled", True),
            sort_order=d.get("order", 0),
        )


# ═══════════════════════════════════════════════════════════════
# 展开函数
# ═══════════════════════════════════════════════════════════════

def expand_to_instances(
    chart_config,
    output_config,
    mode: int = 0,
    existing_instances: list[ChartInstance] | None = None,
) -> list[ChartInstance]:
    """从 Config 对象展开为图表实例列表。

    Args:
        chart_config: ChartConfig 或 None
        output_config: OutputConfig 或 None
        mode: 0=无源, 1=TRP, 2=TIS
        existing_instances: 已有的实例列表 (保留 enabled + sort_order)

    Returns:
        完整的实例列表, 按 sort_order 排序
    """
    instances: list[ChartInstance] = []
    order_counter = [0]

    # 已有实例查找表
    existing_map: dict[str, ChartInstance] = {}
    if existing_instances:
        existing_map = {ci.instance_id: ci for ci in existing_instances}

    def _add(ci: ChartInstance):
        old = existing_map.get(ci.instance_id)
        if old:
            ci.enabled = old.enabled
            ci.sort_order = old.sort_order
        else:
            ci.sort_order = order_counter[0]
            order_counter[0] += 1
        instances.append(ci)

    # ── A 类 3D 方向图 ──
    if chart_config:
        _a_keys = ["pattern_3d_gain", "pattern_3d_eirp", "pattern_3d_ar",
                   "pattern_3d_etheta", "pattern_3d_ephi"]
        if mode == 0:
            _a_keys.remove("pattern_3d_eirp")
        elif mode == 1:
            _a_keys.remove("pattern_3d_ar")

        for key in _a_keys:
            if not getattr(chart_config, key, False):
                continue
            pairs = chart_config.view_angle_pairs or [(chart_config.elev, chart_config.azim)]
            for vi, (el, az) in enumerate(pairs):
                if len(pairs) == 1:
                    img_key = _3D_IMAGE_KEYS.get(key, key)
                    label = _CHART_LABELS.get(key, key)
                    cid = img_key
                else:
                    img_key = f"{_3D_IMAGE_KEYS.get(key, key)}_v{vi}"
                    label = f"{_CHART_LABELS.get(key, key)} 视角{vi+1}"
                    cid = f"{key}_v{vi}"
                _add(ChartInstance(
                    instance_id=cid, parent_type=key, category=ChartCategory.A_3D,
                    label=label, image_key=img_key, per_freq=True,
                    params={"elev": float(el), "azim": float(az), "view_index": vi},
                ))

    # ── B 类 频点曲线 ──
    _B_KEYS = ["chart_eff_freq", "chart_gain_freq", "chart_dir_freq",
               "chart_lag_freq", "chart_trp_freq", "chart_trp_nhprp", "chart_ar_freq"]
    if chart_config:
        for key in _B_KEYS:
            if getattr(chart_config, key, False):
                _add(ChartInstance(
                    instance_id=key, parent_type=key, category=ChartCategory.B_FREQ,
                    label=_CHART_LABELS.get(key, key), image_key=key, per_freq=False,
                ))

    # ── C 类 2D 切面 ──
    if chart_config:
        for flag, label_base, phi_angles, img_prefix in [
            ("cut_2d_polar", "极坐标俯仰面切面图", chart_config.cut_2d_phi_angles, "2d_polar_phi"),
            ("cut_2d_rect", "直角坐标俯仰面切面图", chart_config.cut_2d_phi_angles, "2d_rect_phi"),
        ]:
            if getattr(chart_config, flag, False):
                angles = phi_angles if phi_angles else [0, 90]
                for phi in sorted(set(angles)):
                    cid = f"{flag}_phi{phi:.0f}"
                    img_key = f"{img_prefix}{phi:.0f}"
                    _add(ChartInstance(
                        instance_id=cid, parent_type=flag, category=ChartCategory.C_2D,
                        label=f"{label_base} (φ={phi:.0f}°)", image_key=img_key,
                        per_freq=True, params={"phi_angle": float(phi)},
                    ))

    # ── Z 类 azimuth ──
    if output_config:
        for flag, label_base, angle_charts_attr in [
            ("cut_azimuth_polar", "Gain 极坐标方位面", "angle_charts"),
            ("cut_azimuth_polar_ar", "AR 极坐标方位面", "angle_charts_ar"),
            ("cut_azimuth_polar_rhcp", "RHCP 极坐标方位面", "angle_charts_rhcp"),
            ("cut_azimuth_polar_lhcp", "LHCP 极坐标方位面", "angle_charts_lhcp"),
        ]:
            if getattr(output_config, flag, False):
                charts = getattr(output_config, angle_charts_attr, [[]])
                for ci, angles in enumerate(charts):
                    if not angles:
                        continue
                    angles_str = ", ".join(f"{a:.0f}°" for a in sorted(set(angles)))
                    if len(charts) == 1:
                        cid = flag
                        img_key = _AZ_IMG_KEYS.get(flag, flag)
                        label = f"{label_base} (θ={angles_str})"
                    else:
                        cid = f"{flag}_{ci}"
                        img_key = f"{_AZ_IMG_KEYS.get(flag, flag)}_{ci}"
                        label = f"{label_base} #{ci+1} (θ={angles_str})"
                    _add(ChartInstance(
                        instance_id=cid, parent_type=flag, category=ChartCategory.Z_AZIMUTH,
                        label=label, image_key=img_key, per_freq=True,
                        params={"angles": [float(a) for a in sorted(set(angles))]},
                    ))



    instances.sort(key=lambda x: x.sort_order)
    return instances


# image key 映射: config_key → plotter image key prefix
_3D_IMAGE_KEYS = {
    "pattern_3d_gain": "3d_gain",
    "pattern_3d_eirp": "3d_eirp",
    "pattern_3d_ar": "3d_ar",
    "pattern_3d_etheta": "3d_etheta",
    "pattern_3d_ephi": "3d_ephi",
}

_AZ_IMG_KEYS = {
}
