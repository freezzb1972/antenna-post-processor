"""
方位面极坐标切面图 — 配置数据模型
===================================
OutputConfig 管理方位面极坐标图的生成选项、
输出路径、中间数据路径等。独立于 ChartConfig，关注点分离。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OutputConfig:
    """方位面极坐标报告配置。

    所有字段均可通过 from_dict() / to_dict() 序列化。
    """

    # ── Theta 范围峰值 ──
    pk_theta_ranges: list[float] = field(default_factory=list)
    # 例: [70.0] → 1条 0-70°峰值曲线, [70.0, 110.0] → 2条
    # 空列表 = 不生成峰值曲线
    antenna_name: str = ""                   # 天线名（标题用）
    freq_gap_mhz: int = 10                  # B类频点曲线多段间隔阈值(MHz), 0=不打断
    dual_y_enabled: bool = False            # B类频点曲线启用双Y轴配对
    share_radial_ticks: bool = False         # 配对图共用径向刻度
    show_heading: bool = False              # Word 是否生成章节标题
    show_caption: bool = False              # Word 图片上方是否显示题注

    # ── Word 布局模式 ──
    # "by_type": 每频点同行 2 列 (左 Gain 右 AR)
    # "sequential":   先全部 Gain（前加 Heading1），再全部 AR（前加 Heading1）
    word_layout_mode: str = "by_freq"

    # ── Word 图片尺寸 ──
    word_columns: int = 2                       # 列数: 1=单列, 2=双列
    word_image_width_pct: int = 100              # 图片宽度占列宽的百分比 (10-100)

    # ── Full Report 独立 Word 布局 ──
    fr_word_layout_mode: str = "by_freq"
    fr_word_columns: int = 2
    fr_word_image_width_pct: int = 100
    fr_show_heading: bool = False
    fr_show_caption: bool = False

    # ── 输出路径 — 图表 (Word) ──
    chart_output_dir: str = ""               # 图表输出目录
    chart_output_filename: str = ""          # 图表输出文件名

    # ── 输出路径 — 天线参数报告 (Excel) ──
    excel_output_dir: str = ""
    excel_output_filename: str = ""

    # ── 输出路径 — 中间数据 (多 sheet 单文件) ──
    data_output_dir: str = ""
    data_output_filename: str = ""

    # ── 渲染 ──
    dpi: int = 100

    # ── 内部标志 ──
    _angles_initialized: bool = False  # 角度是否已从 LAG 初始化过

    # ═══════════════════════════════════════════════════════════
    # 属性
    # ═══════════════════════════════════════════════════════════

    @property
    def has_any_azimuth(self) -> bool:
        """是否启用了 pk_theta_ranges。"""
        return bool(self.pk_theta_ranges)




    def is_empty(self) -> bool:
        """是否没有任何方位面图表启用。"""
        return not self.has_any_azimuth

    @staticmethod
    def normalize_angle_charts(data: list) -> list[list[float]]:
        """将旧格式(平列表)或新格式(list-of-lists)统一转为图表列表。"""
        return _normalize_to_charts(data)

    @property
    def chart_output_path(self) -> str:
        """完整的图表输出路径。"""
        if self.chart_output_dir and self.chart_output_filename:
            return str(Path(self.chart_output_dir) / self.chart_output_filename)
        return ""

    @property
    def excel_output_path(self) -> str:
        """完整的天线参数报告输出路径。"""
        if self.excel_output_dir and self.excel_output_filename:
            return str(Path(self.excel_output_dir) / self.excel_output_filename)
        return ""

    @property
    def data_output_path(self) -> str:
        """中间数据完整输出路径。"""
        if self.data_output_dir and self.data_output_filename:
            return str(Path(self.data_output_dir) / self.data_output_filename)
        return ""

    # ═══════════════════════════════════════════════════════════
    # 序列化
    # ═══════════════════════════════════════════════════════════

    def to_dict(self) -> dict:
        """序列化为 dict。"""
        return {
            "pk_theta_ranges": self.pk_theta_ranges,
            "antenna_name": self.antenna_name,
            "word_layout_mode": self.word_layout_mode,
            "word_columns": self.word_columns,
            "word_image_width_pct": self.word_image_width_pct,
            "fr_word_layout_mode": self.fr_word_layout_mode,
            "fr_word_columns": self.fr_word_columns,
            "fr_word_image_width_pct": self.fr_word_image_width_pct,
            "fr_show_heading": self.fr_show_heading,
            "fr_show_caption": self.fr_show_caption,
            "chart_output_dir": self.chart_output_dir,
            "chart_output_filename": self.chart_output_filename,
            "excel_output_dir": self.excel_output_dir,
            "excel_output_filename": self.excel_output_filename,
            "data_output_dir": self.data_output_dir,
            "data_output_filename": self.data_output_filename,
            "dpi": self.dpi,
            "freq_gap_mhz": self.freq_gap_mhz,
            "dual_y_enabled": self.dual_y_enabled,
            "share_radial_ticks": self.share_radial_ticks,
            "show_heading": self.show_heading,
            "show_caption": self.show_caption,
        }

    @classmethod
    def from_dict(cls, d: dict) -> OutputConfig:
        """从 dict 反序列化。"""
        return cls(
            pk_theta_ranges=list(d.get("pk_theta_ranges", [])),
            antenna_name=str(d.get("antenna_name", "")),
            word_layout_mode=str(d.get("word_layout_mode", "by_freq")),
            word_columns=int(d.get("word_columns", 2)),
            word_image_width_pct=int(d.get("word_image_width_pct", 100)),
            fr_word_layout_mode=str(d.get("fr_word_layout_mode", "by_type")),
            fr_word_columns=int(d.get("fr_word_columns", 2)),
            fr_word_image_width_pct=int(d.get("fr_word_image_width_pct", 100)),
            fr_show_heading=bool(d.get("fr_show_heading", True)),
            fr_show_caption=bool(d.get("fr_show_caption", False)),
            chart_output_dir=str(d.get("chart_output_dir", "")),
            chart_output_filename=str(d.get("chart_output_filename", "")),
            excel_output_dir=str(d.get("excel_output_dir", "")),
            excel_output_filename=str(d.get("excel_output_filename", "")),
            data_output_dir=str(d.get("data_output_dir", "")),
            data_output_filename=str(d.get("data_output_filename", "")),
            dpi=int(d.get("dpi", 100)),
            freq_gap_mhz=int(d.get("freq_gap_mhz", 10)),
            dual_y_enabled=bool(d.get("dual_y_enabled", False)),
            share_radial_ticks=bool(d.get("share_radial_ticks", False)),
            show_heading=bool(d.get("show_heading", True)),
            show_caption=bool(d.get("show_caption", False)),
        )

    # ═══════════════════════════════════════════════════════════
    # 合并
    # ═══════════════════════════════════════════════════════════

    def merge(self, other: OutputConfig) -> OutputConfig:
        """合并两个配置（OR 逻辑），角度取并集，路径取 self 优先。"""
        return OutputConfig(
            pk_theta_ranges=sorted(set(self.pk_theta_ranges + other.pk_theta_ranges)),
            antenna_name=self.antenna_name or other.antenna_name,
            word_layout_mode=self.word_layout_mode,
            word_columns=self.word_columns or other.word_columns,
            word_image_width_pct=self.word_image_width_pct or other.word_image_width_pct,
            fr_word_layout_mode=self.fr_word_layout_mode,
            fr_word_columns=self.fr_word_columns or other.fr_word_columns,
            fr_word_image_width_pct=self.fr_word_image_width_pct or other.fr_word_image_width_pct,
            fr_show_heading=self.fr_show_heading and other.fr_show_heading,
            fr_show_caption=self.fr_show_caption and other.fr_show_caption,
            chart_output_dir=self.chart_output_dir or other.chart_output_dir,
            chart_output_filename=self.chart_output_filename or other.chart_output_filename,
            excel_output_dir=self.excel_output_dir or other.excel_output_dir,
            excel_output_filename=self.excel_output_filename or other.excel_output_filename,
            data_output_dir=self.data_output_dir or other.data_output_dir,
            data_output_filename=self.data_output_filename or other.data_output_filename,
            dpi=self.dpi or other.dpi,
            freq_gap_mhz=self.freq_gap_mhz if self.freq_gap_mhz >= 0 else other.freq_gap_mhz,
            dual_y_enabled=self.dual_y_enabled or other.dual_y_enabled,
            share_radial_ticks=self.share_radial_ticks or other.share_radial_ticks,
            show_heading=self.show_heading and other.show_heading,
            show_caption=self.show_caption and other.show_caption,
        )

    # ═══════════════════════════════════════════════════════════
    # 默认路径计算
    # ═══════════════════════════════════════════════════════════

    def reset_to_defaults(self, source_path: str) -> None:
        """根据源文件路径重置所有输出路径为默认值。

        不重置 azimuth_cut_angles 和 antenna_name（尊重用户设置）。
        """
        source = Path(source_path)
        source_dir = str(source.parent)
        source_stem = source.stem

        self.chart_output_dir = source_dir
        self.chart_output_filename = f"{source_stem}图表报告.docx"
        self.excel_output_dir = source_dir
        self.excel_output_filename = f"{source_stem}_AntennaReport.xlsx"
        self.data_output_dir = source_dir
        self.data_output_filename = f"{source_stem}中间数据.xlsx"


# ═══════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════

def _flatten(data: list) -> list[float]:
    """将数据展平为 float 列表，兼容旧格式（平列表）和新格式（list-of-lists）。"""
    if not data:
        return []
    result = []
    for item in data:
        if isinstance(item, (int, float)):
            result.append(float(item))
        elif isinstance(item, (list, tuple)):
            result.extend(float(x) for x in item)
    return result


def _normalize_to_charts(data: list) -> list[list[float]]:
    """将数据统一转为图表列表格式 (list-of-lists)。

    旧格式: [0, 30, 60] → [[0, 30, 60]]  (单图表)
    新格式: [[0, 30], [60]] → 保持不变
    """
    if not data:
        return [[]]
    # 第一个元素是数字 → 旧格式平列表 → 包装为单图表
    if data and isinstance(data[0], (int, float)):
        return [[float(x) for x in data]]
    # 已经是的图表列表 → 深拷贝
    return [[float(x) for x in ch] for ch in data if ch]
