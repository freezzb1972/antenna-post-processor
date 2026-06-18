"""
设置对话框
=========
从主窗口通过菜单调出的设置对话框。
每个对话框管理一组相关设置,确认后将值写回主窗口。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from ui.main_window import MainWindow


# ═══════════════════════════════════════════════════════════════
# 数据源配置对话框
# ═══════════════════════════════════════════════════════════════

class DataSourceDialog(QDialog):
    """文件设置: 模板、数据文件、输出、匹配"""

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self._mw = parent
        self.setWindowTitle("数据源配置")
        self.setMinimumSize(680, 600)
        self.resize(750, 650)
        self._setup_ui()
        self._load_state()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 模板选择
        grp_tpl = QGroupBox("模板文件")
        tpl_layout = QHBoxLayout(grp_tpl)
        self._edit_template = QLineEdit(); self._edit_template.setPlaceholderText("选择模板 .xlsx ...")
        btn_tpl = QPushButton("浏览..."); btn_tpl.clicked.connect(self._on_browse_template)
        tpl_layout.addWidget(self._edit_template); tpl_layout.addWidget(btn_tpl)
        layout.addWidget(grp_tpl)

        # 数据文件
        grp_data = QGroupBox("数据文件")
        data_layout = QVBoxLayout(grp_data)
        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("📂 添加数据文件..."); self._btn_add.setMinimumHeight(32)
        self._btn_add.clicked.connect(self._on_add_files)
        btn_clear = QPushButton("清除"); btn_clear.setMinimumHeight(32)
        btn_clear.clicked.connect(self._on_clear_files)
        btn_row.addWidget(self._btn_add); btn_row.addWidget(btn_clear); btn_row.addStretch()
        data_layout.addLayout(btn_row)

        self._file_list = QListWidget()
        self._file_list.setMinimumHeight(120)
        self._file_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._file_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._file_list.setAlternatingRowColors(True)
        data_layout.addWidget(self._file_list)

        self._match_table = QTableWidget(); self._match_table.setColumnCount(3)
        self._match_table.setHorizontalHeaderLabels(["工作表", "数据文件", "状态"])
        self._match_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._match_table.setMaximumHeight(150)
        data_layout.addWidget(self._match_table)

        match_row = QHBoxLayout()
        self._btn_match = QPushButton("🔗 自动匹配"); self._btn_match.setMinimumHeight(32)
        self._btn_match.clicked.connect(self._on_auto_match)
        self._lbl_status = QLabel("")
        match_row.addWidget(self._btn_match); match_row.addWidget(self._lbl_status); match_row.addStretch()
        data_layout.addLayout(match_row)
        layout.addWidget(grp_data)

        # 输出设置
        grp_out = QGroupBox("输出设置")
        out_layout = QFormLayout(grp_out)
        self._edit_dir = QLineEdit(); self._edit_dir.setPlaceholderText("默认: ./output")
        btn_dir = QPushButton("浏览..."); btn_dir.clicked.connect(self._on_browse_dir)
        dir_row = QHBoxLayout(); dir_row.addWidget(self._edit_dir); dir_row.addWidget(btn_dir)
        out_layout.addRow("输出目录:", dir_row)
        self._edit_name = QLineEdit("antenna_report.xlsx")
        out_layout.addRow("文件名:", self._edit_name)
        self._check_full = QCheckBox("生成完整报告")
        out_layout.addRow("", self._check_full)
        self._edit_report = QLineEdit(); self._edit_report.setPlaceholderText("默认: ./output/full_report.xlsx")
        btn_report = QPushButton("浏览..."); btn_report.clicked.connect(self._on_browse_report)
        rpt_row = QHBoxLayout(); rpt_row.addWidget(self._edit_report); rpt_row.addWidget(btn_report)
        out_layout.addRow("报告路径:", rpt_row)
        layout.addWidget(grp_out)

        # 图表选择
        grp_chart = QGroupBox("输出图表")
        ch_row = QHBoxLayout(grp_chart)
        self._check_chart_eff = QCheckBox("效率曲线"); self._check_chart_eff.setChecked(True)
        self._check_chart_lag = QCheckBox("增益曲线"); self._check_chart_lag.setChecked(True)
        ch_row.addWidget(self._check_chart_eff); ch_row.addWidget(self._check_chart_lag); ch_row.addStretch()
        layout.addWidget(grp_chart)

        # 按钮
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_state(self):
        mw = self._mw
        self._edit_template.setText(mw.ui.editTemplatePath.text())
        self._edit_dir.setText(mw.ui.editOutputDir.text())
        self._edit_name.setText(mw.ui.editOutputName.text())
        self._check_full.setChecked(mw.ui.checkFullReport.isChecked())
        self._edit_report.setText(mw.ui.editFullReportPath.text())
        if hasattr(mw, '_check_chart_eff'):
            self._check_chart_eff.setChecked(mw._check_chart_eff.isChecked())
            self._check_chart_lag.setChecked(mw._check_chart_lag.isChecked())
        # 多文件列表
        if hasattr(mw, '_data_file_paths') and mw._data_file_paths:
            self._file_list.clear()
            for p in mw._data_file_paths:
                self._file_list.addItem(p)
                self._file_list.item(self._file_list.count()-1).setToolTip(p)
        if hasattr(mw, '_match_table') and mw._match_table:
            self._copy_match_table()

    def _copy_match_table(self):
        src = self._mw._match_table
        self._match_table.setRowCount(src.rowCount())
        for r in range(src.rowCount()):
            for c in range(3):
                item = src.item(r, c)
                if item: self._match_table.setItem(r, c, QTableWidgetItem(item.text()))
            widget = src.cellWidget(r, 1)
            if widget:
                combo = QComboBox()
                for i in range(widget.count()): combo.addItem(widget.itemText(i))
                combo.setCurrentIndex(widget.currentIndex())
                self._match_table.setCellWidget(r, 1, combo)

    def _on_browse_template(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择模板", "", "Excel 文件 (*.xlsx *.xls)")
        if path: self._edit_template.setText(path)

    def _on_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择数据文件", "",
            "所有支持格式 (*.csv *.xlsx *.xls);;CSV (*.csv);;Excel (*.xlsx *.xls)")
        for p in paths:
            self._file_list.addItem(p)  # 存完整路径
            self._file_list.item(self._file_list.count()-1).setToolTip(p)

    def _on_clear_files(self): self._file_list.clear(); self._match_table.setRowCount(0)

    def _on_auto_match(self):
        tpl = self._edit_template.text().strip()
        if not tpl:
            QMessageBox.warning(self, "提示", "请先选择模板文件。"); return
        from src.excel_reader import read_template
        from src.sheet_file_matcher import auto_match
        try:
            sheets = read_template(tpl)
            data_files = [self._file_list.item(i).text() for i in range(self._file_list.count())]
            matches = auto_match([s.name for s in sheets], data_files)
            self._match_table.setRowCount(len(matches))
            for i, m in enumerate(matches):
                self._match_table.setItem(i, 0, QTableWidgetItem(m.sheet_name))
                combo = QComboBox(); combo.addItem("—")
                for fp in data_files: combo.addItem(fp)
                if m.file_path:
                    idx = combo.findText(m.file_path)
                    if idx >= 0: combo.setCurrentIndex(idx)
                self._match_table.setCellWidget(i, 1, combo)
                status = "✓ 已匹配" if m.file_path else "未匹配"
                self._match_table.setItem(i, 2, QTableWidgetItem(status))
            matched = sum(1 for m in matches if m.file_path is not None)
            self._lbl_status.setText(f"✓ {matched}/{len(matches)} 已匹配")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取模板失败: {e}")

    def _on_browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self._edit_dir.text() or ".")
        if d: self._edit_dir.setText(d)

    def _on_browse_report(self):
        path, _ = QFileDialog.getSaveFileName(self, "完整报告路径", "full_report.xlsx", "Excel (*.xlsx)")
        if path: self._edit_report.setText(path)

    def _on_accept(self):
        mw = self._mw
        mw.ui.editTemplatePath.setText(self._edit_template.text())
        mw.ui.editOutputDir.setText(self._edit_dir.text())
        mw.ui.editOutputName.setText(self._edit_name.text())
        mw.ui.checkFullReport.setChecked(self._check_full.isChecked())
        mw.ui.editFullReportPath.setText(self._edit_report.text())
        if hasattr(mw, '_check_chart_eff'):
            mw._check_chart_eff.setChecked(self._check_chart_eff.isChecked())
            mw._check_chart_lag.setChecked(self._check_chart_lag.isChecked())
        # 更新数据文件列表 (存完整路径)
        data_files = [self._file_list.item(i).text() for i in range(self._file_list.count())]
        if hasattr(mw, '_data_file_paths'):
            mw._data_file_paths = data_files
        if data_files and hasattr(mw, '_file_list_widget'):
            mw._refresh_data_file_ui()
        self.accept()


# ═══════════════════════════════════════════════════════════════
# 计算参数配置对话框
# ═══════════════════════════════════════════════════════════════

class CalcParamsDialog(QDialog):
    """计算参数配置: 三 Tab 分类 + 双列参数 + 内嵌角度配置 + 算法选项"""

    # ── 参数定义: 三类 Tab 的通用参数 ──
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
    ]

    # 有源发射特有参数
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
            ("nhprp225_ratio", "NHPRP225 / TRP"),
            ("uh_ratio", "UHPRP / TRP"),
            ("lh_ratio", "LHPRP / TRP"),
        ]),
    ]

    # 有源接收特有参数
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
            ("nhpis225_ratio", "NHPIS225 / TIS"),
            ("uh_ratio", "UHPRP / TRP"),
            ("lh_ratio", "LHPRP / TRP"),
        ]),
    ]

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self._mw = parent
        self.setWindowTitle("计算参数配置")
        self.setMinimumSize(780, 600)
        self.resize(820, 680)

        # ── 状态 ──
        self._template_params: set = set()
        self._angle_singles: List[float] = []       # Gain 单角度
        self._angle_ranges: List[tuple] = []         # Gain 范围
        self._ar_angle_singles: List[float] = []     # AR 单角度
        self._ar_angle_ranges: List[tuple] = []      # AR 范围
        self._nh_edge_deg: float = 45.0
        self._extrapolate: bool = False
        self._robust_peak: bool = False
        self._active_tab: int = 0
        self._test_mode: int = 0  # 0=passive, 1=TRP, 2=TIS

        # ── 动态 widget 引用（按 tab 切换时重建） ──
        self._left_checkboxes: Dict[str, QCheckBox] = {}
        self._right_checkboxes: Dict[str, QCheckBox] = {}
        self._left_scroll: Optional[QScrollArea] = None
        self._right_scroll: Optional[QScrollArea] = None

        self._setup_ui()
        self._load_state()
        self._rebuild_param_columns()

    # ═══════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # ── 测试模式选择 ──
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("<b>测试模式:</b>"))
        self._cmb_test_mode = QComboBox()
        self._cmb_test_mode.addItem("📡 无源天线", 0)
        self._cmb_test_mode.addItem("📶 有源发射 TRP", 1)
        self._cmb_test_mode.addItem("📻 有源接收 TIS", 2)
        self._cmb_test_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self._cmb_test_mode)
        mode_row.addStretch()
        main_layout.addLayout(mode_row)

        # ── 顶部: 三个 Tab ──
        self._tabs = QTabWidget()
        self._tabs.addTab(QWidget(), "📡 无源天线参数")
        self._tabs.addTab(QWidget(), "📶 有源发射 TRP")
        self._tabs.addTab(QWidget(), "📻 有源接收 TIS")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self._tabs)

        # ── 中部: 双列参数 (QSplitter) ──
        splitter = QHBoxLayout()
        splitter.setSpacing(8)

        # 左列: 报告必需参数
        left_grp = QGroupBox("报告必需参数（模板自动识别，可调整）")
        left_layout = QVBoxLayout(left_grp)
        self._left_scroll = QScrollArea()
        self._left_scroll.setWidgetResizable(True)
        self._left_scroll.setFrameShape(QScrollArea.NoFrame)
        left_layout.addWidget(self._left_scroll)
        splitter.addWidget(left_grp, 1)

        # 右列: 额外计算参数
        right_grp = QGroupBox("额外计算参数（送 full_report）")
        right_layout = QVBoxLayout(right_grp)
        self._right_scroll = QScrollArea()
        self._right_scroll.setWidgetResizable(True)
        self._right_scroll.setFrameShape(QScrollArea.NoFrame)
        right_layout.addWidget(self._right_scroll)
        splitter.addWidget(right_grp, 1)

        main_layout.addLayout(splitter, 1)

        # ── 角度配置: Gain/AR 切换 ──
        angle_grp = QGroupBox("角度配置")
        angle_outer = QVBoxLayout(angle_grp)
        angle_outer.setSpacing(4)

        # 切换按钮
        toggle_row = QHBoxLayout()
        toggle_row.addWidget(QLabel("<b>当前编辑:</b>"))
        self._btn_gain_angle = QPushButton("📡 Gain 角度")
        self._btn_gain_angle.setCheckable(True); self._btn_gain_angle.setChecked(True)
        self._btn_gain_angle.clicked.connect(lambda: self._on_angle_target_changed(0))
        toggle_row.addWidget(self._btn_gain_angle)
        self._btn_ar_angle = QPushButton("🔄 AR 角度")
        self._btn_ar_angle.setCheckable(True)
        self._btn_ar_angle.clicked.connect(lambda: self._on_angle_target_changed(1))
        toggle_row.addWidget(self._btn_ar_angle)
        toggle_row.addStretch()
        angle_outer.addLayout(toggle_row)
        self._active_angle_tab: int = 0

        # 共享角度控件
        self._build_angle_control_widget()
        angle_outer.addWidget(self._angle_ctrl_widget)

        # NHPRP/NHPIS 地平线角度 (TRP/TIS Tab 时显示)
        self._grp_nh = QGroupBox("NHPRP / NHPIS 地平线边界角度")
        nh_layout = QHBoxLayout(self._grp_nh)
        nh_layout.addWidget(QLabel("±"))
        self._spin_nh_edge = QDoubleSpinBox()
        self._spin_nh_edge.setRange(0, 90); self._spin_nh_edge.setValue(45.0)
        self._spin_nh_edge.setSuffix("°"); self._spin_nh_edge.setFixedWidth(80)
        nh_layout.addWidget(self._spin_nh_edge)
        nh_layout.addWidget(QLabel("（自定义 NHPRP/NHPIS 的地平线边界）"))
        nh_layout.addStretch()
        self._grp_nh.setVisible(False)
        angle_outer.addWidget(self._grp_nh)

        # 已选择区域
        self._selected_widget = QWidget()
        self._selected_layout = QVBoxLayout(self._selected_widget)
        self._selected_layout.setContentsMargins(0, 0, 0, 0)
        self._selected_layout.setSpacing(2)
        angle_outer.addWidget(self._selected_widget)

        main_layout.addWidget(angle_grp)

        # ── 算法选项 ──
        algo_grp = QGroupBox("算法选项")
        algo_layout = QVBoxLayout(algo_grp)
        algo_layout.setSpacing(4)

        freq_row = QHBoxLayout()
        freq_row.addWidget(QLabel("频点来源:"))
        self._cmb_freq_src = QComboBox()
        self._cmb_freq_src.addItem("新 sheet 频点: 数据源", "datasource")
        self._cmb_freq_src.addItem("新 sheet 频点: 模板", "template")
        freq_row.addWidget(self._cmb_freq_src)
        freq_row.addWidget(QLabel("  去除频点: 前"))
        self._spin_trim_start = QSpinBox()
        self._spin_trim_start.setRange(0, 50); self._spin_trim_start.setFixedWidth(50)
        freq_row.addWidget(self._spin_trim_start)
        freq_row.addWidget(QLabel("后"))
        self._spin_trim_end = QSpinBox()
        self._spin_trim_end.setRange(0, 50); self._spin_trim_end.setFixedWidth(50)
        freq_row.addWidget(self._spin_trim_end)
        freq_row.addStretch()
        algo_layout.addLayout(freq_row)

        check_row = QHBoxLayout()
        self._check_extrap = QCheckBox("Theta 外推到 180°")
        check_row.addWidget(self._check_extrap)
        self._check_robust = QCheckBox("Robust peak detection（替代 np.max）")
        check_row.addWidget(self._check_robust)
        check_row.addStretch()
        algo_layout.addLayout(check_row)

        main_layout.addWidget(algo_grp)

        # ── 按钮 ──
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

    # ═══════════════════════════════════════════════════════════
    # Tab 参数列表
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _get_params_for_tab(tab_index: int):
        """返回当前 Tab 的参数定义列表 [(group_name, [(key, label), ...])]."""
        common = list(CalcParamsDialog._COMMON_PARAMS)
        if tab_index == 0:
            return common
        elif tab_index == 1:
            return common + list(CalcParamsDialog._TRP_PARAMS)
        else:
            return common + list(CalcParamsDialog._TIS_PARAMS)

    def _on_mode_changed(self, index: int):
        self._test_mode = index
        # 同步切换 Tab: test_mode 0→Tab0, 1→Tab1, 2→Tab2
        self._tabs.setCurrentIndex(index)

    def _on_tab_changed(self, index: int):
        self._active_tab = index
        self._cmb_test_mode.setCurrentIndex(index)
        self._grp_nh.setVisible(index in (1, 2))  # NH 配置仅 TRP/TIS Tab 显示
        self._rebuild_param_columns()

    def _rebuild_param_columns(self):
        """重建左/右列参数 checkbox 列表。"""
        params = self._get_params_for_tab(self._active_tab)

        # 左列
        left_content = QWidget()
        left_vbox = QVBoxLayout(left_content)
        left_vbox.setContentsMargins(4, 4, 4, 4)
        left_vbox.setSpacing(4)
        self._left_checkboxes.clear()
        for grp_name, items in params:
            grp = QGroupBox(grp_name)
            gl = QVBoxLayout(grp); gl.setSpacing(2)
            for key, label in items:
                cb = QCheckBox(label)
                cb.setChecked(key in self._template_params)
                gl.addWidget(cb)
                self._left_checkboxes[key] = cb
            left_vbox.addWidget(grp)
        left_vbox.addStretch()
        self._left_scroll.setWidget(left_content)

        # 右列
        right_content = QWidget()
        right_vbox = QVBoxLayout(right_content)
        right_vbox.setContentsMargins(4, 4, 4, 4)
        right_vbox.setSpacing(4)
        self._right_checkboxes.clear()
        for grp_name, items in params:
            grp = QGroupBox(grp_name)
            gl = QVBoxLayout(grp); gl.setSpacing(2)
            for key, label in items:
                cb = QCheckBox(label)
                # 右列: 额外参数不与模板重合时未选中
                cb.setChecked(key in (self._template_params if not hasattr(self, '_extra_saved') else set()) and False)
                gl.addWidget(cb)
                self._right_checkboxes[key] = cb
            right_vbox.addWidget(grp)
        right_vbox.addStretch()
        self._right_scroll.setWidget(right_content)

    # ═══════════════════════════════════════════════════════════
    # 角度配置 — 共享 UI, 切换 Gain / AR 状态
    # ═══════════════════════════════════════════════════════════

    def _on_angle_target_changed(self, index: int):
        self._active_angle_tab = index
        self._btn_gain_angle.setChecked(index == 0)
        self._btn_ar_angle.setChecked(index == 1)
        self._sync_angle_buttons()
        self._update_selected_display()

    @property
    def _cur_singles(self) -> List[float]:
        return self._ar_angle_singles if self._active_angle_tab == 1 else self._angle_singles

    @property
    def _cur_ranges(self) -> List[tuple]:
        return self._ar_angle_ranges if self._active_angle_tab == 1 else self._angle_ranges

    def _build_angle_control_widget(self):
        """构建角度设置共享控件（Gain 和 AR 共用）。"""
        self._angle_ctrl_widget = QWidget()
        layout = QVBoxLayout(self._angle_ctrl_widget)
        layout.setSpacing(4)

        # 快捷按钮行
        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel("预设:"))
        self._angle_buttons: Dict[float, QPushButton] = {}
        for a in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]:
            btn = QPushButton(f"{a}°")
            btn.setCheckable(True)
            btn.setFixedWidth(48)
            btn.clicked.connect(lambda checked, angle=a: self._toggle_quick_angle(angle))
            quick_row.addWidget(btn)
            self._angle_buttons[a] = btn
        quick_row.addStretch()
        layout.addLayout(quick_row)

        # 自定义 + 步进行
        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("自定义:"))
        self._spin_custom = QDoubleSpinBox()
        self._spin_custom.setRange(0, 180); self._spin_custom.setValue(0)
        self._spin_custom.setSuffix("°"); self._spin_custom.setFixedWidth(80)
        custom_row.addWidget(self._spin_custom)
        btn_custom_add = QPushButton("+")
        btn_custom_add.setFixedWidth(32)
        btn_custom_add.clicked.connect(self._add_custom_angle)
        custom_row.addWidget(btn_custom_add)
        custom_row.addSpacing(12)
        custom_row.addWidget(QLabel("步进:"))
        self._spin_step_start = QDoubleSpinBox()
        self._spin_step_start.setRange(0, 180); self._spin_step_start.setValue(0)
        self._spin_step_start.setSuffix("°"); self._spin_step_start.setFixedWidth(80)
        custom_row.addWidget(self._spin_step_start)
        custom_row.addWidget(QLabel("—"))
        self._spin_step_end = QDoubleSpinBox()
        self._spin_step_end.setRange(0, 180); self._spin_step_end.setValue(90)
        self._spin_step_end.setSuffix("°"); self._spin_step_end.setFixedWidth(80)
        custom_row.addWidget(self._spin_step_end)
        custom_row.addWidget(QLabel("步长:"))
        self._spin_step_by = QDoubleSpinBox()
        self._spin_step_by.setRange(1, 90); self._spin_step_by.setValue(10)
        self._spin_step_by.setSuffix("°"); self._spin_step_by.setFixedWidth(70)
        custom_row.addWidget(self._spin_step_by)
        btn_step_gen = QPushButton("生成")
        btn_step_gen.clicked.connect(self._on_step_generate)
        custom_row.addWidget(btn_step_gen)
        custom_row.addStretch()
        layout.addLayout(custom_row)

        # 范围行
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("角度范围:"))
        self._spin_range_start = QDoubleSpinBox()
        self._spin_range_start.setRange(0, 180); self._spin_range_start.setValue(0)
        self._spin_range_start.setSuffix("°"); self._spin_range_start.setFixedWidth(80)
        range_row.addWidget(QLabel("起始:")); range_row.addWidget(self._spin_range_start)
        self._spin_range_end = QDoubleSpinBox()
        self._spin_range_end.setRange(0, 180); self._spin_range_end.setValue(90)
        self._spin_range_end.setSuffix("°"); self._spin_range_end.setFixedWidth(80)
        range_row.addWidget(QLabel("结束:")); range_row.addWidget(self._spin_range_end)
        btn_add_range = QPushButton("添加范围")
        btn_add_range.clicked.connect(self._on_add_range)
        range_row.addWidget(btn_add_range)
        range_row.addStretch()
        layout.addLayout(range_row)
        layout.addStretch()

    def _toggle_quick_angle(self, angle: float):
        singles = self._cur_singles
        if angle in singles:
            singles.remove(angle)
        else:
            singles.append(angle)
        self._sync_angle_buttons()
        self._update_selected_display()

    def _add_custom_angle(self):
        a = self._spin_custom.value()
        singles = self._cur_singles
        if a not in singles:
            singles.append(a)
            self._sync_angle_buttons()
            self._update_selected_display()

    def _on_step_generate(self):
        start = self._spin_step_start.value()
        end = self._spin_step_end.value()
        step = self._spin_step_by.value()
        if step <= 0:
            return
        lo, hi = min(start, end), max(start, end)
        singles = self._cur_singles
        a = lo
        while a <= hi + 1e-9:
            rounded = round(a, 6)
            if rounded not in singles:
                singles.append(rounded)
            a += step
        self._sync_angle_buttons()
        self._update_selected_display()

    def _on_add_range(self):
        lo = self._spin_range_start.value()
        hi = self._spin_range_end.value()
        key = (min(lo, hi), max(lo, hi))
        ranges = self._cur_ranges
        if key not in ranges:
            ranges.append(key)
            self._update_selected_display()

    def _remove_single(self, angle: float):
        singles = self._cur_singles  # from which tab the angle was
        if angle in singles:
            singles.remove(angle)
        # Also try the other list
        other = self._ar_angle_singles if self._active_angle_tab == 0 else self._angle_singles
        if angle in other:
            other.remove(angle)
        self._sync_angle_buttons()
        self._update_selected_display()

    def _remove_range(self, lo: float, hi: float):
        key = (lo, hi)
        for rlist in [self._angle_ranges, self._ar_angle_ranges]:
            if key in rlist:
                rlist.remove(key)
        self._update_selected_display()

    def _sync_angle_buttons(self):
        singles = self._cur_singles
        for a, btn in self._angle_buttons.items():
            btn.setChecked(a in singles)

    def _update_selected_display(self):
        """刷新「已选择」区域 — 显示 Gain 和 AR 的角度。"""
        layout = self._selected_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        gain_singles = sorted(set(self._angle_singles))
        gain_ranges = sorted(set(self._angle_ranges))
        ar_singles = sorted(set(self._ar_angle_singles))
        ar_ranges = sorted(set(self._ar_angle_ranges))

        has_gain = gain_singles or gain_ranges
        has_ar = ar_singles or ar_ranges

        if not has_gain and not has_ar:
            lbl = QLabel("（未选择角度）")
            lbl.setStyleSheet("font-size: 12px; color: #888; padding: 4px;")
            layout.addWidget(lbl)
            return

        def _add_tags(label_text, singles, ranges, color):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{label_text}:"))
            for a in singles:
                tag = QWidget()
                tl = QHBoxLayout(tag); tl.setContentsMargins(4,2,4,2); tl.setSpacing(2)
                tlabel = QLabel(f"{a}°")
                tlabel.setStyleSheet(f"font-size:12px;background:{color};color:white;border-radius:3px;padding:1px 4px;")
                tl.addWidget(tlabel)
                btn_x = QPushButton("✕"); btn_x.setFixedSize(18,18)
                btn_x.setStyleSheet("font-size:10px;padding:0;")
                btn_x.clicked.connect(lambda checked, angle=a: self._remove_single(angle))
                tl.addWidget(btn_x); row.addWidget(tag)
            for lo, hi in ranges:
                tag = QWidget()
                tl = QHBoxLayout(tag); tl.setContentsMargins(4,2,4,2); tl.setSpacing(2)
                tlabel = QLabel(f"({lo}°–{hi}°)")
                tlabel.setStyleSheet(f"font-size:12px;background:{color};color:white;border-radius:3px;padding:1px 4px;")
                tl.addWidget(tlabel)
                btn_x = QPushButton("✕"); btn_x.setFixedSize(18,18)
                btn_x.setStyleSheet("font-size:10px;padding:0;")
                btn_x.clicked.connect(lambda checked, l=lo, h=hi: self._remove_range(l, h))
                tl.addWidget(btn_x); row.addWidget(tag)
            row.addStretch()
            layout.addLayout(row)

        if has_gain:
            _add_tags("Gain", gain_singles, gain_ranges, "#3a6fb5")
        if has_ar:
            _add_tags("AR", ar_singles, ar_ranges, "#b53a6f")

    # ═══════════════════════════════════════════════════════════
    # 加载 / 保存状态
    # ═══════════════════════════════════════════════════════════

    def _load_state(self):
        mw = self._mw
        # 测试模式
        if hasattr(mw, '_test_mode'):
            self._test_mode = mw._test_mode
            self._cmb_test_mode.setCurrentIndex(mw._test_mode)
            self._tabs.setCurrentIndex(mw._test_mode)
        # 角度 — Gain
        if hasattr(mw, '_lag_config'):
            self._angle_singles = list(mw._lag_config.single_angles)
            self._angle_ranges = list(mw._lag_config.ranges)
        # 角度 — AR
        if hasattr(mw, '_ar_lag_config'):
            self._ar_angle_singles = list(mw._ar_lag_config.single_angles)
            self._ar_angle_ranges = list(mw._ar_lag_config.ranges)
        self._sync_angle_buttons()
        self._update_selected_display()
        # 频点
        if hasattr(mw, '_cmb_freq_source') and mw._cmb_freq_source:
            self._cmb_freq_src.setCurrentIndex(mw._cmb_freq_source.currentIndex())
        if hasattr(mw, '_spin_trim_start'):
            self._spin_trim_start.setValue(mw._spin_trim_start.value())
            self._spin_trim_end.setValue(mw._spin_trim_end.value())
        # 算法
        if hasattr(mw, '_check_extrapolate'):
            self._check_extrap.setChecked(mw._check_extrapolate.isChecked())
        if hasattr(mw, '_check_robust_peak'):
            self._check_robust.setChecked(mw._check_robust_peak.isChecked())
        # NH 角度
        if hasattr(mw, '_nh_edge_deg'):
            self._nh_edge_deg = mw._nh_edge_deg
            self._spin_nh_edge.setValue(mw._nh_edge_deg)

    def _on_accept(self):
        mw = self._mw
        # 测试模式
        mw._test_mode = self._cmb_test_mode.currentData() if hasattr(self, '_cmb_test_mode') else 0
        # 同步 Gain 角度
        if hasattr(mw, '_lag_config'):
            mw._lag_config.clear()
            for a in sorted(set(self._angle_singles)):
                mw._lag_config.add_single(a)
            for lo, hi in sorted(set(self._angle_ranges)):
                mw._lag_config.add_range(lo, hi)
            mw._sync_quick_buttons()
            mw._update_lag_display()
        # 同步 AR 角度
        if not hasattr(mw, '_ar_lag_config'):
            from src.lag_config import LagConfig
            mw._ar_lag_config = LagConfig()
        mw._ar_lag_config.clear()
        for a in sorted(set(self._ar_angle_singles)):
            mw._ar_lag_config.add_single(a)
        for lo, hi in sorted(set(self._ar_angle_ranges)):
            mw._ar_lag_config.add_range(lo, hi)
        # 保存额外参数 & 必需参数
        required = set(k for k, cb in self._left_checkboxes.items() if cb.isChecked())
        extra = set(k for k, cb in self._right_checkboxes.items() if cb.isChecked())
        mw._required_params = required
        mw._extra_params = extra
        # NH 角度
        mw._nh_edge_deg = self._spin_nh_edge.value()
        # 频点
        if hasattr(mw, '_cmb_freq_source') and mw._cmb_freq_source:
            mw._cmb_freq_source.setCurrentIndex(self._cmb_freq_src.currentIndex())
        if hasattr(mw, '_spin_trim_start'):
            mw._spin_trim_start.setValue(self._spin_trim_start.value())
            mw._spin_trim_end.setValue(self._spin_trim_end.value())
        # 算法
        if hasattr(mw, '_check_extrapolate'):
            mw._check_extrapolate.setChecked(self._check_extrap.isChecked())
        if hasattr(mw, '_check_robust_peak'):
            mw._check_robust_peak.setChecked(self._check_robust.isChecked())
        self.accept()

    # ── 公共接口（外部调用） ──

    def set_template_params(self, params: set):
        """设置模板自动识别的参数集合。"""
        self._template_params = set(params)
        self._rebuild_param_columns()


# ═══════════════════════════════════════════════════════════════
# 图形配置对话框
# ═══════════════════════════════════════════════════════════════

class PlotConfigDialog(QDialog):
    """图形配置: 双列模式 — 报告需要 + 额外(full_report) + 视角参数"""

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self._mw = parent
        self.setWindowTitle("图形配置")
        self.setMinimumSize(720, 560)
        self.resize(780, 620)

        # ── 状态 ──
        self._chart_required: Dict[str, QCheckBox] = {}   # 左列: 报告需要
        self._chart_extra: Dict[str, QCheckBox] = {}      # 右列: 额外(full_report)

        self._setup_ui()
        self._load_state()

    def _setup_ui(self):
        from src.chart_config import ChartConfig
        labels = ChartConfig.chart_labels()
        categories = ChartConfig.chart_categories()

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # ── 图形分类 + 双列 ──
        for cat_name, keys in categories.items():
            grp = QGroupBox(cat_name)
            row_layout = QHBoxLayout(grp)
            row_layout.setSpacing(8)

            # 左列: 报告需要
            left_box = QGroupBox("报告需要")
            left_layout = QVBoxLayout(left_box)
            left_layout.setSpacing(3)
            for key in keys:
                cb = QCheckBox(labels.get(key, key))
                left_layout.addWidget(cb)
                self._chart_required[key] = cb
            left_layout.addStretch()
            row_layout.addWidget(left_box, 1)

            # 右列: 额外(full_report)
            right_box = QGroupBox("额外 (full_report)")
            right_layout = QVBoxLayout(right_box)
            right_layout.setSpacing(3)
            for key in keys:
                cb = QCheckBox(labels.get(key, key))
                right_layout.addWidget(cb)
                self._chart_extra[key] = cb
            right_layout.addStretch()
            row_layout.addWidget(right_box, 1)

            main_layout.addWidget(grp)

        # ── 视角参数 ──
        view_grp = QGroupBox("视角参数")
        view_layout = QHBoxLayout(view_grp)
        view_layout.addWidget(QLabel("仰角:"))
        self._spin_elev = QDoubleSpinBox()
        self._spin_elev.setRange(-90, 90); self._spin_elev.setValue(30)
        self._spin_elev.setSuffix("°"); self._spin_elev.setFixedWidth(80)
        view_layout.addWidget(self._spin_elev)
        view_layout.addWidget(QLabel("方位角:"))
        self._spin_azim = QDoubleSpinBox()
        self._spin_azim.setRange(-180, 180); self._spin_azim.setValue(-60)
        self._spin_azim.setSuffix("°"); self._spin_azim.setFixedWidth(80)
        view_layout.addWidget(self._spin_azim)
        view_layout.addWidget(QLabel("DPI:"))
        self._spin_dpi = QSpinBox()
        self._spin_dpi.setRange(72, 300); self._spin_dpi.setValue(150)
        self._spin_dpi.setFixedWidth(70)
        view_layout.addWidget(self._spin_dpi)
        view_layout.addStretch()
        main_layout.addWidget(view_grp)

        # ── 输出方式 ──
        out_grp = QGroupBox("输出方式")
        out_layout = QHBoxLayout(out_grp)
        self._check_embed = QCheckBox("嵌入 Excel")
        self._check_embed.setChecked(True)
        self._check_png = QCheckBox("保存 PNG 文件夹")
        out_layout.addWidget(self._check_embed)
        out_layout.addWidget(self._check_png)
        out_layout.addStretch()
        main_layout.addWidget(out_grp)

        # ── 按钮 ──
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

    def _load_state(self):
        mw = self._mw
        # 视角
        if hasattr(mw, 'ui'):
            if hasattr(mw.ui, 'spinElev'):
                self._spin_elev.setValue(mw.ui.spinElev.value())
                self._spin_azim.setValue(mw.ui.spinAzim.value())
                self._spin_dpi.setValue(mw.ui.spinDpi.value())
                self._check_embed.setChecked(mw.ui.checkEmbedExcel.isChecked())
                self._check_png.setChecked(mw.ui.checkSavePng.isChecked())
        # 图表配置
        if hasattr(mw, '_chart_config_required'):
            for key, cb in self._chart_required.items():
                val = getattr(mw._chart_config_required, key, False)
                cb.setChecked(val)
        if hasattr(mw, '_chart_config_extra'):
            for key, cb in self._chart_extra.items():
                val = getattr(mw._chart_config_extra, key, False)
                cb.setChecked(val)

    def _on_accept(self):
        from src.chart_config import ChartConfig
        mw = self._mw

        # 构建 ChartConfig 对象
        required = ChartConfig()
        extra = ChartConfig()
        for key in ChartConfig.all_chart_keys():
            setattr(required, key, self._chart_required.get(key, QCheckBox()).isChecked())
            setattr(extra, key, self._chart_extra.get(key, QCheckBox()).isChecked())

        required.elev = self._spin_elev.value()
        required.azim = self._spin_azim.value()
        required.dpi = self._spin_dpi.value()
        required.embed_in_excel = self._check_embed.isChecked()
        extra.elev = required.elev
        extra.azim = required.azim
        extra.dpi = required.dpi
        extra.embed_in_excel = False  # extra charts not embedded in main report

        mw._chart_config_required = required
        mw._chart_config_extra = extra

        # 同步视角到 UI 控件
        if hasattr(mw, 'ui'):
            mw.ui.spinElev.setValue(int(self._spin_elev.value()))
            mw.ui.spinAzim.setValue(int(self._spin_azim.value()))
            mw.ui.spinDpi.setValue(self._spin_dpi.value())
            mw.ui.checkEmbedExcel.setChecked(self._check_embed.isChecked())
            mw.ui.checkSavePng.setChecked(self._check_png.isChecked())

        self.accept()


# ═══════════════════════════════════════════════════════════════
# 帮助搜索对话框
# ═══════════════════════════════════════════════════════════════

class HelpDialog(QDialog):
    """帮助搜索: BM25 全文搜索 + 可选语义搜索 + 可选 LLM RAG 问答"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("帮助 — 天线参数后处理工具")
        self.setMinimumSize(700, 550)
        self.resize(780, 620)

        from src.help_engine import HelpEngine, RAGSettings
        self._engine = HelpEngine()
        self._rag_settings = RAGSettings()
        self._latest_results = []

        self._load_rag_settings()
        self._setup_ui()
        self._lbl_status.setText(f"帮助引擎已就绪 — {self._engine.chunk_count} 个章节")

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── 搜索栏 ──
        search_row = QHBoxLayout()
        self._edit_query = QLineEdit()
        self._edit_query.setPlaceholderText("输入问题或关键词，如: LAG怎么配置、模板列头格式...")
        self._edit_query.returnPressed.connect(self._on_search)
        search_row.addWidget(self._edit_query, 1)

        btn_search = QPushButton("🔍 搜索")
        btn_search.clicked.connect(self._on_search)
        search_row.addWidget(btn_search)

        layout.addLayout(search_row)

        # ── 主体: 结果列表 (左) + RAG 回答 (右) ──
        main_split = QHBoxLayout()
        main_split.setSpacing(8)

        # 左: 搜索结果列表
        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("<b>搜索结果</b>"))

        self._result_list = QListWidget()
        self._result_list.setAlternatingRowColors(True)
        self._result_list.itemClicked.connect(self._on_result_clicked)
        left_panel.addWidget(self._result_list, 1)

        opt_row = QHBoxLayout()
        self._check_semantic = QCheckBox("语义搜索")
        self._check_semantic.setToolTip("启用语义搜索（需要安装 sentence-transformers + faiss）")
        self._check_semantic.setChecked(True)
        opt_row.addWidget(self._check_semantic)
        opt_row.addStretch()
        opt_row.addWidget(QLabel(f"共 {self._engine.chunk_count} 章节"))
        left_panel.addLayout(opt_row)

        main_split.addLayout(left_panel, 1)

        # 右: RAG 回答
        right_panel = QVBoxLayout()
        right_header = QHBoxLayout()
        right_header.addWidget(QLabel("<b>AI 回答</b>"))
        self._btn_ask = QPushButton("🤖 提问 AI")
        self._btn_ask.clicked.connect(self._on_ask)
        self._btn_ask.setToolTip("使用 LLM 对检索到的文档生成回答")
        right_header.addWidget(self._btn_ask)
        self._btn_settings = QPushButton("⚙")
        self._btn_settings.setFixedWidth(32)
        self._btn_settings.setToolTip("LLM API 设置")
        self._btn_settings.clicked.connect(self._on_rag_settings)
        right_header.addWidget(self._btn_settings)
        right_panel.addLayout(right_header)

        self._rag_answer = QPlainTextEdit()
        self._rag_answer.setReadOnly(True)
        self._rag_answer.setPlaceholderText(
            "点击「🤖 提问 AI」使用 LLM 生成回答\n"
            "首次使用请在 ⚙ 中配置 API Key")
        right_panel.addWidget(self._rag_answer, 1)

        self._lbl_sources = QLabel("")
        self._lbl_sources.setStyleSheet("font-size: 11px; color: #888;")
        self._lbl_sources.setWordWrap(True)
        right_panel.addWidget(self._lbl_sources)

        main_split.addLayout(right_panel, 2)
        layout.addLayout(main_split, 1)

        # ── 底部 ──
        bottom_row = QHBoxLayout()
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("font-size: 11px; color: #666;")
        bottom_row.addWidget(self._lbl_status)
        bottom_row.addStretch()
        btn_open = QPushButton("📖 在浏览器中打开完整手册")
        btn_open.clicked.connect(self._on_open_browser)
        bottom_row.addWidget(btn_open)
        layout.addLayout(bottom_row)

    def _on_search(self):
        query = self._edit_query.text().strip()
        if not query:
            return
        self._result_list.clear()
        self._lbl_status.setText("搜索中...")
        use_sem = self._check_semantic.isChecked()
        results = self._engine.search(query, top_k=8, use_semantic=use_sem)
        self._latest_results = results
        for r in results:
            label = f"[{r['source']}] {r['title']}  (score: {r['score']:.2f})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, r)
            self._result_list.addItem(item)
        n = len(results)
        srcs = set(r["source"] for r in results)
        self._lbl_status.setText(f"找到 {n} 个结果（来源: {', '.join(srcs)}）")

    def _on_result_clicked(self, item):
        r = item.data(Qt.UserRole)
        if r:
            detail = f"## {r['title']}\n\n{r['content']}"
            self._rag_answer.setPlainText(detail)

    def _on_ask(self):
        query = self._edit_query.text().strip()
        if not query:
            return
        self._rag_answer.setPlainText("正在请求 AI...")
        self._lbl_sources.setText("")
        QApplication.processEvents()
        result = self._engine.ask(query)
        if result.get("error"):
            self._rag_answer.setPlainText(f"❌ 错误: {result['error']}")
        else:
            self._rag_answer.setPlainText(result["answer"])
            if result["sources"]:
                self._lbl_sources.setText("📚 参考: " + " | ".join(result["sources"]))

    def _on_rag_settings(self):
        dlg = RAGSettingsDialog(self._rag_settings, self)
        if dlg.exec():
            self._rag_settings = dlg.settings
            self._engine.set_rag_settings(self._rag_settings)
            self._save_rag_settings()
            self._rag_answer.setPlaceholderText(
                f"✅ RAG 已配置 (Model: {self._rag_settings.model})")

    def _on_open_browser(self):
        import webbrowser, sys
        from pathlib import Path
        # 查找 USER_GUIDE.html（支持 PyInstaller 打包）
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
            guide = os.path.join(base, 'USER_GUIDE.html')
        else:
            guide = str(Path(__file__).parent.parent / "USER_GUIDE.html")
        if os.path.exists(guide):
            webbrowser.open(f"file://{Path(guide).absolute()}")
        else:
            QMessageBox.warning(self, "提示", "帮助文件未找到。请确认 USER_GUIDE.html 存在。")

    def _load_rag_settings(self):
        try:
            from PySide6.QtCore import QSettings
            s = QSettings("AntennaPP", "AntennaPostProcessor")
            self._rag_settings.enabled = s.value("rag/enabled", False, type=bool)
            self._rag_settings.api_base = s.value("rag/api_base", self._rag_settings.api_base)
            self._rag_settings.api_key = s.value("rag/api_key", "")
            self._rag_settings.model = s.value("rag/model", self._rag_settings.model)
            self._engine.set_rag_settings(self._rag_settings)
        except Exception:
            pass

    def _save_rag_settings(self):
        try:
            from PySide6.QtCore import QSettings
            s = QSettings("AntennaPP", "AntennaPostProcessor")
            s.setValue("rag/enabled", self._rag_settings.enabled)
            s.setValue("rag/api_base", self._rag_settings.api_base)
            s.setValue("rag/api_key", self._rag_settings.api_key)
            s.setValue("rag/model", self._rag_settings.model)
        except Exception:
            pass


class RAGSettingsDialog(QDialog):
    """LLM RAG API 设置对话框。"""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM API 设置")
        self.setMinimumSize(450, 280)
        self.settings = settings
        self._setup_ui()

    def _setup_ui(self):
        from src.help_engine import RAGSettings
        layout = QVBoxLayout(self)

        fl = QFormLayout()
        fl.setSpacing(8)

        self._check_enable = QCheckBox("启用 RAG AI 问答")
        self._check_enable.setChecked(self.settings.enabled)
        fl.addRow("", self._check_enable)

        self._edit_base = QLineEdit(self.settings.api_base)
        self._edit_base.setPlaceholderText("https://api.anthropic.com/v1/messages")
        fl.addRow("API Base URL:", self._edit_base)

        self._edit_key = QLineEdit(self.settings.api_key)
        self._edit_key.setEchoMode(QLineEdit.Password)
        self._edit_key.setPlaceholderText("sk-ant-... 或 sk-...")
        fl.addRow("API Key:", self._edit_key)

        self._cmb_model = QComboBox()
        self._cmb_model.setEditable(True)
        models = [
            "claude-sonnet-4-6",
            "claude-opus-4-8",
            "gpt-4o",
            "gpt-4o-mini",
            "deepseek-chat",
        ]
        for m in models:
            self._cmb_model.addItem(m)
        if self.settings.model:
            idx = self._cmb_model.findText(self.settings.model)
            if idx >= 0:
                self._cmb_model.setCurrentIndex(idx)
            else:
                self._cmb_model.setCurrentText(self.settings.model)
        fl.addRow("Model:", self._cmb_model)

        layout.addLayout(fl)

        info = QLabel(
            "支持 Anthropic Messages API 和 OpenAI-compatible API。\n"
            "API Key 存储在本地 QSettings 中，不会上传。")
        info.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(info)

        layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        from src.help_engine import RAGSettings
        self.settings = RAGSettings(
            enabled=self._check_enable.isChecked(),
            api_base=self._edit_base.text().strip(),
            api_key=self._edit_key.text().strip(),
            model=self._cmb_model.currentText().strip(),
        )
        self.accept()


# ═══════════════════════════════════════════════════════════════
# 系统设置对话框 — 整合主题/语言/字体/LLM
# ═══════════════════════════════════════════════════════════════

class SystemSettingsDialog(QDialog):
    """系统设置: 字体大小 + 主题 + 语言 + LLM API。"""

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self._mw = parent
        self.setWindowTitle("系统设置")
        self.setMinimumSize(480, 360)
        self._setup_ui()
        self._load_state()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 字体大小 ──
        font_grp = QGroupBox("字体大小")
        font_layout = QHBoxLayout(font_grp)
        font_layout.addWidget(QLabel("A"))
        self._spin_font = QSpinBox()
        self._spin_font.setRange(8, 24)
        self._spin_font.setValue(13)
        self._spin_font.setSuffix(" px")
        font_layout.addWidget(self._spin_font)
        font_layout.addWidget(QLabel("A 大"))
        font_layout.addStretch()
        btn_font = QPushButton("应用字体")
        btn_font.clicked.connect(self._on_apply_font)
        font_layout.addWidget(btn_font)
        layout.addWidget(font_grp)

        # ── 主题 ──
        theme_grp = QGroupBox("主题")
        theme_layout = QHBoxLayout(theme_grp)
        self._cmb_theme = QComboBox()
        self._cmb_theme.setMinimumWidth(200)
        theme_layout.addWidget(QLabel("主题:"))
        theme_layout.addWidget(self._cmb_theme)
        theme_layout.addStretch()
        layout.addWidget(theme_grp)

        # ── 语言 ──
        lang_grp = QGroupBox("语言 / Language")
        lang_layout = QHBoxLayout(lang_grp)
        self._btn_lang = QPushButton("中文 / English")
        self._btn_lang.clicked.connect(self._on_toggle_lang)
        lang_layout.addWidget(self._btn_lang)
        lang_layout.addStretch()
        layout.addWidget(lang_grp)

        # ── LLM API ──
        llm_grp = QGroupBox("LLM API (RAG 问答)")
        llm_layout = QFormLayout(llm_grp)
        llm_layout.setSpacing(6)

        self._check_llm = QCheckBox("启用 RAG AI 问答")
        llm_layout.addRow("", self._check_llm)

        self._edit_api_base = QLineEdit()
        self._edit_api_base.setPlaceholderText("https://api.anthropic.com/v1/messages")
        llm_layout.addRow("API URL:", self._edit_api_base)

        self._edit_api_key = QLineEdit()
        self._edit_api_key.setEchoMode(QLineEdit.Password)
        self._edit_api_key.setPlaceholderText("sk-ant-... 或 sk-...")
        llm_layout.addRow("API Key:", self._edit_api_key)

        self._cmb_model = QComboBox()
        self._cmb_model.setEditable(True)
        for m in ["claude-sonnet-4-6", "claude-opus-4-8", "gpt-4o", "gpt-4o-mini", "deepseek-chat"]:
            self._cmb_model.addItem(m)
        llm_layout.addRow("Model:", self._cmb_model)

        layout.addWidget(llm_grp)

        layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_state(self):
        mw = self._mw
        # 字体
        app = QApplication.instance()
        font = app.font()
        self._spin_font.setValue(font.pointSize() if font.pointSize() > 0 else 13)
        # 主题
        from ui.theme_manager import ThemeManager
        for theme_id, name in ThemeManager.ALL_THEMES:
            self._cmb_theme.addItem(name, theme_id)
        cur = ThemeManager.current_theme()
        for i in range(self._cmb_theme.count()):
            if self._cmb_theme.itemData(i) == cur:
                self._cmb_theme.setCurrentIndex(i)
                break
        # 语言
        from i18n.i18n_manager import I18nManager
        lang = I18nManager.current_language()
        self._btn_lang.setText("English" if lang == "zh_CN" else "中文")
        # LLM
        from PySide6.QtCore import QSettings
        s = QSettings("AntennaPP", "AntennaPostProcessor")
        self._check_llm.setChecked(s.value("rag/enabled", False, type=bool))
        self._edit_api_base.setText(s.value("rag/api_base", "https://api.anthropic.com/v1/messages"))
        self._edit_api_key.setText(s.value("rag/api_key", ""))
        model = s.value("rag/model", "claude-sonnet-4-6")
        idx = self._cmb_model.findText(model)
        if idx >= 0:
            self._cmb_model.setCurrentIndex(idx)
        else:
            self._cmb_model.setCurrentText(model)

    def _on_apply_font(self):
        size = self._spin_font.value()
        app = QApplication.instance()
        font = app.font()
        font.setPointSize(size)
        app.setFont(font)

    def _on_toggle_lang(self):
        from i18n.i18n_manager import I18nManager
        new_lang = "en_US" if I18nManager.current_language() == "zh_CN" else "zh_CN"
        I18nManager.switch(QApplication.instance(), new_lang)
        self._btn_lang.setText("English" if new_lang == "zh_CN" else "中文")

    def _on_accept(self):
        # 字体
        self._on_apply_font()
        # 主题
        theme_id = self._cmb_theme.currentData()
        if theme_id:
            from ui.theme_manager import ThemeManager
            ThemeManager.apply(theme_id)
            ThemeManager.save_theme(theme_id)
        # LLM 设置保存
        from PySide6.QtCore import QSettings
        s = QSettings("AntennaPP", "AntennaPostProcessor")
        s.setValue("rag/enabled", self._check_llm.isChecked())
        s.setValue("rag/api_base", self._edit_api_base.text().strip())
        s.setValue("rag/api_key", self._edit_api_key.text().strip())
        s.setValue("rag/model", self._cmb_model.currentText().strip())
        self.accept()


# ═══════════════════════════════════════════════════════════════
# 步进重采样对话框
# ═══════════════════════════════════════════════════════════════

class ResampleDialog(QDialog):
    """步进重采样: 从源文件按指定步进批量导出重采样 CSV。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("步进重采样 — 数据提取")
        self.setMinimumSize(520, 380)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 源文件 ──
        src_grp = QGroupBox("源文件")
        src_row = QHBoxLayout(src_grp)
        self._edit_src = QLineEdit()
        self._edit_src.setPlaceholderText("选择 merged CSV 文件...")
        src_row.addWidget(self._edit_src, 1)
        btn_src = QPushButton("浏览...")
        btn_src.clicked.connect(self._on_browse_src)
        src_row.addWidget(btn_src)
        layout.addWidget(src_grp)

        # ── 输出目录 ──
        out_grp = QGroupBox("输出目录")
        out_row = QHBoxLayout(out_grp)
        self._edit_dir = QLineEdit()
        self._edit_dir.setPlaceholderText("默认: 源文件所在目录")
        out_row.addWidget(self._edit_dir, 1)
        btn_dir = QPushButton("浏览...")
        btn_dir.clicked.connect(self._on_browse_dir)
        out_row.addWidget(btn_dir)
        layout.addWidget(out_grp)

        # ── 目标步进 ──
        step_grp = QGroupBox("目标步进（度）— 多个步进用逗号分隔")
        step_layout = QVBoxLayout(step_grp)
        self._edit_steps = QLineEdit("5, 10, 15")
        self._edit_steps.setPlaceholderText("如: 5, 10, 15, 20")
        step_layout.addWidget(self._edit_steps)

        # 快捷步进按钮
        quick_row = QHBoxLayout()
        for s in [2, 5, 10, 15, 20, 30, 45]:
            btn = QPushButton(f"{s}°")
            btn.setFixedWidth(48)
            btn.clicked.connect(lambda checked, val=s: self._add_step(val))
            quick_row.addWidget(btn)
        quick_row.addStretch()
        step_layout.addLayout(quick_row)

        # 预览
        self._lbl_preview = QLabel("")
        self._lbl_preview.setStyleSheet("font-size: 11px; color: #888;")
        step_layout.addWidget(self._lbl_preview)

        layout.addWidget(step_grp)

        # ── 源文件信息 ──
        self._lbl_info = QLabel("")
        self._lbl_info.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(self._lbl_info)

        layout.addStretch()

        # ── 按钮 ──
        btn_row = QHBoxLayout()
        self._btn_run = QPushButton("▶ 开始批量导出")
        self._btn_run.clicked.connect(self._on_run)
        self._btn_run.setMinimumHeight(36)
        btn_row.addWidget(self._btn_run)
        btn_row.addStretch()
        btn_cancel = QPushButton("关闭")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        # 连接信号
        self._edit_src.textChanged.connect(self._on_src_changed)

    def _on_browse_src(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择源 CSV 文件", "",
            "CSV 文件 (*.csv);;所有文件 (*)")
        if path:
            self._edit_src.setText(path)

    def _on_browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._edit_dir.setText(d)

    def _add_step(self, val: int):
        current = self._edit_steps.text().strip()
        if not current:
            self._edit_steps.setText(str(val))
            return
        steps = [s.strip() for s in current.split(",") if s.strip()]
        if str(val) not in steps:
            steps.append(str(val))
            self._edit_steps.setText(", ".join(steps))
        self._update_preview()

    def _on_src_changed(self):
        path = self._edit_src.text().strip()
        if path and os.path.exists(path):
            try:
                from src.step_resampler import _read_all
                _, theta, phi, sfreqs = _read_all(path)
                freqs = list(sfreqs.values())[0] if sfreqs else []
                t_step = theta[1] - theta[0] if len(theta) > 1 else "?"
                p_step = phi[1] - phi[0] if len(phi) > 1 else "?"
                self._lbl_info.setText(
                    f"源文件: θ={theta[0]:.0f}~{theta[-1]:.0f}° (步进{t_step}°), "
                    f"φ={phi[0]:.0f}~{phi[-1]:.0f}° (步进{p_step}°), {len(freqs)} 频点")
            except Exception as e:
                self._lbl_info.setText(f"读取失败: {e}")
        self._update_preview()

    def _update_preview(self):
        path = self._edit_src.text().strip()
        steps_str = self._edit_steps.text().strip()
        if not path or not os.path.exists(path) or not steps_str:
            self._lbl_preview.setText("")
            return
        steps = _parse_steps(steps_str)
        if not steps:
            self._lbl_preview.setText("")
            return
        stem = Path(path).stem
        names = []
        for s in steps:
            s_str = str(int(s)) if s == int(s) else str(s).replace(".", "p")
            names.append(f"{stem}_step{s_str}deg.csv")
        self._lbl_preview.setText("输出文件: " + ", ".join(names))

    def _on_run(self):
        path = self._edit_src.text().strip()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "提示", "请选择有效的源 CSV 文件。")
            return

        steps_str = self._edit_steps.text().strip()
        if not steps_str:
            QMessageBox.warning(self, "提示", "请输入目标步进值。")
            return

        steps = _parse_steps(steps_str)
        if not steps:
            QMessageBox.warning(self, "提示", "无法解析步进值。请使用逗号分隔的数字，如: 5, 10, 15")
            return

        out_dir = self._edit_dir.text().strip()
        if not out_dir:
            out_dir = str(Path(path).parent)
        os.makedirs(out_dir, exist_ok=True)

        try:
            from src.step_resampler import batch_resample
            self._btn_run.setEnabled(False)
            self._btn_run.setText("处理中...")
            QApplication.processEvents()

            outputs = batch_resample(path, out_dir, steps)

            self._btn_run.setText("▶ 开始批量导出")
            self._btn_run.setEnabled(True)
            QMessageBox.information(self, "完成",
                f"成功导出 {len(outputs)} 个文件:\n" +
                "\n".join(f"  • {Path(o).name}" for o in outputs))
        except Exception as e:
            self._btn_run.setText("▶ 开始批量导出")
            self._btn_run.setEnabled(True)
            QMessageBox.critical(self, "错误", f"重采样失败: {e}")


def _parse_steps(text: str) -> List[float]:
    """解析步进字符串: '5, 10, 15' → [5.0, 10.0, 15.0]"""
    steps = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            val = float(part)
            if val > 0:
                steps.append(val)
        except ValueError:
            pass
    return steps
