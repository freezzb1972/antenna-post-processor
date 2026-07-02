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
    QListWidget,
    QPushButton,
    QRadioButton,
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
from src.azimuth_config import AzimuthReportConfig
from src.sheet_file_matcher import extract_key, sanitize_sheet_name
from ui.layout_utils import FlowLayout, auto_size_dialog
from ui.widgets import (AnglePickerWidget, DataFileSelector, OutputSettingsGroup,
    TemplateSourceRow, ThinSplitter)

if TYPE_CHECKING:
    pass


# ═══════════════════════════════════════════════════════════════
# FileSettingsPage — 输入输出
# ═══════════════════════════════════════════════════════════════

def _make_hsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


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
        if hasattr(self, '_tpl_path_label') and self._tpl_path_label is not None:
            self._tpl_path_label.setText(v)
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
        main_layout.setSpacing(0)

        # 左右分栏：左=输入设置 | 右=输出设置
        h_splitter = ThinSplitter(Qt.Horizontal)

        # === 左侧：输入设置（上下分栏：模版 + 数据文件） ===
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        v_splitter = ThinSplitter(Qt.Vertical)

        # 报告模版组
        tpl_grp = QGroupBox(self.tr("报告模版"))
        tpl_layout = QVBoxLayout(tpl_grp)
        tpl_layout.setSpacing(4)
        # 第一行：预设下拉 + 按钮
        row1 = QHBoxLayout()
        self._tpl_row = TemplateSourceRow(
            on_browse=self._on_browse_template,
            on_preview=self._on_preview_report,
        )
        # 从 TemplateSourceRow 提取内部控件重组布局
        # TemplateSourceRow 有: _cmb_preset, 两个按钮, _lbl_path
        # 直接用其内部布局
        if self._mw and hasattr(self._mw, '_tm'):
            presets = self._mw._tm.get_all_templates()
            presets_list = [
                {"manufacturer": t.manufacturer, "name": t.name, "path": t.path}
                for t in presets
            ]
            self._tpl_row.populate_presets(presets_list)
        self._tpl_row.template_changed.connect(self._on_preset_template_selected)
        tpl_layout.addWidget(self._tpl_row)

        # 第二行：模版路径单独显示, 与 TemplateSourceRow._lbl_path 同步
        self._tpl_path_label = QLineEdit()
        self._tpl_row.template_changed.connect(self._tpl_path_label.setText)
        self._tpl_path_label.setReadOnly(True)
        self._tpl_path_label.setPlaceholderText(self.tr("(未选择模版)"))
        tpl_layout.addWidget(self._tpl_path_label)

        v_splitter.addWidget(tpl_grp)

        # 数据文件选择器 (widgets.DataFileSelector)
        from ui.widgets import DataFileSelector
        self._data_sel = DataFileSelector()
        ds = self._data_sel
        ds.btn_add_files.clicked.connect(self._on_add_data_files)
        ds.btn_clear_selected.clicked.connect(self._on_clear_selected_files)
        ds.btn_clear_all.clicked.connect(self._on_clear_all_files)
        ds.btn_auto_match.clicked.connect(self._on_auto_match)
        ds.cmb_naming_mode.currentIndexChanged.connect(self._on_naming_mode_changed)

        # 公开属性别名 (保持旧代码兼容)
        self._btn_add_files = ds.btn_add_files
        self._btn_clear_selected = ds.btn_clear_selected
        self._btn_clear_all = ds.btn_clear_all
        self._file_list_widget = ds.file_list_widget
        self._match_table = ds.match_table
        self._btn_auto_match = ds.btn_auto_match
        self._lbl_match_status = ds.lbl_match_status
        self._lbl_naming_mode = ds.lbl_naming_mode
        self._cmb_naming_mode = ds.cmb_naming_mode
        self._check_chart_eff = ds.check_chart_eff
        self._check_chart_lag = ds.check_chart_lag

        v_splitter.addWidget(ds)
        left_layout.addWidget(v_splitter)
        h_splitter.addWidget(left_widget)

        # === 右侧：输出设置 ===
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        # ── 输出选项 ──
        out_grp = QGroupBox(self.tr("输出设置"))
        out_layout = QVBoxLayout(out_grp)
        out_layout.setSpacing(6)

        # 1) 天线参数报告 (.xlsx)
        self._check_out_excel = QCheckBox(self.tr("天线参数报告 (.xlsx)"))
        self._check_out_excel.setChecked(True)
        out_layout.addWidget(self._check_out_excel)

        row_xl_dir = QHBoxLayout()
        self._edit_out_dir = QLineEdit()
        self._edit_out_dir.setPlaceholderText(self.tr("默认: ./output"))
        row_xl_dir.addWidget(self._edit_out_dir, 1)
        btn_xl_browse = QPushButton(self.tr("浏览..."))
        btn_xl_browse.clicked.connect(self._on_browse_output)
        row_xl_dir.addWidget(btn_xl_browse)
        out_layout.addLayout(row_xl_dir)

        row_xl_fn = QHBoxLayout()
        row_xl_fn.addWidget(QLabel(self.tr("文件名:")))
        self._edit_out_name = QLineEdit("antenna_report.xlsx")
        row_xl_fn.addWidget(self._edit_out_name, 1)
        out_layout.addLayout(row_xl_fn)

        self._check_out_excel.toggled.connect(lambda c: (
            self._edit_out_dir.setEnabled(c),
            self._edit_out_name.setEnabled(c),
        ))

        out_layout.addWidget(_make_hsep())

        # 2) 图表报告 (.docx)
        self._check_out_word = QCheckBox(self.tr("图表报告 (.docx)"))
        out_layout.addWidget(self._check_out_word)

        row_word_dir = QHBoxLayout()
        self._edit_az_chart_dir = QLineEdit()
        self._edit_az_chart_dir.setPlaceholderText(self.tr("默认: 源文件目录"))
        row_word_dir.addWidget(self._edit_az_chart_dir, 1)
        btn_word_browse = QPushButton(self.tr("浏览..."))
        btn_word_browse.clicked.connect(self._on_browse_az_chart_dir)
        row_word_dir.addWidget(btn_word_browse)
        out_layout.addLayout(row_word_dir)

        row_word_fn = QHBoxLayout()
        row_word_fn.addWidget(QLabel(self.tr("文件名:")))
        self._edit_az_chart_fn = QLineEdit()
        self._edit_az_chart_fn.setPlaceholderText(self.tr("默认: 源文件名图表报告.docx"))
        row_word_fn.addWidget(self._edit_az_chart_fn, 1)
        out_layout.addLayout(row_word_fn)

        self._check_out_word.toggled.connect(lambda c: (
            self._edit_az_chart_dir.setEnabled(c),
            self._edit_az_chart_fn.setEnabled(c),
            self._sync_azimuth_cut_switch(),
        ))

        row_word_settings = QHBoxLayout()
        btn_word_layout = QPushButton(self.tr("Word 输出布局设置..."))
        btn_word_layout.clicked.connect(self._show_word_layout_dialog)
        row_word_settings.addWidget(btn_word_layout)
        row_word_settings.addStretch()
        out_layout.addLayout(row_word_settings)

        # 频段间隔设置 (B类 vs频率曲线多段打断)
        row_gap = QHBoxLayout()
        row_gap.addWidget(QLabel(self.tr("频段间隔 (MHz):")))
        self._spin_freq_gap = QSpinBox()
        self._spin_freq_gap.setRange(0, 999)
        self._spin_freq_gap.setValue(10)
        self._spin_freq_gap.setToolTip(self.tr(
            "B类 vs频率曲线多段间隔阈值。0=不打断单轴；>0=相邻频点差超此值时分段绘制"))
        self._spin_freq_gap.valueChanged.connect(lambda v: (
            setattr(getattr(self._mw, '_azimuth_config', None), 'freq_gap_mhz', v)
            if self._mw and getattr(self._mw, '_azimuth_config', None) else None
        ))
        row_gap.addWidget(self._spin_freq_gap)
        row_gap.addStretch()
        out_layout.addLayout(row_gap)

        out_layout.addWidget(_make_hsep())

        # 3) 中间数据文件 (.xlsx)
        self._check_out_data = QCheckBox(self.tr("中间数据文件 (.xlsx)"))
        out_layout.addWidget(self._check_out_data)

        # Gain
        row_gain_dir = QHBoxLayout()
        self._edit_az_gain_dir = QLineEdit()
        self._edit_az_gain_dir.setPlaceholderText(self.tr("默认: 源文件目录"))
        row_gain_dir.addWidget(self._edit_az_gain_dir, 1)
        btn_gain_browse = QPushButton(self.tr("浏览..."))
        btn_gain_browse.clicked.connect(self._on_browse_az_gain_dir)
        row_gain_dir.addWidget(btn_gain_browse)
        out_layout.addLayout(row_gain_dir)

        row_gain_fn = QHBoxLayout()
        row_gain_fn.addWidget(QLabel(self.tr("Gain 文件名:")))
        self._edit_az_gain_fn = QLineEdit()
        self._edit_az_gain_fn.setPlaceholderText(self.tr("默认: 源文件名Gain.xlsx"))
        row_gain_fn.addWidget(self._edit_az_gain_fn, 1)
        out_layout.addLayout(row_gain_fn)

        # AR
        row_ar_dir = QHBoxLayout()
        self._edit_az_ar_dir = QLineEdit()
        self._edit_az_ar_dir.setPlaceholderText(self.tr("默认: 源文件目录"))
        row_ar_dir.addWidget(self._edit_az_ar_dir, 1)
        btn_ar_browse = QPushButton(self.tr("浏览..."))
        btn_ar_browse.clicked.connect(self._on_browse_az_ar_dir)
        row_ar_dir.addWidget(btn_ar_browse)
        out_layout.addLayout(row_ar_dir)

        row_ar_fn = QHBoxLayout()
        row_ar_fn.addWidget(QLabel(self.tr("AR 文件名:")))
        self._edit_az_ar_fn = QLineEdit()
        self._edit_az_ar_fn.setPlaceholderText(self.tr("默认: 源文件名AR.xlsx"))
        row_ar_fn.addWidget(self._edit_az_ar_fn, 1)
        out_layout.addLayout(row_ar_fn)

        self._check_out_data.toggled.connect(lambda c: (
            self._edit_az_gain_dir.setEnabled(c),
            self._edit_az_gain_fn.setEnabled(c),
            self._edit_az_ar_dir.setEnabled(c),
            self._edit_az_ar_fn.setEnabled(c),
            self._sync_azimuth_cut_switch(),
        ))

        right_layout.addWidget(out_grp)

        self._check_save_task = QCheckBox(
            self.tr("保存任务包 (.ant) — 下次双击秒开，不重算"))
        self._check_save_task.setChecked(False)
        self._check_save_task.setToolTip(
            self.tr("保存为 .ant 任务包后，下次双击即可直接查看结果，无需重新计算。"))
        right_layout.addWidget(self._check_save_task)
        right_layout.addStretch()

        h_splitter.addWidget(right_widget)
        h_splitter.setSizes([600, 300])
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setWidget(h_splitter)
        main_layout.addWidget(scroll_area, 1)

    def _init_state(self):
        """初始化本地状态（无 MainWindow 时使用）。"""
        self._local: dict = {}
        self._file_entries: List[FileEntry] = []
        self._worksheet_naming_mode: int = 0
        from src.config_manager import get_config_manager
        self._cfg = get_config_manager()
        self._load_azimuth_state()

    def _show_word_layout_dialog(self):
        """Word 输出布局设置子对话框: 批量模式 + 图表排序。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Word 输出布局设置"))
        dlg.setMinimumSize(550, 400)
        layout = QVBoxLayout(dlg)

        # 批量模式
        mode_grp = QGroupBox(self.tr("批量输出模式"))
        mode_layout = QVBoxLayout(mode_grp)
        self._radio_by_freq = QRadioButton(self.tr("按频点: 每频点全部图 → 下一频点"))
        self._radio_by_type = QRadioButton(self.tr("按图表类型: 每类图全频点 → 下一类"))
        self._radio_by_freq.setChecked(True)
        mode_layout.addWidget(self._radio_by_freq)
        mode_layout.addWidget(self._radio_by_type)
        layout.addWidget(mode_grp)

        # 图表排序列表
        sort_grp = QGroupBox(self.tr("图表顺序 (上移/下移调整)"))
        sort_layout = QVBoxLayout(sort_grp)
        self._word_chart_list = QListWidget()
        self._word_chart_list.setDragDropMode(QAbstractItemView.InternalMove)
        self._word_chart_list.setSelectionMode(QAbstractItemView.SingleSelection)
        # 默认图表类型列表
        default_items = [
            self.tr("3D Gain Pattern"),
            self.tr("3D E_θ Pattern"),
            self.tr("3D E_φ Pattern"),
            self.tr("3D AR Pattern"),
            self.tr("Gain Azimuth Cut"),
            self.tr("AR Azimuth Cut"),
            self.tr("2D Polar Cuts"),
            self.tr("2D Rectangular Cuts"),
            self.tr("Efficiency vs Freq"),
            self.tr("Peak Gain vs Freq"),
            self.tr("Directivity vs Freq"),
            self.tr("TRP vs Freq"),
            self.tr("AR vs Freq"),
            self.tr("LAG vs Freq"),
        ]
        for item in default_items:
            self._word_chart_list.addItem(item)
        sort_layout.addWidget(self._word_chart_list)

        btn_row = QHBoxLayout()
        btn_up = QPushButton(self.tr("↑ 上移"))
        btn_down = QPushButton(self.tr("↓ 下移"))
        btn_reset = QPushButton(self.tr("恢复默认"))
        btn_up.clicked.connect(lambda: _move_item(-1))
        btn_down.clicked.connect(lambda: _move_item(1))
        btn_reset.clicked.connect(lambda: (
            self._word_chart_list.clear(),
            [self._word_chart_list.addItem(item) for item in default_items]
        ))
        btn_row.addWidget(btn_up)
        btn_row.addWidget(btn_down)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        sort_layout.addLayout(btn_row)
        layout.addWidget(sort_grp)

        def _move_item(direction):
            row = self._word_chart_list.currentRow()
            if 0 <= row < self._word_chart_list.count():
                item = self._word_chart_list.takeItem(row)
                new_row = max(0, min(self._word_chart_list.count(), row + direction))
                self._word_chart_list.insertItem(new_row, item)
                self._word_chart_list.setCurrentRow(new_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    def _load_azimuth_state(self):
        """从 MainWindow 加载输出设置。"""
        if not self._mw:
            return
        # Excel output dir/name
        if hasattr(self._mw, 'ui'):
            if hasattr(self, '_edit_out_dir'):
                self._edit_out_dir.setText(self._mw.ui.editOutputDir.text().strip())
            if hasattr(self, '_edit_out_name'):
                self._edit_out_name.setText(self._mw.ui.editOutputName.text().strip())
        # Azimuth config
        az = getattr(self._mw, '_azimuth_config', None)
        if az is None:
            return
        if hasattr(self, '_edit_az_chart_dir'):
            self._edit_az_chart_dir.setText(az.chart_output_dir)
        if hasattr(self, '_edit_az_chart_fn'):
            self._edit_az_chart_fn.setText(az.chart_output_filename)
        if hasattr(self, '_edit_az_gain_dir'):
            self._edit_az_gain_dir.setText(az.data_gain_output_dir)
        if hasattr(self, '_edit_az_gain_fn'):
            self._edit_az_gain_fn.setText(az.data_gain_output_filename)
        if hasattr(self, '_edit_az_ar_dir'):
            self._edit_az_ar_dir.setText(az.data_ar_output_dir)
        if hasattr(self, '_edit_az_ar_fn'):
            self._edit_az_ar_fn.setText(az.data_ar_output_filename)

    def _sync_azimuth_state(self):
        """将输出设置写回 MainWindow。"""
        if not self._mw:
            return
        # Excel output
        if hasattr(self._mw, 'ui'):
            if hasattr(self, '_edit_out_dir'):
                self._mw.ui.editOutputDir.setText(self._edit_out_dir.text().strip())
            if hasattr(self, '_edit_out_name'):
                self._mw.ui.editOutputName.setText(self._edit_out_name.text().strip())
        # Azimuth config
        az = getattr(self._mw, '_azimuth_config', None)
        if az is None:
            return
        if hasattr(self, '_edit_az_chart_dir'):
            az.chart_output_dir = self._edit_az_chart_dir.text().strip()
        if hasattr(self, '_edit_az_chart_fn'):
            az.chart_output_filename = self._edit_az_chart_fn.text().strip()
        if hasattr(self, '_edit_az_gain_dir'):
            az.data_gain_output_dir = self._edit_az_gain_dir.text().strip()
        if hasattr(self, '_edit_az_gain_fn'):
            az.data_gain_output_filename = self._edit_az_gain_fn.text().strip()
        if hasattr(self, '_edit_az_ar_dir'):
            az.data_ar_output_dir = self._edit_az_ar_dir.text().strip()
        if hasattr(self, '_edit_az_ar_fn'):
            az.data_ar_output_filename = self._edit_az_ar_fn.text().strip()

    def _sync_azimuth_cut_switch(self):
        """勾选 Word 或数据输出时自动开启/关闭方位面开关。"""
        if not self._mw:
            return
        az = getattr(self._mw, '_azimuth_config', None)
        if az is None:
            return
        need_azimuth = (
            getattr(self, '_check_out_word', None) is not None and self._check_out_word.isChecked()
        ) or (
            getattr(self, '_check_out_data', None) is not None and self._check_out_data.isChecked()
        )
        az.cut_azimuth_polar = need_azimuth

    def get_output_flags(self):
        """返回输出开关: (excel, word, data)。"""
        return (
            self._check_out_excel.isChecked() if hasattr(self, '_check_out_excel') else True,
            self._check_out_word.isChecked() if hasattr(self, '_check_out_word') else False,
            self._check_out_data.isChecked() if hasattr(self, '_check_out_data') else False,
        )

    # ── 方位面输出目录浏览 ──

    def _on_browse_az_chart_dir(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, self.tr("选择图表输出目录 (Word)"))
        if d and hasattr(self, '_edit_az_chart_dir'):
            self._edit_az_chart_dir.setText(d)
            self._sync_azimuth_state()

    def _on_browse_az_gain_dir(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, self.tr("选择 Gain 数据输出目录"))
        if d and hasattr(self, '_edit_az_gain_dir'):
            self._edit_az_gain_dir.setText(d)
            self._sync_azimuth_state()

    def _on_browse_az_ar_dir(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, self.tr("选择 AR 数据输出目录"))
        if d and hasattr(self, '_edit_az_ar_dir'):
            self._edit_az_ar_dir.setText(d)
            self._sync_azimuth_state()
        if self._mw:
            from src.config_manager import get_config_manager
            self._cfg = get_config_manager()
        # 绑定 mainwindow 已有的文件列表
        self._sync_from_mw()

    @property
    def _data_stale(self) -> bool:
        if self._mw:
            return getattr(self._mw, '_data_stale', True)
        return self._local.setdefault("data_stale", True)

    @_data_stale.setter
    def _data_stale(self, v: bool):
        if self._mw:
            self._mw._data_stale = v
        self._local["data_stale"] = v

    def _sync_from_mw(self):
        """从 MainWindow 同步已有状态。"""
        if not self._mw:
            return
        self._file_entries = list(getattr(self._mw, '_file_entries', []))
        self._worksheet_naming_mode = getattr(self._mw, '_worksheet_naming_mode', 0)
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
        else:
            print(f"[FileSettingsPage] {message}")

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
        self._tpl_row.set_path(path)
        if self._cfg:
            self._cfg.config.last_template_path = path
            self._cfg._dirty = True
        if self._mw:
            self._mw._chart_config_required = None
            self._mw._cached_template_params = set()
            self._mw._auto_apply_template_params()
            # 立即从模板更新角度配置（不等自动匹配）
            try:
                from src.excel_reader import read_template
                sheets = read_template(path)
                self._mw._auto_update_angle_config_from_template(sheets)
            except Exception:
                pass
        self._match_table.setRowCount(0)
        self._lbl_match_status.setText("")
        if self._data_file_paths:
            self._on_auto_match()

    def _on_preset_template_selected(self, path: str):
        """内置预设被选中 → 更新模板路径并触发自动匹配。"""
        if not path:
            return
        self._template_path = path
        self._tpl_row.set_path(path)
        if self._cfg:
            self._cfg.config.last_template_path = path
            self._cfg._dirty = True
        if self._mw:
            self._mw._chart_config_required = None
            self._mw._cached_template_params = set()
            self._mw._auto_apply_template_params()
            # 立即从模板更新角度配置（不等自动匹配）
            try:
                from src.excel_reader import read_template
                sheets = read_template(path)
                self._mw._auto_update_angle_config_from_template(sheets)
            except Exception:
                pass
        self._match_table.setRowCount(0)
        self._lbl_match_status.setText("")
        if self._data_file_paths:
            self._on_auto_match()

    def _on_preview_report(self):
        """打开模板列预览对话框 — 按列显示、参数修正、另存预设。"""
        tpl_path = self._template_path
        if not tpl_path:
            QMessageBox.warning(self, self.tr("提示"), self.tr("请先选择模板文件。"))
            return
        if not Path(tpl_path).exists():
            QMessageBox.warning(self, self.tr("错误"), self.tr("模板文件不存在。"))
            return

        try:
            from src.column_mapping import detect_columns_from_template, ALL_COL_TYPE_LABELS, TemplatePreset, save_preset
            mappings = detect_columns_from_template(tpl_path)
        except Exception as e:
            QMessageBox.warning(self, self.tr("检测失败"), self.tr(f"列头检测失败:\n{e}"))
            return

        import re
        from src.lag_config import _RE_LAG_SINGLE, _RE_LAG_RANGE
        # AR 正则 — lag_config 中为局部变量
        _RE_AR_S = re.compile(
            r"(?:AR|Axial\s*Ratio)\s+at\s+(?:Theta|θ)\s*[=＝]\s*(\d+\.?\d*)",
            re.IGNORECASE)
        _RE_AR_R = re.compile(
            r"(?:AR|Axial\s*Ratio)\s+at\s+(?:Theta|θ)\s*[=＝]\s*(\d+\.?\d*)\s*[-–—~]\s*(\d+\.?\d*)",
            re.IGNORECASE)

        def _extract_angle(raw: str, ctype: str) -> str:
            if ctype in ("lag_single", "ar_single"):
                rx = _RE_LAG_SINGLE if ctype == "lag_single" else _RE_AR_S
                m = rx.search(raw)
                return f"{m.group(1)}°" if m else ""
            if ctype in ("lag_range", "ar_range"):
                rx = _RE_LAG_RANGE if ctype == "lag_range" else _RE_AR_R
                m = rx.search(raw)
                return f"{m.group(1)}–{m.group(2)}°" if m else ""
            return ""

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("模板列预览"))
        dlg.setMinimumSize(800, 400)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowMaximizeButtonHint)
        layout = QVBoxLayout(dlg)

        # 转置表: 每列=模版一列, 行=属性
        n = len(mappings)
        table = QTableWidget()
        table.setRowCount(7)
        table.setColumnCount(n)
        ROW_LABELS = [self.tr("列号"), self.tr("列头文本"), self.tr("检测类型"),
                       self.tr("参数值"), self.tr("修正类型"), self.tr("修正参数"), self.tr("操作")]
        table.setVerticalHeaderLabels(ROW_LABELS)
        table.horizontalHeader().hide()
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        detected = 0
        for ci, m in enumerate(mappings):
            table.setItem(0, ci, QTableWidgetItem(m.col_letter))
            table.setItem(1, ci, QTableWidgetItem(m.raw_header))
            table.setItem(2, ci, QTableWidgetItem(m.detected_type))
            angle_val = _extract_angle(m.raw_header, m.detected_type)
            table.setItem(3, ci, QTableWidgetItem(angle_val))
            # 修正类型下拉
            cmb = QComboBox()
            for ct, label in ALL_COL_TYPE_LABELS:
                cmb.addItem(label, ct)
            idx = cmb.findData(m.detected_type)
            if idx >= 0:
                cmb.setCurrentIndex(idx)
            table.setCellWidget(4, ci, cmb)
            # 修正参数输入（角度/参数值）
            edit_param = QLineEdit()
            edit_param.setPlaceholderText(self.tr("输入参数值"))
            edit_param.setText(angle_val)
            table.setCellWidget(5, ci, edit_param)
            # 修改按钮（所有类型可用）
            btn_mod = QPushButton(self.tr("应用"))
            btn_mod.setFixedWidth(50)
            btn_mod.clicked.connect(lambda checked, idx=ci, ct=m.detected_type:
                self._on_preview_apply(dlg, idx, ct, table))
            table.setCellWidget(6, ci, btn_mod)
            if m.detected_type != "unknown":
                detected += 1
        table.resizeColumnsToContents()
        table.setMinimumHeight(280)
        layout.addWidget(table)

        # 摘要
        summary = QLabel(
            self.tr("共 {} 列, 识别 {} 列, {} 列未识别, 识别类型见「检测类型」行").format(
                len(mappings), detected, len(mappings) - detected))
        summary.setStyleSheet("")
        layout.addWidget(summary)

        # 按钮
        btn_row = QHBoxLayout()
        btn_save = QPushButton(self.tr("💾 保存为模板预设"))
        btn_close = QPushButton(self.tr("关闭"))
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        btn_close.clicked.connect(dlg.accept)
        save_template_path = tpl_path

        def _on_save():
            col_mappings = []
            for ci in range(n):
                col_letter = table.item(0, ci).text()
                raw = table.item(1, ci).text()
                detected_type = table.item(2, ci).text()
                cmb = table.cellWidget(4, ci)
                confirmed = cmb.currentData() if cmb else ""
                from src.column_mapping import ColumnMapping as CM
                col_mappings.append(CM(
                    col_letter=col_letter, col_index=ci + 1,
                    raw_header=raw, detected_type=detected_type,
                    confirmed_type=confirmed if confirmed != detected_type else "",
                ))
            name = Path(save_template_path).stem
            ext = Path(save_template_path).suffix.lstrip(".")
            preset = TemplatePreset(
                name=name, path=save_template_path, file_type=ext,
                column_mappings=col_mappings,
            )
            save_preset(preset)
            QMessageBox.information(dlg, self.tr("保存成功"),
                self.tr(f"模板预设已保存: {name}\n包含 {len(col_mappings)} 列映射"))

        btn_save.clicked.connect(_on_save)
        layout.addLayout(btn_row)
        dlg.exec()

    def _on_preview_apply(self, parent_dlg, col: int, ctype: str, table):
        """应用修正: 读取修正类型+参数值，更新检测类型并同步到计算参数。"""
        cmb = table.cellWidget(4, col)
        edit_param = table.cellWidget(5, col)
        if not cmb or not edit_param:
            return
        new_type = cmb.currentData() or ctype
        param_val = edit_param.text().strip()
        # 更新检测类型显示
        table.item(2, col).setText(new_type)
        table.item(3, col).setText(param_val)
        # 同步到计算参数（通过 MainWindow 属性）
        if self._mw:
            if new_type in ("lag_single", "lag_range"):
                try:
                    val = float(param_val.replace("°", "").split("–")[0])
                except ValueError:
                    val = None
                if val is not None and hasattr(self._mw, '_lag_config'):
                    if new_type == "lag_single":
                        self._mw._lag_config.add_single(val)
                    else:
                        parts = param_val.replace("°", "").split("–")
                        if len(parts) == 2:
                            self._mw._lag_config.add_range(float(parts[0]), float(parts[1]))
                    self._mw._sync_quick_buttons()
                    self._mw._update_lag_display()
            elif new_type in ("ar_single", "ar_range"):
                try:
                    val = float(param_val.replace("°", "").split("–")[0])
                except ValueError:
                    val = None
                if val is not None and hasattr(self._mw, '_ar_lag_config'):
                    if new_type == "ar_single":
                        self._mw._ar_lag_config.add_single(val)
                    else:
                        parts = param_val.replace("°", "").split("–")
                        if len(parts) == 2:
                            self._mw._ar_lag_config.add_range(float(parts[0]), float(parts[1]))
            self._mw._log(f"✓ 已应用: {new_type} = {param_val}")
        QMessageBox.information(parent_dlg, self.tr("已应用"),
            self.tr(f"已更新参数: {new_type} = {param_val}"))

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
            if hasattr(self, '_edit_out_dir'): self._edit_out_dir.setText(path)
            if self._mw and hasattr(self._mw, 'ui'): self._mw.ui.editOutputDir.setText(path)
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
                    self._log(f"⚠ 匹配表中 {fp} 已不在数据文件列表中，已重置")

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
        ("圆极化 (RHCP/LHCP)", [
            ("rhcp_single", "RHCP Gain @ θ（单角度）"),
            ("cp_xpi_single", "CP-XPI @ θ（单角度）"),
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
        self._left_checkboxes: Dict[str, QCheckBox] = {}
        self._right_checkboxes: Dict[str, QCheckBox] = {}
        self._left_scroll: Optional[QScrollArea] = None
        self._right_scroll: Optional[QScrollArea] = None

        self._setup_ui()
        self._load_state()
        self._rebuild_param_columns()

    # _required_params / _extra_params 代理到 MainWindow (单一数据源)
    @property
    def _required_params(self) -> set:
        return getattr(self._mw, '_required_params', set()) if self._mw else set()

    @_required_params.setter
    def _required_params(self, v: set):
        if self._mw:
            self._mw._required_params = v

    @property
    def _extra_params(self) -> set:
        return getattr(self._mw, '_extra_params', set()) if self._mw else set()

    @_extra_params.setter
    def _extra_params(self, v: set):
        if self._mw:
            self._mw._extra_params = v

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

        # 左右分栏（QSplitter 可手动拖动调整宽度）
        splitter_widget = ThinSplitter(Qt.Horizontal)
        splitter_widget.setChildrenCollapsible(False)

        left_grp = QGroupBox(self.tr("天线参数（模板识别 + full_report）"))
        left_layout = QVBoxLayout(left_grp)
        self._left_scroll = QScrollArea()
        self._left_scroll.setWidgetResizable(True)
        self._left_scroll.setFrameShape(QScrollArea.NoFrame)
        left_layout.addWidget(self._left_scroll)
        splitter_widget.addWidget(left_grp)

        right_grp = QGroupBox(self.tr("算法与步进"))
        right_layout = QVBoxLayout(right_grp)
        self._right_scroll = QScrollArea()
        self._right_scroll.setWidgetResizable(True)
        self._right_scroll.setFrameShape(QScrollArea.NoFrame)
        right_layout.addWidget(self._right_scroll)
        splitter_widget.addWidget(right_grp)

        splitter_widget.setSizes([600, 300])  # 左宽右窄初始比例
        param_layout.addWidget(splitter_widget, 1)
        # 右侧栏内容: 算法选项 + 多步进
        right_content = QWidget()
        right_lyt = QVBoxLayout(right_content)
        right_lyt.setSpacing(8)

        algo_grp = QGroupBox(self.tr("算法选项"))
        algo_layout = QVBoxLayout(algo_grp)
        algo_layout.setSpacing(4)

        self._freq_widget = QWidget()
        freq_row = QHBoxLayout(self._freq_widget)
        freq_row.setContentsMargins(0, 0, 0, 0)
        freq_row.addWidget(QLabel(self.tr("频点:")))
        self._cmb_freq_src = QComboBox()
        self._cmb_freq_src.addItem(self.tr("数据源"), "datasource")
        self._cmb_freq_src.addItem(self.tr("模板"), "template")
        self._cmb_freq_src.currentIndexChanged.connect(lambda: self._sync_to_mw())
        freq_row.addWidget(self._cmb_freq_src)
        algo_layout.addWidget(self._freq_widget)

        trim_row = QHBoxLayout()
        trim_row.addWidget(QLabel(self.tr("去前")))
        self._spin_trim_start = QSpinBox()
        self._spin_trim_start.setRange(0, 50)
        self._spin_trim_start.setFixedWidth(50)
        self._spin_trim_start.valueChanged.connect(lambda: self._sync_to_mw())
        trim_row.addWidget(self._spin_trim_start)
        trim_row.addWidget(QLabel(self.tr("去后")))
        self._spin_trim_end = QSpinBox()
        self._spin_trim_end.setRange(0, 50)
        self._spin_trim_end.setFixedWidth(50)
        self._spin_trim_end.valueChanged.connect(lambda: self._sync_to_mw())
        trim_row.addWidget(self._spin_trim_end)
        algo_layout.addLayout(trim_row)

        self._check_extrap = QCheckBox(self.tr("Theta 外推 180°"))
        self._check_extrap.toggled.connect(lambda: self._sync_to_mw())
        algo_layout.addWidget(self._check_extrap)
        self._check_robust = QCheckBox(self.tr("Robust peak"))
        self._check_robust.toggled.connect(lambda: self._sync_to_mw())
        algo_layout.addWidget(self._check_robust)

        # AR 输出单位（数据属性，在 AR 弹窗中设置）
        self._cmb_ar_output = QComboBox()
        self._cmb_ar_output.addItem("dB", True)
        self._cmb_ar_output.addItem(self.tr("线性"), False)
        self._cmb_ar_output.setVisible(False)  # 不显示在主界面

        # ── 多步进计算（移至右侧栏） ──
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
            self.tr("跳过原始步进（仅计算上述选中的步进值）"))
        sl.addWidget(self._chk_skip_original)
        self._chk_gen_diff = QCheckBox(
            self.tr("生成步进差值比较表"))
        self._chk_gen_diff.setChecked(True)
        self._chk_gen_diff.setToolTip(
            self.tr("勾选后将为每个参数生成步进结果与原始结果的差值表"))
        sl.addWidget(self._chk_gen_diff)
        self._chk_gen_diff_chart = QCheckBox(
            self.tr("生成步进差值图表"))
        self._chk_gen_diff_chart.setChecked(True)
        self._chk_gen_diff_chart.setToolTip(
            self.tr("勾选后生成交互式差值散点图（支持按参数/步进角度筛选，可在 Excel 中右键 PivotTable 插入切片器）"))
        sl.addWidget(self._chk_gen_diff_chart)

        # UI 联动: 图表依赖差值表 → 勾选图表时自动勾选并锁定差值表
        self._chk_gen_diff_chart.toggled.connect(
            lambda checked: self._chk_gen_diff.setEnabled(not checked))
        # 初始化状态: 图表勾选时差值表禁用 (不可单独取消)
        if self._chk_gen_diff_chart.isChecked():
            self._chk_gen_diff.setEnabled(False)

        right_lyt.addWidget(algo_grp)
        right_lyt.addWidget(self._grp_step)
        right_lyt.addStretch()
        self._right_scroll.setWidget(right_content)

        param_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(param_widget)
        main_layout.addWidget(scroll, 1)

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

    def _show_angle_popup(self, target: str):
        """角度配置弹窗：加自定义角度+步进生成+汇总列表(可删)。"""
        is_ar = (target == "ar")
        # 从现有配置加载
        if is_ar and hasattr(self, '_ar_angle_widget') and self._ar_angle_widget:
            src_cfg = self._ar_angle_widget.get_config()
        elif not is_ar and hasattr(self, '_gain_angle_widget') and self._gain_angle_widget:
            src_cfg = self._gain_angle_widget.get_config()
        else:
            src_cfg = LagConfig()
        singles = list(src_cfg.single_angles)
        ranges = list(src_cfg.ranges)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{'AR' if is_ar else 'Gain'} " + self.tr("角度配置"))
        dlg.setMinimumSize(520, 460)
        layout = QVBoxLayout(dlg)

        # ── 已配置项汇总（FlowLayout + 删除按钮） ──
        display_grp = QGroupBox()
        display_layout = QVBoxLayout(display_grp)

        def _refresh():
            while display_layout.count():
                item = display_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            if singles or ranges:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                dw = QWidget()
                fl = FlowLayout(dw, margin=4, h_spacing=6, v_spacing=4)
                for a in sorted(set(singles)):
                    tag = QWidget()
                    tl = QHBoxLayout(tag)
                    tl.setContentsMargins(2, 1, 2, 1)
                    tl.addWidget(QLabel(f"{a}°"))
                    btn_del = QPushButton("✕")
                    btn_del.setFixedSize(20, 20)
                    btn_del.setStyleSheet("padding:0;")
                    btn_del.clicked.connect(lambda checked, v=a: (singles.remove(v), _refresh()))
                    tl.addWidget(btn_del)
                    fl.addWidget(tag)
                for lo, hi in sorted(set(ranges), key=lambda x: (x[0], x[1])):
                    tag = QWidget()
                    tl = QHBoxLayout(tag)
                    tl.setContentsMargins(2, 1, 2, 1)
                    tl.addWidget(QLabel(f"{lo}°~{hi}°"))
                    btn_del = QPushButton("✕")
                    btn_del.setFixedSize(20, 20)
                    btn_del.setStyleSheet("padding:0;")
                    btn_del.clicked.connect(lambda checked, l=lo, h=hi: (ranges.remove((l, h)), _refresh()))
                    tl.addWidget(btn_del)
                    fl.addWidget(tag)
                scroll.setWidget(dw)
                display_layout.addWidget(scroll)
                btn_clear = QPushButton(self.tr("🗑 清空全部"))
                btn_clear.clicked.connect(lambda: (singles.clear(), ranges.clear(), _refresh()))
                display_layout.addWidget(btn_clear)
            else:
                display_layout.addWidget(QLabel(self.tr("  (暂无配置)")))
            display_grp.setTitle(self.tr("已配置: {} 个单角度, {} 个范围").format(len(singles), len(ranges)))

        _refresh()
        layout.addWidget(display_grp)

        # ── 下半部：添加控件 ──
        splitter = ThinSplitter(Qt.Vertical)
        bottom = QWidget()
        btm = QVBoxLayout(bottom)
        btm.setContentsMargins(0, 0, 0, 0)

        # 自定义单角度
        cust_grp = QGroupBox(self.tr("添加单角度"))
        cust_row = QHBoxLayout(cust_grp)
        spin_custom = QDoubleSpinBox()
        spin_custom.setRange(0, 180)
        spin_custom.setValue(45)
        btn_add = QPushButton("+ " + self.tr("添加"))
        btn_add.clicked.connect(lambda: (
            singles.append(spin_custom.value()) if spin_custom.value() not in singles else None,
            _refresh()))
        cust_row.addWidget(QLabel(self.tr("角度:")))
        cust_row.addWidget(spin_custom)
        cust_row.addWidget(btn_add)
        cust_row.addStretch()
        btm.addWidget(cust_grp)

        # 步进批量生成
        step_grp = QGroupBox(self.tr("步进批量生成"))
        step_row = QHBoxLayout(step_grp)
        spin_s = QDoubleSpinBox(); spin_s.setRange(0, 180); spin_s.setValue(0)
        spin_e = QDoubleSpinBox(); spin_e.setRange(0, 180); spin_e.setValue(90)
        spin_st = QDoubleSpinBox(); spin_st.setRange(1, 90); spin_st.setValue(10)
        btn_gen = QPushButton(self.tr("生成"))
        btn_gen.clicked.connect(lambda: (
            [singles.append(round(float(a), 6))
             for a in np.linspace(spin_s.value(), spin_e.value(), int((spin_e.value()-spin_s.value())/spin_st.value())+1)
             if round(float(a), 6) not in singles],
            _refresh()))
        step_row.addWidget(QLabel(self.tr("起:")))
        step_row.addWidget(spin_s)
        step_row.addWidget(QLabel(self.tr("止:")))
        step_row.addWidget(spin_e)
        step_row.addWidget(QLabel(self.tr("步:")))
        step_row.addWidget(spin_st)
        step_row.addWidget(btn_gen)
        step_row.addStretch()
        btm.addWidget(step_grp)

        # 角度范围
        range_grp = QGroupBox(self.tr("角度范围"))
        range_row = QHBoxLayout(range_grp)
        spin_rs = QDoubleSpinBox(); spin_rs.setRange(0, 180); spin_rs.setValue(0)
        spin_re = QDoubleSpinBox(); spin_re.setRange(0, 180); spin_re.setValue(90)
        btn_range = QPushButton(self.tr("添加范围"))
        btn_range.clicked.connect(lambda: (
            ranges.append((spin_rs.value(), spin_re.value()))
            if spin_rs.value() < spin_re.value() else None,
            _refresh()))
        range_row.addWidget(QLabel(self.tr("起始:")))
        range_row.addWidget(spin_rs)
        range_row.addWidget(QLabel(self.tr("结束:")))
        range_row.addWidget(spin_re)
        range_row.addWidget(btn_range)
        range_row.addStretch()
        btm.addWidget(range_grp)

        splitter.addWidget(bottom)
        layout.addWidget(splitter)

        # AR 输出单位
        if is_ar:
            ar_row = QHBoxLayout()
            ar_row.addWidget(QLabel(self.tr("AR 输出单位:")))
            cmb_ar_out = QComboBox()
            cmb_ar_out.addItem(self.tr("dB (20·log₁₀)"), True)
            cmb_ar_out.addItem(self.tr("线性比值"), False)
            cmb_ar_out.setCurrentIndex(0 if self._cmb_ar_output.currentData() else 1)
            ar_row.addWidget(cmb_ar_out)
            ar_row.addStretch()
            layout.addLayout(ar_row)

        # 按钮
        btn_row = QHBoxLayout()
        btn_ok = QPushButton(self.tr("确定"))
        btn_cancel = QPushButton(self.tr("取消"))
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        def on_accept():
            new_cfg = LagConfig(single_angles=singles, ranges=ranges)
            if is_ar:
                if not self._ar_angle_widget:
                    from ui.widgets import AnglePickerWidget
                    self._ar_angle_widget = AnglePickerWidget()
                self._ar_angle_widget.set_config(new_cfg)
                self._cmb_ar_output.setCurrentIndex(cmb_ar_out.currentIndex())
            else:
                if not self._gain_angle_widget:
                    from ui.widgets import AnglePickerWidget
                    self._gain_angle_widget = AnglePickerWidget()
                self._gain_angle_widget.set_config(new_cfg)
            self._on_angle_changed(target)
            dlg.accept()

        btn_ok.clicked.connect(on_accept)
        btn_cancel.clicked.connect(dlg.reject)
        dlg.exec()

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
        self._left_checkboxes.clear()
        self._right_checkboxes.clear()

        # 左右分栏: 报告需要 | 额外(full_report) — 与 ChartSettingsPage 对齐
        content = QWidget()
        hbox = QHBoxLayout(content)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(8)

        # 左列: 报告需要 (模板识别自动勾选)
        left_box = QGroupBox(self.tr("报告需要"))
        left_layout = QVBoxLayout(left_box)
        left_layout.setSpacing(2)
        for grp_name, items in params:
            grp = QGroupBox(grp_name)
            gl = QVBoxLayout(grp)
            gl.setSpacing(2)
            for key, label in items:
                cb = QCheckBox(label)
                self._left_checkboxes[key] = cb
                cb.toggled.connect(lambda checked, k=key: self._sync_to_mw())
                cb.setChecked(key in self._template_params)
                gl.addWidget(cb)
            if grp_name == "Gain":
                btn = QPushButton(self.tr("📡 Gain 角度设置..."))
                btn.clicked.connect(lambda: self._show_angle_popup("gain"))
                gl.addWidget(btn)
            elif grp_name == "Axial Ratio":
                btn = QPushButton(self.tr("🔄 AR 角度设置..."))
                btn.clicked.connect(lambda: self._show_angle_popup("ar"))
                gl.addWidget(btn)
            left_layout.addWidget(grp)
        left_layout.addStretch()
        hbox.addWidget(left_box, 1)

        # 右列: 额外 (full_report, 默认不选)
        right_box = QGroupBox(self.tr("额外 (full_report)"))
        right_layout = QVBoxLayout(right_box)
        right_layout.setSpacing(2)
        for grp_name, items in params:
            grp = QGroupBox(grp_name)
            gl = QVBoxLayout(grp)
            gl.setSpacing(2)
            for key, label in items:
                cb = QCheckBox(label)
                self._right_checkboxes[key] = cb
                cb.toggled.connect(lambda checked, k=key: self._sync_to_mw())
                cb.setChecked(False)
                gl.addWidget(cb)
            if grp_name == "Gain":
                btn = QPushButton(self.tr("📡 Gain 角度设置..."))
                btn.clicked.connect(lambda: self._show_angle_popup("gain"))
                gl.addWidget(btn)
            elif grp_name == "Axial Ratio":
                btn = QPushButton(self.tr("🔄 AR 角度设置..."))
                btn.clicked.connect(lambda: self._show_angle_popup("ar"))
                gl.addWidget(btn)
            right_layout.addWidget(grp)
        right_layout.addStretch()
        hbox.addWidget(right_box, 1)

        self._left_scroll.setWidget(content)
        self._sync_to_mw()
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
             for a in np.linspace(spin_start.value(), spin_end.value() , int((spin_end.value() -spin_start.value())/spin_step.value()+1))
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

        splitter = ThinSplitter(Qt.Vertical)
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
        """摘要已移至下方执行栏显示，此处留空。"""
        pass

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

        # 同步 Gain / AR 角度 widget → MainWindow
        def _sync_widget(widget, cfg_attr, has_ui=False):
            if widget is None:
                return
            if not hasattr(mw, cfg_attr):
                setattr(mw, cfg_attr, LagConfig())
            cfg = widget.get_config()
            dest = getattr(mw, cfg_attr)
            dest.clear()
            for a in sorted(set(cfg.single_angles)):
                dest.add_single(a)
            for lo, hi in sorted(set(cfg.ranges)):
                dest.add_range(lo, hi)
            if has_ui:
                mw._sync_quick_buttons()
                mw._update_lag_display()

        _sync_widget(self._gain_angle_widget, '_lag_config', has_ui=True)
        _sync_widget(self._ar_angle_widget, '_ar_lag_config')

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
        try:
            if hasattr(mw, '_spin_trim_start'):
                mw._spin_trim_start.setValue(self._spin_trim_start.value())
                mw._spin_trim_end.setValue(self._spin_trim_end.value())
            if hasattr(mw, '_check_extrapolate'):
                mw._check_extrapolate.setChecked(self._check_extrap.isChecked())
            if hasattr(mw, '_check_robust_peak'):
                mw._check_robust_peak.setChecked(self._check_robust.isChecked())
            mw._ar_output_db = self._cmb_ar_output.currentData()
        except RuntimeError:
            pass

        self._update_summary()
        self.params_changed.emit()

    # ── 加载/保存状态（与 MainWindow 双向同步） ──

    def _load_state(self):
        """从 MainWindow 加载状态（测试模式/角度/频点/算法/参数勾选）。"""
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

        # 加载参数勾选状态：模板自动识别的 _required_params → checkbox 选中
        if hasattr(mw, '_required_params'):
            self._template_params = set(mw._required_params)
        # _extra_params 通过 property 直接读写 MainWindow，不存本地副本

        if hasattr(mw, '_lag_config'):
            if not self._gain_angle_widget:
                from ui.widgets import AnglePickerWidget
                self._gain_angle_widget = AnglePickerWidget(self.tr("Gain 角度"))
            self._gain_angle_widget.set_config(mw._lag_config)
        if hasattr(mw, '_ar_lag_config'):
            if not self._ar_angle_widget:
                from ui.widgets import AnglePickerWidget
                self._ar_angle_widget = AnglePickerWidget(self.tr("AR 角度"))
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

        # 重建参数列（checkbox 根据 _template_params 选中）
        self._rebuild_param_columns()

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
            "gen_diff": self.get_gen_diff(),
            "gen_diff_chart": self.get_gen_diff_chart(),
        }

    def get_gen_diff(self) -> bool:
        return hasattr(self, '_chk_gen_diff') and self._chk_gen_diff.isChecked()

    def get_gen_diff_chart(self) -> bool:
        return hasattr(self, '_chk_gen_diff_chart') and self._chk_gen_diff_chart.isChecked()

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

        # 方位面极坐标切面
        self._azimuth_angles: List[float] = []
        self._azimuth_angles_ar: List[float] = []
        self._antenna_name: str = ""
        self._word_layout_mode: str = "side_by_side"
        self._chart_output_dir: str = ""
        self._chart_output_filename: str = ""
        self._data_gain_output_dir: str = ""
        self._data_gain_output_filename: str = ""
        self._data_ar_output_dir: str = ""
        self._data_ar_output_filename: str = ""

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

        self._azimuth_angles = []
        self._azimuth_angles_ar = []
        self._cut_2d_phi_angles: List[float] = []
        self._view_angle_pairs: List[Tuple[float, float]] = []
        self._antenna_name = ""
        self._word_layout_mode = "side_by_side"
        self._chart_output_dir = ""
        self._chart_output_filename = ""
        self._data_gain_output_dir = ""
        self._data_gain_output_filename = ""
        self._data_ar_output_dir = ""
        self._data_ar_output_filename = ""

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

        btn_multi_view = QPushButton(self.tr("多视角..."))
        btn_multi_view.setFixedWidth(80)
        btn_multi_view.clicked.connect(self._show_view_angle_popup)
        view_layout.addWidget(btn_multi_view)

        view_layout.addStretch()

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

            content_layout.addStretch()  # 占位, 左右 box 内自有按钮

            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            # 左列: 报告需要
            left_box = QGroupBox(self.tr("报告需要"))
            left_layout = QVBoxLayout(left_box)
            left_layout.setSpacing(3)

            self._add_select_all_row(self._chart_required, keys, left_layout)
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
                elif key in ("cut_2d_polar", "cut_2d_rect"):
                    btn = QPushButton("⚙ " + self.tr("Phi 角度..."))
                    btn.setFixedWidth(85)
                    btn.clicked.connect(lambda checked: self._show_2d_phi_angle_popup())
                    row.addWidget(btn)
                row.addStretch()
                left_layout.addLayout(row)
            # ── 方位面极坐标切面 (Gain + AR) ──
            if "C 类" in cat_name:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setFrameShadow(QFrame.Sunken)
                left_layout.addWidget(sep)

                left_layout.addWidget(QLabel(self.tr("方位面极坐标切面:")))

                # Gain azimuth
                row_az_g = QHBoxLayout()
                cb_az_g = QCheckBox(self.tr("Gain 方位面极坐标"))
                cb_az_g.toggled.connect(lambda: self._sync_to_mw())
                row_az_g.addWidget(cb_az_g)
                self._chart_required["cut_azimuth_polar"] = cb_az_g

                btn_az = QPushButton("⚙ " + self.tr("角度..."))
                btn_az.setFixedWidth(80)
                btn_az.clicked.connect(lambda checked: self._show_azimuth_angle_popup("gain"))
                row_az_g.addWidget(btn_az)
                row_az_g.addStretch()
                left_layout.addLayout(row_az_g)

                # AR azimuth
                row_az_ar = QHBoxLayout()
                cb_az_ar = QCheckBox(self.tr("AR 方位面极坐标"))
                cb_az_ar.toggled.connect(lambda: self._sync_to_mw())
                row_az_ar.addWidget(cb_az_ar)
                self._chart_required["cut_azimuth_polar_ar"] = cb_az_ar

                btn_az_ar = QPushButton("⚙ " + self.tr("角度..."))
                btn_az_ar.setFixedWidth(80)
                btn_az_ar.clicked.connect(lambda checked: self._show_azimuth_angle_popup("ar"))
                row_az_ar.addWidget(btn_az_ar)
                row_az_ar.addStretch()
                left_layout.addLayout(row_az_ar)

                # ── 方位面图表参数 ──
                sep_az = QFrame()
                sep_az.setFrameShape(QFrame.HLine)
                sep_az.setFrameShadow(QFrame.Sunken)
                left_layout.addWidget(sep_az)

                row_ant = QHBoxLayout()
                row_ant.addWidget(QLabel(self.tr("天线名:")))
                self._edit_antenna_name = QLineEdit()
                self._edit_antenna_name.setPlaceholderText(self.tr("可选，用于图表标题"))
                self._edit_antenna_name.setMaximumWidth(160)
                self._edit_antenna_name.textChanged.connect(lambda: self._sync_to_mw())
                row_ant.addWidget(self._edit_antenna_name)
                row_ant.addStretch()
                left_layout.addLayout(row_ant)

            left_layout.addStretch()
            row_layout.addWidget(left_box, 1)

            # 右列: 额外 (full_report)
            right_box = QGroupBox(self.tr("额外 (full_report)"))
            right_layout = QVBoxLayout(right_box)
            right_layout.setSpacing(3)

            # full_report 独立全选/取消全选按钮
            self._add_select_all_row(self._chart_extra, keys, right_layout)

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
                elif key in ("cut_2d_polar", "cut_2d_rect"):
                    btn = QPushButton("⚙ " + self.tr("Phi 角度..."))
                    btn.setFixedWidth(85)
                    btn.clicked.connect(lambda checked: self._show_2d_phi_angle_popup())
                    row.addWidget(btn)
                row.addStretch()
                right_layout.addLayout(row)
            right_layout.addStretch()
            row_layout.addWidget(right_box, 1)

            content_layout.addLayout(row_layout)
            grp_list.append(grp)

            # 视角参数紧跟 A 类 3D 图
            if "A 类" in cat_name:
                grp_list.append(view_grp)

            def make_toggle(g=grp, cw=content_widget, name=cat_name):
                def toggle(checked):
                    cw.setVisible(checked)
                    self._collapse_map[name]["hidden"] = not checked
                return toggle
            grp.toggled.connect(make_toggle(grp, content_widget, cat_name))

        # 输出方式
        out_grp = QGroupBox(self.tr("输出方式"))
        out_layout = QVBoxLayout(out_grp)

        # ── Word 布局 ──
        row_wl = QHBoxLayout()
        row_wl.addWidget(QLabel(self.tr("Word 布局:")))
        self._combo_word_layout = QComboBox()
        self._combo_word_layout.addItem(self.tr("并排(Gain左AR右)"), "side_by_side")
        self._combo_word_layout.addItem(self.tr("先后(Gain全部→AR全部)"), "sequential")
        self._combo_word_layout.currentIndexChanged.connect(lambda: self._sync_to_mw())
        row_wl.addWidget(self._combo_word_layout)
        row_wl.addStretch()
        out_layout.addLayout(row_wl)

        # ── 方位面 DPI / 列数 / 图片宽 ──
        row_img = QHBoxLayout()
        row_img.addWidget(QLabel(self.tr("方位图 DPI:")))
        self._spin_azimuth_dpi = QSpinBox()
        self._spin_azimuth_dpi.setRange(150, 1000)
        self._spin_azimuth_dpi.setValue(150)
        self._spin_azimuth_dpi.setSingleStep(50)
        self._spin_azimuth_dpi.setFixedWidth(70)
        self._spin_azimuth_dpi.valueChanged.connect(lambda: self._sync_to_mw())
        row_img.addWidget(self._spin_azimuth_dpi)

        row_img.addWidget(QLabel(self.tr(" 列数:")))
        self._combo_az_columns = QComboBox()
        self._combo_az_columns.addItem(self.tr("单列"), 1)
        self._combo_az_columns.addItem(self.tr("双列"), 2)
        self._combo_az_columns.setCurrentIndex(1)
        self._combo_az_columns.currentIndexChanged.connect(lambda: self._sync_to_mw())
        row_img.addWidget(self._combo_az_columns)

        row_img.addWidget(QLabel(self.tr(" 宽:")))
        self._spin_az_img_pct = QSpinBox()
        self._spin_az_img_pct.setRange(10, 100)
        self._spin_az_img_pct.setValue(90)
        self._spin_az_img_pct.setSuffix("%")
        self._spin_az_img_pct.setFixedWidth(65)
        self._spin_az_img_pct.valueChanged.connect(lambda: self._sync_to_mw())
        row_img.addWidget(self._spin_az_img_pct)
        row_img.addStretch()
        out_layout.addLayout(row_img)

        # 嵌入/PNG 放在最下方
        row_bottom = QHBoxLayout()
        self._check_embed = QCheckBox(self.tr("嵌入 Excel"))
        self._check_embed.setChecked(False)
        self._check_embed.toggled.connect(lambda: self._sync_to_mw())
        self._check_png = QCheckBox(self.tr("保存 PNG 文件夹"))
        self._check_png.toggled.connect(lambda: self._sync_to_mw())
        row_bottom.addWidget(self._check_embed)
        row_bottom.addWidget(self._check_png)
        row_bottom.addStretch()
        out_layout.addLayout(row_bottom)

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
            self._cut_2d_phi_angles = list(req.cut_2d_phi_angles)
            self._view_angle_pairs = list(req.view_angle_pairs)
        if hasattr(mw, '_chart_config_extra') and mw._chart_config_extra is not None:
            xtr = mw._chart_config_extra
            for key, cb in self._chart_extra.items():
                val = getattr(xtr, key, False)
                cb.setChecked(val)
            self._gain_angles_x = list(xtr.gain_chart_angles)
            self._gain_ranges_x = list(xtr.gain_chart_ranges)
            self._ar_angles_x = list(xtr.ar_chart_angles)
            self._ar_ranges_x = list(xtr.ar_chart_ranges)

        # ── 方位面配置 ──
        if hasattr(mw, '_azimuth_config') and mw._azimuth_config is not None:
            az = mw._azimuth_config
            if "cut_azimuth_polar" in self._chart_required:
                self._chart_required["cut_azimuth_polar"].setChecked(az.cut_azimuth_polar)
            if "cut_azimuth_polar_ar" in self._chart_required:
                self._chart_required["cut_azimuth_polar_ar"].setChecked(az.cut_azimuth_polar_ar)

            self._azimuth_angles = list(az.azimuth_cut_angles)
            self._azimuth_angles_ar = list(az.azimuth_cut_angles_ar)
            self._antenna_name = az.antenna_name
            self._word_layout_mode = az.word_layout_mode
            self._chart_output_dir = az.chart_output_dir
            self._chart_output_filename = az.chart_output_filename
            self._data_gain_output_dir = az.data_gain_output_dir
            self._data_gain_output_filename = az.data_gain_output_filename
            self._data_ar_output_dir = az.data_ar_output_dir
            self._data_ar_output_filename = az.data_ar_output_filename

            if hasattr(self, '_edit_antenna_name'):
                self._edit_antenna_name.setText(az.antenna_name)
            if hasattr(self, '_combo_word_layout'):
                idx = self._combo_word_layout.findData(az.word_layout_mode)
                if idx >= 0:
                    self._combo_word_layout.setCurrentIndex(idx)
            if hasattr(self, '_spin_azimuth_dpi'):
                self._spin_azimuth_dpi.setValue(az.dpi if az.dpi >= 150 else 150)
            if hasattr(self, '_combo_az_columns'):
                idx2 = self._combo_az_columns.findData(az.word_columns if az.word_columns in (1, 2) else 2)
                if idx2 >= 0:
                    self._combo_az_columns.setCurrentIndex(idx2)
            if hasattr(self, '_spin_az_img_pct'):
                self._spin_az_img_pct.setValue(az.word_image_width_pct if 10 <= az.word_image_width_pct <= 100 else 90)

    def _add_select_all_row(self, target_dict, keys, parent_layout):
        """添加全选/取消全选按钮行到指定布局。"""
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        sel = QPushButton(self.tr("全选"))
        des = QPushButton(self.tr("取消全选"))
        sel.setFixedWidth(60)
        des.setFixedWidth(72)
        sel.clicked.connect(
            lambda checked, ks=keys: (
                [target_dict[k].setChecked(True) for k in ks if k in target_dict]
            ))
        des.clicked.connect(
            lambda checked, ks=keys: (
                [target_dict[k].setChecked(False) for k in ks if k in target_dict]
            ))
        btn_row.addWidget(sel)
        btn_row.addWidget(des)
        btn_row.addStretch()
        parent_layout.addLayout(btn_row)

    def _sync_to_mw(self):
        """同步当前配置到 MainWindow。"""
        if not self._mw:
            return
        from src.chart_config import ChartConfig
        mw = self._mw

        step_deg = float(max(1, min(30, self._spin_step.value())))

        # 保留已有 ChartConfig 的非标准字段
        existing_req = getattr(mw, '_chart_config_required', None)
        existing_extra = getattr(mw, '_chart_config_extra', None)
        required = ChartConfig()
        extra = ChartConfig()
        if existing_req:
            for k, v in vars(existing_req).items():
                if k not in ChartConfig.all_chart_keys() and not k.startswith('_'):
                    setattr(required, k, v)
        if existing_extra:
            for k, v in vars(existing_extra).items():
                if k not in ChartConfig.all_chart_keys() and not k.startswith('_'):
                    setattr(extra, k, v)
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
        required.cut_2d_phi_angles = list(self._cut_2d_phi_angles)
        required.view_angle_pairs = list(self._view_angle_pairs)
        extra.gain_chart_angles = list(self._gain_angles_x)
        extra.gain_chart_ranges = list(self._gain_ranges_x)
        extra.ar_chart_angles = list(self._ar_angles_x)
        extra.ar_chart_ranges = list(self._ar_ranges_x)

        # ── 方位面配置 ──
        from src.azimuth_config import AzimuthReportConfig
        existing = getattr(mw, '_azimuth_config', None)
        azimuth = existing if existing is not None else AzimuthReportConfig()
        azimuth.cut_azimuth_polar = self._chart_required.get("cut_azimuth_polar", QCheckBox()).isChecked()
        azimuth.cut_azimuth_polar_ar = self._chart_required.get("cut_azimuth_polar_ar", QCheckBox()).isChecked()
        azimuth.azimuth_cut_angles = list(self._azimuth_angles)
        azimuth.azimuth_cut_angles_ar = list(self._azimuth_angles_ar)
        azimuth.antenna_name = self._edit_antenna_name.text().strip() if hasattr(self, '_edit_antenna_name') else ""
        azimuth.word_layout_mode = self._combo_word_layout.currentData() if hasattr(self, '_combo_word_layout') else "side_by_side"
        azimuth.dpi = self._spin_azimuth_dpi.value() if hasattr(self, '_spin_azimuth_dpi') else 150
        azimuth.word_columns = self._combo_az_columns.currentData() if hasattr(self, '_combo_az_columns') else 2
        azimuth.word_image_width_pct = self._spin_az_img_pct.value() if hasattr(self, '_spin_az_img_pct') else 90

        mw._azimuth_config = azimuth
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

        splitter = ThinSplitter(Qt.Vertical)
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
             for a in np.linspace(spin_start.value(), spin_end.value() , int((spin_end.value() -spin_start.value())/spin_step.value()+1))
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

    # ── 方位面角度弹窗 ──

    def _show_azimuth_angle_popup(self, chart_type: str = "gain"):
        """弹出方位面切图 Theta 角度选择窗口。

        Args:
            chart_type: "gain" 或 "ar"，决定编辑哪个角度列表。
        """
        is_ar = (chart_type == "ar")
        label_text = "AR" if is_ar else "Gain"
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("选择方位面切图角度 — {}").format(label_text))
        dlg.setMinimumSize(480, 400)

        import copy
        src_angles = self._azimuth_angles_ar if is_ar else self._azimuth_angles
        _target = src_angles  # 直接引用，OK 时写回
        _singles: List[float] = copy.deepcopy(_target)

        # 空列表 → 自动加载 LAG
        if not _singles and hasattr(self._mw, '_lag_config'):
            _singles = list(self._mw._lag_config.singles_sorted)

        layout = QVBoxLayout(dlg)

        # 已选角度显示区
        display_grp = QGroupBox(self.tr("已选角度"))
        _display_layout = QVBoxLayout(display_grp)

        def _refresh_display():
            while _display_layout.count():
                item = _display_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            if _singles:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QScrollArea.NoFrame)
                scroll.setMaximumHeight(120)
                tags = QWidget()
                tag_layout = FlowLayout(tags)
                for a in sorted(set(_singles)):
                    row_w = QWidget()
                    row_h = QHBoxLayout(row_w)
                    row_h.setContentsMargins(2, 1, 2, 1)
                    row_h.setSpacing(2)
                    row_h.addWidget(QLabel(f"{a:.0f}°"))
                    btn_del = QPushButton("✕")
                    btn_del.setFixedSize(20, 20)
                    btn_del.clicked.connect(lambda checked, angle=a: (
                        _singles.remove(angle),
                        _refresh_display()
                    ))
                    row_h.addWidget(btn_del)
                    tag_layout.addWidget(row_w)
                scroll.setWidget(tags)
                _display_layout.addWidget(scroll)
                btn_clear_all = QPushButton(self.tr("清空全部"))
                btn_clear_all.clicked.connect(lambda: (_singles.clear(), _refresh_display()))
                _display_layout.addWidget(btn_clear_all)
            else:
                _display_layout.addWidget(QLabel(self.tr("  (未选择任何角度)")))

        _refresh_display()
        layout.addWidget(display_grp)

        # 分割线 + 控制区
        splitter = QSplitter(Qt.Vertical)
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        # 自定义单角度
        cust_grp = QGroupBox(self.tr("自定义"))
        cust_layout = QHBoxLayout(cust_grp)
        spin_custom = QDoubleSpinBox()
        spin_custom.setRange(0, 180)
        spin_custom.setDecimals(1)
        spin_custom.setValue(60)
        spin_custom.setSuffix("°")
        cust_layout.addWidget(QLabel(self.tr("角度:")))
        cust_layout.addWidget(spin_custom)
        btn_add = QPushButton("+ " + self.tr("添加"))
        btn_add.clicked.connect(lambda: (
            _singles.append(spin_custom.value()) if spin_custom.value() not in _singles else None,
            _refresh_display()
        ))
        cust_layout.addWidget(btn_add)
        cust_layout.addStretch()
        bottom_layout.addWidget(cust_grp)

        # 步进批量生成
        step_grp = QGroupBox(self.tr("步进批量生成"))
        step_layout = QHBoxLayout(step_grp)
        step_layout.addWidget(QLabel(self.tr("起始:")))
        spin_start = QDoubleSpinBox()
        spin_start.setRange(0, 180)
        spin_start.setDecimals(1)
        spin_start.setValue(0)
        spin_start.setSuffix("°")
        step_layout.addWidget(spin_start)
        step_layout.addWidget(QLabel(self.tr("结束:")))
        spin_end = QDoubleSpinBox()
        spin_end.setRange(0, 180)
        spin_end.setDecimals(1)
        spin_end.setValue(90)
        spin_end.setSuffix("°")
        step_layout.addWidget(spin_end)
        step_layout.addWidget(QLabel(self.tr("步进:")))
        spin_step = QDoubleSpinBox()
        spin_step.setRange(1, 90)
        spin_step.setDecimals(1)
        spin_step.setValue(10)
        spin_step.setSuffix("°")
        step_layout.addWidget(spin_step)
        btn_gen = QPushButton(self.tr("生成"))
        btn_gen.clicked.connect(lambda: (
            [_singles.append(float(a)) for a in
             np.linspace(spin_start.value(), spin_end.value(),
                         max(1, int((spin_end.value() - spin_start.value()) /
                                    max(1, spin_step.value())) + 1))
             if float(a) not in _singles],
            _refresh_display()
        ))
        step_layout.addWidget(btn_gen)
        step_layout.addStretch()
        bottom_layout.addWidget(step_grp)

        # OK / Cancel
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            _target.clear(),
            _target.extend(sorted(set(_singles))),
            dlg.accept()
        ))
        btns.rejected.connect(dlg.reject)
        bottom_layout.addWidget(btns)

        splitter.addWidget(display_grp)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        layout.addWidget(splitter)
        dlg.exec()
        self._sync_to_mw()

    # ── 中间文件设置子对话框 ──

    def _show_intermediate_file_settings(self):
        """打开中间文件输出设置子对话框。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("中间文件输出设置"))
        dlg.setMinimumSize(580, 320)

        layout = QVBoxLayout(dlg)

        # Gain 数据
        gain_grp = QGroupBox(self.tr("Gain 中间数据"))
        gain_layout = QVBoxLayout(gain_grp)
        row_gd = QHBoxLayout()
        row_gd.addWidget(QLabel(self.tr("输出目录:")))
        edit_gain_dir = QLineEdit(self._data_gain_output_dir)
        edit_gain_dir.setPlaceholderText(self.tr("默认: 源文件目录"))
        edit_gain_dir.setMinimumWidth(220)
        row_gd.addWidget(edit_gain_dir)
        btn_gain_browse = QPushButton(self.tr("浏览..."))
        row_gd.addWidget(btn_gain_browse)
        row_gd.addStretch()
        gain_layout.addLayout(row_gd)

        row_gf = QHBoxLayout()
        row_gf.addWidget(QLabel(self.tr("文件名:")))
        edit_gain_fn = QLineEdit(self._data_gain_output_filename)
        edit_gain_fn.setPlaceholderText(self.tr("默认: 源文件名Gain.xlsx"))
        edit_gain_fn.setMinimumWidth(220)
        row_gf.addWidget(edit_gain_fn)
        row_gf.addStretch()
        gain_layout.addLayout(row_gf)

        layout.addWidget(gain_grp)

        # AR 数据
        ar_grp = QGroupBox(self.tr("AR 中间数据"))
        ar_layout = QVBoxLayout(ar_grp)
        row_ad = QHBoxLayout()
        row_ad.addWidget(QLabel(self.tr("输出目录:")))
        edit_ar_dir = QLineEdit(self._data_ar_output_dir)
        edit_ar_dir.setPlaceholderText(self.tr("默认: 源文件目录"))
        edit_ar_dir.setMinimumWidth(220)
        row_ad.addWidget(edit_ar_dir)
        btn_ar_browse = QPushButton(self.tr("浏览..."))
        row_ad.addWidget(btn_ar_browse)
        row_ad.addStretch()
        ar_layout.addLayout(row_ad)

        row_af = QHBoxLayout()
        row_af.addWidget(QLabel(self.tr("文件名:")))
        edit_ar_fn = QLineEdit(self._data_ar_output_filename)
        edit_ar_fn.setPlaceholderText(self.tr("默认: 源文件名AR.xlsx"))
        edit_ar_fn.setMinimumWidth(220)
        row_af.addWidget(edit_ar_fn)
        row_af.addStretch()
        ar_layout.addLayout(row_af)

        layout.addWidget(ar_grp)

        layout.addStretch()

        # Browse buttons
        btn_gain_browse.clicked.connect(lambda: _pick_dir(edit_gain_dir, "Gain"))
        btn_ar_browse.clicked.connect(lambda: _pick_dir(edit_ar_dir, "AR"))

        def _pick_dir(target_edit, label):
            from PySide6.QtWidgets import QFileDialog
            d = QFileDialog.getExistingDirectory(
                dlg, self.tr("选择 {} 数据输出目录").format(label))
            if d:
                target_edit.setText(d)

        # OK / Cancel
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            setattr(self, '_data_gain_output_dir', edit_gain_dir.text().strip()),
            setattr(self, '_data_gain_output_filename', edit_gain_fn.text().strip()),
            setattr(self, '_data_ar_output_dir', edit_ar_dir.text().strip()),
            setattr(self, '_data_ar_output_filename', edit_ar_fn.text().strip()),
            dlg.accept(),
            self._sync_to_mw(),
        ))
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        dlg.exec()

    # ── 图表输出目录浏览 ──

    def _browse_chart_output_dir(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(
            self, self.tr("选择图表输出目录 (Word)"))
        if d and hasattr(self, '_edit_chart_output_dir'):
            self._edit_chart_output_dir.setText(d)
            self._sync_to_mw()

    # ── 3D 多视角弹窗 ──

    def _show_view_angle_popup(self):
        """弹出 3D 方向图多视角设置窗口。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("3D 多视角设置"))
        dlg.setMinimumSize(500, 350)
        import copy
        _pairs: List[Tuple[float, float]] = copy.deepcopy(self._view_angle_pairs)

        layout = QVBoxLayout(dlg)
        display_grp = QGroupBox(self.tr("视角列表 (仰角, 方位角)"))
        _display_layout = QVBoxLayout(display_grp)

        def _refresh_display():
            while _display_layout.count():
                item = _display_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            if _pairs:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
                scroll.setMaximumHeight(140)
                tags = QWidget()
                tag_layout = FlowLayout(tags)
                for el, az in _pairs:
                    row_w = QWidget()
                    row_h = QHBoxLayout(row_w)
                    row_h.setContentsMargins(2, 1, 2, 1); row_h.setSpacing(2)
                    row_h.addWidget(QLabel(f"仰角 {el:.0f}°, 方位 {az:.0f}°"))
                    btn_del = QPushButton("✕")
                    btn_del.setFixedSize(20, 20)
                    btn_del.clicked.connect(lambda checked, p=(el, az): (
                        _pairs.remove(p), _refresh_display()))
                    row_h.addWidget(btn_del); row_h.addStretch()
                    tag_layout.addWidget(row_w)
                scroll.setWidget(tags)
                _display_layout.addWidget(scroll)
                btn_clear = QPushButton(self.tr("清空全部"))
                btn_clear.clicked.connect(lambda: (_pairs.clear(), _refresh_display()))
                _display_layout.addWidget(btn_clear)
            else:
                _display_layout.addWidget(QLabel(self.tr(
                    "  (未设置，使用上方仰角/方位角单值)")))
        _refresh_display()
        layout.addWidget(display_grp)

        add_grp = QGroupBox(self.tr("添加视角"))
        add_layout = QHBoxLayout(add_grp)
        add_layout.addWidget(QLabel(self.tr("仰角:")))
        spin_el = QDoubleSpinBox()
        spin_el.setRange(-90, 90); spin_el.setDecimals(1)
        spin_el.setValue(30); spin_el.setSuffix("°")
        add_layout.addWidget(spin_el)
        add_layout.addWidget(QLabel(self.tr("方位角:")))
        spin_az = QDoubleSpinBox()
        spin_az.setRange(-180, 180); spin_az.setDecimals(1)
        spin_az.setValue(-60); spin_az.setSuffix("°")
        add_layout.addWidget(spin_az)
        btn_add = QPushButton("+ " + self.tr("添加"))
        btn_add.clicked.connect(lambda: (
            _pairs.append((spin_el.value(), spin_az.value())),
            _refresh_display()))
        add_layout.addWidget(btn_add); add_layout.addStretch()
        layout.addWidget(add_grp)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            self._view_angle_pairs.clear(),
            self._view_angle_pairs.extend(list(_pairs)),
            dlg.accept()))
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        dlg.exec()
        self._sync_to_mw()

    # ── 2D 俯仰面 Phi 角度弹窗 ──

    def _show_2d_phi_angle_popup(self):
        """弹出 2D 俯仰面切面 Phi 角度选择窗口。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("选择俯仰面切图 Phi 角度"))
        dlg.setMinimumSize(480, 380)
        import copy
        _singles: List[float] = copy.deepcopy(self._cut_2d_phi_angles)

        layout = QVBoxLayout(dlg)
        display_grp = QGroupBox(self.tr("已选 Phi 角度"))
        _display_layout = QVBoxLayout(display_grp)

        def _refresh_display():
            while _display_layout.count():
                item = _display_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            if _singles:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
                scroll.setMaximumHeight(120)
                tags = QWidget()
                tag_layout = FlowLayout(tags)
                for a in sorted(set(_singles)):
                    row_w = QWidget()
                    row_h = QHBoxLayout(row_w)
                    row_h.setContentsMargins(2, 1, 2, 1); row_h.setSpacing(2)
                    row_h.addWidget(QLabel(f"{a:.0f}°"))
                    btn_del = QPushButton("✕")
                    btn_del.setFixedSize(20, 20)
                    btn_del.clicked.connect(lambda checked, angle=a: (
                        _singles.remove(angle), _refresh_display()))
                    row_h.addWidget(btn_del); row_h.addStretch()
                    tag_layout.addWidget(row_w)
                scroll.setWidget(tags)
                _display_layout.addWidget(scroll)
                btn_clear = QPushButton(self.tr("清空全部"))
                btn_clear.clicked.connect(lambda: (_singles.clear(), _refresh_display()))
                _display_layout.addWidget(btn_clear)
            else:
                _display_layout.addWidget(QLabel(self.tr("  (未选择，默认 φ=0°, 90°)")))
        _refresh_display()
        layout.addWidget(display_grp)

        splitter = QSplitter(Qt.Vertical)
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        # 自定义 Phi
        cust_grp = QGroupBox(self.tr("自定义"))
        cust_layout = QHBoxLayout(cust_grp)
        spin_custom = QDoubleSpinBox()
        spin_custom.setRange(0, 360); spin_custom.setDecimals(1)
        spin_custom.setValue(0); spin_custom.setSuffix("°")
        cust_layout.addWidget(QLabel(self.tr("Phi:")))
        cust_layout.addWidget(spin_custom)
        btn_add = QPushButton("+ " + self.tr("添加"))
        btn_add.clicked.connect(lambda: (
            _singles.append(spin_custom.value()) if spin_custom.value() not in _singles else None,
            _refresh_display()))
        cust_layout.addWidget(btn_add); cust_layout.addStretch()
        bottom_layout.addWidget(cust_grp)

        # 步进
        step_grp = QGroupBox(self.tr("步进批量生成"))
        step_layout = QHBoxLayout(step_grp)
        for label, default in [("起始:", 0), ("结束:", 180), ("步进:", 45)]:
            step_layout.addWidget(QLabel(self.tr(label)))
            sp = QDoubleSpinBox()
            sp.setRange(0, 360); sp.setDecimals(1); sp.setSuffix("°")
            sp.setValue(default)
            step_layout.addWidget(sp)
            if label == "步进:":
                spin_step = sp
            elif label == "起始:":
                spin_start = sp
            else:
                spin_end = sp
        btn_gen = QPushButton(self.tr("生成"))
        btn_gen.clicked.connect(lambda: (
            [_singles.append(float(a)) for a in
             np.linspace(spin_start.value(), spin_end.value(),
                         max(1, int((spin_end.value()-spin_start.value())/
                                    max(1, spin_step.value()))+1))
             if float(a) not in _singles],
            _refresh_display()))
        step_layout.addWidget(btn_gen); step_layout.addStretch()
        bottom_layout.addWidget(step_grp)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            self._cut_2d_phi_angles.clear(),
            self._cut_2d_phi_angles.extend(sorted(set(_singles))),
            dlg.accept()))
        btns.rejected.connect(dlg.reject)
        bottom_layout.addWidget(btns)

        splitter.addWidget(bottom)
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
