"""
文件条目数据模型
================
纯数据类，无 GUI 依赖。每个 FileEntry 代表一个数据源文件及其处理配置。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileEntry:
    """单个数据源文件的处理条目。

    Attributes:
        path: 数据文件绝对路径。
        test_mode: 测试模式 (0=无源天线, 1=有源发射 TRP, 2=有源接收 TIS)。
        matched_sheet: 自动匹配的工作表名称（空字符串表示未匹配）。
        label: 显示用的简短名称（默认使用文件名）。
    """

    path: str
    test_mode: int = 0
    matched_sheet: str = ""

    @property
    def name(self) -> str:
        """短文件名，用于 GUI 显示。"""
        return Path(self.path).name

    @property
    def stem(self) -> str:
        """无扩展名的文件名。"""
        return Path(self.path).stem

    @property
    def file_size_mb(self) -> float:
        """文件大小 (MB)，读取失败返回 0。"""
        try:
            return Path(self.path).stat().st_size / (1024 * 1024)
        except OSError:
            return 0.0

    @property
    def exists(self) -> bool:
        """文件是否存在。"""
        return Path(self.path).is_file()


MODE_NAMES = {
    0: "📡 无源天线",
    1: "📶 有源发射 TRP",
    2: "📻 有源接收 TIS",
}


def mode_name(mode: int) -> str:
    """返回测试模式的人类可读名称。"""
    return MODE_NAMES.get(mode, f"未知({mode})")


def infer_mode_from_sheet(sheet_name: str) -> int:
    """根据工作表名称推断测试模式。

    返回 0(无源)/1(TRP)/2(TIS)。默认返回 0。
    """
    upper = sheet_name.upper()
    # TIS 关键词
    if any(k in upper for k in ["TIS", "NHPIS", "PIS"]):
        return 2
    # TRP 关键词
    if any(k in upper for k in ["TRP", "EIRP", "NHPRP", "PRP"]):
        return 1
    return 0


def infer_mode_from_headers(headers: list[str]) -> int:
    """根据列头列表推断测试模式。

    返回 0(无源)/1(TRP)/2(TIS)。默认返回 0。
    """
    header_str = " ".join(headers).upper()
    if any(k in header_str for k in ["TIS", "NHPIS", "PIS"]):
        return 2
    if any(k in header_str for k in ["TRP", "EIRP", "NHPRP", "PRP"]):
        return 1
    return 0
