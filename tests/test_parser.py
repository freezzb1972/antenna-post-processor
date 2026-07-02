"""MergedCSVParser 单元测试 — 字节偏移索引 + 流式读取"""
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.parser import MergedCSVParser

# ── 合成测试 CSV ──────────────────────────────────────────────────

def _make_mini_csv(content_lines: list, encoding: str = "utf-8") -> str:
    """创建临时 CSV 文件用于测试。"""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding=encoding)
    tmp.write("\n".join(content_lines))
    tmp.close()
    return tmp.name


# ── Line-level Parsing ────────────────────────────────────────────

class TestDetectSectionHeader:
    def test_theta_logmag(self):
        assert MergedCSVParser._detect_section_header("Theta Log Magnitude,some data") == "Theta Log Magnitude"

    def test_theta_phase(self):
        assert MergedCSVParser._detect_section_header("Theta Phase,1,2,3") == "Theta Phase"

    def test_phi_logmag(self):
        assert MergedCSVParser._detect_section_header("Phi Log Magnitude,data") == "Phi Log Magnitude"

    def test_phi_phase(self):
        assert MergedCSVParser._detect_section_header("Phi Phase,x,y,z") == "Phi Phase"

    def test_not_a_header(self):
        assert MergedCSVParser._detect_section_header("Some random text") is None

    def test_partial_match_no_comma(self):
        # "Theta Log Magnitude" 后面必须有逗号
        assert MergedCSVParser._detect_section_header("Theta Log Magnitude") is None


class TestIsFreqBlockStart:
    def test_valid_block(self):
        assert MergedCSVParser._is_freq_block_start(",699.000,Theta Angle  (deg),0,1,2")

    def test_no_leading_comma(self):
        assert not MergedCSVParser._is_freq_block_start("699.000,Theta Angle")

    def test_no_theta_angle(self):
        assert not MergedCSVParser._is_freq_block_start(",699.000,Some Text")

    def test_non_numeric_freq(self):
        assert not MergedCSVParser._is_freq_block_start(",abc,Theta Angle")


class TestParseFreqFromLine:
    def test_extract_freq(self):
        assert MergedCSVParser._parse_freq_from_line(",699.000,Theta Angle") == 699.0

    def test_extract_freq_integer(self):
        assert MergedCSVParser._parse_freq_from_line(",3300,Theta Angle") == 3300.0

    def test_no_freq(self):
        assert MergedCSVParser._parse_freq_from_line("Theta Log Magnitude") is None


class TestParseThetaAngles:
    def test_extract_angles(self):
        angles = MergedCSVParser._parse_theta_angles(",699,Theta Angle  (deg),0,30,60,90")
        assert angles == [0.0, 30.0, 60.0, 90.0]

    def test_partial_numeric(self):
        angles = MergedCSVParser._parse_theta_angles(",699,Theta Angle  (deg),0.0,30.0,abc,60.0")
        assert angles == [0.0, 30.0, 60.0]


class TestParsePhiFromLine:
    def test_extract_phi(self):
        assert MergedCSVParser._parse_phi_from_line(",,0.0,val1,val2") == 0.0

    def test_extract_phi_mid(self):
        assert MergedCSVParser._parse_phi_from_line(",,180.0,val1,val2") == 180.0

    def test_short_line(self):
        assert MergedCSVParser._parse_phi_from_line("a,b") is None


class TestParsePhiDataLine:
    def test_parse_values(self):
        values = MergedCSVParser._parse_phi_data_line(",,0,-10.5,-9.3,-8.1", 3)
        assert values == [-10.5, -9.3, -8.1]

    def test_pad_short(self):
        values = MergedCSVParser._parse_phi_data_line(",,0,-10.5", 4)
        assert len(values) == 4
        assert values == [-10.5, 0.0, 0.0, 0.0]

    def test_truncate_long(self):
        values = MergedCSVParser._parse_phi_data_line(",,0,1,2,3,4,5", 3)
        assert len(values) == 3
        assert values == [1.0, 2.0, 3.0]


# ── Index Building + Block Reading ─────────────────────────────────

class TestIndexAndRead:
    def test_two_sections_one_freq(self):
        """合成一个包含 2 个 section、1 个频点、2 个 phi、3 个 theta 的 CSV。"""
        lines = [
            "Theta Log Magnitude,header",
            ",699.000,Theta Angle  (deg),0,30,60",
            ",,Phi,Resp,dB",
            ",,0.0,-5.0,-6.0,-7.0",
            ",,180.0,-8.0,-9.0,-10.0",
            "Theta Phase,header",
            ",699.000,Theta Angle  (deg),0,30,60",
            ",,Phi,Resp,deg",
            ",,0.0,10.0,20.0,30.0",
            ",,180.0,40.0,50.0,60.0",
        ]
        path = _make_mini_csv(lines)
        try:
            parser = MergedCSVParser(path)
            assert parser.num_frequencies == 1
            assert parser.frequencies == [699.0]
            assert parser.theta_angles == [0.0, 30.0, 60.0]
            assert parser.phi_angles == [0.0, 180.0]

            block = parser.read_section_block("Theta Log Magnitude", 0)
            assert len(block) == 2  # 2 phi rows
            assert len(block[0]) == 3  # 3 theta values
            assert block[0] == [-5.0, -6.0, -7.0]
            assert block[1] == [-8.0, -9.0, -10.0]

            parser.close()
        finally:
            os.unlink(path)

    def test_read_all_sections(self):
        lines = [
            "Theta Log Magnitude,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,dB",
            ",,0.0,-5.0,-6.0",
            "Theta Phase,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,deg",
            ",,0.0,10.0,20.0",
            "Phi Log Magnitude,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,dB",
            ",,0.0,-7.0,-8.0",
            "Phi Phase,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,deg",
            ",,0.0,30.0,40.0",
        ]
        path = _make_mini_csv(lines)
        try:
            parser = MergedCSVParser(path)
            result = parser.read_all_sections_for_freq(0)
            assert "theta_logmag" in result
            assert "theta_phase" in result
            assert "phi_logmag" in result
            assert "phi_phase" in result
            assert result["theta_logmag"][0] == [-5.0, -6.0]
            parser.close()
        finally:
            os.unlink(path)

    def test_read_sections_ndarray(self):
        """read_sections 返回 ndarray 格式。"""
        lines = [
            "Theta Log Magnitude,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,dB",
            ",,0.0,-5.0,-6.0",
            "Theta Phase,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,deg",
            ",,0.0,10.0,20.0",
            "Phi Log Magnitude,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,dB",
            ",,0.0,-7.0,-8.0",
            "Phi Phase,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,deg",
            ",,0.0,30.0,40.0",
        ]
        path = _make_mini_csv(lines)
        try:
            parser = MergedCSVParser(path)
            result = parser.read_sections(0)
            assert isinstance(result["theta_logmag"], np.ndarray)
            assert result["theta_logmag"].shape == (1, 2)
            assert result["theta_phase"].shape == (1, 2)
            parser.close()
        finally:
            os.unlink(path)

    def test_multi_freq(self):
        """多个频点的索引和读取。"""
        lines = [
            "Theta Log Magnitude,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,dB",
            ",,0.0,-5.0,-6.0",
            ",700.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,dB",
            ",,0.0,-7.0,-8.0",
        ]
        path = _make_mini_csv(lines)
        try:
            parser = MergedCSVParser(path)
            assert parser.num_frequencies == 2
            assert parser.frequencies == [699.0, 700.0]

            b0 = parser.read_section_block("Theta Log Magnitude", 0)
            b1 = parser.read_section_block("Theta Log Magnitude", 1)
            assert b0[0] == [-5.0, -6.0]
            assert b1[0] == [-7.0, -8.0]
            parser.close()
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            MergedCSVParser("/nonexistent/path.csv")

    def test_bad_section_name(self):
        lines = [
            "Theta Log Magnitude,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,dB",
            ",,0.0,-5.0,-6.0",
        ]
        path = _make_mini_csv(lines)
        try:
            parser = MergedCSVParser(path)
            with pytest.raises(ValueError, match="Unknown section"):
                parser.read_section_block("Bad Section", 0)
            parser.close()
        finally:
            os.unlink(path)

    def test_bad_freq_index(self):
        lines = [
            "Theta Log Magnitude,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,dB",
            ",,0.0,-5.0,-6.0",
        ]
        path = _make_mini_csv(lines)
        try:
            parser = MergedCSVParser(path)
            with pytest.raises(IndexError):
                parser.read_section_block("Theta Log Magnitude", 99)
            parser.close()
        finally:
            os.unlink(path)


# ── Real Data ──────────────────────────────────────────────────────

class TestRealData:
    @pytest.fixture
    def parser_5g1(self):
        p = Path(__file__).parent.parent / "data" / "5G1_merged.csv"
        if not p.exists():
            pytest.skip("5G1_merged.csv not found")
        return MergedCSVParser(str(p))

    def test_has_frequencies(self, parser_5g1):
        assert len(parser_5g1.frequencies) > 0

    def test_has_theta_angles(self, parser_5g1):
        assert len(parser_5g1.theta_angles) > 0
        assert abs(parser_5g1.theta_angles[0]) < 1.0  # starts near 0

    def test_has_phi_angles(self, parser_5g1):
        assert len(parser_5g1.phi_angles) > 0

    def test_read_sections_no_crash(self, parser_5g1):
        result = parser_5g1.read_sections(0)
        assert "theta_logmag" in result
        assert isinstance(result["theta_logmag"], np.ndarray)
        assert result["theta_logmag"].ndim == 2

    def test_close(self, parser_5g1):
        parser_5g1.close()
        # close again should be safe
        parser_5g1.close()


# ── Encoding Detection ─────────────────────────────────────────────

class TestEncodingDetection:
    def test_detect_utf8(self):
        lines = [
            "Theta Log Magnitude,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,dB",
            ",,0.0,-5.0,-6.0",
        ]
        path = _make_mini_csv(lines, encoding="utf-8")
        try:
            parser = MergedCSVParser(path)
            # Just accessing frequencies should trigger encoding detection
            assert parser.num_frequencies == 1
            parser.close()
        finally:
            os.unlink(path)

    def test_detect_utf8_bom(self):
        lines = [
            "Theta Log Magnitude,header",
            ",699.000,Theta Angle  (deg),0,90",
            ",,Phi,Resp,dB",
            ",,0.0,-5.0,-6.0",
        ]
        path = _make_mini_csv(lines, encoding="utf-8-sig")
        try:
            parser = MergedCSVParser(path)
            assert parser.num_frequencies == 1
            parser.close()
        finally:
            os.unlink(path)
