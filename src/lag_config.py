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

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


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

# 匹配 "Theta=0-90 LAG" / "Theta=60-90 LAG" / "θ=0-90°"
_RE_LAG_RANGE = re.compile(
    r"(?:Theta|θ)\s*[=＝]\s*(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)",
    re.IGNORECASE,
)

# 匹配 "Theta=60" / "θ=70" / "Theta = 80"（但不能是范围）
_RE_LAG_SINGLE = re.compile(
    r"(?:Theta|θ)\s*[=＝]\s*(\d+\.?\d*)\s*$",
    re.IGNORECASE,
)

# 固定列名识别
_FIXED_COLUMNS = {
    "frequency": "frequency",
    "directivity": "directivity",
    "efficiency": "efficiency",
    "gain": "gain",
}


def _normalize_key(name: str) -> str:
    """将列头转成小写无空格键，用于固定列匹配。"""
    return re.sub(r"[^a-z%％()db]+", "", name.lower())


def is_frequency_column(header: str) -> bool:
    h = _normalize_key(header)
    return "frequency" in h or h in ("freq", "f", "f(mhz)", "freq(mhz)")


def is_directivity_column(header: str) -> bool:
    h = _normalize_key(header)
    return "directivity" in h or h in ("dir", "d(dbi)")


def is_efficiency_column(header: str) -> bool:
    """Efficiency(%) 或 Efficiency(dB)"""
    h = _normalize_key(header)
    return "efficiency" in h


def is_gain_column(header: str) -> bool:
    h = _normalize_key(header)
    return h.startswith("gain") or h in ("g(dbi)", "peakgain")


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

    single_angles: List[float] = field(default_factory=list)
    ranges: List[Tuple[float, float]] = field(default_factory=list)

    # --- 工厂方法 ---

    @classmethod
    def from_start_step(
        cls, start: float, end: float, step: float
    ) -> "LagConfig":
        """起始+步进快速生成单角度列表。

        Example:
            LagConfig.from_start_step(0, 90, 10)
            → single_angles = [0, 10, 20, ..., 90]
        """
        angles: List[float] = []
        a = start
        while a <= end + 1e-9:
            angles.append(round(a, 6))
            a += step
        return cls(single_angles=angles)

    @classmethod
    def from_template_headers(cls, headers: List[str]) -> "LagConfig":
        """从 Excel 列头自动解析 LAG 需求。

        识别模式：
          - ``Theta=60`` / ``θ=60``  → 单角度 60°
          - ``Theta=0-90 LAG``       → 范围 (0, 90)
          - ``Theta=60-90 LAG``      → 范围 (60, 90)

        注意：列头可能含换行符 ``\\n``、全角括号等，先做规范化。
        """
        singles: List[float] = []
        ranges: List[Tuple[float, float]] = []

        for raw in headers:
            h = normalize_header(raw)
            if not h:
                continue

            # 先检测范围（避免 "0-90" 中的 0 被单角度误匹配）
            rm = _RE_LAG_RANGE.search(h)
            if rm:
                lo, hi = float(rm.group(1)), float(rm.group(2))
                # 去重
                key = (min(lo, hi), max(lo, hi))
                if key not in ranges:
                    ranges.append(key)
                continue

            # 再检测单角度
            sm = _RE_LAG_SINGLE.search(h)
            if sm:
                val = float(sm.group(1))
                if val not in singles:
                    singles.append(val)

        return cls(single_angles=singles, ranges=ranges)

    # --- 查询 ---

    @property
    def singles_sorted(self) -> List[float]:
        """去重排序后的单角度列表。"""
        return sorted(set(self.single_angles))

    @property
    def ranges_sorted(self) -> List[Tuple[float, float]]:
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
    def from_dict(cls, d: dict) -> "LagConfig":
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
    def load_preset(cls, path: Path) -> "LagConfig":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# 预设
# ---------------------------------------------------------------------------

# 常用车企 LAG 预设
PRESET_AUTOMOTIVE = LagConfig(
    single_angles=[60, 70, 80, 90],
    ranges=[(0, 90), (60, 90)],
)
