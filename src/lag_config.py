"""
LAG (Linear Average Gain) 配置模型与模板列头解析
=====================================================

支持：
  - 任意 θ 单角度 LAG
  - 任意 θ 范围平均 LAG
  - 起始+步进批量生成
  - 从 Excel 列头自动解析
  - 预设保存/加载
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# 列头规范化
# ---------------------------------------------------------------------------

def normalize_header(text: str) -> str:
    """统一列头格式，消除无关差异。"""
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", " ")
    text = text.replace("（", "(").replace("）", ")")  # 全角 → 半角
    text = text.replace("  ", " ").strip()
    return text


# ---------------------------------------------------------------------------
# LAG 列头正则（容错匹配）
# ---------------------------------------------------------------------------

# 匹配 "Theta=0-90 LAG" / "Theta=60~90 LAG" / "θ=0-90°"
_RE_LAG_RANGE = re.compile(
    r"(?:Theta|θ)\s*[=＝]\s*(\d+\.?\d*)\s*[-–—~]\s*(\d+\.?\d*)",
    re.IGNORECASE,
)

# 匹配 "60-90LAG" / "0~90 LAG"（无 Theta= 前缀的 LAG 范围）
_RE_LAG_RANGE_NO_PREFIX = re.compile(
    r"(\d+\.?\d*)\s*[-–—~]\s*(\d+\.?\d*)\s*LAG",
    re.IGNORECASE,
)

# 匹配 "Theta=60" / "θ=70" / "Theta = 80"（但不能是范围）
_RE_LAG_SINGLE = re.compile(
    r"(?:Theta|θ)\s*[=＝]\s*(\d+\.?\d*)",
    re.IGNORECASE,
)

# 匹配 "60度LAG" / "90度 LAG"（无 Theta= 前缀的单角度 LAG）
_RE_LAG_SINGLE_NO_PREFIX = re.compile(
    r"(\d+\.?\d*)\s*度\s*LAG",
    re.IGNORECASE,
)

# is_*_column / _normalize_key 已移至 excel_reader.py（它们只被模板解析使用）
# ---------------------------------------------------------------------------
# 通用角度提取 — 不关心参数类型，从任意列头提取 θ 角度数值
# ---------------------------------------------------------------------------

# 单角度: "Theta=30", "θ=60°", "@45", "30度", "at 90°", "θ: 30"
_RE_ANGLE_SINGLE = re.compile(
    r"(?:Theta|θ)\s*[=＝:：]\s*(\d+\.?\d*)\s*°?|"
    r"@\s*(\d+\.?\d*)\s*°?|"
    r"(\d+\.?\d*)\s*度|"
    r"at\s+(\d+\.?\d*)\s*°?",
    re.IGNORECASE,
)

# 角度范围: "Theta=0-90", "θ=30~70", "@0–90°", "0-90 LAG", "30~60度"
_RE_ANGLE_RANGE = re.compile(
    r"(?:Theta|θ)\s*[=＝:：]\s*(\d+\.?\d*)\s*[-–—~]\s*(\d+\.?\d*)\s*°?|"
    r"@\s*(\d+\.?\d*)\s*[-–—~]\s*(\d+\.?\d*)\s*°?|"
    r"(\d+\.?\d*)\s*[-–—~]\s*(\d+\.?\d*)\s*(?:°|度)",
    re.IGNORECASE,
)


def extract_angles_from_headers(headers: list[str], param_prefix: str = "") -> tuple[list[float], list[tuple[float, float]]]:
    """通用角度提取: 从列头列表中解析所有 θ 角度值。

    不依赖参数类型关键词，只匹配数字角度模式。
    可按 param_prefix 过滤（如 "ar_", "rhcp_" 只处理对应列头）。

    Returns:
        (singles, ranges) — 单角度列表和范围列表
    """
    singles: list[float] = []
    ranges: list[tuple[float, float]] = []

    for raw in headers:
        h = normalize_header(raw)
        if not h:
            continue
        if param_prefix and param_prefix not in h.lower():
            continue

        # 先检测范围（避免 "0-90" 中的 0/90 被单角度误匹配）
        rm = _RE_ANGLE_RANGE.search(h)
        if rm:
            groups = [g for g in rm.groups() if g is not None]
            if len(groups) >= 2:
                lo, hi = float(groups[0]), float(groups[1])
                key = (min(lo, hi), max(lo, hi))
                if key not in ranges:
                    ranges.append(key)
                continue

        # 再检测单角度
        sm = _RE_ANGLE_SINGLE.search(h)
        if sm:
            val = float(next(g for g in sm.groups() if g is not None))
            if val not in singles:
                singles.append(val)

    return singles, ranges


# ---------------------------------------------------------------------------
# LAG 配置数据类
# ---------------------------------------------------------------------------

@dataclass
class LagConfig:
    """用户可配置的 LAG 计算规格。

    Attributes:
        single_angles: 单个 θ 角度列表，如 [60, 70, 80, 90]。
        ranges: θ 范围列表，如 [(0, 90), (60, 90)]。
    """

    single_angles: list[float] = field(default_factory=list)
    ranges: list[tuple[float, float]] = field(default_factory=list)

    # --- 工厂方法 ---

    @classmethod
    def from_start_step(
        cls, start: float, end: float, step: float
    ) -> LagConfig:
        """起始+步进快速生成单角度列表。

        Example:
            LagConfig.from_start_step(0, 90, 10)
            → single_angles = [0, 10, 20, ..., 90]
        """
        angles: list[float] = []
        a = start
        while a <= end + 1e-9:
            angles.append(round(a, 6))
            a += step
        return cls(single_angles=angles)

    @classmethod
    def from_template_headers(cls, headers: list[str]) -> LagConfig:
        """从 Excel 列头自动解析 LAG 需求。

        识别模式：
          - ``Theta=60`` / ``θ=60``  → 单角度 60°
          - ``60度LAG`` / ``90度 LAG`` → 单角度 60°, 90°
          - ``Theta=0-90 LAG``       → 范围 (0, 90)
          - ``60-90LAG`` / ``0-90 LAG`` → 范围 (60, 90)

        注意：列头可能含换行符 ``\\n``、全角括号等，先做规范化。
        """
        singles, ranges = extract_angles_from_headers(headers)
        return cls(single_angles=singles, ranges=ranges)

    @classmethod
    def from_ar_headers(cls, headers: list[str]) -> LagConfig:
        """从 Excel 列头自动解析 AR 角度需求。"""
        singles, ranges = extract_angles_from_headers(headers, param_prefix="ar")
        return cls(single_angles=singles, ranges=ranges)

    @classmethod
    def from_rhcp_headers(cls, headers: list[str]) -> LagConfig:
        """从 Excel 列头自动解析 RHCP Gain 角度需求。"""
        singles, _ = extract_angles_from_headers(headers, param_prefix="rhcp")
        return cls(single_angles=singles)

    @classmethod
    def from_cpxpi_headers(cls, headers: list[str]) -> LagConfig:
        """从 Excel 列头自动解析 CP-XPI 角度需求。"""
        singles, _ = extract_angles_from_headers(headers, param_prefix="cpxpi")
        return cls(single_angles=singles)

    # --- 查询 ---

    @property
    def singles_sorted(self) -> list[float]:
        """去重排序后的单角度列表。"""
        return sorted(set(self.single_angles))

    @property
    def ranges_sorted(self) -> list[tuple[float, float]]:
        """排序后的范围列表。"""
        return sorted(set(self.ranges), key=lambda x: (x[0], x[1]))

    def is_empty(self) -> bool:
        return len(self.single_angles) == 0 and len(self.ranges) == 0

    # --- 修改 ---

    def add_single(self, angle: float):
        if angle not in self.single_angles:
            self.single_angles.append(angle)

    def add_range(self, start: float, end: float):
        key = (min(start, end), max(start, end))
        if key not in self.ranges:
            self.ranges.append(key)

    def remove_single(self, angle: float):
        self.single_angles = [a for a in self.single_angles if a != angle]

    def remove_range(self, start: float, end: float):
        key = (min(start, end), max(start, end))
        self.ranges = [r for r in self.ranges if r != key]

    def clear(self):
        self.single_angles.clear()
        self.ranges.clear()

    # --- 序列化 ---

    def to_dict(self) -> dict:
        return {
            "single_angles": self.singles_sorted,
            "ranges": [[lo, hi] for lo, hi in self.ranges_sorted],
        }

    @classmethod
    def from_dict(cls, d: dict) -> LagConfig:
        return cls(
            single_angles=d.get("single_angles", []),
            ranges=[(lo, hi) for lo, hi in d.get("ranges", [])],
        )

    def save_preset(self, path: Path):
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load_preset(cls, path: Path) -> LagConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# 预设
# ---------------------------------------------------------------------------

# 常用车企 LAG 预设
PRESET_AUTOMOTIVE = LagConfig(
    single_angles=[60, 70, 80, 90],
    ranges=[(0, 90), (60, 90)],
)
