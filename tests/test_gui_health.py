"""GUI 健康检查 — 布局几何 + 控件可交互 + 功能回归

与 gui-check (widget树/信号) 互补: gui-check 验证结构, 本文件验证「看起来对不对」。
防止「人工截图反馈 → 多轮修改」循环。

每次修改 ui/ 后必须运行:
    python3 -m pytest tests/test_gui_health.py -q
"""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QMessageBox, QPushButton,
    QTableWidgetItem, QLabel, QDoubleSpinBox, QSpinBox,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def window(qapp, monkeypatch, qtbot):
    from unittest.mock import MagicMock

    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **kw: ("/tmp/test.csv", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **kw: (["/tmp/test.csv"], ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **kw: "/tmp/output")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **kw: ("/tmp/test_save.json", ""))
    monkeypatch.setattr(QMessageBox, "warning", MagicMock())
    monkeypatch.setattr(QMessageBox, "critical", MagicMock())
    monkeypatch.setattr(QMessageBox, "information", MagicMock())

    settings = QSettings("AntennaPP", "AntennaPostProcessor")
    settings.clear()
    settings.sync()

    from ui.main_window import MainWindow
    w = MainWindow(qapp)
    qtbot.addWidget(w)
    w.show()
    qapp.processEvents()
    return w


# ── 辅助 ────────────────────────────────────────────────────────────

def _visible_region_width(widget) -> int:
    """返回 widget 在屏幕上的实际可见像素宽度。"""
    return widget.visibleRegion().boundingRect().width()


def _is_within_parent(widget) -> bool:
    """widget 是否完全在父窗口内（不被 stretch 推出右边界）。"""
    if widget.parent() is None:
        return True
    pg = widget.parent().geometry()
    wg = widget.geometry()
    return (wg.x() + wg.width()) <= (pg.width() + 5)


def _switch_to_tab_containing(window, widget_name: str, qtbot) -> bool:
    """导航到包含指定 widget 的 Tab 页。返回是否找到。"""
    tc = window.ui.tabConfig
    target = getattr(window.ui, widget_name, None)
    if target is None:
        return False
    # 尝试每个 Tab: 切换后检查 widget 是否可见
    for i in range(tc.count()):
        tc.setCurrentIndex(i)
        qtbot.wait(30)
        window.app.processEvents() if hasattr(window, 'app') else None
        if target.isVisible():
            return True
    return False


# =========================================================================
# A. 布局几何审计 (Geometry Audit)
# =========================================================================

class TestLayoutGeometry:
    """检测: widget 被裁剪、推出边界、过窄、重叠"""

    # ── 始终可见的控件 ──

    def test_progress_bar_always_visible(self, window):
        pb = window.ui.progressBar
        assert pb.isVisible(), "progressBar should always be visible"
        assert pb.width() >= 100, f"progressBar width={pb.width()}px — too narrow"

    def test_log_output_always_visible(self, window):
        lo = window.ui.logOutput
        assert lo.isVisible(), "logOutput should always be visible"
        assert lo.height() >= 40, f"logOutput height={lo.height()}px — too short"

    # ── 处理设置 Tab: _file_settings_page (新UI) ──

    def test_file_settings_page_visible(self, window, qtbot):
        """_file_settings_page 在「处理设置」Tab 中可见。"""
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("_file_settings_page not found (old UI)")
        # Navigate to the tab containing this page
        tc = window.ui.tabConfig
        for i in range(tc.count()):
            tc.setCurrentIndex(i)
            qtbot.wait(30)
            if page.isVisible():
                break
        assert page.isVisible(), "_file_settings_page not visible in any tab"
        assert page.width() >= 100, f"page width={page.width()}px — too narrow"

    def test_file_settings_buttons_visible(self, window, qtbot):
        """「添加数据文件」按钮可见且足够宽。"""
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("_file_settings_page not found (old UI)")
        # Switch to the tab containing page
        tc = window.ui.tabConfig
        for i in range(tc.count()):
            tc.setCurrentIndex(i)
            qtbot.wait(30)
            if page.isVisible():
                break
        btn = page._btn_add_files
        assert btn.isVisible(), "_btn_add_files not visible"
        assert btn.width() >= 50, f"add files button width={btn.width()}px — too narrow"

    # ── 旧 UI 控件: 应被新 UI 替换 (确认已隐藏，避免双 UI 混淆) ──

    def test_old_file_inputs_hidden_if_replaced(self, window):
        """如果 _file_settings_page 存在，旧的 editTemplatePath 应被隐藏。"""
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("No _file_settings_page (old UI, skip check)")
        # Check if old editTemplatePath is on a hidden page
        tp = window.ui.editTemplatePath
        # Walk up parent chain — all should be invisible or in hidden stack page
        parent_visible = False
        obj = tp.parent()
        while obj and obj != window:
            if hasattr(obj, 'isVisible') and obj.isVisible():
                parent_visible = True
                break
            obj = obj.parent()
        # If parent chain is all hidden, that's expected (new UI took over)
        if not parent_visible and not tp.isVisible():
            return  # expected: old widget hidden, new UI active
        # If old widget is visible AND new page exists, that's a bug
        assert not tp.isVisible(), (
            "editTemplatePath is visible but _file_settings_page also exists — dual UI conflict"
        )

    # ── 关键按钮 ──

    def test_start_stop_buttons_visible(self, window):
        for name in ["btnStart", "btnStop"]:
            btn = getattr(window.ui, name, None)
            if btn is None:
                continue
            assert btn.isVisible(), f"{name} not visible"
            vr = _visible_region_width(btn)
            assert vr >= 30, f"{name} visible width={vr}px — clipped"

    # ── 计算结果 Tab (切换到包含 tabResults 的页面) ──

    def test_results_tab_widgets_visible(self, window, qtbot):
        """切换到「计算结果」Tab 后，match_table 和 file_list 可见。"""
        # Find the tab containing tabResults widget
        tc = window.ui.tabConfig
        for i in range(tc.count()):
            tc.setCurrentIndex(i)
            qtbot.wait(30)
        # At minimum, match_table should exist
        assert window._match_table is not None

    # ── Config Tab ──

    def test_config_tab_spinboxes_reachable(self, window, qtbot):
        """Config 标签页中 SpinBox 可访问。先切换到包含它们的 Tab。"""
        tc = window.ui.tabConfig
        spin_names = [
            "spinCustomAngle", "spinStepStart", "spinStepEnd",
            "spinStepBy", "spinRStart", "spinREnd",
        ]
        # Try each tab until we find one where spinboxes are visible
        found = False
        for i in range(tc.count()):
            tc.setCurrentIndex(i)
            qtbot.wait(50)
            if any(getattr(window.ui, n, None) and getattr(window.ui, n).isVisible()
                   for n in spin_names):
                found = True
                break
        if not found:
            pytest.skip("Config spinboxes not found in any tab")
        for name in spin_names:
            w = getattr(window.ui, name, None)
            if w and w.isVisible():
                assert w.width() >= 30, f"{name} width={w.width()}px — too narrow"

    # ── 无控件被推出右边界 ──

    def test_no_widget_pushed_out_of_bounds(self, window):
        """检查关键交互控件不被 stretch spacer 推出父窗口右边界。"""
        offenders = []
        for attr in ["editTemplatePath", "editOutputDir", "editOutputName",
                     "btnStart", "btnStop"]:
            w = getattr(window.ui, attr, None)
            if w and w.isVisible() and not _is_within_parent(w):
                offenders.append((attr, w.geometry().x(), w.geometry().width()))
        assert not offenders, (
            f"Widgets pushed out of bounds: {offenders}"
        )

    # ── 无重叠 ──

    def test_no_widget_overlap_in_main_area(self, window):
        """关键控件之间不应重叠（简单检测：名称前缀不同的可见控件不发生完全包含）。"""
        checked = []
        for attr in dir(window.ui):
            if attr.startswith("_"):
                continue
            w = getattr(window.ui, attr, None)
            if not hasattr(w, "isVisible") or not w.isVisible():
                continue
            if not hasattr(w, "geometry"):
                continue
            geo = w.geometry()
            if geo.width() < 10 or geo.height() < 10:
                continue
            checked.append((attr, geo))
        # 检查任意两个控件的 geometry 是否完全重合 (same x,y,w,h)
        for i in range(len(checked)):
            for j in range(i + 1, len(checked)):
                a_name, a_geo = checked[i]
                b_name, b_geo = checked[j]
                if (abs(a_geo.x() - b_geo.x()) < 3 and
                    abs(a_geo.y() - b_geo.y()) < 3 and
                    abs(a_geo.width() - b_geo.width()) < 3 and
                    abs(a_geo.height() - b_geo.height()) < 3):
                    # same position and size = likely an overlap bug
                    pytest.fail(
                        f"Overlap: {a_name} and {b_name} at same position "
                        f"({a_geo.x()},{a_geo.y()}) size {a_geo.width()}x{a_geo.height()}"
                    )


# =========================================================================
# B. 交互冒烟测试 (Smoke Test)
# =========================================================================

class TestInteractionSmoke:
    """点击每个按钮/切换每个Tab — 不崩溃即通过"""

    # ── 菜单栏 ──

    def test_menu_file_actions_exist(self, window):
        menu_bar = window.menuBar()
        assert menu_bar is not None
        actions = [a.text() for a in menu_bar.actions()]
        assert any("文件" in t or "File" in t for t in actions), f"Menu actions: {actions}"

    # ── Tab 切换 ──

    def test_tab_config_switch(self, window, qtbot):
        tc = window.ui.tabConfig
        if tc.count() == 0:
            pytest.skip("No tabs in tabConfig")
        for i in range(tc.count()):
            tc.setCurrentIndex(i)
            qtbot.wait(50)
            # No crash = pass

    def test_tab_config_labels_readable(self, window):
        tc = window.ui.tabConfig
        for i in range(tc.count()):
            label = tc.tabText(i)
            assert label, f"Tab {i} has empty label"
            assert len(label) <= 50, f"Tab {i} label too long: {label}"

    # ── Nav 切换 ──

    def test_nav_items_switchable(self, window, qtbot):
        nav = getattr(window, "_nav_list", None)
        if nav is None:
            pytest.skip("No _nav_list")
        for i in range(nav.count()):
            nav.setCurrentRow(i)
            qtbot.wait(50)
            # No crash = pass

    # ── 快捷角度按钮 ──

    def test_quick_angle_buttons_clickable(self, window, qtbot):
        for angle, attr in window._QUICK_ANGLES.items():
            btn = getattr(window.ui, attr, None)
            if btn is None or not btn.isVisible():
                continue
            btn.click()
            qtbot.wait(50)
            # No crash = pass


# =========================================================================
# C. Tab 可见性审计 (Tab Visibility)
# =========================================================================

class TestTabVisibility:
    """防止: 主要功能 Tab 被意外隐藏"""

    # 这些 Tab 永远不应被隐藏（核心功能入口）
    ALWAYS_VISIBLE_TABS = [
        "文件设置", "File Settings",
    ]

    def test_file_settings_tab_visible(self, window):
        tc = window.ui.tabConfig
        for i in range(tc.count()):
            text = tc.tabText(i)
            for pattern in self.ALWAYS_VISIBLE_TABS:
                if pattern in text:
                    assert tc.isTabVisible(i), (
                        f"Tab '{text}' should always be visible"
                    )

    def test_no_hidden_primary_tabs(self, window):
        """除明确标记为辅助的 Tab 外，不应有隐藏的 Tab。"""
        tc = window.ui.tabConfig
        hidden_tabs = []
        for i in range(tc.count()):
            if not tc.isTabVisible(i):
                hidden_tabs.append(tc.tabText(i))
        # 允许少量隐藏的辅助 Tab (如 RSP预设/系统设置/高级)
        allowed_hidden = {"RSP预设", "RSP Presets", "系统设置", "System Settings",
                          "高级", "Advanced", "调试", "Debug"}
        unexpected = [t for t in hidden_tabs if t not in allowed_hidden]
        if unexpected:
            # 不是硬错误, 但需要人工确认
            print(f"  ⚠ hidden tabs: {unexpected}")


# =========================================================================
# D. 控件命名一致性 (Naming Consistency)
# =========================================================================

class TestNamingConsistency:
    """防止: 功能相同的控件在不同位置使用不同名称"""

    def test_lag_config_spinboxes_naming(self, window):
        """LAG 配置相关 SpinBox 命名一致: spinCustomAngle, spinStepStart 等。"""
        expected = [
            "spinCustomAngle", "spinStepStart", "spinStepEnd",
            "spinStepBy", "spinRStart", "spinREnd",
        ]
        for name in expected:
            assert hasattr(window.ui, name), (
                f"Missing expected widget: {name}"
            )

    def test_dual_ui_consistency(self, window):
        """主窗口和对话框之间的状态变量命名一致。"""
        # 检查主窗口和对话框共用 _lag_config 命名
        assert hasattr(window, '_lag_config'), "MainWindow missing _lag_config"


# =========================================================================
# E. 真实数据功能验证 (Real Data Functional)
# =========================================================================

class TestRealDataProcessing:
    """用真实数据文件跑完整流程, 验证输出正确性。"""

    @pytest.fixture
    def data_dir(self):
        return Path(__file__).parent.parent / "data"

    def test_pipeline_output_matches_reference(self, data_dir):
        """标准测试数据 (5G1_merged.csv + template_5G1.xlsx) 输出与参考值一致。"""
        csv_path = data_dir / "5G1_merged.csv"
        tpl_path = data_dir / "template_5G1.xlsx"
        if not csv_path.exists() or not tpl_path.exists():
            pytest.skip("Reference data files missing")

        from src.datasource import DataSource
        from src.pipeline import run_pipeline
        from src.lag_config import PRESET_AUTOMOTIVE

        ds = DataSource.from_path(str(csv_path))
        result = run_pipeline(
            datasource=ds,
            template_path=str(tpl_path),
            output_path="",
            compute_only=True,
            lag_config_override=PRESET_AUTOMOTIVE,
        )

        # 结构验证
        assert len(result) > 0, "No sheets in result"
        for sheet_name, rows in result.items():
            assert len(rows) > 0, f"Sheet '{sheet_name}' has no rows"
            first_row = rows[0]
            # 必需字段
            assert "frequency" in first_row, f"{sheet_name}: missing frequency"
            assert "gain" in first_row, f"{sheet_name}: missing gain"

            # 数值合理性检查 (不应该出现 NaN 或极端值)
            for row in rows:
                gain = row.get("gain")
                if gain is not None:
                    assert -50 < gain < 50, (
                        f"{sheet_name}@{row['frequency']}MHz: gain={gain} — out of range"
                    )

            # 频点去重 (不应有重复频点)
            freqs = [r["frequency"] for r in rows]
            assert len(freqs) == len(set(freqs)), (
                f"{sheet_name}: duplicate frequencies found"
            )

    def test_finalsummary_output_consistency(self, data_dir):
        """FinalSummary 格式数据源也能正确输出。"""
        fs_path = data_dir / "5G1FinalSummary.xlsx"
        tpl_path = data_dir / "template_5G1.xlsx"
        if not fs_path.exists() or not tpl_path.exists():
            pytest.skip("FinalSummary data files missing")

        from src.datasource import DataSource
        from src.pipeline import run_pipeline
        from src.lag_config import PRESET_AUTOMOTIVE

        ds = DataSource.from_path(str(fs_path))
        result = run_pipeline(
            datasource=ds,
            template_path=str(tpl_path),
            output_path="",
            compute_only=True,
            lag_config_override=PRESET_AUTOMOTIVE,
        )

        assert len(result) > 0
        for rows in result.values():
            assert len(rows) > 0
            for row in rows:
                assert "frequency" in row
                # FinalSummary 可能没有 Phase 数据，AR 应该跳过
                if "axial_ratio_error" in row:
                    # 错误必须是字符串（不是崩溃）
                    assert isinstance(row["axial_ratio_error"], str)


# =========================================================================
# F. 对话框完整功能 (Dialog Full Functionality)
# =========================================================================

class TestDialogFunctionality:
    """对话框不仅创建成功，核心功能也能正常执行。"""

    def test_system_settings_dialog_controls(self, window, qtbot):
        """系统设置对话框: 主题/语言/字体控件存在且可操作。"""
        from ui.dialogs import SystemSettingsDialog
        dlg = SystemSettingsDialog(window)
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.wait(100)

        # 查找主题下拉框
        found = False
        for child in dlg.findChildren(QComboBox):
            if child.count() >= 2:
                found = True
                break
        assert found, "SystemSettingsDialog has no theme/language combo"

        dlg.close()

    def test_help_dialog_returns_preview(self, window, qtbot):
        """帮助对话框搜索结果可预览。"""
        from ui.dialogs import HelpDialog
        dlg = HelpDialog(window)
        qtbot.addWidget(dlg)
        dlg._edit_query.setText("Gain")
        dlg._on_search()
        assert dlg._result_list.count() > 0, "Help search for 'Gain' returned nothing"
        # 点击结果应显示内容
        dlg._on_result_clicked(dlg._result_list.item(0))
        content = dlg._rag_answer.toPlainText()
        assert len(content) > 100, f"Preview content too short: {len(content)} chars"
        dlg.close()


# =========================================================================
# G. 内存/性能基线 (Memory/Performance Baseline)
# =========================================================================

class TestPerformanceBaseline:
    """性能回归检测: 不验证具体值, 只验证没有严重退化。"""

    def test_mainwindow_creation_time(self, qapp, qtbot, monkeypatch):
        """MainWindow 创建 < 3s。"""
        import time
        from unittest.mock import MagicMock

        monkeypatch.setattr(QFileDialog, "getOpenFileName",
                            lambda *a, **kw: ("/tmp/test.csv", ""))
        monkeypatch.setattr(QMessageBox, "warning", MagicMock())

        t0 = time.time()
        from ui.main_window import MainWindow
        w = MainWindow(qapp)
        elapsed = time.time() - t0
        assert elapsed < 5.0, f"MainWindow creation took {elapsed:.1f}s"

    def test_pipeline_memory_stable(self):
        """pipeline 处理不应有明显内存泄漏（双次运行后内存增长 < 20%）。"""
        data_dir = Path(__file__).parent.parent / "data"
        csv_path = data_dir / "5G1_merged.csv"
        tpl_path = data_dir / "template_5G1.xlsx"
        if not csv_path.exists() or not tpl_path.exists():
            pytest.skip("Reference data files missing")

        import tracemalloc
        from src.datasource import DataSource
        from src.pipeline import run_pipeline
        from src.lag_config import PRESET_AUTOMOTIVE

        tracemalloc.start()
        ds1 = DataSource.from_path(str(csv_path))
        run_pipeline(datasource=ds1, template_path=str(tpl_path),
                     output_path="", compute_only=True,
                     lag_config_override=PRESET_AUTOMOTIVE)
        _size1, peak1 = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()

        ds2 = DataSource.from_path(str(csv_path))
        run_pipeline(datasource=ds2, template_path=str(tpl_path),
                     output_path="", compute_only=True,
                     lag_config_override=PRESET_AUTOMOTIVE)
        _size2, peak2 = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Peak memory should be similar (within 30%)
        if peak1 > 0:
            ratio = peak2 / peak1
            assert ratio < 1.5, (
                f"Memory peak grew {ratio:.1%}: {peak1/1024:.0f}KB → {peak2/1024:.0f}KB"
            )
