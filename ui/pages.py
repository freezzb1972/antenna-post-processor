"""
独立页面组件
============
Master-Detail 布局的 3 个右侧页面：

  - FileSettingsPage    (输入输出 — 模板/数据/输出)
  - AntennaParamsPage   (天线参数 — 模式/参数/角度/算法)
  - ChartSettingsPage   (图表配置 — 分类/视角/输出)

设计原则：
  每个 Page 直接读写 MainWindow 属性（self._mw.xxx），
  MainWindow 是唯一数据源。
  无 parent 时可独立实例化显示（字段显示默认值）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QVBoxLayout,
    QWidget,
)

from src.file_entry import FileEntry, mode_name, infer_mode_from_sheet
from src.lag_config import LagConfig
from src.sheet_file_matcher import extract_key, sanitize_sheet_name
from ui.layout_utils import FlowLayout, auto_size_dialog
from ui.widgets import AnglePickerWidget, TemplateSourceRow, OutputSettingsGroup

if TYPE_CHECKING:
    pass


# ═══════════════════════════════════════════════════════════════
# FileSettingsPage — 输入输出
# ═══════════════════════════════════════════════════════════════

class FileSettingsPage(QWidget):
    """文件设置：模板 + 数据 + 输出 集中管理。

    直接读写 MainWindow 的以下属性：
      - ui.editTemplatePath / ui.editOutputDir / ui.editOutputName / …
      - _data_file_paths, _file_entries, …
    """

    def __init__(self, mainwindow=None):
        super().__init__(mainwindow)
        self._mw = mainwindow
        self._setup_ui()
        self._init_state()

    # ── 属性代理（优先 mainwindow，否则用本地值） ──

    @property
    def _template_path(self) -> str:
        if self._mw:
            return self._mw.ui.editTemplatePath.text().strip()
        return self._local.get("template_path", "")

    @_template_path.setter
    def _template_path(self, v: str):
        if self._mw:
            self._mw.ui.editTemplatePath.setText(v)
        self._local["template_path"] = v

    @property
    def _data_file_paths(self) -> List[str]:
        if self._mw:
            return self._mw._data_file_paths
        return self._local.setdefault("data_file_paths", [])

    @_data_file_paths.setter
    def _data_file_paths(self, v: List[str]):
        if self._mw:
            self._mw._data_file_paths = v
        self._local["data_file_paths"] = v

    @property
    def _output_dir(self) -> str:
        if self._mw:
            return self._mw.ui.editOutputDir.text().strip()
        return self._local.get("output_dir", "")

    @_output_dir.setter
    def _output_dir(self, v: str):
        if self._mw:
            self._mw.ui.editOutputDir.setText(v)
        self._local["output_dir"] = v

    @property
    def _output_name(self) -> str:
        if self._mw:
            return self._mw.ui.editOutputName.text().strip()
        return self._local.get("output_name", "antenna_report.xlsx")

    @_output_name.setter
    def _output_name(self, v: str):
        if self._mw:
            self._mw.ui.editOutputName.setText(v)
        self._local["output_name"] = v

    # ── UI 构建 ──

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # ────── 模板文件 ──────
        self._tpl_row = TemplateSourceRow(
            on_browse=self._on_browse_template,
            on_preview=self._on_preview_report,
        )
        main_layout.addWidget(self._tpl_row)
        # 填充内置模板预设
        if self._mw and hasattr(self._mw, '_tm'):
            presets = self._mw._tm.get_all_templates()
            presets_list = [
                {"manufacturer": t.manufacturer, "name": t.name, "path": t.path}
                for t in presets
            ]
            self._tpl_row.populate_presets(presets_list)
        self._tpl_row.template_changed.connect(self._on_preset_template_selected)

        # ────── 数据文件 ──────
        data_grp = QGroupBox(self.tr("数据文件"))
        data_layout = QVBoxLayout(data_grp)
        data_layout.setSpacing(6)

        # 按钮行
        btn_row = QHBoxLayout()
        self._btn_add_files = QPushButton(self.tr("📂 添加数据文件..."))
        self._btn_add_files.setToolTip(self.tr("选择多个数据文件 (Ctrl+点击多选 / 拖拽)"))
        self._btn_clear_selected = QPushButton(self.tr("清除选中"))
        self._btn_clear_all = QPushButton(self.tr("全部清除"))
        self._btn_add_files.clicked.connect(self._on_add_data_files)
        self._btn_clear_selected.clicked.connect(self._on_clear_selected_files)
        self._btn_clear_all.clicked.connect(self._on_clear_all_files)
        btn_row.addWidget(self._btn_add_files)
        btn_row.addWidget(self._btn_clear_selected)
        btn_row.addWidget(self._btn_clear_all)
        btn_row.addStretch()
        data_layout.addLayout(btn_row)

        # 文件列表
        self._file_list_widget = QTableWidget()
        self._file_list_widget.setColumnCount(2)
        self._file_list_widget.setHorizontalHeaderLabels([
            self.tr("数据源文件"), self.tr("测试模式")
        ])
        self._file_list_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._file_list_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._file_list_widget.setColumnWidth(1, 140)
        self._file_list_widget.verticalHeader().setDefaultSectionSize(28)
        self._file_list_widget.verticalHeader().setVisible(False)
        self._file_list_widget.setMinimumHeight(80)
        self._file_list_widget.setMaximumHeight(180)
        self._file_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._file_list_widget.setAlternatingRowColors(True)
        self._file_list_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._file_list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        data_layout.addWidget(self._file_list_widget)

        # 匹配表
        self._match_table = QTableWidget()
        self._match_table.setColumnCount(3)
        self._match_table.setHorizontalHeaderLabels([
            self.tr("工作表"), self.tr("数据文件"), self.tr("状态")
        ])
        self._match_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self._match_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._match_table.setColumnWidth(0, 120)
        self._match_table.verticalHeader().setDefaultSectionSize(28)
        self._match_table.verticalHeader().setVisible(False)
        self._match_table.setMinimumHeight(120)
        self._match_table.setMaximumHeight(280)
        self._match_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._match_table.setAlternatingRowColors(True)
        data_layout.addWidget(self._match_table)

        # 自动匹配按钮行
        match_row = QHBoxLayout()
        self._btn_auto_match = QPushButton(self.tr("🔗 自动匹配"))
        self._btn_auto_match.clicked.connect(self._on_auto_match)
        self._btn_auto_match.setToolTip(self.tr("按文件命名自动匹配工作表"))
        self._lbl_match_status = QLabel("")
        self._lbl_match_status.setMinimumHeight(22)
        self._lbl_match_status.setStyleSheet("padding: 2px 0;")
        match_row.addWidget(self._btn_auto_match)
        match_row.addWidget(self._lbl_match_status)
        match_row.addSpacing(12)
        self._lbl_naming_mode = QLabel(self.tr("工作表命名:"))
        match_row.addWidget(self._lbl_naming_mode)
        self._cmb_naming_mode = QComboBox()
        self._cmb_naming_mode.addItem(self.tr("保留原模板工作表名"), 0)
        self._cmb_naming_mode.addItem(self.tr("用数据源名替换"), 1)
        self._cmb_naming_mode.setToolTip(self.tr("多数据源时，选择工作表命名方式"))
        self._cmb_naming_mode.setFixedWidth(190)
        self._cmb_naming_mode.currentIndexChanged.connect(self._on_naming_mode_changed)
        match_row.addWidget(self._cmb_naming_mode)
        match_row.addStretch()
        data_layout.addLayout(match_row)

        # 图表选择行
        chart_row = QHBoxLayout()
        self._check_chart_eff = QCheckBox(self.tr("效率曲线"))
        self._check_chart_eff.setChecked(True)
        chart_row.addWidget(self._check_chart_eff)
        self._check_chart_lag = QCheckBox(self.tr("增益曲线"))
        self._check_chart_lag.setChecked(True)
        chart_row.addWidget(self._check_chart_lag)
        chart_row.addStretch()
        data_layout.addLayout(chart_row)

        main_layout.addWidget(data_grp)

        # ────── 输出设置 ──────
        self._output_group = OutputSettingsGroup(
            output_dir="",
            output_name="antenna_report.xlsx",
            on_browse_output=self._on_browse_output,
            on_browse_full_report=self._on_browse_full_report,
        )
        main_layout.addWidget(self._output_group)

        main_layout.addStretch()

    def _init_state(self):
        """初始化本地状态（无 MainWindow 时使用）。"""
        self._local: dict = {}
        self._file_entries: List[FileEntry] = []
        self._worksheet_naming_mode: int = 0
        self._data_stale: bool = True
        self._cfg = None
        if self._mw:
            from src.config_manager import get_config_manager
            self._cfg = get_config_manager()
        # 绑定 mainwindow 已有的文件列表
        self._sync_from_mw()

    def _sync_from_mw(self):
        """从 MainWindow 同步已有状态。"""
        if not self._mw:
            return
        self._file_entries = list(getattr(self._mw, '_file_entries', []))
        self._worksheet_naming_mode = getattr(self._mw, '_worksheet_naming_mode', 0)
        self._data_stale = getattr(self._mw, '_data_stale', True)
        # 刷新 UI
        self._refresh_data_file_ui()
        self._sync_match_table_from_mw()

    def _sync_match_table_from_mw(self):
        """从 MainWindow 同步匹配表。"""
        if not self._mw:
            return
        mw_match = getattr(self._mw, '_match_table', None)
        if mw_match is not None and mw_match.rowCount() > 0:
            # 复制匹配表数据
            self._match_table.setRowCount(mw_match.rowCount())
            for row in range(mw_match.rowCount()):
                self._match_table.setRowHeight(row, 28)
                item0 = mw_match.item(row, 0)
                if item0:
                    self._match_table.setItem(row, 0, QTableWidgetItem(item0.text()))
                item2 = mw_match.item(row, 2)
                if item2:
                    s = QTableWidgetItem(item2.text())
                    s.setForeground(item2.foreground())
                    self._match_table.setItem(row, 2, s)
            self._lbl_match_status.setText(
                getattr(self._mw, '_lbl_match_status', QLabel("")).text()
            )

    # ── 日志 ──

    def _log(self, message: str):
        if self._mw:
            self._mw._log(message)

    # ── 文件操作事件 ──

    def _on_browse_template(self):
        """选择模板文件。"""
        start_dir = ""
        if self._cfg:
            start_dir = self._cfg.config.last_template_path or ""
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择模板文件"),
            start_dir,
            self.tr("所有支持格式 (*.xlsx *.xls *.csv *.docx);;Excel 新版 (*.xlsx);;Excel 旧版 (*.xls)")
        )
        if not path:
            return
        self._template_path = path  # 属性 setter
        if self._cfg:
            self._cfg.config.last_template_path = path
            self._cfg._dirty = True
        if self._mw:
            self._mw._chart_config_required = None
            self._mw._cached_template_params = set()
            self._mw._auto_apply_template_params()
        self._match_table.setRowCount(0)
        self._lbl_match_status.setText("")
        if self._data_file_paths:
            self._on_auto_match()

    def _on_preset_template_selected(self, path: str):
        """内置预设被选中 → 更新模板路径并触发自动匹配。"""
        if not path:
            return
        self._template_path = path
        if self._cfg:
            self._cfg.config.last_template_path = path
            self._cfg._dirty = True
        if self._mw:
            self._mw._chart_config_required = None
            self._mw._cached_template_params = set()
            self._mw._auto_apply_template_params()
        self._match_table.setRowCount(0)
        self._lbl_match_status.setText("")
        if self._data_file_paths:
            self._on_auto_match()

    def _on_preview_report(self):
        """打开报告预览对话框。"""
        if self._mw:
            self._mw._show_template_preview()

    def _on_add_data_files(self):
        if not self._cfg:
            return
        last_paths = self._cfg.config.last_csv_paths
        paths, _ = QFileDialog.getOpenFileNames(
            self, self.tr("选择数据文件 (可多选)"),
            last_paths[0] if last_paths else "",
            self.tr("所有支持格式 (*.csv *.xlsx *.xls);;CSV 文件 (*.csv);;Excel 新版 (*.xlsx)")
        )
        if not paths:
            return
        # 自动清除上次计算遗留数据
        if self._data_stale and self._mw:
            n_stale = len(self._data_file_paths)
            if n_stale > 0:
                self._log(f"🗑 自动清除上次计算遗留的 {n_stale} 个文件")
            self._data_file_paths.clear()
            self._file_entries.clear()
            self._file_list_widget.setRowCount(0)
            self._match_table.setRowCount(0)
            self._lbl_match_status.setText("")
        existing = set(self._data_file_paths)
        new_paths = [p for p in paths if p not in existing]
        if not new_paths:
            return
        self._data_file_paths.extend(new_paths)
        self._data_stale = False
        self._sync_file_entries()
        if self._cfg:
            self._cfg.config.last_csv_paths = [new_paths[0]]
            self._cfg._dirty = True
        self._refresh_data_file_ui()
        # 无预设模板时，输出目录自动设为数据源目录
        if not self._output_dir or self._output_dir == str(Path.cwd() / "output"):
            self._output_dir = str(Path(new_paths[0]).parent)
        if self._template_path:
            self._on_auto_match()

    def _on_clear_selected_files(self):
        rows = sorted({idx.row() for idx in self._file_list_widget.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, self.tr("提示"), self.tr("请先在文件列表中选中要清除的行。"))
            return
        for r in rows:
            if r < len(self._data_file_paths):
                del self._data_file_paths[r]
                if r < len(self._file_entries):
                    del self._file_entries[r]
        self._refresh_data_file_ui()
        if not self._data_file_paths:
            self._match_table.setRowCount(0)
            self._lbl_match_status.setText("")
            self._data_stale = True
        else:
            self._data_stale = False
            if self._template_path:
                self._on_auto_match()
        self._log(f"🗑 已清除 {len(rows)} 行, 剩余 {len(self._data_file_paths)} 个文件")

    def _on_clear_all_files(self):
        self._data_file_paths.clear()
        self._file_entries.clear()
        self._file_list_widget.setRowCount(0)
        self._match_table.setRowCount(0)
        self._lbl_match_status.setText("")
        self._data_stale = True

    def _on_browse_output(self):
        start_dir = self._output_dir or str(Path.cwd() / "output")
        path = QFileDialog.getExistingDirectory(self, self.tr("选择输出目录"), start_dir)
        if path:
            self._output_dir = path
            if self._cfg:
                self._cfg.config.last_output_dir = path
                self._cfg._dirty = True

    def _on_browse_full_report(self):
        start_dir = self._output_dir or str(Path.cwd() / "output")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存完整报告"),
            str(Path(start_dir) / "full_report.xlsx"),
            self.tr("Excel 文件 (*.xlsx)")
        )
        if path and self._mw:
            self._mw.ui.editFullReportPath.setText(path)

    def _sync_file_entries(self):
        old_map = {e.path: e for e in self._file_entries}
        self._file_entries = []
        test_mode = getattr(self._mw, '_test_mode', 0) if self._mw else 0
        for p in self._data_file_paths:
            if p in old_map:
                self._file_entries.append(old_map[p])
            else:
                self._file_entries.append(FileEntry(path=p, test_mode=test_mode))

    def _refresh_data_file_ui(self):
        t = self._file_list_widget
        t.setRowCount(len(self._data_file_paths))
        for i, p in enumerate(self._data_file_paths):
            try:
                size_mb = Path(p).stat().st_size / (1024 * 1024)
                label = f"📄 {Path(p).name}  ({size_mb:.1f} MB)"
            except OSError:
                label = f"📄 {Path(p).name}"
            item = QTableWidgetItem(label)
            item.setToolTip(p)
            t.setItem(i, 0, item)
            mode_combo = QComboBox()
            for mode_val in [0, 1, 2]:
                mode_combo.addItem(mode_name(mode_val), mode_val)
            if i < len(self._file_entries):
                mode_combo.setCurrentIndex(self._file_entries[i].test_mode)
            mode_combo.currentIndexChanged.connect(
                lambda idx, row=i: self._on_file_mode_changed(row))
            t.setCellWidget(i, 1, mode_combo)
            t.setRowHeight(i, 28)
        self._update_window_title()

    def _update_window_title(self):
        if self._mw:
            self._mw._update_window_title()

    def _on_file_mode_changed(self, row: int):
        combo = self._file_list_widget.cellWidget(row, 1)
        if combo and row < len(self._file_entries):
            self._file_entries[row].test_mode = combo.currentData()

    def _on_naming_mode_changed(self, index: int):
        data = self._cmb_naming_mode.currentData() or 0
        self._worksheet_naming_mode = data
        if self._mw:
            self._mw._worksheet_naming_mode = data
        if self._match_table.rowCount() > 0:
            self._on_auto_match()

    def _on_auto_match(self):
        template_path = self._template_path
        if not template_path:
            QMessageBox.warning(self, self.tr("提示"), self.tr("请先选择模板文件。"))
            return
        if not self._data_file_paths:
            QMessageBox.warning(self, self.tr("提示"), self.tr("请先添加数据文件。"))
            return

        from src.excel_reader import read_template
        from src.sheet_file_matcher import auto_match

        try:
            sheets = read_template(template_path)
        except Exception as e:
            self._log(f"⚠ 读取模板失败: {e}")
            return

        sheet_names = [s.name for s in sheets]
        if not sheet_names:
            self._log("模板中未检测到数据工作表")
            return

        # 从模板自动更新角度配置
        if self._mw and hasattr(self._mw, '_auto_update_angle_config_from_template'):
            self._mw._auto_update_angle_config_from_template(sheets)

        matches = auto_match(sheet_names, self._data_file_paths)
        self._populate_match_table(matches)

        for m in matches:
            if m.file_path:
                inferred = infer_mode_from_sheet(m.sheet_name)
                for e in self._file_entries:
                    if e.path == m.file_path and e.test_mode == 0:
                        e.test_mode = inferred
        self._refresh_data_file_ui()

        matched = sum(1 for m in matches if m.file_path is not None)
        self._lbl_match_status.setText(f"✓ {matched}/{len(matches)} 个工作表已匹配")
        self._log(f"自动匹配完成: {matched}/{len(matches)}")

    def _populate_match_table(self, matches):
        from src.sheet_file_matcher import extract_key, sanitize_sheet_name
        use_file_names = self._worksheet_naming_mode == 1
        self._match_table.setRowCount(len(matches))
        for i, m in enumerate(matches):
            self._match_table.setRowHeight(i, 28)
            display_name = m.sheet_name
            if use_file_names and m.file_path:
                display_name = sanitize_sheet_name(extract_key(m.file_path))
            self._match_table.setItem(i, 0, QTableWidgetItem(display_name))
            combo = QComboBox()
            combo.addItem("—")
            for fp in self._data_file_paths:
                combo.addItem(Path(fp).name, fp)
                combo.model().item(combo.count() - 1).setToolTip(fp)
            if m.file_path:
                idx = combo.findData(m.file_path)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(lambda idx, row=i: self._on_match_changed(row))
            self._match_table.setCellWidget(i, 1, combo)

            if m.file_path:
                status = QTableWidgetItem(self.tr("✓ 已匹配"))
                status.setForeground(QColor("green"))
            else:
                status = QTableWidgetItem(self.tr("未匹配"))
                status.setForeground(QColor("orange"))
            self._match_table.setItem(i, 2, status)

    def _on_match_changed(self, row: int):
        combo = self._match_table.cellWidget(row, 1)
        fp = combo.currentData() or "" if combo else ""
        valid = fp and fp != "—" and Path(fp).exists()
        status = self._match_table.item(row, 2)
        if status:
            if valid:
                status.setText(self.tr("✓ 已匹配"))
                status.setForeground(QColor("green"))
            else:
                status.setText(self.tr("未匹配"))
                status.setForeground(QColor("orange"))

    # ── 对外接口 ──

    def apply_template_preset(self, path: str, output_dir: str = "", tpl_name: str = ""):
        """应用模板预设，由 MainWindow 调用。"""
        self._template_path = path
        if self._mw:
            self._mw._save_template_path(path)
        if output_dir:
            self._output_dir = output_dir
        elif self._data_file_paths:
            self._output_dir = str(Path(self._data_file_paths[0]).parent)
        if tpl_name and self._mw and hasattr(self._mw, '_tm'):
            out_dir = self._output_dir or "."
            fname = self._mw._tm.next_available_filename(out_dir, tpl_name)
            self._output_name = fname
        if self._mw:
            self._mw._cached_template_params = set()
            self._mw._auto_apply_template_params()

    def get_lag_checkboxes(self):
        """返回 {效率曲线, 增益曲线} 勾选状态。"""
        return {
            "chart_eff": self._check_chart_eff.isChecked(),
            "chart_lag": self._check_chart_lag.isChecked(),
        }

    def build_datasource_map(self, progress_callback=None):
        """构建数据源映射（同 MainWindow._build_datasource_map）。"""
        from src.datasource import DataSource
        from src.sheet_file_matcher import extract_key, sanitize_sheet_name
        result = {}
        total_files = max(len(self._data_file_paths), 1)
        file_idx = 0
        use_file_names = self._worksheet_naming_mode == 1

        valid_paths = set(self._data_file_paths)
        for row in range(self._match_table.rowCount()):
            combo = self._match_table.cellWidget(row, 1)
            if combo:
                fp = combo.currentData() or ""
                if fp and fp != "—" and fp not in valid_paths:
                    combo.setCurrentIndex(0)

        matched_files = set()
        for row in range(self._match_table.rowCount()):
            template_sheet_name = self._match_table.item(row, 0).text()
            combo = self._match_table.cellWidget(row, 1)
            fp = combo.currentData() or "" if combo else ""
            if fp and Path(fp).exists():
                if progress_callback:
                    file_idx += 1
                    progress_callback(file_idx, total_files, f"Loading {Path(fp).name}...")
                try:
                    if use_file_names:
                        key = sanitize_sheet_name(extract_key(fp))
                        result[key] = DataSource.from_path(fp)
                    else:
                        result[sanitize_sheet_name(template_sheet_name)] = DataSource.from_path(fp)
                    matched_files.add(fp)
                except Exception as e:
                    self._log(f"⚠ {template_sheet_name} 数据源加载失败: {e}")

        unmatched = [f for f in self._data_file_paths if f not in matched_files]
        if unmatched:
            for fp in unmatched:
                sheet_name = sanitize_sheet_name(extract_key(fp))
                if progress_callback:
                    file_idx += 1
                    progress_callback(file_idx, total_files, f"Loading {Path(fp).name}...")
                try:
                    result[sheet_name] = DataSource.from_path(fp)
                    self._log(f"  ↗ 自动添加: {sheet_name} ← {Path(fp).name}")
                except Exception as e:
                    self._log(f"⚠ {Path(fp).name} 加载失败: {e}")
        return result

    def build_sheet_mode_map(self, datasource_map: dict) -> dict:
        """从 _file_entries 和 _match_table 构建 sheet→test_mode 映射。

        遍历匹配表，查找每个已匹配文件的 test_mode 并关联到工作表名。
        未映射到的 sheet 使用当前 _test_mode 作为默认值。
        当 _worksheet_naming_mode==1 时，用数据源名（extract_key）做映射键。
        """
        sheet_mode_map: Dict[str, int] = {}
        file_mode_lookup = {e.path: e.test_mode for e in self._file_entries}
        use_file_names = self._worksheet_naming_mode == 1
        for row in range(self._match_table.rowCount()):
            sn = self._match_table.item(row, 0)
            combo = self._match_table.cellWidget(row, 1)
            if sn and combo:
                fp = combo.currentData() or ""
                if fp and fp in file_mode_lookup:
                    key = sanitize_sheet_name(extract_key(fp)) if use_file_names else sanitize_sheet_name(sn.text())
                    sheet_mode_map[key] = file_mode_lookup[fp]
        for sn in datasource_map:
            if sn not in sheet_mode_map:
                sheet_mode_map[sn] = getattr(self._mw, '_test_mode', 0) if self._mw else 0
        return sheet_mode_map


# ═══════════════════════════════════════════════════════════════
# AntennaParamsPage — 天线参数
# ═══════════════════════════════════════════════════════════════

class AntennaParamsPage(QWidget):
    """天线参数设置页面（原 CalcParamsDialog → QWidget）。

    直接读写 MainWindow 属性：
      _test_mode, _lag_config, _ar_lag_config, _required_params,
      _extra_params, _mode_states, _nh_custom_angles, _ar_output_db,
      _cmb_freq_source, _spin_trim_start/end,
      _check_extrapolate, _check_robust_peak
    """

    params_changed = Signal()  # 参数变更时发射

    # ── 参数定义（来自 CalcParamsDialog） ──
    _COMMON_PARAMS = [
        ("Gain", [
            ("gain", "Peak Gain"),
            ("lag_single", "Gain @ θ（单角度）"),
            ("lag_range", "Gain @ θ Range（范围）"),
        ]),
        ("Directivity", [
            ("directivity", "Directivity (dBi)"),
        ]),
        ("Efficiency", [
            ("efficiency_pct", "Efficiency (%)"),
            ("efficiency_db", "Efficiency (dB)"),
        ]),
        ("Axial Ratio", [
            ("ar_single", "AR @ θ（单角度）"),
            ("ar_range", "AR @ θ Range（范围）"),
        ]),
        ("波束参数", [
            ("boresight_theta", "Boresight θ"),
            ("boresight_phi", "Boresight φ"),
            ("theta_bw", "Theta Beamwidth (3dB)"),
            ("phi_bw", "Phi Beamwidth (3dB)"),
            ("front_back_ratio", "Front/Back Ratio"),
        ]),
        ("功率统计", [
            ("max_power", "Maximum Power"),
            ("min_power", "Minimum Power"),
            ("avg_gain", "Average Gain"),
            ("avg_power", "Average Power"),
            ("max_min_ratio", "Max/Min Ratio"),
            ("max_avg_ratio", "Max/Avg Ratio"),
            ("min_avg_ratio", "Min/Avg Ratio"),
        ]),
        ("交叉极化隔离度 (XPI)", [
            ("xpi_boresight", "XPI @ Boresight (dB)"),
            ("xpi_mean", "XPI Mean (dB)"),
            ("xpi_min", "XPI Min (dB)"),
        ]),
        ("总效率", [
            ("total_efficiency_pct", "Total Efficiency (%)"),
            ("mismatch_loss_db", "Mismatch Loss (dB)"),
        ]),
        ("相位中心", [
            ("pc_theta_mm", "PC Theta (mm)"),
            ("pc_phi_mm", "PC Phi (mm)"),
        ]),
    ]

    _TRP_PARAMS = [
        ("TRP", [
            ("trp", "Total Radiated Power (TRP)"),
            ("peak_eirp", "Peak EIRP"),
        ]),
        ("NHPRP", [
            ("nhprp_45", "NHPRP ±45° (Pi/4)"),
            ("nhprp_30", "NHPRP ±30° (Pi/6)"),
            ("nhprp_225", "NHPRP ±22.5° (Pi/8)"),
            ("nhprp_custom", "NHPRP 自定义角度"),
        ]),
        ("半球 PRP", [
            ("uh_prp", "Upper Hemisphere PRP"),
            ("lh_prp", "Lower Hemisphere PRP"),
            ("prp_120", "PRP (theta 0-120°)"),
        ]),
        ("比率", [
            ("nhprp45_ratio", "NHPRP45 / TRP"),
            ("nhprp30_ratio", "NHPRP30 / TRP"),
            ("nhprp225_ratio", "NHPRP22.5 / TRP"),
            ("uh_ratio", "UHPRP / TRP"),
            ("lh_ratio", "LHPRP / TRP"),
        ]),
    ]

    _TIS_PARAMS = [
        ("TIS", [
            ("tis", "Total Isotropic Sensitivity (TIS)"),
        ]),
        ("NHPIS", [
            ("nhpis_45", "NHPIS ±45° (Pi/4)"),
            ("nhpis_30", "NHPIS ±30° (Pi/6)"),
            ("nhpis_225", "NHPIS ±22.5° (Pi/8)"),
            ("nhpis_custom", "NHPIS 自定义角度"),
        ]),
        ("半球 PIS", [
            ("uh_pis", "Upper Hemisphere PIS"),
            ("lh_pis", "Lower Hemisphere PIS"),
            ("pis_120", "PIS (theta 0-120°)"),
        ]),
        ("比率", [
            ("nhpis45_ratio", "NHPIS45 / TIS"),
            ("nhpis30_ratio", "NHPIS30 / TIS"),
            ("nhpis225_ratio", "NHPIS22.5 / TIS"),
            ("uh_ratio", "UHPIS / TIS"),
            ("lh_ratio", "LHPIS / TIS"),
        ]),
    ]

    def __init__(self, mainwindow=None):
        super().__init__(mainwindow)
        self._mw = mainwindow
        self._template_params: set = set()

        # ── 三模式独立状态 ──
        self._mode_states = [
            {"singles": [], "ranges": [], "ar_singles": [], "ar_ranges": [],
             "nh_custom_angles": [], "extrapolate": False, "robust_peak": False,
             "ar_output_db": True,
             "freq_source": "datasource", "trim_start": 0, "trim_end": 0,
             "required": set(), "extra": set()},
            {"singles": [], "ranges": [], "ar_singles": [], "ar_ranges": [],
             "nh_custom_angles": [], "extrapolate": False, "robust_peak": False,
             "ar_output_db": True,
             "freq_source": "datasource", "trim_start": 0, "trim_end": 0,
             "required": set(), "extra": set()},
            {"singles": [], "ranges": [], "ar_singles": [], "ar_ranges": [],
             "nh_custom_angles": [], "extrapolate": False, "robust_peak": False,
             "ar_output_db": True,
             "freq_source": "datasource", "trim_start": 0, "trim_end": 0,
             "required": set(), "extra": set()},
        ]

        self._gain_angle_widget: Optional[AnglePickerWidget] = None
        self._ar_angle_widget: Optional[AnglePickerWidget] = None
        self._nh_custom_angles: List[float] = []
        self._extrapolate: bool = False
        self._robust_peak: bool = False
        self._active_tab: int = 0
        self._test_mode: int = 0
        self._required_params: set = set()
        self._extra_params: set = set()

        self._left_checkboxes: Dict[str, QCheckBox] = {}
        self._right_checkboxes: Dict[str, QCheckBox] = {}
        self._left_scroll: Optional[QScrollArea] = None
        self._right_scroll: Optional[QScrollArea] = None
        self._summary_label: Optional[QLabel] = None

        self._setup_ui()
        self._load_state()
        self._rebuild_param_columns()

    # ── UI 构建 ──

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # 测试模式选择
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("<b>" + self.tr("测试模式:") + "</b>"))
        self._cmb_test_mode = QComboBox()
        self._cmb_test_mode.addItem("📡 " + self.tr("无源天线"), 0)
        self._cmb_test_mode.addItem("📶 " + self.tr("有源发射 TRP"), 1)
        self._cmb_test_mode.addItem("📻 " + self.tr("有源接收 TIS"), 2)
        self._cmb_test_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self._cmb_test_mode)
        mode_row.addStretch()
        main_layout.addLayout(mode_row)

        # 参数选择区域 (scroll)
        param_widget = QWidget()
        param_layout = QVBoxLayout(param_widget)
        param_layout.setSpacing(8)

        # 双列参数
        splitter = QHBoxLayout()
        splitter.setSpacing(8)

        left_grp = QGroupBox(self.tr("报告必需参数（模板自动识别，可调整）"))
        left_layout = QVBoxLayout(left_grp)
        self._left_scroll = QScrollArea()
        self._left_scroll.setWidgetResizable(True)
        self._left_scroll.setFrameShape(QScrollArea.NoFrame)
        left_layout.addWidget(self._left_scroll)
        splitter.addWidget(left_grp, 1)

        right_grp = QGroupBox(self.tr("额外计算参数（送 full_report）"))
        right_layout = QVBoxLayout(right_grp)
        self._right_scroll = QScrollArea()
        self._right_scroll.setWidgetResizable(True)
        self._right_scroll.setFrameShape(QScrollArea.NoFrame)
        right_layout.addWidget(self._right_scroll)
        splitter.addWidget(right_grp, 1)

        param_layout.addLayout(splitter, 1)

        # ── Gain 角度 (AnglePickerWidget) ──
        gain_sep = QFrame()
        gain_sep.setFrameShape(QFrame.HLine)
        param_layout.addWidget(gain_sep)
        self._gain_angle_widget = AnglePickerWidget(self.tr("Gain 角度"))
        self._gain_angle_widget.angle_changed.connect(lambda cfg: self._on_angle_changed("gain"))
        param_layout.addWidget(self._gain_angle_widget)

        # ── AR 角度 (AnglePickerWidget) ──
        ar_sep = QFrame()
        ar_sep.setFrameShape(QFrame.HLine)
        param_layout.addWidget(ar_sep)
        self._ar_angle_widget = AnglePickerWidget(self.tr("AR 角度"))
        self._ar_angle_widget.angle_changed.connect(lambda cfg: self._on_angle_changed("ar"))
        param_layout.addWidget(self._ar_angle_widget)

        # ── 算法选项 ──
        algo_grp = QGroupBox(self.tr("算法选项"))
        algo_layout = QVBoxLayout(algo_grp)
        algo_layout.setSpacing(4)

        self._freq_widget = QWidget()
        freq_row = QHBoxLayout(self._freq_widget)
        freq_row.setContentsMargins(0, 0, 0, 0)
        freq_row.addWidget(QLabel(self.tr("频点来源:")))
        self._cmb_freq_src = QComboBox()
        self._cmb_freq_src.addItem(self.tr("新 sheet 频点: 数据源"), "datasource")
        self._cmb_freq_src.addItem(self.tr("新 sheet 频点: 模板"), "template")
        self._cmb_freq_src.currentIndexChanged.connect(lambda: self._sync_to_mw())
        freq_row.addWidget(self._cmb_freq_src)
        freq_row.addWidget(QLabel(self.tr("  去除频点: 前")))
        self._spin_trim_start = QSpinBox()
        self._spin_trim_start.setRange(0, 50)
        self._spin_trim_start.setFixedWidth(50)
        self._spin_trim_start.valueChanged.connect(lambda: self._sync_to_mw())
        freq_row.addWidget(self._spin_trim_start)
        freq_row.addWidget(QLabel(self.tr("后")))
        self._spin_trim_end = QSpinBox()
        self._spin_trim_end.setRange(0, 50)
        self._spin_trim_end.setFixedWidth(50)
        self._spin_trim_end.valueChanged.connect(lambda: self._sync_to_mw())
        freq_row.addWidget(self._spin_trim_end)
        freq_row.addStretch()
        algo_layout.addWidget(self._freq_widget)

        check_row = QHBoxLayout()
        self._check_extrap = QCheckBox(self.tr("Theta 外推到 180°"))
        self._check_extrap.toggled.connect(lambda: self._sync_to_mw())
        check_row.addWidget(self._check_extrap)
        self._check_robust = QCheckBox(self.tr("Robust peak detection（替代 np.max）"))
        self._check_robust.toggled.connect(lambda: self._sync_to_mw())
        check_row.addWidget(self._check_robust)
        self._cmb_ar_output = QComboBox()
        self._cmb_ar_output.addItem(self.tr("AR 输出 dB"), True)
        self._cmb_ar_output.addItem(self.tr("AR 输出 线性"), False)
        self._cmb_ar_output.setCurrentIndex(0)
        self._cmb_ar_output.setToolTip(self.tr("AR 输出单位: dB (20·log₁₀) 或线性比值"))
        self._cmb_ar_output.currentIndexChanged.connect(lambda: self._sync_to_mw())
        check_row.addWidget(self._cmb_ar_output)
        check_row.addStretch()
        algo_layout.addLayout(check_row)

        param_layout.addWidget(algo_grp)

        # ── 多步进计算 (原 _init_step_selector) ──
        self._grp_step = QGroupBox(self.tr("📏 多步进计算"))
        self._grp_step.setCheckable(True)
        self._grp_step.setChecked(False)
        self._grp_step.setToolTip(self.tr("勾选后可以选择多个步进值同时计算，结果输出到同一个Excel的不同Sheet"))
        sl = QVBoxLayout(self._grp_step)
        sl.setSpacing(6)
        sl.addWidget(QLabel(self.tr("选择要计算的步进值（可多选）。未选中则使用源文件原始步进。")))
        from PySide6.QtWidgets import QLineEdit
        self._step_checks: Dict[float, QCheckBox] = {}
        cb_row = QHBoxLayout()
        cb_row.setSpacing(8)
        COMMON_STEPS = [2, 5, 10, 15, 20, 30, 45]
        for s in COMMON_STEPS:
            cb = QCheckBox(f"{s}°")
            cb.setChecked(s in [5, 10])
            self._step_checks[s] = cb
            cb_row.addWidget(cb)
        cb_row.addStretch()
        sl.addLayout(cb_row)
        cust_row = QHBoxLayout()
        cust_row.addWidget(QLabel(self.tr("自定义:")))
        self._edit_step_custom = QLineEdit()
        self._edit_step_custom.setPlaceholderText(self.tr("如: 3, 8, 25 (逗号分隔)"))
        self._edit_step_custom.setMaximumWidth(250)
        cust_row.addWidget(self._edit_step_custom)
        cust_row.addStretch()
        sl.addLayout(cust_row)
        self._chk_skip_original = QCheckBox(
            self.tr("☐ 跳过原始步进（仅计算上述选中的步进值）"))
        sl.addWidget(self._chk_skip_original)
        param_layout.addWidget(self._grp_step)

        param_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(param_widget)
        main_layout.addWidget(scroll, 1)

        # 已选参数概览
        self._summary_grp = QGroupBox("📋 " + self.tr("已选参数概览"))
        summary_layout = QVBoxLayout(self._summary_grp)
        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        self._summary_label.setTextFormat(Qt.RichText)
        self._summary_label.setStyleSheet("padding: 4px; font-size: 12px;")
        summary_layout.addWidget(self._summary_label)
        main_layout.addWidget(self._summary_grp)

        # NHPRP/NHPIS 自定义角度 (TRP/TIS 时显示)
        self._grp_nh = QGroupBox("NHPRP / NHPIS " + self.tr("自定义角度"))
        nh_layout = QHBoxLayout(self._grp_nh)
        self._btn_nh_angle = QPushButton("⚙ " + self.tr("自定义角度..."))
        self._btn_nh_angle.clicked.connect(self._show_nh_angle_popup)
        nh_layout.addWidget(self._btn_nh_angle)
        self._lbl_nh_angles = QLabel(self.tr("（默认 45°）"))
        nh_layout.addWidget(self._lbl_nh_angles)
        nh_layout.addStretch()
        self._grp_nh.setVisible(False)
        param_layout.addWidget(self._grp_nh)

    # ── 参数列表 ──

    @staticmethod
    def _get_params_for_tab(tab_index: int):
        if tab_index == 0:
            return list(AntennaParamsPage._COMMON_PARAMS)
        elif tab_index == 1:
            no_ar = [(g, plist) for g, plist in AntennaParamsPage._COMMON_PARAMS if g != "Axial Ratio"]
            return no_ar + list(AntennaParamsPage._TRP_PARAMS)
        else:
            return list(AntennaParamsPage._TIS_PARAMS)

    # ── 模式切换 ──

    def _on_angle_changed(self, target: str):
        """AnglePickerWidget 角度变更回调。"""
        self._save_current_mode_state()
        self._sync_to_mw()

    def _on_mode_changed(self, index: int):
        self._save_current_mode_state()
        self._load_mode_state(index)
        self._active_tab = index
        self._test_mode = index
        is_active = index in (1, 2)
        is_tis = index == 2
        self._grp_nh.setVisible(is_active)
        self._freq_widget.setVisible(not is_active)
        self._rebuild_param_columns()
        self._sync_to_mw()

    def _save_current_mode_state(self):
        m = self._test_mode
        s = self._mode_states[m]
        gain_cfg = self._gain_angle_widget.get_config() if self._gain_angle_widget else LagConfig()
        s["singles"] = list(gain_cfg.single_angles)
        s["ranges"] = list(gain_cfg.ranges)
        ar_cfg = self._ar_angle_widget.get_config() if self._ar_angle_widget else LagConfig()
        s["ar_singles"] = list(ar_cfg.single_angles)
        s["ar_ranges"] = list(ar_cfg.ranges)
        s["nh_custom_angles"] = list(self._nh_custom_angles)
        s["extrapolate"] = self._check_extrap.isChecked()
        s["robust_peak"] = self._check_robust.isChecked()
        s["ar_output_db"] = self._cmb_ar_output.currentData()
        s["freq_source"] = self._cmb_freq_src.currentData()
        s["trim_start"] = self._spin_trim_start.value()
        s["trim_end"] = self._spin_trim_end.value()
        s["required"] = self._get_checked_keys(self._left_checkboxes)
        s["extra"] = self._get_checked_keys(self._right_checkboxes)

    def _load_mode_state(self, mode: int):
        self._test_mode = mode
        s = self._mode_states[mode]
        gain_cfg = LagConfig(
            single_angles=list(s.get("singles", [])),
            ranges=list(s.get("ranges", [])),
        )
        if self._gain_angle_widget:
            self._gain_angle_widget.set_config(gain_cfg)
        ar_cfg = LagConfig(
            single_angles=list(s.get("ar_singles", [])),
            ranges=list(s.get("ar_ranges", [])),
        )
        if self._ar_angle_widget:
            self._ar_angle_widget.set_config(ar_cfg)
        self._nh_custom_angles = list(s.get("nh_custom_angles", []))
        self._sync_nh_angle_display()
        self._check_extrap.setChecked(s["extrapolate"])
        self._check_robust.setChecked(s["robust_peak"])
        self._cmb_ar_output.setCurrentIndex(0 if s.get("ar_output_db", True) else 1)
        idx = self._cmb_freq_src.findData(s["freq_source"])
        if idx >= 0:
            self._cmb_freq_src.setCurrentIndex(idx)
        self._spin_trim_start.setValue(s["trim_start"])
        self._spin_trim_end.setValue(s["trim_end"])
        self._required_params = s["required"]
        self._extra_params = s["extra"]

    # ── 参数列重建 ──

    def _rebuild_param_columns(self):
        params = self._get_params_for_tab(self._active_tab)
        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(6)
        self._left_checkboxes.clear()
        self._right_checkboxes.clear()

        for grp_name, items in params:
            grp = QGroupBox(grp_name)
            gl = QVBoxLayout(grp)
            gl.setSpacing(2)
            for key, label in items:
                cb = QCheckBox(label)
                cb.setChecked(key in self._template_params)
                cb.toggled.connect(lambda checked, k=key: self._sync_to_mw())
                gl.addWidget(cb)
                self._left_checkboxes[key] = cb
                self._right_checkboxes[key] = cb
            # AnglePickerWidget instances are inline in _setup_ui
            vbox.addWidget(grp)
        vbox.addStretch()

        self._left_scroll.setWidget(content)
        rw = self._right_scroll.parent()
        if rw and hasattr(rw, 'hide'):
            rw.hide()
        self._update_summary()

    
    def _show_nh_angle_popup(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("NHPRP / NHPIS " + self.tr("自定义角度"))
        dlg.setMinimumSize(460, 380)

        import copy
        _src_angles = self._nh_custom_angles
        _angles = copy.deepcopy(_src_angles)

        _display_grp = QGroupBox()
        _display_layout = QVBoxLayout(_display_grp)

        def _refresh_display():
            while _display_layout.count():
                item = _display_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            if _angles:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                dw = QWidget()
                fl = FlowLayout(dw, margin=4, h_spacing=6, v_spacing=4)
                for a in sorted(set(_angles)):
                    tag = QWidget()
                    tl = QHBoxLayout(tag)
                    tl.setContentsMargins(2, 1, 2, 1)
                    tl.setSpacing(2)
                    tl.addWidget(QLabel(f"±{a}°"))
                    btn_del = QPushButton("✕")
                    btn_del.setFixedSize(20, 20)
                    btn_del.setStyleSheet("padding:0;")
                    btn_del.clicked.connect(lambda checked, v=a: (_angles.remove(v), _refresh_display()))
                    tl.addWidget(btn_del)
                    fl.addWidget(tag)
                scroll.setWidget(dw)
                _display_layout.addWidget(scroll)
                btn_clear = QPushButton("🗑 " + self.tr("清空全部"))
                btn_clear.clicked.connect(lambda: (_angles.clear(), _refresh_display()))
                _display_layout.addWidget(btn_clear)
            else:
                _display_layout.addWidget(QLabel(self.tr("  (默认 45°，添加自定义角度可覆盖默认值)")))
            _display_grp.setTitle(self.tr("已配置: {} 个角度").format(len(_angles)))

        _refresh_display()

        bottom_ctls = QWidget()
        bottom_layout = QVBoxLayout(bottom_ctls)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        quick_grp = QGroupBox(self.tr("快捷预置"))
        quick_layout = QHBoxLayout(quick_grp)
        presets = [
            ("22.5° (Pi/8)", 22.5),
            ("30° (Pi/6)", 30.0),
            ("45° (Pi/4)", 45.0),
            ("60° (Pi/3)", 60.0),
            ("75°", 75.0),
        ]
        for label, val in presets:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, v=val: (
                _angles.append(v) if v not in _angles else None,
                _refresh_display()
            ))
            quick_layout.addWidget(btn)
        bottom_layout.addWidget(quick_grp)

        cust_grp = QGroupBox(self.tr("自定义"))
        cust_layout = QHBoxLayout(cust_grp)
        spin_custom = QDoubleSpinBox()
        spin_custom.setRange(0, 90)
        spin_custom.setValue(45)
        spin_custom.setSuffix("°")
        spin_custom.setDecimals(1)
        btn_add_custom = QPushButton("+ " + self.tr("添加"))
        btn_add_custom.clicked.connect(lambda: (
            _angles.append(spin_custom.value()) if spin_custom.value() not in _angles else None,
            _refresh_display()
        ))
        cust_layout.addWidget(QLabel(self.tr("角度:")))
        cust_layout.addWidget(spin_custom)
        cust_layout.addWidget(btn_add_custom)
        cust_layout.addStretch()
        bottom_layout.addWidget(cust_grp)

        step_grp = QGroupBox(self.tr("步进批量生成"))
        step_layout = QHBoxLayout(step_grp)
        spin_start = QDoubleSpinBox()
        spin_start.setRange(0, 90)
        spin_start.setValue(0)
        spin_end = QDoubleSpinBox()
        spin_end.setRange(0, 90)
        spin_end.setValue(90)
        spin_step = QDoubleSpinBox()
        spin_step.setRange(1, 45)
        spin_step.setValue(15)
        btn_gen = QPushButton(self.tr("生成"))
        btn_gen.clicked.connect(lambda: (
            [_angles.append(round(float(a), 6))
             for a in np.arange(spin_start.value(), spin_end.value() + 1, spin_step.value())
             if round(float(a), 6) not in _angles],
            _refresh_display()
        ))
        step_layout.addWidget(QLabel(self.tr("起:")))
        step_layout.addWidget(spin_start)
        step_layout.addWidget(QLabel(self.tr("止:")))
        step_layout.addWidget(spin_end)
        step_layout.addWidget(QLabel(self.tr("步:")))
        step_layout.addWidget(spin_step)
        step_layout.addWidget(btn_gen)
        bottom_layout.addWidget(step_grp)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            _src_angles.clear(),
            _src_angles.extend(sorted(set(_angles))),
            dlg.accept()
        ))
        btns.rejected.connect(dlg.reject)
        bottom_layout.addWidget(btns)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(_display_grp)
        splitter.addWidget(bottom_ctls)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        layout = QVBoxLayout(dlg)
        layout.addWidget(splitter)
        dlg.exec()
        self._sync_nh_angle_display()
        self._sync_to_mw()

    def _sync_nh_angle_display(self):
        if self._nh_custom_angles:
            angles_str = ", ".join(f"{a}°" for a in sorted(set(self._nh_custom_angles)))
            self._lbl_nh_angles.setText(angles_str)
        else:
            self._lbl_nh_angles.setText(self.tr("（默认 45°）"))

    # ── 摘要 ──

    @staticmethod
    def _get_checked_keys(checkbox_dict: dict) -> set:
        return {k for k, cb in checkbox_dict.items() if cb.isChecked()}

    def _update_summary(self):
        if not self._summary_label:
            return
        mode_names = {0: self.tr("📡 无源天线"), 1: self.tr("📶 有源发射 TRP"), 2: self.tr("📻 有源接收 TIS")}
        mode_str = mode_names.get(self._test_mode, self.tr("未知"))
        lines = [f"<b>{self.tr('测试模式')}:</b> {mode_str}"]

        checked = sorted(set(cb.text() for cb in self._left_checkboxes.values() if cb.isChecked()))
        if checked:
            lines.append(f"<b>{self.tr('计算参数')} ({len(checked)}):</b> {', '.join(checked)}")
        else:
            lines.append(f"<b>{self.tr('计算参数')}:</b> <span style='color:#888;'>({self.tr('未选择')})</span>")

        gain_cfg_s = self._gain_angle_widget.get_config() if self._gain_angle_widget else LagConfig()
        gain_singles = sorted(set(gain_cfg_s.single_angles))
        gain_ranges = sorted(set(gain_cfg_s.ranges))
        if gain_singles or gain_ranges:
            parts = [f"{a}°" for a in gain_singles] + [f"({lo}°–{hi}°)" for lo, hi in gain_ranges]
            lines.append(f"<b>Gain {self.tr('角度')} ({len(parts)}):</b> {', '.join(parts)}")
        else:
            lines.append(f"<b>Gain {self.tr('角度')}:</b> <span style='color:#888;'>({self.tr('未设置')})</span>")

        ar_cfg_s = self._ar_angle_widget.get_config() if self._ar_angle_widget else LagConfig()
        ar_singles = sorted(set(ar_cfg_s.single_angles))
        ar_ranges = sorted(set(ar_cfg_s.ranges))
        if ar_singles or ar_ranges:
            parts = [f"{a}°" for a in ar_singles] + [f"({lo}°–{hi}°)" for lo, hi in ar_ranges]
            lines.append(f"<b>AR {self.tr('角度')} ({len(parts)}):</b> {', '.join(parts)}")
        else:
            lines.append(f"<b>AR {self.tr('角度')}:</b> <span style='color:#888;'>({self.tr('未设置')})</span>")

        algo_parts = []
        if self._check_extrap.isChecked():
            algo_parts.append(self.tr("Theta 外推到 180°"))
        if self._check_robust.isChecked():
            algo_parts.append(self.tr("Robust peak detection"))
        if not self._cmb_ar_output.currentData():
            algo_parts.append(self.tr("AR 输出线性"))
        algo_str = ", ".join(algo_parts) if algo_parts else (
            "<span style='color:#888;'>(" + self.tr("默认") + ")</span>")
        lines.append(f"<b>{self.tr('算法选项')}:</b> {algo_str}")

        freq_src = self._cmb_freq_src.currentText()
        trim = f"{self.tr('去除')}: {self.tr('前')} {self._spin_trim_start.value()} / {self.tr('后')} {self._spin_trim_end.value()}"
        lines.append(f"<b>{self.tr('频点')}:</b> {freq_src} | {trim}")

        self._summary_label.setText("<br>".join(lines))

    # ── 同步到 MainWindow ──

    def _sync_to_mw(self):
        """将当前页面状态同步到 MainWindow 属性。"""
        if not self._mw:
            self._update_summary()
            return

        mw = self._mw
        self._save_current_mode_state()
        mw._mode_states = [dict(s) for s in self._mode_states]
        mw._test_mode = self._test_mode

        # 同步 Gain 角度 (从 AnglePickerWidget 读取)
        gain_cfg = self._gain_angle_widget.get_config() if self._gain_angle_widget else LagConfig()
        if hasattr(mw, '_lag_config'):
            mw._lag_config.clear()
            for a in sorted(set(gain_cfg.single_angles)):
                mw._lag_config.add_single(a)
            for lo, hi in sorted(set(gain_cfg.ranges)):
                mw._lag_config.add_range(lo, hi)
            mw._sync_quick_buttons()
            mw._update_lag_display()

        # 同步 AR 角度 (从 AnglePickerWidget 读取)
        ar_cfg = self._ar_angle_widget.get_config() if self._ar_angle_widget else LagConfig()
        if not hasattr(mw, '_ar_lag_config'):
            mw._ar_lag_config = LagConfig()
        mw._ar_lag_config.clear()
        for a in sorted(set(ar_cfg.single_angles)):
            mw._ar_lag_config.add_single(a)
        for lo, hi in sorted(set(ar_cfg.ranges)):
            mw._ar_lag_config.add_range(lo, hi)

        required = set(k for k, cb in self._left_checkboxes.items() if cb.isChecked())
        extra = set(k for k, cb in self._right_checkboxes.items() if cb.isChecked())
        mw._required_params = required
        mw._extra_params = extra
        mw._nh_custom_angles = list(self._nh_custom_angles)

        if hasattr(mw, '_cmb_freq_source') and mw._cmb_freq_source:
            data = self._cmb_freq_src.currentData()
            idx = mw._cmb_freq_source.findData(data)
            if idx >= 0:
                mw._cmb_freq_source.setCurrentIndex(idx)
        if hasattr(mw, '_spin_trim_start'):
            mw._spin_trim_start.setValue(self._spin_trim_start.value())
            mw._spin_trim_end.setValue(self._spin_trim_end.value())
        if hasattr(mw, '_check_extrapolate'):
            mw._check_extrapolate.setChecked(self._check_extrap.isChecked())
        if hasattr(mw, '_check_robust_peak'):
            mw._check_robust_peak.setChecked(self._check_robust.isChecked())
        mw._ar_output_db = self._cmb_ar_output.currentData()

        self._update_summary()
        self.params_changed.emit()

    # ── 加载/保存状态（与 MainWindow 双向同步） ──

    def _load_state(self):
        """从 MainWindow 加载状态。"""
        if not self._mw:
            return
        mw = self._mw
        if hasattr(mw, '_mode_states') and mw._mode_states:
            self._mode_states = [dict(s) for s in mw._mode_states]
        if hasattr(mw, '_test_mode'):
            self._test_mode = mw._test_mode
            self._cmb_test_mode.blockSignals(True)
            self._cmb_test_mode.setCurrentIndex(mw._test_mode)
            self._cmb_test_mode.blockSignals(False)
        if hasattr(mw, '_lag_config') and self._gain_angle_widget:
            self._gain_angle_widget.set_config(mw._lag_config)
        if hasattr(mw, '_ar_lag_config') and self._ar_angle_widget:
            self._ar_angle_widget.set_config(mw._ar_lag_config)
        # 以下读取 MainWindow UI 控件，可能因跨测试 GC 导致 C++ 对象已删除
        try:
            if hasattr(mw, '_cmb_freq_source') and mw._cmb_freq_source:
                data = mw._cmb_freq_source.currentData()
                idx = self._cmb_freq_src.findData(data)
                if idx >= 0:
                    self._cmb_freq_src.setCurrentIndex(idx)
        except RuntimeError:
            pass
        try:
            if hasattr(mw, '_spin_trim_start'):
                self._spin_trim_start.setValue(mw._spin_trim_start.value())
                self._spin_trim_end.setValue(mw._spin_trim_end.value())
        except RuntimeError:
            pass
        try:
            if hasattr(mw, '_check_extrapolate'):
                self._check_extrap.setChecked(mw._check_extrapolate.isChecked())
            if hasattr(mw, '_check_robust_peak'):
                self._check_robust.setChecked(mw._check_robust_peak.isChecked())
        except RuntimeError:
            pass
        if hasattr(mw, '_nh_custom_angles'):
            self._nh_custom_angles = list(mw._nh_custom_angles)
        self._cmb_ar_output.setCurrentIndex(0 if getattr(mw, '_ar_output_db', True) else 1)
        self._sync_nh_angle_display()

    # ── 公共接口 ──

    def set_template_params(self, params: set):
        """设置模板自动识别的参数集合 + 自动匹配测试模式。"""
        self._template_params = set(params)
        trp_keys = {k for grp in self._TRP_PARAMS for k, _ in grp[1]}
        tis_keys = {k for grp in self._TIS_PARAMS for k, _ in grp[1]}
        if params & tis_keys:
            mode = 2
        elif params & trp_keys:
            mode = 1
        else:
            mode = 0
        if mode != self._active_tab:
            self._cmb_test_mode.blockSignals(True)
            self._cmb_test_mode.setCurrentIndex(mode)
            self._cmb_test_mode.blockSignals(False)
            self._on_mode_changed(mode)
        else:
            self._rebuild_param_columns()

    def set_angle_config(self, cfg: "LagConfig", is_ar: bool = False):
        """从模板配置角度 (Gain 或 AR)。"""
        if is_ar:
            if self._ar_angle_widget:
                self._ar_angle_widget.set_config(cfg)
        else:
            if self._gain_angle_widget:
                self._gain_angle_widget.set_config(cfg)
        self._sync_to_mw()

    def update_ui(self):
        """由外部触发刷新 UI 状态。"""
        self._load_state()
        self._rebuild_param_columns()

    def get_current_params(self) -> dict:
        """获取当前参数快照。"""
        return {
            "test_mode": self._test_mode,
            "required_params": set(
                k for k, cb in self._left_checkboxes.items() if cb.isChecked()
            ),
            "extra_params": set(
                k for k, cb in self._right_checkboxes.items() if cb.isChecked()
            ),
            "lag_config": self._gain_angle_widget.get_config() if self._gain_angle_widget else LagConfig(),
            "ar_lag_config": self._ar_angle_widget.get_config() if self._ar_angle_widget else LagConfig(),
            "extrapolate": self._check_extrap.isChecked(),
            "robust_peak": self._check_robust.isChecked(),
            "ar_output_db": self._cmb_ar_output.currentData(),
            "freq_source": self._cmb_freq_src.currentData(),
            "trim_start": self._spin_trim_start.value(),
            "trim_end": self._spin_trim_end.value(),
            "step_values": self.get_selected_steps(),
            "skip_original": self.get_skip_original(),
        }

    def get_selected_steps(self) -> list:
        """获取用户选中的步进值列表。未启用多步进则返回空。"""
        if not hasattr(self, '_grp_step') or not self._grp_step.isChecked():
            return []
        steps = [s for s, cb in self._step_checks.items() if cb.isChecked()]
        custom = self._edit_step_custom.text().strip()
        if custom:
            for part in custom.split(","):
                part = part.strip()
                if part:
                    try:
                        v = float(part)
                        if v > 0 and v not in steps:
                            steps.append(v)
                    except ValueError:
                        pass
        return sorted(steps)

    def get_skip_original(self) -> bool:
        """是否跳过原始步进。"""
        return hasattr(self, '_chk_skip_original') and self._chk_skip_original.isChecked()


# ═══════════════════════════════════════════════════════════════
# ChartSettingsPage — 图表配置
# ═══════════════════════════════════════════════════════════════

class ChartSettingsPage(QWidget):
    """图表配置页面（原 PlotConfigDialog → QWidget）。

    直接读写 MainWindow 属性：
      _chart_config_required, _chart_config_extra,
      ui.spinElev, ui.spinAzim, ui.spinDpi,
      ui.checkEmbedExcel, ui.checkSavePng
    """

    chart_config_changed = Signal()

    def __init__(self, mainwindow=None):
        super().__init__(mainwindow)
        self._mw = mainwindow
        self._chart_required: Dict[str, QCheckBox] = {}
        self._chart_extra: Dict[str, QCheckBox] = {}
        self._collapse_map: dict = {}

        # 子角度选择状态
        self._gain_angles: List[float] = []
        self._gain_ranges: List[tuple] = []
        self._ar_angles: List[float] = []
        self._ar_ranges: List[tuple] = []
        self._gain_angles_x: List[float] = []
        self._gain_ranges_x: List[tuple] = []
        self._ar_angles_x: List[float] = []
        self._ar_ranges_x: List[tuple] = []

        self._setup_ui()
        self._load_state()

    def _setup_ui(self):
        from src.chart_config import ChartConfig
        labels = ChartConfig.chart_labels()
        categories = ChartConfig.chart_categories()

        self._gain_angles = []
        self._gain_ranges = []
        self._ar_angles = []
        self._ar_ranges = []
        self._gain_angles_x = []
        self._gain_ranges_x = []
        self._ar_angles_x = []
        self._ar_ranges_x = []

        grp_list: list = []

        for cat_name, keys in categories.items():
            grp = QGroupBox(cat_name)
            grp.setCheckable(True)
            grp.setChecked(True)
            grp.setStyleSheet("""
                QGroupBox { font-weight: bold; padding-top: 16px; }
                QGroupBox::indicator { width: 14px; height: 14px; margin-right: 4px; }
            """)
            grp.setCursor(Qt.PointingHandCursor)
            outer_layout = QVBoxLayout(grp)
            outer_layout.setSpacing(4)
            self._collapse_map[cat_name] = {"grp": grp, "hidden": False}
            content_widget = QWidget()
            content_layout = QVBoxLayout(content_widget)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(4)
            outer_layout.addWidget(content_widget)

            # 全选/取消全选
            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)
            btn_select_all = QPushButton(self.tr("全选"))
            btn_select_all.setFixedWidth(60)
            btn_deselect_all = QPushButton(self.tr("取消全选"))
            btn_deselect_all.setFixedWidth(72)
            btn_select_all.clicked.connect(
                lambda checked, ks=keys: (
                    [self._chart_required[k].setChecked(True) for k in ks if k in self._chart_required] or
                    [self._chart_extra[k].setChecked(True) for k in ks if k in self._chart_extra]
                ))
            btn_deselect_all.clicked.connect(
                lambda checked, ks=keys: (
                    [self._chart_required[k].setChecked(False) for k in ks if k in self._chart_required] or
                    [self._chart_extra[k].setChecked(False) for k in ks if k in self._chart_extra]
                ))
            btn_row.addWidget(btn_select_all)
            btn_row.addWidget(btn_deselect_all)
            btn_row.addStretch()
            content_layout.addLayout(btn_row)

            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            # 左列: 报告需要
            left_box = QGroupBox(self.tr("报告需要"))
            left_layout = QVBoxLayout(left_box)
            left_layout.setSpacing(3)
            for key in keys:
                row = QHBoxLayout()
                cb = QCheckBox(labels.get(key, key))
                cb.toggled.connect(lambda: self._sync_to_mw())
                row.addWidget(cb)
                self._chart_required[key] = cb
                if key in ("chart_gain_freq", "chart_ar_freq"):
                    btn = QPushButton("⚙ " + self.tr("角度..."))
                    btn.setFixedWidth(80)
                    is_ar = (key == "chart_ar_freq")
                    btn.clicked.connect(lambda checked, k=key: self._show_chart_angle_popup(k, is_left=True))
                    row.addWidget(btn)
                elif key == "chart_lag_freq":
                    btn = QPushButton("⚙ " + self.tr("角度..."))
                    btn.setFixedWidth(80)
                    btn.clicked.connect(lambda checked: self._show_chart_angle_popup("chart_lag_freq", is_left=True))
                    row.addWidget(btn)
                row.addStretch()
                left_layout.addLayout(row)
            left_layout.addStretch()
            row_layout.addWidget(left_box, 1)

            # 右列: 额外 (full_report)
            right_box = QGroupBox(self.tr("额外 (full_report)"))
            right_layout = QVBoxLayout(right_box)
            right_layout.setSpacing(3)
            for key in keys:
                row = QHBoxLayout()
                cb = QCheckBox(labels.get(key, key))
                cb.toggled.connect(lambda: self._sync_to_mw())
                row.addWidget(cb)
                self._chart_extra[key] = cb
                if key in ("chart_gain_freq", "chart_ar_freq"):
                    btn = QPushButton("⚙ " + self.tr("角度..."))
                    btn.setFixedWidth(80)
                    btn.clicked.connect(lambda checked, k=key: self._show_chart_angle_popup(k, is_left=False))
                    row.addWidget(btn)
                elif key == "chart_lag_freq":
                    btn = QPushButton("⚙ " + self.tr("角度..."))
                    btn.setFixedWidth(80)
                    btn.clicked.connect(lambda checked: self._show_chart_angle_popup("chart_lag_freq", is_left=False))
                    row.addWidget(btn)
                row.addStretch()
                right_layout.addLayout(row)
            right_layout.addStretch()
            row_layout.addWidget(right_box, 1)

            content_layout.addLayout(row_layout)
            grp_list.append(grp)

            def make_toggle(g=grp, cw=content_widget, name=cat_name):
                def toggle(checked):
                    cw.setVisible(checked)
                    self._collapse_map[name]["hidden"] = not checked
                return toggle
            grp.toggled.connect(make_toggle(grp, content_widget, cat_name))

        # 视角参数
        view_grp = QGroupBox(self.tr("视角参数"))
        view_layout = QHBoxLayout(view_grp)
        view_layout.addWidget(QLabel(self.tr("仰角:")))
        self._spin_elev = QDoubleSpinBox()
        self._spin_elev.setRange(-90, 90)
        self._spin_elev.setValue(30)
        self._spin_elev.setSuffix("°")
        self._spin_elev.setFixedWidth(80)
        self._spin_elev.valueChanged.connect(lambda: self._sync_to_mw())
        view_layout.addWidget(self._spin_elev)
        view_layout.addWidget(QLabel(self.tr("方位角:")))
        self._spin_azim = QDoubleSpinBox()
        self._spin_azim.setRange(-180, 180)
        self._spin_azim.setValue(-60)
        self._spin_azim.setSuffix("°")
        self._spin_azim.setFixedWidth(80)
        self._spin_azim.valueChanged.connect(lambda: self._sync_to_mw())
        view_layout.addWidget(self._spin_azim)
        view_layout.addWidget(QLabel("DPI:"))
        self._spin_dpi = QSpinBox()
        self._spin_dpi.setRange(72, 300)
        self._spin_dpi.setValue(150)
        self._spin_dpi.setFixedWidth(70)
        self._spin_dpi.valueChanged.connect(lambda: self._sync_to_mw())
        view_layout.addWidget(self._spin_dpi)
        view_layout.addWidget(QLabel(self.tr("采样精度:")))
        self._spin_step = QSpinBox()
        self._spin_step.setRange(1, 30)
        self._spin_step.setValue(5)
        self._spin_step.setSuffix("°")
        self._spin_step.setFixedWidth(70)
        self._spin_step.setToolTip(self.tr(
            "3D 图形采样步进 (1°–30°):\n"
            "  1°=最精细(~40K点/频点,慢)\n"
            "  5°=标准(~1.7K点/频点)\n"
            "  30°=最快(~150点/频点)\n"
            "值越小图形越精细但计算越慢。"
        ))
        self._spin_step.valueChanged.connect(lambda: self._sync_to_mw())
        view_layout.addWidget(self._spin_step)
        view_layout.addStretch()
        grp_list.append(view_grp)

        # 输出方式
        out_grp = QGroupBox(self.tr("输出方式"))
        out_layout = QHBoxLayout(out_grp)
        self._check_embed = QCheckBox(self.tr("嵌入 Excel"))
        self._check_embed.setChecked(True)
        self._check_embed.toggled.connect(lambda: self._sync_to_mw())
        self._check_png = QCheckBox(self.tr("保存 PNG 文件夹"))
        self._check_png.toggled.connect(lambda: self._sync_to_mw())
        out_layout.addWidget(self._check_embed)
        out_layout.addWidget(self._check_png)
        out_layout.addStretch()
        grp_list.append(out_grp)

        # 包装进滚动
        main_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        scroll_vbox = QVBoxLayout(scroll_content)
        for g in grp_list:
            scroll_vbox.addWidget(g)
        scroll_vbox.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def _load_state(self):
        if not self._mw:
            return
        mw = self._mw

        self._spin_elev_value = 30
        self._spin_azim_value = -60
        self._spin_dpi_value = 150

        if hasattr(mw, 'ui'):
            if hasattr(mw.ui, 'spinElev'):
                self._spin_elev.setValue(mw.ui.spinElev.value())
                self._spin_azim.setValue(mw.ui.spinAzim.value())
                self._spin_dpi.setValue(mw.ui.spinDpi.value())
                self._check_embed.setChecked(mw.ui.checkEmbedExcel.isChecked())
                self._check_png.setChecked(mw.ui.checkSavePng.isChecked())

        step_deg = 5
        if hasattr(mw, '_chart_config_required') and mw._chart_config_required is not None:
            step_deg = int(getattr(mw._chart_config_required, 'step_deg', 5))
        self._spin_step.setValue(max(1, min(30, step_deg)))

        if hasattr(mw, '_chart_config_required') and mw._chart_config_required is not None:
            req = mw._chart_config_required
            for key, cb in self._chart_required.items():
                val = getattr(req, key, False)
                cb.setChecked(val)
            self._gain_angles = list(req.gain_chart_angles)
            self._gain_ranges = list(req.gain_chart_ranges)
            self._ar_angles = list(req.ar_chart_angles)
            self._ar_ranges = list(req.ar_chart_ranges)
        if hasattr(mw, '_chart_config_extra') and mw._chart_config_extra is not None:
            xtr = mw._chart_config_extra
            for key, cb in self._chart_extra.items():
                val = getattr(xtr, key, False)
                cb.setChecked(val)
            self._gain_angles_x = list(xtr.gain_chart_angles)
            self._gain_ranges_x = list(xtr.gain_chart_ranges)
            self._ar_angles_x = list(xtr.ar_chart_angles)
            self._ar_ranges_x = list(xtr.ar_chart_ranges)

    def _sync_to_mw(self):
        """同步当前配置到 MainWindow。"""
        if not self._mw:
            return
        from src.chart_config import ChartConfig
        mw = self._mw

        step_deg = float(max(1, min(30, self._spin_step.value())))

        required = ChartConfig()
        extra = ChartConfig()
        for key in ChartConfig.all_chart_keys():
            setattr(required, key, self._chart_required.get(key, QCheckBox()).isChecked())
            setattr(extra, key, self._chart_extra.get(key, QCheckBox()).isChecked())

        required.elev = self._spin_elev.value()
        required.azim = self._spin_azim.value()
        required.dpi = self._spin_dpi.value()
        required.step_deg = step_deg
        required.embed_in_excel = self._check_embed.isChecked()
        extra.elev = required.elev
        extra.azim = required.azim
        extra.dpi = required.dpi
        extra.step_deg = step_deg
        extra.embed_in_excel = False

        required.gain_chart_angles = list(self._gain_angles)
        required.gain_chart_ranges = list(self._gain_ranges)
        required.ar_chart_angles = list(self._ar_angles)
        required.ar_chart_ranges = list(self._ar_ranges)
        extra.gain_chart_angles = list(self._gain_angles_x)
        extra.gain_chart_ranges = list(self._gain_ranges_x)
        extra.ar_chart_angles = list(self._ar_angles_x)
        extra.ar_chart_ranges = list(self._ar_ranges_x)

        mw._chart_config_required = required
        mw._chart_config_extra = extra

        if hasattr(mw, 'ui'):
            mw.ui.spinElev.setValue(int(self._spin_elev.value()))
            mw.ui.spinAzim.setValue(int(self._spin_azim.value()))
            mw.ui.spinDpi.setValue(self._spin_dpi.value())
            mw.ui.checkEmbedExcel.setChecked(self._check_embed.isChecked())
            mw.ui.checkSavePng.setChecked(self._check_png.isChecked())

        self.chart_config_changed.emit()

    def _parse_step_deg(self) -> float:
        return float(max(1, min(30, self._spin_step.value())))

    def _show_chart_angle_popup(self, chart_key: str, is_left: bool = True):
        dlg = QDialog(self)
        is_ar = (chart_key == "chart_ar_freq")
        if is_left:
            singles = self._ar_angles if is_ar else self._gain_angles
            ranges = self._ar_ranges if is_ar else self._gain_ranges
        else:
            singles = self._ar_angles_x if is_ar else self._gain_angles_x
            ranges = self._ar_ranges_x if is_ar else self._gain_ranges_x

        label_text = "AR" if is_ar else "Gain"
        dlg.setWindowTitle(self.tr("选择 {} 曲线角度 — 频点曲线").format(label_text))
        dlg.setMinimumSize(500, 420)

        import copy
        _singles = copy.deepcopy(singles)
        _ranges = copy.deepcopy(ranges)

        layout = QVBoxLayout(dlg)

        def _refresh_display():
            from ui.layout_utils import FlowLayout
            while _display_layout.count():
                item = _display_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            if _singles or _ranges:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                dw = QWidget()
                fl = FlowLayout(dw, margin=4, h_spacing=6, v_spacing=4)
                for a in sorted(set(_singles)):
                    tag = QWidget()
                    tl = QHBoxLayout(tag)
                    tl.setContentsMargins(2, 1, 2, 1)
                    tl.setSpacing(2)
                    tl.addWidget(QLabel(f"{a}°"))
                    btn_del = QPushButton("✕")
                    btn_del.setFixedSize(20, 20)
                    btn_del.setStyleSheet("padding:0;")
                    btn_del.clicked.connect(lambda checked, v=a: (_singles.remove(v), _refresh_display()))
                    tl.addWidget(btn_del)
                    fl.addWidget(tag)
                for lo, hi in sorted(set(_ranges), key=lambda x: (x[0], x[1])):
                    tag = QWidget()
                    tl = QHBoxLayout(tag)
                    tl.setContentsMargins(2, 1, 2, 1)
                    tl.setSpacing(2)
                    tl.addWidget(QLabel(f"{lo}°~{hi}°"))
                    btn_del = QPushButton("✕")
                    btn_del.setFixedSize(20, 20)
                    btn_del.setStyleSheet("padding:0;")
                    btn_del.clicked.connect(lambda checked, l=lo, h=hi: (_ranges.remove((l, h)), _refresh_display()))
                    tl.addWidget(btn_del)
                    fl.addWidget(tag)
                scroll.setWidget(dw)
                _display_layout.addWidget(scroll)
                btn_clear = QPushButton("🗑 " + self.tr("清空全部"))
                btn_clear.clicked.connect(lambda: (_singles.clear(), _ranges.clear(), _refresh_display()))
                _display_layout.addWidget(btn_clear)
            else:
                _display_layout.addWidget(QLabel(self.tr("  (暂无选择 — 将自动使用默认值)")))

        _display_grp = QGroupBox(
            self.tr("已选: {} 个单角度, {} 个范围").format(len(_singles), len(_ranges)))
        _display_layout = QVBoxLayout(_display_grp)
        _refresh_display()

        splitter = QSplitter(Qt.Vertical)
        bottom_ctls = QWidget()
        bottom_layout = QVBoxLayout(bottom_ctls)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        # 快捷预设
        quick_grp = QGroupBox(self.tr("快捷预设 — {}").format(label_text))
        quick_layout = QHBoxLayout(quick_grp)
        for a in [0, 30, 45, 60, 90]:
            btn = QPushButton(f"{a}°")
            btn.clicked.connect(lambda checked, v=a: (
                _singles.append(v) if v not in _singles else None, _refresh_display()))
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        bottom_layout.addWidget(quick_grp)

        # 自定义
        cust_grp = QGroupBox(self.tr("自定义"))
        cust_layout = QHBoxLayout(cust_grp)
        spin_custom = QDoubleSpinBox()
        spin_custom.setRange(0, 180)
        spin_custom.setValue(45)
        btn_add_custom = QPushButton("+ " + self.tr("添加"))
        btn_add_custom.clicked.connect(lambda: (
            _singles.append(spin_custom.value()) if spin_custom.value() not in _singles else None,
            _refresh_display()
        ))
        cust_layout.addWidget(QLabel(self.tr("角度:")))
        cust_layout.addWidget(spin_custom)
        cust_layout.addWidget(btn_add_custom)
        cust_layout.addStretch()
        bottom_layout.addWidget(cust_grp)

        # 步进
        step_grp = QGroupBox(self.tr("步进批量生成"))
        step_layout = QHBoxLayout(step_grp)
        spin_start = QDoubleSpinBox()
        spin_start.setRange(0, 180)
        spin_start.setValue(0)
        spin_end = QDoubleSpinBox()
        spin_end.setRange(0, 180)
        spin_end.setValue(90)
        spin_step = QDoubleSpinBox()
        spin_step.setRange(1, 90)
        spin_step.setValue(10)
        btn_gen = QPushButton(self.tr("生成"))
        btn_gen.clicked.connect(lambda: (
            [_singles.append(round(float(a), 6))
             for a in np.arange(spin_start.value(), spin_end.value() + 1, spin_step.value())
             if round(float(a), 6) not in _singles],
            _refresh_display()
        ))
        step_layout.addWidget(QLabel(self.tr("起:")))
        step_layout.addWidget(spin_start)
        step_layout.addWidget(QLabel(self.tr("止:")))
        step_layout.addWidget(spin_end)
        step_layout.addWidget(QLabel(self.tr("步:")))
        step_layout.addWidget(spin_step)
        step_layout.addWidget(btn_gen)
        bottom_layout.addWidget(step_grp)

        # 范围
        range_grp = QGroupBox(self.tr("角度范围"))
        range_layout = QHBoxLayout(range_grp)
        spin_rs = QDoubleSpinBox()
        spin_rs.setRange(0, 180)
        spin_rs.setValue(0)
        spin_re = QDoubleSpinBox()
        spin_re.setRange(0, 180)
        spin_re.setValue(90)

        def _add_range():
            lo, hi = spin_rs.value(), spin_re.value()
            key = (min(lo, hi), max(lo, hi))
            if key not in _ranges:
                _ranges.append(key)
                _refresh_display()

        btn_add_range = QPushButton(self.tr("添加范围"))
        btn_add_range.clicked.connect(_add_range)
        range_layout.addWidget(QLabel(self.tr("起:")))
        range_layout.addWidget(spin_rs)
        range_layout.addWidget(QLabel(self.tr("止:")))
        range_layout.addWidget(spin_re)
        range_layout.addWidget(btn_add_range)
        range_layout.addStretch()
        bottom_layout.addWidget(range_grp)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            singles.clear(),
            singles.extend(sorted(set(_singles))),
            ranges.clear(),
            ranges.extend(sorted(set(_ranges), key=lambda x: (x[0], x[1]))),
            dlg.accept()
        ))
        btns.rejected.connect(dlg.reject)
        bottom_layout.addWidget(btns)

        splitter.addWidget(_display_grp)
        splitter.addWidget(bottom_ctls)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        layout.addWidget(splitter)
        dlg.exec()
        self._sync_to_mw()

    # ── 公共接口 ──

    def get_chart_config(self) -> tuple:
        """返回 (chart_config_required, chart_config_extra)。"""
        from src.chart_config import ChartConfig

        def _build(required_map, extra_map, gain_angles, gain_ranges, ar_angles, ar_ranges):
            cfg = ChartConfig()
            for key in ChartConfig.all_chart_keys():
                setattr(cfg, key, required_map.get(key, QCheckBox()).isChecked())
            cfg.elev = self._spin_elev.value()
            cfg.azim = self._spin_azim.value()
            cfg.dpi = self._spin_dpi.value()
            cfg.step_deg = self._parse_step_deg()
            cfg.embed_in_excel = self._check_embed.isChecked()
            cfg.gain_chart_angles = list(gain_angles)
            cfg.gain_chart_ranges = list(gain_ranges)
            cfg.ar_chart_angles = list(ar_angles)
            cfg.ar_chart_ranges = list(ar_ranges)
            return cfg

        req = _build(self._chart_required, self._chart_extra,
                     self._gain_angles, self._gain_ranges,
                     self._ar_angles, self._ar_ranges)
        xtr = _build(self._chart_extra, self._chart_extra,
                     self._gain_angles_x, self._gain_ranges_x,
                     self._ar_angles_x, self._ar_ranges_x)
        xtr.embed_in_excel = False
        return req, xtr

    def update_ui(self):
        """由外部触发刷新 UI 状态。"""
        self._load_state()
