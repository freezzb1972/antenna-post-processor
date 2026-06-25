"""
RSP 预设选择对话框
===================
工具入口点使用此对话框选择 RSP 校准预设，
替代原始 QFileDialog 逐文件浏览的方式。

支持:
  - 按测试模式筛选预设列表
  - 显示选中预设的详情
  - 手动浏览文件 (回退)
  - 跳过 (不应用 RSP 校准)
  - 自动选择: 仅有一个匹配预设时自动使用

用法:
    from ui.rsp_picker_dialog import RspPickerDialog
    h_path, v_path = RspPickerDialog.pick(parent, test_mode=0)
"""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QVBoxLayout,
)

from src.rsp_preset_manager import MODE_ANY, RspPreset, RspPresetManager


class RspPickerDialog(QDialog):
    """选择或浏览 RSP 校准预设。"""

    def __init__(self, parent, test_mode: int = MODE_ANY):
        super().__init__(parent)
        self._test_mode = test_mode
        self._result_h: str = ""
        self._result_v: str = ""

        self.setWindowTitle("选择 RSP 校准预设")
        self.setMinimumWidth(480)
        self._setup_ui()
        self._load_presets()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 预设选择 ──
        preset_grp = QGroupBox("预设 RSP 校准")
        preset_layout = QFormLayout(preset_grp)
        preset_layout.setSpacing(6)

        self._cmb_preset = QComboBox()
        self._cmb_preset.setMinimumWidth(350)
        self._cmb_preset.currentIndexChanged.connect(self._on_preset_selected)
        preset_layout.addRow("选择预设:", self._cmb_preset)

        self._lbl_h_path = QLabel("")
        self._lbl_h_path.setWordWrap(True)
        self._lbl_h_path.setStyleSheet("color: #666;")
        preset_layout.addRow("H-pol:", self._lbl_h_path)

        self._lbl_v_path = QLabel("")
        self._lbl_v_path.setWordWrap(True)
        self._lbl_v_path.setStyleSheet("color: #666;")
        preset_layout.addRow("V-pol:", self._lbl_v_path)

        self._lbl_desc = QLabel("")
        self._lbl_desc.setWordWrap(True)
        self._lbl_desc.setStyleSheet("color: #888;")
        preset_layout.addRow("描述:", self._lbl_desc)

        layout.addWidget(preset_grp)

        # ── 手动浏览 ──
        browse_grp = QGroupBox("或者手动浏览文件")
        browse_layout = QFormLayout(browse_grp)
        browse_layout.setSpacing(6)

        h_row = QHBoxLayout()
        self._edit_browse_h = self._make_path_edit("选择 H-pol RSP 文件...")
        btn_browse_h = QPushButton("浏览...")
        btn_browse_h.clicked.connect(self._on_browse_h)
        h_row.addWidget(self._edit_browse_h)
        h_row.addWidget(btn_browse_h)
        browse_layout.addRow("H-pol:", h_row)

        v_row = QHBoxLayout()
        self._edit_browse_v = self._make_path_edit("选择 V-pol RSP 文件...")
        btn_browse_v = QPushButton("浏览...")
        btn_browse_v.clicked.connect(self._on_browse_v)
        v_row.addWidget(self._edit_browse_v)
        v_row.addWidget(btn_browse_v)
        browse_layout.addRow("V-pol:", v_row)

        layout.addWidget(browse_grp)

        # ── 跳过 + 确认 ──
        bottom_row = QHBoxLayout()
        btn_skip = QPushButton("跳过 — 不应用 RSP 校准")
        btn_skip.clicked.connect(self._on_skip)
        bottom_row.addWidget(btn_skip)
        bottom_row.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        bottom_row.addWidget(btns)
        layout.addLayout(bottom_row)

    @staticmethod
    def _make_path_edit(placeholder: str):
        from PySide6.QtWidgets import QLineEdit
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        return edit

    # ── 预设加载 ──

    def _load_presets(self):
        mgr = RspPresetManager()
        self._cmb_preset.addItem("-- 选择预设（或使用下方浏览）--", None)

        # 精确匹配在前
        exact = [p for p in mgr.presets if p.test_mode == self._test_mode]
        any_mode = [p for p in mgr.presets if p.test_mode == MODE_ANY and p not in exact]
        others = [p for p in mgr.presets if p not in exact and p not in any_mode]

        for preset in exact:
            self._cmb_preset.addItem(f"✓ {preset.name}", preset)
        for preset in any_mode:
            self._cmb_preset.addItem(f"  {preset.name} (通用)", preset)
        if others:
            self._cmb_preset.insertSeparator(self._cmb_preset.count())
            for preset in others:
                self._cmb_preset.addItem(f"  {preset.name}", preset)

    def _on_preset_selected(self, _index: int):
        preset: RspPreset = self._cmb_preset.currentData()
        if preset:
            self._lbl_h_path.setText(preset.rsp_h_path or "（未设置）")
            self._lbl_v_path.setText(preset.rsp_v_path or "（未设置）")
            self._lbl_desc.setText(preset.description or "—")

    # ── 浏览 ──

    def _on_browse_h(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 H-pol RSP 校准文件", "",
            "CSV/Excel 文件 (*.csv *.xlsx *.xls);;所有文件 (*)")
        if path:
            self._edit_browse_h.setText(path)

    def _on_browse_v(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 V-pol RSP 校准文件", "",
            "CSV/Excel 文件 (*.csv *.xlsx *.xls);;所有文件 (*)")
        if path:
            self._edit_browse_v.setText(path)

    # ── 确认/跳过 ──

    def _on_accept(self):
        preset: RspPreset = self._cmb_preset.currentData()
        if preset:
            self._result_h = preset.rsp_h_path
            self._result_v = preset.rsp_v_path
            self.accept()
            return

        h = self._edit_browse_h.text().strip()
        v = self._edit_browse_v.text().strip()
        if h or v:
            self._result_h = h
            self._result_v = v
            self.accept()
            return

        QMessageBox.warning(self, "提示",
            "请选择一个预设，或浏览文件，或点击「跳过」。")

    def _on_skip(self):
        self._result_h = ""
        self._result_v = ""
        self.accept()

    @property
    def result_paths(self) -> Tuple[Optional[str], Optional[str]]:
        return (self._result_h or None, self._result_v or None)

    # ── 静态便捷方法 ──

    @staticmethod
    def pick(parent, test_mode: int = MODE_ANY,
             auto_skip_if_no_presets: bool = True
             ) -> Tuple[Optional[str], Optional[str]]:
        """便捷方法：选择一个 RSP 预设。

        Args:
            parent: 父窗口。
            test_mode: 测试模式 (0/1/2/-1)。
            auto_skip_if_no_presets: 无预设时静默返回 (None, None)。

        Returns:
            (rsp_h_path, rsp_v_path) 或 (None, None)。
        """
        mgr = RspPresetManager()

        # 无预设时静默跳过
        if auto_skip_if_no_presets and not mgr.presets:
            return (None, None)

        # 有默认值时自动使用
        best = mgr.get_best_match(test_mode)
        if best and RspPickerDialog._should_auto_select(mgr, test_mode):
            return (best.rsp_h_path or None, best.rsp_v_path or None)

        dlg = RspPickerDialog(parent, test_mode=test_mode)
        if dlg.exec() == QDialog.Accepted:
            return dlg.result_paths
        return (None, None)

    @staticmethod
    def _should_auto_select(mgr: RspPresetManager, test_mode: int) -> bool:
        """是否自动选择预设而不弹对话框。"""
        # 该模式有显式默认值 → 自动使用
        if mgr.get_default(test_mode):
            return True
        # 仅有一个匹配预设 → 自动使用
        matches = mgr.get_by_test_mode(test_mode)
        if len(matches) == 1:
            return True
        return False
