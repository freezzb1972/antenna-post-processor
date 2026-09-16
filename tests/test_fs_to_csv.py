"""FinalSummary → merged CSV 转换器测试。

存在的理由: 本模块此前**没有任何测试**。它的 phi 角度曾用 `range(n_phi)` 合成,
不是读文件里的真实值 —— 对 1° 栅格恰好正确, 对 2°/5°/10° 栅格写出的角度轴
完全错误, 而行数与数值都正常、不报错。

布局生成器 `build` 用的就是 10° 栅格, 因此用它即可直接复现该缺陷。
"""

import csv
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fs_to_csv import convert_fs_to_csv  # noqa: E402
from tests.test_finalsummary_layouts import build  # noqa: E402


def _parse_csv_angles(path):
    """取 CSV 中 Theta Log Magnitude 段的 (theta 角度, phi 角度)。"""
    theta, phi = [], []
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    for i, row in enumerate(rows):
        if len(row) > 3 and row[2].strip() == "Theta Angle  (deg)":
            theta = [float(x) for x in row[3:] if x.strip()]
            for r2 in rows[i + 2:]:
                # 下一个频点块以 "频率" 打头 → 本段结束
                if len(r2) < 3 or r2[0].strip() or r2[1].strip():
                    break
                if r2[2].strip():
                    phi.append(float(r2[2]))
            break
    return theta, phi


def test_angles_are_real_not_synthesized():
    """非 1° 栅格文件的 theta/phi 角度必须写成真实值, 不能合成等差数列。

    回归: 旧实现 `phi_vals = [float(i) for i in range(n_phi)]` —— 10° 栅格会写出
    0,1,2,...,5 而非 0,10,20,...,50。行数和响应值都正常, 只有角度轴是错的。
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    out = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    out.close()
    try:
        build(tmp.name, n_phi=6, n_theta=5)          # 栅格 = 10°
        convert_fs_to_csv(tmp.name, out.name)
        theta, phi = _parse_csv_angles(out.name)
        assert theta == [0.0, 10.0, 20.0, 30.0, 40.0], f"theta 角度错误: {theta}"
        assert phi == [0.0, 10.0, 20.0, 30.0, 40.0, 50.0], f"phi 角度错误: {phi}"
    finally:
        os.unlink(tmp.name)
        os.unlink(out.name)


def test_csv_roundtrips_through_mergesvparser():
    """转换产物必须能被 MergedCSVParser 读回, 且四个段的数据与源文件一致。"""
    import numpy as np

    from src.datasource import DataSource
    from src.finalsummary_reader import FinalSummarySource

    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    out = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    out.close()
    try:
        build(tmp.name, n_phi=4, n_theta=4)
        convert_fs_to_csv(tmp.name, out.name)

        src = FinalSummarySource(tmp.name)
        csv_ds = DataSource.from_path(out.name)
        try:
            assert src.frequencies == csv_ds.frequencies, "频点不一致"
            s_sec, c_sec = src.read_sections(0), csv_ds.read_sections(0)
            assert np.allclose(s_sec["theta_logmag"], c_sec["theta_logmag"], equal_nan=True), \
                "theta 幅度经 CSV 往返后不一致"
            assert np.allclose(s_sec["phi_logmag"], c_sec["phi_logmag"], equal_nan=True), \
                "phi 幅度经 CSV 往返后不一致"
            # CSV 路径的 phi 轴必须与源文件一致 (< 360 的部分)
            assert [p for p in src.phi_angles if p < 360.0] == csv_ds.phi_angles, \
                "phi 角度经 CSV 往返后不一致"
        finally:
            src.close()
            csv_ds.close()
    finally:
        os.unlink(tmp.name)
        os.unlink(out.name)
