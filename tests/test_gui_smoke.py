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
    QGroupBox, QPushButton, QDialogButtonBox,
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
    # QMessageBox.about 也是**静态模态** —— 上面这几个没覆盖到它。
    # 实测 test_menu_action_no_crash[&帮助-关于...] 因此挂死。
    monkeypatch.setattr(QMessageBox, "about", MagicMock(return_value=None))
    # QDialog.exec() 会**模态阻塞**在嵌套事件循环里 —— offscreen 下无人点击关闭,
    # 测试永远走不到后面那句「关闭可能弹出的对话框」的清理代码。
    # 实测 test_menu_action_no_crash[&文件-系统设置...] 因此挂死 20 分钟(CPU 0%)。
    # 打桩为立即返回 0, 相当于用户直接关掉对话框。
    monkeypatch.setattr(QDialog, "exec", lambda self, *a, **k: 0)

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

def _find_in_menu(menu, action_text: str):
    """在 menu 中**递归**查找文本完全匹配的 action, 不触发。

    同样必须保持 `actions()` 列表的引用(见 _top_menu): 临时列表被 GC 时
    PySide 会连带销毁 C++ 的 QAction -> 递归进子菜单或返回后访问都会抛
    "Internal C++ object (QAction) already deleted"。
    实测: 工具子菜单的 6 个项全因此失败。
    """
    actions = menu.actions()
    _MENU_ACTION_REFS.append(actions)
    if len(_MENU_ACTION_REFS) > 64:
        del _MENU_ACTION_REFS[:-32]
    for sa in actions:
        if sa.isSeparator():
            continue
        if sa.text() == action_text:
            return sa
        sub = sa.menu()
        if sub is not None:
            hit = _find_in_menu(sub, action_text)
            if hit is not None:
                return hit
    return None


# 保持 QAction 包装器的引用 —— 见 _top_menu 的说明。
_MENU_ACTION_REFS: list = []


def _top_menu(window, menu_text: str):
    """按文本找到顶层菜单 (忽略 & 助记符)。

    ⚠️ **必须把 actions 列表存下来**, 不能写成 `for a in window.menuBar().actions()`:
    `actions()` 返回的是 PySide 包装器列表, 该临时列表被 GC 时 PySide 会**连带
    销毁 C++ 的 QAction**(它认为自己拥有), 进而销毁其子 QMenu —— 于是本函数
    返回的 QMenu 在调用方手里已经是死对象, 访问即抛
    "Internal C++ object (QMenu) already deleted"。
    实测: 临时列表写法必失败, 保持引用则正常(11 个 action)。
    生产代码无此问题: window_manager.py 用的是 `actions = menu.actions()`(赋给
    局部变量), 菜单也由 `window._menu_window` 长期持有。
    """
    actions = window.menuBar().actions()
    _MENU_ACTION_REFS.append(actions)
    if len(_MENU_ACTION_REFS) > 64:
        del _MENU_ACTION_REFS[:-32]
    for a in actions:
        if a.text().replace("&", "") == menu_text.replace("&", ""):
            return a.menu()
    return None


def _click_menu_action(window, menu_text: str, action_text: str, qtbot):
    """点击指定菜单(可含子菜单)的指定 action, 返回该 action 对象。

    必须是**递归**的: 工具类菜单已改为两级 ——
    `&工具 → 数据处理 → 数据检查与转换...`。只扫一层会找不到这些项。
    """
    sub = _top_menu(window, menu_text)
    if sub is None:
        return None
    sa = _find_in_menu(sub, action_text)
    if sa is None:
        return None
    sub.close()          # 先关闭菜单避免悬空
    sa.trigger()
    qtbot.wait(100)
    return sa


def _click_menu_action_strict(window, menu_text: str, action_text: str, qtbot):
    """同 _click_menu_action, 但找不到时**断言失败**。

    原版找不到时静默返回 None, 而调用方不看返回值 -> 用例「什么都没点却通过」,
    菜单项改名/移动后测试不会报警。实测 [&文件-导出报告...] 就是这样空过的。
    """
    sa = _click_menu_action(window, menu_text, action_text, qtbot)
    assert sa is not None, f"菜单项不存在: {menu_text} → {action_text}"
    return sa


def _all_menu_texts(menu) -> set:
    """递归收集菜单项文本。

    菜单已改为**两级**(如 &工具 → 数据处理 → 数据检查与转换等 7 个工具),
    只遍历一层会漏掉整个子菜单 —— 实测 test_tools_menu_structure_complete
    因此误报 7 个工具全部缺失。
    """
    out = set()
    for a in menu.actions():
        if a.isSeparator():
            continue
        out.add(a.text())
        if a.menu() is not None:
            out |= _all_menu_texts(a.menu())
    return out


def _find_menu_action(window, menu_text: str, action_text: str):
    """查找菜单 action (递归, 含子菜单), 不触发。"""
    sub = _top_menu(window, menu_text)
    return None if sub is None else _find_in_menu(sub, action_text)


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
        ("&文件", "系统设置..."),
        # Window
        ("&窗口", "新建窗口"),
        # Tools
        ("&工具", "数据检查与转换..."),
        ("&工具", "路径损耗补偿..."),
        ("&工具", "数据合并 (多段拼接)..."),
        ("&工具", "步进重采样..."),
        ("&工具", "数据修复 (插值)..."),
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
        _click_menu_action_strict(window, menu, action, qtbot)
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
        # 注: 原期望含 "导出报告", 但该 action 在 main_window.py 中并不存在
        # (导出已移到执行栏的「📄 出报告」按钮)。参数化用例之所以"通过",
        # 是因为 _click_menu_action 找不到时静默返回 None 而调用方未断言。
        expected = {"新建窗口", "打开任务包", "保存任务包", "另存任务包",
                     "打印", "系统设置", "退出"}
        mb = window.menuBar()
        file_menu = None
        for a in mb.actions():
            if "文件" in a.text() or "File" in a.text():
                file_menu = a.menu()
                break
        assert file_menu is not None, "File menu not found"
        found = _all_menu_texts(file_menu)
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
        found = _all_menu_texts(tools_menu)
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

    def test_add_files_click_opens_dialog(self, window, qtbot, monkeypatch):
        page = getattr(window, '_file_settings_page', None)
        if page is None:
            pytest.skip("No _file_settings_page")
        # 打桩并记录调用。原断言 `QFileDialog.getOpenFileNames.called or True`
        # 有两处问题: 既没打桩 (原生函数没有 .called 属性, 取属性直接抛
        # AttributeError), 又用 `or True` 让断言恒真 —— 等于什么都没验证。
        # 返回空列表 = 用户取消了选择。
        calls = []
        monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                            lambda *a, **k: (calls.append(a), ([], ""))[1])
        page._btn_add_files.click()
        qtbot.wait(100)
        assert calls, "点击「添加数据文件」未调用 QFileDialog.getOpenFileNames"

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

class TestAnglePopupButtons:
    """角度配置弹窗 (AntennaParamsPage._show_angle_popup) 的按钮测试。

    本类替换原来的 TestConfigTabButtons。后者测的是 tabLag 页里的
    btnQuick0/30/60/90 / btnAddCustomAngle / btnAddRange / btnStepGenerate /
    btnClearConfig / btnLoadFromTemplate / btnLoadPreset / btnSavePreset。
    但 tabLag 已随 MainWindow._hide_settings_tabs() 的重构被 removeTab 移除
    —— 这些控件对象虽然还活着, 却不在任何 tab 中 (实测
    tabConfig.indexOf(该页) == -1), 永不显示。于是原类 21 个用例里:
      * 4 个 `pytest.skip(f"{attr} not visible")` 型用例永远跳过;
      * 其余用 `if btn.isVisible() and btn.isEnabled(): btn.click()` 的用例
        静默略过点击、且无任何断言 —— 函数跑完即 PASSED。
    即没有一个真正验证过行为 (假绿)。重构后的等价功能在本弹窗内, 故改为覆盖它。

    弹窗实际结构 (实测, 非按源码猜测):
      汇总组 "已配置: N 个单角度, M 个范围"
      「添加单角度」→ "+ 添加"   「步进批量生成」→ "生成"
      「角度范围」  → "添加范围"  顶层 → "确定" / "取消"
    """

    @pytest.fixture
    def popup(self, window, qtbot, monkeypatch):
        """打开 Gain 角度弹窗并返回该 QDialog。

        弹窗以 dlg.exec() 模态阻塞, offscreen 下无人点击关闭。打桩 exec 使其
        立即返回, 并在打桩函数内捕获 dialog 对象 —— 它是 _show_angle_popup 的
        局部变量, 函数返回后便失去引用。
        """
        page = getattr(window, '_antenna_params_page', None)
        if page is None:
            pytest.skip("No _antenna_params_page")
        captured = []

        def fake_exec(self, *a, **k):
            captured.append(self)
            return 0          # 相当于用户直接关闭

        monkeypatch.setattr(QDialog, "exec", fake_exec)
        page._show_angle_popup("gain")
        assert captured, "_show_angle_popup 未创建 QDialog"
        dlg = captured[0]
        qtbot.addWidget(dlg)
        dlg.show()            # 可见性断言需要真实显示
        qtbot.wait(30)
        return dlg

    @staticmethod
    def _group(dlg, title):
        """按标题取 QGroupBox。"""
        for g in dlg.findChildren(QGroupBox):
            if g.title() == title:
                return g
        return None

    @staticmethod
    def _btn(root, text):
        """按文本取 QPushButton (在 root 子树内)。"""
        for b in root.findChildren(QPushButton):
            if b.text() == text:
                return b
        return None

    def test_popup_structure(self, popup):
        """弹窗应含汇总组 + 三个操作组 + 确定/取消。"""
        titles = [g.title() for g in popup.findChildren(QGroupBox)]
        assert any(t.startswith("已配置") for t in titles), f"缺少汇总组: {titles}"
        for t in ("添加单角度", "步进批量生成", "角度范围"):
            assert t in titles, f"缺少按钮组 {t!r} (实得 {titles})"
        for t in ("确定", "取消"):
            assert self._btn(popup, t) is not None, f"缺少按钮 {t!r}"

    def test_add_single_angle_click_no_crash(self, popup, qtbot):
        """「添加单角度」的 + 添加 按钮点击不崩溃。"""
        grp = self._group(popup, "添加单角度")
        assert grp is not None, "未找到「添加单角度」组"
        btn = self._btn(grp, "+ 添加")
        got = [b.text() for b in grp.findChildren(QPushButton)]
        assert btn is not None, f"组内未找到「+ 添加」, 实得 {got}"
        assert btn.isVisible(), "+ 添加 应可见 (弹窗已 show)"
        btn.click()
        qtbot.wait(20)

    def test_step_generate_click_no_crash(self, popup, qtbot):
        """「步进批量生成」的 生成 按钮点击不崩溃。"""
        grp = self._group(popup, "步进批量生成")
        assert grp is not None, "未找到「步进批量生成」组"
        btn = self._btn(grp, "生成")
        assert btn is not None, "缺少「生成」按钮"
        btn.click()
        qtbot.wait(20)

    def test_add_range_click_no_crash(self, popup, qtbot):
        """「角度范围」的 添加范围 按钮点击不崩溃。"""
        grp = self._group(popup, "角度范围")
        assert grp is not None, "未找到「角度范围」组"
        btn = self._btn(grp, "添加范围")
        assert btn is not None, "缺少「添加范围」按钮"
        btn.click()
        qtbot.wait(20)

    def test_cancel_button_no_crash(self, popup, qtbot):
        """取消按钮点击不崩溃。"""
        btn = self._btn(popup, "取消")
        assert btn is not None, "缺少「取消」按钮"
        btn.click()
        qtbot.wait(20)

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
        from src.help_engine import RAGSettings   # 不在 ui.dialogs, 而是 src.help_engine
        # 签名是 (settings, parent=None) —— 原来传单参数会把 MainWindow
        # 当成 settings, 随后 self.settings.enabled 抛 AttributeError。
        dlg = RAGSettingsDialog(RAGSettings(), window)
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
        from ui import dialogs as dlg_module
        from src.help_engine import RAGSettings
        # 用工厂而非裸类: RAGSettingsDialog 的签名是 (settings, parent=None),
        # 与其余 (parent) 不同 —— 统一写 `cls(window)` 会把 MainWindow 当作
        # settings, 在 self.settings.enabled 抛 AttributeError。
        factories = [
            lambda: dlg_module.DataSourceDialog(window),
            lambda: dlg_module.CalcParamsDialog(window),
            lambda: dlg_module.PlotConfigDialog(window),
            lambda: dlg_module.HelpDialog(window),
            lambda: dlg_module.RAGSettingsDialog(RAGSettings(), window),
            lambda: dlg_module.SystemSettingsDialog(window),
            lambda: dlg_module.ResampleDialog(window),
            lambda: dlg_module.BatchCalibrateDialog(window),
            lambda: dlg_module.MergeDialog(window),
            lambda: dlg_module.RepairDialog(window),
            lambda: dlg_module.ActivationDialog(window),
            lambda: dlg_module.PathLossDialog(window),
        ]
        for make in factories:
            dlg = make()
            # 只交给 pytest-qt 托管, **不要**再手动 dlg.deleteLater():
            # addWidget 已登记该对象, teardown 时 _close_widgets 会对它再
            # close 一次; 手动 deleteLater 先销毁了 C++ 对象, teardown 随即抛
            # "Internal C++ object (X) already deleted" —— 该错误还会让下一个
            # 用例在 setup 阶段失败 ("previous item was not torn down properly")。
            qtbot.addWidget(dlg)
            dlg.show()
            qtbot.wait(50)
            dlg.close()
            qtbot.wait(50)
            assert not dlg.isVisible(), f"{type(dlg).__name__} close() 后仍可见"


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
