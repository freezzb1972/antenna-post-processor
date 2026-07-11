"""
方向图数据类型注册表 (单一真源, 纯逻辑无 Qt)
=============================================
统一定义 11 种方向图数据类型: 物理量 ↔ 显示名 ↔ image_key ↔ 单位 ↔ 依赖数据。
查看器 (graph_viewer) 与 报告 (chart_config/plotter) 都从此表派生, 消除双套枚举。

依赖 (deps): 幅度类只需 "logmag"; 极化/相位类必须 "phase" (无相位数据时不可用)。
动态可用性由 available_keys(has_phase) 决定 → 有源发射/接收/aborted 无相位时自动降级。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PatternType:
    key: str            # 统一内部 key
    display: str        # 显示名 (英文技术缩写)
    image_key: str      # 报告 plotter image key
    viewer_key: str     # graph_data 输出的 key (查看器用)
    unit: str           # dBi / dB / deg
    kind: str           # "magnitude" (半径归一) | "phase" (常数球+相位色)
    deps: frozenset     # 依赖数据: {"logmag"} 或 {"phase"}


# 11 种类型 (全部可 3D)。顺序 = 默认显示顺序。
PATTERN_TYPES: list[PatternType] = [
    PatternType("gain",        "Gain (dBi)",      "3d_gain",        "gain_db",     "dBi", "magnitude", frozenset({"logmag"})),
    PatternType("eirp",        "EIRP (dBi)",      "3d_eirp",        "gain_db",     "dBi", "magnitude", frozenset({"logmag"})),  # EIRP≡Gain(无P_in)
    PatternType("etheta",      "E_θ (dB)",        "3d_etheta",      "theta_db",    "dB",  "magnitude", frozenset({"logmag"})),
    PatternType("ephi",        "E_φ (dB)",        "3d_ephi",        "phi_db",      "dB",  "magnitude", frozenset({"logmag"})),
    PatternType("total_power", "Total Power (dBi)","3d_total_power","total_power",  "dBi", "magnitude", frozenset({"logmag"})),
    PatternType("theta_phase", "E_θ Phase (°)",   "3d_theta_phase", "theta_phase", "deg", "phase",     frozenset({"phase"})),
    PatternType("phi_phase",   "E_φ Phase (°)",   "3d_phi_phase",   "phi_phase",   "deg", "phase",     frozenset({"phase"})),
    PatternType("ar",          "AR (dB)",         "3d_ar",          "ar_linear",   "dB",  "magnitude", frozenset({"phase"})),
    PatternType("rhcp",        "RHCP (dBi)",      "3d_rhcp",        "rhcp_db",     "dBi", "magnitude", frozenset({"phase"})),
    PatternType("lhcp",        "LHCP (dBi)",      "3d_lhcp",        "lhcp_db",     "dBi", "magnitude", frozenset({"phase"})),
    PatternType("cpxpi",       "CP-XPI (dB)",     "3d_cpxpi",       "cpxpi_db",    "dB",  "magnitude", frozenset({"phase"})),
]

BY_KEY: dict[str, PatternType] = {p.key: p for p in PATTERN_TYPES}
BY_VIEWER_KEY: dict[str, PatternType] = {p.viewer_key: p for p in PATTERN_TYPES}


def available_keys(has_phase: bool) -> list[str]:
    """按数据可用性返回可用类型 key。has_phase=False → 相位/极化类不可用。"""
    present = {"logmag"} | ({"phase"} if has_phase else set())
    return [p.key for p in PATTERN_TYPES if p.deps <= present]


def viewer_keys(has_phase: bool = True) -> list[str]:
    """查看器用: 可用类型的 graph_data key 列表 (按注册顺序, 去重)。
    eirp≡gain 共用 gain_db → 查看器只保留一个。"""
    avail = set(available_keys(has_phase))
    seen: list[str] = []
    for p in PATTERN_TYPES:
        if p.key in avail and p.viewer_key not in seen:
            seen.append(p.viewer_key)
    return seen


def display_of(viewer_key: str) -> str:
    """graph_data key → 显示名。"""
    p = BY_VIEWER_KEY.get(viewer_key)
    return p.display if p else viewer_key


def kind_of(viewer_key: str) -> str:
    """graph_data key → kind (magnitude/phase)。"""
    p = BY_VIEWER_KEY.get(viewer_key)
    return p.kind if p else "magnitude"
