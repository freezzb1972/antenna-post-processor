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

from src.datasource import DataSource, ResampledDataSource  # noqa: E402
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
