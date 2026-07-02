"""sheet_file_matcher 单元测试 — 键提取 + 自动匹配"""
from src.sheet_file_matcher import MatchResult, auto_match, extract_key, sanitize_sheet_name


class TestExtractKey:
    def test_g_pattern_5G1(self):
        assert extract_key("5G1") == "G1"

    def test_g_pattern_G2(self):
        assert extract_key("G2Final") == "G2"

    def test_g_pattern_lowercase(self):
        assert extract_key("5g3_summary") == "G3"

    def test_g_pattern_no_prefix_digit(self):
        assert extract_key("G4") == "G4"

    def test_g_pattern_two_digit(self):
        assert extract_key("G12") == "G12"

    def test_fallback_stem_upper(self):
        assert extract_key("Antenna") == "ANTENNA"

    def test_strips_extension(self):
        assert extract_key("/path/to/file_5G1_merged.csv") == "G1"

    def test_multi_digit_prefix(self):
        # "25G8" -> strip leading digits -> "G8"
        assert extract_key("25G8_test") == "G8"


class TestSanitizeSheetName:
    def test_no_change_needed(self):
        assert sanitize_sheet_name("Sheet1") == "Sheet1"

    def test_brackets_replaced(self):
        result = sanitize_sheet_name("Sheet[1]")
        assert "[" not in result
        assert "]" not in result

    def test_special_chars_replaced(self):
        result = sanitize_sheet_name("a*b/c\\d?e:f#g")
        assert "*" not in result and "/" not in result and "\\" not in result
        assert "?" not in result and ":" not in result and "#" not in result

    def test_consecutive_underscores_collapsed(self):
        result = sanitize_sheet_name("a[*/]b")
        assert "__" not in result

    def test_truncate_to_max_len(self):
        long_name = "A" * 50
        result = sanitize_sheet_name(long_name, max_len=31)
        assert len(result) == 31


class TestAutoMatch:
    def test_exact_key_match(self):
        sheets = ["5G1", "5G2"]
        files = ["data/5G1_merged.csv", "data/5G2_merged.csv"]
        results = auto_match(sheets, files)

        assert len(results) == 2
        assert results[0].file_path == files[0]
        assert results[0].confidence == 1.0
        assert results[1].file_path == files[1]
        assert results[1].confidence == 1.0

    def test_substring_match(self):
        sheets = ["5G1"]
        files = ["data/5G1FinalSummary.xlsx"]
        results = auto_match(sheets, files)

        assert results[0].file_path == files[0]
        assert results[0].confidence >= 0.8

    def test_fallback_assignment(self):
        sheets = ["Sheet1"]
        files = ["data/unknown_file.csv"]
        results = auto_match(sheets, files)

        assert results[0].file_path == files[0]
        assert results[0].confidence == 0.5

    def test_empty_files(self):
        results = auto_match(["5G1"], [])
        assert len(results) == 1
        assert results[0].file_path is None
        assert results[0].confidence == 0.0

    def test_more_sheets_than_files(self):
        sheets = ["5G1", "5G2", "5G3"]
        files = ["data/5G1_merged.csv"]
        results = auto_match(sheets, files)

        assert len(results) == 3
        matched = [r for r in results if r.file_path is not None]
        assert len(matched) == 1

    def test_more_files_than_sheets(self):
        sheets = ["5G1"]
        files = ["data/5G1_merged.csv", "data/5G2_merged.csv"]
        results = auto_match(sheets, files)

        assert len(results) == 1
        assert results[0].file_path is not None
        assert results[0].confidence > 0

    def test_exact_before_substring(self):
        """精确匹配优先于子串匹配。"""
        sheets = ["G1", "G10"]
        files = ["data/G10_merged.csv", "data/G1_merged.csv"]
        results = auto_match(sheets, files)

        g1 = next(r for r in results if r.sheet_name == "G1")
        g10 = next(r for r in results if r.sheet_name == "G10")
        # G1 应该匹配 G1_merged.csv（精确），不是 G10_merged.csv（子串）
        assert g1.file_path and "G1_" in g1.file_path
        assert g10.file_path and "G10" in g10.file_path

    def test_matchresult_dataclass(self):
        mr = MatchResult(sheet_name="test", file_path="/tmp/test.csv", confidence=1.0)
        assert mr.sheet_name == "test"
        assert mr.confidence == 1.0
