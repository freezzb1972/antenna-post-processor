"""pipeline 单元测试 — 外推、任务收集、单频点处理、管线"""
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.datasource import DataSource
from src.excel_reader import ColumnInfo, SheetInfo
from src.lag_config import PRESET_AUTOMOTIVE, LagConfig
from src.pipeline import (
    _derive_sheet_name,
    _expand_template_sheets,
    _find_closest_freq,
    _process_one_frequency,
    extrapolate_theta,
    run_batch_pipeline,
    run_pipeline,
)

# ── Extrapolation ──────────────────────────────────────────────────

class TestExtrapolateTheta:
    def test_no_extrap_needed_theta_covers_180(self):
        theta = np.array([0.0, 30.0, 60.0, 90.0, 120.0, 150.0, 180.0])
        data = np.ones((2, 7))  # 2 phi, 7 theta
        new_theta, new_data = extrapolate_theta(theta, data, "linear")
        assert len(new_theta) == 7  # unchanged
        assert new_data.shape == (2, 7)

    def test_no_extrap_needed_near_180(self):
        theta = np.array([0.0, 45.0, 90.0, 135.0, 179.0])
        data = np.ones((2, 5))
        new_theta, new_data = extrapolate_theta(theta, data, "linear")
        assert len(new_theta) == 5  # 179 >= 179, no extrap needed

    def test_linear_extrap(self):
        theta = np.array([0.0, 30.0, 60.0, 90.0])
        data = np.array([
            [-5.0, -4.0, -3.0, -2.0],   # phi=0
            [-6.0, -5.0, -4.0, -3.0],   # phi=180
        ])
        new_theta, new_data = extrapolate_theta(theta, data, "linear")
        assert len(new_theta) > 4  # extended
        assert new_data.shape[1] == len(new_theta)
        assert new_theta[-1] >= 179.0

    def test_constant_extrap(self):
        theta = np.array([0.0, 30.0, 60.0, 90.0])
        data = np.array([[-5.0, -4.0, -3.0, -2.0]])
        new_theta, new_data = extrapolate_theta(theta, data, "constant")
        assert new_data.shape[1] > 4
        # Values beyond original should equal tail average
        assert np.allclose(new_data[0, 4:], np.mean(data[0, -10:]), atol=2.0)

    def test_mirror_extrap(self):
        theta = np.array([0.0, 30.0, 60.0, 90.0])
        data = np.array([[-5.0, -4.0, -3.0, -2.0]])
        new_theta, new_data = extrapolate_theta(theta, data, "mirror")
        assert new_data.shape[1] > 4

    def test_preserves_original_data(self):
        theta = np.array([0.0, 30.0, 60.0, 90.0])
        data = np.array([[-5.0, -4.0, -3.0, -2.0]])
        _, new_data = extrapolate_theta(theta, data, "linear")
        # First n columns should match original
        assert np.array_equal(new_data[:, :4], data)


# ── Frequency Matching ─────────────────────────────────────────────

class TestFindClosestFreq:
    def test_exact_match(self):
        idx = _find_closest_freq([699.0, 1700.0, 2600.0], 1700.0)
        assert idx == 1

    def test_near_match(self):
        idx = _find_closest_freq([699.0, 1700.0, 2600.0], 1702.0)
        assert idx == 1

    def test_outside_tolerance(self):
        idx = _find_closest_freq([699.0, 1700.0, 2600.0], 5000.0)
        assert idx is None

    def test_empty_list(self):
        assert _find_closest_freq([], 100.0) is None


# ── Sheet Name Derivation ──────────────────────────────────────────

class TestDeriveSheetName:
    def test_simple(self):
        assert _derive_sheet_name("5G1", "G2") == "5G2"

    def test_prefix_with_underscore(self):
        assert _derive_sheet_name("Antenna_G1", "G3") == "Antenna_G3"

    def test_different_case(self):
        assert _derive_sheet_name("5g1_data", "G2") == "5G2_data"

    def test_no_g_in_reference(self):
        result = _derive_sheet_name("Sheet1", "G2")
        assert result == "G2"  # fallback


# ── Sheet Expansion ────────────────────────────────────────────────

class TestExpandTemplateSheets:
    @staticmethod
    def _make_mock_ds(freqs=None):
        """构造最小 DataSource mock —— 实现 frequencies 和 theta_angles。"""
        class _MockDS:
            def __init__(self, f):
                self.frequencies = list(f) if f else [699.0, 1700.0]
                self.theta_angles = [0.0, 30.0, 60.0, 90.0]
        return _MockDS(freqs)

    def _make_si(self, name="5G1", freqs=None):
        freqs = freqs or [699.0, 1700.0]
        cols = [
            ColumnInfo("A", 1, "Frequency", "frequency", "frequency"),
            ColumnInfo("B", 2, "Gain (dBi)", "gain", "gain"),
        ]
        return SheetInfo(name, 1, 2, 3, cols, freqs)

    def test_no_expansion_needed(self):
        si = [self._make_si("5G1"), self._make_si("5G2")]
        ds_map = {"5G1": self._make_mock_ds(), "5G2": self._make_mock_ds()}
        result = _expand_template_sheets(si, ds_map)
        assert len(result) == 2

    def test_expands_when_fewer_sheets(self):
        si = [self._make_si("5G1")]
        ds_map = {"5G1": self._make_mock_ds(), "5G2": self._make_mock_ds()}
        result = _expand_template_sheets(si, ds_map)
        assert len(result) == 2
        assert result[1].name == "5G2"

    def test_use_raw_name_mode(self):
        si = [self._make_si("5G1")]
        ds_map = {"file_5G2_merged": self._make_mock_ds()}
        result = _expand_template_sheets(si, ds_map, use_raw_name=True)
        assert len(result) == 1
        assert "5G2" in result[0].name or "file" in result[0].name


# ── Single Frequency Processing ────────────────────────────────────

class TestProcessOneFrequency:
    @staticmethod
    def _make_raw(theta_lm=None, phi_lm=None, theta_phase=None, phi_phase=None):
        """构建合成 raw data dict。"""
        if theta_lm is None:
            theta_lm = np.ones((36, 19)) * -5.0  # 36 phi × 19 theta (0-180)
        if phi_lm is None:
            phi_lm = np.ones((36, 19)) * -8.0
        return {
            "theta_logmag": theta_lm,
            "phi_logmag": phi_lm,
            "theta_phase": theta_phase,
            "phi_phase": phi_phase,
        }

    def test_basic_output_keys(self):
        raw = self._make_raw()
        theta = np.linspace(0, 180, 19)
        lag = LagConfig.from_start_step(0, 90, 10)  # creates singles 0,10,...,90

        row = _process_one_frequency(raw, 699.0, theta, lag, needed_params={"gain"})
        assert row["frequency"] == 699.0
        assert "gain" in row

    def test_gain_is_float(self):
        raw = self._make_raw()
        theta = np.linspace(0, 180, 19)
        lag = LagConfig()

        row = _process_one_frequency(raw, 699.0, theta, lag, needed_params={"gain"})
        assert isinstance(row["gain"], float)

    def test_directivity_when_requested(self):
        raw = self._make_raw()
        theta = np.linspace(0, 180, 19)
        lag = LagConfig()

        row = _process_one_frequency(raw, 699.0, theta, lag, needed_params={"directivity"})
        assert "directivity" in row
        assert isinstance(row["directivity"], float)

    def test_efficiency_when_requested(self):
        raw = self._make_raw()
        theta = np.linspace(0, 180, 19)
        lag = LagConfig()

        row = _process_one_frequency(raw, 699.0, theta, lag, needed_params={"efficiency_pct"})
        assert "efficiency_pct" in row

    def test_trp_when_requested(self):
        raw = self._make_raw()
        theta = np.linspace(0, 180, 19)
        lag = LagConfig()

        row = _process_one_frequency(raw, 699.0, theta, lag, needed_params={"trp"})
        assert "trp" in row

    def test_lag_singles(self):
        raw = self._make_raw()
        theta = np.linspace(0, 180, 19)
        lag = LagConfig.from_start_step(0, 90, 30)  # 0, 30, 60, 90

        row = _process_one_frequency(raw, 699.0, theta, lag)
        assert "lag_single_0" in row
        assert "lag_single_30" in row
        assert "lag_single_60" in row
        assert "lag_single_90" in row

    def test_lag_ranges(self):
        raw = self._make_raw()
        theta = np.linspace(0, 180, 19)
        lag = LagConfig()
        lag.add_range(0, 70)

        row = _process_one_frequency(raw, 699.0, theta, lag)
        assert "lag_range_0_70" in row

    def test_ar_with_phase_data(self):
        theta_lm = np.ones((36, 19)) * -5.0
        phi_lm = np.ones((36, 19)) * -8.0
        theta_ph = np.zeros((36, 19))
        phi_ph = np.zeros((36, 19))
        raw = self._make_raw(theta_lm, phi_lm, theta_ph, phi_ph)
        theta = np.linspace(0, 180, 19)
        lag = LagConfig()
        lag.add_single(30)

        row = _process_one_frequency(raw, 699.0, theta, lag)
        # AR should be computed since phase data exists
        assert "ar_single_30.0" in row or "axial_ratio" in row

    def test_no_ar_without_phase(self):
        raw = self._make_raw()  # no phase
        theta = np.linspace(0, 180, 19)
        lag = LagConfig()
        lag.add_single(30)

        row = _process_one_frequency(raw, 699.0, theta, lag)
        # AR single should NOT be present without phase data
        assert "ar_single_30.0" not in row

    def test_extrapolation_triggers(self):
        """当 theta 不到 175° 且 do_extrapolate=True 时外推。"""
        raw = self._make_raw()
        theta = np.linspace(0, 90, 10)  # only to 90°
        lag = LagConfig()

        row = _process_one_frequency(raw, 699.0, theta, lag, theta_extrap_method="linear")
        assert "gain" in row

    def test_compute_only_skips_graphics(self):
        raw = self._make_raw()
        theta = np.linspace(0, 180, 19)
        lag = LagConfig()

        row = _process_one_frequency(raw, 699.0, theta, lag, compute_only=True)
        assert "_images" not in row  # no graphics

    def test_rhcp_computed_with_phase(self):
        theta_lm = np.ones((36, 19)) * -5.0
        phi_lm = np.ones((36, 19)) * -8.0
        theta_ph = np.zeros((36, 19))
        phi_ph = np.zeros((36, 19))
        raw = self._make_raw(theta_lm, phi_lm, theta_ph, phi_ph)
        theta = np.linspace(0, 180, 19)
        lag = LagConfig()
        lag.add_single(0)

        row = _process_one_frequency(raw, 699.0, theta, lag)
        # RHCP/LHCP should be computed when phase data exists
        assert "rhcp_single_0" in row

    def test_result_contains_raw_data(self):
        raw = self._make_raw()
        theta = np.linspace(0, 180, 19)
        lag = LagConfig()

        row = _process_one_frequency(raw, 699.0, theta, lag)
        assert "_raw_data" in row
        assert "_theta_angles" in row
        assert "_phi_angles" in row

    def test_round_to_6_decimals(self):
        raw = self._make_raw()
        theta = np.linspace(0, 180, 19)
        lag = LagConfig()

        row = _process_one_frequency(raw, 699.0, theta, lag, needed_params={"gain"})
        # All values should be rounded to 6 decimal places
        for val in row.values():
            if isinstance(val, float) and not np.isnan(val):
                # round(x, 6) should not change it again
                assert round(val, 6) == val, f"value {val} not rounded to 6 decimals"


# ── Pipeline (integration with real data) ──────────────────────────

class TestRunPipeline:
    def test_run_with_real_data(self):
        data_path = "data/5G1_merged.csv"
        tpl_path = "data/template_5G1.xlsx"
        if not Path(data_path).exists() or not Path(tpl_path).exists():
            pytest.skip("Test data not available")

        out = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        out.close()

        try:
            from src.datasource import DataSource
            ds = DataSource.from_path(data_path)
            result = run_pipeline(
                datasource=ds,
                template_path=tpl_path,
                output_path=out.name,
                lag_config_override=PRESET_AUTOMOTIVE,
            )
            assert len(result) > 0
            total_rows = sum(len(v) for v in result.values())
            assert total_rows > 0

            # Verify output file exists and is non-empty
            assert Path(out.name).exists()
            assert Path(out.name).stat().st_size > 100
        finally:
            if os.path.exists(out.name):
                os.unlink(out.name)

    def test_compute_only_mode(self):
        data_path = "data/5G1_merged.csv"
        tpl_path = "data/template_5G1.xlsx"
        if not Path(data_path).exists() or not Path(tpl_path).exists():
            pytest.skip("Test data not available")

        ds = DataSource.from_path(data_path)
        result = run_pipeline(
            datasource=ds,
            template_path=tpl_path,
            output_path="",
            compute_only=True,
            lag_config_override=PRESET_AUTOMOTIVE,
        )
        assert len(result) > 0
        # Result should contain all computed fields
        first_row = list(result.values())[0][0]
        assert "frequency" in first_row

    def test_batch_pipeline_backward_compat(self):
        data_path = "data/5G1_merged.csv"
        tpl_path = "data/template_5G1.xlsx"
        if not Path(data_path).exists() or not Path(tpl_path).exists():
            pytest.skip("Test data not available")

        out = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        out.close()

        try:
            result = run_batch_pipeline(
                csv_path=data_path,
                template_path=tpl_path,
                output_path=out.name,
                lag_config_override=PRESET_AUTOMOTIVE,
            )
            assert len(result) > 0
        finally:
            if os.path.exists(out.name):
                os.unlink(out.name)

    def test_mutual_exclusion_error(self):
        """datasource 和 datasource_map 不能同时提供。"""
        with pytest.raises(ValueError, match="互斥"):
            run_pipeline(datasource=object(), datasource_map={}, template_path="x")

    def test_missing_both_error(self):
        """必须提供 datasource 或 datasource_map。"""
        with pytest.raises(ValueError, match="必须提供"):
            run_pipeline(template_path="x")
