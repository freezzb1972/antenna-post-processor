"""
主窗口
======
Qt Designer 编译 UI + 信号/槽逻辑。

功能：
  - 文件选择（CSV / 模板 / 输出）
  - LAG 配置面板交互
  - 3D 图形设置
  - 后台 Worker 启动/停止
  - 进度条 + 日志 + 状态栏
  - 中英文切换
  - Material Design 主题切换
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QEvent, QSettings, Qt, QThread
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QPalette, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from i18n.i18n_manager import I18nManager
from src.lag_config import LagConfig, PRESET_AUTOMOTIVE
from src.plot_config import PlotConfig
from src.chart_config import ChartConfig
from src.worker import ProcessingWorker
from ui.compiled.ui_main_window import Ui_MainWindow
from ui.theme_manager import ThemeManager


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """天线参数后处理工具主窗口。"""

    # 快捷按钮角度映射（单一定义，_connect_signals 和 _sync_quick_buttons 共享）
    _QUICK_ANGLES: dict = {
        0.0: "btnQuick0",
        30.0: "btnQuick30",
        60.0: "btnQuick60",
        70.0: "btnQuick70",
        80.0: "btnQuick80",
        90.0: "btnQuick90",
    }

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # 允许拖拽文件到窗口 (优先级2)
        self.setAcceptDrops(True)

        # ---- 状态 ----
        self._lag_config = LagConfig(
            single_angles=[60, 70, 80, 90],
            ranges=[(0, 90), (60, 90)],
        )
        self._thread: Optional[QThread] = None
        self._worker: Optional[ProcessingWorker] = None
        self._running = False
        self._settings = QSettings("AntennaPP", "AntennaPostProcessor")

        # 恢复窗口大小/位置 (优先级3)
        geo = self._settings.value("window_geometry")
        if geo: self.restoreGeometry(geo)
        self._data_file_paths: List[str] = []
        self._data_file_widget: Optional[QWidget] = None
        self._file_list_widget: Optional[QListWidget] = None
        self._match_table: Optional[QTableWidget] = None
        self._lbl_match_status: Optional[QLabel] = None
        self._required_params: set = set()   # 用户确认的报告必需参数
        self._extra_params: set = set()      # 用户额外选择的计算参数
        self._nh_edge_deg: float = 45.0      # NHPRP/NHPIS 自定义地平线边界角
        self._chart_config_required = None   # ChartConfig: 报告需要
        self._chart_config_extra = None      # ChartConfig: 额外(full_report)

        # ---- 初始化 ----
        self._init_theme_selector()
        self._apply_custom_qss()
        self._init_file_paths()
        self._init_multi_file_ui()
        self._init_params_tab()
        self._init_param_overview()
        self._connect_signals()
        self._update_lag_display()
        self._init_menu()
        self._hide_settings_tabs()
        self._log("天线参数后处理工具已启动")
        self._log(self.tr("默认 LAG 配置: 单角度 [60°, 70°, 80°, 90°], 范围 [(0-90°), (60-90°)]"))

    # ==================================================================
    # 初始化
    # ==================================================================

    def _init_file_paths(self):
        """从 QSettings 恢复上次路径。"""
        template_path = self._settings.value("template_path", "")
        output_dir = self._settings.value("output_dir", str(Path.cwd() / "output"))

        if template_path and Path(template_path).exists():
            self.ui.editTemplatePath.setText(template_path)
        if output_dir:
            self.ui.editOutputDir.setText(output_dir)

        self.ui.editOutputName.setText("antenna_report.xlsx")


    def _init_multi_file_ui(self):
        """构建多文件选择 + 自动匹配 UI（动态插入到 vTabFile）。"""
        # ---- 隐藏旧的单文件输入行（与多文件功能重复） ----
        self.ui.lblCsv.hide()
        self.ui.editCsvPath.hide()
        self.ui.btnBrowseCsv.hide()
        self.ui.groupInput.setTitle(self.tr("模板文件"))

        # ---- 输出字段加最小宽度，防止被压缩 ----
        self.ui.editOutputDir.setMinimumWidth(200)
        self.ui.editOutputName.setMinimumWidth(200)
        self.ui.editFullReportPath.setMinimumWidth(200)

        self._data_file_widget = QWidget()
        layout = QVBoxLayout(self._data_file_widget)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        # 数据文件按钮行
        btn_row = QHBoxLayout()
        self._btn_add_files = QPushButton(self.tr("📂 添加数据文件..."))
        self._btn_add_files.setToolTip(self.tr("选择多个数据文件 (Ctrl+点击多选 / 拖拽)"))
        self._btn_clear_files = QPushButton(self.tr("清除"))
        self._btn_add_files.clicked.connect(self._on_add_data_files)
        self._btn_clear_files.clicked.connect(self._on_clear_data_files)
        btn_row.addWidget(self._btn_add_files)
        btn_row.addWidget(self._btn_clear_files)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 文件列表 — 可滚动、自适应高度
        self._file_list_widget = QListWidget()
        self._file_list_widget.setMinimumHeight(80)
        self._file_list_widget.setMaximumHeight(160)
        self._file_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._file_list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._file_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._file_list_widget.setAlternatingRowColors(True)
        layout.addWidget(self._file_list_widget)

        # 匹配表
        self._match_table = QTableWidget()
        self._match_table.setColumnCount(3)
        self._match_table.setHorizontalHeaderLabels([
            self.tr("工作表"), self.tr("数据文件"), self.tr("状态")
        ])
        self._match_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._match_table.verticalHeader().setDefaultSectionSize(28)
        self._match_table.verticalHeader().setVisible(False)
        self._match_table.setMinimumHeight(100)
        self._match_table.setMaximumHeight(200)
        self._match_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._match_table.setAlternatingRowColors(True)
        layout.addWidget(self._match_table)

        # 自动匹配按钮行
        match_row = QHBoxLayout()
        self._btn_auto_match = QPushButton(self.tr("🔗 自动匹配"))
        self._btn_auto_match.clicked.connect(self._on_auto_match)
        self._btn_auto_match.setToolTip(self.tr("按文件命名自动匹配工作表"))
        self._lbl_match_status = QLabel("")
        self._lbl_match_status.setMinimumHeight(22)
        self._lbl_match_status.setStyleSheet("font-size: 12px; padding: 2px 0;")
        match_row.addWidget(self._btn_auto_match)
        match_row.addWidget(self._lbl_match_status)
        match_row.addStretch()
        layout.addLayout(match_row)

        # 图表选择行
        chart_row = QHBoxLayout()
        self._check_chart_eff = QCheckBox(self.tr("效率曲线"))
        self._check_chart_eff.setChecked(True)
        chart_row.addWidget(self._check_chart_eff)
        self._check_chart_lag = QCheckBox(self.tr("增益曲线"))
        self._check_chart_lag.setChecked(True)
        chart_row.addWidget(self._check_chart_lag)
        chart_row.addStretch()
        layout.addLayout(chart_row)

        # 插入到 groupInput 之后
        vtab = self.ui.vTabFile
        idx = vtab.indexOf(self.ui.groupInput)
        if idx >= 0:
            vtab.insertWidget(idx + 1, self._data_file_widget)

        # 完整报告路径显示/隐藏
        self.ui.checkFullReport.toggled.connect(self._on_full_report_toggled)
        self._on_full_report_toggled(self.ui.checkFullReport.isChecked())

        # ---- 将整个 Tab 的内容包裹在可滚动区域中，防止内容溢出被压缩 ----
        self._make_tab_scrollable(self.ui.tabFile)
        self._make_tab_scrollable(self.ui.tabLag)

    def _init_params_tab(self):
        """构建「参数设置」标签页（频点 + 算法选项）。"""
        vtab = self.ui.vTabCalc

        group_freq = QGroupBox(self.tr("频点设置"))
        freq_form = QFormLayout(group_freq)
        freq_form.setSpacing(8)

        self._cmb_freq_source = QComboBox()
        self._cmb_freq_source.addItem(self.tr("新 sheet 频点: 数据源"), "datasource")
        self._cmb_freq_source.addItem(self.tr("新 sheet 频点: 模板"), "template")
        freq_form.addRow(self.tr("频点来源:"), self._cmb_freq_source)

        trim_row = QHBoxLayout()
        trim_row.addWidget(QLabel(self.tr("前")))
        self._spin_trim_start = self._create_spinbox(0, 0, 50, self.tr("去除数据前 N 个频点"))
        trim_row.addWidget(self._spin_trim_start)
        trim_row.addWidget(QLabel(self.tr("后")))
        self._spin_trim_end = self._create_spinbox(0, 0, 50, self.tr("去除数据后 N 个频点"))
        trim_row.addStretch()
        freq_form.addRow(self.tr("去除频点:"), trim_row)

        vtab.addWidget(group_freq)

        group_algo = QGroupBox(self.tr("计算算法"))
        algo_vbox = QVBoxLayout(group_algo)
        algo_vbox.setSpacing(6)

        self._check_extrapolate = QCheckBox(
            self.tr("Theta 外推到 180°"))
        self._check_extrapolate.setChecked(False)
        algo_vbox.addWidget(self._check_extrapolate)

        self._check_robust_peak = QCheckBox(
            self.tr("Robust peak detection (替代 np.max)"))
        self._check_robust_peak.setChecked(False)
        self._check_robust_peak.setToolTip(self.tr(
            "启用后使用鲁棒峰值检测。适用于存在异常值的数据。默认关闭（IEEE 149 np.max）。"))
        algo_vbox.addWidget(self._check_robust_peak)

        algo_vbox.addStretch()
        vtab.addWidget(group_algo)
        vtab.addStretch()

        self._make_tab_scrollable(self.ui.tabCalc)

    def _init_param_overview(self):
        """在处理参数配置 Tab 顶部插入参数分类概览面板。"""
        vtab = self.ui.vTabLag

        overview = QGroupBox(self.tr("计算参数分类"))
        ov_layout = QVBoxLayout(overview)
        ov_layout.setSpacing(3)

        params = [
            ("📡", self.tr("无源天线参数"), self.tr("Gain, Directivity, Efficiency, LAG, AR, 波束, 功率统计")),
            ("📶", self.tr("有源发射 TRP"), self.tr("TRP, Peak EIRP, NHPRP, 半球 PRP, 比率")),
            ("📻", self.tr("有源接收 TIS"), self.tr("TIS, NHPIS, 半球 PIS, 比率")),
        ]
        for icon, name, desc in params:
            row = QHBoxLayout()
            lbl = QLabel(f"{icon} {name}: {desc}")
            lbl.setStyleSheet("font-size: 12px; color: #aaa;")
            row.addWidget(lbl)
            row.addStretch()
            ov_layout.addLayout(row)

        vtab.insertWidget(0, overview)

    def _make_tab_scrollable(self, tab: QWidget):
        """将指定 Tab 的内容包裹在 QScrollArea 中，防止内容溢出被压缩。"""
        layout = tab.layout()
        if layout is None:
            return
        # 创建 scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        # 创建内容 widget，移入 layout
        content = QWidget()
        content.setLayout(layout)
        scroll.setWidget(content)
        # 替换 tab
        tc = self.ui.tabConfig
        for i in range(tc.count()):
            if tc.widget(i) is tab:
                title = tc.tabText(i)
                tc.removeTab(i)
                tc.insertTab(i, scroll, title)
                break

    # ==================================================================
    # 菜单
    # ==================================================================

    def _init_menu(self):
        from PySide6.QtGui import QAction, QKeySequence
        menubar = self.menuBar()
        fm = menubar.addMenu(self.tr("&文件"))
        fm.addAction(self.tr("保存结果..."), self._on_browse_output, QKeySequence("Ctrl+S"))
        fm.addSeparator(); fm.addAction(self.tr("退出"), self.close, QKeySequence("Ctrl+Q"))
        sm = menubar.addMenu(self.tr("&设置"))
        sm.addAction(self.tr("数据源配置..."), self._show_data_source_dialog)
        sm.addAction(self.tr("计算参数配置..."), self._show_calc_params_dialog)
        sm.addAction(self.tr("图形配置..."), self._show_plot_config_dialog)
        pm = menubar.addMenu(self.tr("&处理"))
        pm.addAction(self.tr("▶ 开始处理"), self._on_start, QKeySequence("F5"))
        pm.addAction(self.tr("⏹ 停止"), self._on_stop, QKeySequence("Esc"))
        tm = menubar.addMenu(self.tr("&工具"))
        tm.addAction(self.tr("数据转换 (Raw→标准)..."), self._on_tool_convert)
        tm.addAction(self.tr("数据合并 (多段拼接)..."), self._on_tool_merge)
        hm = menubar.addMenu(self.tr("&帮助"))
        hm.addAction(self.tr("使用说明"), self._on_help, QKeySequence("F1"))
        hm.addAction(self.tr("关于..."), self._on_about)

    def _hide_settings_tabs(self):
        tc = self.ui.tabConfig
        for tab, idx in [(self.ui.tabFile, 0), (self.ui.tabLag, 1), (self.ui.tabPlot, 2), (self.ui.tabCalc, 3)]:
            if idx < tc.count(): tc.setTabVisible(idx, False)

    def _show_data_source_dialog(self):
        from ui.dialogs import DataSourceDialog
        DataSourceDialog(self).exec()

    def _show_calc_params_dialog(self):
        from ui.dialogs import CalcParamsDialog
        dlg = CalcParamsDialog(self)
        # 传递模板自动识别的参数
        tp = self._get_template_params()
        if tp:
            dlg.set_template_params(tp)
        if dlg.exec():
            # 状态由对话框在 _on_accept 中直接写入 self._mw
            pass

    def _get_template_params(self) -> set:
        """读取模板，提取所有 Sheet 的列类型集合。"""
        tp = self.ui.editTemplatePath.text().strip()
        if not tp or not Path(tp).exists():
            return set()
        try:
            from src.excel_reader import read_template
            sheets = read_template(tp)
            params = set()
            for si in sheets:
                for c in si.columns:
                    params.add(c.col_type)
            return params - {"unknown", "frequency"}
        except Exception:
            return set()

    def _show_plot_config_dialog(self):
        from ui.dialogs import PlotConfigDialog
        from src.chart_config import ChartConfig

        # 首次打开时，从模板自动检测图形需求
        if self._chart_config_required is None:
            tp = self.ui.editTemplatePath.text().strip()
            if tp and Path(tp).exists():
                try:
                    self._chart_config_required = ChartConfig.from_template(tp)
                except Exception:
                    self._chart_config_required = ChartConfig()
            else:
                self._chart_config_required = ChartConfig()
        if self._chart_config_extra is None:
            self._chart_config_extra = ChartConfig()

        dlg = PlotConfigDialog(self)
        dlg.exec()

    def _on_help(self):
        from ui.dialogs import HelpDialog
        dlg = HelpDialog(self)
        dlg.exec()

    def _on_tool_convert(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("选择 Raw CSV 文件"), "",
            self.tr("CSV 文件 (*.csv);;所有文件 (*)"))
        if not path: return
        out = str(Path(path).parent / f"{Path(path).stem}_converted.csv")
        out_path, _ = QFileDialog.getSaveFileName(self, self.tr("保存转换结果"), out,
            self.tr("CSV 文件 (*.csv)"))
        if not out_path: return
        try:
            from src.raw_converter import convert_aborted_to_normal
            self._log(f"🔄 数据转换: {Path(path).name}")
            result = convert_aborted_to_normal(path, out_path,
                progress_callback=lambda c, t, m: self._on_progress(c, t, m))
            self._log(f"✓ 转换完成: {result}")
            QMessageBox.information(self, self.tr("完成"), self.tr(f"转换完成:\n{result}"))
        except Exception as e:
            self._log(f"✗ 转换失败: {e}")
            QMessageBox.critical(self, self.tr("错误"), str(e))

    def _on_tool_merge(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self.tr("选择要合并的 CSV 文件 (可多选)"), "",
            self.tr("CSV 文件 (*.csv);;所有文件 (*)"))
        if len(paths) < 2: return
        out = str(Path(paths[0]).parent / "merged.csv")
        out_path, _ = QFileDialog.getSaveFileName(self, self.tr("保存合并结果"), out,
            self.tr("CSV 文件 (*.csv)"))
        if not out_path: return
        try:
            from src.raw_converter import merge_csv_files
            self._log(f"🔗 数据合并: {len(paths)} 个文件")
            result = merge_csv_files(paths, out_path,
                progress_callback=lambda c, t, m: self._on_progress(c, t, m))
            self._log(f"✓ 合并完成: {result}")
            QMessageBox.information(self, self.tr("完成"), self.tr(f"合并完成:\n{result}"))
        except Exception as e:
            self._log(f"✗ 合并失败: {e}")
            QMessageBox.critical(self, self.tr("错误"), str(e))

    def _on_about(self):
        QMessageBox.about(self, self.tr("关于"),
            self.tr("天线参数后处理工具 v2.0\n\n从 EMQuest 数据计算天线参数\nGitHub: freezzb1972/antenna-post-processor"))

    # ==================================================================
    # 多文件操作
    # ==================================================================

    def _on_add_data_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, self.tr("选择数据文件 (可多选)"),
            self._settings.value("csv_path", ""),
            self.tr("所有支持格式 (*.csv *.xlsx *.xls);;CSV 文件 (*.csv);;Excel 新版 (*.xlsx);;Excel 旧版 (*.xls);;所有文件 (*)")
        )
        if not paths:
            return
        existing = set(self._data_file_paths)
        new_paths = [p for p in paths if p not in existing]
        if not new_paths:
            return
        self._data_file_paths.extend(new_paths)
        self._settings.setValue("csv_path", new_paths[0])
        self._refresh_data_file_ui()
        if self.ui.editTemplatePath.text().strip():
            self._on_auto_match()

    def _on_clear_data_files(self):
        self._data_file_paths.clear()
        self._file_list_widget.clear()
        self._match_table.setRowCount(0)
        self._lbl_match_status.setText("")

    def _refresh_data_file_ui(self):
        if self._file_list_widget is None:
            return
        self._file_list_widget.clear()
        for p in self._data_file_paths:
            try:
                size_mb = Path(p).stat().st_size / (1024 * 1024)
                self._file_list_widget.addItem(f"📄 {Path(p).name}  ({size_mb:.1f} MB)")
            except OSError:
                self._file_list_widget.addItem(f"📄 {Path(p).name}")

    def _on_auto_match(self):
        template_path = self.ui.editTemplatePath.text().strip()
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
            self._log(f"模板中未检测到数据工作表")
            return

        matches = auto_match(sheet_names, self._data_file_paths)
        self._populate_match_table(matches)

        matched = sum(1 for m in matches if m.file_path is not None)
        self._lbl_match_status.setText(
            f"✓ {matched}/{len(matches)} 个工作表已匹配"
        )
        self._log(f"自动匹配完成: {matched}/{len(matches)}")

    def _populate_match_table(self, matches):
        self._match_table.setRowCount(len(matches))
        for i, m in enumerate(matches):
            self._match_table.setRowHeight(i, 28)
            self._match_table.setItem(i, 0, QTableWidgetItem(m.sheet_name))
            combo = QComboBox()
            combo.addItem("—")
            for fp in self._data_file_paths:
                combo.addItem(fp)
            if m.file_path:
                idx = combo.findText(m.file_path)
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
        fp = combo.currentText().strip() if combo else ""
        valid = fp and fp != "—" and Path(fp).exists()
        status = self._match_table.item(row, 2)
        if status:
            if valid:
                status.setText(self.tr("✓ 已匹配"))
                status.setForeground(QColor("green"))
            else:
                status.setText(self.tr("未匹配"))
                status.setForeground(QColor("orange"))

    def _build_datasource_map(self):
        from src.datasource import DataSource
        from src.sheet_file_matcher import extract_key
        result = {}

        # 已匹配的行
        matched_files = set()
        for row in range(self._match_table.rowCount()):
            sheet_name = self._match_table.item(row, 0).text()
            combo = self._match_table.cellWidget(row, 1)
            fp = combo.currentText().strip() if combo else ""
            if fp and fp != "—" and Path(fp).exists():
                try:
                    result[sheet_name] = DataSource.from_path(fp)
                    matched_files.add(fp)
                except Exception as e:
                    self._log(f"⚠ {sheet_name} 数据源加载失败: {e}")

        # 未匹配的剩余数据文件：自动按命名推导工作表名
        unmatched = [f for f in self._data_file_paths if f not in matched_files]
        if unmatched and self._match_table.rowCount() > 0:
            ref_name = self._match_table.item(0, 0).text() if self._match_table.item(0, 0) else ""
            for fp in unmatched:
                key = extract_key(fp).lstrip("0123456789")
                sheet_name = self._derive_new_sheet_name(ref_name, key)
                try:
                    result[sheet_name] = DataSource.from_path(fp)
                    self._log(f"  ↗ 自动添加: {sheet_name} ← {Path(fp).name}")
                except Exception as e:
                    self._log(f"⚠ {Path(fp).name} 加载失败: {e}")

        return result

    def _derive_new_sheet_name(self, reference_name: str, target_key: str) -> str:
        """从参考工作表名推导新工作表名: "5G1"+"G2" → "5G2" """
        import re
        m = re.search(r'G\d+', reference_name, re.IGNORECASE)
        tk = re.search(r'G\d+', target_key, re.IGNORECASE)
        if m and tk:
            return reference_name[:m.start()] + tk.group(0).upper() + reference_name[m.end():]
        return target_key

    def _init_theme_selector(self):
        """填充主题下拉框并选中当前主题。"""
        cmb = self.ui.cmbThemeSelector
        for theme_id, display_name in ThemeManager.ALL_THEMES:
            cmb.addItem(display_name, theme_id)
        current = ThemeManager.current_theme()
        for i in range(cmb.count()):
            if cmb.itemData(i) == current:
                cmb.setCurrentIndex(i)
                break

    def _apply_custom_qss(self):
        """统一配色/字体微调。qt-material 主题已覆盖大部分样式。"""
        base_font = "font-size: 13px;"
        qss = f"""
        * {{ {base_font} }}
        QGroupBox {{
            border: 1px solid rgba(128,128,128,50);
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 14px;
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }}
        QPlainTextEdit {{
            border-radius: 4px;
            font-family: "Consolas","Courier New",monospace;
            font-size: 12px;
        }}
        QPushButton#btnStart {{
            font-size: 14px;
            font-weight: bold;
            letter-spacing: 1px;
        }}
        QPushButton#btnStop {{ font-size: 14px; }}
        """
        self.app.setStyleSheet(self.app.styleSheet() + qss)

    def _connect_signals(self):
        """连接所有信号/槽。"""
        # 主题切换
        self.ui.cmbThemeSelector.currentIndexChanged.connect(self._on_theme_changed)

        # 文件浏览
        self.ui.btnBrowseTemplate.clicked.connect(self._on_browse_template)
        self.ui.btnBrowseOutput.clicked.connect(self._on_browse_output)
        self.ui.btnBrowseFullReport.clicked.connect(self._on_browse_full_report)

        # LAG 快捷按钮
        for angle, btn_attr in self._QUICK_ANGLES.items():
            btn = getattr(self.ui, btn_attr)
            btn.clicked.connect(lambda checked, a=angle: self._toggle_quick_angle(a))
        self.ui.btnAddCustomAngle.clicked.connect(self._add_custom_angle)

        # LAG 步进
        self.ui.btnStepGenerate.clicked.connect(self._on_step_generate)
        # LAG 范围
        self.ui.btnAddRange.clicked.connect(self._on_add_range)
        # LAG 操作按钮
        self.ui.btnLoadFromTemplate.clicked.connect(self._on_load_from_template)
        self.ui.btnClearConfig.clicked.connect(self._on_clear_config)
        self.ui.btnSavePreset.clicked.connect(self._on_save_preset)
        self.ui.btnLoadPreset.clicked.connect(self._on_load_preset)

        # 运行
        self.ui.btnStart.clicked.connect(self._on_start)
        self.ui.btnStop.clicked.connect(self._on_stop)

        # 语言切换
        self.ui.btnLangToggle.clicked.connect(self._on_toggle_language)
        self._update_lang_button()

    # ==================================================================
    # 文件浏览
    # ==================================================================

    @staticmethod
    def _create_spinbox(value, min_v, max_v, tooltip=""):
        sb = QSpinBox()
        sb.setRange(min_v, max_v)
        sb.setValue(value)
        sb.setToolTip(tooltip)
        sb.setFixedWidth(50)
        return sb

    def _on_full_report_toggled(self, checked: bool):
        """完整报告复选框切换 → 显示/隐藏路径输入框。"""
        self.ui.lblFullReportPath.setVisible(checked)
        self.ui.editFullReportPath.setVisible(checked)
        self.ui.btnBrowseFullReport.setVisible(checked)

    def _on_browse_template(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择模板 Excel 文件"),
            self._settings.value("template_path", ""),
            self.tr("Excel 文件 (*.xlsx *.xls);;所有文件 (*)")
        )
        if path:
            self.ui.editTemplatePath.setText(path)
            self._settings.setValue("template_path", path)

    def _on_browse_output(self):
        start_dir = self.ui.editOutputDir.text() or str(Path.cwd() / "output")
        path = QFileDialog.getExistingDirectory(
            self, self.tr("选择输出目录"), start_dir
        )
        if path:
            self.ui.editOutputDir.setText(path)
            self._settings.setValue("output_dir", path)

    def _on_browse_full_report(self):
        start_dir = self.ui.editFullReportPath.text() or str(Path.cwd() / "output")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存完整报告"),
            str(Path(start_dir) / "full_report.xlsx"),
            self.tr("Excel 文件 (*.xlsx)")
        )
        if path:
            self.ui.editFullReportPath.setText(path)

    # ==================================================================
    # LAG 配置
    # ==================================================================

    def _toggle_quick_angle(self, angle: float):
        """切换快捷按钮对应的单角度。"""
        if angle in self._lag_config.single_angles:
            self._lag_config.remove_single(angle)
        else:
            self._lag_config.add_single(angle)
        self._sync_quick_buttons()
        self._update_lag_display()

    def _add_custom_angle(self):
        angle = self.ui.spinCustomAngle.value()
        if angle in self._lag_config.single_angles:
            return  # 已存在，跳过
        self._lag_config.add_single(angle)
        self._sync_quick_buttons()
        self._update_lag_display()
        self._log(f"添加单角度: {angle}°")

    def _on_step_generate(self):
        start = self.ui.spinStepStart.value()
        end = self.ui.spinStepEnd.value()
        step = self.ui.spinStepBy.value()
        gen = LagConfig.from_start_step(start, end, step)
        for a in gen.single_angles:
            self._lag_config.add_single(a)
        self._sync_quick_buttons()
        self._update_lag_display()
        self._log(self.tr(f"步进生成: {start}° → {end}°, step={step}° → {len(gen.single_angles)} 个角度"))

    def _on_add_range(self):
        lo = self.ui.spinRStart.value()
        hi = self.ui.spinREnd.value()
        key = (min(lo, hi), max(lo, hi))
        if key in self._lag_config.ranges:
            return  # 已存在，跳过
        self._lag_config.add_range(lo, hi)
        self._update_lag_display()
        self._log(f"添加 LAG 范围: ({lo}°-{hi}°)")

    def _on_load_from_template(self):
        template_path = self.ui.editTemplatePath.text()
        if not template_path or not Path(template_path).exists():
            QMessageBox.warning(self, self.tr("警告"), self.tr("请先选择模板 Excel 文件。"))
            return

        try:
            from src.excel_reader import read_template
            sheets = read_template(template_path)
            if sheets:
                # 合并所有 Sheet 的 LAG 配置
                merged = LagConfig()
                for si in sheets:
                    for a in si.lag_config.single_angles:
                        merged.add_single(a)
                    for r in si.lag_config.ranges:
                        merged.add_range(*r)
                if not merged.is_empty():
                    self._lag_config = merged
                    self._sync_quick_buttons()
                    self._update_lag_display()
                    self._log(f"从模板加载: {len(sheets)} 个工作表")
                    for si in sheets:
                        self._log(f"  {si.name}: 单角度={si.lag_config.singles_sorted}, 范围={si.lag_config.ranges_sorted}")
                else:
                    self._log("模板中未检测到 LAG 列")
        except Exception as e:
            QMessageBox.critical(self, self.tr("错误"), self.tr(f"读取模板失败: {e}"))

    def _on_clear_config(self):
        self._lag_config.clear()
        self._sync_quick_buttons()
        self._update_lag_display()
        self._log("LAG 配置已清空")

    def _on_save_preset(self):
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存 LAG 预设"), "lag_preset.json",
            self.tr("JSON 文件 (*.json)")
        )
        if path:
            self._lag_config.save_preset(Path(path))
            self._log(f"预设已保存: {path}")

    def _on_load_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("加载 LAG 预设"), "",
            self.tr("JSON 文件 (*.json);;所有文件 (*)")
        )
        if path:
            try:
                self._lag_config = LagConfig.load_preset(Path(path))
                self._sync_quick_buttons()
                self._update_lag_display()
                self._log(f"预设已加载: {path}")
            except Exception as e:
                QMessageBox.critical(self, self.tr("错误"), self.tr(f"加载预设失败: {e}"))

    def _sync_quick_buttons(self):
        """同步快捷按钮选中状态。"""
        for angle, btn_attr in self._QUICK_ANGLES.items():
            btn = getattr(self.ui, btn_attr)
            btn.setChecked(angle in self._lag_config.single_angles)

    def _update_lag_display(self):
        """刷新已配置项 — 每项带删除按钮。"""
        widget = self.ui.configItemsWidget
        layout = widget.layout()
        if layout is None:
            from PySide6.QtWidgets import QVBoxLayout
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
        # 清除所有旧 widget
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        singles = self._lag_config.singles_sorted
        ranges = self._lag_config.ranges_sorted

        if not singles and not ranges:
            label = QLabel(self.tr("—"))
            label.setStyleSheet("font-size: 13px; color: #888; padding: 8px;")
            layout.addWidget(label)
            return

        # ---- 单角度 ----
        if singles:
            header = QLabel(self.tr("单角度："))
            header.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 4px;")
            layout.addWidget(header)
            for a in singles:
                row = QWidget()
                row.setMinimumHeight(30)
                h = QHBoxLayout(row)
                h.setContentsMargins(8, 4, 0, 4)
                h.setSpacing(8)
                lbl = QLabel(f"  {a}°")
                lbl.setStyleSheet("font-size: 13px;")
                lbl.setMinimumHeight(24)
                btn = QPushButton(" ✕ ")
                btn.setFixedHeight(24)
                btn.setToolTip(self.tr("移除此角度"))
                btn.setStyleSheet("font-size: 11px; padding: 2px 6px;")
                btn.clicked.connect(lambda checked, angle=a: self._remove_single(angle))
                h.addWidget(lbl)
                h.addWidget(btn)
                h.addStretch()
                layout.addWidget(row)

        # ---- 角度范围 ----
        if ranges:
            header = QLabel(self.tr("角度范围："))
            header.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 4px;")
            layout.addWidget(header)
            for lo, hi in ranges:
                row = QWidget()
                row.setMinimumHeight(30)
                h = QHBoxLayout(row)
                h.setContentsMargins(8, 4, 0, 4)
                h.setSpacing(8)
                lbl = QLabel(f"  ({lo}° - {hi}°)")
                lbl.setStyleSheet("font-size: 13px;")
                lbl.setMinimumHeight(24)
                btn = QPushButton(" ✕ ")
                btn.setFixedHeight(24)
                btn.setToolTip(self.tr("移除此范围"))
                btn.setStyleSheet("font-size: 11px; padding: 2px 6px;")
                btn.clicked.connect(lambda checked, lo=lo, hi=hi: self._remove_range(lo, hi))
                h.addWidget(lbl)
                h.addWidget(btn)
                h.addStretch()
                layout.addWidget(row)

        layout.addStretch()

    def _remove_single(self, angle: float):
        self._lag_config.remove_single(angle)
        self._sync_quick_buttons()
        self._update_lag_display()

    def _remove_range(self, lo: float, hi: float):
        self._lag_config.remove_range(lo, hi)
        self._update_lag_display()

    # ==================================================================
    # 运行控制
    # ==================================================================

    def _on_start(self):
        """启动后台处理。支持单文件或多文件模式。"""
        if self._running:
            return
        if not self._data_file_paths:
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("请先通过「设置→数据源配置」添加数据文件并执行自动匹配。"))
            return

        # 自动触发匹配
        if self._match_table.rowCount() == 0 and self._data_file_paths:
            try:
                self._on_auto_match()
            except Exception:
                pass

        template_path = self.ui.editTemplatePath.text().strip()
        output_dir = self.ui.editOutputDir.text().strip() or str(Path.cwd() / "output")
        output_name = self.ui.editOutputName.text().strip() or "antenna_report.xlsx"
        output_name = output_name.replace("\\", "").replace("/", "")

        if not template_path:
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("请选择模板 Excel 文件。"))
            return
        if not Path(template_path).exists():
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("模板文件不存在"))
            return
        template_ext = Path(template_path).suffix.lower()
        if template_ext not in (".xlsx", ".xls"):
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("模板文件必须是 Excel 格式 (.xlsx .xls)"))
            return

        os.makedirs(output_dir, exist_ok=True)
        output_path = str(Path(output_dir) / output_name)

        full_report_path: Optional[str] = None
        if self.ui.checkFullReport.isChecked():
            path_text = self.ui.editFullReportPath.text().strip()
            full_report_path = path_text if path_text else str(Path(output_dir) / "full_report.xlsx")

        plot_config = PlotConfig(
            elev=self.ui.spinElev.value(),
            azim=self.ui.spinAzim.value(),
            dpi=self.ui.spinDpi.value(),
            embed_in_excel=self.ui.checkEmbedExcel.isChecked(),
            save_png_folder=str(Path(output_dir) / "png") if self.ui.checkSavePng.isChecked() else None,
        )

        datasource = None
        datasource_map = self._build_datasource_map()
        if not datasource_map:
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("没有有效的工作表↔文件匹配，请先执行自动匹配。"))
            return
        self._log(f"多源模式: {len(datasource_map)} 个工作表")
        for sn, ds in datasource_map.items():
            self._log(f"  {sn} ← {type(ds).__name__}")

        self.ui.logOutput.clear()
        self.ui.progressBar.setValue(0)
        self.ui.lblProgressMsg.setText(self.tr("启动中..."))

        self._thread = QThread(self)
        # 合并图表配置（报告需要 + 额外）
        full_chart_config = None
        if self._chart_config_required is not None or self._chart_config_extra is not None:
            req = self._chart_config_required or ChartConfig()
            xtr = self._chart_config_extra or ChartConfig()
            full_chart_config = req.merge(xtr)
            if hasattr(plot_config, 'save_png_folder'):
                png_dir = plot_config.save_png_folder
            else:
                png_dir = str(Path(output_dir) / "png") if self.ui.checkSavePng.isChecked() else None
            full_chart_config.save_png_folder = png_dir

        self._worker = ProcessingWorker(
            datasource=datasource,
            datasource_map=datasource_map,
            template_path=template_path,
            output_path=output_path,
            lag_config=self._lag_config,
            plot_config=plot_config,
            full_report_path=full_report_path,
            extrapolate_theta=self._check_extrapolate.isChecked(),
            freq_source=self._cmb_freq_source.currentData() or "datasource",
            trim_start=self._spin_trim_start.value(),
            trim_end=self._spin_trim_end.value(),
            chart_eff=self._check_chart_eff.isChecked(),
            chart_lag=self._check_chart_lag.isChecked(),
            robust_peak=self._check_robust_peak.isChecked(),
            extra_params=self._extra_params if self._extra_params else None,
            chart_config_obj=full_chart_config,
        )
        self._worker.moveToThread(self._thread)

        # 连接信号
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_worker_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._thread.finished.connect(self._thread.deleteLater)

        # 设置运行状态
        self._running = True
        self.ui.btnStart.setEnabled(False)
        self.ui.btnStop.setEnabled(True)

        self._thread.start()
        self._log(self.tr(f"▶ 开始处理"))
        self._log(self.tr(f"  模板: {template_path}"))
        self._log(self.tr(f"  输出: {output_path}"))
        if full_report_path:
            self._log(self.tr(f"  完整报告: {full_report_path}"))

    def _on_stop(self):
        """停止处理。"""
        if self._worker:
            self._worker.cancel()
        self._log("⏹ 用户请求停止...")
        self.ui.btnStop.setEnabled(False)

    def _on_progress(self, current: int, total: int, message: str):
        self.ui.progressBar.setMaximum(total)
        self.ui.progressBar.setValue(current)
        self.ui.lblProgressMsg.setText(message)

    def _on_worker_log(self, message: str):
        self._log(message)

    def _on_finished(self, results, images):
        self._running = False
        self.ui.btnStart.setEnabled(True)
        self.ui.btnStop.setEnabled(False)
        self.ui.progressBar.setValue(self.ui.progressBar.maximum())
        self.ui.lblProgressMsg.setText(self.tr("✓ 处理完成"))

        total_rows = sum(len(v) for v in results.values())
        total_imgs = sum(len(v) for v in images.values())
        self._log(f"\n{'='*50}")
        self._log(f"✓ 全部完成! 共 {len(results)} 个工作表, {total_rows} 行数据")
        if total_imgs:
            self._log(f"  生成 {total_imgs} 张 3D 方向图")
        self._update_status()

        # 填充参数结果表
        self._populate_results_table(results)
        # 生成图形展示
        self._populate_charts(results)
        # 自动切到结果Tab (优先级4)
        self.ui.tabConfig.setCurrentIndex(0)  # 参数结果Tab

    def _populate_results_table(self, results):
        """填充参数结果表格。"""
        vtab = self.ui.vTabResults
        # 清除旧内容
        while vtab.count():
            item = vtab.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not results: return
        # 取第一个 sheet 的数据
        first_sheet = next(iter(results.values()))
        if not first_sheet: return
        # 收集所有参数列 (排除内部 error key)
        keys = sorted(k for k in first_sheet[0].keys() if not k.startswith('_'))
        # 可读列名映射
        KEY_LABELS = {
            "frequency":"Frequency (MHz)","gain":"Gain (dBi)","directivity":"Directivity (dBi)",
            "efficiency_pct":"Efficiency (%)","efficiency_db":"Efficiency (dB)",
            "trp":"TRP (dBm)","peak_eirp":"Peak EIRP (dBm)",
            "nhprp_45":"NHPRP ±45°","nhprp_30":"NHPRP ±30°","nhprp_225":"NHPRP ±22.5°",
            "uh_prp":"Upper Hem. PRP","lh_prp":"Lower Hem. PRP","prp_120":"PRP 0-120°",
            "max_power":"Max Power","min_power":"Min Power",
            "avg_gain":"Avg Gain (dB)","avg_power":"Avg Power (dBm)",
            "boresight_theta":"Boresight θ°","boresight_phi":"Boresight φ°",
        }

        table = QTableWidget()
        table.setColumnCount(len(keys))
        table.setHorizontalHeaderLabels([KEY_LABELS.get(k, k) for k in keys])
        table.setRowCount(len(first_sheet))
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.setMinimumHeight(300)

        for ri, row in enumerate(first_sheet):
            for ci, key in enumerate(keys):
                val = row.get(key, "")
                if isinstance(val, float):
                    item = QTableWidgetItem(f"{val:.4f}")
                else:
                    item = QTableWidgetItem(str(val) if val is not None else "")
                table.setItem(ri, ci, item)

        vtab.addWidget(table)
        self._log(self.tr(f"📊 参数表格已更新: {len(keys)} 列 × {len(first_sheet)} 行"))

    def _populate_charts(self, results):
        """在图形展示 Tab 动态渲染图表：B 类曲线 + A/C 类已生成图像。"""
        vtab = self.ui.vTabCharts
        while vtab.count():
            item = vtab.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not results: return

        import matplotlib
        matplotlib.use('QtAgg')
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure

        # 收集所有 results 中的图像
        all_images = {}  # freq_mhz -> {img_key: BytesIO}
        for sn, rows in results.items():
            if not rows: continue
            for r in rows:
                freq = r.get("frequency", 0)
                imgs = r.get("_images", {})
                if imgs:
                    all_images[freq] = imgs

        # ── B 类: 频点曲线（Matplotlib 动态绘制） ──
        for sn, rows in results.items():
            if not rows: continue
            if len(rows) < 2: continue
            freqs = [r.get("frequency", 0) for r in rows]

            # Efficiency vs Freq
            if "efficiency_pct" in rows[0]:
                eff_vals = [r.get("efficiency_pct", 0) or 0 for r in rows]
                self._add_result_chart(vtab, f"{sn}: Efficiency vs Freq",
                    freqs, eff_vals, "Frequency (MHz)", "Efficiency (%)", 'g')

            # Peak Gain vs Freq
            if "gain" in rows[0]:
                gain_vals = [r.get("gain", 0) or 0 for r in rows]
                self._add_result_chart(vtab, f"{sn}: Peak Gain vs Freq",
                    freqs, gain_vals, "Frequency (MHz)", "Gain (dBi)", 'b')

            # TRP vs Freq
            if "trp" in rows[0]:
                trp_vals = [r.get("trp", -999) or -999 for r in rows]
                self._add_result_chart(vtab, f"{sn}: TRP vs Freq",
                    freqs, trp_vals, "Frequency (MHz)", "TRP (dBm)", 'r')

            # Directivity vs Freq
            if "directivity" in rows[0]:
                dir_vals = [r.get("directivity", 0) or 0 for r in rows]
                self._add_result_chart(vtab, f"{sn}: Directivity vs Freq",
                    freqs, dir_vals, "Frequency (MHz)", "Directivity (dBi)", 'm')

            break  # 只展示第一个 sheet 的 B 类曲线

        # ── A/C 类: 逐频点图像（显示第一个频点的图） ──
        if all_images:
            # 频点选择控件
            freq_list = sorted(all_images.keys())
            freq_row = QHBoxLayout()
            freq_row.addWidget(QLabel(self.tr("频点:")))
            freq_combo = QComboBox()
            for f in freq_list:
                freq_combo.addItem(f"{f:.1f} MHz", f)
            freq_row.addWidget(freq_combo)
            freq_row.addStretch()
            vtab.addLayout(freq_row)

            # 图像展示容器
            img_container = QWidget()
            img_layout = QVBoxLayout(img_container)
            vtab.addWidget(img_container, 1)

            def _show_images_for_freq(freq_mhz):
                # 清除旧图
                while img_layout.count():
                    child = img_layout.takeAt(0)
                    if child.widget(): child.widget().deleteLater()

                imgs = all_images.get(freq_mhz, {})
                if not imgs:
                    lbl = QLabel(self.tr("此频点无图形"))
                    img_layout.addWidget(lbl)
                    return

                # 每个图用 matplotlib 渲染到 canvas
                for img_key in sorted(imgs.keys()):
                    buf = imgs[img_key]
                    buf.seek(0)
                    # 将 PNG buffer 显示为 QLabel pixmap
                    from PySide6.QtGui import QPixmap
                    from PySide6.QtCore import QByteArray
                    pixmap = QPixmap()
                    pixmap.loadFromData(buf.read())
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(450, 350,
                            Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        lbl = QLabel()
                        lbl.setPixmap(scaled)
                        lbl.setAlignment(Qt.AlignCenter)
                        img_layout.addWidget(lbl)
                    buf.seek(0)

            freq_combo.currentIndexChanged.connect(
                lambda idx: _show_images_for_freq(freq_combo.itemData(idx)))
            if freq_list:
                _show_images_for_freq(freq_list[0])
        else:
            vtab.addWidget(QLabel(self.tr("（未生成图形 — 请在图形配置中启用）")))

    def _add_result_chart(self, parent_layout, title, x, y, xlabel, ylabel, color):
        """添加一个 matplotlib 图表到布局。"""
        import matplotlib
        matplotlib.use('QtAgg')
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure

        fig = Figure(figsize=(8, 4), dpi=100)
        ax = fig.add_subplot(111)
        ax.plot(x, y, f'{color}-', linewidth=1.5)
        ax.set_title(title);
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
        if ylabel == "Gain (dB)": ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))

        canvas = FigureCanvas(fig)
        canvas.setMinimumHeight(250)
        parent_layout.addWidget(canvas)

    def _on_error(self, message: str):
        self._running = False
        self.ui.btnStart.setEnabled(True)
        self.ui.btnStop.setEnabled(False)
        self._log(f"✗ 错误: {message}")
        QMessageBox.critical(self, self.tr("处理错误"), message)

    # ==================================================================
    # 主题切换
    # ==================================================================

    def _on_theme_changed(self, index: int):
        """切换 Material Design 主题。"""
        if index < 0:
            return
        theme_id = self.ui.cmbThemeSelector.itemData(index)
        if theme_id and theme_id != ThemeManager.current_theme():
            ThemeManager.apply(theme_id)
            ThemeManager.save_theme(theme_id)

    # ==================================================================
    # 语言切换
    # ==================================================================

    def _on_toggle_language(self):
        new_lang = "en_US" if I18nManager.current_language() == "zh_CN" else "zh_CN"
        I18nManager.switch(self.app, new_lang)
        self._update_lang_button()

    def _update_lang_button(self):
        if I18nManager.current_language() == "zh_CN":
            self.ui.btnLangToggle.setText("EN")
        else:
            self.ui.btnLangToggle.setText("中")

    def changeEvent(self, event: QEvent):
        """语言切换事件 → 刷新所有 UI 文字。"""
        if event.type() == QEvent.LanguageChange:
            self.ui.retranslateUi(self)
            self._update_lag_display()
            self._update_status()
        super().changeEvent(event)

    # ==================================================================
    # 辅助
    # ==================================================================

    def _log(self, message: str):
        """追加日志行。"""
        ts = datetime.now().strftime("%H:%M:%S")
        self.ui.logOutput.appendPlainText(f"[{ts}] {message}")
        # 自动滚动到底部
        cursor = self.ui.logOutput.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.ui.logOutput.setTextCursor(cursor)

    def _update_status(self):
        """更新状态栏。"""
        singles = len(self._lag_config.singles_sorted)
        ranges = len(self._lag_config.ranges_sorted)
        self.ui.statusBar.showMessage(
            self.tr(f"LAG: {singles} 单角度 + {ranges} 范围 | 就绪")
        )

    # ==================================================================
    # 拖拽文件 (优先级2)
    # ==================================================================

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            valid = any(Path(u.toLocalFile()).suffix.lower() in ('.csv','.xlsx','.xls')
                       for u in event.mimeData().urls())
            if valid: event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        valid = [p for p in paths if Path(p).suffix.lower() in ('.csv','.xlsx','.xls')]
        if valid:
            existing = set(self._data_file_paths)
            new = [p for p in valid if p not in existing]
            if new:
                self._data_file_paths.extend(new)
                self._refresh_data_file_ui()
                self._log(f"📂 拖拽添加 {len(new)} 个文件")
                if self.ui.editTemplatePath.text().strip():
                    self._on_auto_match()

    # ==================================================================
    # 窗口关闭
    # ==================================================================

    def closeEvent(self, event):
        """窗口关闭时停止线程 + 保存位置。"""
        self._settings.setValue("window_geometry", self.saveGeometry())
        if self._thread and self._thread.isRunning():
            if self._worker:
                self._worker.cancel()
            self._thread.quit()
            if not self._thread.wait(5000):
                self._thread.terminate()
                self._thread.wait()
        self._running = False
        event.accept()
