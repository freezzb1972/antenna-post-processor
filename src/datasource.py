"""统一数据源抽象接口"""

from __future__ import annotations

import os
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


# 并行读取的进程数上限与最小任务数 —— 依据实测, 见 auto_read_workers()
_READ_WORKERS_CAP = 8
_READ_WORKERS_MIN_TASKS = 4


def auto_read_workers(n_tasks: int) -> int:
    """按**本机**能力决定并行读取的进程数 (运行时计算, 不写死常数)。

    实测 (16 核 / 267MB 30-sheet xlsx / fork 启动):
        W=1 25.4s(1.00x) | W=2 1.67x | W=3 2.00x | W=4 2.58x
        W=6 2.80x        | W=8 3.07x(峰值) | W=12 2.89x(回落)

    故:
      - 主控 = CPU 核数 - 1 (留一核给 GUI 主线程, 与 worker.py 的多步进并行同策略)
      - **封顶 8** —— 再多则各 worker 争抢同一文件的读取, 收益反而回落
      - 任务太少时进程池启动开销 (实测 ~1.6s) 盖过收益 → 返回 1, 调用方走串行
    """
    if n_tasks < _READ_WORKERS_MIN_TASKS:
        return 1
    cpu = os.cpu_count() or 1
    return max(1, min(cpu - 1, _READ_WORKERS_CAP, n_tasks))


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

    def read_many(self, freq_indices: list[int], workers: int | None = None,
                  on_result=None, cancel_callback=None) -> dict[int, dict]:
        """批量读取多个频点。

        默认**串行** —— CSV/JSON 解析开销小, 并行不划算。解析昂贵的子类可覆写
        (见 FinalSummarySource: xlsx 的 XML 解析是纯 Python, 受 GIL 限制, 必须用
        进程; 线程实测反而慢 1.1~1.4x)。

        Args:
            freq_indices:    频点索引列表
            workers:         并行进程数; None = auto_read_workers(len(freq_indices))
            on_result:       (idx, sections) → None, 每完成一个频点调用一次 (进度用)
            cancel_callback: () → bool, 返回 True 时停止读取

        Returns:
            {freq_index: sections}  (取消时可能少于请求数)
        """
        out: dict[int, dict] = {}
        for i in freq_indices:
            if cancel_callback is not None and cancel_callback():
                break
            sec = self.read_sections(i)
            out[i] = sec
            if on_result is not None:
                on_result(i, sec)
        return out

    def close(self):
        """释放资源（子类可覆盖）。"""
        pass

    @property
    def detection_notes(self) -> list[str]:
        """结构/格式探测中的异常提示; 空列表表示一切正常。

        只产出数据, 不直接打日志 —— 由上层 (pipeline → GUI) 决定是否提示。
        """
        return []

    @property
    def source_name(self) -> str:
        """数据来源的可读名称 (通常是文件名); 未知时返回空串。

        供提示信息标识问题出在哪个文件 —— 批处理下没有它无法定位。
        """
        return ""

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

    def read_many(self, freq_indices, workers=None, on_result=None,
                  cancel_callback=None) -> dict[int, dict]:
        """委托被包装的数据源并行读取原文, 再抽稀 —— 保住并行收益。"""
        raw = self._base.read_many(freq_indices, workers=workers,
                                   on_result=None, cancel_callback=cancel_callback)
        out = {}
        for i, data in raw.items():
            sec = {}
            for key, arr in data.items():
                sec[key] = (arr[::self._phi_stride, ::self._theta_stride]
                            if arr is not None and arr.ndim == 2 else arr)
            out[i] = sec
            if on_result is not None:
                on_result(i, sec)
        return out

    @property
    def detection_notes(self) -> list[str]:
        return self._base.detection_notes

    @property
    def source_name(self) -> str:
        return self._base.source_name

    def close(self):
        self._cached = None
        self._base.close()
