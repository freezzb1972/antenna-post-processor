"""
设置对话框
=========
从主窗口通过菜单调出的设置对话框。
每个对话框管理一组相关设置,确认后将值写回主窗口。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPushButton,
    QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem,
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
        self.setMinimumSize(650, 550)
        self.resize(700, 600)
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
        self._btn_add = QPushButton("📂 添加数据文件..."); self._btn_add.clicked.connect(self._on_add_files)
        btn_clear = QPushButton("清除"); btn_clear.clicked.connect(self._on_clear_files)
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
        self._btn_match = QPushButton("🔗 自动匹配"); self._btn_match.clicked.connect(self._on_auto_match)
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
                for fp in (full_paths or data_files): combo.addItem(fp)
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
    """计算参数配置: 参数选择 + 角度配置 + 算法选项"""

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self._mw = parent
        self.setWindowTitle("计算参数配置")
        self.setMinimumSize(550, 450)
        self._setup_ui()
        self._load_state()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Tab 1: 参数选择
        tab_params = QWidget(); tabs.addTab(tab_params, "参数选择")
        pl = QVBoxLayout(tab_params)
        self._param_checkboxes = {}
        param_groups = [
            ("基础参数", [
                ("gain", "Gain / Peak EIRP"),
                ("directivity", "Directivity"),
                ("efficiency_pct", "Efficiency (%)"),
                ("efficiency_db", "Efficiency (dB)"),
                ("frequency", "Frequency"),
            ]),
            ("有源 TRP/TIS 参数", [
                ("trp", "Tot. Rad. Pwr. (TRP)"),
                ("tis", "Tot. Isot. Sens. (TIS)"),
                ("peak_eirp", "Peak EIRP"),
                ("nhprp_45", "NHPRP ±45° (Pi/4)"),
                ("nhprp_30", "NHPRP ±30° (Pi/6)"),
                ("nhprp_225", "NHPRP ±22.5° (Pi/8)"),
                ("nhprp_custom", "NHPRP 自定义角度"),
                ("nhpis_45", "NHPIS ±45° (Pi/4)"),
                ("nhpis_30", "NHPIS ±30° (Pi/6)"),
                ("nhpis_225", "NHPIS ±22.5° (Pi/8)"),
                ("nhpis_custom", "NHPIS 自定义角度"),
                ("uh_prp", "Upper Hem. PRP"),
                ("lh_prp", "Lower Hem. PRP"),
                ("uh_pis", "Upper Hem. PIS"),
                ("lh_pis", "Lower Hem. PIS"),
                ("prp_120", "PRP (theta 0-120°)"),
                ("pis_120", "PIS (theta 0-120°)"),
            ]),
            ("比率参数", [
                ("nhprp45_ratio", "NHPRP45 / TRP Ratio"),
                ("nhprp30_ratio", "NHPRP30 / TRP Ratio"),
                ("nhprp225_ratio", "NHPRP225 / TRP Ratio"),
                ("nhpis45_ratio", "NHPIS45 / TIS Ratio"),
                ("nhpis30_ratio", "NHPIS30 / TIS Ratio"),
                ("nhpis225_ratio", "NHPIS225 / TIS Ratio"),
                ("uh_ratio", "UHPRP / TRP Ratio"),
                ("lh_ratio", "LHPRP / TRP Ratio"),
                ("max_min_ratio", "Max/Min Ratio"),
                ("max_avg_ratio", "Max/Avg Ratio"),
                ("min_avg_ratio", "Min/Avg Ratio"),
            ]),
            ("方向与波束", [
                ("boresight_theta", "Boresight Theta"),
                ("boresight_phi", "Boresight Phi"),
                ("theta_bw", "Theta Beamwidth (3dB)"),
                ("phi_bw", "Phi Beamwidth (3dB)"),
                ("front_back_ratio", "Front/Back Ratio"),
            ]),
            ("功率统计", [
                ("max_power", "Maximum Power"),
                ("min_power", "Minimum Power"),
                ("avg_gain", "Average Gain"),
                ("avg_power", "Average Power"),
            ]),
            ("LAG 参数", [
                ("lag_single", "LAG 单角度"),
                ("lag_range", "LAG 范围"),
            ]),
            ("轴比参数 (AR)", [
                ("ar_single", "AR 单角度"),
                ("ar_range", "AR 范围"),
            ]),
        ]
        for grp_name, items in param_groups:
            grp = QGroupBox(grp_name); grp.setEnabled(True)
            gl = QVBoxLayout(grp)
            for key, label in items:
                cb = QCheckBox(label); cb.setChecked(True); cb.setEnabled(True)
                gl.addWidget(cb)
                self._param_checkboxes[key] = cb
            pl.addWidget(grp)
        pl.addStretch()

        # Tab 2: 角度配置
        tab_angles = QWidget(); tabs.addTab(tab_angles, "角度配置")
        al = QVBoxLayout(tab_angles)
        grp_quick = QGroupBox("快捷单角度")
        ql = QHBoxLayout(grp_quick)
        self._angle_buttons = {}
        for a in [0, 30, 60, 70, 80, 90]:
            btn = QPushButton(f"{a}°"); btn.setCheckable(True)
            ql.addWidget(btn); self._angle_buttons[a] = btn
        ql.addStretch()
        al.addWidget(grp_quick)

        grp_custom = QGroupBox("自定义角度")
        cl = QHBoxLayout(grp_custom)
        self._spin_custom = QDoubleSpinBox(); self._spin_custom.setRange(0, 180)
        self._spin_custom.setValue(0); self._spin_custom.setSuffix("°")
        cl.addWidget(QLabel("角度:")); cl.addWidget(self._spin_custom)
        btn_add = QPushButton("+"); btn_add.clicked.connect(self._add_angle)
        cl.addWidget(btn_add); cl.addStretch()
        al.addWidget(grp_custom)

        grp_range = QGroupBox("角度范围")
        rl = QHBoxLayout(grp_range)
        self._spin_start = QDoubleSpinBox(); self._spin_start.setRange(0, 180)
        self._spin_start.setValue(0); self._spin_start.setSuffix("°")
        self._spin_end = QDoubleSpinBox(); self._spin_end.setRange(0, 180)
        self._spin_end.setValue(90); self._spin_end.setSuffix("°")
        rl.addWidget(QLabel("起始:")); rl.addWidget(self._spin_start)
        rl.addWidget(QLabel("结束:")); rl.addWidget(self._spin_end)
        btn_range = QPushButton("添加范围"); rl.addWidget(btn_range); rl.addStretch()
        al.addWidget(grp_range)

        # NHPRP/NHPIS 自定义地平线角度
        grp_nh = QGroupBox("NHPRP/NHPIS 地平线边界角度")
        nhl = QHBoxLayout(grp_nh)
        nhl.addWidget(QLabel("±"))
        self._spin_nhprp_angle = QDoubleSpinBox(); self._spin_nhprp_angle.setRange(0, 90)
        self._spin_nhprp_angle.setValue(45.0); self._spin_nhprp_angle.setSuffix("°")
        nhl.addWidget(self._spin_nhprp_angle)
        nhl.addWidget(QLabel("(地平线±角度)"))
        nhl.addStretch()
        al.addWidget(grp_nh)
        al.addStretch()

        # Tab 3: 算法选项
        tab_algo = QWidget(); tabs.addTab(tab_algo, "算法选项")
        ol = QVBoxLayout(tab_algo)
        grp_freq = QGroupBox("频点设置")
        fl = QFormLayout(grp_freq)
        self._cmb_freq_src = QComboBox()
        self._cmb_freq_src.addItem("新 sheet 频点: 数据源", "datasource")
        self._cmb_freq_src.addItem("新 sheet 频点: 模板", "template")
        fl.addRow("频点来源:", self._cmb_freq_src)
        trim_row = QHBoxLayout()
        self._spin_trim_start = QSpinBox(); self._spin_trim_start.setRange(0, 50)
        self._spin_trim_end = QSpinBox(); self._spin_trim_end.setRange(0, 50)
        trim_row.addWidget(QLabel("前")); trim_row.addWidget(self._spin_trim_start)
        trim_row.addWidget(QLabel("后")); trim_row.addWidget(self._spin_trim_end)
        trim_row.addStretch()
        fl.addRow("去除频点:", trim_row)
        ol.addWidget(grp_freq)

        grp_algo = QGroupBox("计算算法")
        gl2 = QVBoxLayout(grp_algo)
        self._check_extrap = QCheckBox("Theta 外推到 180°")
        self._check_robust = QCheckBox("Robust peak detection (替代 np.max)")
        gl2.addWidget(self._check_extrap); gl2.addWidget(self._check_robust)
        ol.addWidget(grp_algo)
        ol.addStretch()

        layout.addWidget(tabs)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _add_angle(self):
        if self._spin_custom:
            a = self._spin_custom.value()
            for btn_a, btn in self._angle_buttons.items():
                if abs(btn_a - a) < 0.01:
                    btn.setChecked(True); return
            QMessageBox.information(self, "提示", f"角度 {a}° 不是预设值，请在主界面添加自定义角度")

    def _load_state(self):
        mw = self._mw
        # 角度按钮
        if hasattr(mw, '_lag_config'):
            for a, btn in self._angle_buttons.items():
                btn.setChecked(a in mw._lag_config.single_angles)
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

    def _on_accept(self):
        mw = self._mw
        if hasattr(mw, '_lag_config'):
            for a, btn in self._angle_buttons.items():
                if btn.isChecked() and a not in mw._lag_config.single_angles:
                    mw._lag_config.add_single(a)
                elif not btn.isChecked() and a in mw._lag_config.single_angles:
                    mw._lag_config.remove_single(a)
            mw._sync_quick_buttons(); mw._update_lag_display()
        if hasattr(mw, '_cmb_freq_source') and mw._cmb_freq_source:
            mw._cmb_freq_source.setCurrentIndex(self._cmb_freq_src.currentIndex())
        if hasattr(mw, '_spin_trim_start'):
            mw._spin_trim_start.setValue(self._spin_trim_start.value())
            mw._spin_trim_end.setValue(self._spin_trim_end.value())
        if hasattr(mw, '_check_extrapolate'):
            mw._check_extrapolate.setChecked(self._check_extrap.isChecked())
        if hasattr(mw, '_check_robust_peak'):
            mw._check_robust_peak.setChecked(self._check_robust.isChecked())
        self.accept()


# ═══════════════════════════════════════════════════════════════
# 图形配置对话框
# ═══════════════════════════════════════════════════════════════

class PlotConfigDialog(QDialog):
    """图形配置: 报告图形 + 展示图形 + 3D参数"""

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self._mw = parent
        self.setWindowTitle("图形配置")
        self.setMinimumSize(400, 350)
        self._setup_ui()
        self._load_state()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Tab 1: 报告图形
        tab_rpt = QWidget(); tabs.addTab(tab_rpt, "报告图形")
        rl = QVBoxLayout(tab_rpt)
        rl.addWidget(QLabel("以下图形嵌入 Excel 报告:"))
        self._check_rpt_eff = QCheckBox("效率 vs 频率曲线"); self._check_rpt_eff.setChecked(True)
        self._check_rpt_gain = QCheckBox("增益 @Theta 范围 vs 频率曲线"); self._check_rpt_gain.setChecked(True)
        rl.addWidget(self._check_rpt_eff); rl.addWidget(self._check_rpt_gain)
        rl.addStretch()

        # Tab 2: 展示图形
        tab_show = QWidget(); tabs.addTab(tab_show, "展示图形")
        sl = QVBoxLayout(tab_show)
        sl.addWidget(QLabel("以下图形仅在 GUI 中展示:"))
        self._check_show_3d = QCheckBox("3D 球面方向图"); self._check_show_3d.setChecked(True)
        self._check_show_2d = QCheckBox("2D 切面图"); self._check_show_2d.setChecked(False)
        sl.addWidget(self._check_show_3d); sl.addWidget(self._check_show_2d)
        sl.addStretch()

        # Tab 3: 图形参数
        tab_par = QWidget(); tabs.addTab(tab_par, "图形参数")
        fl = QFormLayout(tab_par)
        self._spin_elev = QDoubleSpinBox(); self._spin_elev.setRange(-90,90); self._spin_elev.setValue(30); self._spin_elev.setSuffix("°")
        self._spin_azim = QDoubleSpinBox(); self._spin_azim.setRange(-180,180); self._spin_azim.setValue(-60); self._spin_azim.setSuffix("°")
        self._spin_dpi = QSpinBox(); self._spin_dpi.setRange(72,300); self._spin_dpi.setValue(150)
        self._check_embed = QCheckBox("嵌入 Excel"); self._check_embed.setChecked(True)
        self._check_png = QCheckBox("保存 PNG 文件")
        fl.addRow("仰角:", self._spin_elev); fl.addRow("方位角:", self._spin_azim); fl.addRow("DPI:", self._spin_dpi)
        fl.addRow("", self._check_embed); fl.addRow("", self._check_png)

        layout.addWidget(tabs)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_state(self):
        mw = self._mw
        if hasattr(mw, 'ui'):
            if hasattr(mw.ui, 'checkEmbedExcel'): self._check_embed.setChecked(mw.ui.checkEmbedExcel.isChecked())
            if hasattr(mw.ui, 'checkSavePng'): self._check_png.setChecked(mw.ui.checkSavePng.isChecked())

    def _on_accept(self):
        mw = self._mw
        if hasattr(mw, 'ui'):
            if hasattr(mw.ui, 'checkEmbedExcel'): mw.ui.checkEmbedExcel.setChecked(self._check_embed.isChecked())
            if hasattr(mw.ui, 'checkSavePng'): mw.ui.checkSavePng.setChecked(self._check_png.isChecked())
        self.accept()
