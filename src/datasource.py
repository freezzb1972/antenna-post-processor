"""统一数据源抽象接口"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import numpy as np


class DataSource(ABC):
    """天线测试数据源抽象基类。

    支持两种实现:
      - MergedCsvSource:   EMQuest 合并 CSV 格式
      - FinalSummarySource: FinalSummary.xlsx 格式
    """

    @property
    @abstractmethod
    def frequencies(self) -> List[float]:
        """频点列表 (MHz)，按文件顺序。"""
        ...

    @property
    @abstractmethod
    def theta_angles(self) -> List[float]:
        """俯仰角列表 (°)。"""
        ...

    @property
    @abstractmethod
    def phi_angles(self) -> List[float]:
        """方位角列表 (°)。"""
        ...

    @abstractmethod
    def read_sections(self, freq_index: int) -> Dict[str, Optional[np.ndarray]]:
        """读取单个频点的全部 section 数据。

        Args:
            freq_index: 0-based 频点索引。

        Returns:
            {
                'theta_logmag': ndarray (n_phi, n_theta),  # 必有
                'theta_phase':  ndarray | None,              # None = 无相位数据
                'phi_logmag':   ndarray (n_phi, n_theta),  # 必有
                'phi_phase':    ndarray | None,              # None = 无相位数据
            }
        """
        ...

    def close(self):
        """释放资源（子类可覆盖）。"""
        pass

    @staticmethod
    def from_path(path: str) -> "DataSource":
        """根据文件扩展名自动创建合适的 DataSource。

        - .xlsx / .xls → FinalSummarySource
        - .csv           → MergedCSVParser
        - .json          → JsonDataSource (EMQuest 导出)
        """
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in ("xlsx", "xls"):
            from .finalsummary_reader import FinalSummarySource
            return FinalSummarySource(path)
        elif ext == "json":
            from .json_reader import JsonDataSource
            return JsonDataSource(path)
        else:
            from .parser import MergedCSVParser
            return MergedCSVParser(path)
