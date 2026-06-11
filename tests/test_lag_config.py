"""
LAG 配置模型测试
=================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lag_config import (
    LagConfig,
    normalize_header,
    PRESET_AUTOMOTIVE,
)


class TestNormalizeHeader:
    def test_basic(self):
        assert normalize_header("Theta=60") == "Theta=60"

    def test_newline(self):
        assert normalize_header("Theta=0-90\nLAG") == "Theta=0-90 LAG"

    def test_fullwidth_parens(self):
        assert normalize_header("Efficiency（%）") == "Efficiency(%)"


class TestLagConfigFromTemplateHeaders:
    def test_single_angles(self):
        cfg = LagConfig.from_template_headers(["Theta=60", "Theta=70", "Theta=80", "Theta=90"])
        assert cfg.singles_sorted == [60.0, 70.0, 80.0, 90.0]
        assert cfg.ranges_sorted == []

    def test_ranges(self):
        cfg = LagConfig.from_template_headers([
            "Theta=0-90 LAG", "Theta=60-90 LAG"
        ])
        assert (0.0, 90.0) in cfg.ranges_sorted
        assert (60.0, 90.0) in cfg.ranges_sorted

    def test_mixed(self):
        cfg = LagConfig.from_template_headers([
            "Theta=60", "Theta=70", "Theta=0-90 LAG", "Theta=60-90 LAG"
        ])
        assert 60.0 in cfg.singles_sorted
        assert 70.0 in cfg.singles_sorted
        assert (0.0, 90.0) in cfg.ranges_sorted
        assert (60.0, 90.0) in cfg.ranges_sorted

    def test_theta_symbol(self):
        cfg = LagConfig.from_template_headers(["θ=60"])
        assert 60.0 in cfg.singles_sorted

    def test_empty(self):
        cfg = LagConfig.from_template_headers(["Frequency", "Directivity", "Gain"])
        assert cfg.is_empty()


class TestLagConfigFromStartStep:
    def test_0_90_10(self):
        cfg = LagConfig.from_start_step(0, 90, 10)
        assert cfg.singles_sorted == [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]

    def test_60_90_5(self):
        cfg = LagConfig.from_start_step(60, 90, 5)
        assert cfg.singles_sorted == [60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0]


class TestLagConfigModify:
    def test_add_remove(self):
        cfg = LagConfig()
        cfg.add_single(60)
        cfg.add_single(70)
        assert 60.0 in cfg.singles_sorted
        cfg.remove_single(60)
        assert 60.0 not in cfg.singles_sorted

    def test_add_range(self):
        cfg = LagConfig()
        cfg.add_range(0, 90)
        cfg.add_range(60, 90)
        assert (0.0, 90.0) in cfg.ranges_sorted
        assert (60.0, 90.0) in cfg.ranges_sorted

    def test_clear(self):
        cfg = LagConfig(single_angles=[60, 70], ranges=[(0, 90)])
        cfg.clear()
        assert cfg.is_empty()


class TestLagConfigSerialize:
    def test_roundtrip(self):
        cfg = LagConfig(single_angles=[60, 70, 80], ranges=[(0, 90)])
        d = cfg.to_dict()
        cfg2 = LagConfig.from_dict(d)
        assert cfg2.singles_sorted == [60.0, 70.0, 80.0]
        assert cfg2.ranges_sorted == [(0.0, 90.0)]


class TestPresetAutomotive:
    def test_default(self):
        assert 60.0 in PRESET_AUTOMOTIVE.singles_sorted
        assert 90.0 in PRESET_AUTOMOTIVE.singles_sorted
        assert (0.0, 90.0) in PRESET_AUTOMOTIVE.ranges_sorted
        assert (60.0, 90.0) in PRESET_AUTOMOTIVE.ranges_sorted
