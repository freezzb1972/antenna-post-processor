"""统一数据源抽象接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

import numpy as np


class PipelineCancelled(Exception):
    """解析/计算被用户取消。

    **必须与普通异常区分**: worker 捕获它时应报告「已取消」而非「失败」。

    为什么需要异常而不是像 pipeline 那样 `if cancel_callback(): break`:
    长耗时的解析(如 158MB merged.csv 的首次索引, 单次 5-7s)若中途 break,
    frequencies 会返回**不完整的频点表** —— 后续照样能算出一份"看起来合理
    但是错的"结果, 比直接报错更危险。
    """


class DataSource(ABC):
    """天线测试数据源抽象基类。

    支持两种实现:
      - MergedCsvSource:   EMQuest 合并 CSV 格式
      - FinalSummarySource: FinalSummary.xlsx 格式
    """

    # 取消回调 —— 由 pipeline 在开始处理前注入 (见 set_cancel_callback)。
    # 长耗时解析在循环里周期性检查它, 以便用户点「停止」能及时生效。
    _cancel_callback: "Callable[[], bool] | None" = None

    def set_cancel_callback(self, cb: "Callable[[], bool] | None") -> None:
        """注入取消回调。返回 True 表示应中止。

        由 pipeline 调用, 使「首次解析数据源」这一步也可被中断 ——
        此前 pipeline 的 cancel_callback 只按文件/频点粒度检查, 覆盖不到它。
        """
        self._cancel_callback = cb

    def _check_cancelled(self) -> None:
        """若已取消则抛 PipelineCancelled。供子类在长循环里调用。"""
        cb = self._cancel_callback
        if cb is not None and cb():
            raise PipelineCancelled()

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
