"""GUI regression tests — pytest-qt"""

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def window(qapp, monkeypatch, qtbot):
    """Create MainWindow with mocked file dialogs."""
    # Prevent actual QFileDialog from opening
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **kw: ("/tmp/test_input.csv", ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **kw: "/tmp/output")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **kw: ("/tmp/test_save.json", ""))

    # Mock QMessageBox to prevent blocking popups
    from unittest.mock import MagicMock
    monkeypatch.setattr(QMessageBox, "warning", MagicMock())
    monkeypatch.setattr(QMessageBox, "critical", MagicMock())
    monkeypatch.setattr(QMessageBox, "information", MagicMock())

    from ui.main_window import MainWindow
    w = MainWindow(qapp)
    qtbot.addWidget(w)
    return w


class TestFileInput:
    """Bug #1: 输入文件支持 csv/xlsx/xls — 通过多文件添加"""

    def test_csv_field_hidden(self, window, qtbot):
        """旧的单文件输入框已隐藏，由多文件 Widget 替代。"""
        assert window.ui.editCsvPath.isHidden(), "Old CSV path field should be hidden"
        assert window.ui.btnBrowseCsv.isHidden(), "Old CSV browse button should be hidden"

    def test_multi_file_widget_exists(self, window, qtbot):
        """多文件选择 Widget 已创建。"""
        assert window._file_list_widget is not None
        assert window._btn_add_files is not None
        assert hasattr(window, '_last_matches'), "_last_matches should exist"

    def test_add_data_files_button_text(self, window):
        """添加数据文件按钮存在。"""
        assert window._btn_add_files is not None
        assert "添加" in window._btn_add_files.text() or "add" in window._btn_add_files.text().lower()


class TestFileDisplay:
    """Bug #2: 文件列表显示在添加按钮下方，正确更新"""

    def test_file_list_exists(self, window):
        """_file_list_widget 存在（替代旧的 _selected_file_label）。"""
        assert hasattr(window, '_file_list_widget')
        assert window._file_list_widget is not None

    def test_file_list_updates(self, window):
        """添加文件后列表正确更新。"""
        window._data_file_paths = ["/tmp/test_antenna.csv"]
        window._refresh_data_file_ui()
        assert window._file_list_widget.rowCount() == 1
        assert "test_antenna.csv" in window._file_list_widget.item(0, 0).text()

    def test_file_list_empty_shows_nothing(self, window):
        """无文件时列表为空。"""
        window._data_file_paths.clear()
        window._refresh_data_file_ui()
        assert window._file_list_widget.rowCount() == 0


class TestTemplateReadOnly:
    """Bug #3: 模板路径持久化到 config_manager, 但有意不自动回填输入框。

    历史: 原测试断言「重启后自动恢复上次模板」, 该行为已在 9cab0cc
    (fix: 不自动恢复上次模板 — 用户需手动选择) 有意移除, 理由是避免
    「旧模板自动加载 → 自动匹配 → 意外 Excel 输出」。测试随之过期。
    """

    def test_template_not_auto_restored(self, window):
        """启动时不自动回填模板输入框 — 用户须手动选择。"""
        window._cfg.config.last_template_path = "/test/persisted_template.xlsx"
        try:
            window._init_file_paths()
            assert window.ui.editTemplatePath.text() == ""
        finally:
            window._cfg.config.last_template_path = ""  # cleanup

    def test_template_path_used_as_dialog_start_dir(self, window, monkeypatch):
        """持久化的真实用途: 作为选择模板对话框的起始目录。"""
        window._cfg.config.last_template_path = "/test/persisted_template.xlsx"
        captured = {}

        def _fake_get_open_file_name(parent, title, start_dir, filt):
            captured["start_dir"] = start_dir
            return ("", "")

        monkeypatch.setattr(QFileDialog, "getOpenFileName", _fake_get_open_file_name)
        try:
            window._on_browse_template()
        finally:
            window._cfg.config.last_template_path = ""  # cleanup
        assert captured.get("start_dir") == "/test/persisted_template.xlsx"


class TestStartValidation:
    """Bug #4: 输入检测 — 提示语匹配实际格式"""

    def test_empty_input_shows_warning(self, window, qtbot):
        window._data_file_paths.clear()
        window._file_list_widget.clear()
        window._last_matches = []
        window.ui.editTemplatePath.setText("/tmp/template.xlsx")
        window._on_start()
        QMessageBox.warning.assert_called_once()
        args = QMessageBox.warning.call_args[0]
        assert "数据文件" in args[2] or "匹配" in args[2]

    def test_input_label_is_generic(self, window):
        assert window.ui.lblCsv.isHidden() or "输入" in window.ui.lblCsv.text()
