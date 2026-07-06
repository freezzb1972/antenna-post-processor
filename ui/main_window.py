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
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from PySide6.QtCore import QEvent, QSettings, Qt, QThread, QTimer
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
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QAbstractItemView,
    QDialog,
    QVBoxLayout,
    QWidget,
)

from src.file_entry import FileEntry, mode_name, infer_mode_from_sheet
from src.lag_config import LagConfig, PRESET_AUTOMOTIVE
from src.multi_antenna import AntennaConfig, extract_antenna_name
from src.scale_manager import ScaleManager, AdaptiveWidgetMixin
from ui.compiled.ui_main_window import Ui_MainWindow
from ui.pages import FileSettingsPage, AntennaParamsPage, ChartSettingsPage
from ui.widgets import ThinSplitter

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

        # 覆盖编译 UI 中的过长标题
        self.setWindowTitle(self.tr("天线参数后处理"))

        # 允许拖拽文件到窗口 (优先级2)
        self.setAcceptDrops(True)

        # 标记用户手动编辑输出文件名
        self.ui.editOutputName.textEdited.connect(
            lambda: setattr(self, '_user_set_output_name', True))

        # ---- 状态 ----
        self._lag_config = LagConfig(
            single_angles=[0, 10, 20, 90],
            ranges=[(0, 90), (60, 90)],
        )
        self._thread: Optional[QThread] = None
        self._worker: Optional[ProcessingWorker] = None
        self._running = False
        self._data_stale = True  # 数据是否为上次计算遗留 (用于自动清除)
        # 预览 → 出报告 状态机
        self._PREVIEW_IDLE = 0; self._PREVIEWING = 1; self._READY = 2; self._EXPORTING = 3
        self._preview_state = self._PREVIEW_IDLE
        self._preview_dirty = False  # 预览运行中参数变更标记
        self._user_set_output_name = False  # 用户手动编辑输出文件名后置 True
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
        self._last_matches: list = []        # 工作表-文件匹配结果
        self._chart_instances: list = []     # 图表实例列表 (ChartInstance)
        self._required_params: set = set()   # 用户确认的报告必需参数
        self._extra_params: set = set()      # 用户额外选择的计算参数
        self._dir_extrap_method: str = "linear"  # Directivity 外推算法
        self._test_mode: int = 0             # 0=passive, 1=TRP, 2=TIS
        self._worksheet_naming_mode: int = 0  # 0=保留原模板工作表名, 1=用数据源名命名
        self._mode_states = [{}, {}, {}]     # 三种测试模式独立参数状态
        self._ar_lag_config = LagConfig()     # AR 独立角度配置
        self._rhcp_lag_config = LagConfig()  # RHCP 独立角度配置
        self._cpxpi_lag_config = LagConfig() # CP-XPI 独立角度配置
        self._multi_antenna_config = None     # 多天线配置
        self._antenna_configs: dict[str, "AntennaConfig"] = {}  # per-antenna 配置
        self._current_antenna_name: str = ""   # 当前编辑的天线
        self._antenna_results: dict[str, dict] = {}   # antenna_name → results
        self._antenna_images: dict[str, dict] = {}    # antenna_name → images
        self._ant_queue: list[str] = []               # 多天线处理队列
        self._ant_idx: int = 0                        # 当前处理索引
        self._ant_all_results: dict = {}              # 累积结果
        self._ant_all_images: dict = {}               # 累积图片
        self._nh_custom_angles: List[float] = []  # NHPRP/NHPIS 自定义角度列表
        self._ar_output_db: bool = True     # AR 默认输出 dB
        self._chart_config_required = None   # ChartConfig: 报告需要
        self._chart_config_extra = None      # ChartConfig: 额外(full_report)
        from src.azimuth_config import AzimuthReportConfig
        self._azimuth_config = AzimuthReportConfig()  # 方位面报告配置
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
        self._update_params_display() # 初始化执行栏参数面板
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
        # 输出默认: 嵌入Excel 默认关闭, 图片优先输出到 Word
        self.ui.checkEmbedExcel.setChecked(False)
        self._enter_idle()  # 初始化按钮状态机（btnStart/btnExport/btnOneClick/btnStop）
        self._log("天线参数后处理工具已启动")

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

        # 输出文件名: 默认用数据源名+日期，用户编辑后保留自定义
        if not self._user_set_output_name and template_path:
            from src.template_manager import TemplateManager as TM
            out_dir = self.ui.editOutputDir.text() or str(Path.cwd() / "output")
            if self._data_file_paths:
                src_name = Path(self._data_file_paths[0]).stem
            else:
                src_name = Path(template_path).stem
            fname = TM.next_available_filename(out_dir, src_name)
            self.ui.editOutputName.setText(fname)

        # 模板预设管理已移至「文件→系统设置」对话框


    def _apply_minimum_sizes(self):
        """设置关键输入框的最小宽度 — setStyleSheet 后会重置,需独立调用。"""
        self.ui.editOutputDir.setMinimumWidth(200)
        self.ui.editOutputName.setMinimumWidth(200)
        self.ui.editFullReportPath.setMinimumWidth(200)

    def _init_multi_file_ui(self):
        """构建多文件选择 + 自动匹配 UI。

        注意: 具体的按钮/列表/匹配表控件已由 FileSettingsPage._setup_ui() 统一管理，
        此方法仅保留旧版单文件 UI 隐藏 + 全局设置。
        """
        # ---- 隐藏旧的单文件输入行（与多文件功能重复） ----
        self.ui.lblCsv.hide()
        self.ui.editCsvPath.hide()
        self.ui.btnBrowseCsv.hide()
        self.ui.groupInput.setTitle(self.tr("模板文件"))

        self._apply_minimum_sizes()

        # 完整报告路径显示/隐藏
        self.ui.checkFullReport.toggled.connect(self._on_full_report_toggled)
        self._on_full_report_toggled(self.ui.checkFullReport.isChecked())

        # ---- 将整个 Tab 的内容包裹在可滚动区域中，防止内容溢出被压缩 ----
        self._make_tab_scrollable(self.ui.tabLag)

        # ---- 图形展示 Tab: 启动时创建空 GraphViewer (工具栏立即可见) ----
        from ui.graph_viewer import GraphViewer
        viewer = GraphViewer()
        viewer._mw = self  # 用于 _on_apply_angles_to_config 回写
        self._graph_viewer = viewer
        self.ui.vTabCharts.addWidget(self._graph_viewer)

    # ── Widget 代理 — 所有控件现在由 FileSettingsPage 统一管理 ──

    @property
    def _file_list_widget(self):
        p = getattr(self, '_file_settings_page', None)
        return p._file_list_widget if p else None

    @property


    def _cmb_naming_mode(self):
        p = getattr(self, '_file_settings_page', None)
        return p._cmb_naming_mode if p else None

    @property
    def _data_file_widget(self):
        p = getattr(self, '_file_settings_page', None)
        return p if p else None

    @property
    def _btn_add_files(self):
        p = getattr(self, '_file_settings_page', None)
        return p._btn_add_files if p else None

    @property
    def _btn_clear_selected(self):
        p = getattr(self, '_file_settings_page', None)
        return p._btn_clear_selected if p else None

    @property
    def _btn_clear_all(self):
        p = getattr(self, '_file_settings_page', None)
        return p._btn_clear_all if p else None

    @property
    def _btn_auto_match(self):
        p = getattr(self, '_file_settings_page', None)
        return p._btn_auto_match if p else None

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

        row_theta_extrap = QHBoxLayout()
        row_theta_extrap.addWidget(QLabel(self.tr("Theta 外推:")))
        self._cmb_extrapolate = QComboBox()
        self._cmb_extrapolate.addItem(self.tr("不外推"), None)
        self._cmb_extrapolate.addItem(self.tr("线性"), "linear")
        self._cmb_extrapolate.addItem(self.tr("常数"), "constant")
        self._cmb_extrapolate.addItem(self.tr("镜像"), "mirror")
        self._cmb_extrapolate.setCurrentIndex(0)
        self._cmb_extrapolate.setToolTip(self.tr("除 Directivity 外所有参数的 Theta 外推算法"))
        row_theta_extrap.addWidget(self._cmb_extrapolate)
        row_theta_extrap.addStretch()
        algo_vbox.addLayout(row_theta_extrap)


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
                w.hide()  # 清空旧的 vTabFile 内容（被 Master-Detail 布局替代）

        # 3. 构建 Master-Detail 布局
        container = QWidget()
        h_layout = QHBoxLayout(container)
        h_layout.setSpacing(8)
        h_layout.setContentsMargins(0, 0, 12, 0)

        # 左侧导航
        left_sidebar = QVBoxLayout()
        left_sidebar.setSpacing(4)
        left_sidebar.setContentsMargins(0, 0, 0, 0)

        # 天线选择器
        ant_sel_row = QHBoxLayout()
        ant_sel_row.addWidget(QLabel("<b>" + self.tr("天线:") + "</b>"))
        self._antenna_selector = QComboBox()
        self._antenna_selector.setMinimumWidth(100)
        self._antenna_selector.setToolTip(self.tr("选择要配置的天线"))
        self._antenna_selector.currentIndexChanged.connect(self._on_antenna_selector_changed)
        ant_sel_row.addWidget(self._antenna_selector, 1)
        left_sidebar.addLayout(ant_sel_row)

        self._nav_list = QListWidget()
        self._nav_list.setFixedWidth(140)
        self._nav_list.setSpacing(2)
        self._nav_list.setStyleSheet("QListWidget::item { padding: 8px 4px; }")
        left_sidebar.addWidget(self._nav_list, 1)
        h_layout.addLayout(left_sidebar)

        # 右侧页面栈
        self._page_stack = QStackedWidget()
        h_layout.addWidget(self._page_stack, 1)

        # 创建 3 个页面
        self._file_settings_page = FileSettingsPage(self)
        self._antenna_params_page = AntennaParamsPage(self)
        self._chart_settings_page = ChartSettingsPage(self)

        self._file_settings_page.setObjectName("pageInput")
        self._antenna_params_page.setObjectName("pageAntenna")
        self._chart_settings_page.setObjectName("pageChart")
        self._page_stack.addWidget(self._file_settings_page)    # 0
        self._page_stack.addWidget(self._antenna_params_page)   # 1
        self._page_stack.addWidget(self._chart_settings_page)   # 2

        # 导航项 (含 tooltip 说明页面内容)
        nav_items = [
            ("📂 " + self.tr("输入输出"), 0, self.tr("添加数据文件、选择模板、配置输出路径")),
            ("📡 " + self.tr("天线参数"), 1, self.tr("配置 LAG/AR 角度、计算参数、预览结果")),
            ("📊 " + self.tr("图表配置"), 2, self.tr("3D方向图、2D切面、频点曲线图表设置")),
        ]
        for label, idx, tip in nav_items:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, idx)
            item.setToolTip(tip)
            self._nav_list.addItem(item)

        self._nav_list.currentRowChanged.connect(self._on_nav_changed)
        self._nav_list.setCurrentRow(0)

        # 天线参数变更 → 实时更新执行栏参数面板
        self._antenna_params_page.params_changed.connect(self._update_params_display)
        self._antenna_params_page.params_changed.connect(self._staleness_check)

        # 添加到 tabFile
        self.ui.vTabFile.addWidget(container)

    def _extract_execution_bar(self):
        """将执行栏从 tabFile 移动到 rootVBox（跨标签页共享）。"""
        vtab = self.ui.vTabFile

        for i in reversed(range(vtab.count())):
            item = vtab.itemAt(i)
            if item is None: continue
            lyt = item.layout(); w = item.widget()
            if lyt is self.ui.hProgress or lyt is self.ui.hButtons: vtab.takeAt(i)
            elif w is self.ui.logOutput: vtab.takeAt(i)

        exec_bar = QWidget()
        exec_layout = QVBoxLayout(exec_bar)
        exec_layout.setContentsMargins(0, 0, 0, 0); exec_layout.setSpacing(4)

        progress_row = QHBoxLayout()
        progress_row.addWidget(self.ui.progressBar)
        progress_row.addWidget(self.ui.lblProgressMsg)
        exec_layout.addLayout(progress_row)

        h_splitter = ThinSplitter(Qt.Horizontal)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._params_display = QTextEdit()
        self._params_display.setReadOnly(True)
        self._params_display.setStyleSheet("background: rgba(0,0,0,0.03); border: none; padding: 4px; font-size: 12px;")
        self._params_display.setMinimumWidth(250)
        left_layout.addWidget(self._params_display, 1)

        # 按钮行: 模式标签 + hButtons (spBtnLeft → btnStart → btnStop → _btn_export)
        btn_row = QHBoxLayout()
        self._mode_freq_label = QLabel()
        self._mode_freq_label.setTextFormat(Qt.RichText)
        self._mode_freq_label.setStyleSheet("padding: 2px 4px; font-size: 12px;")
        btn_row.addWidget(self._mode_freq_label)
        btn_row.addStretch()
        # hButtons 直接包进 QWidget 保持原对齐
        btn_wrap = QWidget()
        btn_wrap.setLayout(self.ui.hButtons)
        self._btn_export = QPushButton(self.tr("📄 出报告"))
        self._btn_export.setMinimumSize(110, 32)
        self._btn_export.clicked.connect(self._on_export)
        self._btn_export.setEnabled(False)
        self.ui.hButtons.addWidget(self._btn_export)

        self._btn_one_click = QPushButton(self.tr("🚀 一键出报告"))
        self._btn_one_click.setMinimumSize(120, 32)
        self._btn_one_click.clicked.connect(self._on_one_click)
        self._btn_one_click.setEnabled(False)
        self.ui.hButtons.addWidget(self._btn_one_click)
        btn_row.addWidget(btn_wrap)
        left_layout.addLayout(btn_row)

        h_splitter.addWidget(left_panel)
        self.ui.logOutput.setParent(exec_bar)
        h_splitter.addWidget(self.ui.logOutput)
        h_splitter.setSizes([300, 500])
        exec_layout.addWidget(h_splitter, 1)

        # 重命名按钮
        self.ui.btnStart.setText(self.tr("👁 预览"))
        # 断开旧连接(编译 UI 已连接 _on_start), 重新连接到 _on_preview
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try: self.ui.btnStart.clicked.disconnect()
            except (RuntimeError, TypeError): pass
        self.ui.btnStart.clicked.connect(self._on_preview)

        v_splitter = ThinSplitter(Qt.Vertical)
        idx = self.ui.rootVBox.indexOf(self.ui.tabConfig)
        self.ui.rootVBox.removeWidget(self.ui.tabConfig)
        v_splitter.addWidget(self.ui.tabConfig)
        v_splitter.addWidget(exec_bar)
        v_splitter.setStretchFactor(0, 3); v_splitter.setStretchFactor(1, 1)
        self.ui.rootVBox.insertWidget(idx, v_splitter)
        self._execution_bar = exec_bar

    def _on_nav_changed(self, row: int):
        """导航列表切换 → 切换页面栈。所有页面内联展开。"""
        if hasattr(self, '_page_stack') and 0 <= row < self._page_stack.count():
            if row == 1 and hasattr(self, '_antenna_params_page'):
                self._antenna_params_page._load_state()
            self._page_stack.setCurrentIndex(row)

    def _on_config_tab_changed(self, index: int):
        """切换标签页时显示/隐藏执行栏（仅 tab[0] 处理设置显示）。"""
        if hasattr(self, '_execution_bar'):
            self._execution_bar.setVisible(index == 0)

    # ═══════════════════════════════════════════════════════════════
    # 天线选择器
    # ═══════════════════════════════════════════════════════════════

    def _refresh_antenna_selector(self):
        """从 FileSettingsPage._file_entries 刷新天线选择器。"""
        self._antenna_selector.blockSignals(True)
        current = self._antenna_selector.currentData()
        self._antenna_selector.clear()
        seen = set()
        # 从 FileSettingsPage 读取已填充 antenna_name 的 FileEntry 列表
        file_page = getattr(self, '_file_settings_page', None)
        entries = file_page._file_entries if file_page else []
        if not entries and self._data_file_paths:
            # fallback: 直接从文件路径提取
            from src.multi_antenna import extract_antenna_name as _extract
            for p in self._data_file_paths:
                name = _extract(p)
                if name not in seen:
                    self._antenna_selector.addItem(name, name)
                    seen.add(name)
                    if name not in self._antenna_configs:
                        self._antenna_configs[name] = AntennaConfig(
                            name=name, data_files=[p],
                            required_params=set(self._required_params))
        else:
            for fe in entries:
                name = fe.antenna_name or extract_antenna_name(fe.path)
                if name not in seen:
                    self._antenna_selector.addItem(name, name)
                    seen.add(name)
                    if name not in self._antenna_configs:
                        ant = AntennaConfig(name=name, data_files=[fe.path],
                                            test_mode=fe.test_mode,
                                            required_params=set(self._required_params))
                        self._antenna_configs[name] = ant
                    else:
                        ant = self._antenna_configs[name]
                        if fe.path not in ant.data_files:
                            ant.data_files.append(fe.path)
        # 恢复选择
        if current and current in seen:
            idx = self._antenna_selector.findData(current)
            if idx >= 0: self._antenna_selector.setCurrentIndex(idx)
        elif self._antenna_selector.count() > 0:
            self._antenna_selector.setCurrentIndex(0)
        self._antenna_selector.blockSignals(False)

    def _on_antenna_selector_changed(self, idx: int):
        """切换天线 → 保存当前配置 → 加载新天线配置。"""
        if idx < 0:
            return
        new_name = self._antenna_selector.itemData(idx)
        if not new_name or new_name == self._current_antenna_name:
            return

        # 保存当前天线配置
        self._save_current_antenna_config()

        # 切换到新天线
        self._current_antenna_name = new_name
        self._load_antenna_config(new_name)

    def _save_current_antenna_config(self):
        """保存当前页面的编辑状态到当前 AntennaConfig。"""
        if not self._current_antenna_name:
            return
        ant = self._antenna_configs.get(self._current_antenna_name)
        if not ant:
            return
        # 从 AntennaParamsPage 保存
        if hasattr(self, '_antenna_params_page'):
            ap = self._antenna_params_page
            ant.test_mode = getattr(ap, '_test_mode', 0)
            ant.lag_config = ap._gain_angle_widget.get_config() if getattr(ap, '_gain_angle_widget', None) else LagConfig()
            ant.ar_lag_config = ap._ar_angle_widget.get_config() if getattr(ap, '_ar_angle_widget', None) else LagConfig()
            ant.rhcp_lag_config = ap._rhcp_angle_widget.get_config() if getattr(ap, '_rhcp_angle_widget', None) else LagConfig()
            ant.cpxpi_lag_config = ap._cpxpi_angle_widget.get_config() if getattr(ap, '_cpxpi_angle_widget', None) else LagConfig()
            ant.required_params = ap._get_checked_keys(ap._left_checkboxes) if hasattr(ap, '_get_checked_keys') else set()
            ant.extra_params = ap._get_checked_keys(ap._right_checkboxes) if hasattr(ap, '_get_checked_keys') else set()

    def _load_antenna_config(self, name: str):
        """加载指定天线的配置到 UI 页面。"""
        ant = self._antenna_configs.get(name)
        if not ant:
            return
        # 同步 test_mode 到 MainWindow
        self._test_mode = ant.test_mode

        # 同步到 AntennaParamsPage
        if hasattr(self, '_antenna_params_page'):
            ap = self._antenna_params_page
            ap._test_mode = ant.test_mode
            # 更新 mode selector
            if hasattr(ap, '_cmb_test_mode'):
                ap._cmb_test_mode.blockSignals(True)
                idx = ap._cmb_test_mode.findData(ant.test_mode)
                if idx >= 0: ap._cmb_test_mode.setCurrentIndex(idx)
                ap._cmb_test_mode.blockSignals(False)
            # 加载参数 checkbox 状态（如果天线未独立配置，继承模板参数）
            params_to_use = ant.required_params if ant.required_params else self._required_params
            extra_to_use = ant.extra_params if ant.extra_params else self._extra_params
            for key, cb in ap._left_checkboxes.items():
                cb.setChecked(key in params_to_use)
            for key, cb in ap._right_checkboxes.items():
                cb.setChecked(key in extra_to_use)
            # 加载角度配置（如果天线未独立配置，继承全局模板配置）
            gain_cfg = ant.lag_config if not ant.lag_config.is_empty() else self._lag_config
            ar_cfg = ant.ar_lag_config if not ant.ar_lag_config.is_empty() else (
                self._ar_lag_config if hasattr(self, '_ar_lag_config') else LagConfig())
            rhcp_cfg = ant.rhcp_lag_config if not ant.rhcp_lag_config.is_empty() else (
                self._rhcp_lag_config if hasattr(self, '_rhcp_lag_config') else LagConfig())
            cpxpi_cfg = ant.cpxpi_lag_config if not ant.cpxpi_lag_config.is_empty() else (
                self._cpxpi_lag_config if hasattr(self, '_cpxpi_lag_config') else LagConfig())
            if getattr(ap, '_gain_angle_widget', None):
                ap._gain_angle_widget.set_config(gain_cfg)
            if getattr(ap, '_ar_angle_widget', None):
                ap._ar_angle_widget.set_config(ar_cfg)
            if getattr(ap, '_rhcp_angle_widget', None):
                ap._rhcp_angle_widget.set_config(rhcp_cfg)
            if getattr(ap, '_cpxpi_angle_widget', None):
                ap._cpxpi_angle_widget.set_config(cpxpi_cfg)

        # 同步到 ChartSettingsPage mode selector
        if hasattr(self, '_chart_settings_page'):
            cp = self._chart_settings_page
            if hasattr(cp, '_cmb_test_mode'):
                cp._cmb_test_mode.blockSignals(True)
                idx = cp._cmb_test_mode.findData(ant.test_mode)
                if idx >= 0: cp._cmb_test_mode.setCurrentIndex(idx)
                cp._cmb_test_mode.blockSignals(False)
                cp._rebuild_chart_categories(ant.test_mode)
            # 单向同步天线名到图表配置 (用户可在图表页手动修改)
            if hasattr(cp, '_edit_antenna_name') and ant.name:
                cur = cp._edit_antenna_name.text().strip()
                if not cur or cur == getattr(self, '_last_ant_name_synced', ''):
                    cp._edit_antenna_name.setText(ant.name)
                    self._last_ant_name_synced = ant.name

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
        fm.addAction(self.tr("打开任务包..."), self._on_open_task_package, QKeySequence("Ctrl+O"))
        fm.addSeparator()
        fm.addAction(self.tr("保存任务包"), self._on_save_task_package, QKeySequence("Ctrl+S"))
        fm.addAction(self.tr("另存任务包..."), self._on_saveas_task_package, QKeySequence("Ctrl+Shift+S"))
        fm.addSeparator()
        fm.addAction(self.tr("打印..."), self._on_print, QKeySequence("Ctrl+P"))
        fm.addSeparator()
        fm.addAction(self.tr("系统设置..."), self._show_system_settings)
        fm.addSeparator()
        fm.addAction(self.tr("退出"), QApplication.instance().quit, QKeySequence("Ctrl+Q"))

        # ── 项目管理 ──
        pm = menubar.addMenu(self.tr("项目(&P)"))
        pm.addAction(self.tr("📂 打开项目管理..."), self._on_project_manager)
        pm.addAction(self.tr("📋 从 JSON 导入..."), self._on_project_import_json)
        self._menu_recent_projects = pm.addMenu(self.tr("📄 最近项目"))
        self._menu_recent_projects.aboutToShow.connect(self._on_refresh_recent_menu)

        # ── 窗口 ──
        self._menu_window = menubar.addMenu(self.tr("&窗口"))
        self._menu_window.addAction(self.tr("新建窗口"), self._on_new_window)
        self._menu_window.addSeparator()
        # 窗口列表由 WindowManager 动态填充

        # ── 工具 ──
        tm = menubar.addMenu(self.tr("&工具"))
        # 数据处理子菜单
        data_menu = tm.addMenu(self.tr("数据处理"))
        data_menu.addAction(self.tr("数据检查与转换..."), self._on_tool_batch_check)
        data_menu.addAction(self.tr("路径损耗补偿..."), self._on_tool_calibrate)
        data_menu.addAction(self.tr("数据合并 (多段拼接)..."), self._on_tool_merge)
        data_menu.addAction(self.tr("步进重采样..."), self._on_tool_resample)
        data_menu.addAction(self.tr("数据修复 (插值)..."), self._on_tool_quality_repair)
        data_menu.addSeparator()
        data_menu.addAction(self.tr("EMQuest 数据导出..."), self._on_tool_emq_export)
        data_menu.addAction(self.tr("FinalSummary 转 CSV..."), self._on_tool_xlsx_to_csv)
        # 模板/SDT
        tm.addAction(self.tr("模板预设管理..."), self._on_tool_template_recognizer)
        tm.addAction(self.tr("Docx SDT 工具箱..."), self._on_tool_docx_sdt)
        tm.addAction(self.tr("报告元数据..."), self._on_tool_metadata)
        tm.addAction(self.tr("列识别规则..."), self._on_tool_pattern_mgr)
        tm.addSeparator()
        tm.addAction(self.tr("校准预设管理..."), self._on_show_rsp_presets)

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

        # 包裹 QScrollArea 防止内容溢出被压缩 (G4 门禁)
        for idx in [0, 2]:
            w = tc.widget(idx)
            if w is not None and not isinstance(w, QScrollArea):
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QScrollArea.NoFrame)
                title = tc.tabText(idx)
                tc.removeTab(idx)
                scroll.setWidget(w)
                tc.insertTab(idx, scroll, title)

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

    def _on_open_task_package(self):
        """打开 .ant 任务包。"""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("打开任务包"), "",
            self.tr("任务包 (*.ant);;所有文件 (*)"))
        if not path:
            return
        try:
            from src.task_package import load_task_package, verify_data_integrity
            meta = load_task_package(path)
            integrity = verify_data_integrity(meta)
            modified = [k for k, v in integrity.items() if v == "modified"]
            missing = [k for k, v in integrity.items() if v == "missing"]
            msg = [self.tr(f"任务: {meta.get('task_name', '?')}"),
                   self.tr(f"创建: {meta.get('created', '?')}")]
            if modified:
                msg.append(self.tr(f"\n⚠ {len(modified)} 个数据文件已修改，建议重新计算。"))
            if missing:
                msg.append(self.tr(f"\n❌ {len(missing)} 个数据文件已移动。"))
            QMessageBox.information(self, self.tr("任务包信息"), "\n".join(msg))
        except Exception as e:
            QMessageBox.warning(self, self.tr("打开失败"), self.tr(f"无法打开任务包:\n{e}"))

    def _on_save_task_package(self):
        """快速保存任务包（自动命名，覆盖已存在）。"""
        tpl_name = Path(self.ui.editTemplatePath.text().strip()).stem if self.ui.editTemplatePath.text().strip() else "task"
        output_dir = self.ui.editOutputDir.text().strip() or "."
        from src.task_package import next_available_filename, save_task_package
        ant_path = next_available_filename(output_dir, tpl_name)
        config_snapshot = {
            "test_mode": self._test_mode,
            "template_path": self.ui.editTemplatePath.text().strip(),
            "lag_singles": self._lag_config.singles_sorted,
            "lag_ranges": self._lag_config.ranges_sorted,
            "ar_singles": self._ar_lag_config.singles_sorted if hasattr(self, '_ar_lag_config') else [],
            "ar_ranges": self._ar_lag_config.ranges_sorted if hasattr(self, '_ar_lag_config') else [],
            "rhcp_singles": self._rhcp_lag_config.singles_sorted if hasattr(self, '_rhcp_lag_config') else [],
            "rhcp_ranges": self._rhcp_lag_config.ranges_sorted if hasattr(self, '_rhcp_lag_config') else [],
            "cpxpi_singles": self._cpxpi_lag_config.singles_sorted if hasattr(self, '_cpxpi_lag_config') else [],
            "cpxpi_ranges": self._cpxpi_lag_config.ranges_sorted if hasattr(self, '_cpxpi_lag_config') else [],
        }
        save_task_package(ant_path, tpl_name,
            data_file_paths=list(self._data_file_paths),
            template_path=self.ui.editTemplatePath.text().strip(),
            config_snapshot=config_snapshot)
        self._log(f"📦 任务包已保存: {Path(ant_path).name}")

    def _on_saveas_task_package(self):
        """另存任务包 — 选择路径保存。"""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("另存任务包"), "",
            self.tr("任务包 (*.ant);;所有文件 (*)"))
        if not path:
            return
        tpl_name = Path(path).stem
        from src.task_package import save_task_package
        config_snapshot = {
            "test_mode": self._test_mode,
            "template_path": self.ui.editTemplatePath.text().strip(),
            "lag_singles": self._lag_config.singles_sorted,
            "lag_ranges": self._lag_config.ranges_sorted,
            "ar_singles": self._ar_lag_config.singles_sorted if hasattr(self, '_ar_lag_config') else [],
            "ar_ranges": self._ar_lag_config.ranges_sorted if hasattr(self, '_ar_lag_config') else [],
            "rhcp_singles": self._rhcp_lag_config.singles_sorted if hasattr(self, '_rhcp_lag_config') else [],
            "rhcp_ranges": self._rhcp_lag_config.ranges_sorted if hasattr(self, '_rhcp_lag_config') else [],
            "cpxpi_singles": self._cpxpi_lag_config.singles_sorted if hasattr(self, '_cpxpi_lag_config') else [],
            "cpxpi_ranges": self._cpxpi_lag_config.ranges_sorted if hasattr(self, '_cpxpi_lag_config') else [],
        }
        save_task_package(path, tpl_name,
            data_file_paths=list(self._data_file_paths),
            template_path=self.ui.editTemplatePath.text().strip(),
            config_snapshot=config_snapshot)
        self._log(f"📦 任务包已保存: {Path(path).name}")

    def _on_print(self):
        """打印当前参数结果（调用系统打印机/PDF）。"""
        from PySide6.QtPrintSupport import QPrinter, QPrintDialog
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle(self.tr("打印"))
        if dlg.exec() != QDialog.Accepted:
            return
        # 打印日志内容
        self.ui.logOutput.print_(printer)

    def _on_help(self):
        from ui.dialogs import HelpDialog
        dlg = HelpDialog(self)
        dlg.exec()

    # ── 项目管理 ──

    def _on_project_manager(self):
        from ui.project_manager import ProjectManagerDialog
        dlg = ProjectManagerDialog(self)
        dlg.exec()

    def _on_project_import_json(self):
        from ui.project_manager import ImportFromJSONDialog
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择 EMQuest JSON 文件"), "",
            self.tr("JSON 文件 (*.json)"))
        if path:
            dlg = ImportFromJSONDialog(self, path)
            dlg.exec()

    def _on_refresh_recent_menu(self):
        self._menu_recent_projects.clear()
        try:
            from src.project_db import get_db
            db = get_db()
            tests = db.get_recent_tests(5)
            if not tests:
                self._menu_recent_projects.addAction(self.tr("(无)")).setEnabled(False)
            for t in tests:
                name = f"{t.get('customer_name','')} — {t.get('model','')} ({t.get('test_date','')[:10]})"
                action = self._menu_recent_projects.addAction(name)
                action.setData(t.get('id'))
                action.triggered.connect(lambda checked, tid=t.get('id'): self._on_open_recent(tid))
        except Exception:
            self._menu_recent_projects.addAction(self.tr("(数据库不可用)")).setEnabled(False)

    def _on_open_recent(self, tid: int):
        from src.project_db import get_db
        db = get_db()
        t = db.get_test_by_id(tid)
        if t:
            files = t.get('data_files', [])
            if files:
                self._data_file_paths = [f for f in files if Path(f).exists()]
            tpl = t.get('template_path', '')
            if tpl and Path(tpl).exists():
                self.ui.editTemplatePath.setText(tpl)
            out = t.get('output_dir', '')
            if out and Path(out).exists():
                self.ui.editOutputDir.setText(out)
            from src.config_manager import get_config_manager
            cfg = get_config_manager()
            cfg.config.metadata = t.get('metadata', {})
            cfg._dirty = True
            cfg._save()
            self._log(f"✓ 已加载项目: {t.get('customer_name')} — {t.get('model')}")

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

    def _on_tool_docx_sdt(self):
        """Docx SDT 工具箱: 分析 Word 模板，自动推荐 SDT tag，插入并保存。"""
        from ui.template_recognizer import DocxTemplateToolbox
        fp = getattr(self, '_file_settings_page', None)
        word_path = getattr(fp, '_edit_word_report_tpl', '') if fp else ''
        if not word_path:
            word_path = self.ui.editTemplatePath.text().strip() if hasattr(self, 'ui') else ""
        dlg = DocxTemplateToolbox(self, word_path if word_path and Path(word_path).exists() else "")
        dlg.exec()

    def _on_tool_metadata(self):
        """报告元数据编辑: 客户/项目/测试信息，支持 Excel 导入。"""
        fp = getattr(self, '_file_settings_page', None)
        if fp and hasattr(fp, '_show_metadata_editor'):
            fp._show_metadata_editor()

    def _on_tool_pattern_mgr(self):
        """列识别规则管理: 编辑 column_patterns.json。"""
        fp = getattr(self, '_file_settings_page', None)
        if fp and hasattr(fp, '_show_pattern_manager'):
            fp._show_pattern_manager()

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

    def _on_tool_xlsx_to_csv(self):
        """FinalSummary .xlsx → merged CSV 转换。一次转换，之后秒读。"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit
        from PySide6.QtWidgets import QFileDialog as FD, QGroupBox, QProgressBar

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("FinalSummary 转 CSV"))
        dlg.setMinimumWidth(500)
        layout = QVBoxLayout(dlg)

        # 源文件
        src_grp = QGroupBox(self.tr("源文件"))
        src_layout = QHBoxLayout(src_grp)
        src_edit = QLineEdit()
        src_edit.setReadOnly(True)
        src_edit.setPlaceholderText(self.tr("选择 FinalSummary .xlsx 文件"))
        src_btn = QPushButton(self.tr("浏览..."))
        src_layout.addWidget(src_edit)
        src_layout.addWidget(src_btn)
        layout.addWidget(src_grp)

        # 输出目录
        out_grp = QGroupBox(self.tr("输出"))
        out_layout = QHBoxLayout(out_grp)
        out_edit = QLineEdit()
        out_edit.setReadOnly(True)
        out_btn = QPushButton(self.tr("浏览..."))
        out_layout.addWidget(QLabel(self.tr("输出到:")))
        out_layout.addWidget(out_edit)
        out_layout.addWidget(out_btn)
        layout.addWidget(out_grp)

        # 进度
        prog = QProgressBar()
        prog.setVisible(False)
        layout.addWidget(prog)
        status_lbl = QLabel("")
        layout.addWidget(status_lbl)

        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton(self.tr("开始转换"))
        cancel_btn = QPushButton(self.tr("取消"))
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        def on_src():
            f, _ = FD.getOpenFileName(dlg, self.tr("选择 FinalSummary .xlsx"), "",
                                       self.tr("Excel (*.xlsx *.xls)"))
            if f:
                src_edit.setText(f)
                if not out_edit.text():
                    out_edit.setText(str(Path(f).parent))

        def on_out():
            d = FD.getExistingDirectory(dlg, self.tr("选择输出目录"))
            if d: out_edit.setText(d)

        src_btn.clicked.connect(on_src)
        out_btn.clicked.connect(on_out)

        def do_convert():
            src = src_edit.text().strip()
            out_dir = out_edit.text().strip()
            if not src or not out_dir:
                status_lbl.setText(self.tr("请选择源文件和输出目录"))
                return
            stem = Path(src).stem
            out_path = str(Path(out_dir) / f"{stem}_merged.csv")
            ok_btn.setEnabled(False)
            prog.setVisible(True)
            prog.setMaximum(0)  # indeterminate
            status_lbl.setText(self.tr("转换中..."))
            QApplication.processEvents()

            try:
                from src.fs_to_csv import convert_fs_to_csv
                t0 = time.time()
                out_path = convert_fs_to_csv(src,
                    progress_callback=lambda c, t, m: (
                        prog.setMaximum(t), prog.setValue(c),
                        status_lbl.setText(m), QApplication.processEvents()
                    ))
                sz = os.path.getsize(out_path)/1024/1024
                status_lbl.setText(self.tr(f"✅ 完成 ({sz:.0f} MB, {time.time()-t0:.0f}s)"))
                prog.setMaximum(1); prog.setValue(1)
            except Exception as e:
                status_lbl.setText(self.tr(f"❌ 失败: {e}"))
            finally:
                ok_btn.setEnabled(True)

        ok_btn.clicked.connect(do_convert)
        cancel_btn.clicked.connect(dlg.reject)
        dlg.exec()

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

    # ── 旧方法代理到 FileSettingsPage (保持向后兼容) ──

    def _on_add_data_files(self):
        p = getattr(self, '_file_settings_page', None)
        if p: p._on_add_data_files()

    def _on_clear_selected_files(self):
        p = getattr(self, '_file_settings_page', None)
        if p: p._on_clear_selected_files()

    def _on_clear_all_files(self):
        p = getattr(self, '_file_settings_page', None)
        if p: p._on_clear_all_files()

    def _sync_file_entries(self):
        """委托给 FileSettingsPage 同步文件条目并刷新天线选择器。"""
        fp = getattr(self, '_file_settings_page', None)
        if fp:
            fp._sync_file_entries()
        self._refresh_antenna_selector()

    def _refresh_data_file_ui(self):
        """委托给 FileSettingsPage 刷新文件列表 UI。"""
        fp = getattr(self, '_file_settings_page', None)
        if fp:
            fp._refresh_data_file_ui()

    def _on_file_mode_changed(self, row: int):
        """委托给 FileSettingsPage 处理文件模式变更。"""
        fp = getattr(self, '_file_settings_page', None)
        if fp:
            fp._on_file_mode_changed(row)

    def _on_naming_mode_changed(self, index: int):
        """工作表命名方式变更回调。"""
        self._worksheet_naming_mode = self._cmb_naming_mode.currentData() or 0
        # 命名方式变了，重建匹配表
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
                fp = getattr(self, '_file_settings_page', None)
                entries = fp._file_entries if fp else []
                for e in entries:
                    if e.path == m.file_path and e.test_mode == 0:
                        e.test_mode = inferred
        self._refresh_data_file_ui()

        matched = sum(1 for m in matches if m.file_path is not None)
        fp = getattr(self, '_file_settings_page', None)
        if fp and hasattr(fp, '_lbl_match_status') and fp._lbl_match_status is not None:
            fp._lbl_match_status.setText(
                f"✓ {matched}/{len(matches)} 个工作表已匹配"
            )
        self._log(f"自动匹配完成: {matched}/{len(matches)}")

    def _populate_match_table(self, matches):
        self._last_matches = matches
        matched = sum(1 for m in matches if m.file_path is not None)
        fp = getattr(self, '_file_settings_page', None)
        if fp and hasattr(fp, '_lbl_match_status') and fp._lbl_match_status is not None:
            fp._lbl_match_status.setText(f'{matched}/{len(matches)} done')
        fp = getattr(self, '_file_settings_page', None)
        if fp and hasattr(fp, '_populate_match_table'):
            fp._populate_match_table(matches)

    def _build_datasource_map(self, progress_callback=None):
        from src.datasource import DataSource
        from src.sheet_file_matcher import extract_key, sanitize_sheet_name
        result = {}

        total_files = max(len(self._data_file_paths), 1)
        file_idx = 0
        use_file_names = self._worksheet_naming_mode == 1

        # 防御: 清除不在 _data_file_paths 中的匹配表行 (陈旧数据保护)
        valid_paths = set(self._data_file_paths)
        for m in getattr(self, '_last_matches', []):
            fp = m.file_path or ""
            if combo:
                fp = combo.currentData() or ""
                if fp and fp != "—" and fp not in valid_paths:
                    # 此匹配表行引用了不存在于 _data_file_paths 的旧文件 → 重置
                    combo.setCurrentIndex(0)

        # 已匹配的行
        matched_files = set()
        for m in getattr(self, '_last_matches', []):
            template_sheet_name = m.sheet_name
            fp = m.file_path or ""
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
    @staticmethod
    def _auto_rename_if_exists(filepath: str) -> str:
        """如果文件已存在，自动添加 _NN 后缀避免覆盖（与 .ant 逻辑一致）。"""
        p = Path(filepath)
        if not p.exists():
            return filepath
        from datetime import date
        today = date.today().strftime("%Y%m%d")
        stem = p.stem
        ext = p.suffix
        parent = p.parent
        # 如果 stem 已包含日期后缀（如 name_20260628_01），去掉旧后缀重新编号
        import re
        m = re.search(r'_\d{8}_\d{2}$', stem)
        if m:
            stem = stem[:m.start()]
        new_stem = f"{stem}_{today}"
        seq = 1
        while True:
            new_name = f"{new_stem}_{seq:02d}{ext}"
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
        if not getattr(self, '_last_matches', None):
            return
        matched_files = set()
        for m in getattr(self, '_last_matches', []):
            fp = m.file_path or ""
            if fp and Path(fp).exists():
                matched_files.add(fp)
        unmatched = [f for f in self._data_file_paths if f not in matched_files]
        if not unmatched:
            return
        try:
            from src.llm_assist import LLMAssist
            sheet_names = [m.sheet_name for m in getattr(self, '_last_matches', [])]
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

        self.ui.btnStop.clicked.connect(self._on_stop)
        # btnStart 已在 _extract_execution_bar 中连接到 _on_preview

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
            if path.lower().endswith('.doc') and not path.lower().endswith('.docx'):
                QMessageBox.warning(self, self.tr("格式不支持"),
                    self.tr("不支持 .doc 格式。\n请用 Word 打开该文件，另存为 .docx 后再使用。"))
                return
            self.ui.editTemplatePath.setText(path)
            self._cfg.config.last_template_path = path
            self._cfg._dirty = True
            self._chart_config_required = None  # 模板已变，下次使用时重新检测
            self._cached_template_params = set()  # 强制刷新模板参数缓存
            # 自动应用模板检测到的计算参数
            self._auto_apply_template_params()
            # 立即从模板更新角度配置（不等自动匹配）
            try:
                from src.excel_reader import read_template
                sheets = read_template(path)
                self._auto_update_angle_config_from_template(sheets)
            except Exception:
                pass
            # 模板路径变更后，旧的匹配表基于旧模板的工作表名，无效
            fp = getattr(self, '_file_settings_page', None)
            if fp and hasattr(fp, '_lbl_match_status') and fp._lbl_match_status is not None:
                fp._lbl_match_status.setText("")
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
        from PySide6.QtWidgets import QLineEdit, QDialogButtonBox
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
        # 显示关联的 Word 模板 (如有)
        word_tpl = ""
        if hasattr(self, '_file_settings_page'):
            fp = self._file_settings_page
            if hasattr(fp, '_edit_word_report_tpl'):
                word_tpl = (fp._edit_word_report_tpl or "").strip()
        if word_tpl:
            word_lbl = QLabel(Path(word_tpl).name)
            word_lbl.setToolTip(word_tpl)
            form.addRow(self.tr("Word 模板:"), word_lbl)
        layout.addLayout(form)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)
        if dlg.exec() != QDialog.Accepted: return
        mfr = mfr_combo.currentText().strip()
        tpl_name = name_edit.text().strip()
        if not mfr or not tpl_name: return
        # 同时保存 Word 模板路径
        word_tpl = ""
        if hasattr(self, '_file_settings_page'):
            fp = self._file_settings_page
            if hasattr(fp, '_edit_word_report_tpl'):
                word_tpl = (fp._edit_word_report_tpl or "").strip()
        self._tm.add_template(mfr, tpl_name, template_path, output_dir, word_tpl)
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
        self._update_params_display()

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

        # RHCP 配置
        rhcp_cfg = LagConfig.from_rhcp_headers(all_headers)
        if not rhcp_cfg.is_empty():
            self._rhcp_lag_config = rhcp_cfg
            self._log(f"从模板自动更新 RHCP 角度: 单角度={rhcp_cfg.singles_sorted}")

        # CP-XPI 配置
        cpxpi_cfg = LagConfig.from_cpxpi_headers(all_headers)
        if not cpxpi_cfg.is_empty():
            self._cpxpi_lag_config = cpxpi_cfg
            self._log(f"从模板自动更新 CP-XPI 角度: 单角度={cpxpi_cfg.singles_sorted}")

        self._update_params_display()

    def _auto_apply_template_params(self):
        """从模板自动识别并应用计算参数到主窗口 + AntennaParamsPage。

        选择模板后自动调用，无需用户打开计算参数对话框。
        同步更新三个目标: _required_params, AntennaParamsPage checkbox, 执行栏显示。
        """
        tp = self._get_template_params()
        if not tp:
            return

        # 检查是否有变化
        if tp == self._required_params:
            return  # 没变化，不重复日志

        self._required_params = tp
        self._extra_params = set()

        # 同步到 AntennaParamsPage
        if hasattr(self, '_antenna_params_page') and self._antenna_params_page:
            self._antenna_params_page.set_template_params(tp)

        # 同步到当前天线配置
        ant = self._antenna_configs.get(self._current_antenna_name) if self._current_antenna_name else None
        if ant and not ant.required_params:
            ant.required_params = set(tp)

        # 自动推断图表配置
        from src.chart_config import auto_detect_charts
        auto_charts = auto_detect_charts(tp)
        if auto_charts:
            self._auto_apply_chart_config(auto_charts)

        self._update_params_display()

    def _auto_apply_chart_config(self, auto_charts: dict[str, bool]):
        """根据模板参数自动启用对应的图表 checkbox。"""
        if not hasattr(self, '_chart_settings_page') or not self._chart_settings_page:
            return
        cp = self._chart_settings_page
        for chart_key, enabled in auto_charts.items():
            if chart_key in cp._chart_required:
                cp._chart_required[chart_key].setChecked(enabled)
            if chart_key in cp._chart_extra:
                cp._chart_extra[chart_key].setChecked(enabled)
        cp._sync_to_mw()
        self._log(f"📊 从模板自动推断图表: {', '.join(auto_charts.keys())}")

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
            label.setStyleSheet("padding: 8px;")
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
        self._update_params_display()

    def _remove_single(self, angle: float):
        self._lag_config.remove_single(angle)
        self._sync_quick_buttons()
        self._update_lag_display()

    def _remove_range(self, lo: float, hi: float):
        self._lag_config.remove_range(lo, hi)
        self._update_lag_display()

    # ==================================================================
    # 运行控制 — 预览 / 出报告 / 停止 状态机
    # ==================================================================

    def _set_preview_state(self, state: int):
        """更新预览状态机并刷新按钮互锁。"""
        self._preview_state = state
        idle = state == self._PREVIEW_IDLE
        running = state == self._PREVIEWING or state == self._EXPORTING
        ready = state == self._READY
        self.ui.btnStart.setEnabled(idle)  # 仅 IDLE 可预览, READY 时禁用以防误点
        self._btn_export.setEnabled(ready)
        self._btn_one_click.setEnabled(idle or ready)
        self.ui.btnStop.setEnabled(running)

    def _enter_previewing(self):
        self._set_preview_state(self._PREVIEWING)
        self.ui.btnStart.setText(self.tr("⏳ 预览中..."))

    def _enter_exporting(self):
        self._set_preview_state(self._EXPORTING)
        self._btn_export.setText(self.tr("⏳ 报告中..."))

    def _enter_ready(self):
        self._running = False
        self._set_preview_state(self._READY)
        self.ui.btnStart.setText(self.tr("👁 预览"))

    def _enter_idle(self):
        self._running = False
        self._set_preview_state(self._PREVIEW_IDLE)
        self.ui.btnStart.setText(self.tr("👁 预览"))
        self._btn_export.setText(self.tr("📄 出报告"))

    def _staleness_check(self):
        """天线参数/LAG角度变更 → 强制重新预览。"""
        if self._preview_state == self._PREVIEWING:
            self._preview_dirty = True  # 运行时标记，worker 完成时检查
        elif self._preview_state == self._READY:
            self._enter_idle()
            self._log("📡 参数已变更，请重新预览")

    def _on_preview(self):
        """预览: compute_only=True，快速计算不导出。"""
        if self._preview_state == self._PREVIEWING or self._preview_state == self._EXPORTING:
            return
        self._cached_datasource_map = None  # 清除旧缓存
        self._enter_previewing()
        self._do_run(compute_only=True)

    def _on_export(self):
        """出报告: compute_only=False，复用预览的 datasource_map 避免重新加载。"""
        if self._preview_state != self._READY:
            QMessageBox.warning(self, self.tr("请先预览"),
                self.tr("请先点击「预览」确认计算结果，再出报告。"))
            return
        self._enter_exporting()
        self._do_run(compute_only=False, reuse_datasource=True)

    def _on_one_click(self):
        """一键出报告: 支持多天线逐个处理。"""
        self._save_current_antenna_config()
        if self._antenna_configs and len(self._antenna_configs) > 1:
            # 多天线模式: 逐个处理
            self._log(f"🚀 多天线处理: {len(self._antenna_configs)} 个天线")
            self._process_antennas_sequential()
        else:
            # 单天线模式
            self._enter_exporting()
            self._do_run(compute_only=False, reuse_datasource=False)

    def _process_antennas_sequential(self):
        """逐个串行处理所有天线。"""
        self._enter_exporting()
        ant_names = list(self._antenna_configs.keys())
        self._ant_queue = ant_names[:]
        self._ant_idx = 0
        self._ant_all_results = {}
        self._ant_all_images = {}
        self._process_next_antenna()

    def _process_next_antenna(self):
        """处理队列中的下一个天线。"""
        if self._ant_idx >= len(self._ant_queue):
            # 全部完成
            self._log(f"✅ 全部天线处理完成: {len(self._ant_all_results)} 个")
            self._antenna_results = self._ant_all_results
            self._antenna_images = self._ant_all_images
            return
        name = self._ant_queue[self._ant_idx]
        self._log(f"📡 处理天线: {name} ({self._ant_idx + 1}/{len(self._ant_queue)})")
        self._load_antenna_config(name)
        self._current_antenna_name = name
        self._ant_idx += 1
        self._do_run(compute_only=False, reuse_datasource=False)
        # _on_finished 会收集结果并调用 _process_next_antenna 继续

    def _do_run(self, compute_only: bool = False, reuse_datasource: bool = False):
        """统一执行入口（预览/出报告共用）。"""
        self._on_start(compute_only=compute_only, reuse_datasource=reuse_datasource)

    def _on_start(self, compute_only: bool = False, reuse_datasource: bool = False):
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

        # 自动触发匹配 (如果尚未匹配)
        file_page = getattr(self, '_file_settings_page', None)
        if not getattr(self, '_last_matches', None) and self._data_file_paths:
            try:
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

        # ── 输出选项 ──
        file_page = getattr(self, '_file_settings_page', None)
        out_excel = True
        out_word = False
        out_data = False
        if file_page and hasattr(file_page, 'get_output_flags'):
            out_excel, out_word, out_data = file_page.get_output_flags()
        # 有图表配置 → 自动开启 Word 输出
        if not out_word and getattr(self, '_chart_instances', None):
            out_word = True
            if file_page and hasattr(file_page, '_check_out_word'):
                file_page._check_out_word.setChecked(True)
        # 同步 Word 输出路径: _edit_word → azimuth_config
        if out_word and file_page and hasattr(file_page, '_sync_azimuth_state'):
            file_page._sync_azimuth_state()

        if not out_excel and not out_word and not out_data:
            self._restore_start_button()
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("请至少选择一种输出类型 (天线参数/图表/中间数据)。"))
            return

        template_path = self.ui.editTemplatePath.text().strip()
        output_dir = self.ui.editOutputDir.text().strip() or str(Path.cwd() / "output")
        output_name = self.ui.editOutputName.text().strip() or "antenna_report.xlsx"
        output_name = output_name.replace("\\", "").replace("/", "")

        if out_excel and not template_path:
            self._restore_start_button()
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("请选择模板 Excel 文件。"))
            return
        if out_excel and not Path(template_path).exists():
            self._restore_start_button()
            QMessageBox.warning(self, self.tr("警告"),
                self.tr("模板文件不存在"))
            return
        if out_excel:
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
        output_path = str(Path(output_dir) / output_name) if out_excel else ""
        output_path = self._auto_rename_if_exists(output_path) if output_path else ""

        # 完整报告: 参数 → Excel, 图表 → Word (覆盖独立输出设置)
        full_report_enabled = False
        if file_page and hasattr(file_page, '_check_full_report'):
            full_report_enabled = file_page._check_full_report.isChecked()
        else:
            full_report_enabled = self.ui.checkFullReport.isChecked()

        if full_report_enabled:
            out_excel = True
            out_word = True
            # Word 图表路径: 从 FileSettingsPage 读取
            if file_page and hasattr(file_page, '_edit_full_graph'):
                fg_path = file_page._edit_full_graph.text().strip()
                if fg_path and hasattr(self, '_azimuth_config') and self._azimuth_config:
                    self._azimuth_config.chart_output_filename = Path(fg_path).name
                    self._azimuth_config.chart_output_dir = str(Path(fg_path).parent)
            output_path = self._auto_rename_if_exists(output_path)
            full_report_path = None  # 不再生成旧的综合 Excel

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
        if reuse_datasource and getattr(self, '_cached_datasource_map', None):
            datasource_map = self._cached_datasource_map
            self.ui.progressBar.setMaximum(1); self.ui.progressBar.setValue(1)
            self.ui.lblProgressMsg.setText(self.tr("✅ 复用已加载数据"))
        else:
            self.ui.progressBar.setRange(0, 100)
            self.ui.progressBar.setValue(5)
            self.ui.lblProgressMsg.setText(self.tr("正在打开数据文件..."))
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
            self._cached_datasource_map = datasource_map  # 缓存供导出复用
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
        # 切面角度默认从 Gain 角度配置读取 (统一)
        if hasattr(self, '_lag_config') and not full_chart_config.cut_2d_phi_angles:
            full_chart_config.cut_2d_phi_angles = self._lag_config.singles_sorted
        if self._chart_config_required is not None or self._chart_config_extra is not None:
            req = self._chart_config_required or ChartConfig()
            xtr = self._chart_config_extra or ChartConfig()
            full_chart_config = req.merge(xtr)
        png_dir = plot_config.save_png_folder
        full_chart_config.save_png_folder = png_dir

        # ── 方位面配置：默认路径 + 角度自动加载 ──
        if hasattr(self, '_azimuth_config') and self._azimuth_config is not None:
            az = self._azimuth_config
            # 默认路径：从第一个源文件推导（不管是否启用 azimuth, Word 输出需要路径）
            first_path = self._data_file_paths[0] if self._data_file_paths else ""
            if first_path:
                p = Path(first_path)
                src_dir = str(p.parent)
                src_stem = p.stem
                if not az.chart_output_dir:
                    az.chart_output_dir = src_dir
                if not az.chart_output_filename:
                    az.chart_output_filename = f"{src_stem}图表报告.docx"
                if not az.data_output_dir:
                    az.data_output_dir = src_dir
                if not az.data_output_filename:
                    az.data_output_filename = f"{src_stem}_中间数据.xlsx"
            # 角度自动加载 (仅首次，之后用户手动管理)
                if not az._angles_initialized:
                    gain_singles = self._lag_config.singles_sorted
                    ar_singles = (self._ar_lag_config.singles_sorted
                                  if hasattr(self, '_ar_lag_config') else gain_singles)
                    # 包装为图表列表格式: 每个图表一个角度列表
                    az.azimuth_cut_angles = [list(gain_singles)] if gain_singles else [[]]
                    az.azimuth_cut_angles_ar = [list(ar_singles)] if ar_singles else [[]]
                    if not az.azimuth_cut_angles_ar:
                        az.azimuth_cut_angles_ar = list(self._lag_config.singles_sorted)
                    az._angles_initialized = True

        # 从 MainWindow widget 读取（天线参数 dialog 通过 _sync_to_mw 写入此处）
        extrapolate_theta = self._cmb_extrapolate.currentData()
        dir_extrap = getattr(self, '_dir_extrap_method', 'linear')
        freq_source = self._cmb_freq_source.currentData() or "datasource"
        trim_start = self._spin_trim_start.value()
        trim_end = self._spin_trim_end.value()
        robust_peak = self._check_robust_peak.isChecked()
        # 步进参数（从 inline AntennaParamsPage 读取）
        ant_page = getattr(self, '_antenna_params_page', None)
        step_values = ant_page.get_selected_steps() if ant_page else []
        skip_original = ant_page.get_skip_original() if ant_page else False
        gen_diff = ant_page.get_gen_diff() if ant_page else False
        gen_diff_chart = ant_page.get_gen_diff_chart() if ant_page else False

        self._worker = ProcessingWorker(
            datasource_map=datasource_map,
            sheet_mode_map=sheet_mode_map,
            template_path=template_path,
            output_path=output_path,
            lag_config=self._lag_config,
            plot_config=plot_config,
            full_report_path=full_report_path,
            theta_extrap_method=extrapolate_theta,
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
            azimuth_config=getattr(self, '_azimuth_config', None),  # 始终传递(含输出路径)
            out_excel=out_excel,
            out_word=out_word,
            out_data=out_data,
            compute_only=compute_only,
            dir_extrap_method=dir_extrap,
            # 多步进参数
            step_values=step_values,
            skip_original=skip_original,
            gen_diff=gen_diff,
            gen_diff_chart=gen_diff_chart,
            antenna_configs=self._antenna_configs if self._antenna_configs else None,
            chart_instances=getattr(self, '_chart_instances', None),
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
        """恢复按钮到空闲状态（向后兼容，内部委托 _enter_idle）。"""
        self._enter_idle()

    def _enter_busy(self, text="⏳ 处理中..."):
        """进入忙碌状态：锁定预览按钮，防止主计算与工具操作并发。"""
        self._running = True
        self.ui.btnStart.setEnabled(False)
        self._btn_export.setEnabled(False)
        self.ui.btnStop.setEnabled(True)

    def _exit_busy(self):
        """退出忙碌状态：恢复预览按钮。_btn_export 由状态机管理。"""
        self._running = False
        self.ui.btnStart.setText(self.tr("👁 预览"))
        self.ui.btnStart.setEnabled(True)
        self.ui.btnStop.setEnabled(False)
        # _btn_export 不由这里管 — 状态机(_enter_ready/_enter_idle)负责

    def _on_progress(self, current: int, total: int, message: str):
        self.ui.progressBar.setMaximum(total)
        self.ui.progressBar.setValue(current)
        pct = int(current / max(total, 1) * 100)
        self.ui.lblProgressMsg.setText(f"[{pct}%] {message}")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

    def _on_worker_log(self, message: str):
        self._log(message)

    def _on_finished(self, results, images):
        # 防 QThread.finished 二次发射: 非运行态直接 return
        if self._preview_state not in (self._PREVIEWING, self._EXPORTING):
            return
        self.ui.progressBar.setValue(self.ui.progressBar.maximum())
        self.ui.lblProgressMsg.setText("✅ 完成")
        self._running = False
        self._worker = None
        self._data_stale = True  # 计算完成，数据变为陈旧
        # 安全退出线程：quit() 退出事件循环，wait(3000) 等待线程结束
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
        total_rows = sum(len(v) for v in results.values())
        total_imgs = sum(len(v) for v in images.values())
        self._log(f"\n{'='*50}")
        self._log(f"✓ 全部完成! 共 {len(results)} 个工作表, {total_rows} 行数据")
        if total_imgs:
            self._log(f"  生成 {total_imgs} 张 3D 方向图")

        # 保存 .ant 任务包（在进度条置为完成前执行）
        file_page = getattr(self, '_file_settings_page', None)
        if file_page and getattr(file_page, '_check_save_task', None) and file_page._check_save_task.isChecked():
            self.ui.lblProgressMsg.setText(self.tr("📦 正在打包任务包..."))
            self.ui.progressBar.setMaximum(100)
            self.ui.progressBar.setValue(70)
            QApplication.processEvents()
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
                    "extrapolate": self._cmb_extrapolate.currentData() if hasattr(self, '_cmb_extrapolate') else None,
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

        # 状态机: 预览完成→READY (除非中途参数变更), 出报告完成→IDLE
        if self._preview_state == self._PREVIEWING:
            if self._preview_dirty:
                self._preview_dirty = False
                self._enter_idle()
                self._log("⚠ 预览期间参数已变更，数据已过时，请重新预览")
            else:
                self._enter_ready()
        else:
            self._enter_idle()
        self.ui.progressBar.setValue(100)
        self.ui.lblProgressMsg.setText(self.tr("✓ 处理完成"))
        self._update_status()

        # 按天线名存储结果
        ant_name = self._current_antenna_name or "默认天线"
        self._antenna_results[ant_name] = results
        self._antenna_images[ant_name] = images

        # 填充参数结果表 (当前天线)
        self._populate_results_table(results, ant_name)
        # 生成图形展示
        self._populate_charts(results)
        # 更新图形查看器模式标签 + 天线列表
        if self._graph_viewer:
            self._graph_viewer.update_mode_display()
            self._graph_viewer.set_antenna_list(list(self._antenna_results.keys()),
                                                ant_name)
        # 生成图形数据表
        self._populate_graph_data(results)
        # ── Word 模板填充 ──
        if file_page and hasattr(file_page, '_edit_word_report_tpl'):
            word_tpl = (file_page._edit_word_report_tpl or "").strip()
            if word_tpl and Path(word_tpl).exists() and results:
                try:
                    self.ui.lblProgressMsg.setText(self.tr("📝 正在填充 Word 模板..."))
                    QApplication.processEvents()
                    self._fill_docx_template(word_tpl, results, images, file_page)
                except Exception as e:
                    self._log(f"⚠ Word 模板填充失败: {e}")

        # 自动切到结果Tab
        self.ui.tabConfig.setCurrentIndex(0)

        # 多天线模式: 继续处理下一个
        if hasattr(self, '_ant_queue') and self._ant_idx < len(self._ant_queue):
            self._ant_all_results[ant_name] = results
            self._ant_all_images[ant_name] = images
            QTimer.singleShot(500, self._process_next_antenna)
            return

        # 全部完成，恢复状态
        if hasattr(self, '_ant_all_results') and self._ant_all_results:
            self._antenna_results = self._ant_all_results
            self._antenna_images = self._ant_all_images
            self._ant_queue = []

    def _process_antennas_parallel(self, antennas):
        """并行处理多个天线 (自动检测 CPU 核数)。"""
        import os
        from concurrent.futures import ThreadPoolExecutor, as_completed
        n_cpu = os.cpu_count() or 4
        workers = 1 if n_cpu <= 4 else (2 if n_cpu <= 8 else min(len(antennas), n_cpu // 2))
        self._log(f"  并行处理: {workers} 线程 (CPU={n_cpu}核)")
        results = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._run_single_antenna, ant): ant for ant in antennas if ant.data_files}
            for f in as_completed(futures):
                ant = futures[f]
                try:
                    r, imgs = f.result()
                    results[ant.name] = (r, imgs)
                    self._log(f"  \u2713 {ant.name}: {sum(len(v) for v in r.values())} rows")
                except Exception as e:
                    self._log(f"  \u2717 {ant.name}: {e}")
        return results

    def _run_single_antenna(self, ant):
        """运行单个天线的管线计算。"""
        from src.datasource import DataSource
        from src.pipeline import run_pipeline
        from src.graph_data import extract_graph_data
        from src.renderer import MatplotlibRenderer
        results = {}
        images = {}
        for fp in ant.data_files:
            if not Path(fp).exists():
                continue
            ds = DataSource.from_path(fp)
            res = run_pipeline(
                datasource=ds,
                template_path=self.ui.editTemplatePath.text().strip() or "/tmp/minimal_template.xlsx",
                output_path="/tmp/dummy.xlsx",
                lag_config_override=ant.lag_config if not ant.lag_config.is_empty() else self._lag_config,
                ar_lag_config_override=ant.ar_lag_config if not ant.ar_lag_config.is_empty() else self._ar_lag_config,
                theta_extrap_method=getattr(self, '_cmb_extrapolate', None) and self._cmb_extrapolate.currentData() if hasattr(self, '_cmb_extrapolate') else None,
                compute_only=True,
            )
            results.update(res)
            # 生成前几频点图
            gd = extract_graph_data(res, step_deg=5.0)
            renderer = MatplotlibRenderer()
            for freq, d in sorted(gd.items())[:3]:
                gain = d.get("gain_db")
                theta = d.get("theta")
                phi = d.get("phi")
                if gain is not None and theta is not None:
                    buf = renderer.render_3d_pattern(theta, phi, gain, freq, elev=30, azim=-60, dpi=60, title="Gain")
                    images.setdefault(ant.name, []).append((f"gain_{freq:.0f}", buf.getvalue()))
        return results, images


    def _fill_docx_template(self, template_path: str, results: dict, images: dict,
                             file_page=None):
        """使用 SDT Tag 填充 Word 模板。"""
        from src.docx_exporter import DocxTemplateFiller

        filler = DocxTemplateFiller(template_path)
        tags = filler.list_tags()
        self._log(f"  Word 模板: {len(tags)} 个 SDT tag")

        # ── 多天线模式 ──
        multi_cfg = getattr(self, '_multi_antenna_config', None)
        if multi_cfg and multi_cfg.antennas and len(multi_cfg.antennas) > 1:
            for ant in multi_cfg.antennas:
                sfx = ant.sdt_suffix
                ant_results = results.get(ant.name, {})
                if not ant_results:
                    continue
                # 数据表
                for tag in tags:
                    if tag.startswith("table_data") and (not sfx or sfx in tag):
                        try: filler.auto_fill_table(tag, ant_results)
                        except Exception as e: self._log(f"  \u26a0 {tag}: {e}")
                # 图片
                imgs_for_tag = [t for t in tags if t.startswith("img_") and sfx in t]
                all_imgs = []
                for ilist in images.values():
                    if isinstance(ilist, list): all_imgs.extend(ilist)
                for i, t in enumerate(imgs_for_tag):
                    if i < len(all_imgs):
                        try: filler.fill_image(t, all_imgs[i][1], width_cm=8.0)
                        except Exception: pass
            return

        # ── 元数据 ──
        from src.config_manager import get_config_manager
        cfg = get_config_manager()
        metadata = getattr(cfg.config, 'metadata', {}) or {}
        meta_tags = {
            'meta_customer': metadata.get('customer', ''),
            'meta_project': metadata.get('project', ''),
            'meta_contract_no': metadata.get('contract_no', ''),
            'meta_antenna_model': metadata.get('antenna_model', ''),
            'meta_report_no': metadata.get('report_no', ''),
            'meta_test_standard': metadata.get('test_standard', ''),
            'meta_test_lab': metadata.get('test_lab', ''),
            'meta_test_lab_addr': metadata.get('test_lab_addr', ''),
            'meta_test_engineer': metadata.get('test_engineer', ''),
            'meta_reviewer': metadata.get('reviewer', ''),
            'meta_test_start_date': metadata.get('test_start_date', ''),
            'meta_test_end_date': metadata.get('test_end_date', ''),
            'meta_test_plan_no': metadata.get('test_plan_no', ''),
            'meta_test_plan_ver': metadata.get('test_plan_ver', ''),
            'meta_notes': metadata.get('notes', ''),
        }
        filler.fill_batch(meta_tags)

        # ── 数据表 ──
        for tag in tags:
            if tag.startswith("table_"):
                filler.auto_fill_table(tag, results)

        # ── 单值 ──
        flat_data = {}
        for sheet_results in results.values():
            for row in sheet_results:
                for key, val in row.items():
                    if key.startswith("_") or isinstance(val, (list, dict)):
                        continue
                    flat_data[f"data_{key}"] = val
        filler.fill_batch(flat_data)

        # ── 图片 ──
        img_tags = [t for t in tags if t.startswith("img_")]
        all_images = []
        for img_list in images.values():
            all_images.extend(img_list)
        for i, (title, img_bytes) in enumerate(all_images):
            if i < len(img_tags):
                try:
                    filler.fill_image(img_tags[i], img_bytes, width_cm=8.0)
                except Exception:
                    pass

        # ── 保存 ──
        output_dir = self.ui.editOutputDir.text().strip() or "."
        src_stem = Path(self._data_file_paths[0]).stem if self._data_file_paths else "report"
        out_path = str(Path(output_dir) / f"{src_stem}_测试报告.docx")
        filler.save(out_path)
        self._log(f"  ✓ Word 报告已生成: {Path(out_path).name}")
        if filler.warn_count():
            self._log(f"  ⚠ {filler.warn_count()} 个 tag 未填充")

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

    def _populate_results_table(self, results, antenna_name: str = ""):
        """填充参数结果表格。"""
        vtab = self.ui.vTabResults
        # 清除旧内容
        while vtab.count():
            item = vtab.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        # ── 顶栏: 天线选择 + 数据层选择 + 联动 checkbox ──
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("<b>" + self.tr("天线:") + "</b>"))
        cmb_ant = QComboBox()
        cmb_ant.setMinimumWidth(120)
        ant_names = list(self._antenna_results.keys())
        for an in ant_names:
            cmb_ant.addItem(an)
        if antenna_name:
            idx = cmb_ant.findText(antenna_name)
            if idx >= 0: cmb_ant.setCurrentIndex(idx)
        cmb_ant.currentIndexChanged.connect(
            lambda i: self._show_antenna_results(cmb_ant.itemText(i)))
        top_row.addWidget(cmb_ant)

        top_row.addWidget(QLabel(self.tr("  数据层:")))
        cmb_layer = QComboBox()
        cmb_layer.addItem(self.tr("最终参数"))
        cmb_layer.addItem(self.tr("中间数据"))
        cmb_layer.addItem(self.tr("原始数据 (TODO)"))
        top_row.addWidget(cmb_layer)

        check_link = QCheckBox(self.tr("☑ 联动"))
        check_link.setChecked(True)
        check_link.setToolTip(self.tr("跟随主天线选择器"))
        top_row.addWidget(check_link)
        top_row.addStretch()

        vtab.addLayout(top_row)
        # 存储引用供联动使用
        self._results_ant_combo = cmb_ant
        self._results_link_check = check_link

        if not results:
            vtab.addWidget(QLabel(self.tr("  (暂无计算结果 — 请先预览)")))
            return
        # 取第一个 sheet 的数据
        first_sheet = next(iter(results.values()))
        if not first_sheet:
            vtab.addWidget(QLabel(self.tr("  (无数据)")))
            return
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

    def _show_antenna_results(self, antenna_name: str):
        """切换显示指定天线的计算结果。"""
        results = self._antenna_results.get(antenna_name)
        if results:
            self._populate_results_table(results, antenna_name)

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
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
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

    def _update_params_display(self):
        """刷新执行栏左侧天线参数面板（实时更新，不累积）。"""
        if not hasattr(self, '_params_display') or not self._params_display:
            return
        mode_names = {0: "📡 无源", 1: "📶 TRP", 2: "📻 TIS"}
        mode_str = mode_names.get(self._test_mode, "?")
        freq = self._cmb_freq_source.currentText() if hasattr(self, '_cmb_freq_source') else "—"
        extrap = self._cmb_extrapolate.currentText() if hasattr(self, '_cmb_extrapolate') else "不外推"
        robust = hasattr(self, '_check_robust_peak') and self._check_robust_peak.isChecked()

        # ── 上方参数面板 ──
        lines = []

        # 显示具体参数名（按当前测试模式过滤）
        all_params = getattr(self, '_required_params', set()) | getattr(self, '_extra_params', set())
        # 模式过滤: 无源不显示 TRP/TIS 专有参数
        passive_only = {"gain", "lag_single", "lag_range", "directivity", "efficiency_pct",
                        "efficiency_db", "total_efficiency_pct", "mismatch_loss_db",
                        "ar_single", "ar_range", "boresight_theta", "boresight_phi",
                        "max_power", "min_power", "avg_gain", "avg_power",
                        "xpi_boresight", "xpi_mean", "xpi_min",
                        "pc_theta_mm", "pc_phi_mm", "peak_eirp"}
        trp_only = {"trp", "nhprp_45", "nhprp_30", "nhprp_225", "uh_prp", "lh_prp"}
        tis_only = {"tis"}
        mode_filter = passive_only
        if self._test_mode == 1:
            mode_filter = passive_only | trp_only
        elif self._test_mode == 2:
            mode_filter = passive_only | tis_only | trp_only
        checked = sorted(k for k in all_params if k in mode_filter)
        if checked:
            from src.ui_utils import _get_param_labels
            labels = _get_param_labels()
            param_names = [labels.get(k, k) for k in checked]
            lines.append(f"<b>参数:</b> {', '.join(param_names)}")
        else:
            lines.append("<b>参数:</b> <span style='color:#888;'>(未选择)</span>")

        # 角度显示: 从 ANGLE_TYPE_CONFIG 读取，与右边面板共用同一数据源
        from src.ui_utils import ANGLE_TYPE_CONFIG
        for info in ANGLE_TYPE_CONFIG.values():
            cfg = getattr(self, info.attr, None)
            if cfg is None:
                continue
            singles = cfg.singles_sorted
            ranges = cfg.ranges_sorted
            if singles or ranges:
                parts = [f"{a}°" for a in singles]
                parts += [f"({lo}–{hi}°)" for lo, hi in ranges]
                lines.append(f"<b>{info.label}:</b> {', '.join(parts)}")
        algo = []
        if extrap: algo.append("外推")
        if robust: algo.append("Robust")
        if algo: lines.append(f"<b>算法:</b> {', '.join(algo)}")

        self._params_display.setHtml("<br>".join(lines))

        # ── 按钮行左对齐: 模式 ──
        if hasattr(self, '_mode_freq_label') and self._mode_freq_label:
            self._mode_freq_label.setText(f"{mode_str}")
    def _update_status(self):
        """更新状态栏 — 显示模式 + Gain/AR 角度配置概要。"""
        mode_names = {0: "📡 无源", 1: "📶 TRP", 2: "📻 TIS"}
        mode_str = mode_names.get(self._test_mode, "?")
        parts = [mode_str]
        gain_singles = len(self._lag_config.singles_sorted)
        gain_ranges = len(self._lag_config.ranges_sorted)
        ar_cfg = getattr(self, '_ar_lag_config', None)
        ar_singles = len(ar_cfg.singles_sorted) if ar_cfg else 0
        ar_ranges = len(ar_cfg.ranges_sorted) if ar_cfg else 0
        if gain_singles or gain_ranges:
            parts.append(f"Gain: {gain_singles}单+{gain_ranges}范围")
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
                fp = getattr(self, '_file_settings_page', None)
                if fp: fp._file_entries.clear()
                self._file_list_widget.setRowCount(0)
                if fp and hasattr(fp, '_lbl_match_status') and fp._lbl_match_status is not None:
                    fp._lbl_match_status.setText("")
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
