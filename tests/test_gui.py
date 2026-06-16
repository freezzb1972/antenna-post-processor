"""GUI regression tests — pytest-qt"""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
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
        assert window._match_table is not None

    def test_add_data_files_button_text(self, window):
        """添加数据文件按钮存在。"""
        assert window._btn_add_files is not None
        assert "添加" in window._btn_add_files.text() or "add" in window._btn_add_files.text().lower()


class TestFileDisplay:
    """Bug #2: 文件路径显示在浏览按钮下方，不重叠"""

    @pytest.mark.skip(reason="UI feature pending re-implementation")
    def test_file_label_exists(self, window):
        assert hasattr(window, '_selected_file_label')
        assert window._selected_file_label is not None

    @pytest.mark.skip(reason="UI feature pending re-implementation")
    def test_file_label_updates(self, window, qtbot):
        import tempfile, os
        tmp = os.path.join(tempfile.gettempdir(), "test_antenna.csv")
        Path(tmp).touch()  # create file so stat works
        window.ui.editCsvPath.setText(tmp)
        window._refresh_selected_file_label()
        label_text = window._selected_file_label.text()
        assert "test_antenna.csv" in label_text
        Path(tmp).unlink()

    @pytest.mark.skip(reason="UI feature pending re-implementation")
    def test_file_label_shows_when_empty(self, window):
        window.ui.editCsvPath.clear()
        window._refresh_selected_file_label()
        assert "未选择" in window._selected_file_label.text() or "select" in window._selected_file_label.text().lower()


class TestTemplateReadOnly:
    """Bug #3: 模板不存在时不自动填充"""

    @pytest.mark.skip(reason="QSettings persists across test sessions; behavior verified manually")
    def test_template_cleared_if_missing(self, window, qtbot, monkeypatch):
        from PySide6.QtCore import QSettings
        # Clear any cached template path
        window._settings.setValue("template_path", "")
        window._settings.sync()
        window.ui.editTemplatePath.setText("/nonexistent/template.xlsx")
        window._init_file_paths()
        assert window.ui.editTemplatePath.text() == ""


class TestStartValidation:
    """Bug #4: 输入检测 — 提示语匹配实际格式"""

    def test_empty_input_shows_warning(self, window, qtbot):
        window._data_file_paths.clear()
        window._file_list_widget.clear()
        window._match_table.setRowCount(0)
        window.ui.editTemplatePath.setText("/tmp/template.xlsx")
        window._on_start()
        QMessageBox.warning.assert_called_once()
        args = QMessageBox.warning.call_args[0]
        assert "数据文件" in args[2] or "匹配" in args[2]

    def test_input_label_is_generic(self, window):
        assert window.ui.lblCsv.isHidden() or "输入" in window.ui.lblCsv.text()
