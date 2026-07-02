"""统一数据源抽象接口"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class DataSource(ABC):
    """天线测试数据源抽象基类。

    支持两种实现:
      - MergedCsvSource:   EMQuest 合并 CSV 格式
      - FinalSummarySource: FinalSummary.xlsx 格式
    """

    @property
    @abstractmethod
    def frequencies(self) -> list[float]:
        """频点列表 (MHz)，按文件顺序。"""
        ...

    @property
    @abstractmethod
    def theta_angles(self) -> list[float]:
        """俯仰角列表 (°)。"""
        ...

    @property
    @abstractmethod
    def phi_angles(self) -> list[float]:
        """方位角列表 (°)。"""
        ...

    @abstractmethod
    def read_sections(self, freq_index: int) -> dict[str, np.ndarray | None]:
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
    def from_path(path: str) -> DataSource:
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


# ═══════════════════════════════════════════════════════════════
# 零拷贝步进重采样数据源
# ═══════════════════════════════════════════════════════════════

class ResampledDataSource(DataSource):
    """在内存中对已加载数据按步进重采样，避免重复 I/O。

    使用 stride 索引而非数据拷贝：theta/phi 角度取子集，
    read_sections 返回 view（无内存副本）。
    """

    def __init__(self, base: DataSource, theta_stride: int, phi_stride: int = 1):
        self._base = base
        self._theta_stride = max(1, int(theta_stride))
        self._phi_stride = max(1, int(phi_stride))
        self._cached: dict[int, dict[str, np.ndarray]] | None = None

    @property
    def frequencies(self) -> list[float]:
        return self._base.frequencies

    @property
    def theta_angles(self) -> list[float]:
        return self._base.theta_angles[::self._theta_stride]

    @property
    def phi_angles(self) -> list[float]:
        return self._base.phi_angles[::self._phi_stride]

    def read_sections(self, freq_index: int) -> dict[str, np.ndarray | None]:
        data = self._base.read_sections(freq_index)
        out = {}
        for key, arr in data.items():
            if arr is not None and arr.ndim == 2:
                # arr shape: (n_phi, n_theta)
                out[key] = arr[::self._phi_stride, ::self._theta_stride]
            else:
                out[key] = arr
        return out

    def close(self):
        self._cached = None
        self._base.close()
