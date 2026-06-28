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
from typing import TYPE_CHECKING, Dict, List, Optional

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
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QVBoxLayout,
    QWidget,
)

from src.file_entry import FileEntry, mode_name, infer_mode_from_sheet
from src.lag_config import LagConfig, PRESET_AUTOMOTIVE
from src.scale_manager import ScaleManager, AdaptiveWidgetMixin
from ui.compiled.ui_main_window import Ui_MainWindow
from ui.pages import FileSettingsPage, AntennaParamsPage, ChartSettingsPage

if TYPE_CHECKING:
    from src.worker import ProcessingWorker


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class MainWindow(AdaptiveWidgetMixin, QMainWindow):
    """天线参数后处理工具主窗口。"""

    # 快捷按钮角度映射（_sync_quick_buttons 使用）
    _QUICK_ANGLES: dict = {
        0.0: "btnQuick0",
        10.0: "btnQuick10",
        20.0: "btnQuick20",
        30.0: "btnQuick30",
        40.0: "btnQuick40",
        50.0: "btnQuick50",
        60.0: "btnQuick60",
        70.0: "btnQuick70",
        80.0: "btnQuick80",
        90.0: "btnQuick90",
    }

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        # 全分辨率自适应引擎
        self.init_scale_manager(base_width=1920)
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
        self._data_stale = True  # 数据是否为上次计算遗留 (用于自动清除)
        # 使用统一配置管理器 (antenna_config.json)
        from src.config_manager import get_config_manager
        self._cfg = get_config_manager()

        # 恢复窗口大小/位置 (优先级3)
        from PySide6.QtCore import QByteArray
        geo_str = self._cfg.config.window_geometry
        if geo_str:
            geo = QByteArray.fromBase64(bytes(geo_str, 'utf-8'))
            self.restoreGeometry(geo)
        self._data_file_paths: List[str] = []
        self._file_entries: List[FileEntry] = []  # Phase 1: FileEntry 并行列表
        self._data_file_widget: Optional[QWidget] = None
        self._file_list_widget: Optional[QTableWidget] = None
        self._match_table: Optional[QTableWidget] = None
        self._lbl_match_status: Optional[QLabel] = None
        self._lbl_naming_mode: Optional[QLabel] = None
        self._cmb_naming_mode: Optional[QComboBox] = None
        self._required_params: set = set()   # 用户确认的报告必需参数
        self._extra_params: set = set()      # 用户额外选择的计算参数
        self._test_mode: int = 0             # 0=passive, 1=TRP, 2=TIS
        self._worksheet_naming_mode: int = 0  # 0=保留原模板工作表名, 1=用数据源名命名
        self._mode_states = [{}, {}, {}]     # 三种测试模式独立参数状态
        self._ar_lag_config = LagConfig()    # AR 独立角度配置
        self._nh_custom_angles: List[float] = []  # NHPRP/NHPIS 自定义角度列表
        self._ar_output_db: bool = True     # AR 默认输出 dB
        self._chart_config_required = None   # ChartConfig: 报告需要
        self._chart_config_extra = None      # ChartConfig: 额外(full_report)
        self._graph_viewer = None            # GraphViewer: 启动时创建，处理完后填充数据
        self._cached_template_path: Optional[str] = None  # 模板路径缓存
        self._cached_template_mtime: float = 0           # 模板文件 mtime 缓存
        self._cached_template_params: set = set()        # 模板参数缓存

        # ---- 初始化 ----
        # 主题/语言已移至系统设置对话框
        self._custom_qss = self._make_custom_qss()
        self._init_file_paths()
        self._init_multi_file_ui()
        self._init_quick_angle_buttons()
        self._init_params_tab()
        self._build_parameter_tab()   # Master-Detail 布局 + 共享执行栏
        # 执行栏默认可见（处理设置标签）
        self.ui.tabConfig.currentChanged.connect(self._on_config_tab_changed)
        self._connect_signals()
        self._update_lag_display()
        self._init_menu()
        self._hide_settings_tabs()
        # 基础 QSS = 主题(已去字号) + 自定义样式; ScaleManager 动态叠加
        self._theme_qss = self.app.styleSheet()
        self.set_base_qss(self._theme_qss + self._custom_qss)
        # setStyleSheet 会重置子控件的 minimumWidth → 重新应用
        self._apply_minimum_sizes()
        self._log("天线参数后处理工具已启动")
        self._log_current_params()

    # ==================================================================
    # 初始化
    # ==================================================================

    def _init_quick_angle_buttons(self):
        """为编译 UI 中缺失的快捷角度按钮动态创建并插入布局。"""
        layout = self.ui.hQuickSingle
        # 已存在: 0, 30, 60, 70, 80, 90
        # 需添加: 10, 20, 40, 50
        existing = {"btnQuick0", "btnQuick30", "btnQuick60", "btnQuick70", "btnQuick80", "btnQuick90"}
        # 找到插入位置 (0 和 30 之间, 30 和 60 之间, etc.)
        insert_map = {
            "btnQuick10": ("btnQuick0", 10),
            "btnQuick20": ("btnQuick10", 20),
            "btnQuick40": ("btnQuick30", 40),
            "btnQuick50": ("btnQuick40", 50),
        }
        for attr_name, (after_attr, angle) in insert_map.items():
            if hasattr(self.ui, attr_name):
                continue  # already exists
            btn = QPushButton(f"{angle}°")
            btn.setObjectName(attr_name)
            btn.setCheckable(True)
            setattr(self.ui, attr_name, btn)
            # 找到 after_attr 按钮的索引，在其后插入
            after_btn = getattr(self.ui, after_attr)
            idx = layout.indexOf(after_btn)
            if idx >= 0:
                layout.insertWidget(idx + 1, btn)
            else:
                layout.addWidget(btn)

    def _init_file_paths(self):
        """从配置管理器恢复上次路径 + 字体大小 + 初始化模板管理 UI。"""
        from src.template_manager import TemplateManager

        self._tm = TemplateManager()

        # 恢复上次字体大小 — 从配置管理器
        cfg = self._cfg.config
        saved_font_size = cfg.font_size
        if saved_font_size:
            ScaleManager._font_scale = int(saved_font_size) / ScaleManager.BASE_FONT_SIZE

        template_path = cfg.last_template_path
        output_dir = cfg.last_output_dir

        # 始终恢复上次模板路径（即使文件暂时不存在，保留引用）
        if template_path:
            self.ui.editTemplatePath.setText(template_path)
        # 恢复输出目录，无保存值时自动设为数据源目录（后续 _on_add_data_files 触发更新）
        if output_dir and Path(output_dir).exists():
            self.ui.editOutputDir.setText(output_dir)
        elif self._data_file_paths:
            self.ui.editOutputDir.setText(str(Path(self._data_file_paths[0]).parent))
        else:
            self.ui.editOutputDir.setText(str(Path.cwd() / "output"))

        # 输出文件名: 优先模板名+日期+序号
        if template_path:
            tpl_name = Path(template_path).stem
            from src.template_manager import TemplateManager as TM
            out_dir = self.ui.editOutputDir.text() or str(Path.cwd() / "output")
            fname = TM.next_available_filename(out_dir, tpl_name)
            self.ui.editOutputName.setText(fname)
        else:
            self.ui.editOutputName.setText("antenna_report.xlsx")

        # 模板预设管理已移至「文件→系统设置」对话框


    def _apply_minimum_sizes(self):
        """设置关键输入框的最小宽度 — setStyleSheet 后会重置,需独立调用。"""
        self.ui.editOutputDir.setMinimumWidth(200)
        self.ui.editOutputName.setMinimumWidth(200)
        self.ui.editFullReportPath.setMinimumWidth(200)

    def _init_multi_file_ui(self):
        """构建多文件选择 + 自动匹配 UI（动态插入到 vTabFile）。"""
        # ---- 隐藏旧的单文件输入行（与多文件功能重复） ----
        self.ui.lblCsv.hide()
        self.ui.editCsvPath.hide()
        self.ui.btnBrowseCsv.hide()
        self.ui.groupInput.setTitle(self.tr("模板文件"))

        self._apply_minimum_sizes()

        self._data_file_widget = QWidget()
        layout = QVBoxLayout(self._data_file_widget)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        # 数据文件按钮行
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
        layout.addLayout(btn_row)

        # 文件列表 — 可滚动、自适应高度
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
        layout.addWidget(self._file_list_widget)

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
        layout.addWidget(self._match_table)

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
        # 工作表命名选项 — 紧跟在匹配按钮后面，stretch 之前
        self._lbl_naming_mode = QLabel(self.tr("工作表命名:"))
        match_row.addWidget(self._lbl_naming_mode)
        self._cmb_naming_mode = QComboBox()
        self._cmb_naming_mode.addItem(self.tr("保留原模板工作表名"), 0)
        self._cmb_naming_mode.addItem(self.tr("用数据源名替换"), 1)
        self._cmb_naming_mode.setToolTip(
            self.tr("多数据源时，选择工作表命名方式：保留原模板名称 或 用数据源文件名替换"))
        self._cmb_naming_mode.setFixedWidth(190)
        self._cmb_naming_mode.currentIndexChanged.connect(self._on_naming_mode_changed)
        match_row.addWidget(self._cmb_naming_mode)
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

        # ---- 图形展示 Tab: 启动时创建空 GraphViewer (工具栏立即可见) ----
        from ui.graph_viewer import GraphViewer
        self._graph_viewer = GraphViewer()
        self.ui.vTabCharts.addWidget(self._graph_viewer)

    def _init_params_tab(self):
        """构建「天线参数」子节 — 频点 + 算法选项，加入 tabFile。"""
        vtab = self.ui.vTabFile  # 放入文件设置区域

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

    # ═══════════════════════════════════════════════════════════════
    # Step 3: Master-Detail 布局
    # ═══════════════════════════════════════════════════════════════

    def _build_parameter_tab(self):
        """构建 Master-Detail 布局 + 提取共享执行栏到 rootVBox。"""
        from PySide6.QtWidgets import QListWidgetItem, QStackedWidget, QSizePolicy as SP

        # 1. 提取执行栏（移除 hProgress/hButtons/logOutput 到 rootVBox）
        self._extract_execution_bar()

        # 2. 隐藏 vTabFile 剩余旧内容，移出布局但不销毁 widget 对象
        for _ in range(self.ui.vTabFile.count()):
            item = self.ui.vTabFile.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.hide()

        # 3. 构建 Master-Detail 布局
        container = QWidget()
        h_layout = QHBoxLayout(container)
        h_layout.setSpacing(8)
        h_layout.setContentsMargins(0, 0, 0, 0)

        # 左侧导航
        self._nav_list = QListWidget()
        self._nav_list.setFixedWidth(140)
        self._nav_list.setSpacing(2)
        self._nav_list.setStyleSheet("QListWidget::item { padding: 8px 4px; }")
        h_layout.addWidget(self._nav_list)

        # 右侧页面栈
        self._page_stack = QStackedWidget()
        h_layout.addWidget(self._page_stack, 1)

        # 创建 3 个页面
        self._file_settings_page = FileSettingsPage(self)
        self._antenna_params_page = AntennaParamsPage(self)
        self._chart_settings_page = ChartSettingsPage(self)

        self._page_stack.addWidget(self._file_settings_page)    # 0
        self._page_stack.addWidget(self._antenna_params_page)   # 1
        self._page_stack.addWidget(self._chart_settings_page)   # 2

        # 导航项
        nav_items = [
            ("📂 " + self.tr("输入输出"), 0),
            ("📡 " + self.tr("天线参数"), 1),
            ("📊 " + self.tr("图表配置"), 2),
        ]
        for label, idx in nav_items:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, idx)
            self._nav_list.addItem(item)

        self._nav_list.currentRowChanged.connect(self._on_nav_changed)
        self._nav_list.setCurrentRow(0)

        # 添加到 tabFile
        self.ui.vTabFile.addWidget(container)

    def _extract_execution_bar(self):
        """将执行栏从 tabFile 移动到 rootVBox（跨标签页共享）。"""
        vtab = self.ui.vTabFile

        # 找到并移除执行栏相关布局项
        for i in reversed(range(vtab.count())):
            item = vtab.itemAt(i)
            if item is None:
                continue
            lyt = item.layout()
            w = item.widget()
            if lyt is self.ui.hProgress or lyt is self.ui.hButtons:
                vtab.removeItem(vtab.takeAt(i))
            elif w is self.ui.logOutput:
                vtab.removeItem(vtab.takeAt(i))

        # 创建执行栏容器
        exec_bar = QWidget()
        exec_layout = QVBoxLayout(exec_bar)
        exec_layout.setContentsMargins(0, 0, 0, 0)
        exec_layout.setSpacing(4)

        # 进度行
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.ui.progressBar)
        progress_row.addWidget(self.ui.lblProgressMsg)
        exec_layout.addLayout(progress_row)

        # 日志
        self.ui.logOutput.setParent(exec_bar)
        exec_layout.addWidget(self.ui.logOutput)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.ui.btnStart)
        btn_row.addWidget(self.ui.btnStop)
        exec_layout.addLayout(btn_row)

        # 插入到 rootVBox（tabConfig 下方）
        self.ui.rootVBox.insertWidget(
            self.ui.rootVBox.indexOf(self.ui.tabConfig) + 1, exec_bar
        )
        self._execution_bar = exec_bar

    def _on_nav_changed(self, row: int):
        """导航列表切换 → 切换页面栈。"""
        if hasattr(self, '_page_stack') and 0 <= row < self._page_stack.count():
            self._page_stack.setCurrentIndex(row)

    def _on_config_tab_changed(self, index: int):
        """切换标签页时显示/隐藏执行栏（仅 tab[0] 处理设置显示）。"""
        if hasattr(self, '_execution_bar'):
            self._execution_bar.setVisible(index == 0)

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

        # ── 文件 ──
        fm = menubar.addMenu(self.tr("&文件"))
        fm.addAction(self.tr("新建窗口"), self._on_new_window, QKeySequence("Ctrl+N"))
        fm.addSeparator()
        fm.addAction(self.tr("系统设置..."), self._show_system_settings)
        fm.addSeparator()
        fm.addAction(self.tr("保存结果..."), self._on_browse_output, QKeySequence("Ctrl+S"))
        fm.addSeparator()
        fm.addAction(self.tr("关闭窗口"), self.close, QKeySequence("Ctrl+W"))

        # ── 窗口 ──
        self._menu_window = menubar.addMenu(self.tr("&窗口"))
        self._menu_window.addAction(self.tr("新建窗口"), self._on_new_window)
        self._menu_window.addSeparator()
        # 窗口列表由 WindowManager 动态填充

        # ── 工具 ──
        tm = menubar.addMenu(self.tr("&工具"))
        tm.addAction(self.tr("数据检查与转换..."), self._on_tool_batch_check)
        tm.addAction(self.tr("路径损耗补偿..."), self._on_tool_calibrate)
        tm.addAction(self.tr("数据合并 (多段拼接)..."), self._on_tool_merge)
        tm.addAction(self.tr("步进重采样..."), self._on_tool_resample)
        tm.addSeparator()
        tm.addAction(self.tr("数据修复 (插值)"), self._on_tool_quality_repair)
        tm.addSeparator()
        tm.addAction(self.tr("模板预设管理..."), self._on_tool_template_recognizer)
        tm.addAction(self.tr("校准预设管理..."), self._on_show_rsp_presets)
        tm.addAction(self.tr("EMQuest 数据导出..."), self._on_tool_emq_export)

        # ── 帮助 ──
        hm = menubar.addMenu(self.tr("&帮助"))
        hm.addAction(self.tr("使用说明"), self._on_help, QKeySequence("F1"))
        hm.addAction(self.tr("许可管理..."), self._on_license)
        hm.addAction(self.tr("关于..."), self._on_about)

        # 注册到 WindowManager
        from ui.window_manager import WindowManager
        WindowManager.instance().register(self)

    def _hide_settings_tabs(self):
        """重组标签页：移除废弃标签，重命名保留标签。

        Tab 最终顺序：
          0 - 📐 处理设置 (Master-Detail: 文件/天线参数/图表配置)
          1 - 📊 计算结果 (原 tabResults)
          2 - 📈 图表查看 (原 tabCharts)
        tabLag/tabPlot/tabCalc 被移除（控件对象保持存活，Step 5 清扫）。

        注意: _make_tab_scrollable 会替换 QTabWidget 中的页 widget
        （将 QWidget 包裹进 QScrollArea），导致 indexOf(widget) 失效，
        因此按固定索引而非 widget 引用来移除。
        """
        tc = self.ui.tabConfig
        # 固定索引: tabFile(0), tabLag(1), tabPlot(2), tabCalc(3), tabResults(4), tabCharts(5)
        # 倒序移除 tabLag(1), tabPlot(2), tabCalc(3) — 倒序防止索引漂移
        for idx in reversed([1, 2, 3]):
            tc.removeTab(idx)

        # 重命名保留的三个标签 (0=tabFile, 1=tabResults, 2=tabCharts)
        tc.setTabText(0, self.tr("📐 处理设置"))
        tc.setTabText(1, self.tr("📊 计算结果"))
        tc.setTabText(2, self.tr("📈 图表查看"))

    def _show_system_settings(self):
        from ui.dialogs import SystemSettingsDialog
        SystemSettingsDialog(self).exec()

    def _get_template_params(self) -> set:
        """读取模板，提取所有 Sheet 的列类型集合（结果缓存，仅路径变化时重读）。"""
        tp = self.ui.editTemplatePath.text().strip()
        if not tp or not Path(tp).exists():
            self._cached_template_path = None
            self._cached_template_params = set()
            return set()
        # 缓存命中: 路径相同且文件未修改
        mtime = Path(tp).stat().st_mtime
        if getattr(self, '_cached_template_path', None) == tp and \
           getattr(self, '_cached_template_mtime', 0) == mtime:
            return self._cached_template_params
        # 大文件检测 — 模板通常 <1MB, >10MB 可能是源数据文件
        size_mb = Path(tp).stat().st_size / (1024 * 1024)
        if size_mb > 10:
            reply = QMessageBox.question(
                self, self.tr("模板文件异常"),
                self.tr(f"选择的模板文件大小为 {size_mb:.0f} MB，\n"
                        "通常模板文件不超过 1 MB。\n\n"
                        "可能误选了源数据文件（如 RawData / FinalSummary），\n"
                        "继续解析可能需要较长时间。\n\n"
                        "是否仍然使用此文件作为模板？"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                self._cached_template_params = set()
                return set()
        try:
            from src.excel_reader import read_template
            sheets = read_template(tp)
            params = set()
            for si in sheets:
                for c in si.columns:
                    params.add(c.col_type)
            result = params - {"unknown", "frequency"}
            self._cached_template_path = tp
            self._cached_template_mtime = mtime
            self._cached_template_params = result
            return result
        except Exception:
            return set()

    def window_title(self) -> str:
        """返回窗口标题，用于窗口菜单列表。"""
        if self._data_file_paths:
            import os
            names = [os.path.splitext(os.path.basename(p))[0] for p in self._data_file_paths]
            return ", ".join(names[:2]) + ("..." if len(names) > 2 else "")
        return self.tr("未命名窗口")

    def _update_window_title(self):
        """更新窗口标题和窗口菜单。"""
        title = self.window_title()
        self.setWindowTitle(title)
        # 同步窗口菜单
        from ui.window_manager import WindowManager
        WindowManager.instance()._update_all_window_menus()

    def _on_new_window(self):
        """创建新的工作窗口。"""
        from ui.window_manager import WindowManager
        WindowManager.instance().create_window(self.app)

    def _on_help(self):
        from ui.dialogs import HelpDialog
        dlg = HelpDialog(self)
        dlg.exec()

    def _on_tool_batch_check(self):
        from ui.dialogs import BatchCalibrateDialog
        BatchCalibrateDialog(self).exec()

    def _on_tool_calibrate(self):
        from ui.dialogs import PathLossDialog
        PathLossDialog(self).exec()

    def _on_tool_merge(self):
        from ui.dialogs import MergeDialog
        MergeDialog(self).exec()

    def _on_tool_quality_repair(self):
        from ui.dialogs import RepairDialog
        RepairDialog(self).exec()

    def _on_tool_resample(self):
        from ui.dialogs import ResampleDialog
        ResampleDialog(self).exec()

    def _on_tool_template_recognizer(self):
        """模板预设管理: 加载模板 Excel，显示列头检测，支持手动修正并保存。"""
        from ui.template_recognizer import TemplateRecognizerDialog
        TemplateRecognizerDialog(self).exec()

    def _on_show_rsp_presets(self):
        """校准预设管理: 打开 RSP 预设管理对话框。"""
        from ui.rsp_picker_dialog import RspPickerDialog
        dlg = RspPickerDialog(self)
        dlg.exec()

    def _on_tool_emq_export(self):
        """EMQuest 数据导出: 将 .raw 文件通过 EMQuest CLI 导出为 CSV/Excel/JSON。"""
        # Step 1: 选择文件或文件夹
        from PySide6.QtWidgets import QButtonGroup, QRadioButton, QDialog, QVBoxLayout, \
            QHBoxLayout, QPushButton, QComboBox, QLabel, QLineEdit, QFileDialog as FD, QGroupBox

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("EMQuest 数据导出"))
        dlg.setMinimumWidth(500)
        layout = QVBoxLayout(dlg)

        # --- 导出格式选择 ---
        fmt_group = QGroupBox(self.tr("导出格式"))
        fmt_layout = QHBoxLayout(fmt_group)
        fmt_combo = QComboBox()
        fmt_combo.addItems(["CSV (数据)", "Excel (数据)", "JSON (数据+参数)"])
        fmt_combo.setCurrentIndex(0)
        fmt_layout.addWidget(QLabel(self.tr("格式:")))
        fmt_layout.addWidget(fmt_combo)
        fmt_layout.addStretch()
        layout.addWidget(fmt_group)

        # --- 文件选择 ---
        file_group = QGroupBox(self.tr("源文件"))
        file_layout = QVBoxLayout(file_group)
        h1 = QHBoxLayout()
        file_radio = QRadioButton(self.tr("选择 .raw 文件"))
        folder_radio = QRadioButton(self.tr("选择文件夹 (递归扫描 .raw)"))
        file_radio.setChecked(True)
        h1.addWidget(file_radio)
        h1.addWidget(folder_radio)
        h1.addStretch()
        file_layout.addLayout(h1)
        h2 = QHBoxLayout()
        path_edit = QLineEdit()
        path_edit.setReadOnly(True)
        browse_btn = QPushButton(self.tr("浏览..."))
        h2.addWidget(path_edit)
        h2.addWidget(browse_btn)
        file_layout.addLayout(h2)
        layout.addWidget(file_group)

        # --- 输出目录 ---
        out_group = QGroupBox(self.tr("输出目录"))
        out_layout = QHBoxLayout(out_group)
        out_edit = QLineEdit()
        out_edit.setReadOnly(True)
        out_browse = QPushButton(self.tr("浏览..."))
        out_layout.addWidget(QLabel(self.tr("输出到:")))
        out_layout.addWidget(out_edit)
        out_layout.addWidget(out_browse)
        layout.addWidget(out_group)

        # --- 状态标签 ---
        status_label = QLabel("")
        layout.addWidget(status_label)

        # --- 按钮 ---
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton(self.tr("开始导出"))
        cancel_btn = QPushButton(self.tr("取消"))
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        selected_paths = []

        def on_browse():
            nonlocal selected_paths
            if file_radio.isChecked():
                files, _ = FD.getOpenFileNames(dlg, self.tr("选择 .raw 文件"), "",
                    self.tr("Raw 文件 (*.raw);;所有文件 (*)"))
                if files:
                    selected_paths = list(files)
                    path_edit.setText(f"{len(files)} 个文件已选择")
                    if not out_edit.text():
                        out_edit.setText(str(Path(files[0]).parent))
            else:
                folder = FD.getExistingDirectory(dlg, self.tr("选择包含 .raw 文件的文件夹"))
                if folder:
                    from src.emquest_exporter import discover_raw_files
                    selected_paths = discover_raw_files(folder, recursive=True)
                    path_edit.setText(f"{folder} ({len(selected_paths)} 个 .raw)")
                    if not out_edit.text():
                        out_edit.setText(folder)

        def on_out_browse():
            folder = FD.getExistingDirectory(dlg, self.tr("选择输出目录"))
            if folder:
                out_edit.setText(folder)

        browse_btn.clicked.connect(on_browse)
        out_browse.clicked.connect(on_out_browse)

        def on_ok():
            if not selected_paths:
                status_label.setText("⚠ 请先选择 .raw 文件")
                return
            if not out_edit.text():
                status_label.setText("⚠ 请选择输出目录")
                return
            dlg.accept()

        ok_btn.clicked.connect(on_ok)
        cancel_btn.clicked.connect(dlg.reject)

        if dlg.exec() != QDialog.Accepted:
            return

        # 检查大文件
        large_files = []
        for fp in selected_paths:
            size_mb = os.path.getsize(fp) / (1024 * 1024)
            if size_mb > 100:
                large_files.append((Path(fp).name, size_mb))

        if large_files:
            warning = self.tr("检测到大文件 (EMQuest 为 32 位，内存上限约 4GB):\n\n")
            for name, size in large_files[:5]:
                warning += f"  • {name} ({size:.0f} MB)\n"
            if len(large_files) > 5:
                warning += f"  ... 共 {len(large_files)} 个大文件\n"
            warning += (f"\nCLI 模式下大文件可能因内存不足而导出失败。\n"
                        f"建议: 打开 EMQuest GUI → File → Export 手动导出大文件。\n\n"
                        f"是否仍要继续尝试 CLI 导出？")
            reply = QMessageBox.warning(self, self.tr("⚠ 大文件警告"), warning,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.No:
                # 仍然继续
                pass
            else:
                return

        # Step 2: 执行导出
        fmt_idx = fmt_combo.currentIndex()
        fmt_keys = ["csv", "excel", "json"]
        export_fmt = fmt_keys[fmt_idx]
        output_dir = out_edit.text()

        try:
            from src.emquest_exporter import export_raw_files
            self._enter_busy(self.tr("⏳ EMQuest 导出中..."))
            self._log(f"📦 EMQuest 导出: {len(selected_paths)} 个 .raw → {export_fmt.upper()}")
            self._log(f"  输出目录: {output_dir}")
            self._log(f"  EMQuest 后台运行 (-s silent mode)")
            self._log(f"  NI 弹窗自动处理: 已启用")

            result = export_raw_files(
                selected_paths, export_fmt, output_dir,
                progress_callback=lambda c, t, m: self._on_progress(c, t, m))

            ok = len(result["exported"])
            fail = len(result["failed"])
            self._log(f"✓ 导出完成: {ok} 成功, {fail} 失败")

            summary = f"EMQuest 导出完成:\n\n✅ 成功: {ok} 个\n❌ 失败: {fail} 个"
            if ok > 0:
                total_mb = sum(e["size_mb"] for e in result["exported"])
                summary += f"\n总大小: {total_mb:.1f} MB\n\n输出目录:\n{output_dir}"
            if fail > 0:
                summary += "\n\n失败详情:\n"
                for f in result["failed"]:
                    summary += f"  • {Path(f['source']).name}: {f['error']}\n"
            QMessageBox.information(self, self.tr("完成"), summary)
        except Exception as e:
            self._log(f"✗ 导出失败: {e}")
            QMessageBox.critical(self, self.tr("错误"), str(e))
        finally:
            self._exit_busy()

    def _on_license(self):
        from src.license import LicenseManager, get_machine_id
        mgr = LicenseManager()
        mgr.auto_load()
        mid = get_machine_id()
        info = mgr.license_info
        if info and mgr.is_valid:
            msg = (f"许可状态: {mgr.status_text}\n被许可方: {info.licensee}\n到期: {info.expiry}\n机器ID: {mid}")
        else:
            msg = (f"许可状态: 未找到有效许可\n\n将 license.json 放到程序目录\n机器ID: {mid}")
        QMessageBox.information(self, "许可管理", msg)

    def _on_about(self):
        QMessageBox.about(self, self.tr("关于"),
            self.tr("天线参数后处理工具 v2.0\n\n从 EMQuest 数据计算天线参数\nGitHub: freezzb1972/antenna-post-processor"))

    # ==================================================================
    # 多文件操作
    # ==================================================================

    def _on_add_data_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, self.tr("选择数据文件 (可多选)"),
            self._cfg.config.last_csv_paths[0] if self._cfg.config.last_csv_paths else "",
            self.tr("所有支持格式 (*.csv *.xlsx *.xls);;CSV 文件 (*.csv);;Excel 新版 (*.xlsx);;Excel 旧版 (*.xls);;所有文件 (*)")
        )
        if not paths:
            return
        # 自动清除上次计算遗留的陈旧数据 (即使 _data_file_paths 为空仍须清 UI)
        if self._data_stale:
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
        self._cfg.config.last_csv_paths = [new_paths[0]] if new_paths else []
        self._cfg._dirty = True
        self._refresh_data_file_ui()
        # 无预设模板时，输出目录自动设为数据源目录
        if not self.ui.editOutputDir.text().strip() or self.ui.editOutputDir.text() == str(Path.cwd() / "output"):
            self.ui.editOutputDir.setText(str(Path(new_paths[0]).parent))
        if self.ui.editTemplatePath.text().strip():
            self._on_auto_match()

    def _on_clear_selected_files(self):
        """清除选中数据行。"""
        rows = sorted({idx.row() for idx in self._file_list_widget.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, self.tr("提示"), self.tr("请先在文件列表中选中要清除的行。"))
            return
        for r in rows:
            if r < len(self._data_file_paths):
                del self._data_file_paths[r]
                if r < len(self._file_entries):
                    del self._file_entries[r]
        # 重建 UI (行索引已变)
        self._refresh_data_file_ui()
        if not self._data_file_paths:
            self._match_table.setRowCount(0)
            self._lbl_match_status.setText("")
            self._data_stale = True
        else:
            # 剩余文件 → 重建匹配表，移除已删除文件的旧条目
            self._data_stale = False
            template_path = self.ui.editTemplatePath.text().strip()
            if template_path and Path(template_path).exists():
                self._on_auto_match()
        self._log(f"🗑 已清除 {len(rows)} 行, 剩余 {len(self._data_file_paths)} 个文件")

    def _on_clear_all_files(self):
        self._data_file_paths.clear()
        self._file_entries.clear()
        self._file_list_widget.setRowCount(0)
        self._match_table.setRowCount(0)
        self._lbl_match_status.setText("")
        self._data_stale = True

    def _sync_file_entries(self):
        """同步 _file_entries 与 _data_file_paths，保留已设置的 test_mode。"""
        old_map = {e.path: e for e in self._file_entries}
        self._file_entries = []
        for p in self._data_file_paths:
            if p in old_map:
                self._file_entries.append(old_map[p])
            else:
                self._file_entries.append(FileEntry(path=p, test_mode=self._test_mode))

    def _refresh_data_file_ui(self):
        if self._file_list_widget is None:
            return
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
            # 测试模式下拉
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

    def _on_file_mode_changed(self, row: int):
        """文件行测试模式变更回调。"""
        combo = self._file_list_widget.cellWidget(row, 1)
        if combo and row < len(self._file_entries):
            self._file_entries[row].test_mode = combo.currentData()

    def _on_naming_mode_changed(self, index: int):
        """工作表命名方式变更回调。"""
        self._worksheet_naming_mode = self._cmb_naming_mode.currentData() or 0
        # 命名方式变了，重建匹配表
        if self._match_table.rowCount() > 0:
            self._on_auto_match()

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

        # 从模板自动更新 LAG 和 AR 角度配置
        self._auto_update_angle_config_from_template(sheets)

        matches = auto_match(sheet_names, self._data_file_paths)
        self._populate_match_table(matches)

        # 根据匹配的工作表名称自动推断文件测试模式
        for m in matches:
            if m.file_path:
                inferred = infer_mode_from_sheet(m.sheet_name)
                for e in self._file_entries:
                    if e.path == m.file_path and e.test_mode == 0:
                        e.test_mode = inferred
        self._refresh_data_file_ui()

        matched = sum(1 for m in matches if m.file_path is not None)
        self._lbl_match_status.setText(
            f"✓ {matched}/{len(matches)} 个工作表已匹配"
        )
        self._log(f"自动匹配完成: {matched}/{len(matches)}")

    def _populate_match_table(self, matches):
        from src.sheet_file_matcher import extract_key, sanitize_sheet_name
        use_file_names = self._worksheet_naming_mode == 1
        self._match_table.setRowCount(len(matches))
        for i, m in enumerate(matches):
            self._match_table.setRowHeight(i, 28)
            # 工作表名: mode=0 用模板原名, mode=1 用数据源文件名推导
            display_name = m.sheet_name
            if use_file_names and m.file_path:
                display_name = sanitize_sheet_name(extract_key(m.file_path))
            self._match_table.setItem(i, 0, QTableWidgetItem(display_name))
            combo = QComboBox()
            combo.addItem("—")
            for fp in self._data_file_paths:
                # 只显示文件名，完整路径放 tooltip
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

    def _build_datasource_map(self, progress_callback=None):
        from src.datasource import DataSource
        from src.sheet_file_matcher import extract_key, sanitize_sheet_name
        result = {}

        total_files = max(len(self._data_file_paths), 1)
        file_idx = 0
        use_file_names = self._worksheet_naming_mode == 1

        # 防御: 清除不在 _data_file_paths 中的匹配表行 (陈旧数据保护)
        valid_paths = set(self._data_file_paths)
        for row in range(self._match_table.rowCount()):
            combo = self._match_table.cellWidget(row, 1)
            if combo:
                fp = combo.currentData() or ""
                if fp and fp != "—" and fp not in valid_paths:
                    # 此匹配表行引用了不存在于 _data_file_paths 的旧文件 → 重置
                    combo.setCurrentIndex(0)

        # 已匹配的行
        matched_files = set()
        for row in range(self._match_table.rowCount()):
            template_sheet_name = self._match_table.item(row, 0).text()
            combo = self._match_table.cellWidget(row, 1)
            fp = combo.currentData() or "" if combo else ""
            if fp and Path(fp).exists():
                if progress_callback:
                    file_idx += 1
                    progress_callback(file_idx, total_files,
                                     f"Loading {Path(fp).name}...")
                try:
                    if use_file_names:
                        # 用数据源文件名推导工作表名，并清理为合法 Excel 名
                        key = sanitize_sheet_name(extract_key(fp))
                        result[key] = DataSource.from_path(fp)
                    else:
                        result[sanitize_sheet_name(template_sheet_name)] = DataSource.from_path(fp)
                    matched_files.add(fp)
                except Exception as e:
                    self._log(f"⚠ {template_sheet_name} 数据源加载失败: {e}")

        # 未匹配的剩余数据文件：自动按命名推导工作表名
        unmatched = [f for f in self._data_file_paths if f not in matched_files]
        if unmatched:
            for fp in unmatched:
                sheet_name = sanitize_sheet_name(extract_key(fp))
                if progress_callback:
                    file_idx += 1
                    progress_callback(file_idx, total_files,
                                     f"Loading {Path(fp).name}...")
                try:
                    result[sheet_name] = DataSource.from_path(fp)
                    self._log(f"  ↗ 自动添加: {sheet_name} ← {Path(fp).name}")
                except Exception as e:
                    self._log(f"⚠ {Path(fp).name} 加载失败: {e}")

        return result

    @staticmethod
    def _auto_rename_if_exists(filepath: str) -> str:
        """如果文件已存在，自动添加 _YYYYMMDD_NN 后缀避免覆盖。"""
        p = Path(filepath)
        if not p.exists():
            return filepath
        from datetime import date
        today = date.today().strftime("%Y%m%d")
        stem = p.stem
        ext = p.suffix
        parent = p.parent
        seq = 1
        while True:
            new_name = f"{stem}_{today}_{seq:02d}{ext}"
            new_path = parent / new_name
            if not new_path.exists():
                return str(new_path)
            seq += 1

    def _derive_new_sheet_name(self, reference_name: str, target_key: str) -> str:
        """从参考工作表名推导新工作表名: "5G1"+"G2" → "5G2" """
        import re
        m = re.search(r'G\d+', reference_name, re.IGNORECASE)
        tk = re.search(r'G\d+', target_key, re.IGNORECASE)
        if m and tk:
            return reference_name[:m.start()] + tk.group(0).upper() + reference_name[m.end():]
        return target_key

    def _retry_unmatched_files(self):
        """LLM 辅助: 自动匹配后仍有未匹配文件时尝试 LLM 建议。"""
        if self._match_table.rowCount() == 0:
            return
        matched_files = set()
        for row in range(self._match_table.rowCount()):
            combo = self._match_table.cellWidget(row, 1)
            fp = combo.currentData() or "" if combo else ""
            if fp and Path(fp).exists():
                matched_files.add(fp)
        unmatched = [f for f in self._data_file_paths if f not in matched_files]
        if not unmatched:
            return
        try:
            from src.llm_assist import LLMAssist
            sheet_names = []
            for row in range(self._match_table.rowCount()):
                item = self._match_table.item(row, 0)
                if item:
                    sheet_names.append(item.text())
            suggestions = LLMAssist.suggest_file_matches(
                sheet_names, self._data_file_paths,
                current_matches=None, logger=self._log,
            )
            if suggestions:
                for sn, fp in suggestions.items():
                    self._log(f"🤖 LLM 建议: {sn} ← {Path(fp).name}")
        except Exception as e:
            self._log(f"LLM 匹配建议失败: {e}")

    def _build_sheet_mode_map(self, datasource_map: dict) -> dict:
        """委托到 FileSettingsPage.build_sheet_mode_map。"""
        return self._file_settings_page.build_sheet_mode_map(datasource_map)



    @staticmethod
    def _make_custom_qss() -> str:
        """生成自定义 QSS（不立即应用, 由 set_base_qss 统一处理）。"""
        return """
        QGroupBox {
            border: 1px solid rgba(128,128,128,50);
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 14px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        QPlainTextEdit {
            border-radius: 4px;
            font-family: "Consolas","Courier New",monospace;
        }
        QPushButton#btnStart { font-weight: bold; letter-spacing: 1px; }
        QPushButton#btnStop { font-weight: bold; }
        """

    def _connect_signals(self):
        """连接所有信号/槽。"""
        # 文件浏览
        self.ui.btnBrowseTemplate.clicked.connect(self._on_browse_template)
        self.ui.btnBrowseOutput.clicked.connect(self._on_browse_output)
        self.ui.btnBrowseFullReport.clicked.connect(self._on_browse_full_report)

        # 运行
        self.ui.btnStart.clicked.connect(self._on_start)
        self.ui.btnStop.clicked.connect(self._on_stop)

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
            self, self.tr("选择模板文件"),
            self._cfg.config.last_template_path or "",
            self.tr("所有支持格式 (*.xlsx *.xls *.csv *.docx);;Excel 新版 (*.xlsx);;Excel 旧版 (*.xls);;CSV (*.csv);;Word (*.docx);;所有文件 (*)")
        )
        if path:
            self.ui.editTemplatePath.setText(path)
            self._cfg.config.last_template_path = path
            self._cfg._dirty = True
            self._chart_config_required = None  # 模板已变，下次使用时重新检测
            self._cached_template_params = set()  # 强制刷新模板参数缓存
            # 自动应用模板检测到的计算参数
            self._auto_apply_template_params()
            # 模板路径变更后，旧的匹配表基于旧模板的工作表名，无效
            if self._match_table is not None:
                self._match_table.setRowCount(0)
            if hasattr(self, '_lbl_match_status') and self._lbl_match_status is not None:
                self._lbl_match_status.setText("")
            # 若已有数据文件，立即重建匹配表
            if self._data_file_paths:
                self._on_auto_match()

    def _on_browse_output(self):
        start_dir = self.ui.editOutputDir.text() or str(Path.cwd() / "output")
        path = QFileDialog.getExistingDirectory(
            self, self.tr("选择输出目录"), start_dir
        )
        if path:
            self.ui.editOutputDir.setText(path)
            self._cfg.config.last_output_dir = path
            self._cfg._dirty = True

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
    # 模板预设管理
    # ==================================================================

    def apply_template_preset(self, path: str, output_dir: str = "", tpl_name: str = ""):
        """应用模板预设: 设置模板路径 + 输出目录 + 文件名。"""
        self.ui.editTemplatePath.setText(path)
        self._save_template_path(path)
        if output_dir:
            self.ui.editOutputDir.setText(output_dir)
        elif self._data_file_paths:
            self.ui.editOutputDir.setText(str(Path(self._data_file_paths[0]).parent))
        if tpl_name:
            out_dir = self.ui.editOutputDir.text() or "."
            fname = self._tm.next_available_filename(out_dir, tpl_name)
            self.ui.editOutputName.setText(fname)
        # 模板变更后自动识别并应用计算参数
        self._cached_template_params = set()
        self._auto_apply_template_params()

    def _show_save_preset_dialog(self, template_path: str, output_dir: str):
        """弹出保存模板预设对话框 (公共方法, SystemSettingsDialog 也调用)。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("保存模板预设"))
        dlg.setMinimumWidth(350)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        mfr_combo = QComboBox()
        mfr_combo.setEditable(True)
        for m in self._tm.manufacturers:
            mfr_combo.addItem(m)
        name_edit = QLineEdit()
        default_name = Path(template_path).stem
        for t in self._tm.get_all_templates():
            if t.path == template_path:
                default_name = t.name; break
        name_edit.setText(default_name)
        form.addRow(self.tr("厂商:"), mfr_combo)
        form.addRow(self.tr("模板名:"), name_edit)
        layout.addLayout(form)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)
        if dlg.exec() != QDialog.Accepted: return
        mfr = mfr_combo.currentText().strip()
        tpl_name = name_edit.text().strip()
        if not mfr or not tpl_name: return
        self._tm.add_template(mfr, tpl_name, template_path, output_dir)
        self._log(f"✓ 模板预设已保存: {mfr} → {tpl_name}")

    def _save_template_path(self, path: str):
        """持久化模板路径到配置文件。"""
        self._cfg.config.last_template_path = path
        self._cfg._dirty = True

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

    def _auto_update_angle_config_from_template(self, sheets):
        """从模板工作表自动更新 Gain/AR 角度配置。

        当自动匹配触发时调用，确保角度配置与模板列头一致。
        仅在当前配置为默认值(PRESET_AUTOMOTIVE)或空时自动更新，
        用户手动修改过的配置不会被覆盖。
        """
        # 读取模板所有 LAG/AR 列头
        all_headers = []
        for si in sheets:
            for c in si.columns:
                all_headers.append(c.raw_header)

        # Gain (LAG) 配置
        lag_cfg = LagConfig.from_template_headers(all_headers)
        if not lag_cfg.is_empty():
            current_singles = set(self._lag_config.singles_sorted)
            template_singles = set(lag_cfg.singles_sorted)
            current_ranges = set(self._lag_config.ranges_sorted)
            template_ranges = set(lag_cfg.ranges_sorted)

            if current_singles != template_singles or current_ranges != template_ranges:
                self._lag_config = lag_cfg
                self._sync_quick_buttons()
                self._update_lag_display()
                self._log(
                    f"从模板自动更新 Gain 角度: "
                    f"单角度={lag_cfg.singles_sorted}, 范围={lag_cfg.ranges_sorted}"
                )

        # AR 配置
        ar_cfg = LagConfig.from_ar_headers(all_headers)
        if not ar_cfg.is_empty():
            current_ar_singles = set(self._ar_lag_config.singles_sorted)
            template_ar_singles = set(ar_cfg.singles_sorted)
            current_ar_ranges = set(self._ar_lag_config.ranges_sorted)
            template_ar_ranges = set(ar_cfg.ranges_sorted)

            if current_ar_singles != template_ar_singles or current_ar_ranges != template_ar_ranges:
                self._ar_lag_config = ar_cfg
                self._log(
                    f"从模板自动更新 AR 角度: "
                    f"单角度={ar_cfg.singles_sorted}, 范围={ar_cfg.ranges_sorted}"
                )

    def _auto_apply_template_params(self):
        """从模板自动识别并应用计算参数到主窗口。

        选择模板后自动调用，无需用户打开计算参数对话框。
        仅当检测到参数时才更新，避免覆盖用户手动设置。
        """
        tp = self._get_template_params()
        if not tp:
            return

        # 检查是否有变化
        if tp == self._required_params:
            return  # 没变化，不重复日志

        self._required_params = tp
        self._extra_params = set()
        self._log_current_params()

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
        """刷新已配置项 — 每项带删除按钮, 内容过多时自动滚动。"""
        # 确保 configItemsWidget 在 QScrollArea 中防止溢出重叠
        parent_layout = self.ui.configItemsWidget.parent().layout()
        if not hasattr(self, '_lag_scroll'):
            self._lag_scroll = QScrollArea()
            self._lag_scroll.setWidgetResizable(True)
            self._lag_scroll.setMaximumHeight(200)
            idx = parent_layout.indexOf(self.ui.configItemsWidget)
            parent_layout.removeWidget(self.ui.configItemsWidget)
            self._lag_scroll.setWidget(self.ui.configItemsWidget)
            parent_layout.insertWidget(idx, self._lag_scroll)

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
            label.setStyleSheet("color: #888; padding: 8px;")
            layout.addWidget(label)
            return

        # ---- 单角度 ----
        if singles:
            header = QLabel(self.tr("单角度："))
            header.setStyleSheet("font-weight: bold; margin-top: 4px;")
            layout.addWidget(header)
            for a in singles:
                row = QWidget()
                row.setMinimumHeight(30)
                h = QHBoxLayout(row)
                h.setContentsMargins(8, 4, 0, 4)
                h.setSpacing(8)
                lbl = QLabel(f"  {a}°")
                lbl.setStyleSheet("")
                lbl.setMinimumHeight(24)
                btn = QPushButton(" ✕ ")
                btn.setFixedHeight(24)
                btn.setToolTip(self.tr("移除此角度"))
                btn.setStyleSheet("padding: 2px 6px;")
                btn.clicked.connect(lambda checked, angle=a: self._remove_single(angle))
                h.addWidget(lbl)
                h.addWidget(btn)
                h.addStretch()
                layout.addWidget(row)

        # ---- 角度范围 ----
        if ranges:
            header = QLabel(self.tr("角度范围："))
            header.setStyleSheet("font-weight: bold; margin-top: 4px;")
            layout.addWidget(header)
            for lo, hi in ranges:
                row = QWidget()
                row.setMinimumHeight(30)
                h = QHBoxLayout(row)
                h.setContentsMargins(8, 4, 0, 4)
                h.setSpacing(8)
                lbl = QLabel(f"  ({lo}° - {hi}°)")
                lbl.setStyleSheet("")
                lbl.setMinimumHeight(24)
                btn = QPushButton(" ✕ ")
                btn.setFixedHeight(24)
                btn.setToolTip(self.tr("移除此范围"))
                btn.setStyleSheet("padding: 2px 6px;")
                btn.clicked.connect(lambda checked, lo=lo, hi=hi: self._remove_range(lo, hi))
                h.addWidget(lbl)
                h.addWidget(btn)
                h.addStretch()
                layout.addWidget(row)

        layout.addStretch()
        self._log_current_params()

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
        # 懒导入：处理链模块较重，仅在首次点击处理时加载
        from src.chart_config import ChartConfig
        from src.plot_config import PlotConfig
        from src.worker import ProcessingWorker
        # Guard: prevent re-entry if a worker is already running (race condition)
        # 检查 worker 是否还在运行（防止信号未处理时的竞态）
        worker_still_running = (
            self._worker is not None
            and not getattr(self._worker, '_cancelled', True)
            and self._thread is not None
            and self._thread.isRunning()
        )
        if worker_still_running:
            self._log(self.tr("⚠ 处理已在运行中，请等待完成"))
            return
        if self._running:
            return
        # 立即设置忙碌状态，防止用户在文件加载期间重复点击
        self._enter_busy(self.tr("⏳ 处理中..."))
        self.ui.btnStop.setEnabled(True)
        if not self._data_file_paths:
            self._restore_start_button()
            self.ui.btnStop.setEnabled(False)
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("请先通过「设置→数据源配置」添加数据文件并执行自动匹配。"))
            return

        # 自动触发匹配 (从 FileSettingsPage 读取)
        file_page = getattr(self, '_file_settings_page', None)
        match_table = file_page._match_table if file_page else getattr(self, '_match_table', None)
        if match_table is not None and match_table.rowCount() == 0 and self._data_file_paths:
            try:
                if file_page:
                    file_page._on_auto_match()
                else:
                    self._on_auto_match()
            except Exception as e:
                self._log(f"⚠ 自动匹配失败: {e}")
                QMessageBox.warning(self, self.tr("自动匹配失败"),
                    self.tr("无法自动匹配工作表与数据文件。\n"
                            "请通过「设置→数据源配置」手动进行匹配。\n\n"
                            "错误详情: ") + str(e))
                self._restore_start_button()
                return

        # LLM 辅助: 自动匹配后仍有未匹配文件时尝试 LLM 建议
        self._retry_unmatched_files()

        template_path = self.ui.editTemplatePath.text().strip()
        output_dir = self.ui.editOutputDir.text().strip() or str(Path.cwd() / "output")
        output_name = self.ui.editOutputName.text().strip() or "antenna_report.xlsx"
        output_name = output_name.replace("\\", "").replace("/", "")

        if not template_path:
            self._restore_start_button()
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("请选择模板 Excel 文件。"))
            return
        if not Path(template_path).exists():
            self._restore_start_button()
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("模板文件不存在"))
            return
        template_ext = Path(template_path).suffix.lower()
        if template_ext not in (".xlsx", ".xls", ".csv", ".docx"):
            self._restore_start_button()
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("不支持的模板文件格式。支持: .xlsx .xls .csv .docx"))
            return
        if template_ext in (".csv", ".docx"):
            self._restore_start_button()
            QMessageBox.warning(self, self.tr("不支持的模板格式"),
                self.tr(f"{template_ext} 模板格式当前仅支持存储预设，处理功能尚未实现。\n\n请使用 .xlsx 或 .xls 格式的模板文件。"))
            return

        os.makedirs(output_dir, exist_ok=True)
        output_path = str(Path(output_dir) / output_name)
        output_path = self._auto_rename_if_exists(output_path)

        full_report_path: Optional[str] = None
        if self.ui.checkFullReport.isChecked():
            path_text = self.ui.editFullReportPath.text().strip()
            full_report_path = path_text if path_text else str(Path(output_dir) / "full_report.xlsx")
            full_report_path = self._auto_rename_if_exists(full_report_path)

        plot_config = PlotConfig(
            elev=self.ui.spinElev.value(),
            azim=self.ui.spinAzim.value(),
            dpi=self.ui.spinDpi.value(),
            step_deg=getattr(self._chart_config_required, 'step_deg', 5.0) if self._chart_config_required else 5.0,
            embed_in_excel=self.ui.checkEmbedExcel.isChecked(),
            save_png_folder=str(Path(output_dir) / "png") if self.ui.checkSavePng.isChecked() else None,
        )


        # 显示文件加载进度 (setMaximum 只设一次, processEvents 每 20 个文件一次)
        # 为什么要节流: 每次 processEvents 会刷新整个 Qt 事件循环,
        # 在大量文件(>200)时每文件都调用会导致 UI 卡死. 每 20 个文件刷新一次
        # 在响应性和性能之间取得了平衡.
        file_page = getattr(self, '_file_settings_page', None)
        match_table = file_page._match_table if file_page else getattr(self, '_match_table', None)
        total_files = max(match_table.rowCount() if match_table else 0, 1)
        self.ui.progressBar.setMaximum(total_files)
        self.ui.progressBar.setValue(0)
        self.ui.lblProgressMsg.setText(self.tr("正在加载数据文件..."))
        if file_page:
            datasource_map = file_page.build_datasource_map(
                progress_callback=lambda c, t, m: (
                    self.ui.progressBar.setValue(c),
                    self.ui.lblProgressMsg.setText(m),
                    QApplication.processEvents() if c % 20 == 0 else None
                )
            )
        else:
            datasource_map = self._build_datasource_map(
                progress_callback=lambda c, t, m: (
                    self.ui.progressBar.setValue(c),
                    self.ui.lblProgressMsg.setText(m),
                    QApplication.processEvents() if c % 20 == 0 else None
                )
            )
        if not datasource_map:
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("没有有效的工作表↔文件匹配，请先执行自动匹配。"))
            self._restore_start_button()
            return
        self._log(f"多源模式: {len(datasource_map)} 个工作表")
        for sn, ds in datasource_map.items():
            self._log(f"  {sn} ← {type(ds).__name__}")

        # 构建 sheet → test_mode 映射 (混合批处理)
        if file_page:
            sheet_mode_map: Dict[str, int] = file_page.build_sheet_mode_map(datasource_map)
        else:
            sheet_mode_map: Dict[str, int] = self._build_sheet_mode_map(datasource_map)

        self.ui.logOutput.clear()
        self.ui.progressBar.setValue(0)
        self.ui.lblProgressMsg.setText(self.tr("启动中..."))

        self._thread = QThread(self)
        # 合并图表配置: 报告需要的 + 额外 + GUI checkbox 状态
        # GUI checkbox 优先级最高, 确保用户关闭图表后不会因默认值重新打开
        full_chart_config = ChartConfig()
        if self._chart_config_required is not None or self._chart_config_extra is not None:
            req = self._chart_config_required or ChartConfig()
            xtr = self._chart_config_extra or ChartConfig()
            full_chart_config = req.merge(xtr)
        # GUI checkbox 状态覆盖 ChartConfig 默认 (用户意图优先)
        if file_page:
            chart_flags = file_page.get_lag_checkboxes()
            full_chart_config.chart_eff_freq = chart_flags["chart_eff"]
            full_chart_config.chart_gain_freq = chart_flags["chart_lag"]
        png_dir = plot_config.save_png_folder
        full_chart_config.save_png_folder = png_dir

        # 从天线参数页面读取当前参数（Step 5: 替代旧 widget 读取）
        ant_page = getattr(self, '_antenna_params_page', None)
        if ant_page:
            params = ant_page.get_current_params()
            extrapolate_theta = params["extrapolate"]
            freq_source = params["freq_source"] or "datasource"
            trim_start = params["trim_start"]
            trim_end = params["trim_end"]
            robust_peak = params["robust_peak"]
        else:
            extrapolate_theta = self._check_extrapolate.isChecked()
            freq_source = self._cmb_freq_source.currentData() or "datasource"
            trim_start = self._spin_trim_start.value()
            trim_end = self._spin_trim_end.value()
            robust_peak = self._check_robust_peak.isChecked()

        # 多步进参数（从 AntennaParamsPage 读取）
        ant_page = getattr(self, '_antenna_params_page', None)
        if ant_page:
            step_values = ant_page.get_selected_steps()
            skip_original = ant_page.get_skip_original()
        else:
            step_values = []
            skip_original = False

        self._worker = ProcessingWorker(
            datasource_map=datasource_map,
            sheet_mode_map=sheet_mode_map,
            template_path=template_path,
            output_path=output_path,
            lag_config=self._lag_config,
            plot_config=plot_config,
            full_report_path=full_report_path,
            extrapolate_theta=extrapolate_theta,
            freq_source=freq_source,
            trim_start=trim_start,
            trim_end=trim_end,
            robust_peak=robust_peak,
            extra_params=self._extra_params if self._extra_params else None,
            nh_custom_angles=self._nh_custom_angles if self._nh_custom_angles else None,
            worksheet_naming_mode=self._worksheet_naming_mode,
            chart_config_obj=full_chart_config,
            ar_lag_config=self._ar_lag_config if hasattr(self, '_ar_lag_config') and not self._ar_lag_config.is_empty() else None,
            ar_output_db=self._ar_output_db,
            # 多步进参数
            step_values=step_values,
            skip_original=skip_original,
        )
        self._worker.moveToThread(self._thread)

        # 连接信号
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_worker_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._thread.finished.connect(self._thread.deleteLater)

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
        self._running = False
        self._data_stale = True  # 中断的计算，数据标记为陈旧
        self._worker = None
        # 安全退出线程：quit() 退出事件循环，wait(3000) 等待线程结束
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
        self._restore_start_button()
        self.ui.btnStop.setEnabled(False)

    def _restore_start_button(self):
        """恢复开始按钮到空闲状态。"""
        self._running = False
        self.ui.btnStart.setText(self.tr("▶ 开始处理"))
        self.ui.btnStart.setEnabled(True)
        self.ui.btnStop.setEnabled(False)

    def _enter_busy(self, text="⏳ 处理中..."):
        """进入忙碌状态：锁定开始按钮，防止主计算与工具操作并发。"""
        self._running = True
        self.ui.btnStart.setText(self.tr(text))
        self.ui.btnStart.setEnabled(False)

    def _exit_busy(self):
        """退出忙碌状态：恢复开始按钮。"""
        self._running = False
        self.ui.btnStart.setText(self.tr("▶ 开始处理"))
        self.ui.btnStart.setEnabled(True)

    def _on_progress(self, current: int, total: int, message: str):
        self.ui.progressBar.setMaximum(total)
        self.ui.progressBar.setValue(current)
        self.ui.lblProgressMsg.setText(message)

    def _on_worker_log(self, message: str):
        self._log(message)

    def _on_finished(self, results, images):
        self._running = False
        self._worker = None
        self._data_stale = True  # 计算完成，数据变为陈旧
        # 安全退出线程：quit() 退出事件循环，wait(3000) 等待线程结束
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
        self._restore_start_button()
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

        # 保存 .ant 任务包
        file_page = getattr(self, '_file_settings_page', None)
        if file_page and getattr(file_page, '_check_save_task', None) and file_page._check_save_task.isChecked():
            try:
                from src.task_package import save_task_package, next_available_filename
                output_dir = self.ui.editOutputDir.text().strip() or "."
                tpl_name = Path(self.ui.editTemplatePath.text().strip()).stem if self.ui.editTemplatePath.text().strip() else "task"
                ant_path = next_available_filename(output_dir, tpl_name)
                config_snapshot = {
                    "test_mode": self._test_mode,
                    "template_path": self.ui.editTemplatePath.text().strip(),
                    "output_path": self._worker.output_path if hasattr(self._worker, 'output_path') else "",
                    "lag_singles": self._lag_config.singles_sorted,
                    "lag_ranges": self._lag_config.ranges_sorted,
                    "ar_singles": self._ar_lag_config.singles_sorted if hasattr(self, '_ar_lag_config') else [],
                    "ar_ranges": self._ar_lag_config.ranges_sorted if hasattr(self, '_ar_lag_config') else [],
                    "extrapolate": self._check_extrapolate.isChecked() if hasattr(self, '_check_extrapolate') else False,
                }
                save_task_package(
                    ant_path, tpl_name,
                    data_file_paths=list(self._data_file_paths),
                    template_path=self.ui.editTemplatePath.text().strip(),
                    config_snapshot=config_snapshot,
                    results=results, images=images,
                )
                self._log(f"📦 任务包已保存: {Path(ant_path).name}")
            except Exception as e:
                self._log(f"⚠ 任务包保存失败: {e}")

        # 填充参数结果表
        self._populate_results_table(results)
        # 生成图形展示
        self._populate_charts(results)
        # 生成图形数据表
        self._populate_graph_data(results)
        # 自动切到结果Tab
        self.ui.tabConfig.setCurrentIndex(0)

    def _make_readable_label(self, key: str) -> str:
        """将内部 key 转换为短可读标签。
        ar_single_10 → AR 10°    lag_single_60.0 → LAG 60°
        ar_range_0_30 → AR 0-30°   lag_range_0_30 → LAG 0-30°
        """
        import re
        # AR/LAG single: xxx_single_<angle>
        m = re.match(r'(ar|lag)_single_([\d.]+)$', key)
        if m:
            prefix = m.group(1).upper()
            angle = m.group(2).rstrip('0').rstrip('.') if '.' in m.group(2) else m.group(2)
            return f"{prefix} {angle}°"
        # AR/LAG range: xxx_range_<lo>_<hi>
        m = re.match(r'(ar|lag)_range_([\d.]+)_([\d.]+)$', key)
        if m:
            prefix = m.group(1).upper()
            lo = m.group(2).rstrip('0').rstrip('.') if '.' in m.group(2) else m.group(2)
            hi = m.group(3).rstrip('0').rstrip('.') if '.' in m.group(3) else m.group(3)
            return f"{prefix} {lo}-{hi}°"
        return key

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

        # 生成列标签: 先用映射表，再用动态规则，最后回退到原始 key
        col_labels = [KEY_LABELS.get(k) or self._make_readable_label(k) for k in keys]

        table = QTableWidget()
        table.setColumnCount(len(keys))
        table.setHorizontalHeaderLabels(col_labels)
        table.setRowCount(len(first_sheet))
        table.setAlternatingRowColors(True)
        # 自动换行 + 按内容调整宽度
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        for ci in range(len(keys)):
            header.setSectionResizeMode(ci, QHeaderView.ResizeToContents)
        table.setWordWrap(True)
        table.setTextElideMode(Qt.ElideNone)
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
        """用处理结果填充 GraphViewer（GraphViewer 在启动时已创建，工具栏始终可见）。"""
        if not results or self._graph_viewer is None:
            return
        viewer = self._graph_viewer
        # 应用图形配置中的视角设置
        if self._chart_config_required is not None:
            viewer._elev = self._chart_config_required.elev
            viewer._azim = self._chart_config_required.azim
            step_deg = getattr(self._chart_config_required, 'step_deg', 5.0)
        else:
            step_deg = 5.0
        viewer.load_data(results, step_deg=step_deg)
        self._log("图形数据已加载 — 可在「📈 图形展示」标签页查看 3D 方向图")

    def _populate_graph_data(self, results):
        """在独立标签页展示 3D 图形原始数据表格。"""
        from ui.graph_viewer import GraphDataTab
        GraphDataTab.install_in(self.ui.tabConfig, results)
        self._log("图形数据已加载 — 可在「📈 图形展示」标签页查看 3D 方向图")

    def _on_error(self, message: str):
        self._running = False
        self._worker = None
        self._data_stale = True  # 错误后数据陈旧，下次处理前自动清除
        # 安全退出线程：quit() 退出事件循环，wait(3000) 等待线程结束
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
        self._restore_start_button()
        self.ui.btnStop.setEnabled(False)
        self._log(f"✗ 错误: {message}")
        QMessageBox.critical(self, self.tr("处理错误"), message)

    # ==================================================================
    # 主题切换
    # ==================================================================


    # ==================================================================
    # 语言切换
    # ==================================================================


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
        """追加日志行。Emoji 在 GUI 环境中提供视觉提示；若需 CLI 纯文本
        输出，调用方可预先 strip 掉 emoji 字符。"""
        ts = datetime.now().strftime("%H:%M:%S")
        self.ui.logOutput.appendPlainText(f"[{ts}] {message}")
        # 自动滚动到底部
        cursor = self.ui.logOutput.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.ui.logOutput.setTextCursor(cursor)

    def _update_param_summary(self) -> str:
        """生成当前天线参数摘要（供底部状态栏显示）。"""
        from src.ui_utils import build_param_summary_text
        return build_param_summary_text(
            test_mode=self._test_mode,
            required_params=self._required_params,
            extra_params=self._extra_params,
            lag_config=self._lag_config,
            ar_lag_config=self._ar_lag_config if hasattr(self, '_ar_lag_config') else None,
        )

    def _log_current_params(self):
        """将当前天线参数摘要打印到日志窗口。"""
        mode_names = {0: "📡 无源天线", 1: "📶 有源发射 TRP", 2: "📻 有源接收 TIS"}
        mode_str = mode_names.get(self._test_mode, "未知")

        # 构建参数 key → 人类可读名称的映射
        from ui.dialogs import CalcParamsDialog
        param_labels = {}
        for params_list in [CalcParamsDialog._COMMON_PARAMS,
                            CalcParamsDialog._TRP_PARAMS,
                            CalcParamsDialog._TIS_PARAMS]:
            for _, items in params_list:
                for key, label in items:
                    param_labels[key] = label

        lines = [
            "══════ 当前天线参数 ══════",
            f"  测试模式: {mode_str}",
        ]

        # 计算参数
        all_params = sorted(self._required_params | self._extra_params)
        param_names = [param_labels.get(k, k) for k in all_params]
        if param_names:
            lines.append(f"  计算参数: {', '.join(param_names)}")
        else:
            lines.append("  计算参数: (未选择)")

        # Gain/LAG 角度
        gain_singles = self._lag_config.singles_sorted
        gain_ranges = self._lag_config.ranges_sorted
        if gain_singles or gain_ranges:
            parts = [f"{a}°" for a in gain_singles]
            if gain_ranges:
                parts.append("范围: " + ", ".join(f"({lo}°–{hi}°)" for lo, hi in gain_ranges))
            lines.append(f"  Gain 角度: {', '.join(parts)}")
        else:
            lines.append("  Gain 角度: (未设置)")

        # AR 角度
        if hasattr(self, '_ar_lag_config'):
            ar_cfg = self._ar_lag_config
            ar_singles = ar_cfg.singles_sorted
            ar_ranges = ar_cfg.ranges_sorted
            if ar_singles or ar_ranges:
                parts = [f"{a}°" for a in ar_singles]
                if ar_ranges:
                    parts.append("范围: " + ", ".join(f"({lo}°–{hi}°)" for lo, hi in ar_ranges))
                lines.append(f"  AR 角度: {', '.join(parts)}")
            else:
                lines.append("  AR 角度: (未设置)")

        # 频点 & 算法 — 优先从天线参数页面读取
        ant_page = getattr(self, '_antenna_params_page', None)
        if ant_page:
            params = ant_page.get_current_params()
            freq_src = params["freq_source"]
            freq_text = "数据源" if freq_src == "datasource" else "模板"
            trim_start = params["trim_start"]
            trim_end = params["trim_end"]
            extrap = params["extrapolate"]
            robust = params["robust_peak"]
        else:
            freq_text = self._cmb_freq_source.currentText() if hasattr(self, '_cmb_freq_source') and self._cmb_freq_source else "—"
            trim_start = self._spin_trim_start.value() if hasattr(self, '_spin_trim_start') else 0
            trim_end = self._spin_trim_end.value() if hasattr(self, '_spin_trim_end') else 0
            extrap = hasattr(self, '_check_extrapolate') and self._check_extrapolate.isChecked()
            robust = hasattr(self, '_check_robust_peak') and self._check_robust_peak.isChecked()
        trim = f"去除: 前{trim_start} / 后{trim_end}"
        lines.append(f"  频点: {freq_text} | {trim}")

        # 算法
        algo = []
        if extrap:
            algo.append("Theta 外推 180°")
        if robust:
            algo.append("Robust peak")
        lines.append(f"  算法: {', '.join(algo) if algo else '(默认)'}")

        lines.append("════════════════════════════")

        # 一次性打印到日志区（不加时间戳，保持格式整洁）
        self.ui.logOutput.appendPlainText("\n".join(lines))
        # 自动滚动
        cursor = self.ui.logOutput.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.ui.logOutput.setTextCursor(cursor)

    def _update_status(self):
        """更新状态栏 — 显示当前 Gain 和 AR 角度配置概要。"""
        gain_singles = len(self._lag_config.singles_sorted)
        gain_ranges = len(self._lag_config.ranges_sorted)
        ar_cfg = getattr(self, '_ar_lag_config', None)
        ar_singles = len(ar_cfg.singles_sorted) if ar_cfg else 0
        ar_ranges = len(ar_cfg.ranges_sorted) if ar_cfg else 0
        parts = [f"Gain: {gain_singles}单+{gain_ranges}范围"]
        if ar_singles or ar_ranges:
            parts.append(f"AR: {ar_singles}单+{ar_ranges}范围")
        self.statusBar().showMessage(
            self.tr(" | ".join(parts) + " | 就绪"))

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
            # 自动清除上次计算遗留的陈旧数据 (即使 _data_file_paths 为空仍须清 UI)
            if self._data_stale:
                n_stale = len(self._data_file_paths)
                if n_stale > 0:
                    self._log(f"🗑 自动清除上次计算遗留的 {n_stale} 个文件")
                self._data_file_paths.clear()
                self._file_entries.clear()
                self._file_list_widget.setRowCount(0)
                self._match_table.setRowCount(0)
                self._lbl_match_status.setText("")
            existing = set(self._data_file_paths)
            new = [p for p in valid if p not in existing]
            if new:
                self._data_file_paths.extend(new)
                self._data_stale = False
                self._sync_file_entries()
                self._refresh_data_file_ui()
                self._log(f"📂 拖拽添加 {len(new)} 个文件")
                if self.ui.editTemplatePath.text().strip():
                    self._on_auto_match()

    # ==================================================================
    # 窗口关闭
    # ==================================================================

    def closeEvent(self, event):
        """窗口关闭时停止线程 + 保存位置。"""
        import base64
        geom = self.saveGeometry()
        self._cfg.config.window_geometry = bytes(geom.toBase64().data()).decode()
        self._cfg._dirty = True
        if self._thread and self._thread.isRunning():
            if self._worker:
                self._worker.cancel()
            self._thread.quit()
            if not self._thread.wait(5000):
                self._thread.terminate()
                self._thread.wait()
        self._running = False
        event.accept()
