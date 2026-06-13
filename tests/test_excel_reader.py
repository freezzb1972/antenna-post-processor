"""
Excel 模板读取测试
===================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.excel_reader import read_template


TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "data" / "template_5G1.xlsx"
if not TEMPLATE_PATH.exists():
    TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "data" / "20260601乐来_SVW 5G1.xlsx"


class TestReadTemplate:
    def test_detect_sheets(self):
        sheets = read_template(str(TEMPLATE_PATH))
        sheet_names = [s.name for s in sheets]
        assert "5G1" in sheet_names
        assert "5G2" in sheet_names
        assert "5G3" in sheet_names
        assert "5G4" in sheet_names
        assert len(sheets) == 4

    def test_5g1_frequencies(self):
        sheets = read_template(str(TEMPLATE_PATH))
        s5g1 = next(s for s in sheets if s.name == "5G1")
        assert len(s5g1.frequencies) >= 100  # full band
        assert s5g1.frequencies[0] == 690.0

    def test_5g3_frequencies(self):
        sheets = read_template(str(TEMPLATE_PATH))
        s5g3 = next(s for s in sheets if s.name == "5G3")
        assert len(s5g3.frequencies) >= 70  # mid+high band
        # 5G3 starts from 1710 MHz
        assert s5g3.frequencies[0] >= 1700

    def test_lag_detection(self):
        sheets = read_template(str(TEMPLATE_PATH))
        for s in sheets:
            assert 60.0 in s.lag_config.singles_sorted
            assert 90.0 in s.lag_config.singles_sorted
            assert (0.0, 90.0) in s.lag_config.ranges_sorted
            assert (60.0, 90.0) in s.lag_config.ranges_sorted

    def test_column_types(self):
        sheets = read_template(str(TEMPLATE_PATH))
        s5g1 = next(s for s in sheets if s.name == "5G1")
        has_freq = any(c.col_type == "frequency" for c in s5g1.columns)
        has_dir = any(c.col_type == "directivity" for c in s5g1.columns)
        has_gain = any(c.col_type == "gain" for c in s5g1.columns)
        assert has_freq
        assert has_dir
        assert has_gain
