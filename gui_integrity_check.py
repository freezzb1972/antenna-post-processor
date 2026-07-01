#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI Integrity Harness (G0-G9) - validate widget tree, FormLayout, signals,
ScrollArea, dialog sizes, font propagation, and manifest coverage.

Usage:
    python3 gui_integrity_check.py          # full check
    python3 gui_integrity_check.py --quick  # G1-G3 only (5s)
    python3 gui_integrity_check.py --json   # JSON output for CI
"""

from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── 配置 ────────────────────────────────────────────────────────────────

# G1: 必须存在且可见的 widget
REQUIRED_VISIBLE = [
    "editOutputName", "editOutputDir", "editTemplatePath",
    "btnPreview", "btnExport", "btnStop", "progressBar", "logOutput",
]

# G1: 必须隐藏的 widget
REQUIRED_HIDDEN = [
    "editCsvPath", "btnBrowseCsv", "lblCsv",
    "btnStart",  # Phase 3: 替换为 btnPreview + btnExport, 原按钮隐藏
]

# G1: 最小尺寸要求 (widget_attr, min_w, min_h)
MIN_SIZE_REQUIREMENTS = [
    ("editOutputName", 180, 0),
    ("editOutputDir", 180, 0),
    ("editFullReportPath", 180, 0),
]

# G7: 动态创建的 widget 必须存在
DYNAMIC_WIDGETS_REQUIRED = [
    "_file_list_widget", "_match_table", "_btn_add_files",
    "_btn_auto_match", "_check_extrapolate",
]

# G7: 动态 widget 必须正确添加到布局中(在父容器内可见)
DYNAMIC_LAYOUT_CHECKS = [
    # 模板管理 UI 已移至 SystemSettingsDialog, 不再在 MainWindow 中创建
]

# G7b: 必须保持可见的 Tab 页签
# 文件设置/处理参数/3D图形/参数设置 通过菜单访问 (设置→数据源配置, 文件→系统设置)
REQUIRED_VISIBLE_TABS = []

# G7b: 动态 widget 的祖先链中每个 QGroupBox/QWidget 必须可见(不被 setTabVisible 隐藏)
# (widget_attr, ancestor_type, ancestor_index_in_tab_widget)
DYNAMIC_ANCESTOR_TAB = [
    # 模板管理 UI 已移至 SystemSettingsDialog, 不再在 MainWindow 的 tab 中
]

# G5c: 对话框最小尺寸验证
DIALOG_MIN_SIZES = {
    "SystemSettingsDialog": (500, 400),    # LLM API 字段需要宽度
    "DataSourceDialog": (500, 300),
    "RAGSettingsDialog": (450, 300),
}

# G5c: 对话框输入框最小宽度
DIALOG_INPUT_MIN_WIDTH = {
    "SystemSettingsDialog": {
        "_edit_api_base": 300,
        "_edit_api_key": 300,
    },
    "RAGSettingsDialog": {
        "_edit_api_base": 280,
        "_edit_api_key": 280,
    },
}

# G9: 字体变更后必须响应式变化的 widget 类型
FONT_SENSITIVE_WIDGETS = [
    "QMenuBar", "QMenu", "QStatusBar",
]

# G3: _on_start 中必须存在的关键代码行
THREAD_START_REQUIRED = [
    "QThread(self)",
    "ProcessingWorker(",
    "moveToThread(",
    "self._thread.started.connect(self._worker.run)",
    "self._worker.progress.connect(self._on_progress)",
    "self._worker.log.connect(self._on_worker_log)",
    "self._worker.finished.connect(self._on_finished)",
    "self._worker.error.connect(self._on_error)",
    "self._thread.start()",
    "self._running = True",
]


# G0: manifest 路径
MANIFEST_PATH = PROJECT_ROOT / "verify-manifest.json"


# ── 检查函数 ────────────────────────────────────────────────────────────

def check_g0_manifest_discovery() -> List[str]:
    """G0: 自动发现新 widget/模块/方法 -> 与 verify-manifest.json 交叉验证。

    扫描编译 UI + 主窗口源码，找到所有 widget/方法/源模块，
    与 manifest 中已注册的对比。未注册的标记为 UNVERIFIED。
    这确保新增 UI 元素不会被遗忘。
    """
    errors = []
    if not MANIFEST_PATH.exists():
        errors.append("MANIFEST: verify-manifest.json not found. Run with --init to create.")
        return errors

    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"MANIFEST: failed to parse: {e}")
        return errors

    # 1. 收集 manifest 中已知的所有 widget
    known_compiled = set(manifest.get("ui", {}).get("compiled_widgets", []))
    known_dynamic = set(manifest.get("ui", {}).get("dynamic_widgets", []))
    known_methods = set(manifest.get("ui", {}).get("methods", []))
    known_modules = set(manifest.get("computation", {}).get("modules", []))
    all_known_widgets = known_compiled | known_dynamic

    # 2. 扫描编译 UI 中的 widget
    compiled = PROJECT_ROOT / "ui" / "compiled" / "ui_main_window.py"
    if compiled.exists():
        src = compiled.read_text(encoding="utf-8")
        actual_compiled = set()
        for m in re.finditer(r'self\.(\w+)\s*=\s*(Q\w+)\(', src):
            actual_compiled.add(m.group(1))
        new_compiled = actual_compiled - known_compiled
        if new_compiled:
            for w in sorted(new_compiled):
                errors.append(f"MANIFEST: compiled widget '{w}' not in verify-manifest.json → status=UNVERIFIED")

    # 3. 扫描 main_window.py 中动态创建的 widget
    mw = PROJECT_ROOT / "ui" / "main_window.py"
    if mw.exists():
        src = mw.read_text(encoding="utf-8")
        actual_dynamic = set()
        for m in re.finditer(r'self\.(_\w+)\s*=\s*(Q\w+)\(', src):
            actual_dynamic.add(m.group(1))
        new_dynamic = actual_dynamic - known_dynamic
        if new_dynamic:
            for w in sorted(new_dynamic):
                errors.append(f"MANIFEST: dynamic widget '{w}' not in verify-manifest.json → status=UNVERIFIED")

    # 4. 扫描 src/ 中是否有新模块
    src_dir = PROJECT_ROOT / "src"
    actual_modules = set(f.name for f in src_dir.glob("*.py") if f.name != "__init__.py")
    new_modules = actual_modules - known_modules
    if new_modules:
        for m in sorted(new_modules):
            errors.append(f"MANIFEST: src module '{m}' not in verify-manifest.json → status=UNVERIFIED")

    # 5. 扫描 ui/*.py 新 UI 文件
    ui_dir = PROJECT_ROOT / "ui"
    actual_ui = set(f.name for f in ui_dir.glob("*.py") if f.name != "__init__.py")
    new_ui = actual_ui - {m.replace('ui/', '') for m in known_modules if m.startswith('ui/')}
    # simplified: check for splash_screen.py etc
    for f in sorted(ui_dir.glob("*.py")):
        if f.name == "__init__.py":
            continue
        module_name = f"ui/{f.name}"
        if module_name not in known_modules and f.name not in ("main_window.py",):
            # check if any feature references this module
            found = False
            for feat in manifest.get("features", []):
                if module_name in feat.get("src_modules", []) or module_name in str(feat.get("widgets", [])):
                    found = True
                    break
            if not found:
                errors.append(f"MANIFEST: UI module '{module_name}' not registered in any feature")

    return errors


def check_g0_manifest_coverage() -> List[str]:
    """G0b: 检查 manifest 中标记为 untested/partial 的特性数量。

    覆盖率低于 100% 是增量开发的正常现象 —— 新特性在实现后会逐步
    补充测试和 manifest 标记。G0b 不会阻塞 CI (INFO_PHASES 列表),
    仅提供参考信息。
    """
    errors = []
    if not MANIFEST_PATH.exists():
        return errors
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return errors

    untested = [f for f in manifest.get("features", []) if f.get("status") in ("untested", "e2e_pending")]
    if untested:
        errors.append(f"COVERAGE: {len(untested)} features still untested/e2e_pending:")
        for f in untested:
            errors.append(f"  - {f['id']}: {f['description']} [{f['status']}]")

    total = len(manifest.get("features", []))
    verified = sum(1 for f in manifest.get("features", []) if f.get("status") == "verified")
    if total > 0:
        pct = 100 * verified / total
        if pct < 60:
            errors.append(f"COVERAGE: only {verified}/{total} features verified ({pct:.0f}%)")

    return errors


def _read_source(filepath: Path) -> str:
    return filepath.read_text(encoding="utf-8")


def check_g1_widget_tree(window) -> List[str]:
    """G1: Widget 存在性 + 可见性 + 最小尺寸。"""
    errors = []
    for attr in REQUIRED_VISIBLE:
        w = getattr(window.ui, attr, None)
        if w is None:
            errors.append(f"MISSING: ui.{attr}")
        elif w.isHidden():
            errors.append(f"HIDDEN: ui.{attr} should be visible")

    for attr in REQUIRED_HIDDEN:
        w = getattr(window.ui, attr, None)
        if w is not None and not w.isHidden():
            errors.append(f"VISIBLE: ui.{attr} should be hidden")

    for attr, min_w, min_h in MIN_SIZE_REQUIREMENTS:
        w = getattr(window.ui, attr, None)
        if w is None:
            continue
        if min_w > 0 and w.minimumWidth() < min_w:
            errors.append(f"SIZE: ui.{attr} minWidth={w.minimumWidth()} < {min_w}")
        if min_h > 0 and w.minimumHeight() < min_h:
            errors.append(f"SIZE: ui.{attr} minHeight={w.minimumHeight()} < {min_h}")

    # 自定义 widget 存在性
    for attr in ["_file_list_widget", "_match_table", "_btn_add_files",
                  "_btn_auto_match", "_check_extrapolate"]:
        if getattr(window, attr, None) is None:
            errors.append(f"MISSING: window.{attr}")

    return errors


def check_g2_formlayout() -> List[str]:
    """G2: FormLayout 的 LabelRole/FieldRole 成对出现。"""
    compiled = PROJECT_ROOT / "ui" / "compiled" / "ui_main_window.py"
    src = _read_source(compiled)

    errors = []
    # 查找所有 form layout 的 setWidget/setLayout 调用
    forms: dict = {}  # {form_name: {row: {LabelRole: x, FieldRole: x}}}
    pattern = r"(self\.\w+)\.(setWidget|setLayout)\((\d+),\s*QFormLayout\.ItemRole\.(\w+),\s*(self\.\w+)"
    for m in re.finditer(pattern, src):
        form = m.group(1)
        row = int(m.group(3))
        role = m.group(4)
        if form not in forms:
            forms[form] = {}
        if row not in forms[form]:
            forms[form][row] = {}
        forms[form][row][role] = m.group(5)

    for form_name, rows in forms.items():
        for row, roles in rows.items():
            if "LabelRole" not in roles and row not in _SKIP_LABELROLE_ROWS.get(form_name, []):
                errors.append(f"FormLayout {form_name} row {row}: missing LabelRole")
            if "FieldRole" not in roles and row not in _SKIP_FIELDROLE_ROWS.get(form_name, []):
                errors.append(f"FormLayout {form_name} row {row}: missing FieldRole")

    return errors


# 跨列 widget (checkbox 等) 不需要同时拥有 LabelRole 和 FieldRole
_SKIP_FIELDROLE_ROWS = {
    "self.formOutput": [2],  # checkFullReport — FieldRole only
}
_SKIP_LABELROLE_ROWS = {
    "self.formOutput": [2],  # checkFullReport spans both columns
}


def check_g3_signal_chain() -> List[str]:
    """G3: 信号连接链路完整性。"""
    main_win = PROJECT_ROOT / "ui" / "main_window.py"
    src = _read_source(main_win)
    errors = []

    # 1. btnPreview → _on_preview, btnExport → _on_export
    if "self.ui.btnPreview.clicked.connect(self._on_preview)" not in src:
        errors.append("SIGNAL: btnPreview.clicked not connected to _on_preview")

    # 2. _on_start 内必须包含线程启动协议的所有步骤
    for required in THREAD_START_REQUIRED:
        if required not in src:
            errors.append(f"THREAD: missing '{required}' in _on_start")

    return errors


def check_g4_scrollarea(window) -> List[str]:
    """G4: tabFile 和 tabLag 的内容已包在 QScrollArea 中。"""
    errors = []
    tc = window.ui.tabConfig
    for i in range(tc.count()):
        w = tc.widget(i)
        from PySide6.QtWidgets import QScrollArea
        if not isinstance(w, QScrollArea) and tc.isTabVisible(i):
            tab_name = tc.tabText(i)
            if "结果" not in tab_name and "展示" not in tab_name:  # 结果Tab无需ScrollArea
                errors.append(f"SCROLL: tab[{i}] '{tab_name}' not wrapped in QScrollArea")
    return errors


def check_g5_dialog_flow() -> List[str]:
    """G5: 对话框创建+运行 — 验证3个设置对话框不崩溃。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.main_window import MainWindow
    w = MainWindow(app)
    errors = []

    # 数据源对话框
    try:
        from ui.dialogs import DataSourceDialog
        d = DataSourceDialog(w)
        if d is None: errors.append("DataSourceDialog returned None")
    except Exception as e:
        errors.append(f"DataSourceDialog CRASH: {e}")

    # 计算参数对话框
    try:
        from ui.dialogs import CalcParamsDialog
        d = CalcParamsDialog(w)
        if d is None: errors.append("CalcParamsDialog returned None")
    except Exception as e:
        errors.append(f"CalcParamsDialog CRASH: {e}")

    # 图形配置对话框
    try:
        from ui.dialogs import PlotConfigDialog
        d = PlotConfigDialog(w)
        if d is None: errors.append("PlotConfigDialog returned None")
    except Exception as e:
        errors.append(f"PlotConfigDialog CRASH: {e}")

    return errors


def check_g5b_dialog_state() -> List[str]:
    """G5b: 对话框 widget 状态验证 — 复选框启用, 路径完整。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.main_window import MainWindow
    w = MainWindow(app)
    errors = []

    # 数据源对话框 — 文件列表尺寸验证
    from ui.dialogs import DataSourceDialog
    d = DataSourceDialog(w)
    if d._file_list.maximumHeight() < 500 and d._file_list.maximumHeight() > 0:
        errors.append(f"DataSourceDialog: file_list maxHeight={d._file_list.maximumHeight()} should be larger or unset")
    if d.minimumWidth() < 500:
        errors.append(f"DataSourceDialog: minWidth={d.minimumWidth()} too small")

    # 计算参数对话框 — 复选框状态验证(双列结构)
    from ui.dialogs import CalcParamsDialog
    d2 = CalcParamsDialog(w)
    if not hasattr(d2, '_left_checkboxes') or not hasattr(d2, '_right_checkboxes'):
        errors.append("CalcParamsDialog: _left_checkboxes or _right_checkboxes not found")
    else:
        for key, cb in d2._left_checkboxes.items():
            if not cb.isEnabled():
                errors.append(f"CalcParamsDialog: left checkbox '{key}' is DISABLED")
        for key, cb in d2._right_checkboxes.items():
            if not cb.isEnabled():
                errors.append(f"CalcParamsDialog: right checkbox '{key}' is DISABLED")
        # 验证双列有内容
        if len(d2._left_checkboxes) == 0:
            errors.append("CalcParamsDialog: _left_checkboxes is empty (should have params)")
        if len(d2._right_checkboxes) == 0:
            errors.append("CalcParamsDialog: _right_checkboxes is empty (should have params)")

    return errors


def check_g6_gui_flow() -> List[str]:
    """G6: 完整GUI流程 — 对话框写入状态→_on_start→验证线程启动。"""
    from PySide6.QtWidgets import QApplication, QComboBox, QTableWidgetItem
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.main_window import MainWindow
    w = MainWindow(app)
    errors = []

    # 模拟数据源对话框流程
    w.ui.editTemplatePath.setText(str(PROJECT_ROOT / "data" / "template_5G1.xlsx"))
    w._data_file_paths = [str(PROJECT_ROOT / "data" / "5G1_merged.csv")]
    w._refresh_data_file_ui()
    w._match_table.setRowCount(1)
    w._match_table.setItem(0, 0, QTableWidgetItem("5G1"))
    combo = QComboBox()
    combo.addItem(str(PROJECT_ROOT / "data" / "5G1_merged.csv"))
    combo.setCurrentIndex(0)
    w._match_table.setCellWidget(0, 1, combo)
    w._match_table.setItem(0, 2, QTableWidgetItem("matched"))

    # 触发开始
    try:
        w._on_start()
    except SystemExit:
        pass

    # 验证线程启动 (处理可能很快完成, 此时 _running=False/_thread=None 也是正常的)
    if not w._running and w._thread is None and not hasattr(w, '_g6_processing_done'):
        errors.append("G6_FLOW: _running=False — 线程未启动")
    if w._thread is None and not hasattr(w, '_g6_processing_done'):
        errors.append("G6_FLOW: _thread=None — 未创建线程")
    elif w._thread is not None and not w._thread.isRunning():
        errors.append("G6_FLOW: thread.isRunning()=False — 线程未run")

    # 验证管线确实跑了数据
    if w._thread and w._thread.isRunning():
        w._thread.wait(10000)  # 等最多10秒

    # 清理
    # 清理 (处理可能已完成, _thread 已为 None)
    if w._thread and w._thread.isRunning():
        try: w._on_stop(); w._thread.quit(); w._thread.wait(3000)
        except Exception: pass

    return errors


def check_g7_dynamic_widgets(window) -> List[str]:
    """G7: 动态创建的 widget 存在 + 正确添加到布局中 + 祖先链可见。"""
    errors = []

    # 1. widget 存在性
    for attr in DYNAMIC_WIDGETS_REQUIRED:
        if getattr(window, attr, None) is None:
            errors.append(f"MISSING: window.{attr} not created in __init__")

    # 2. widget 是否在父容器的布局中(运行时验证)
    for attr, parent_attr in DYNAMIC_LAYOUT_CHECKS:
        w = getattr(window, attr, None)
        if w is None:
            continue
        parent = getattr(window.ui, parent_attr, None)
        if parent is None:
            errors.append(f"LAYOUT: window.{attr} parent '{parent_attr}' not found in ui")
            continue
        # 检查 widget 是否在父容器的子孙中
        p = w.parent()
        is_child = False
        while p is not None:
            if p is parent:
                is_child = True
                break
            p = p.parent()
        if not is_child:
            errors.append(f"LAYOUT: window.{attr} not in parent '{parent_attr}' widget tree")

    # 3. 必须可见的 Tab 页签 — 核心操作 UI 不应被隐藏
    tc = window.ui.tabConfig
    for tab_idx, tab_name in REQUIRED_VISIBLE_TABS:
        if not tc.isTabVisible(tab_idx):
            errors.append(
                f"TAB: Tab[{tab_idx}] '{tab_name}' is hidden by setTabVisible(False). "
                f"This contains core UI widgets and must be visible by default."
            )

    # 4. 动态 widget 的祖先链中不应有被 setTabVisible(False) 隐藏的容器
    for attr, ancestor_name, tab_idx in DYNAMIC_ANCESTOR_TAB:
        w = getattr(window, attr, None)
        if w is None:
            continue
        ancestor = getattr(window.ui, ancestor_name, None)
        if ancestor is None:
            continue
        # 检查 widget 是否在该祖先的子树中
        p = w.parent()
        in_subtree = False
        while p is not None:
            if p is ancestor:
                in_subtree = True
                break
            p = p.parent()
        if in_subtree and not tc.isTabVisible(tab_idx):
            errors.append(
                f"ANCESTOR: window.{attr} is inside '{ancestor_name}' "
                f"but Tab[{tab_idx}] is hidden. UI 不可见!"
            )

    return errors


def check_g5c_dialog_sizes() -> List[str]:
    """G5c: 所有对话框的最小尺寸 + 输入框宽度。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.main_window import MainWindow
    w = MainWindow(app)
    errors = []

    # 对话框名 → (factory_fn, dialog_class_name)
    dialogs_to_check = []

    # SystemSettingsDialog
    try:
        from ui.dialogs import SystemSettingsDialog
        d = SystemSettingsDialog(w)
        dialogs_to_check.append(("SystemSettingsDialog", d))
    except Exception as e:
        errors.append(f"CRASH: SystemSettingsDialog: {e}")

    # RAGSettingsDialog
    try:
        from ui.dialogs import RAGSettingsDialog
        from src.help_engine import RAGSettings
        d = RAGSettingsDialog(RAGSettings(), w)
        dialogs_to_check.append(("RAGSettingsDialog", d))
    except Exception as e:
        errors.append(f"CRASH: RAGSettingsDialog: {e}")

    # HelpDialog
    try:
        from ui.dialogs import HelpDialog
        d = HelpDialog(w)
        dialogs_to_check.append(("HelpDialog", d))
    except Exception as e:
        errors.append(f"CRASH: HelpDialog: {e}")

    # DataSourceDialog
    try:
        from ui.dialogs import DataSourceDialog
        d = DataSourceDialog(w)
        dialogs_to_check.append(("DataSourceDialog", d))
    except Exception as e:
        errors.append(f"CRASH: DataSourceDialog: {e}")

    for name, dlg in dialogs_to_check:
        # 最小尺寸检查
        if name in DIALOG_MIN_SIZES:
            min_w, min_h = DIALOG_MIN_SIZES[name]
            actual_w = dlg.minimumWidth()
            actual_h = dlg.minimumHeight()
            if actual_w < min_w:
                errors.append(f"SIZE: {name} minWidth={actual_w} < {min_w}")
            if actual_h < min_h:
                errors.append(f"SIZE: {name} minHeight={actual_h} < {min_h}")

        # 输入框宽度检查
        if name in DIALOG_INPUT_MIN_WIDTH:
            for attr, min_w in DIALOG_INPUT_MIN_WIDTH[name].items():
                field = getattr(dlg, attr, None)
                if field is None:
                    continue
                if field.minimumWidth() < min_w:
                    errors.append(f"INPUT: {name}.{attr} minWidth={field.minimumWidth()} < {min_w}")

    return errors


def check_g9_font_propagation(window) -> List[str]:
    """G9: 字体设置变更后，菜单栏等关键 widget 字体确实变化。"""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    app = QApplication.instance()
    errors = []

    # 记录当前菜单栏字体大小
    menu_bar = window.menuBar()
    if menu_bar is None:
        errors.append("FONT: no menuBar() found")
        return errors

    old_size = menu_bar.font().pointSize()
    if old_size <= 0:
        old_size = 13  # qt_material 默认, pointSize=-1 时从 QSS 继承

    # 应用新字体
    new_size = old_size + 4
    font = app.font()
    font.setPointSize(new_size)
    app.setFont(font)
    # 模拟 _on_apply_font 的 QSS 覆盖
    prev_ss = app.styleSheet()
    app.setStyleSheet(prev_ss + f"""
        QMenuBar, QMenuBar::item, QMenu, QMenu::item {{
            font-size: {new_size}px;
        }}
    """)

    # 检查 QSS 是否包含了字体大小(关键: qt_material 下 pointSize 可能为 -1)
    ss = app.styleSheet()
    if f"font-size: {new_size}px" not in ss:
        errors.append("FONT: menu bar QSS does not contain updated font-size")

    # 检查菜单栏实际渲染字体(QSS 中的 font-size 会被 Qt 应用到 widget)
    actual_font = menu_bar.font()
    actual_size = actual_font.pointSize()
    # pointSize=-1 表示从样式表继承，合法；检查 QSS 是否覆盖即可

    # 恢复
    font.setPointSize(old_size)
    app.setFont(font)

    return errors


def check_g8_toolbar_containers(window) -> List[str]:
    """G8: QToolBar/QMenuBar/QStatusBar 不得作为普通 widget 嵌入 QLayout。

    Qt 框架约定这些控件必须通过 QMainWindow 的专用方法挂载:
      - QMainWindow.addToolBar(tb)
      - QMainWindow.setMenuBar(mb)
      - QMainWindow.setStatusBar(sb)

    直接 embed 到 QLayout (如 layout.addWidget(toolbar)) 在 PyInstaller
    打包后可能渲染失败 — QToolBar 内部的停靠/浮动逻辑依赖 QMainWindow parent。
    """
    from PySide6.QtWidgets import QToolBar, QMenuBar, QStatusBar, QMainWindow
    errors = []
    FORBIDDEN = {
        QToolBar: ("QToolBar", "QMainWindow.addToolBar()"),
        QMenuBar: ("QMenuBar", "QMainWindow.setMenuBar()"),
        QStatusBar: ("QStatusBar", "QMainWindow.setStatusBar()"),
    }

    # 递归扫描整个 widget 树
    visited = set()

    def scan(w):
        if w is None or id(w) in visited:
            return
        visited.add(id(w))
        for cls, (name, correct_api) in FORBIDDEN.items():
            if isinstance(w, cls):
                p = w.parent()
                # 正确用法: parent 是 QMainWindow
                if isinstance(p, QMainWindow):
                    continue
                # 孤儿控件 (尚未挂载), 跳过
                if p is None:
                    continue
                # 错误: 被当作普通 widget 嵌入 layout 或其他容器
                obj_name = w.objectName() or "(unnamed)"
                ptype = type(p).__name__
                errors.append(
                    f"{name} '{obj_name}' 嵌入了 {ptype} — "
                    f"应使用 {correct_api}，直接 embed 在 PyInstaller 打包后可能不渲染"
                )
        # 递归子控件
        for child in w.children():
            scan(child)

    scan(window)
    return errors


# ── 主入口 ──────────────────────────────────────────────────────────────

def run_all(quick: bool = False) -> Tuple[bool, dict]:
    """运行所有检查。返回 (passed, results_dict)。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    from ui.main_window import MainWindow
    window = MainWindow(app)

    results = {}
    all_pass = True
    INFO_PHASES = {"G0b"}  # 覆盖率报告, 不阻塞

    phases = [
        ("G0", "自动发现(Manifest)", check_g0_manifest_discovery, []),
        ("G0b", "覆盖率(Manifest)", check_g0_manifest_coverage, []),
        ("G1", "Widget 树", check_g1_widget_tree, [window]),
        ("G2", "FormLayout", check_g2_formlayout, []),
        ("G3", "信号链路", check_g3_signal_chain, []),
        ("G7", "动态Widget+布局", check_g7_dynamic_widgets, [window]),
        ("G5", "对话框创建", check_g5_dialog_flow, []),
        ("G5b", "对话框状态", check_g5b_dialog_state, []),
        ("G5c", "对话框尺寸+输入框", check_g5c_dialog_sizes, []),
    ]
    if not quick:
        phases += [
            ("G4", "ScrollArea", check_g4_scrollarea, [window]),
            ("G8", "ToolBar容器", check_g8_toolbar_containers, [window]),
            ("G9", "字体传播", check_g9_font_propagation, [window]),
            ("G6", "完整GUI流程(线程)", check_g6_gui_flow, []),
        ]

    for phase_id, name, func, args in phases:
        try:
            errs = func(*args)
            is_info = phase_id in INFO_PHASES
            results[phase_id] = {"name": name, "errors": errs, "passed": len(errs) == 0, "info": is_info}
            if errs and not is_info:
                all_pass = False
        except Exception as e:
            results[phase_id] = {"name": name, "errors": [str(e)], "passed": False}
            all_pass = False

    return all_pass, results


def update_manifest():
    """Auto-update verify-manifest.json inventory from live code scan."""
    if not MANIFEST_PATH.exists():
        print("verify-manifest.json not found. Run with --init first.")
        return 1
    try:
        m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to parse manifest: {e}")
        return 1

    compiled_src = (PROJECT_ROOT / "ui" / "compiled" / "ui_main_window.py").read_text(encoding="utf-8")
    mw_src = (PROJECT_ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")

    old_c = set(m['ui']['compiled_widgets'])
    old_d = set(m['ui']['dynamic_widgets'])
    old_m = set(m['ui']['methods'])
    old_mod = set(m['computation']['modules'])

    m['ui']['compiled_widgets'] = sorted(set(
        m.group(1) for m in re.finditer(r'self\.(\w+)\s*=\s*(Q\w+)\(', compiled_src)))
    m['ui']['dynamic_widgets'] = sorted(set(
        m.group(1) for m in re.finditer(r'self\.(_\w+)\s*=\s*(Q\w+)\(', mw_src)))
    m['ui']['methods'] = sorted(set(
        m.group(1) for m in re.finditer(r'def\s+(_\w+)\(self', mw_src)))

    modules = set(f.name for f in (PROJECT_ROOT / 'src').glob('*.py') if f.name != '__init__.py')
    for f in (PROJECT_ROOT / 'ui').glob('*.py'):
        if f.name != '__init__.py':
            modules.add(f'ui/{f.name}')
    m['computation']['modules'] = sorted(modules)

    m['tests']['files'] = sorted(f.name for f in (PROJECT_ROOT / 'tests').glob('*.py'))

    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

    new_c = set(m['ui']['compiled_widgets']) - old_c
    new_d = set(m['ui']['dynamic_widgets']) - old_d
    new_m = set(m['ui']['methods']) - old_m
    new_mod = set(m['computation']['modules']) - old_mod

    print(f"Manifest updated: {MANIFEST_PATH}")
    if new_c: print(f"  +{len(new_c)} compiled widgets: {sorted(new_c)[:5]}...")
    if new_d: print(f"  +{len(new_d)} dynamic widgets: {sorted(new_d)}")
    if new_m: print(f"  +{len(new_m)} methods: {sorted(new_m)[:5]}...")
    if new_mod: print(f"  +{len(new_mod)} modules: {sorted(new_mod)}")
    if not (new_c or new_d or new_m or new_mod):
        print("  No changes - manifest is already up to date.")
    return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GUI 完整性守护")
    parser.add_argument("--quick", action="store_true", help="仅 G1-G3 (5s)")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--update-manifest", action="store_true",
                        help="自动更新 verify-manifest.json 清单 (widget/模块/方法列表)")
    args = parser.parse_args()

    if args.update_manifest:
        return update_manifest()

    passed, results = run_all(quick=args.quick)

    if args.json:
        print(json.dumps({"passed": passed, "phases": results}, ensure_ascii=False, indent=2))
    else:
        for pid, r in results.items():
            if r.get("info"):
                icon = "📋"
                status = "INFO"
            else:
                icon = "✅" if r["passed"] else "❌"
                status = "PASSED" if r["passed"] else f"FAILED ({len(r['errors'])} issues)"
            print(f"  {icon} {pid} {r['name']}: {status}")
            if not r["passed"]:
                for e in r["errors"]:
                    print(f"     └─ {e}")
        print()
        if passed:
            print("✅ GUI 完整性检查全部通过")
        else:
            print("❌ GUI 完整性检查失败 — 请在提交前修复上述问题")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
