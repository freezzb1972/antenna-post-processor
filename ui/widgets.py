"""
可复用 GUI 组件
==============
包含 AnglePickerWidget, TemplateSourceRow, OutputSettingsGroup 等。
"""
from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplitter, QSplitterHandle, QTableWidget,
    QVBoxLayout, QWidget,
)

from src.lag_config import LagConfig


# ═══════════════════════════════════════════════════════════════
# ThinSplitter — 1px 分割线
# ═══════════════════════════════════════════════════════════════

class ThinSplitter(QSplitter):
    """QSplitter 子类，handle 超薄但可拖拽。"""
    def createHandle(self):
        from PySide6.QtCore import Qt as _Qt
        h = QSplitterHandle(self.orientation(), self)
        # 只固定薄边，另一边自动撑满不锁死
        if self.orientation() == _Qt.Vertical:
            h.setFixedHeight(3)   # 水平分割条: 高 3px, 宽撑满
        else:
            h.setFixedWidth(3)    # 垂直分割条: 宽 3px, 高撑满
        return h


# ═══════════════════════════════════════════════════════════════
# AnglePickerWidget — 角度选择组件（Gain/LAG/AR 共用）
# ═══════════════════════════════════════════════════════════════

class AnglePickerWidget(QWidget):
    """角度选择组件：快捷角度 + 步进生成 + 范围添加 + 已配置项显示。

    信号:
        angle_changed(LagConfig) — 任何角度变更时发出
    """

    angle_changed = Signal(LagConfig)

    COMMON_ANGLES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
    DEFAULT_SINGLES = [60, 70, 80, 90]
    DEFAULT_RANGES = [(0, 90), (60, 90)]

    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self._config = LagConfig(
            single_angles=list(self.DEFAULT_SINGLES),
            ranges=list(self.DEFAULT_RANGES),
        )
        self._label = label
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel(self._label)
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        # ── 快捷单角度 ──
        quick_label = QLabel(self.tr("快捷单角度（点击切换）"))
        quick_label.setStyleSheet("font-size: 0.9em; color: #888;")
        layout.addWidget(quick_label)

        self._quick_btns: Dict[float, QPushButton] = {}
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        for angle in self.COMMON_ANGLES:
            btn = QPushButton(f"{angle}°")
            btn.setFixedWidth(42)
            btn.setCheckable(True)
            btn.setChecked(angle in self._config.single_angles)
            btn.clicked.connect(lambda checked, a=angle: self._toggle_single(a, checked))
            self._quick_btns[angle] = btn
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── 步进批量生成 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        step_label = QLabel(self.tr("步进批量生成"))
        step_label.setStyleSheet("font-size: 0.9em; color: #888;")
        layout.addWidget(step_label)

        step_row = QHBoxLayout()
        step_row.setSpacing(6)
        step_row.addWidget(QLabel(self.tr("起始:")))
        self._spin_gen_start = QSpinBox()
        self._spin_gen_start.setRange(0, 180)
        self._spin_gen_start.setValue(0)
        step_row.addWidget(self._spin_gen_start)
        step_row.addWidget(QLabel(self.tr("结束:")))
        self._spin_gen_end = QSpinBox()
        self._spin_gen_end.setRange(0, 180)
        self._spin_gen_end.setValue(90)
        step_row.addWidget(self._spin_gen_end)
        step_row.addWidget(QLabel(self.tr("步进:")))
        self._spin_gen_step = QSpinBox()
        self._spin_gen_step.setRange(1, 45)
        self._spin_gen_step.setValue(10)
        step_row.addWidget(self._spin_gen_step)
        btn_gen = QPushButton(self.tr("生成 >>"))
        btn_gen.clicked.connect(self._on_generate)
        step_row.addWidget(btn_gen)
        step_row.addStretch()
        layout.addLayout(step_row)

        # ── 范围添加 ──
        range_label = QLabel(self.tr("添加角度范围"))
        range_label.setStyleSheet("font-size: 0.9em; color: #888;")
        layout.addWidget(range_label)

        range_row = QHBoxLayout()
        range_row.setSpacing(6)
        range_row.addWidget(QLabel(self.tr("起始:")))
        self._spin_range_start = QSpinBox()
        self._spin_range_start.setRange(0, 180)
        self._spin_range_start.setValue(0)
        range_row.addWidget(self._spin_range_start)
        range_row.addWidget(QLabel(self.tr("结束:")))
        self._spin_range_end = QSpinBox()
        self._spin_range_end.setRange(0, 180)
        self._spin_range_end.setValue(90)
        range_row.addWidget(self._spin_range_end)
        btn_add = QPushButton(self.tr("添加范围"))
        btn_add.clicked.connect(self._on_add_range)
        range_row.addWidget(btn_add)
        range_row.addStretch()
        layout.addLayout(range_row)

        # ── 已配置项显示 ──
        self._lbl_configured = QLabel("")
        self._lbl_configured.setStyleSheet("color: #666; font-size: 0.9em;")
        self._update_configured_label()
        layout.addWidget(self._lbl_configured)

    def _toggle_single(self, angle: float, checked: bool):
        """切换单角度。"""
        angles = list(self._config.single_angles)
        if checked and angle not in angles:
            angles.append(angle)
            angles.sort()
        elif not checked and angle in angles:
            angles.remove(angle)
        self._config.single_angles = angles
        self._sync_quick_buttons()
        self._update_configured_label()
        self.angle_changed.emit(self._config)

    def _sync_quick_buttons(self):
        """同步快捷按钮的勾选状态。"""
        for angle, btn in self._quick_btns.items():
            btn.blockSignals(True)
            btn.setChecked(angle in self._config.single_angles)
            btn.blockSignals(False)

    def _on_generate(self):
        """步进批量生成。"""
        start = self._spin_gen_start.value()
        end = self._spin_gen_end.value()
        step = self._spin_gen_step.value()
        gen = LagConfig.generate_singles(start, end, step)
        self._config.add_singles(gen)
        self._sync_quick_buttons()
        self._update_configured_label()
        self.angle_changed.emit(self._config)

    def _on_add_range(self):
        """添加角度范围。"""
        lo = self._spin_range_start.value()
        hi = self._spin_range_end.value()
        if lo < hi:
            self._config.add_range(lo, hi)
            self._update_configured_label()
            self.angle_changed.emit(self._config)

    def _update_configured_label(self):
        """更新已配置项标签。"""
        singles = self._config.singles_sorted
        ranges = self._config.ranges_sorted
        parts = []
        if singles:
            parts.append(f"{self.tr('单角度')}: {', '.join(f'{a}°' for a in singles[:10])}"
                         f"{'...' if len(singles) > 10 else ''}")
        if ranges:
            parts.append(f"{self.tr('范围')}: {', '.join(f'({lo}°-{hi}°)' for lo, hi in ranges)}")
        self._lbl_configured.setText(" | ".join(parts) if parts else self.tr("(未配置)"))

    # ── 外部接口 ──

    def get_config(self) -> LagConfig:
        return self._config

    def set_config(self, config: LagConfig):
        """外部设置角度配置（不触发 signal）。"""
        self._config = LagConfig(
            single_angles=list(config.single_angles),
            ranges=list(config.ranges),
        )
        self._sync_quick_buttons()
        self._update_configured_label()

    def reset_to_defaults(self):
        """重置为默认角度。"""
        self._config = LagConfig(
            single_angles=list(self.DEFAULT_SINGLES),
            ranges=list(self.DEFAULT_RANGES),
        )
        self._sync_quick_buttons()
        self._update_configured_label()
        self.angle_changed.emit(self._config)


# ═══════════════════════════════════════════════════════════════
# TemplateSourceRow — 模板来源选择
# ═══════════════════════════════════════════════════════════════

class TemplateSourceRow(QWidget):
    """模板来源选择行：内置模板 ▾ | 从电脑选择... | 📋 预览报告。

    信号:
        template_changed(str) — 模板路径变化时发出
    """

    template_changed = Signal(str)
    template_pair_changed = Signal(str, str)

    def __init__(self, parent=None, on_browse=None, on_preview=None):
        super().__init__(parent)
        self._on_browse_cb = on_browse
        self._on_preview_cb = on_preview
        self._path: str = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # 单一下拉: 厂商为分组标题(不可选), 模板为缩进子项
        self._cmb_tpl = QComboBox()
        self._cmb_tpl.setEditable(True)
        self._cmb_tpl.setInsertPolicy(QComboBox.NoInsert)
        self._cmb_tpl.lineEdit().setPlaceholderText(self.tr("模板..."))
        self._cmb_tpl.setMinimumWidth(220)
        self._cmb_tpl.currentIndexChanged.connect(self._on_tpl_selected)
        layout.addWidget(self._cmb_tpl)

        btn_browse = QPushButton(self.tr("从电脑选择..."))
        btn_browse.clicked.connect(self._on_browse_cb if self._on_browse_cb else self._on_browse)
        layout.addWidget(btn_browse)

        btn_preview = QPushButton(self.tr("📋 预览报告"))
        btn_preview.clicked.connect(self._on_preview_cb if self._on_preview_cb else self._on_preview)
        layout.addWidget(btn_preview)
        layout.addStretch()

    def set_path(self, path: str):
        """手动设置模板路径（非预设选择时使用, 不触发信号以避免递归）。"""
        self._path = path
        self._cmb_tpl.blockSignals(True)
        self._cmb_tpl.setCurrentIndex(0)
        self._cmb_tpl.blockSignals(False)

    def get_path(self) -> str:
        """返回当前模板路径。"""
        return self._path

    def populate_presets(self, presets: List[dict]):
        """填充单一下拉: 厂商为分组标题(不可选), 模板为缩进子项。"""
        self._all_presets = presets
        self._cmb_tpl.blockSignals(True)
        self._cmb_tpl.clear()
        self._cmb_tpl.addItem("", "")  # 空项
        mfrs = sorted(set(p.get('manufacturer', '') for p in presets if p.get('manufacturer')))
        for mfr in mfrs:
            # 厂商标题 (不可选, 用 icon 或纯文本标记)
            self._cmb_tpl.insertSeparator(self._cmb_tpl.count())
            self._cmb_tpl.addItem(f"— {mfr} —")
            # 标记为不可选: 通过 model 设置
            idx = self._cmb_tpl.count() - 1
            self._cmb_tpl.model().item(idx).setEnabled(False)
            mfr_presets = [p for p in presets if p.get('manufacturer', '') == mfr]
            for p in mfr_presets:
                label = p.get('name', '')
                self._cmb_tpl.addItem(f"    {label}", json.dumps({
                    "excel": p.get("path", ""),
                    "word": p.get("word_template_path", ""),
                }))
        self._cmb_tpl.blockSignals(False)

    def _on_tpl_selected(self, idx: int):
        data = self._cmb_tpl.currentData()
        if not data:
            return  # 空项或厂商标题
        try:
            d = json.loads(data)
            excel = d.get("excel", ""); word = d.get("word", "")
        except Exception:
            return
        self._path = excel
        self.template_changed.emit(excel)
        if word:
            self.template_pair_changed.emit(excel, word)

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择模板文件"), "",
            self.tr("所有支持格式 (*.xlsx *.xls *.docx *.doc);;Excel (*.xlsx *.xls);;Word (*.docx *.doc);;所有文件 (*)"))
        if path:
            self._path = path
            self.template_changed.emit(path)

    def _on_preview(self):
        """打开报告预览。"""
        path = self._path
        if not path or not os.path.exists(path):
            return
        from src.column_mapping import detect_columns_from_template, get_col_type_labels
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QComboBox, QHeaderView, QPushButton, QMessageBox

        mappings = detect_columns_from_template(path)
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("报告预览 — 列头检测结果"))
        dlg.setMinimumSize(600, 400)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowMaximizeButtonHint)
        dl = QVBoxLayout(dlg)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels([self.tr("列"), self.tr("列头"), self.tr("类型")])
        table.horizontalHeader().setStretchLastSection(True)
        table.setRowCount(len(mappings))
        for ri, m in enumerate(mappings):
            table.setItem(ri, 0, QTableWidgetItem(m.col_letter))
            table.setItem(ri, 1, QTableWidgetItem(m.raw_header))
            cmb = QComboBox()
            for ct, label in get_col_type_labels(0):
                cmb.addItem(label, ct)
            idx = cmb.findData(m.detected_type)
            if idx >= 0:
                cmb.setCurrentIndex(idx)
            table.setCellWidget(ri, 2, cmb)
        dl.addWidget(table)
        btn_close = QPushButton(self.tr("关闭"))
        btn_close.clicked.connect(dlg.accept)
        dl.addWidget(btn_close)
        dlg.exec()


# ═══════════════════════════════════════════════════════════════
# OutputSettingsGroup — 输出设置组
# ═══════════════════════════════════════════════════════════════

class OutputSettingsGroup(QGroupBox):
    """输出目录 + 文件名 + 完整报告路径。"""

    output_changed = Signal(str, str)  # (output_dir, output_name)

    def __init__(self, parent=None, output_dir="", output_name="antenna_report.xlsx",
                 on_browse_output=None, on_browse_full_report=None):
        super().__init__(parent)
        self.setTitle(self.tr("输出设置"))
        self._on_browse_output_cb = on_browse_output
        self._on_browse_full_report_cb = on_browse_full_report
        self._setup_ui(output_dir, output_name)

    def _setup_ui(self, output_dir="", output_name="antenna_report.xlsx"):
        layout = QFormLayout(self)
        layout.setSpacing(6)

        # 输出目录
        dir_row = QHBoxLayout()
        self._edit_dir = QLineEdit(output_dir)
        self._edit_dir.setPlaceholderText(self.tr("默认: ./output"))
        dir_row.addWidget(self._edit_dir, 1)
        btn_dir = QPushButton(self.tr("浏览..."))
        if self._on_browse_output_cb:
            btn_dir.clicked.connect(self._on_browse_output_cb)
        else:
            btn_dir.clicked.connect(self._on_browse_dir)
        dir_row.addWidget(btn_dir)
        layout.addRow(self.tr("输出目录:"), dir_row)

        # 文件名
        self._edit_name = QLineEdit(output_name)
        layout.addRow(self.tr("文件名:"), self._edit_name)

        # 完整报告
        report_row = QHBoxLayout()
        self._chk_full_report = QCheckBox(self.tr("生成完整报告（独立文件，含全部指标 + 2D/3D 图）"))
        report_row.addWidget(self._chk_full_report)
        layout.addRow(report_row)

        self._edit_report_path = QLineEdit()
        self._edit_report_path.setPlaceholderText(self.tr("默认: ./output/full_report.xlsx"))
        self._chk_full_report.toggled.connect(self._edit_report_path.setVisible)
        self._edit_report_path.setVisible(False)
        layout.addRow(self.tr("报告路径:"), self._edit_report_path)

        # 信号连接
        self._edit_dir.textChanged.connect(self._emit_changed)
        self._edit_name.textChanged.connect(self._emit_changed)

    def get_directory(self) -> str:
        return self._edit_dir.text().strip()

    def get_filename(self) -> str:
        return self._edit_name.text().strip()

    def get_report_path(self) -> str:
        return self._edit_report_path.text().strip()

    def set_directory(self, path: str):
        self._edit_dir.blockSignals(True)
        self._edit_dir.setText(path)
        self._edit_dir.blockSignals(False)

    def set_filename(self, name: str):
        self._edit_name.blockSignals(True)
        self._edit_name.setText(name)
        self._edit_name.blockSignals(False)

    def is_full_report_enabled(self) -> bool:
        return self._chk_full_report.isChecked()

    def _on_browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("选择输出目录"))
        if d:
            self._edit_dir.setText(d)

    def _emit_changed(self):
        self.output_changed.emit(self.get_directory(), self.get_filename())


class DataFileSelector(QGroupBox):
    """数据文件选择器: 按钮行 + 文件列表 + 工作表匹配表 + 命名/图表选项。

    所有子控件作为公开属性暴露, 由父页面连接信号/填充数据。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle(self.tr("数据文件"))
        self.setStyleSheet("QGroupBox { padding-top: 4px; padding-bottom: 1px; margin-top: 14px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)

        # 按钮行
        btn_row = QHBoxLayout()
        self.btn_add_files = QPushButton(self.tr("📂 添加数据文件..."))
        self.btn_add_files.setToolTip(self.tr("选择多个数据文件 (Ctrl+点击多选 / 拖拽)"))
        self.btn_clear_selected = QPushButton(self.tr("清除选中"))
        self.btn_clear_all = QPushButton(self.tr("全部清除"))
        btn_row.addWidget(self.btn_add_files)
        btn_row.addWidget(self.btn_clear_selected)
        btn_row.addWidget(self.btn_clear_all)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 文件列表
        self.file_list_widget = QTableWidget()
        self.file_list_widget.setColumnCount(3)
        self.file_list_widget.setHorizontalHeaderLabels([
            self.tr("数据源文件"), self.tr("天线名称"), self.tr("测试模式")
        ])
        self.file_list_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_list_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.file_list_widget.setColumnWidth(1, 120)
        self.file_list_widget.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.file_list_widget.setColumnWidth(2, 120)
        self.file_list_widget.verticalHeader().setDefaultSectionSize(22)
        self.file_list_widget.verticalHeader().setVisible(False)
        self.file_list_widget.setMinimumHeight(80)
        self.file_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.file_list_widget.setAlternatingRowColors(True)
        self.file_list_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.file_list_widget, 1)  # stretch=1, 占满空间

        # 自动匹配按钮行 (底部)
        match_row = QHBoxLayout()
        self.btn_auto_match = QPushButton(self.tr("🔗 自动匹配"))
        self.btn_auto_match.setToolTip(self.tr("按文件命名自动匹配工作表"))
        self.lbl_match_status = QLabel("")
        self.lbl_match_status.setMinimumHeight(22)
        self.lbl_match_status.setStyleSheet("padding: 2px 0;")
        match_row.addWidget(self.btn_auto_match)
        match_row.addWidget(self.lbl_match_status)
        match_row.addSpacing(12)
        self.lbl_naming_mode = QLabel(self.tr("工作表命名:"))
        match_row.addWidget(self.lbl_naming_mode)
        self.cmb_naming_mode = QComboBox()
        self.cmb_naming_mode.addItem(self.tr("用数据源名替换"), 1)
        self.cmb_naming_mode.addItem(self.tr("保留原模板工作表名"), 0)
        self.cmb_naming_mode.setToolTip(self.tr("多数据源时，选择工作表命名方式"))
        self.cmb_naming_mode.setFixedWidth(190)
        match_row.addWidget(self.cmb_naming_mode)
        match_row.addStretch()
        layout.addLayout(match_row)


# ═══════════════════════════════════════════════════════════════
# FrequencyPickerWidget — 频点批量选择组件
# ═══════════════════════════════════════════════════════════════

class FrequencyPickerWidget(QWidget):
    """频点批量选择: 全选/清除/范围 + checkbox 网格 + 计数。

    用法:
        picker = FrequencyPickerWidget()
        picker.set_frequencies([698.0, 824.0, 960.0, ...])
        selected = picker.get_selected()
    """

    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._freqs: list[float] = []
        self._checks: dict[float, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── 操作按钮行 ──
        btn_row = QHBoxLayout()
        btn_all = QPushButton("全选")
        btn_all.clicked.connect(self._select_all)
        btn_row.addWidget(btn_all)
        btn_clear = QPushButton("清除")
        btn_clear.clicked.connect(self._clear_all)
        btn_row.addWidget(btn_clear)
        btn_range = QPushButton("范围选择...")
        btn_range.clicked.connect(self._show_range_dialog)
        btn_row.addWidget(btn_range)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── checkbox 区域 (scrollable) ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setMaximumHeight(200)
        self._check_container = QWidget()
        self._check_layout = QVBoxLayout(self._check_container)
        self._check_layout.setSpacing(1)
        self._check_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._check_container)
        layout.addWidget(scroll)

        # ── 计数 ──
        self._lbl_count = QLabel("已选: 0 / 0")
        self._lbl_count.setStyleSheet("color: #888; font-size: 9pt;")
        layout.addWidget(self._lbl_count)

    # ── 公共 API ──

    def set_frequencies(self, freqs: list[float]):
        """设置可选频点列表（覆盖旧数据）。"""
        self._freqs = sorted(set(freqs))
        self._checks.clear()
        # 清空旧 checkbox
        while self._check_layout.count():
            item = self._check_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # 创建新 checkbox（每行 4 个，使用嵌套 HBoxLayout）
        row_layout = None
        for i, f in enumerate(self._freqs):
            if i % 5 == 0:
                row_layout = QHBoxLayout()
                row_layout.setSpacing(4)
                self._check_layout.addLayout(row_layout)
            cb = QCheckBox(f"{f:.1f}")
            cb.setChecked(True)
            cb.toggled.connect(self._update_count)
            self._checks[f] = cb
            row_layout.addWidget(cb)
        self._check_layout.addStretch()
        self._update_count()

    def get_selected(self) -> list[float]:
        """返回选中的频点列表（排序）。"""
        return sorted(f for f, cb in self._checks.items() if cb.isChecked())

    def set_selected(self, freqs: list[float]):
        """设置哪些频点被选中。"""
        target = set(freqs)
        for f, cb in self._checks.items():
            cb.setChecked(f in target)
        self._update_count()

    # ── 内部 ──

    def _select_all(self):
        for cb in self._checks.values():
            cb.setChecked(True)
        self._update_count()

    def _clear_all(self):
        for cb in self._checks.values():
            cb.setChecked(False)
        self._update_count()

    def _show_range_dialog(self):
        """弹出范围选择对话框：起始 MHz ~ 结束 MHz。"""
        if not self._freqs:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("频点范围选择")
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        spin_lo = QDoubleSpinBox()
        spin_lo.setRange(min(self._freqs), max(self._freqs))
        spin_lo.setValue(min(self._freqs))
        spin_lo.setDecimals(1)
        spin_lo.setSuffix(" MHz")
        form.addRow("起始频率:", spin_lo)
        spin_hi = QDoubleSpinBox()
        spin_hi.setRange(min(self._freqs), max(self._freqs))
        spin_hi.setValue(max(self._freqs))
        spin_hi.setDecimals(1)
        spin_hi.setSuffix(" MHz")
        form.addRow("结束频率:", spin_hi)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            [cb.setChecked(spin_lo.value() <= f <= spin_hi.value())
             for f, cb in self._checks.items()],
            self._update_count(),
            dlg.accept()))
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    def _update_count(self):
        sel = sum(1 for cb in self._checks.values() if cb.isChecked())
        total = len(self._checks)
        self._lbl_count.setText(f"已选: {sel} / {total}")
        self.selection_changed.emit()
