"""
图形配置数据模型
================
ChartConfig 定义需要生成哪些图形、视角参数、输出方式。
支持从模板自动检测图形需求。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set



# ═══════════════════════════════════════════════════════════════
# 标题匹配正则 — 英文 + 中文
# ═══════════════════════════════════════════════════════════════

_CHART_PATTERNS: Dict[str, List[str]] = {
    # A 类: 3D 方向图
    "pattern_3d_gain": [
        r"3D.*Gain.*(Pattern|Radiation|方向图)",
        r"3D.*增益.*方向图",
        r"球面.*(增益|Gain).*(方向图|Pattern)",
    ],
    "pattern_3d_eirp": [
        r"3D.*EIRP.*(Pattern|方向图)",
        r"3D.*EIRP.*方向图",
    ],
    "pattern_3d_ar": [
        r"3D.*(AR|Axial|Polarization).*(Pattern|方向图)",
        r"3D.*(轴比|AR|极化).*方向图",
    ],
    # B 类: 频点曲线
    "chart_eff_freq": [
        r"(Eff|Efficiency).*(vs|over|Frequency|频率)",
        r"效率.*(vs|频率)",
    ],
    "chart_gain_freq": [
        r"(Peak\s?)?Gain.*(vs|over|Frequency|频率)",
        r"(峰值\s?)?增益.*(vs|频率)",
    ],
    "chart_dir_freq": [
        r"Directivity.*(vs|over|Frequency|频率)",
        r"方向性.*(vs|频率)",
    ],
    "chart_lag_freq": [
        r"Gain.*Theta.*(vs|over|频率)",
        r"(增益|LAG).*(角度|Theta).*(vs|频率)",
    ],
    "chart_trp_freq": [
        r"TRP((?!NHPRP).)*(vs|over|Frequency|频率)",
        r"TRP.*(vs|频率)",
    ],
    "chart_trp_nhprp": [
        r"TRP.*NHPRP",
        r"TRP.*NHPRP",
    ],
    "chart_ar_freq": [
        r"(AR|Axial)((?!3D).)*(vs|over|Frequency|频率)",
        r"(轴比|AR)((?!3D).)*(vs|频率)",
    ],
    # C 类: 2D 切面
    "cut_2d_polar": [
        r"Polar.*(Cut|Plot|切面|图)",
        r"极坐标.*(切面|图)",
    ],
    "cut_2d_rect": [
        r"(Rect|Cartesian).*(Cut|Plot|切面|图)",
        r"直角坐标.*(切面|图)",
    ],
}

# 从列类型推导 B 类图表的映射
_COLTYPE_TO_CHART = {
    "efficiency_pct": "chart_eff_freq",
    "efficiency_db": "chart_eff_freq",
    "gain": "chart_gain_freq",
    "directivity": "chart_dir_freq",
    "lag_range": "chart_lag_freq",
    "lag_single": "chart_lag_freq",
    "trp": "chart_trp_freq",
    "ar_single": "chart_ar_freq",
    "ar_range": "chart_ar_freq",
    "peak_eirp": "chart_trp_freq",
}


@dataclass
class ChartConfig:
    """图形生成配置。

    所有图表分为三类:
      - A 类: 3D 球面方向图（每频点 1 张 PNG）
      - B 类: 频点-参数曲线（openpyxl 原生图表嵌入 Excel）
      - C 类: 2D 切面图（每频点 PNG）
    """

    # A 类: 3D 方向图
    pattern_3d_gain: bool = False
    pattern_3d_eirp: bool = False
    pattern_3d_ar: bool = False

    # B 类: 频点曲线
    chart_eff_freq: bool = False
    chart_gain_freq: bool = False
    chart_dir_freq: bool = False
    chart_lag_freq: bool = False
    chart_trp_freq: bool = False
    chart_trp_nhprp: bool = False
    chart_ar_freq: bool = False
    chart_lag_vs_phi: bool = False      # LAG vs Phi 散点图 (待修复: 数据结构需重写)
    chart_ar_vs_phi: bool = False       # AR  vs Phi 散点图 (待修复: 数据结构需重写)

    # B 类子选择: 具体角度/范围 (为空时自动使用模板默认值)
    gain_chart_angles: List[float] = field(default_factory=list)   # PK Gain + 指定 θ 单角度
    gain_chart_ranges: List[tuple] = field(default_factory=list)   # 指定 θ 范围
    ar_chart_angles: List[float] = field(default_factory=list)     # AR 指定 θ 单角度
    ar_chart_ranges: List[tuple] = field(default_factory=list)     # AR 指定 θ 范围

    # C 类: 2D 切面
    cut_2d_polar: bool = False
    cut_2d_rect: bool = False

    # 视角参数
    elev: float = 30.0
    azim: float = -60.0
    dpi: int = 150
    step_deg: float = 5.0          # 3D 图形采样精度 (°)

    # 输出方式
    embed_in_excel: bool = True
    save_png_folder: Optional[str] = None

    # ── 属性 ──

    @property
    def has_any_a_class(self) -> bool:
        return self.pattern_3d_gain or self.pattern_3d_eirp or self.pattern_3d_ar

    @property
    def has_any_b_class(self) -> bool:
        return (self.chart_eff_freq or self.chart_gain_freq or
                self.chart_dir_freq or self.chart_lag_freq or
                self.chart_trp_freq or self.chart_trp_nhprp or
                self.chart_ar_freq or self.chart_lag_vs_phi or
                self.chart_ar_vs_phi)

    @property
    def has_any_c_class(self) -> bool:
        return self.cut_2d_polar or self.cut_2d_rect

    @property
    def has_any_pattern_or_cut(self) -> bool:
        """是否有需要逐频点生成的图形（A 或 C 类）。"""
        return self.has_any_a_class or self.has_any_c_class

    # ── 合并 ──

    def merge(self, other: "ChartConfig") -> "ChartConfig":
        """合并两个配置（OR 逻辑），视角参数取 self 的值。"""
        fields = [
            "pattern_3d_gain", "pattern_3d_eirp", "pattern_3d_ar",
            "chart_eff_freq", "chart_gain_freq", "chart_dir_freq",
            "chart_lag_freq", "chart_trp_freq", "chart_trp_nhprp",
            "chart_ar_freq", "chart_lag_vs_phi", "chart_ar_vs_phi", "cut_2d_polar", "cut_2d_rect",
        ]
        merged = ChartConfig(
            elev=self.elev, azim=self.azim, dpi=self.dpi,
            step_deg=self.step_deg,
            embed_in_excel=self.embed_in_excel,
            save_png_folder=self.save_png_folder,
            gain_chart_angles=list(set(self.gain_chart_angles + other.gain_chart_angles)),
            gain_chart_ranges=list(set(self.gain_chart_ranges + other.gain_chart_ranges)),
            ar_chart_angles=list(set(self.ar_chart_angles + other.ar_chart_angles)),
            ar_chart_ranges=list(set(self.ar_chart_ranges + other.ar_chart_ranges)),
        )
        for f in fields:
            setattr(merged, f, getattr(self, f) or getattr(other, f))
        return merged

    # ── 工厂方法 ──

    @classmethod
    def from_template(cls, template_path: str) -> "ChartConfig":
        """扫描模板文件：元数据行 + 列头 → 自动检测图形需求。

        扫描策略:
          1. 在数据列头行之前的所有行中搜索匹配标题正则
          2. 从模板列类型推导 B 类图表
          3. 合并为默认启用的 ChartConfig
        """
        import openpyxl
        wb = openpyxl.load_workbook(template_path, data_only=True)
        config = ChartConfig()
        col_types: Set[str] = set()

        try:
            for ws in wb.worksheets:
                max_row = ws.max_row or 100
                max_col = ws.max_column or 20

                # 扫描元数据行（在 Frequency 列头之前）
                header_row = None
                for row_idx in range(1, min(max_row + 1, 200)):
                    row_texts = []
                    for c_idx in range(1, max_col + 1):
                        v = ws.cell(row_idx, c_idx).value
                        if v is not None:
                            row_texts.append(str(v).strip())

                    # 检查是否到了 Frequency 列头行
                    for t in row_texts:
                        if _match_text(t, [r"(?i)freq", r"(?i)频率"]):
                            header_row = row_idx
                            break

                    if header_row is not None:
                        # 此行为列头行 —— 解析列类型
                        for c_idx in range(1, max_col + 1):
                            v = ws.cell(header_row, c_idx).value
                            if v is not None:
                                from .excel_reader import _parse_sheet
                                # 简化: 直接通过文本判断
                                col_type = _classify_column_text(str(v).strip())
                                if col_type:
                                    col_types.add(col_type)
                        break

                    # 元数据行：搜索图表标题
                    for t in row_texts:
                        for chart_key, patterns in _CHART_PATTERNS.items():
                            if _match_text(t, patterns):
                                setattr(config, chart_key, True)
                                break
        finally:
            wb.close()

        # 从列类型推导 B 类图表
        for ct in col_types:
            chart_key = _COLTYPE_TO_CHART.get(ct)
            if chart_key:
                setattr(config, chart_key, True)

        # NHPRP 存在 → 多线图
        if any(c in col_types for c in ("nhprp_45", "nhprp_30", "nhprp_225")):
            config.chart_trp_nhprp = True

        return config

    @classmethod
    def from_template_headers(cls, headers: List[str], col_types: Set[str]) -> "ChartConfig":
        """从列头文本列表和 col_type 集合推导图形需求。

        用于 UI 对话框在已有 SheetInfo 的情况下快速推导。
        """
        config = ChartConfig()

        # 扫描列头文本
        for h in headers:
            for chart_key, patterns in _CHART_PATTERNS.items():
                if _match_text(h, patterns):
                    setattr(config, chart_key, True)

        # 从 col_type 推导
        for ct in col_types:
            chart_key = _COLTYPE_TO_CHART.get(ct)
            if chart_key:
                setattr(config, chart_key, True)

        if any(c in col_types for c in ("nhprp_45", "nhprp_30", "nhprp_225")):
            config.chart_trp_nhprp = True

        return config

    @classmethod
    def all_chart_keys(cls) -> List[str]:
        """返回所有图形 flag 的 key 列表（不含视角参数和角度列表）。"""
        return [
            "pattern_3d_gain", "pattern_3d_eirp", "pattern_3d_ar",
            "chart_eff_freq", "chart_gain_freq", "chart_dir_freq",
            "chart_lag_freq", "chart_trp_freq", "chart_trp_nhprp",
            "chart_ar_freq", "chart_lag_vs_phi", "chart_ar_vs_phi", "cut_2d_polar", "cut_2d_rect",
        ]

    @classmethod
    def all_sub_angle_keys(cls) -> List[str]:
        """返回所有子角度列表的 key。"""
        return ["gain_chart_angles", "gain_chart_ranges",
                "ar_chart_angles", "ar_chart_ranges"]

    @classmethod
    def chart_labels(cls) -> Dict[str, str]:
        """返回图形 key → 中文显示名称映射。"""
        return {
            "pattern_3d_gain": "3D 增益方向图",
            "pattern_3d_eirp": "3D EIRP 方向图",
            "pattern_3d_ar": "3D 轴比方向图",
            "chart_eff_freq": "效率 vs 频率",
            "chart_gain_freq": "峰值增益 vs 频率",
            "chart_dir_freq": "方向性 vs 频率",
            "chart_lag_freq": "增益@角度 vs 频率",
            "chart_trp_freq": "TRP vs 频率",
            "chart_trp_nhprp": "TRP+NHPRP vs 频率",
            "chart_ar_freq": "轴比 vs 频率",
        "chart_lag_vs_phi": "LAG vs Phi 散点图",
        "chart_ar_vs_phi": "AR vs Phi 散点图",
            "cut_2d_polar": "极坐标切面图",
            "cut_2d_rect": "直角坐标切面图",
        }

    @classmethod
    def chart_categories(cls) -> Dict[str, List[str]]:
        """返回图形分类: 类别名 → [chart_key, ...]"""
        return {
            "A 类: 3D 方向图": [
                "pattern_3d_gain", "pattern_3d_eirp", "pattern_3d_ar",
            ],
            "B 类: 频点曲线": [
                "chart_eff_freq", "chart_gain_freq", "chart_dir_freq",
                "chart_lag_freq", "chart_trp_freq", "chart_trp_nhprp",
                "chart_ar_freq",
            ],
            "C 类: 2D 切面图": [
                "cut_2d_polar", "cut_2d_rect",
            ],
        }


# ═══════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════

def _match_text(text: str, patterns: List[str]) -> bool:
    """检查 text 是否匹配任一正则 pattern。"""
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def _classify_column_text(text: str) -> Optional[str]:
    """从列头文本推导 col_type（简化版，JSON 模式优先，fallback 到内置正则）。"""
    from .excel_reader import (
        _classify_by_json_patterns, is_frequency_column, is_directivity_column,
        is_efficiency_column, is_gain_column, is_trp_column, is_nhprp_45_column,
        is_nhprp_30_column, is_peak_eirp_column, is_ar_single_column,
        is_ar_range_column, is_nhprp_225_column, is_uh_prp_column,
        is_lh_prp_column, detect_ratio_column_type,
        is_boresight_phi_column, is_boresight_theta_column,
        is_max_power_column, is_min_power_column,
        is_avg_gain_column, is_avg_power_column,
    )
    # JSON 用户模式优先
    json_type = _classify_by_json_patterns(text)
    if json_type is not None:
        return json_type
    if is_frequency_column(text): return "frequency"
    if is_directivity_column(text): return "directivity"
    if is_efficiency_column(text):
        return "efficiency_pct"
    if is_gain_column(text): return "gain"
    if is_trp_column(text): return "trp"
    if is_nhprp_45_column(text): return "nhprp_45"
    if is_nhprp_30_column(text): return "nhprp_30"
    if is_peak_eirp_column(text): return "peak_eirp"
    if is_ar_single_column(text): return "ar_single"
    if is_ar_range_column(text): return "ar_range"
    if is_nhprp_225_column(text): return "nhprp_225"
    if is_uh_prp_column(text): return "uh_prp"
    if is_lh_prp_column(text): return "lh_prp"
    ratio = detect_ratio_column_type(text)
    if ratio: return ratio
    if is_boresight_phi_column(text): return "boresight_phi"
    if is_boresight_theta_column(text): return "boresight_theta"
    if is_max_power_column(text): return "max_power"
    if is_min_power_column(text): return "min_power"
    if is_avg_gain_column(text): return "avg_gain"
    if is_avg_power_column(text): return "avg_power"
    return None
