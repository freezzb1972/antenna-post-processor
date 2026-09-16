"""DataSource 接口一致性 — 包装类必须代理全部接口成员。

存在的理由: GUI「多步进计算」经 src/worker.py:280 构造 ResampledDataSource
作为 task_ds 传进 pipeline。pipeline 会读它的 source_name / detection_notes ——
若包装类漏掉代理, 多步进功能会在运行中 AttributeError。

这条路径此前**没有任何测试覆盖**: test_e2e_features 的 4 处 from_path 全部指向
merged.csv (不走 ResampledDataSource), 其余 GUI 测试用的是不存在的假路径。
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.datasource import (  # noqa: E402
    DataSource,
    ResampledDataSource,
    auto_read_workers,
)
from tests.test_finalsummary_layouts import build  # noqa: E402

# pipeline 依赖的 DataSource 接口成员 —— 新增成员时必须同步所有包装类
INTERFACE_MEMBERS = ("source_name", "detection_notes", "theta_angles", "phi_angles",
                     "frequencies")


def _all_datasource_classes():
    from src.finalsummary_reader import FinalSummarySource
    from src.json_reader import JsonDataSource
    from src.parser import MergedCSVParser
    return [FinalSummarySource, MergedCSVParser, JsonDataSource, ResampledDataSource]


@pytest.mark.parametrize("cls", _all_datasource_classes(),
                         ids=lambda c: c.__name__)
def test_every_datasource_exposes_pipeline_interface(cls):
    """所有数据源类都必须提供 pipeline 会用到的成员 (含包装类)。"""
    missing = [m for m in INTERFACE_MEMBERS if not hasattr(cls, m)]
    assert not missing, f"{cls.__name__} 缺少接口成员: {missing}"


def test_resampled_proxies_interface_from_base():
    """ResampledDataSource 必须把 source_name / detection_notes 代理给被包装的数据源。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    try:
        # 表头缺一个格子 → 产生结构告警, 用于验证告警也透传
        build(tmp.name, n_phi=3, n_theta=3, header_gap_at=1)
        base = DataSource.from_path(tmp.name)
        rs = ResampledDataSource(base, theta_stride=2, phi_stride=2)
        try:
            assert base.source_name == os.path.basename(tmp.name)
            assert base.detection_notes, "前提不成立: 该布局应产生探测告警"

            assert rs.source_name == base.source_name, "source_name 未代理"
            assert rs.detection_notes == base.detection_notes, "detection_notes 未代理"
            assert len(rs.theta_angles) < len(base.theta_angles), "theta 未被抽稀"
            assert len(rs.phi_angles) < len(base.phi_angles), "phi 未被抽稀"
        finally:
            rs.close()
    finally:
        os.unlink(tmp.name)


def test_pipeline_runs_through_resampled_datasource():
    """GUI 多步进路径: pipeline 读 ResampledDataSource 不得抛 AttributeError。"""
    from src.pipeline import run_pipeline

    root = Path(__file__).resolve().parent.parent
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    out = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    out.close()
    try:
        build(tmp.name, n_phi=4, n_theta=4)
        base = DataSource.from_path(tmp.name)
        rs = ResampledDataSource(base, theta_stride=2, phi_stride=2)
        try:
            logs = []
            run_pipeline(datasource=rs,
                         template_path=str(root / "data" / "template_AFN_L1.xlsx"),
                         output_path=out.name,
                         log_callback=logs.append)
            # 告警出口按数据源提示一次 —— 走通即证明 source_name/detection_notes 可用
            assert isinstance(logs, list)
        finally:
            rs.close()
    finally:
        os.unlink(tmp.name)
        os.unlink(out.name)


# ── 并行读取 (xlsx 解析受 GIL 限制 → 进程) ──────────────────────

def test_auto_read_workers_is_runtime_and_capped():
    """进程数按本机核数运行时决定, 且必须封顶 —— 实测收益在 8 之后回落。"""
    assert auto_read_workers(0) == 1, "无任务时不应起进程"
    assert auto_read_workers(3) == 1, "任务太少时进程池启动开销(~1.6s)盖过收益"
    w = auto_read_workers(1000)
    assert 2 <= w <= 8, f"大任务量应落在 [2,8], 实得 {w}"
    cpu = os.cpu_count() or 1
    if cpu > 2:
        assert w <= cpu - 1, "应给 GUI 主线程留一核"


def test_read_many_parallel_matches_serial():
    """并行读取必须与串行读取逐元素一致 —— 这是接进核心读数路径的前提。"""
    import numpy as np

    from src.finalsummary_reader import FinalSummarySource
    from tests.test_finalsummary_reader import _make_finalsummary_xlsx

    path = _make_finalsummary_xlsx(freqs=[699.0, 700.0, 701.0, 702.0])
    idxs = [0, 1, 2, 3]
    keys = ("theta_logmag", "theta_phase", "phi_logmag", "phi_phase")
    try:
        a = FinalSummarySource(path)
        try:
            ser = a.read_many(idxs, workers=1)
        finally:
            a.close()

        b = FinalSummarySource(path)
        seen = []
        try:
            par = b.read_many(idxs, workers=4, on_result=lambda i, s: seen.append(i))
        finally:
            b.close()

        assert sorted(seen) == idxs, f"on_result 未覆盖全部频点: {sorted(seen)}"
        for i in idxs:
            for k in keys:
                x, y = ser[i][k], par[i][k]
                assert (x is None) == (y is None), f"#{i}.{k} None 性不同"
                if x is not None:
                    assert np.array_equal(x, y, equal_nan=True), f"#{i}.{k} 数值不一致"
    finally:
        os.unlink(path)


def test_read_many_serial_default_covers_all():
    """默认 (workers=None) 在任务数不足阈值时走串行, 也必须覆盖全部频点。"""
    from src.finalsummary_reader import FinalSummarySource
    from tests.test_finalsummary_reader import _make_finalsummary_xlsx

    path = _make_finalsummary_xlsx(freqs=[699.0, 700.0])
    try:
        ds = FinalSummarySource(path)
        try:
            seen = []
            out = ds.read_many([0, 1], on_result=lambda i, s: seen.append(i))
            assert sorted(out) == [0, 1]
            assert sorted(seen) == [0, 1]
        finally:
            ds.close()
    finally:
        os.unlink(path)
