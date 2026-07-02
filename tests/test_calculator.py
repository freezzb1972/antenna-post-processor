"""
计算引擎测试
=============
用 690 MHz 实测数据验证天线参数计算正确性。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest

from src.calculator import (
    compute_directivity,
    compute_efficiency,
    compute_lag_at_angles,
    compute_lag_range,
    compute_lag_ranges,
    compute_total_gain_linear,
)
from src.parser import MergedCSVParser

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def parser():
    return MergedCSVParser(
        str(Path(__file__).resolve().parent.parent / "data" / "5G1_merged.csv")
    )


@pytest.fixture(scope="module")
def data_690mhz(parser):
    """690 MHz 频点的 4 section 数据。"""
    return parser.read_all_sections_for_freq(0)


@pytest.fixture(scope="module")
def theta_arrays(parser):
    theta_deg = np.array(parser.theta_angles)
    theta_rad = np.deg2rad(theta_deg)
    return theta_deg, theta_rad


@pytest.fixture(scope="module")
def gain_data(data_690mhz):
    theta_lm = np.array(data_690mhz["theta_logmag"], dtype=np.float64)
    phi_lm = np.array(data_690mhz["phi_logmag"], dtype=np.float64)
    return compute_total_gain_linear(theta_lm, phi_lm)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPeakGain:
    def test_not_extreme(self, gain_data):
        gain_lin, peak_dbi = gain_data
        # 天线增益应在合理范围
        assert -20 < peak_dbi < 20
        # 峰值应出现在合理位置
        assert np.max(gain_lin) > 0

    def test_gain_shape(self, gain_data):
        gain_lin, _ = gain_data
        assert gain_lin.shape == (360, 111)  # phi × theta


class TestDirectivity:
    def test_reasonable_range(self, gain_data, theta_arrays):
        gain_lin, _ = gain_data
        _, theta_rad = theta_arrays
        d = compute_directivity(gain_lin, theta_rad)
        # 方向性应在合理范围
        assert 0 < d < 25


class TestEfficiency:
    def test_percentage_range(self, gain_data, theta_arrays):
        gain_lin, peak_dbi = gain_data
        _, theta_rad = theta_arrays
        d = compute_directivity(gain_lin, theta_rad)
        pct, db = compute_efficiency(peak_dbi, d)
        # 效率应在 0-100%
        assert 0 < pct <= 100
        # dB 效率应 ≤ 0
        assert db <= 0


class TestLAG:
    def test_single_lag_values(self, gain_data, theta_arrays):
        gain_lin, _ = gain_data
        theta_deg, _ = theta_arrays
        results = compute_lag_at_angles(gain_lin, theta_deg, [0, 60, 90])
        # LAG(0°) 应该较大（靠近主瓣）
        assert results[0.0] > -30
        # LAG(90°) 应该较小（远离主瓣）
        assert results[90.0] < 0

    def test_lag_range_monotonic(self, gain_data, theta_arrays):
        """LAG(0-60) 应大于 LAG(60-90)（主瓣能量更集中在低角度）"""
        gain_lin, _ = gain_data
        theta_deg, _ = theta_arrays
        lag_0_60 = compute_lag_range(gain_lin, theta_deg, 0, 60)
        lag_60_90 = compute_lag_range(gain_lin, theta_deg, 60, 90)
        assert lag_0_60 > lag_60_90

    def test_range_batch(self, gain_data, theta_arrays):
        gain_lin, _ = gain_data
        theta_deg, _ = theta_arrays
        results = compute_lag_ranges(gain_lin, theta_deg, [(0, 90), (60, 90)])
        assert (0.0, 90.0) in results
        assert (60.0, 90.0) in results
        # (0-90) 应大于 (60-90)
        assert results[(0.0, 90.0)] > results[(60.0, 90.0)]


class TestParserBasics:
    def test_frequencies(self, parser):
        freqs = parser.frequencies
        assert len(freqs) == 105
        assert freqs[0] == 690.0
        assert freqs[-1] == 5000.0

    def test_theta_angles(self, parser):
        theta = parser.theta_angles
        assert len(theta) == 111
        assert theta[0] == 0.0
        assert theta[-1] == 110.0

    def test_phi_angles(self, parser):
        phi = parser.phi_angles
        assert len(phi) == 360
        assert phi[0] == 0
        assert phi[-1] == 359
