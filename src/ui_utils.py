"""
UI 工具函数（无 Qt 依赖）
========================
纯函数，供 MainWindow 和各 Page 调用。
"""
from __future__ import annotations

from src.lag_config import LagConfig


def build_param_summary_text(
    test_mode: int,
    required_params: set[str],
    extra_params: set[str],
    lag_config: LagConfig,
    ar_lag_config: LagConfig | None = None,
) -> str:
    """构建天线参数摘要字符串。

    Args:
        test_mode: 0=无源, 1=TRP, 2=TIS
        required_params: 报告必需参数 key 集合
        extra_params: full_report 额外参数 key 集合
        lag_config: LAG/Gain 角度配置
        ar_lag_config: AR 角度配置（可选）

    Returns:
        多行摘要文本
    """
    mode_names = {0: "无源天线", 1: "有源发射 TRP", 2: "有源接收 TIS"}
    mode_str = mode_names.get(test_mode, "未知")

    lines = [f"测试模式: {mode_str}"]

    # 计算参数
    all_params = sorted(required_params | extra_params)
    # 转可读名称
    param_labels = _get_param_labels()
    param_names = [param_labels.get(k, k) for k in all_params]
    if param_names:
        lines.append(f"参数: {', '.join(param_names)}")
    else:
        lines.append("参数: (未选择)")

    # LAG 角度
    singles = lag_config.singles_sorted
    ranges = lag_config.ranges_sorted
    if singles or ranges:
        parts = [f"{a}°" for a in singles]
        if ranges:
            parts.append("范围: " + ", ".join(f"({lo}°–{hi}°)" for lo, hi in ranges))
        lines.append(f"Gain: {', '.join(parts)}")
    else:
        lines.append("Gain: (未设置)")

    # AR 角度
    if ar_lag_config and not ar_lag_config.is_empty():
        ar_s = ar_lag_config.singles_sorted
        ar_r = ar_lag_config.ranges_sorted
        parts = [f"{a}°" for a in ar_s]
        if ar_r:
            parts.append("范围: " + ", ".join(f"({lo}°–{hi}°)" for lo, hi in ar_r))
        lines.append(f"AR: {', '.join(parts)}")

    return "\n".join(lines)


def _get_param_labels() -> dict[str, str]:
    """返回参数 key → 人类可读名称的映射。"""
    return {
        "gain": "Gain",
        "directivity": "Directivity",
        "efficiency_pct": "Efficiency(%)",
        "efficiency_db": "Efficiency(dB)",
        "trp": "TRP",
        "nhprp_45": "NHPRP ±45°",
        "nhprp_30": "NHPRP ±30°",
        "nhprp_225": "NHPRP ±22.5°",
        "peak_eirp": "Peak EIRP",
        "ar_single": "AR(单角度)",
        "ar_range": "AR(范围)",
        "uh_prp": "UH PRP",
        "lh_prp": "LH PRP",
        "xpi_boresight": "XPI Boresight",
        "xpi_mean": "XPI Mean",
        "xpi_min": "XPI Min",
        "mismatch_loss_db": "Mismatch Loss",
        "pc_theta_mm": "PC Theta",
        "pc_phi_mm": "PC Phi",
        "boresight_phi": "Boresight Phi",
        "boresight_theta": "Boresight Theta",
        "max_power": "Max Power",
        "min_power": "Min Power",
        "avg_gain": "Avg Gain",
        "avg_power": "Avg Power",
        "lag_single": "LAG(单角度)",
        "lag_range": "LAG(范围)",
    }


def merge_params_from_columns(column_types: set[str]) -> set[str]:
    """从模板列类型推断需要的计算参数。

    从 column_patterns.json 的 col_type 映射到计算参数 key。

    Args:
        column_types: 模板列检测出的 col_type 集合

    Returns:
        需要计算的参数 key 集合
    """
    # col_type → 计算参数 key 映射
    COL_TYPE_TO_PARAM = {
        "frequency": set(),
        "directivity": {"directivity"},
        "efficiency_pct": {"efficiency_pct"},
        "efficiency_db": {"efficiency_db"},
        "total_efficiency_pct": {"total_efficiency_pct"},
        "total_efficiency_db": {"total_efficiency_db"},
        "gain": {"gain"},
        "lag_single": {"lag_single"},
        "lag_range": {"lag_range"},
        "trp": {"trp"},
        "nhprp_45": {"nhprp_45"},
        "nhprp_30": {"nhprp_30"},
        "nhprp_225": {"nhprp_225"},
        "peak_eirp": {"peak_eirp"},
        "ar_single": {"ar_single"},
        "ar_range": {"ar_range"},
        "uh_prp": {"uh_prp"},
        "lh_prp": {"lh_prp"},
        "boresight_phi": {"boresight_phi"},
        "boresight_theta": {"boresight_theta"},
        "max_power": {"max_power"},
        "min_power": {"min_power"},
        "avg_gain": {"avg_gain"},
        "avg_power": {"avg_power"},
        "xpi_boresight": {"xpi_boresight"},
        "xpi_mean": {"xpi_mean"},
        "xpi_min": {"xpi_min"},
        "mismatch_loss_db": {"mismatch_loss_db"},
        "pc_theta_mm": {"pc_theta_mm"},
        "pc_phi_mm": {"pc_phi_mm"},
        "unknown": set(),
    }

    result: set[str] = set()
    for ct in column_types:
        params = COL_TYPE_TO_PARAM.get(ct, {ct})
        result.update(params)
    return result


# ═══════════════════════════════════════════════════════════════
# 角度类型配置（单一定义, 底部栏/右边面板/字报告共用）
# ═══════════════════════════════════════════════════════════════

class AngleTypeInfo:
    """角度类型元数据: config 属性名、显示名、弹窗 key、是否有区间。"""
    __slots__ = ("attr", "label", "popup", "has_range", "param_keys")

    def __init__(self, attr: str, label: str, popup: str, has_range: bool, *param_keys: str):
        self.attr = attr
        self.label = label
        self.popup = popup
        self.has_range = has_range
        self.param_keys = param_keys


ANGLE_TYPE_CONFIG: dict[str, AngleTypeInfo] = {
    "lag": AngleTypeInfo("_lag_config", "Gain", "gain", True, "gain", "lag_single", "lag_range"),
    "ar": AngleTypeInfo("_ar_lag_config", "AR", "ar", True, "ar", "ar_single", "ar_range"),
    "rhcp": AngleTypeInfo("_rhcp_lag_config", "RHCP", "rhcp", False, "rhcp_single"),
    "cpxpi": AngleTypeInfo("_cpxpi_lag_config", "CP-XPI", "cpxpi", False, "cp_xpi_single"),
}
# 反向索引: param_key → info (用于 checkbox 循环中的 key 查找)
_ANGLE_BY_PARAM_KEY: dict[str, AngleTypeInfo] = {}
for _info in ANGLE_TYPE_CONFIG.values():
    for _k in _info.param_keys:
        _ANGLE_BY_PARAM_KEY[_k] = _info
"""角度类型 → 元数据的唯一数据源。底部栏、右边面板、Word 报告均从此读取。"""


# ═══════════════════════════════════════════════════════════════
# 通用文件工具
# ═══════════════════════════════════════════════════════════════

def next_available_filename(directory: str, base_name: str, ext: str = "",
                            mkdir: bool = False, sanitize: bool = False) -> str:
    """生成不重复的文件名: {name}_{YYYYMMDD}_{seq:02d}{ext}

    Args:
        directory: 目标目录
        base_name: 基础文件名
        ext: 扩展名 (含点, 如 ".xlsx")
        mkdir: 是否自动创建目录
        sanitize: 是否清理路径分隔符

    Returns:
        完整路径 (若 mkdir=False 且 dir 不存在则只返回文件名)
    """
    from datetime import date
    from pathlib import Path

    name = base_name.replace("/", "_").replace("\\", "_") if sanitize else base_name
    today = date.today().strftime("%Y%m%d")
    d = Path(directory)
    if mkdir:
        d.mkdir(parents=True, exist_ok=True)
    seq = 1
    while True:
        fname = f"{name}_{today}_{seq:02d}{ext}"
        if not (d / fname).exists():
            return str(d / fname) if mkdir else fname
        seq += 1
