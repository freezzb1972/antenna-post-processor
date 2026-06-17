#!/usr/bin/env python3
"""
GUI 完整性守护 (Harness G1-G5)
===============================
每次修改 ui/main_window.py 或 ui/compiled/*.py 后运行。
验证 widget 树、FormLayout、信号链路、ScrollArea、线程启动。

用法:
    python3 gui_integrity_check.py          # 完整检查
    python3 gui_integrity_check.py --quick  # 仅 G1-G3 (5s)
    python3 gui_integrity_check.py --json   # JSON 输出（CI 集成）
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
    "btnStart", "btnStop", "progressBar", "logOutput",
]

# G1: 必须隐藏的 widget
REQUIRED_HIDDEN = [
    "editCsvPath", "btnBrowseCsv", "lblCsv",
]

# G1: 最小尺寸要求 (widget_attr, min_w, min_h)
MIN_SIZE_REQUIREMENTS = [
    ("editOutputName", 180, 0),
    ("editOutputDir", 180, 0),
    ("editFullReportPath", 180, 0),
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


# ── 检查函数 ────────────────────────────────────────────────────────────

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
            if "LabelRole" not in roles:
                errors.append(f"FormLayout {form_name} row {row}: missing LabelRole")
            if "FieldRole" not in roles and row not in _SKIP_FIELDROLE_ROWS.get(form_name, []):
                errors.append(f"FormLayout {form_name} row {row}: missing FieldRole")

    return errors


# formOutput row 2 只有 LabelRole (checkFullReport 复选框) — 合法
_SKIP_FIELDROLE_ROWS = {
    "self.formOutput": [2],
}


def check_g3_signal_chain() -> List[str]:
    """G3: 信号连接链路完整性。"""
    main_win = PROJECT_ROOT / "ui" / "main_window.py"
    src = _read_source(main_win)
    errors = []

    # 1. btnStart → _on_start
    if "self.ui.btnStart.clicked.connect(self._on_start)" not in src:
        errors.append("SIGNAL: btnStart.clicked not connected to _on_start")

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
    """G5b: 对话框 widget 状态验证 — 复选框启用、路径完整。"""
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

    # 计算参数对话框 — 复选框状态验证
    from ui.dialogs import CalcParamsDialog
    d2 = CalcParamsDialog(w)
    if not hasattr(d2, '_param_checkboxes'):
        errors.append("CalcParamsDialog: _param_checkboxes not found")
    else:
        for key, cb in d2._param_checkboxes.items():
            if not cb.isEnabled():
                errors.append(f"CalcParamsDialog: checkbox '{key}' is DISABLED")
            if not cb.isChecked():
                errors.append(f"CalcParamsDialog: checkbox '{key}' is UNCHECKED")

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

    # 验证线程启动
    if not w._running:
        errors.append("G6_FLOW: _running=False — 线程未启动")
    if w._thread is None:
        errors.append("G6_FLOW: _thread=None — 未创建线程")
    elif not w._thread.isRunning():
        errors.append("G6_FLOW: thread.isRunning()=False — 线程未run")

    # 验证管线确实跑了数据
    if w._thread and w._thread.isRunning():
        w._thread.wait(10000)  # 等最多10秒

    # 清理
    if w._thread and w._thread.isRunning():
        w._on_stop()
        w._thread.quit()
        w._thread.wait(3000)

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

    phases = [
        ("G1", "Widget 树", check_g1_widget_tree, [window]),
        ("G2", "FormLayout", check_g2_formlayout, []),
        ("G3", "信号链路", check_g3_signal_chain, []),
        ("G5", "对话框创建", check_g5_dialog_flow, []),
        ("G5b", "对话框状态", check_g5b_dialog_state, []),
    ]
    if not quick:
        phases += [
            ("G4", "ScrollArea", check_g4_scrollarea, [window]),
            ("G6", "完整GUI流程(线程)", check_g6_gui_flow, []),
        ]

    for phase_id, name, func, args in phases:
        try:
            errs = func(*args)
            results[phase_id] = {"name": name, "errors": errs, "passed": len(errs) == 0}
            if errs:
                all_pass = False
        except Exception as e:
            results[phase_id] = {"name": name, "errors": [str(e)], "passed": False}
            all_pass = False

    return all_pass, results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GUI 完整性守护")
    parser.add_argument("--quick", action="store_true", help="仅 G1-G3 (5s)")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    passed, results = run_all(quick=args.quick)

    if args.json:
        print(json.dumps({"passed": passed, "phases": results}, ensure_ascii=False, indent=2))
    else:
        for pid, r in results.items():
            icon = "✅" if r["passed"] else "❌"
            print(f"  {icon} {pid} {r['name']}: ", end="")
            if r["passed"]:
                print("PASSED")
            else:
                print(f"FAILED ({len(r['errors'])} issues)")
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
