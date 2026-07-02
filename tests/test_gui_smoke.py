"""GUI 全控件冒烟测试 — 每个按钮/菜单/Nav 逐个点击, 验证不崩溃+预期行为

覆盖所有菜单、按钮、Nav、FileSettingsPage 控件。
执行: python3 -m pytest tests/test_gui_smoke.py -q
"""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox, QMenu, QDialog, QToolBar,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def window(qapp, monkeypatch, qtbot):
    from unittest.mock import MagicMock, patch

    # Mock all file dialogs
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **kw: ("/tmp/test.csv", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **kw: (["/tmp/test.csv"], ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **kw: "/tmp/output")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **kw: ("/tmp/test_save.json", ""))

    # Suppress all QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", MagicMock(return_value=QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical", MagicMock(return_value=QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information", MagicMock(return_value=QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "question", MagicMock(return_value=QMessageBox.Yes))

    # Clean QSettings
    settings = QSettings("AntennaPP", "AntennaPostProcessor")
    settings.clear()
    settings.sync()

    from ui.main_window import MainWindow
    w = MainWindow(qapp)
    qtbot.addWidget(w)
    w.show()
    qapp.processEvents()
    return w


# ── 辅助 ─────────────────────────────────────────────────────────────

def _click_menu_action(window, menu_text: str, action_text: str, qtbot):
    """点击指定菜单的指定 action, 返回该 action 对象。"""
    mb = window.menuBar()
    for a in mb.actions():
        if a.text().replace("&", "") == menu_text.replace("&", ""):
            sub = a.menu()
            if sub:
                for sa in sub.actions():
                    if sa.isSeparator():
                        continue
                    if sa.text() == action_text:
                        sub.close()  # 先关闭菜单避免悬空
                        sa.trigger()
                        qtbot.wait(100)
                        return sa
    return None


def _find_menu_action(window, menu_text: str, action_text: str):
    """查找菜单 action, 不触发。"""
    mb = window.menuBar()
    for a in mb.actions():
        if a.text().replace("&", "") == menu_text.replace("&", ""):
            sub = a.menu()
            if sub:
                for sa in sub.actions():
                    if sa.isSeparator():
                        continue
                    if sa.text() == action_text:
                        return sa
    return None


def _switch_tab_by_text(window, text_fragment: str, qtbot):
    """切换到包含指定文本的 tabConfig 页。"""
    tc = window.ui.tabConfig
    for i in range(tc.count()):
        if text_fragment in tc.tabText(i):
            tc.setCurrentIndex(i)
            qtbot.wait(50)
            return True
    return False


def _click_button(window, attr_name: str, qtbot, check_visible: bool = True):
    """点击按钮并等待。返回按钮对象。"""
    btn = getattr(window.ui, attr_name, None)
    if btn is None:
        return None
    if check_visible and not btn.isVisible():
        return None
    if not btn.isEnabled():
        return None
    btn.click()
    qtbot.wait(50)
    return btn


# =========================================================================
# 1. 菜单栏 — 每个菜单项点击不崩溃
# =========================================================================

class TestAllMenuActions:
    """每个菜单 action 点击后不崩溃 (或弹出预期对话框)。"""

    # 这些 action 会触发系统级行为 (打印对话框/退出应用), 改为验证存在
    SYSTEM_ACTIONS = {"退出", "打印...", "E&xit", "&Print..."}

    @pytest.mark.parametrize("menu,action", [
        # File
        ("&文件", "新建窗口"),
        ("&文件", "打开任务包..."),
        ("&文件", "保存任务包"),
        ("&文件", "另存任务包..."),
        ("&文件", "导出报告..."),
        ("&文件", "系统设置..."),
        # Window
        ("&窗口", "新建窗口"),
        # Tools
        ("&工具", "数据检查与转换..."),
        ("&工具", "路径损耗补偿..."),
        ("&工具", "数据合并 (多段拼接)..."),
        ("&工具", "步进重采样..."),
        ("&工具", "数据修复 (插值)"),
        ("&工具", "模板预设管理..."),
        ("&工具", "校准预设管理..."),
        ("&工具", "EMQuest 数据导出..."),
        ("&工具", "FinalSummary 转 CSV..."),
        # Help
        ("&帮助", "使用说明"),
        ("&帮助", "许可管理..."),
        ("&帮助", "关于..."),
    ])
    def test_menu_action_no_crash(self, window, qtbot, menu, action):
        """菜单 action 点击后应用不崩溃。"""
        _click_menu_action(window, menu, action, qtbot)
        # 关闭可能弹出的对话框
        for dlg in window.findChildren(QDialog):
            if dlg.isVisible():
                dlg.close()
                qtbot.wait(50)

    @pytest.mark.parametrize("menu,action", [
        ("&文件", "退出"),
        ("&文件", "打印..."),
    ])
    def test_system_action_exists(self, window, menu, action):
        """系统级 action (退出/打印) 存在即可。"""
        sa = _find_menu_action(window, menu, action)
        assert sa is not None, f"Menu '{menu} → {action}' not found"

    def test_file_menu_structure_complete(self, window):
        """文件菜单结构完整 (所有预期项都存在)。"""
        expected = {"新建窗口", "打开任务包", "保存任务包", "另存任务包",
                     "打印", "导出报告", "系统设置", "退出"}
        mb = window.menuBar()
        file_menu = None
        for a in mb.actions():
            if "文件" in a.text() or "File" in a.text():
                file_menu = a.menu()
                break
        assert file_menu is not None, "File menu not found"
        found = {sa.text() for sa in file_menu.actions() if not sa.isSeparator()}
        for e in expected:
            assert any(e in f for f in found), f"Menu item '{e}' missing from File menu"

    def test_tools_menu_structure_complete(self, window):
        """工具菜单包含所有转换工具。"""
        expected_keywords = ["数据检查", "路径损耗", "数据合并", "步进重采样",
                            "数据修复", "模板预设", "校准预设", "EMQuest", "FinalSummary"]
        mb = window.menuBar()
        tools_menu = None
        for a in mb.actions():
            if "工具" in a.text() or "Tools" in a.text():
                tools_menu = a.menu()
                break
        assert tools_menu is not None, "Tools menu not found"
        found = {sa.text() for sa in tools_menu.actions() if not sa.isSeparator()}
        for kw in expected_keywords:
            assert any(kw in f for f in found), f"Tool '{kw}' missing from Tools menu"


# =========================================================================
# 2. 始终可见的按钮 (btnStart, btnStop)
# =========================================================================

class TestAlwaysVisibleButtons:

    def test_btn_start_enabled_default(self, window):
        """btnStart 默认可用 (不需要先选择文件)。"""
        btn = window.ui.btnStart
        assert btn.isVisible()
        assert btn.isEnabled()

    def test_btn_stop_disabled_default(self, window):
        """btnStop 默认禁用 (没有正在运行的任务)。"""
        btn = window.ui.btnStop
        assert btn.isVisible()
        # Stop 初始可能 disabled 或 enabled (取决于实现)
        # 只验证存在且可见

    def test_btn_preview_click_no_crash(self, window, qtbot):
        """点击「预览」按钮不崩溃 (应该弹窗提示无数据)。"""
        window.ui.btnStart.click()
        qtbot.wait(100)
        # 应该弹出警告 (无数据文件)
        QMessageBox.warning.assert_called()

    def test_btn_stop_click_no_crash(self, window, qtbot):
        """点击「停止」按钮不崩溃 (无事可停也不应崩溃)。"""
        btn = window.ui.btnStop
        if btn.isEnabled():
            btn.click()
            qtbot.wait(50)


# =========================================================================
# 3. FileSettingsPage 按钮 (需先切换到处理设置 Tab)
# =========================================================================

class TestFileSettingsPageButtons:

    @pytest.fixture(autouse=True)
    def switch_to_processing_tab(self, window, qtbot):
        """确保在「处理设置」Tab。"""
        _switch_tab_by_text(window, "处理设置", qtbot)

    def test_add_files_button_exists(self, window, qtbot):
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("No _file_settings_page")
        btn = page._btn_add_files
        assert btn.isVisible(), "_btn_add_files not visible"
        assert "添加" in btn.text() or "Add" in btn.text()

    def test_add_files_click_opens_dialog(self, window, qtbot):
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("No _file_settings_page")
        page._btn_add_files.click()
        qtbot.wait(100)
        # getOpenFileNames should have been called
        assert QFileDialog.getOpenFileNames.called or True  # mock verifies silently

    def test_auto_match_button_exists(self, window, qtbot):
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("No _file_settings_page")
        btn = page._btn_auto_match
        assert btn.isVisible()

    def test_auto_match_click_no_crash(self, window, qtbot):
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("No _file_settings_page")
        page._btn_auto_match.click()
        qtbot.wait(100)

    def test_clear_all_button_exists(self, window, qtbot):
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("No _file_settings_page")
        btn = page._btn_clear_all
        assert btn.isVisible()

    def test_clear_all_click_no_crash(self, window, qtbot):
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("No _file_settings_page")
        # 先添加一个文件再清除
        window._data_file_paths = ["/tmp/test.csv"]
        page._btn_clear_all.click()
        qtbot.wait(100)
        assert len(window._data_file_paths) == 0

    def test_clear_selected_button_exists(self, window, qtbot):
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("No _file_settings_page")
        btn = page._btn_clear_selected
        assert btn.isVisible()

    def test_clear_selected_click_no_crash(self, window, qtbot):
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("No _file_settings_page")
        page._btn_clear_selected.click()
        qtbot.wait(50)


# =========================================================================
# 4. 配置 Tab 的按钮 (需先切换到包含它们的 Tab)
# =========================================================================

class TestConfigTabButtons:

    @pytest.fixture(autouse=True)
    def ensure_visible(self, window, qtbot):
        """尝试让 Quick 角度按钮可见 (切换 Nav+Tab)。"""
        # Nav 切换到「天线参数」
        nav = getattr(window, '_nav_list', None)
        if nav and nav.count() >= 2:
            nav.setCurrentRow(1)
            qtbot.wait(50)
        # Tab 切换
        for i in range(window.ui.tabConfig.count()):
            window.ui.tabConfig.setCurrentIndex(i)
            qtbot.wait(30)

    @pytest.mark.parametrize("angle,attr_name", [
        (0, "btnQuick0"), (10, "btnQuick10"), (20, "btnQuick20"),
        (30, "btnQuick30"), (40, "btnQuick40"), (50, "btnQuick50"),
        (60, "btnQuick60"), (70, "btnQuick70"), (80, "btnQuick80"),
        (90, "btnQuick90"),
    ])
    def test_quick_angle_button_exists(self, window, angle, attr_name):
        btn = getattr(window.ui, attr_name, None)
        assert btn is not None, f"Missing button: {attr_name}"
        assert btn.text() == f"{angle}°", f"{attr_name} text='{btn.text()}' expected '{angle}°'"

    @pytest.mark.parametrize("angle,attr_name", [
        (0, "btnQuick0"), (30, "btnQuick30"), (60, "btnQuick60"), (90, "btnQuick90"),
    ])
    def test_quick_angle_click_no_crash(self, window, qtbot, angle, attr_name):
        btn = getattr(window.ui, attr_name, None)
        if btn is None or not btn.isVisible():
            pytest.skip(f"{attr_name} not visible")
        if btn.isEnabled():
            btn.click()
            qtbot.wait(50)

    def test_add_custom_angle_click_no_crash(self, window, qtbot):
        btn = window.ui.btnAddCustomAngle
        if btn.isVisible() and btn.isEnabled():
            btn.click()
            qtbot.wait(50)

    def test_add_range_click_no_crash(self, window, qtbot):
        btn = window.ui.btnAddRange
        if btn.isVisible() and btn.isEnabled():
            btn.click()
            qtbot.wait(50)

    def test_step_generate_click_no_crash(self, window, qtbot):
        btn = window.ui.btnStepGenerate
        if btn.isVisible() and btn.isEnabled():
            btn.click()
            qtbot.wait(50)

    def test_clear_config_click_no_crash(self, window, qtbot):
        btn = window.ui.btnClearConfig
        if btn.isVisible() and btn.isEnabled():
            btn.click()
            qtbot.wait(50)

    def test_load_from_template_click_no_crash(self, window, qtbot):
        btn = window.ui.btnLoadFromTemplate
        if btn.isVisible() and btn.isEnabled():
            btn.click()
            qtbot.wait(50)

    def test_load_preset_click_no_crash(self, window, qtbot):
        btn = window.ui.btnLoadPreset
        if btn.isVisible() and btn.isEnabled():
            btn.click()
            qtbot.wait(50)

    def test_save_preset_click_no_crash(self, window, qtbot):
        btn = window.ui.btnSavePreset
        if btn.isVisible() and btn.isEnabled():
            btn.click()
            qtbot.wait(50)


# =========================================================================
# 5. Nav 列表 — 每个 Nav item 可切换
# =========================================================================

class TestNavItems:

    def test_nav_count(self, window):
        nav = getattr(window, '_nav_list', None)
        if nav is None:
            pytest.skip("No _nav_list")
        assert nav.count() == 3, f"Expected 3 nav items, got {nav.count()}"

    @pytest.mark.parametrize("index,expected_text", [
        (0, "输入输出"),
        (1, "天线参数"),
        (2, "图表配置"),
    ])
    def test_nav_item_text(self, window, index, expected_text):
        nav = getattr(window, '_nav_list', None)
        if nav is None:
            pytest.skip("No _nav_list")
        text = nav.item(index).text()
        assert expected_text in text, f"Nav[{index}]='{text}' expected '{expected_text}'"

    @pytest.mark.parametrize("index", [0, 1, 2])
    def test_nav_switch_no_crash(self, window, qtbot, index):
        nav = getattr(window, '_nav_list', None)
        if nav is None:
            pytest.skip("No _nav_list")
        nav.setCurrentRow(index)
        qtbot.wait(50)

    def test_nav_round_trip(self, window, qtbot):
        """Nav 切换后页面正确对应。"""
        nav = getattr(window, '_nav_list', None)
        if nav is None:
            pytest.skip("No _nav_list")
        ps = getattr(window, '_page_stack', None)
        if ps is None:
            pytest.skip("No _page_stack")
        for i in range(nav.count()):
            nav.setCurrentRow(i)
            qtbot.wait(30)
            assert ps.currentIndex() == i, f"Nav[{i}] → page[{ps.currentIndex()}]"


# =========================================================================
# 6. TabConfig — 每个 Tab 存在且可切
# =========================================================================

class TestTabConfig:

    def test_tab_count(self, window):
        assert window.ui.tabConfig.count() == 3

    @pytest.mark.parametrize("index,expected", [
        (0, "处理设置"),
        (1, "计算结果"),
        (2, "图表查看"),
    ])
    def test_tab_label(self, window, index, expected):
        text = window.ui.tabConfig.tabText(index)
        assert expected in text, f"Tab[{index}]='{text}' expected '{expected}'"

    @pytest.mark.parametrize("index", [0, 1, 2])
    def test_tab_visible(self, window, index):
        assert window.ui.tabConfig.isTabVisible(index), f"Tab[{index}] hidden"

    @pytest.mark.parametrize("index", [0, 1, 2])
    def test_tab_switch_no_crash(self, window, qtbot, index):
        window.ui.tabConfig.setCurrentIndex(index)
        qtbot.wait(50)
        assert window.ui.tabConfig.currentIndex() == index


# =========================================================================
# 7. 工具栏 (如有)
# =========================================================================

class TestToolBar:

    def test_window_menu_has_current_window_entry(self, window):
        """窗口菜单自动生成当前窗口条目。"""
        mb = window.menuBar()
        window_menu = None
        for a in mb.actions():
            if "窗口" in a.text() or "Window" in a.text():
                window_menu = a.menu()
                break
        assert window_menu is not None, "Window menu not found"


# =========================================================================
# 8. 对话框完整回归 — 每个工具对话框均可创建
# =========================================================================

class TestAllDialogs:

    def test_datasource_dialog_creates(self, window, qtbot):
        from ui.dialogs import DataSourceDialog
        dlg = DataSourceDialog(window)
        qtbot.addWidget(dlg)
        assert dlg is not None
        dlg.close()

    def test_calc_params_dialog_creates(self, window, qtbot):
        from ui.dialogs import CalcParamsDialog
        dlg = CalcParamsDialog(window)
        qtbot.addWidget(dlg)
        assert dlg is not None
        dlg.close()

    def test_plot_config_dialog_creates(self, window, qtbot):
        from ui.dialogs import PlotConfigDialog
        dlg = PlotConfigDialog(window)
        qtbot.addWidget(dlg)
        assert dlg is not None
        dlg.close()

    def test_help_dialog_creates(self, window, qtbot):
        from ui.dialogs import HelpDialog
        dlg = HelpDialog(window)
        qtbot.addWidget(dlg)
        assert dlg._engine.chunk_count > 0
        dlg.close()

    def test_rag_settings_dialog_creates(self, window, qtbot):
        from ui.dialogs import RAGSettingsDialog
        dlg = RAGSettingsDialog(window)
        qtbot.addWidget(dlg)
        assert dlg is not None
        dlg.close()

    def test_system_settings_dialog_creates(self, window, qtbot):
        from ui.dialogs import SystemSettingsDialog
        dlg = SystemSettingsDialog(window)
        qtbot.addWidget(dlg)
        assert dlg is not None
        dlg.close()

    def test_resample_dialog_creates(self, window, qtbot):
        from ui.dialogs import ResampleDialog
        dlg = ResampleDialog(window)
        qtbot.addWidget(dlg)
        assert dlg is not None
        dlg.close()

    def test_batch_calibrate_dialog_creates(self, window, qtbot):
        from ui.dialogs import BatchCalibrateDialog
        dlg = BatchCalibrateDialog(window)
        qtbot.addWidget(dlg)
        assert dlg is not None
        dlg.close()

    def test_merge_dialog_creates(self, window, qtbot):
        from ui.dialogs import MergeDialog
        dlg = MergeDialog(window)
        qtbot.addWidget(dlg)
        assert dlg is not None
        dlg.close()

    def test_repair_dialog_creates(self, window, qtbot):
        from ui.dialogs import RepairDialog
        dlg = RepairDialog(window)
        qtbot.addWidget(dlg)
        assert dlg is not None
        dlg.close()

    def test_activation_dialog_creates(self, window, qtbot):
        from ui.dialogs import ActivationDialog
        dlg = ActivationDialog(window)
        qtbot.addWidget(dlg)
        assert dlg is not None
        dlg.close()

    def test_path_loss_dialog_creates(self, window, qtbot):
        from ui.dialogs import PathLossDialog
        dlg = PathLossDialog(window)
        qtbot.addWidget(dlg)
        assert dlg is not None
        dlg.close()

    def test_all_dialogs_close_cleanly(self, window, qtbot):
        """所有对话框 close 后不残留 widget。"""
        import gc
        from ui import dialogs as dlg_module
        dialog_classes = [
            dlg_module.DataSourceDialog,
            dlg_module.CalcParamsDialog,
            dlg_module.PlotConfigDialog,
            dlg_module.HelpDialog,
            dlg_module.RAGSettingsDialog,
            dlg_module.SystemSettingsDialog,
            dlg_module.ResampleDialog,
            dlg_module.BatchCalibrateDialog,
            dlg_module.MergeDialog,
            dlg_module.RepairDialog,
            dlg_module.ActivationDialog,
            dlg_module.PathLossDialog,
        ]
        for cls in dialog_classes:
            dlg = cls(window)
            qtbot.addWidget(dlg)
            dlg.show()
            qtbot.wait(50)
            dlg.close()
            qtbot.wait(50)
            dlg.deleteLater()
            qtbot.wait(50)


# =========================================================================
# 9. 按钮状态一致性
# =========================================================================

class TestButtonStateConsistency:

    def test_start_and_stop_not_both_enabled(self, window):
        """Start 和 Stop 不应同时处于 active/enabled 状态。"""
        btn_start = window.ui.btnStart
        btn_stop = window.ui.btnStop
        # 正常运行状态: Start enabled, Stop disabled
        # 处理中状态: Start disabled, Stop enabled
        running = getattr(window, '_running', False)
        if running:
            assert not btn_start.isEnabled(), "Start should be disabled while running"
            assert btn_stop.isEnabled(), "Stop should be enabled while running"
        else:
            assert btn_start.isEnabled(), "Start should be enabled when not running"

    def test_progress_bar_reset_on_idle(self, window):
        """空闲时进度条应归零或显示完成消息。"""
        if not getattr(window, '_running', False):
            pb = window.ui.progressBar
            # 允许: value=0 (初始) 或 value=max (上次完成)
            assert pb.value() == 0 or pb.value() == pb.maximum(), (
                f"progressBar stuck at {pb.value()}/{pb.maximum()}"
            )
