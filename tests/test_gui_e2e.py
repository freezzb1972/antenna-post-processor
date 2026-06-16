"""Comprehensive GUI E2E tests with real data — pytest-qt"""
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def window(qapp, monkeypatch, qtbot):
    """Create MainWindow with mocked file dialogs and real data paths."""
    from unittest.mock import MagicMock

    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **kw: ("/tmp/test.csv", ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **kw: "/tmp/output")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **kw: ("/tmp/test_save.json", ""))
    monkeypatch.setattr(QMessageBox, "warning", MagicMock())
    monkeypatch.setattr(QMessageBox, "critical", MagicMock())
    monkeypatch.setattr(QMessageBox, "information", MagicMock())

    # Clean QSettings to avoid stale values
    from PySide6.QtCore import QSettings
    settings = QSettings("AntennaPP", "AntennaPostProcessor")
    settings.clear()
    settings.sync()

    from ui.main_window import MainWindow
    w = MainWindow(qapp)
    qtbot.addWidget(w)
    return w


# =========================================================================
# LAG Display Visibility
# =========================================================================

class TestLagDisplayVisibility:
    """Bug: LAG 已配置项和输入框在暗色主题下看不清"""

    @pytest.mark.skip(reason="QSS palette re-integration needed")
    def test_config_items_text_visible(self, window):
        """每个已配置项 label 有显式 styleSheet 颜色设置（暗色主题兼容）。"""
        window._update_lag_display()
        layout = window.ui.configItemsWidget.layout()
        assert layout is not None, "configItemsWidget has no layout"
        # 获取当前主题的期望颜色
        expected_color = window.palette().color(QPalette.WindowText).name()

        for i in range(layout.count()):
            item = layout.itemAt(i)
            if not item or not item.widget():
                continue
            w = item.widget()
            if not hasattr(w, 'text'):
                continue
            text = w.text()
            if not text or text == '—':
                continue
            ss = w.styleSheet().lower()
            assert "color" in ss, (
                f"Config item '{text}' missing explicit color in stylesheet "
                f"(ss='{w.styleSheet()}') — would be invisible on dark theme"
            )

    def test_spinboxes_have_readable_text(self, window):
        """所有 LAG 设置区的 QDoubleSpinBox 文字可见。"""
        spin_names = [
            "spinCustomAngle", "spinStepStart", "spinStepEnd",
            "spinStepBy", "spinRStart", "spinREnd",
        ]
        for name in spin_names:
            w = getattr(window.ui, name)
            fg = w.palette().color(QPalette.Text)
            bg = w.palette().color(QPalette.Base)
            fg_lum = 0.299 * fg.red() + 0.587 * fg.green() + 0.114 * fg.blue()
            bg_lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
            contrast = abs(fg_lum - bg_lum)
            assert contrast > 50, (
                f"{name}: text={fg.name()} bg={bg.name()} contrast={contrast:.0f} — too low"
            )

    def test_quick_buttons_have_readable_text(self, window):
        """快捷角度按钮文字可见。"""
        for angle, attr in window._QUICK_ANGLES.items():
            btn = getattr(window.ui, attr)
            text_c = btn.palette().color(QPalette.ButtonText)
            bg_c = btn.palette().color(QPalette.Button)
            contrast = abs(
                (0.299 * text_c.red() + 0.587 * text_c.green() + 0.114 * text_c.blue()) -
                (0.299 * bg_c.red() + 0.587 * bg_c.green() + 0.114 * bg_c.blue())
            )
            assert contrast > 30, f"{attr}: button text/bg contrast={contrast:.0f}"

    @pytest.mark.skip(reason="QSS palette re-integration needed")
    def test_custom_qss_applied(self, window):
        """自定义 QSS 包含 LAG 数字框样式。"""
        qss = window.app.styleSheet()
        assert "spinCustomAngle" in qss, "QSS should contain spinCustomAngle styling"
        assert "palette(text)" in qss, "QSS should use palette(text) for color"


# =========================================================================
# File Input & Validation
# =========================================================================

class TestFileInput:
    """Bug: CSV 输入文件加载后点击开始就消失"""

    def test_csv_path_preserved_after_start(self, window):
        """输入路径在 _on_start 调用后不会被清空。"""
        window.ui.editCsvPath.setText("/tmp/test.csv")
        window.ui.editTemplatePath.setText("/tmp/template.xlsx")
        assert window.ui.editCsvPath.text() == "/tmp/test.csv"

        # _on_start 应该因为文件不存在而弹窗警告，但不应清空路径
        window._on_start()
        assert window.ui.editCsvPath.text() == "/tmp/test.csv", (
            "CSV path was cleared after _on_start() — this is the bug!"
        )

    def test_csv_filter_in_dialog(self, window, monkeypatch):
        """文件浏览对话框的运行时 filter 以 CSV 开头。"""
        from unittest.mock import ANY
        filters_captured = []

        def capture_filter(*args, **kwargs):
            # args: (self, title, dir, filter)
            if len(args) >= 4:
                filters_captured.append(args[3])
            return ("/tmp/test.csv", "")

        monkeypatch.setattr(QFileDialog, "getOpenFileName", capture_filter)
        window._on_browse_csv()
        assert len(filters_captured) > 0, "getOpenFileName should have been called"
        actual_filter = filters_captured[0]
        # 第一个（默认）filter 应该是 CSV
        assert actual_filter.startswith("CSV 文件 (*.csv)"), (
            f"Default filter should be CSV, got: {actual_filter}"
        )
        assert "Excel 文件 (*.xlsx *.xls)" in actual_filter, (
            f"Filter should also contain Excel option, got: {actual_filter}"
        )

    def test_empty_input_shows_warning(self, window):
        """空输入时弹窗警告。"""
        window.ui.editCsvPath.clear()
        window.ui.editTemplatePath.setText("/tmp/template.xlsx")
        window._on_start()
        QMessageBox.warning.assert_called()
        args = QMessageBox.warning.call_args[0]
        assert "输入文件" in args[2] or ".csv" in args[2]

    def test_invalid_input_extension_shows_warning(self, window, monkeypatch):
        """不支持的输入文件格式弹窗警告。"""
        from pathlib import Path
        # Create temp file with .txt extension
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        tmp.close()
        monkeypatch.setattr(Path, "exists", lambda self: True)

        window.ui.editCsvPath.setText(tmp.name)
        window.ui.editTemplatePath.setText("/tmp/template.xlsx")
        window._on_start()
        QMessageBox.warning.assert_called()
        args = QMessageBox.warning.call_args[0]
        assert "不支持" in args[2] or "格式" in args[2]

        Path(tmp.name).unlink()

    def test_template_not_excel_shows_warning(self, window, monkeypatch):
        """模板不是 Excel 格式时弹窗警告。"""
        from pathlib import Path
        window.ui.editCsvPath.setText("/tmp/test.csv")
        window.ui.editTemplatePath.setText("/tmp/bad_template.txt")
        monkeypatch.setattr(Path, "exists", lambda self: True)
        window._on_start()
        QMessageBox.warning.assert_called()
        args = QMessageBox.warning.call_args[0]
        assert "模板" in args[2] or "Excel" in args[2]


# =========================================================================
# QFormLayout Integrity
# =========================================================================

class TestFormLayoutIntegrity:
    """Bug: QFormLayout insertRow 导致布局冲突"""

    def test_no_cell_already_occupied(self):
        """验证 formInput 的 LabelRole 和 FieldRole 都分配正确。"""
        # 直接导入模块级常量验证（不需要实例化窗口）
        from ui.compiled.ui_main_window import Ui_MainWindow
        import inspect
        src = inspect.getsource(Ui_MainWindow.setupUi)
        # FieldRole 的行必须正确分配（不能和 LabelRole 混在同一格）
        # 检查 formInput 的 setLayout 是否使用了 FieldRole
        assert 'self.formInput.setLayout(0, QFormLayout.ItemRole.FieldRole, self.hboxLayout)' in src, \
            "formInput row 0 should use FieldRole for hboxLayout"
        assert 'self.formInput.setLayout(1, QFormLayout.ItemRole.FieldRole, self.hboxLayout1)' in src, \
            "formInput row 1 should use FieldRole for hboxLayout1"
        # 检查 formOutput 的 setLayout 也别混
        assert 'self.formOutput.setLayout(0, QFormLayout.ItemRole.FieldRole, self.hboxLayout2)' in src, \
            "formOutput row 0 should use FieldRole for hboxLayout2"
        assert 'self.formOutput.setLayout(3, QFormLayout.ItemRole.FieldRole, self.hboxLayout3)' in src, \
            "formOutput row 3 should use FieldRole for hboxLayout3"
        # 检查 formOutput row 1 的 editOutputName 用 FieldRole
        assert "self.formOutput.setWidget(1, QFormLayout.ItemRole.FieldRole, self.editOutputName)" in src, \
            "formOutput row 1 should use FieldRole for editOutputName"

    @pytest.mark.skip(reason="UI feature re-integration needed")
    def test_selected_file_label_in_vtab(self, window):
        """已选文件标签应该在 vTabFile 中，不破坏 formInput。"""
        vtab = window.ui.vTabFile
        idx = vtab.indexOf(window._selected_file_label)
        assert idx >= 0, "_selected_file_label should be in vTabFile"

        group_idx = vtab.indexOf(window.ui.groupInput)
        assert idx > group_idx, "file label should be after groupInput"

    def test_edit_fields_accessible(self, window):
        """editCsvPath 和 editTemplatePath 可以直接访问和修改。"""
        # Set text
        window.ui.editCsvPath.setText("/tmp/hello.csv")
        assert window.ui.editCsvPath.text() == "/tmp/hello.csv"
        window.ui.editTemplatePath.setText("/tmp/template.xlsx")
        assert window.ui.editTemplatePath.text() == "/tmp/template.xlsx"

        # Clear and re-set
        window.ui.editCsvPath.clear()
        assert window.ui.editCsvPath.text() == ""
        window.ui.editCsvPath.setText("/tmp/new.csv")
        assert window.ui.editCsvPath.text() == "/tmp/new.csv"


# =========================================================================
# Drag & Drop
# =========================================================================

class TestDragDrop:
    """Drag & drop 文件支持"""

    @pytest.mark.skip(reason="Drag-drop re-integration needed")
    def test_csv_accepted(self, window, qtbot):
        from PySide6.QtCore import QMimeData, QUrl
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile("/tmp/test.csv")])
        from PySide6.QtGui import QDragEnterEvent
        event = QDragEnterEvent(
            window.rect().center(), Qt.CopyAction, mime,
            Qt.LeftButton, Qt.NoModifier
        )
        window.dragEnterEvent(event)
        assert event.isAccepted(), "CSV drag should be accepted"

    def test_txt_rejected(self, window, qtbot):
        from PySide6.QtCore import QMimeData, QUrl
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile("/tmp/test.txt")])
        from PySide6.QtGui import QDragEnterEvent
        event = QDragEnterEvent(
            window.rect().center(), Qt.CopyAction, mime,
            Qt.LeftButton, Qt.NoModifier
        )
        window.dragEnterEvent(event)
        assert not event.isAccepted(), "TXT drag should be rejected"


# =========================================================================
# Placeholder Text
# =========================================================================

class TestPlaceholderText:
    """输入框提示语"""

    def test_csv_placeholder_mentions_all_formats(self, window):
        pt = window.ui.editCsvPath.placeholderText().lower()
        assert "csv" in pt
        assert "xlsx" in pt or "xls" in pt

    def test_template_placeholder_mentions_xlsx(self, window):
        pt = window.ui.editTemplatePath.placeholderText().lower()
        assert "xlsx" in pt or "模板" in pt
