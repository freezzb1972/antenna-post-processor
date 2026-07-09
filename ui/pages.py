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
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.file_entry import FileEntry, mode_name, infer_mode_from_sheet
from src.lag_config import LagConfig
from src.output_config import OutputConfig
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

    Word 模板路径存为内部属性 (非 GUI widget)，供 preset 和出报告使用。
    """

    _edit_word_report_tpl = ""  # 内部属性: str, 存储 Word 报告模版路径

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
        left_layout.setSpacing(1)

        v_splitter = QSplitter(Qt.Vertical)
        v_splitter.setHandleWidth(4)  # 可拖拽分割线

        # Excel + Word 模版并列
        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(4)

        # Excel 模版组
        self.excel_grp = QGroupBox(self.tr("Excel 参数模版"))
        excel_layout = QVBoxLayout(self.excel_grp)
        excel_layout.setContentsMargins(2, 0, 2, 0)
        excel_layout.setSpacing(0)
        self._tpl_row = TemplateSourceRow(
            on_browse=self._on_browse_template,
            on_preview=self._on_preview_report,
        )
        if self._mw and hasattr(self._mw, '_tm'):
            presets = self._mw._tm.get_all_templates()
            presets_list = []
            for t in presets:
                presets_list.append({"manufacturer": t.manufacturer, "name": t.name, "path": t.path,
                    "word_template_path": t.word_template_path})
            self._tpl_row.populate_presets(presets_list)
        self._tpl_row.template_changed.connect(self._on_preset_template_selected)
        excel_layout.addWidget(self._tpl_row)
        self._tpl_path_label = QLineEdit()
        self._tpl_row.template_changed.connect(self._tpl_path_label.setText)
        self._tpl_path_label.setReadOnly(True)
        self._tpl_path_label.setPlaceholderText(self.tr("(未选择 Excel 参数模版)"))
        self._tpl_path_label.setFixedHeight(20)
        excel_layout.addWidget(self._tpl_path_label)
        tpl_row.addWidget(self.excel_grp, 1)

        # Word 报告模版组
        self.word_grp = QGroupBox(self.tr("Word 报告模版"))
        self.word_grp.setStyleSheet("QGroupBox { padding-top: 4px; padding-bottom: 1px; margin-top: 14px; }")
        word_layout = QVBoxLayout(self.word_grp)
        word_layout.setContentsMargins(2, 0, 2, 0)
        word_layout.setSpacing(0)
        self._word_tpl_row = TemplateSourceRow(
            on_browse=self._on_browse_word_template,
            on_preview=self._on_preview_word,
        )
        if self._mw and hasattr(self._mw, '_tm'):
            self._word_tpl_row.populate_presets(self._mw._tm.get_all_templates())
        self._word_tpl_row.template_changed.connect(self._on_word_tpl_path_set)
        self._word_tpl_row.template_pair_changed.connect(self._on_word_preset_excel_load)
        word_layout.addWidget(self._word_tpl_row)
        self._edit_word_tpl_widget = QLineEdit()
        self._edit_word_tpl_widget.setReadOnly(True)
        self._edit_word_tpl_widget.setPlaceholderText(self.tr("(未选择 Word 报告模版)"))
        self._edit_word_tpl_widget.setFixedHeight(20)
        self._word_tpl_row.template_changed.connect(self._edit_word_tpl_widget.setText)
        word_layout.addWidget(self._edit_word_tpl_widget)
        tpl_row.addWidget(self.word_grp, 1)

        # 模板行打包到一个 widget 加入垂直 splitter
        tpl_widget = QWidget()
        tpl_widget.setLayout(tpl_row)
        tpl_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        v_splitter.addWidget(tpl_widget)

        # 数据文件选择器 (widgets.DataFileSelector)
        from ui.widgets import DataFileSelector
        self._data_sel = DataFileSelector()
        ds = self._data_sel
        ds.btn_add_files.clicked.connect(self._on_add_data_files)
        ds.btn_clear_selected.clicked.connect(self._on_clear_selected_files)
        ds.btn_clear_all.clicked.connect(self._on_clear_all_files)
        ds.btn_auto_match.clicked.connect(self._on_auto_match)
        ds.cmb_naming_mode.currentIndexChanged.connect(self._on_naming_mode_changed)

        # 多天线确认按钮
        ds.btn_multi_antenna = QPushButton(self.tr("📡 多天线确认..."))
        ds.btn_multi_antenna.setToolTip(self.tr("为多个源文件配置天线标识/图表参数/Word模板"))
        ds.btn_multi_antenna.clicked.connect(self._on_multi_antenna_confirm)
        ds.btn_multi_antenna.setVisible(False)
        # 添加到 DataFileSelector 的主 layout 末尾
        ds.layout().addWidget(ds.btn_multi_antenna)

        # 公开属性别名 (保持旧代码兼容)
        self._btn_add_files = ds.btn_add_files
        self._btn_clear_selected = ds.btn_clear_selected
        self._btn_clear_all = ds.btn_clear_all
        self._file_list_widget = ds.file_list_widget
        self._btn_auto_match = ds.btn_auto_match
        self._lbl_match_status = ds.lbl_match_status
        self._lbl_naming_mode = ds.lbl_naming_mode
        self._cmb_naming_mode = ds.cmb_naming_mode

        v_splitter.addWidget(ds)
        v_splitter.setStretchFactor(0, 0)  # 模板区不拉伸
        v_splitter.setStretchFactor(1, 1)  # 数据文件区可拉伸
        v_splitter.setSizes([60, 500])     # 模板区贴内容, 数据区撑满
        left_layout.addWidget(v_splitter)
        h_splitter.addWidget(left_widget)

        # === 右侧：输出设置 ===
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 8, 0)
        right_layout.setSpacing(1)

        # ── 输出选项 ──
        out_grp = QGroupBox(self.tr("输出设置"))
        out_layout = QVBoxLayout(out_grp)
        out_layout.setContentsMargins(4, 0, 4, 0)
        out_layout.setSpacing(0)

        def _make_block_sep():
            """分隔块: 匹配当前主题的细线。"""
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setFrameShadow(QFrame.Sunken)
            sep.setStyleSheet("QFrame { color: palette(mid); margin: 6px 0; }")
            return sep

        def _default_output_dir() -> str:
            """从第一个数据源文件推导 output 子目录。"""
            mw = getattr(self, '_mw', None)
            files = getattr(mw, '_data_file_paths', []) if mw else []
            if files:
                d = Path(files[0]).parent / "output"
                return str(d)
            return str(Path.cwd() / "output")

        def _make_two_line_output(check, edit, btn, parent_layout):
            """统一的两行布局: checkbox 行 + 路径/浏览 行。check 可为 None。"""
            # 行1: checkbox (可为 None → 跳过)
            if check is not None:
                row1 = QHBoxLayout()
                row1.addWidget(check)
                row1.addStretch()
                parent_layout.addLayout(row1)
            # 行2: 路径 + 浏览
            row2 = QHBoxLayout()
            row2.setContentsMargins(10, 0, 0, 0)  # 缩进区分
            row2.addWidget(edit, 1)
            row2.addWidget(btn)
            parent_layout.addLayout(row2)

        # ── 1) 天线参数报告 (.xlsx) ──
        self._check_out_excel = QCheckBox(self.tr("天线参数报告 (.xlsx)"))
        self._check_out_excel.setChecked(False)
        self._edit_xlsx = QLineEdit()
        self._edit_xlsx.setPlaceholderText(self.tr("选择输出路径..."))
        btn_xl = QPushButton(self.tr("浏览..."))
        btn_xl.clicked.connect(self._on_browse_xlsx)
        _make_two_line_output(self._check_out_excel, self._edit_xlsx, btn_xl, out_layout)
        self._check_out_excel.toggled.connect(lambda c: self._edit_xlsx.setEnabled(c))
        out_layout.addWidget(_make_block_sep())

        # ── 2) 图表报告 (.docx) ──
        self._check_out_word = QCheckBox(self.tr("测试报告 (.docx)"))
        self._edit_word = QLineEdit()
        self._edit_word.setPlaceholderText(self.tr("选择输出路径..."))
        btn_wd = QPushButton(self.tr("浏览..."))
        btn_wd.clicked.connect(self._on_browse_word)
        _make_two_line_output(self._check_out_word, self._edit_word, btn_wd, out_layout)
        self._check_out_word.toggled.connect(lambda c: (
            self._edit_word.setEnabled(c),
            self._sync_azimuth_cut_switch(),
        ))
        out_layout.addWidget(_make_block_sep())

        # ── 3) 中间数据文件 (.xlsx) ──
        self._check_out_data = QCheckBox(self.tr("中间数据文件 (.xlsx)"))
        self._edit_data = QLineEdit()
        self._edit_data.setPlaceholderText(self.tr("选择输出路径..."))
        btn_dt = QPushButton(self.tr("浏览..."))
        btn_dt.clicked.connect(self._on_browse_data)
        _make_two_line_output(self._check_out_data, self._edit_data, btn_dt, out_layout)
        self._check_out_data.toggled.connect(lambda c: (
            self._edit_data.setEnabled(c),
            self._sync_azimuth_cut_switch(),
        ))
        out_layout.addWidget(_make_block_sep())

        # ── 4) 保存任务包 (.ant) ──
        self._check_save_task = QCheckBox(
            self.tr("保存任务包 (.ant) — 下次双击秒开，不重算"))
        self._check_save_task.setChecked(False)
        self._check_save_task.setToolTip(
            self.tr("保存为 .ant 任务包后，下次双击即可直接查看结果，无需重新计算。"))
        self._edit_task = QLineEdit()
        self._edit_task.setPlaceholderText(self.tr("选择保存路径..."))
        self._edit_task.setEnabled(False)
        btn_tsk = QPushButton(self.tr("浏览..."))
        btn_tsk.clicked.connect(self._on_browse_task)
        _make_two_line_output(self._check_save_task, self._edit_task, btn_tsk, out_layout)
        self._check_save_task.toggled.connect(lambda c: self._edit_task.setEnabled(c))
        out_layout.addWidget(_make_block_sep())

        # ── 5) 完整报告: 独立 Excel + 独立 Word ──
        self._check_full_report = QCheckBox(
            self.tr("生成完整报告（独立 Excel + 独立 Word，含全部参数和图表）"))
        self._check_full_report.setChecked(False)
        # Excel 路径
        self._edit_full_xlsx = QLineEdit()
        self._edit_full_xlsx.setPlaceholderText(self.tr("完整报告 Excel 路径..."))
        self._edit_full_xlsx.setEnabled(False)
        btn_fx = QPushButton(self.tr("浏览..."))
        btn_fx.clicked.connect(self._on_browse_full_xlsx)
        _make_two_line_output(None, self._edit_full_xlsx, btn_fx, out_layout)
        # Word 路径
        self._edit_full_graph = QLineEdit()
        self._edit_full_graph.setPlaceholderText(self.tr("完整报告 Word 路径..."))
        self._edit_full_graph.setEnabled(False)
        btn_fg = QPushButton(self.tr("浏览..."))
        btn_fg.clicked.connect(self._on_browse_full_graph)
        _make_two_line_output(self._check_full_report, self._edit_full_graph, btn_fg, out_layout)
        self._check_full_report.toggled.connect(lambda c: (
            self._edit_full_xlsx.setEnabled(c),
            self._edit_full_graph.setEnabled(c),
        ))

        right_layout.addWidget(out_grp)

        # 设置默认输出目录 (初始占位，加载文件后 _auto_set_output_defaults 更新)
        self._default_out_dir = _default_output_dir()
        if not self._edit_xlsx.text():
            self._edit_xlsx.setPlaceholderText(self.tr("加载源文件后自动生成"))
        if not self._edit_word.text():
            self._edit_word.setPlaceholderText(self.tr("加载源文件后自动生成"))
        if not self._edit_data.text():
            self._edit_data.setPlaceholderText(self.tr("加载源文件后自动生成"))
        if not self._edit_task.text():
            self._edit_task.setPlaceholderText(self.tr("加载源文件后自动生成"))
        if not self._edit_full_xlsx.text():
            self._edit_full_xlsx.setPlaceholderText(self.tr("加载源文件后自动生成"))
        if not self._edit_full_graph.text():
            self._edit_full_graph.setPlaceholderText(self.tr("加载源文件后自动生成"))

        right_layout.addStretch()

        h_splitter.addWidget(right_widget)
        h_splitter.setSizes([600, 300])
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setWidget(h_splitter)
        main_layout.addWidget(scroll_area, 1)

    def showEvent(self, event):
        super().showEvent(event)
        if not hasattr(self, '_spacing_applied'):
            self._spacing_applied = True
            self._apply_tight_spacing()

    def _apply_tight_spacing(self):
        """确保 QGroupBox 紧贴内容高度不被 splitter 撑大。"""
        for grp in [getattr(self, 'excel_grp', None), getattr(self, 'word_grp', None)]:
            if grp:
                grp.setSizePolicy(grp.sizePolicy().horizontalPolicy(), QSizePolicy.Fixed)
        if hasattr(self, '_data_sel'):
            self._data_sel.setSizePolicy(
                self._data_sel.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)

    def _init_state(self):
        """初始化本地状态（无 MainWindow 时使用）。"""
        self._local: dict = {}
        self._file_entries: List[FileEntry] = []
        self._worksheet_naming_mode: int = 0
        from src.config_manager import get_config_manager
        self._cfg = get_config_manager()
        self._load_azimuth_state()

    def _load_azimuth_state(self):
        """从 OutputConfig 恢复输出路径。"""
        if not self._mw:
            return
        az = getattr(self._mw, '_output_config', None)
        if az is None:
            return
        # Excel 报告: 从 output_config 恢复
        if hasattr(self, '_edit_xlsx') and az.excel_output_dir and az.excel_output_filename:
            self._edit_xlsx.setText(str(Path(az.excel_output_dir) / az.excel_output_filename))
        # Word 报告
        if hasattr(self, '_edit_word') and az.chart_output_dir and az.chart_output_filename:
            self._edit_word.setText(str(Path(az.chart_output_dir) / az.chart_output_filename))
        # 中间数据: 新增恢复
        if hasattr(self, '_edit_data') and az.data_output_dir and az.data_output_filename:
            self._edit_data.setText(str(Path(az.data_output_dir) / az.data_output_filename))

    def _sync_azimuth_state(self):
        """将输出路径写回 OutputConfig。"""
        if not self._mw:
            return
        az = getattr(self._mw, '_output_config', None)
        if az is None:
            return
        # Excel 报告 → output_config
        if hasattr(self, '_edit_xlsx'):
            txt = self._edit_xlsx.text().strip()
            if txt:
                p = Path(txt)
                az.excel_output_dir = str(p.parent)
                az.excel_output_filename = p.name
        # Word 报告
        if hasattr(self, '_edit_word'):
            txt = self._edit_word.text().strip()
            if txt:
                p = Path(txt)
                az.chart_output_dir = str(p.parent)
                az.chart_output_filename = p.name
        # 中间数据: 修复 — 同时保存 dir + filename
        if hasattr(self, '_edit_data'):
            txt = self._edit_data.text().strip()
            if txt:
                p = Path(txt)
                az.data_output_dir = str(p.parent)
                az.data_output_filename = p.name

    def _sync_azimuth_cut_switch(self):
        """勾选 Word 或数据输出时自动开启/关闭方位面开关。"""
        if not self._mw:
            return
        az = getattr(self._mw, '_output_config', None)
        if az is None:
            return
        need_azimuth = (
            getattr(self, '_check_out_word', None) is not None and self._check_out_word.isChecked()
        ) or (
            getattr(self, '_check_out_data', None) is not None and self._check_out_data.isChecked()
        )

    def get_output_flags(self):
        """返回输出开关: (excel, word, data)。"""
        return (
            self._check_out_excel.isChecked() if hasattr(self, '_check_out_excel') else True,
            self._check_out_word.isChecked() if hasattr(self, '_check_out_word') else False,
            self._check_out_data.isChecked() if hasattr(self, '_check_out_data') else False,
        )

    # ── 方位面输出目录浏览 ──

    def _on_browse_xlsx(self):
        """浏览: Excel 报告输出路径。"""
        from pathlib import Path
        start = self._edit_xlsx.text().strip() or str(self._default_out_dir / "AntennaReport.xlsx")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存天线参数报告"), start,
            self.tr("Excel 文件 (*.xlsx)"))
        if path:
            self._edit_xlsx.setText(path)
            self._sync_azimuth_state()

    def _on_browse_word(self):
        """浏览: Word 报告输出路径。"""
        from pathlib import Path
        start = self._edit_word.text().strip() or str(self._default_out_dir / "Graph.docx")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存测试报告"), start,
            self.tr("Word 文档 (*.docx)"))
        if path:
            self._edit_word.setText(path)
            self._sync_azimuth_state()

    def _on_browse_data(self):
        """浏览: 中间数据输出路径。"""
        from pathlib import Path
        start = self._edit_data.text().strip() or str(self._default_out_dir / "internaldata.xlsx")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存中间数据"), start,
            self.tr("Excel 文件 (*.xlsx)"))
        if path:
            self._edit_data.setText(path)
            self._sync_azimuth_state()

    def _on_browse_task(self):
        """浏览: 任务包保存路径。"""
        from pathlib import Path
        start = self._edit_task.text().strip() or str(self._default_out_dir / "task.ant")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存任务包"), start,
            self.tr("任务包文件 (*.ant)"))
        if path:
            self._edit_task.setText(path)

    def _on_browse_full_xlsx(self):
        """浏览: 完整报告 Excel 输出路径。"""
        from pathlib import Path
        start = self._edit_full_xlsx.text().strip() or str(self._default_out_dir / "FullReport.xlsx")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存完整报告 Excel"), start,
            self.tr("Excel 文件 (*.xlsx)"))
        if path:
            self._edit_full_xlsx.setText(path)

    def _on_browse_full_graph(self):
        """浏览: 完整报告 Word 图表输出路径。"""
        from pathlib import Path
        start = self._edit_full_graph.text().strip() or str(self._default_out_dir / "fullGraph.docx")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存完整报告图表"), start,
            self.tr("Word 文档 (*.docx)"))
        if path:
            self._edit_full_graph.setText(path)

    def _on_browse_word_template(self):
        """选择带 SDT tag 的 Word 模板（不自动预览）。"""
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path
        start = self._edit_word_report_tpl or str(Path.cwd())
        d, _ = QFileDialog.getOpenFileName(self, self.tr("选择 Word 模板"), start,
                                            self.tr("Word 文档 (*.docx)"))
        if d:
            self._edit_word_report_tpl = d
            if hasattr(self, '_edit_word_tpl_widget'):
                self._edit_word_tpl_widget.setText(d)

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
        self._tpl_path_label.setText(path)
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
        self._lbl_match_status.setText("")
        if self._data_file_paths:
            self._on_auto_match()

    def _check_excel_word_consistency(self):
        """检查 Excel 参数模板与 Word SDT tag 的一致性。"""
        excel_path = self._tpl_path_label.text().strip()
        word_path = (self._edit_word_report_tpl or "").strip() if hasattr(self, '_edit_word_report_tpl') else ""
        if not excel_path or not word_path or not Path(excel_path).exists() or not Path(word_path).exists():
            return
        try:
            from src.excel_reader import read_template
            from src.docx_exporter import DocxTemplateFiller
            sheets = read_template(excel_path)
            excel_params = set()
            for s in sheets:
                for col in s.columns:
                    excel_params.add(col.col_type)
            filler = DocxTemplateFiller(word_path)
            word_tags = set(filler.list_tags())
            # 提取 Word 中隐含的参数需求 (table_data → 数据表, 所有 data_* tag)
            word_params = set()
            for t in word_tags:
                if t.startswith("data_"):
                    word_params.add(t.replace("data_", ""))
                elif t.startswith("table_data"):
                    word_params.add("table")  # 表自动识别, 不做细粒度检查

            # 计算差异
            in_excel_not_word = excel_params - word_params - {"frequency", "unknown"}
            in_word_not_excel = word_params - excel_params - {"table"}

            if in_excel_not_word:
                self._mw._log(f"⚠ Excel 中有但 Word SDT 未覆盖的参数: {sorted(in_excel_not_word)}", level="warning")
            if in_word_not_excel:
                self._mw._log(f"⚠ Word SDT 中有但 Excel 未定义的参数: {sorted(in_word_not_excel)}", level="warning")
            if not in_excel_not_word and not in_word_not_excel:
                self._mw._log("✓ Excel 参数与 Word SDT tag 一致")
        except Exception as e:
            self._mw._log(f"⚠ Excel/Word 一致性检查失败: {e}", level="warning")

    def _on_word_tpl_path_set(self, path: str):
        """Word 模板预设选中 → 更新路径。"""
        if path:
            self._edit_word_report_tpl = path

    def _on_word_preset_excel_load(self, excel_path: str, word_path: str):
        """Word 预设选中 → 同步加载对应 Excel 模板。"""
        if excel_path and Path(excel_path).exists():
            self._tpl_row.set_path(excel_path)
            self._tpl_path_label.setText(excel_path)
            self._template_path = excel_path
            if self._mw:
                self._mw.ui.editTemplatePath.setText(excel_path)

    def _on_preview_word(self):
        """预览 Word 模板: 分屏视图 — 文档 + SDT tag 树。"""
        path = (getattr(self, '_edit_word_report_tpl', '') or '').strip()
        if not path or not Path(path).exists():
            from PySide6.QtWidgets import QFileDialog
            d, _ = QFileDialog.getOpenFileName(self, self.tr("选择 Word 模板"), "",
                                                self.tr("Word 文档 (*.docx)"))
            if d:
                self._edit_word_report_tpl = d
                path = d
            else:
                return
        try:
            from src.docx_exporter import DocxTemplateFiller
            from src.docx_sdt_inserter import scan_docx
            from src.llm_tagger import rule_based_suggest
            filler = DocxTemplateFiller(path)
            existing = set(filler.list_tags())
            positions = scan_docx(path)
            rule_based_suggest(positions)
            multi_cfg = getattr(self._mw, '_multi_antenna_config', None) if self._mw else None
            dlg = WordTemplatePreviewDialog(self, path, existing, positions, multi_cfg)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, self.tr("预览失败"), str(e))

    def _on_preset_word_loaded(self, excel_path: str, word_path: str):
        """预设选中时，同时加载 Word 模板路径。"""
        if word_path and hasattr(self, '_edit_word_report_tpl'):
            self._edit_word_report_tpl = word_path
            # 更新 Word 预设下拉选中项
            # Word 预设同步到 TemplateSourceRow
            if hasattr(self, '_word_tpl_row') and word_path:
                existing = self._word_tpl_row._all_presets if hasattr(self._word_tpl_row, '_all_presets') else []

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
            from src.column_mapping import detect_columns_from_template, TemplatePreset, save_preset
            mappings = detect_columns_from_template(tpl_path)
        except Exception as e:
            QMessageBox.warning(self, self.tr("检测失败"), self.tr(f"列头检测失败:\n{e}"))
            return

        def _extract_angle(raw: str, ctype: str) -> str:
            from src.lag_config import extract_angles_from_headers
            singles, ranges = extract_angles_from_headers([raw])
            if ctype.endswith("_range") and ranges:
                lo, hi = ranges[0]
                return f"{lo:.0f}–{hi:.0f}"
            if singles:
                return ", ".join(f"{a:.0f}" for a in singles[:5])
            return ""

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("模板列预览"))
        dlg.setMinimumSize(800, 400)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowMaximizeButtonHint)
        layout = QVBoxLayout(dlg)

        # ── 测试模式选择 (双向同步天线参数页) ──
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("<b>" + self.tr("测试类型:") + "</b>"))
        cmb_mode = QComboBox()
        cmb_mode.addItem("📡 " + self.tr("无源天线"), 0)
        cmb_mode.addItem("📶 " + self.tr("有源发射 TRP"), 1)
        cmb_mode.addItem("📻 " + self.tr("有源接收 TIS"), 2)
        # 自动检测模式: 扫描检测到的列类型
        detected_types = {m.detected_type for m in mappings}
        if any(t in detected_types for t in ("trp", "nhprp_45", "nhprp_30", "nhprp_225", "peak_eirp")):
            auto_mode = 1  # 有源发射
        elif any(t in detected_types for t in ("tis", "nhpis_45", "nhpis_30", "nhpis_225")):
            auto_mode = 2  # 有源接收
        else:
            auto_mode = 0  # 无源天线
        # 优先用天线参数页当前模式，其次用自动检测
        cur_mode = self._mw._test_mode if self._mw and hasattr(self._mw, '_test_mode') else auto_mode
        cmb_mode.setCurrentIndex(cur_mode if cur_mode in (0, 1, 2) else auto_mode)
        def _on_mode_changed(idx):
            new_mode = cmb_mode.currentData()
            if self._mw:
                self._mw._test_mode = new_mode
            self._rebuild_preview_types(mode=new_mode)
        cmb_mode.currentIndexChanged.connect(_on_mode_changed)
        mode_row.addWidget(cmb_mode)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # ── 重建类型下拉 (按模式过滤) ──
        def _build_type_combo(col, ctype):
            from src.column_mapping import get_col_type_labels
            cur_mode = cmb_mode.currentData() or 0
            labels = get_col_type_labels(cur_mode)
            cmb = QComboBox()
            for t, label in labels:
                cmb.addItem(label, t)
            idx = cmb.findData(ctype)
            if idx >= 0:
                cmb.setCurrentIndex(idx)
            return cmb

        dlg._rebuild_types = lambda mode: _rebuild_preview_types(mode)

        def _rebuild_preview_types(mode: int):
            """模式变更 → 重建所有修正类型下拉列表，保留已选值。"""
            from src.column_mapping import get_col_type_labels
            labels = get_col_type_labels(mode)
            for ci in range(table.columnCount()):
                old_cmb = table.cellWidget(4, ci)
                old_val = old_cmb.currentData() if old_cmb else None
                new_cmb = QComboBox()
                for ct, label in labels:
                    new_cmb.addItem(label, ct)
                idx = new_cmb.findData(old_val)
                if idx >= 0:
                    new_cmb.setCurrentIndex(idx)
                # 重连信号
                new_cmb.currentIndexChanged.connect(
                    lambda _i, c=ci, cb=new_cmb, ep=None:
                    self._on_preview_type_changed(c, cb, table, mappings[c].raw_header if c < len(mappings) else ""))
                table.setCellWidget(4, ci, new_cmb)

        # 转置表: 每列=模版一列, 行=属性
        n = len(mappings)
        table = QTableWidget()
        table.setRowCount(8)
        table.setColumnCount(n)
        ROW_LABELS = [self.tr("列号"), self.tr("列头文本"), self.tr("检测类型"),
                       self.tr("参数值"), self.tr("修正类型"), self.tr("修正参数"), self.tr("操作")]
        table.setVerticalHeaderLabels(ROW_LABELS)
        table.horizontalHeader().hide()  # 使用竖表头作行标签，隐藏横表头
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        detected = 0
        for ci, m in enumerate(mappings):
            table.setItem(0, ci, QTableWidgetItem(m.col_letter))
            table.setItem(1, ci, QTableWidgetItem(m.raw_header))
            table.setItem(2, ci, QTableWidgetItem(m.detected_type))
            angle_val = _extract_angle(m.raw_header, m.detected_type)
            table.setItem(3, ci, QTableWidgetItem(angle_val))
            # 修正类型下拉 (按当前模式过滤)
            cmb = QComboBox()
            from src.column_mapping import get_col_type_labels
            for ct, label in get_col_type_labels(cur_mode):
                cmb.addItem(label, ct)
            idx = cmb.findData(m.detected_type)
            if idx >= 0:
                cmb.setCurrentIndex(idx)
            table.setCellWidget(4, ci, cmb)
            # 修正参数输入（角度/参数值）+ ⚙ 快捷打开角度配置
            param_widget = QWidget()
            param_layout = QHBoxLayout(param_widget)
            param_layout.setContentsMargins(0, 0, 0, 0)
            param_layout.setSpacing(2)
            edit_param = QLineEdit()
            edit_param.setPlaceholderText(self.tr("输入参数值"))
            edit_param.setText(angle_val)
            param_layout.addWidget(edit_param, 1)
            table.setCellWidget(5, ci, param_widget)
            # ⚙ 按钮独占一行
            btn_cfg = QPushButton("⚙")
            btn_cfg.setToolTip(self.tr("打开角度配置对话框"))
            btn_cfg.clicked.connect(
                lambda checked, ci=ci, cb=cmb, ep=edit_param, tbl=table:
                self._on_preview_open_angle_popup(ci, cb, ep, tbl))
            table.setCellWidget(6, ci, btn_cfg)
            # 类型变更 → 自动填充角度参数
            cmb.currentIndexChanged.connect(
                lambda _i, c=ci, cb=cmb, ep=edit_param, rh=m.raw_header:
                self._on_preview_type_changed(c, cb, table, rh, ep))
            # 应用按钮
            btn_mod = QPushButton(self.tr("应用"))
            btn_mod.setFixedWidth(50)
            btn_mod.clicked.connect(lambda checked, idx=ci, ct=m.detected_type:
                self._on_preview_apply(dlg, idx, ct, table))
            table.setCellWidget(7, ci, btn_mod)
            if m.detected_type != "unknown":
                detected += 1
        table.resizeColumnsToContents()
        table.setMinimumHeight(320)
        layout.addWidget(table)

        # 摘要
        summary = QLabel(
            self.tr("共 {} 列, 识别 {} 列, {} 列未识别, 识别类型见「检测类型」行").format(
                len(mappings), detected, len(mappings) - detected))
        summary.setStyleSheet("")
        layout.addWidget(summary)
        dlg._summary_label = summary  # 供 _on_preview_apply_all 更新

        # 按钮
        btn_row = QHBoxLayout()
        btn_save = QPushButton(self.tr("💾 保存为模板预设"))
        btn_apply_all = QPushButton(self.tr("✅ 全部应用"))
        btn_apply_all.setStyleSheet("font-weight:bold;")
        btn_apply_all.setToolTip(self.tr("批量应用所有列的修正参数，不弹窗确认"))
        btn_apply_all.clicked.connect(lambda: self._on_preview_apply_all(dlg, table, n, mappings))
        btn_close = QPushButton(self.tr("关闭"))
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_apply_all)
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
        param_widget = table.cellWidget(5, col)
        if not cmb or not param_widget:
            return
        # edit_param is QLineEdit inside the param_widget
        edit_param = param_widget.findChild(QLineEdit) if hasattr(param_widget, 'findChild') else param_widget
        new_type = cmb.currentData() or ctype
        param_val = edit_param.text().strip() if hasattr(edit_param, 'text') else ""
        # 更新检测类型显示
        table.item(2, col).setText(new_type)
        table.item(3, col).setText(param_val)
        # 通用: 按类型前缀写入对应 config
        if self._mw and param_val:
            from src.ui_utils import ANGLE_TYPE_CONFIG
            for prefix, info in ANGLE_TYPE_CONFIG.items():
                if not new_type.startswith(prefix + "_"):
                    continue
                cfg = getattr(self._mw, info.attr, None)
                if cfg is None:
                    break
                try:
                    if new_type.endswith("_range") and info.has_range:
                        parts = param_val.replace("°", "").split("–")
                        if len(parts) == 2:
                            cfg.add_range(float(parts[0]), float(parts[1]))
                    else:
                        for v in param_val.replace("°", "").split(","):
                            cfg.add_single(float(v.strip()))
                except ValueError:
                    pass
                if hasattr(self._mw, '_sync_quick_buttons'):
                    self._mw._sync_quick_buttons()
                if hasattr(self._mw, '_update_lag_display'):
                    self._mw._update_lag_display()
                self._mw._log(f"✓ 已应用: {new_type} = {param_val}")
                break

    def _on_preview_type_changed(self, col: int, cmb: QComboBox, table, raw_header: str,
                                  edit_param=None):
        """修正类型变更 → 从天线参数配置自动填充角度值。"""
        if edit_param is None:
            pw = table.cellWidget(5, col)
            edit_param = pw.findChild(QLineEdit) if pw and hasattr(pw, 'findChild') else pw
        if edit_param is None:
            return
        new_type = cmb.currentData()
        if not new_type:
            return

        # 通用角度提取
        from src.lag_config import extract_angles_from_headers
        angle_val = ""
        singles, ranges = extract_angles_from_headers([raw_header])
        if new_type.endswith("_range") and ranges:
            lo, hi = ranges[0]
            angle_val = f"{lo:.0f}–{hi:.0f}"
        elif singles:
            angle_val = ", ".join(f"{a:.0f}" for a in singles[:5])

        # 列头未提取到 → 从天线参数 AnglePicker 配置读取
        if not angle_val and self._mw:
            lag_cfg = getattr(self._mw, '_lag_config', None)
            ar_cfg = getattr(self._mw, '_ar_lag_config', None)

            if new_type in ("lag_single",) and lag_cfg:
                singles = lag_cfg.singles_sorted
                if singles:
                    angle_val = ", ".join(f"{a:.0f}" for a in singles[:3])
            elif new_type in ("lag_range",) and lag_cfg:
                ranges = lag_cfg.ranges_sorted
                if ranges:
                    lo, hi = ranges[0]
                    angle_val = f"{lo:.0f}–{hi:.0f}"
            elif new_type in ("ar_single",) and ar_cfg:
                singles = ar_cfg.singles_sorted
                if singles:
                    angle_val = ", ".join(f"{a:.0f}" for a in singles[:3])
            elif new_type in ("ar_range",) and ar_cfg:
                ranges = ar_cfg.ranges_sorted
                if ranges:
                    lo, hi = ranges[0]
                    angle_val = f"{lo:.0f}–{hi:.0f}"
            elif new_type == "rhcp_single":
                rhcp_cfg = getattr(self._mw, '_rhcp_lag_config', None) or lag_cfg
                singles = rhcp_cfg.singles_sorted if rhcp_cfg else []
                if singles:
                    angle_val = ", ".join(f"{a:.0f}" for a in singles[:3])
            elif new_type == "cp_xpi_single":
                cp_cfg = getattr(self._mw, '_cpxpi_lag_config', None) or lag_cfg
                singles = cp_cfg.singles_sorted if cp_cfg else []
                if singles:
                    angle_val = ", ".join(f"{a:.0f}" for a in singles[:3])

        if angle_val:
            edit_param.setText(angle_val)

    def _on_preview_open_angle_popup(self, col: int, cmb: QComboBox, edit_param: QLineEdit,
                                       table: QTableWidget = None):
        """预览中点击 ⚙ → 打开角度配置弹窗，批量填充所有同 target 列。"""
        ctype = cmb.currentData()
        if not ctype:
            return
        type_to_target = {
            "lag_single": "gain", "lag_range": "gain",
            "ar_single": "ar", "ar_range": "ar",
            "rhcp_single": "rhcp", "cp_xpi_single": "cpxpi",
        }
        target = type_to_target.get(ctype)
        if not target:
            return
        # _show_angle_popup 在 AntennaParamsPage 上, FileSettingsPage 通过 mw 访问
        ant_page = getattr(self._mw, '_antenna_params_page', None) if self._mw else None
        if ant_page and hasattr(ant_page, '_show_angle_popup'):
            ant_page._show_angle_popup(target)
        else:
            return
        if not self._mw:
            return
        from src.ui_utils import ANGLE_TYPE_CONFIG
        info = ANGLE_TYPE_CONFIG.get(target)
        if not info:
            return
        cfg = getattr(self._mw, info.attr, None)
        if not cfg:
            return

        # 扫描表所有列，批量填充同 target 的参数
        all_same_target = {t for t, tg in type_to_target.items() if tg == target}
        if table is None:
            # fallback: 从 widget 树查找
            pw_parent = edit_param.parent()
            table = pw_parent.parent().parent() if pw_parent else None
        if not isinstance(table, QTableWidget):
            return
        n = table.columnCount()
        for ci in range(n):
            cell_cmb = table.cellWidget(4, ci)
            if not cell_cmb:
                continue
            cell_ctype = cell_cmb.currentData()
            if cell_ctype not in all_same_target:
                continue
            pw = table.cellWidget(5, ci)
            cell_edit = pw.findChild(QLineEdit) if pw and hasattr(pw, 'findChild') else pw
            if not cell_edit:
                continue
            singles = cfg.singles_sorted
            ranges = cfg.ranges_sorted
            if cell_ctype.endswith("_single") and singles:
                cell_edit.setText(", ".join(f"{a:.0f}" for a in singles[:5]))
            elif cell_ctype.endswith("_range") and ranges:
                lo, hi = ranges[0]
                cell_edit.setText(f"{lo:.0f}–{hi:.0f}")

    def _on_preview_apply_all(self, dlg, table, n_cols, mappings):
        """批量应用: 类型有改动 或 参数值有改动 都生效。"""
        applied = 0
        for ci in range(n_cols):
            cmb = table.cellWidget(4, ci)
            if not cmb:
                continue
            new_type = cmb.currentData()
            orig_type = mappings[ci].detected_type if ci < len(mappings) else "unknown"
            pw = table.cellWidget(5, ci)
            if not pw:
                continue
            edit_param = pw.findChild(QLineEdit) if hasattr(pw, 'findChild') else pw
            param_changed = bool(edit_param.text().strip()) if hasattr(edit_param, 'text') else False
            if new_type == orig_type and not param_changed:
                continue  # 类型没变且参数为空, 跳过
            self._on_preview_apply(dlg, ci, orig_type, table)
            applied += 1
        # 更新摘要
        sl = getattr(dlg, '_summary_label', None)
        if sl:
            sl.setText(self.tr("已批量应用 {} 项修正").format(applied))

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
            self._lbl_match_status.setText("")
        existing = set(self._data_file_paths)
        new_paths = [p for p in paths if p not in existing]
        if not new_paths:
            return
        self._data_file_paths.extend(new_paths)
        self._data_stale = False
        self._sync_file_entries()
        # 刷新 MainWindow 天线选择器
        if self._mw and hasattr(self._mw, '_refresh_antenna_selector'):
            self._mw._refresh_antenna_selector()
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
        self._lbl_match_status.setText("")
        self._data_stale = True

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
        from src.multi_antenna import extract_antenna_name
        for p in self._data_file_paths:
            if p in old_map:
                self._file_entries.append(old_map[p])
            else:
                self._file_entries.append(FileEntry(path=p, test_mode=test_mode,
                    antenna_name=extract_antenna_name(p)))

    def _refresh_data_file_ui(self):
        t = self._file_list_widget
        t.setRowCount(len(self._data_file_paths))
        from src.multi_antenna import extract_antenna_name
        for i, p in enumerate(self._data_file_paths):
            try:
                size_mb = Path(p).stat().st_size / (1024 * 1024)
                label = f"📄 {Path(p).name}  ({size_mb:.1f} MB)"
            except OSError:
                label = f"📄 {Path(p).name}"
            item = QTableWidgetItem(label)
            item.setToolTip(p)
            t.setItem(i, 0, item)
            # 天线名称: 默认从文件名提取
            entry = self._file_entries[i] if i < len(self._file_entries) else None
            ant_name = entry.antenna_name if entry else ""
            if not ant_name:
                ant_name = extract_antenna_name(p)
            name_edit = QLineEdit(ant_name)
            name_edit.setPlaceholderText(self.tr("天线标识"))
            name_edit.textChanged.connect(
                lambda txt, row=i: self._on_antenna_name_changed(row, txt))
            t.setCellWidget(i, 1, name_edit)
            # 测试模式
            mode_combo = QComboBox()
            for mode_val in [0, 1, 2]:
                mode_combo.addItem(mode_name(mode_val), mode_val)
            if entry:
                mode_combo.setCurrentIndex(entry.test_mode)
            mode_combo.currentIndexChanged.connect(
                lambda idx, row=i: self._on_file_mode_changed(row))
            t.setCellWidget(i, 2, mode_combo)
            t.setRowHeight(i, 28)
        self._update_window_title()
        self._auto_set_output_defaults()

    def _auto_set_output_defaults(self):
        """若输出路径为空，自动填充为源文件目录下 output 子目录。"""
        if not self._data_file_paths:
            return
        src_path = Path(self._data_file_paths[0])
        src_dir = str(src_path.parent)
        stem = src_path.stem  # 源文件名(无扩展名)
        out_dir = str(Path(src_dir) / "output")
        os.makedirs(out_dir, exist_ok=True)  # 自动创建 output 子目录

        defaults = [
            ("_edit_xlsx", f"{stem}_AntennaReport.xlsx"),
            ("_edit_word", f"{stem}_Graph.docx"),
            ("_edit_data", f"{stem}_internaldata.xlsx"),
            ("_edit_task", f"{stem}.ant"),
            ("_edit_full_xlsx", f"{stem}_FullReport.xlsx"),
            ("_edit_full_graph", f"{stem}_FullGraph.docx"),
        ]
        for attr, fname in defaults:
            w = getattr(self, attr, None)
            if w and not w.text().strip():
                w.setText(str(Path(out_dir) / fname))

        # 同步到 output_config (确保 pipeline 消费端有默认值)
        az = getattr(self._mw, '_output_config', None) if self._mw else None
        if az:
            for attr, fname in defaults:
                w = getattr(self, attr, None)
                if w and w.text().strip():
                    p = Path(w.text().strip())
                    if attr == "_edit_xlsx":
                        az.excel_output_dir = str(p.parent)
                        az.excel_output_filename = p.name
                    elif attr == "_edit_word":
                        az.chart_output_dir = str(p.parent)
                        az.chart_output_filename = p.name
                    elif attr == "_edit_data":
                        az.data_output_dir = str(p.parent)
                        az.data_output_filename = p.name

    def _on_antenna_name_changed(self, row: int, text: str):
        if row < len(self._file_entries):
            self._file_entries[row].antenna_name = text.strip()
        # 同步更新天线选择器
        if self._mw and hasattr(self._mw, '_refresh_antenna_selector'):
            self._mw._refresh_antenna_selector()

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
        """存储匹配结果并更新状态标签（匹配表 GUI 已移除）。"""
        self._last_matches = matches
        matched = sum(1 for m in matches if m.file_path is not None)
        self._lbl_match_status.setText(f"✓ {matched}/{len(matches)} 个工作表已匹配")


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

    def _on_multi_antenna_confirm(self):
        """打开多天线确认对话框 (预填已加载的文件)。"""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout
        from ui.multi_antenna_page import MultiAntennaPage
        from src.multi_antenna import extract_antenna_name
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("多天线配置确认"))
        dlg.resize(950, 680)
        layout = QVBoxLayout(dlg)
        page = MultiAntennaPage(dlg, self._mw if self._mw else None)
        files = self._data_file_paths if hasattr(self, '_data_file_paths') else []
        if files:
            for fp in files:
                ant = page._config.add_antenna(extract_antenna_name(fp), [fp])
                page._antenna_list.addItem(ant.name)
            page._antenna_list.setCurrentRow(0)
        if hasattr(self, '_edit_word_report_tpl'):
            word_path = (self._edit_word_report_tpl or "").strip()
            if word_path:
                page._edit_word_tpl = word_path
        layout.addWidget(page)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            setattr(self._mw, '_multi_antenna_config', page.get_config()) if self._mw else None,
            dlg.accept()))
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()
    def get_lag_checkboxes(self):
        """返回 {效率曲线, 增益曲线} 勾选状态。"""
        return {
        }

    def build_datasource_map(self, progress_callback=None):
        """构建数据源映射（同 MainWindow._build_datasource_map）。"""
        from src.datasource import DataSource
        from src.sheet_file_matcher import extract_key, sanitize_sheet_name
        result = {}
        total_files = max(len(self._data_file_paths), 1)
        file_idx = 0
        use_file_names = self._worksheet_naming_mode == 1

        matched_files = set()
        for m in getattr(self, '_last_matches', []):
            template_sheet_name = m.sheet_name
            fp = m.file_path or ""
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
        for m in getattr(self, '_last_matches', []):
            fp = m.file_path or ""
            if fp and fp in file_mode_lookup:
                key = sanitize_sheet_name(extract_key(fp)) if use_file_names else sanitize_sheet_name(m.sheet_name)
                sheet_mode_map[key] = file_mode_lookup[fp]
        for sn in datasource_map:
            if sn not in sheet_mode_map:
                sheet_mode_map[sn] = getattr(self._mw, '_test_mode', 0) if self._mw else 0
        return sheet_mode_map

    def _show_metadata_editor(self):
        """打开报告元数据编辑对话框。"""
        from ui.dialogs import ReportMetadataDialog
        dlg = ReportMetadataDialog(self._mw if self._mw else self)
        dlg.exec()

    def _show_pattern_manager(self):
        """打开列识别规则管理对话框。"""
        dlg = PatternManagerDialog(self._mw if self._mw else self)
        dlg.exec()
        try:
            from src.excel_reader import reload_column_patterns
            reload_column_patterns()
        except ImportError:
            pass


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
            ("gain", "Gain (Peak / 单角度 / 范围)"),
        ]),
        ("Directivity", [
            ("directivity", "Directivity (dBi)"),
        ]),
        ("Efficiency / 总效率", [
            ("efficiency_pct", "Efficiency (%)"),
            ("efficiency_db", "Efficiency (dB)"),
            ("total_efficiency_pct", "Total Efficiency (%)"),
            ("mismatch_loss_db", "Mismatch Loss (dB)"),
        ]),
        ("AR", [
            ("ar", "AR (单角度 / 范围)"),
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
        # 注意: NHPRP/NHPIS 角度使用 AnglePicker 配置 (天线参数页 — Gain ⚙)
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
        self._rhcp_angle_widget: Optional[AnglePickerWidget] = None
        self._cpxpi_angle_widget: Optional[AnglePickerWidget] = None
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
        self._current_mode = getattr(self._mw, '_test_mode', 0) if self._mw else 0
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

        left_grp = QGroupBox(self.tr("天线参数"))
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

        row_extrap = QHBoxLayout()
        row_extrap.addWidget(QLabel(self.tr("Theta 外推:")))
        self._cmb_extrap = self._make_extrap_combo(include_none=True)
        self._cmb_extrap.setToolTip(self.tr("除 Directivity 外所有参数的 Theta 外推算法"))
        self._cmb_extrap.currentIndexChanged.connect(lambda: self._sync_to_mw())
        row_extrap.addWidget(self._cmb_extrap)
        row_extrap.addStretch()
        algo_layout.addLayout(row_extrap)
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
        # 从现有配置加载
        target_widgets = {
            "gain":  ("_gain_angle_widget",  "Gain"),
            "ar":    ("_ar_angle_widget",    "AR"),
            "rhcp":  ("_rhcp_angle_widget",  "RHCP Gain"),
            "cpxpi": ("_cpxpi_angle_widget", "CP-XPI"),
        }
        attr, label = target_widgets.get(target, ("_gain_angle_widget", "Gain"))
        widget = getattr(self, attr, None)
        if widget and hasattr(widget, 'get_config'):
            src_cfg = widget.get_config()
        else:
            src_cfg = LagConfig()
        singles = list(src_cfg.single_angles)
        ranges = list(src_cfg.ranges)

        dlg = QDialog(self)
        dlg.setWindowTitle(label + " " + self.tr("参数设置"))
        dlg.setMinimumSize(560, 460)
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

        # AR 输出单位（仅 AR 需要）
        if target == "ar":
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
            from ui.widgets import AnglePickerWidget
            new_cfg = LagConfig(single_angles=singles, ranges=ranges)
            widget_attrs = {
                "gain": "_gain_angle_widget", "ar": "_ar_angle_widget",
                "rhcp": "_rhcp_angle_widget", "cpxpi": "_cpxpi_angle_widget",
            }
            attr = widget_attrs.get(target, "_gain_angle_widget")
            if not getattr(self, attr, None):
                setattr(self, attr, AnglePickerWidget())
            getattr(self, attr).set_config(new_cfg)
            if target == "ar":
                self._cmb_ar_output.setCurrentIndex(cmb_ar_out.currentIndex())
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
        rhcp_cfg = self._rhcp_angle_widget.get_config() if self._rhcp_angle_widget else LagConfig()
        s["rhcp_singles"] = list(rhcp_cfg.single_angles)
        s["rhcp_ranges"] = list(rhcp_cfg.ranges)
        cpxpi_cfg = self._cpxpi_angle_widget.get_config() if self._cpxpi_angle_widget else LagConfig()
        s["cpxpi_singles"] = list(cpxpi_cfg.single_angles)
        s["cpxpi_ranges"] = list(cpxpi_cfg.ranges)
        s["nh_custom_angles"] = list(self._nh_custom_angles)
        s["extrapolate"] = self._cmb_extrap.currentData()
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
        rhcp_cfg = LagConfig(
            single_angles=list(s.get("rhcp_singles", [])),
            ranges=list(s.get("rhcp_ranges", [])),
        )
        if self._rhcp_angle_widget:
            self._rhcp_angle_widget.set_config(rhcp_cfg)
        cpxpi_cfg = LagConfig(
            single_angles=list(s.get("cpxpi_singles", [])),
            ranges=list(s.get("cpxpi_ranges", [])),
        )
        if self._cpxpi_angle_widget:
            self._cpxpi_angle_widget.set_config(cpxpi_cfg)
        self._nh_custom_angles = list(s.get("nh_custom_angles", []))
        self._sync_nh_angle_display()
        cur = s.get("extrapolate")
        if isinstance(cur, bool):
            # 兼容旧版 bool 状态: True → "linear", False → None
            cur = "linear" if cur else None
        idx = self._cmb_extrap.findData(cur)
        if idx >= 0:
            self._cmb_extrap.setCurrentIndex(idx)
        self._check_robust.setChecked(s.get("robust_peak", False))
        self._cmb_ar_output.setCurrentIndex(0 if s.get("ar_output_db", True) else 1)
        idx = self._cmb_freq_src.findData(s.get("freq_source"))
        if idx >= 0:
            self._cmb_freq_src.setCurrentIndex(idx)
        self._spin_trim_start.setValue(s.get("trim_start", 0))
        self._spin_trim_end.setValue(s.get("trim_end", 0))
        self._required_params = s.get("required", set())
        self._extra_params = s.get("extra", set())

    # ── 参数列重建 ──

    def _rebuild_param_columns(self):
        params = self._get_params_for_tab(self._active_tab)
        self._left_checkboxes.clear()
        self._right_checkboxes.clear()

        # 左右分栏: 测试报告 | 额外报告
        content = QWidget()
        vbox_outer = QVBoxLayout(content)
        vbox_outer.setContentsMargins(0, 0, 0, 0)
        vbox_outer.setSpacing(4)

        # 共享标题行: 测试报告 + 额外报告 [启用]
        hdr_row = QHBoxLayout()
        hdr_row.addWidget(QLabel(self.tr("测试报告")))
        hdr_row.addStretch()
        hdr_row.addWidget(QLabel(self.tr("额外报告")))
        self._check_full_report_enable = QCheckBox(self.tr("启用"))
        self._check_full_report_enable.setChecked(
            getattr(self._mw, '_full_report_enabled', False) if self._mw else False)
        self._check_full_report_enable.toggled.connect(self._on_full_report_toggled)
        hdr_row.addWidget(self._check_full_report_enable)
        vbox_outer.addLayout(hdr_row)

        # 左右列
        hbox = QHBoxLayout()
        hbox.setSpacing(8)

        # 左列: 测试报告内容
        left_box = QGroupBox()
        left_layout = QVBoxLayout(left_box)
        left_layout.setSpacing(2)
        for grp_name, items in params:
            grp = QGroupBox(grp_name)
            gl = QVBoxLayout(grp)
            gl.setSpacing(2)
            for key, label in items:
                row = QHBoxLayout()
                row.setSpacing(4)
                cb = QCheckBox(label)
                self._left_checkboxes[key] = cb
                cb.toggled.connect(lambda checked, k=key: self._sync_to_mw())
                tpl = self._template_params
                cascade_up = (key == "gain" and ("lag_single" in tpl or "lag_range" in tpl)) or                              (key == "ar" and ("ar_single" in tpl or "ar_range" in tpl))
                cb.setChecked(key in self._template_params or cascade_up)
                row.addWidget(cb)
                # 同行参数按钮 — 数据驱动，新增角度类型只需在 dict 加一行
                from src.ui_utils import ANGLE_TYPE_CONFIG, _ANGLE_BY_PARAM_KEY
                if key in _ANGLE_BY_PARAM_KEY:
                    info = _ANGLE_BY_PARAM_KEY[key]
                    btn = QPushButton(self.tr("⚙ 参数"))
                    btn.setFixedWidth(60)
                    btn.setToolTip(self.tr(f"{info.label} 参数设置"))
                    btn.clicked.connect(lambda checked, t=info.popup: self._show_angle_popup(t))
                    row.addWidget(btn)
                row.addStretch()
                gl.addLayout(row)
            if grp_name == "Directivity":
                row_de = QHBoxLayout()
                row_de.addWidget(QLabel(self.tr("外推:")))
                cmb_de = self._make_extrap_combo(include_none=True)
                cmb_de.setToolTip(self.tr("Directivity 外推算法"))
                cmb_de.currentIndexChanged.connect(lambda: self._sync_to_mw())
                mw = getattr(self, '_mw', None)
                if mw:
                    cur = getattr(mw, '_dir_extrap_method', 'none')
                    idx = cmb_de.findData(cur)
                    if idx >= 0: cmb_de.setCurrentIndex(idx)
                row_de.addWidget(cmb_de)
                row_de.addStretch()
                gl.addLayout(row_de)
                setattr(self, '_cmb_dir_extrap_de', cmb_de)
            left_layout.addWidget(grp)
        left_layout.addStretch()
        hbox.addWidget(left_box, 1)

        # 右列: 额外报告内容
        right_box = QGroupBox()
        right_layout = QVBoxLayout(right_box)
        right_layout.setSpacing(2)
        for grp_name, items in params:
            grp = QGroupBox(grp_name)
            gl = QVBoxLayout(grp)
            gl.setSpacing(2)
            for key, label in items:
                row = QHBoxLayout()
                row.setSpacing(4)
                cb = QCheckBox(label)
                self._right_checkboxes[key] = cb
                cb.toggled.connect(lambda checked, k=key: self._sync_to_mw())
                cb.setChecked(False)
                row.addWidget(cb)
                # 同行参数按钮 — 数据驱动，新增角度类型只需在 dict 加一行
                from src.ui_utils import ANGLE_TYPE_CONFIG, _ANGLE_BY_PARAM_KEY
                if key in _ANGLE_BY_PARAM_KEY:
                    info = _ANGLE_BY_PARAM_KEY[key]
                    btn = QPushButton(self.tr("⚙ 参数"))
                    btn.setFixedWidth(60)
                    btn.setToolTip(self.tr(f"{info.label} 参数设置"))
                    btn.clicked.connect(lambda checked, t=info.popup: self._show_angle_popup(t))
                    row.addWidget(btn)
                row.addStretch()
                gl.addLayout(row)
            if grp_name == "Directivity":
                row_de = QHBoxLayout()
                row_de.addWidget(QLabel(self.tr("外推:")))
                cmb_de = self._make_extrap_combo(include_none=True)
                cmb_de.setToolTip(self.tr("Directivity 外推算法"))
                mw = getattr(self, '_mw', None)
                if mw:
                    cur = getattr(mw, '_dir_extrap_method', 'none')
                    idx = cmb_de.findData(cur)
                    if idx >= 0: cmb_de.setCurrentIndex(idx)
                cmb_de.currentIndexChanged.connect(lambda: self._on_dir_extrap_xtr_changed(cmb_de))
                row_de.addWidget(cmb_de)
                row_de.addStretch()
                gl.addLayout(row_de)
                setattr(self, '_cmb_dir_extrap_de_xtr', cmb_de)
            right_layout.addWidget(grp)
        right_layout.addStretch()
        hbox.addWidget(right_box, 1)
        vbox_outer.addLayout(hbox)

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

    def _make_extrap_combo(self, include_none: bool = True):
        """创建外推算法下拉框。include_none=True 时首项为"不外推"。"""
        cmb = QComboBox()
        if include_none:
            cmb.addItem(self.tr("不外推"), "none")
        cmb.addItem(self.tr("线性"), "linear")
        cmb.addItem(self.tr("常数"), "constant")
        cmb.addItem(self.tr("镜像"), "mirror")
        cmb.setCurrentIndex(0)
        return cmb

    @staticmethod
    def _get_checked_keys(checkbox_dict: dict) -> set:
        return {k for k, cb in checkbox_dict.items() if cb.isChecked()}

    def _update_summary(self):
        """摘要已移至下方执行栏显示，此处留空。"""
        pass

    def _on_full_report_toggled(self, checked: bool):
        """Full Report 总开关切换。"""
        if self._mw:
            self._mw._full_report_enabled = checked

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
        _sync_widget(self._rhcp_angle_widget, '_rhcp_lag_config')
        _sync_widget(self._cpxpi_angle_widget, '_cpxpi_lag_config')

        required = set(k for k, cb in self._left_checkboxes.items() if cb.isChecked())
        extra = set(k for k, cb in self._right_checkboxes.items() if cb.isChecked())

        # Gain 联动: 勾选 Gain → 自动包含 lag_single + lag_range
        if "gain" in required:
            required.add("lag_single")
            required.add("lag_range")
        if "gain" in extra:
            extra.add("lag_single")
            extra.add("lag_range")

        # AR 联动: 勾选 AR → 自动包含 ar_single + ar_range
        if "ar" in required:
            required.add("ar_single")
            required.add("ar_range")
        if "ar" in extra:
            extra.add("ar_single")
            extra.add("ar_range")
        mw._required_params = required
        mw._extra_params = extra
        mw._nh_custom_angles = list(self._nh_custom_angles)
        if hasattr(self, '_cmb_dir_extrap_de'):
            cur = self._cmb_dir_extrap_de.currentData()
            mw._dir_extrap_method = cur
            # 同步到右侧 full_report 的独立下拉框
            if hasattr(self, '_cmb_dir_extrap_de_xtr'):
                self._cmb_dir_extrap_de_xtr.blockSignals(True)
                idx = self._cmb_dir_extrap_de_xtr.findData(cur)
                if idx >= 0:
                    self._cmb_dir_extrap_de_xtr.setCurrentIndex(idx)
                self._cmb_dir_extrap_de_xtr.blockSignals(False)

    def _on_dir_extrap_xtr_changed(self, cmb: QComboBox):
        """右侧 full_report 栏 Directivity 外推下拉变更 → 同步到左侧 + MainWindow。"""
        cur = cmb.currentData()
        mw = getattr(self, '_mw', None)
        if mw:
            mw._dir_extrap_method = cur
        if hasattr(self, '_cmb_dir_extrap_de'):
            self._cmb_dir_extrap_de.blockSignals(True)
            idx = self._cmb_dir_extrap_de.findData(cur)
            if idx >= 0:
                self._cmb_dir_extrap_de.setCurrentIndex(idx)
            self._cmb_dir_extrap_de.blockSignals(False)
        self._sync_to_mw()

        if hasattr(mw, '_cmb_freq_source') and mw._cmb_freq_source:
            data = self._cmb_freq_src.currentData()
            idx = mw._cmb_freq_source.findData(data)
            if idx >= 0:
                mw._cmb_freq_source.setCurrentIndex(idx)
        try:
            if hasattr(mw, '_spin_trim_start'):
                mw._spin_trim_start.setValue(self._spin_trim_start.value())
                mw._spin_trim_end.setValue(self._spin_trim_end.value())
            if hasattr(self, '_cmb_extrap'):
                mw._theta_extrap_method = self._cmb_extrap.currentData()
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
        if hasattr(mw, '_rhcp_lag_config'):
            if not self._rhcp_angle_widget:
                from ui.widgets import AnglePickerWidget
                self._rhcp_angle_widget = AnglePickerWidget(self.tr("RHCP 角度"))
            self._rhcp_angle_widget.set_config(mw._rhcp_lag_config)
        if hasattr(mw, '_cpxpi_lag_config'):
            if not self._cpxpi_angle_widget:
                from ui.widgets import AnglePickerWidget
                self._cpxpi_angle_widget = AnglePickerWidget(self.tr("CP-XPI 角度"))
            self._cpxpi_angle_widget.set_config(mw._cpxpi_lag_config)
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
            if hasattr(mw, '_theta_extrap_method') and hasattr(self, '_cmb_extrap'):
                idx = self._cmb_extrap.findData(mw._theta_extrap_method)
                if idx >= 0:
                    self._cmb_extrap.setCurrentIndex(idx)
            elif hasattr(mw, '_cmb_extrapolate'):
                val = mw._cmb_extrapolate.currentData()
                idx = self._cmb_extrap.findData(val) if val else 0
                if idx >= 0:
                    self._cmb_extrap.setCurrentIndex(idx)
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
            "rhcp_lag_config": self._rhcp_angle_widget.get_config() if self._rhcp_angle_widget else LagConfig(),
            "cpxpi_lag_config": self._cpxpi_angle_widget.get_config() if self._cpxpi_angle_widget else LagConfig(),
            "extrapolate": self._cmb_extrap.currentData(),
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

    def get_skip_original(self) -> bool:
        """是否跳过原始步进。"""
        return hasattr(self, '_chk_skip_original') and self._chk_skip_original.isChecked()

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

# ═══════════════════════════════════════════════════════════════
# PatternManagerDialog — 列识别规则 JSON 编辑器
# ═══════════════════════════════════════════════════════════════

class PatternManagerDialog(QDialog):
    """管理 src/param_patterns.json 别名 — 控制列头自动识别规则。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("参数识别规则管理"))
        self.setMinimumSize(900, 600)
        self._dirty = False

        layout = QVBoxLayout(self)
        info = QLabel(self.tr(
            "编辑别名（逗号分隔）。列头包含任一别名即识别为该参数。\n"
            "保存后自动重载，下次加载模板时生效。"))
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; padding: 4px;")
        layout.addWidget(info)

        test_grp = QGroupBox(self.tr("测试匹配"))
        test_row = QHBoxLayout(test_grp)
        test_row.addWidget(QLabel(self.tr("列头:")))
        self._edit_test = QLineEdit()
        self._edit_test.setPlaceholderText(self.tr("输入列头文本，如: RHCP Theta=0(dB)"))
        test_row.addWidget(self._edit_test, 1)
        btn_test = QPushButton(self.tr("测试"))
        btn_test.clicked.connect(self._test_match)
        test_row.addWidget(btn_test)
        self._lbl_test_result = QLabel("")
        test_row.addWidget(self._lbl_test_result)
        layout.addWidget(test_grp)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            self.tr("参数键"), self.tr("英文名"), self.tr("中文名"),
            self.tr("别名 (逗号分隔)"), self.tr("排除词"), self.tr("必须词"),
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        btn_reload = QPushButton(self.tr("重新加载"))
        btn_reload.clicked.connect(self._load)
        btn_row.addWidget(btn_reload)
        btn_save = QPushButton(self.tr("💾 保存"))
        btn_save.setStyleSheet("font-weight:bold;")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._load()

    def _load(self):
        import json, os, sys
        candidates = []
        if getattr(sys, 'frozen', False):
            candidates.append(os.path.join(os.path.dirname(sys.executable), "src", "param_patterns.json"))
        candidates.append(os.path.join(os.path.dirname(__file__), "..", "src", "param_patterns.json"))
        data = {}
        for p in candidates:
            p = os.path.normpath(p)
            if os.path.isfile(p):
                with open(p, encoding='utf-8') as f:
                    data = json.load(f)
                break
        self._data = data
        params = data.get("params", data)
        items = sorted(params.items())
        self._table.setRowCount(len(items))
        for i, (key, info) in enumerate(items):
            self._table.setItem(i, 0, QTableWidgetItem(key))
            self._table.setItem(i, 1, QTableWidgetItem(info.get("label", "")))
            self._table.setItem(i, 2, QTableWidgetItem(info.get("cn", "")))
            aliases = info.get("aliases", [])
            alias_str = ", ".join(aliases) if isinstance(aliases, list) else str(aliases)
            self._table.setItem(i, 3, QTableWidgetItem(alias_str))
            negate = info.get("negate", [])
            neg_str = ", ".join(negate) if isinstance(negate, list) else str(negate)
            self._table.setItem(i, 4, QTableWidgetItem(neg_str))
            extra = info.get("extra_req", [])
            ext_str = ", ".join(extra) if isinstance(extra, list) else str(extra)
            self._table.setItem(i, 5, QTableWidgetItem(ext_str))
        self._dirty = False

    def _save(self):
        import json, os, sys
        params = self._data.get("params", self._data)
        for i in range(self._table.rowCount()):
            key = self._table.item(i, 0).text().strip() if self._table.item(i, 0) else ""
            if not key:
                continue
            alias_str = self._table.item(i, 3).text().strip() if self._table.item(i, 3) else ""
            aliases = [a.strip() for a in alias_str.split(",") if a.strip()]
            neg_str = self._table.item(i, 4).text().strip() if self._table.item(i, 4) else ""
            negate = [n.strip() for n in neg_str.split(",") if n.strip()]
            ext_str = self._table.item(i, 5).text().strip() if self._table.item(i, 5) else ""
            extra = [e.strip() for e in ext_str.split(",") if e.strip()]
            if key in params:
                params[key]["aliases"] = aliases
                params[key]["negate"] = negate
                params[key]["extra_req"] = extra

        candidates = []
        if getattr(sys, 'frozen', False):
            candidates.append(os.path.join(os.path.dirname(sys.executable), "src", "param_patterns.json"))
        candidates.append(os.path.join(os.path.dirname(__file__), "..", "src", "param_patterns.json"))
        for p in candidates:
            p = os.path.normpath(p)
            if os.path.isfile(p):
                with open(p, 'w', encoding='utf-8') as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                self._dirty = False
                import src.excel_reader as er
                er._PARAM_PATTERNS = None
                er.reload_column_patterns()
                QMessageBox.information(self, self.tr("已保存"),
                    self.tr(f"已保存 {self._table.rowCount()} 个参数规则"))
                return
        QMessageBox.warning(self, self.tr("错误"), self.tr("找不到 param_patterns.json"))

    def _test_match(self):
        text = self._edit_test.text().strip()
        if not text:
            self._lbl_test_result.setText("")
            return
        from src.excel_reader import _classify_by_param_patterns, _classify_by_builtin
        result = _classify_by_param_patterns(text)
        if result:
            self._lbl_test_result.setText(f"✓ 匹配: {result}")
            self._lbl_test_result.setStyleSheet("color: green;")
        else:
            result2 = _classify_by_builtin(text, normalize_header(text))
            if result2:
                self._lbl_test_result.setText(f"△ 内置: {result2}")
                self._lbl_test_result.setStyleSheet("color: orange;")
            else:
                self._lbl_test_result.setText("✗ 未匹配")
                self._lbl_test_result.setStyleSheet("color: red;")


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
        self._azimuth_angles_rhcp: List[float] = []
        self._azimuth_angles_lhcp: List[float] = []
        self._antenna_name: str = ""
        self._word_layout_mode: str = "side_by_side"
        self._chart_output_dir: str = ""
        self._chart_output_filename: str = ""
        self._data_output_filename: str = ""
        self._current_mode: int = -1  # 跟踪模式变更
        self._setup_ui()
        self._load_state()
        self._current_mode = getattr(self._mw, '_test_mode', 0) if self._mw else 0

    def _setup_ui(self):
        from src.chart_config import ChartConfig
        labels = ChartConfig.chart_labels()
        mode = getattr(self._mw, '_test_mode', 0) if self._mw else 0
        categories = ChartConfig.chart_categories(mode)

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
        self._azimuth_angles_rhcp: List[float] = []
        self._azimuth_angles_lhcp: List[float] = []
        self._cut_2d_phi_angles: List[float] = []
        self._view_angle_pairs: List[Tuple[float, float]] = []
        self._antenna_name = ""
        self._word_layout_mode = "side_by_side"
        self._chart_output_dir = ""
        self._chart_output_filename = ""
        self._data_output_filename = ""

        # 视角参数默认值（每个3D图表参数对话框中可单独调整）
        self._elev = 30.0; self._azim = -60.0
        self._dpi = 150; self._step_deg = 5.0

        grp_list: list = []

        # ── 外层左右列 (只创建一次, 各包含全部类别) ──
        # 左列: 测试报告
        left_box = QGroupBox()
        left_outer = QVBoxLayout(left_box)
        left_outer.setSpacing(6)
        hdr_l = QHBoxLayout()
        hdr_l.addWidget(QLabel(self.tr("测试报告")))
        self._check_test_report_enable = QCheckBox(self.tr("启用"))
        self._check_test_report_enable.setChecked(True)
        self._check_test_report_enable.toggled.connect(self._on_test_report_toggled)
        hdr_l.addWidget(self._check_test_report_enable)
        hdr_l.addStretch()
        left_outer.addLayout(hdr_l)
        sep_l = QFrame(); sep_l.setFrameShape(QFrame.HLine); sep_l.setFrameShadow(QFrame.Sunken)
        left_outer.addWidget(sep_l)

        # 右列: 额外报告
        right_box = QGroupBox()
        right_outer = QVBoxLayout(right_box)
        right_outer.setSpacing(6)
        hdr_r = QHBoxLayout()
        hdr_r.addWidget(QLabel(self.tr("额外报告")))
        self._check_full_report_enable = QCheckBox(self.tr("启用"))
        self._check_full_report_enable.setChecked(
            getattr(self._mw, '_full_report_enabled', False) if self._mw else False)
        self._check_full_report_enable.toggled.connect(
            lambda checked: setattr(self._mw, '_full_report_enabled', checked) if self._mw else None)
        hdr_r.addWidget(self._check_full_report_enable)
        hdr_r.addStretch()
        right_outer.addLayout(hdr_r)
        sep_r = QFrame(); sep_r.setFrameShape(QFrame.HLine); sep_r.setFrameShadow(QFrame.Sunken)
        right_outer.addWidget(sep_r)

        for cat_name, keys in categories.items():
            # ── 左列: 本类别 ──
            cat_left = QGroupBox(cat_name)
            cat_left.setCheckable(True)
            cat_left.setChecked(True)
            cat_left.setStyleSheet("""
                QGroupBox { font-weight: bold; padding-top: 16px; }
                QGroupBox::indicator { width: 14px; height: 14px; margin-right: 4px; }
            """)
            cat_left.setCursor(Qt.PointingHandCursor)
            cat_left_ly = QVBoxLayout(cat_left)
            cat_left_ly.setSpacing(3)
            self._collapse_map[cat_name] = {"grp": cat_left, "hidden": False}

            self._add_select_all_row(self._chart_required, keys, cat_left_ly)
            # C 类: 俯仰面切面图标题 (在 checkbox 之前)
            for key in keys:
                self._add_chart_checkbox_row(key, labels, self._chart_required, cat_left_ly)
            cat_left_ly.addStretch()
            left_outer.addWidget(cat_left)

            # ── 右列: 本类别 ──
            cat_right = QGroupBox(cat_name)
            cat_right.setCheckable(True)
            cat_right.setChecked(True)
            cat_right.setStyleSheet("""
                QGroupBox { font-weight: bold; padding-top: 16px; }
                QGroupBox::indicator { width: 14px; height: 14px; margin-right: 4px; }
            """)
            cat_right.setCursor(Qt.PointingHandCursor)
            cat_right_ly = QVBoxLayout(cat_right)
            cat_right_ly.setSpacing(3)

            self._add_select_all_row(self._chart_extra, keys, cat_right_ly)
            for key in keys:
                self._add_chart_checkbox_row(key, labels, self._chart_extra, cat_right_ly)
            cat_right_ly.addStretch()
            right_outer.addWidget(cat_right)

            # 记录到 grp_list (用于 scroll 添加)
            grp_list.append(cat_left)
            grp_list.append(cat_right)

            def make_toggle_l(g=cat_left, name=cat_name):
                def toggle(checked):
                    self._collapse_map[name]["hidden"] = not checked
                    # 同步折叠右列同一类别
                    for _g in grp_list:
                        if _g is not g and _g.title() == name:
                            _g.setChecked(checked)
                return toggle
            cat_left.toggled.connect(make_toggle_l(cat_left, cat_name))
            def make_toggle_r(g=cat_right, name=cat_name):
                def toggle(checked):
                    for _g in grp_list:
                        if _g is not g and _g.title() == name:
                            _g.setChecked(checked)
                return toggle
            cat_right.toggled.connect(make_toggle_r(cat_right, cat_name))


        # 输出设置
        out_grp = QGroupBox(self.tr("输出设置"))
        out_layout = QVBoxLayout(out_grp)

        # ── Word 布局 ──
        row_wl = QHBoxLayout()
        btn_word_layout = QPushButton(self.tr("Word 输出布局设置..."))
        btn_word_layout.clicked.connect(self._show_word_layout_dialog)
        row_wl.addWidget(btn_word_layout)
        btn_fr_layout = QPushButton(self.tr("Full Report Word 布局设置..."))
        btn_fr_layout.clicked.connect(lambda: self._show_word_layout_dialog(fr_mode=True))
        row_wl.addWidget(btn_fr_layout)
        row_wl.addStretch()
        out_layout.addLayout(row_wl)

        # 图表标题天线名
        row_ant = QHBoxLayout()
        row_ant.addWidget(QLabel(self.tr("图表标题天线名:")))
        self._edit_antenna_name = QLineEdit()
        self._edit_antenna_name.setPlaceholderText(self.tr("天线名，用于图表标题"))
        self._edit_antenna_name.setMaximumWidth(200)
        self._edit_antenna_name.textChanged.connect(lambda: self._sync_to_mw())
        row_ant.addWidget(self._edit_antenna_name)
        row_ant.addStretch()
        out_layout.addLayout(row_ant)

        # 嵌入/PNG 已移除 — 所有图表统一输出到 Word

        grp_list.append(out_grp)

        # 测试模式选择器（放在滚动区上方，始终可见）
        main_layout = QVBoxLayout(self)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("<b>" + self.tr("测试模式:") + "</b>"))
        self._cmb_test_mode = QComboBox()
        self._cmb_test_mode.addItem("📡 " + self.tr("无源天线"), 0)
        self._cmb_test_mode.addItem("📶 " + self.tr("有源发射 TRP"), 1)
        self._cmb_test_mode.addItem("📻 " + self.tr("有源接收 TIS"), 2)
        cur_mode = getattr(self._mw, '_test_mode', 0) if self._mw else 0
        idx = self._cmb_test_mode.findData(cur_mode)
        if idx >= 0: self._cmb_test_mode.setCurrentIndex(idx)
        self._cmb_test_mode.currentIndexChanged.connect(self._on_chart_mode_changed)
        mode_row.addWidget(self._cmb_test_mode)
        mode_row.addStretch()
        main_layout.addLayout(mode_row)

        # 左右列各独立滚动 (左滚动条在中间, 右滚动条在右侧)
        self._chart_grp_list = grp_list
        scroll_left = QScrollArea()
        scroll_left.setWidgetResizable(True); scroll_left.setFrameShape(QScrollArea.NoFrame)
        scroll_left.setWidget(left_box)
        scroll_right = QScrollArea()
        scroll_right.setWidgetResizable(True); scroll_right.setFrameShape(QScrollArea.NoFrame)
        scroll_right.setWidget(right_box)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(scroll_left)
        splitter.addWidget(scroll_right)
        splitter.setSizes([400, 400])
        # 将 splitter 放入外层容器 (含输出设置)
        outer_w = QWidget()
        outer_lo = QVBoxLayout(outer_w); outer_lo.setContentsMargins(0,0,0,0)
        outer_lo.addWidget(splitter)
        outer_lo.addWidget(out_grp)
        outer_lo.addStretch()
        self._chart_scroll_vbox = outer_lo  # rebuild 用
        main_layout.addWidget(outer_w)


    def _on_chart_mode_changed(self, idx: int):
        """图表配置页测试模式切换 → 重建分类列表。"""
        mode = self._cmb_test_mode.currentData()
        if mode is None: return
        if self._mw:
            self._mw._test_mode = mode
        self._rebuild_chart_categories(mode)

    def _load_state(self):
        if not self._mw:
            return
        mw = self._mw

        if hasattr(mw, 'ui'):
            if hasattr(mw.ui, 'spinElev'):
                self._elev = mw.ui.spinElev.value()
                self._azim = mw.ui.spinAzim.value()
                self._dpi = mw.ui.spinDpi.value()

        if hasattr(mw, '_chart_config_required') and mw._chart_config_required is not None:
            self._step_deg = int(getattr(mw._chart_config_required, 'step_deg', 5))

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
        if hasattr(mw, '_output_config') and mw._output_config is not None:
            az = mw._output_config

            self._antenna_name = az.antenna_name
            self._word_layout_mode = az.word_layout_mode
            self._chart_output_dir = az.chart_output_dir
            self._chart_output_filename = az.chart_output_filename
            self._data_output_filename = az.data_output_filename

            if hasattr(self, '_edit_antenna_name'):
                self._edit_antenna_name.setText(az.antenna_name)

            if hasattr(self, '_spin_azimuth_dpi'):
                self._spin_azimuth_dpi.setValue(az.dpi if az.dpi >= 72 else 100)
            if hasattr(self, '_spin_azimuth_dpi_xtr'):
                self._spin_azimuth_dpi_xtr.setValue(az.dpi if az.dpi >= 72 else 100)
            if hasattr(self, '_combo_az_columns'):
                idx2 = self._spin_az_columns.findData(az.word_columns if az.word_columns in (1, 2) else 2)
                if idx2 >= 0:
                    self._spin_az_columns.setCurrentIndex(idx2)
            if hasattr(self, '_spin_az_img_pct'):
                self._spin_az_img_pct.setValue(az.word_image_width_pct if 10 <= az.word_image_width_pct <= 100 else 100)
            if hasattr(self, '_check_show_caption'):
                self._check_show_caption.setChecked(getattr(az, 'show_caption', True))
            if hasattr(self, '_check_share_ticks'):
                self._check_share_ticks.setChecked(getattr(az, 'share_radial_ticks', False))

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


    # ── Word 输出布局子对话框 ──

    def _show_word_layout_dialog(self, fr_mode: bool = False):
        """Word 输出布局设置: 批量模式 + 图表排序 + 排版参数。

        Args:
            fr_mode: True=Full Report布局, False=普通Word布局
        """
        az = getattr(self._mw, '_output_config', None) if self._mw else None
        prefix = "fr_" if fr_mode else ""
        title = self.tr("Full Report Word 布局设置") if fr_mode else self.tr("Word 输出布局设置")
        cur_mode = getattr(az, f"{prefix}word_layout_mode", "side_by_side") if az else "side_by_side"
        cur_cols = getattr(az, f"{prefix}word_columns", 2) if az else 2
        cur_pct = getattr(az, f"{prefix}word_image_width_pct", 100) if az else 100
        cur_cap = getattr(az, f"{prefix}show_caption", False) if az else False
        cur_hd = getattr(az, f"{prefix}show_heading", True) if az else True

        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(550, 500)
        layout = QVBoxLayout(dlg)
        mode_grp = QGroupBox(self.tr("批量输出模式"))
        mode_layout = QVBoxLayout(mode_grp)
        self._radio_by_freq = QRadioButton(self.tr("按频点: 每频点全部图 → 下一频点"))
        self._radio_by_type = QRadioButton(self.tr("按图表类型: 每类图全频点 → 下一类"))
        self._radio_by_freq.setChecked(cur_mode == "by_freq")
        self._radio_by_type.setChecked(cur_mode in ("by_type", "side_by_side"))
        mode_layout.addWidget(self._radio_by_freq)
        mode_layout.addWidget(self._radio_by_type)
        layout.addWidget(mode_grp)
        sort_grp = QGroupBox(self.tr("图表顺序 (上移/下移调整)"))
        sort_layout = QVBoxLayout(sort_grp)
        self._word_chart_list = QListWidget()
        self._word_chart_list.setDragDropMode(QAbstractItemView.InternalMove)
        self._word_chart_list.setSelectionMode(QAbstractItemView.SingleSelection)
        # \u4ece ChartInstance \u5217\u8868\u8bfb\u53d6\uff08\u552f\u4e00\u6570\u636e\u6e90\uff0c\u4e0e Pipeline \u5171\u4eab\uff09
        from src.chart_plan import ChartCategory
        instances = getattr(self._mw, '_chart_instances', None) or []
        cat_badges = {ChartCategory.A_3D: "3D", ChartCategory.B_FREQ: "\u66f2\u7ebf",
                      ChartCategory.C_2D: "\u5207\u9762", ChartCategory.Z_AZIMUTH: "\u65b9\u4f4d\u9762"}
        active_labels = []
        if instances:
            for ci in sorted(instances, key=lambda x: x.sort_order):
                if not ci.enabled:
                    continue
                badge = cat_badges.get(ci.category, "?")
                active_labels.append(f"[{badge}] {ci.label}")
        if not active_labels:
            active_labels = [self.tr("(\u672a\u9009\u62e9\u4efb\u4f55\u56fe\u8868)")]
        for item in active_labels:
            self._word_chart_list.addItem(item)
        sort_layout.addWidget(self._word_chart_list)
        btn_row = QHBoxLayout()
        btn_up = QPushButton(self.tr("\u2191 \u4e0a\u79fb"))
        btn_down = QPushButton(self.tr("\u2193 \u4e0b\u79fb"))
        btn_reset = QPushButton(self.tr("\u6062\u590d\u9ed8\u8ba4"))
        def _move_item(direction):
            row = self._word_chart_list.currentRow()
            if 0 <= row < self._word_chart_list.count():
                item = self._word_chart_list.takeItem(row)
                new_row = max(0, min(self._word_chart_list.count(), row + direction))
                self._word_chart_list.insertItem(new_row, item)
                self._word_chart_list.setCurrentRow(new_row)
        btn_up.clicked.connect(lambda: _move_item(-1))
        btn_down.clicked.connect(lambda: _move_item(1))
        btn_reset.clicked.connect(lambda: (
            self._word_chart_list.clear(),
            [self._word_chart_list.addItem(item) for item in active_labels]
        ))
        btn_row.addWidget(btn_up); btn_row.addWidget(btn_down)
        btn_row.addWidget(btn_reset); btn_row.addStretch()
        sort_layout.addLayout(btn_row)
        layout.addWidget(sort_grp)

        # ── 排版参数 ──
        fmt_grp = QGroupBox(self.tr("排版参数"))
        fmt_layout = QFormLayout(fmt_grp)
        spin_cols = QSpinBox()
        spin_cols.setRange(1, 6); spin_cols.setValue(cur_cols)
        spin_cols.setPrefix(self.tr("每行 ")); spin_cols.setSuffix(self.tr(" 列"))
        fmt_layout.addRow(self.tr("列数:"), spin_cols)

        spin_pct = QSpinBox()
        spin_pct.setRange(10, 100); spin_pct.setValue(cur_pct)
        spin_pct.setSuffix("%")
        spin_pct.setToolTip(self.tr("图片宽度占列宽的百分比"))
        fmt_layout.addRow(self.tr("图片宽(%):"), spin_pct)

        check_hd = QCheckBox(self.tr("生成章节标题"))
        check_hd.setChecked(cur_hd)
        fmt_layout.addRow("", check_hd)

        check_cap = QCheckBox(self.tr("显示图片题注"))
        check_cap.setChecked(cur_cap)
        fmt_layout.addRow("", check_cap)
        layout.addWidget(fmt_grp)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        def _on_accept_layout():
            mode_val = "by_type" if self._radio_by_type.isChecked() else "by_freq"
            if fr_mode:
                if az:
                    az.fr_word_layout_mode = mode_val
                    az.fr_word_columns = spin_cols.value()
                    az.fr_word_image_width_pct = spin_pct.value()
                    az.fr_show_caption = check_cap.isChecked()
            else:
                self._word_layout_mode = mode_val
                self._az_columns = spin_cols.value()
                self._az_img_pct = spin_pct.value()
                self._az_show_caption = check_cap.isChecked()
                self._az_show_heading = check_hd.isChecked()
            # 将列表顺序回写到 ChartInstance.sort_order
            instances = getattr(self._mw, '_chart_instances', None) or []
            if instances:
                enabled_ids = set()
                for i in range(self._word_chart_list.count()):
                    item_text = self._word_chart_list.item(i).text()
                    # 匹配 label (去掉类别 badge 前缀)
                    for ci in instances:
                        if ci.enabled and item_text.endswith(ci.label):
                            ci.sort_order = i
                            enabled_ids.add(ci.instance_id)
                            break
                # 列表中不存在的实例标记为 disabled
                for ci in instances:
                    if ci.instance_id not in enabled_ids:
                        ci.enabled = False
            self._sync_to_mw()
            dlg.accept()
        btns.accepted.connect(_on_accept_layout)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    def _on_test_report_toggled(self, checked: bool):
        """测试报告总开关: 控制 Word 输出自动选中/取消。"""
        if self._mw:
            fp = getattr(self._mw, '_file_settings_page', None)
            if fp and hasattr(fp, '_check_out_word'):
                fp._check_out_word.setChecked(checked)

    def _sync_to_mw(self):
        """同步当前配置到 MainWindow。"""
        if not self._mw:
            return
        from src.chart_config import ChartConfig
        mw = self._mw

        # 模式变更 → 自动刷新图表分类 (跳过首次初始化)
        new_mode = getattr(mw, '_test_mode', 0)
        if self._current_mode >= 0 and self._current_mode != new_mode:
            self._rebuild_chart_categories(new_mode)

        step_deg = float(max(1, min(30, getattr(self, '_step_deg', 5))))

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

        required.elev = getattr(self, '_elev', 30.0)
        required.azim = getattr(self, '_azim', -60.0)
        required.dpi = getattr(self, '_dpi', 150)
        required.step_deg = getattr(self, '_step_deg', 5.0)
        required.embed_in_excel = False  # 图表统一到 Word
        extra.elev = required.elev
        extra.azim = required.azim
        extra.dpi = required.dpi
        extra.step_deg = required.step_deg
        extra.embed_in_excel = False

        required.gain_chart_angles = list(self._gain_angles)
        required.gain_chart_ranges = list(self._gain_ranges)
        required.ar_chart_angles = list(self._ar_angles)
        required.ar_chart_ranges = list(self._ar_ranges)
        required.cut_2d_phi_angles = list(self._cut_2d_phi_angles)
        for attr in ("_cut_2d_polar_entries", "_cut_2d_rect_entries",
                      "_cut_azimuth_polar_entries", "_cut_azimuth_rect_entries"):
            if hasattr(self, attr):
                setattr(required, attr[1:], list(getattr(self, attr)))
        required.view_angle_pairs = list(self._view_angle_pairs)
        extra.gain_chart_angles = list(self._gain_angles_x)
        extra.gain_chart_ranges = list(self._gain_ranges_x)
        extra.ar_chart_angles = list(self._ar_angles_x)
        extra.ar_chart_ranges = list(self._ar_ranges_x)

        # ── 方位面配置 ──
        from src.output_config import OutputConfig
        existing = getattr(mw, '_output_config', None)
        azimuth = existing if existing is not None else OutputConfig()
        azimuth.antenna_name = self._edit_antenna_name.text().strip() if hasattr(self, '_edit_antenna_name') else ""
        azimuth.word_layout_mode = self._word_layout_mode if hasattr(self, '_word_layout_mode') else "side_by_side"
        azimuth.dpi = self._spin_azimuth_dpi.value() if hasattr(self, '_spin_azimuth_dpi') else 100
        if hasattr(self, '_spin_azimuth_dpi_xtr'):
            azimuth.dpi = self._spin_azimuth_dpi_xtr.value()  # 右侧优先(最后设置)
        azimuth.word_columns = getattr(self, '_az_columns', 2)
        azimuth.word_image_width_pct = getattr(self, '_az_img_pct', 100)
        azimuth.show_caption = getattr(self, '_az_show_caption', False)
        azimuth.show_heading = getattr(self, '_az_show_heading', True)
        azimuth.share_radial_ticks = self._check_share_ticks.isChecked() if hasattr(self, '_check_share_ticks') else False

        # 图表联动已移除 — 用户手动控制每个图表类型

        # 标记角度已由用户配置, 防止 _start_processing 中自动用 LAG 角度覆盖
        azimuth._angles_initialized = True

        mw._output_config = azimuth
        mw._chart_config_required = required
        mw._chart_config_extra = extra
        if hasattr(mw, '_auto_check_output_flags'):
            mw._auto_check_output_flags()

        # 展开为 ChartInstance 列表（单一数据源供 Word 布局 + Pipeline）
        from src.chart_plan import expand_to_instances
        mw._chart_instances = expand_to_instances(
            required, azimuth, mode=getattr(mw, '_test_mode', 0),
            existing_instances=getattr(mw, '_chart_instances', None),
        )

        # 有图表 → 自动开启 Word 输出
        if mw._chart_instances:
            fp = getattr(mw, '_file_settings_page', None)
            if fp and hasattr(fp, '_check_out_word'):
                fp._check_out_word.setChecked(True)

        if hasattr(mw, 'ui'):
            mw.ui.spinElev.setValue(int(getattr(self, '_elev', 30)))
            mw.ui.spinAzim.setValue(int(getattr(self, '_azim', -60)))
            mw.ui.spinDpi.setValue(getattr(self, '_dpi', 150))
            mw.ui.checkEmbedExcel.setChecked(False)  # 图表统一到 Word
            mw.ui.checkSavePng.setChecked(False)

        self.chart_config_changed.emit()

    def _parse_step_deg(self) -> float:
        return float(max(1, min(30, getattr(self, '_step_deg', 5))))

    def _rebuild_chart_categories(self, mode: int):
        """模式变更时重建图表分类组。"""
        if mode == self._current_mode:
            return
        self._current_mode = mode
        from src.chart_config import ChartConfig
        categories = ChartConfig.chart_categories(mode)
        labels = ChartConfig.chart_labels()

        # 保存当前勾选状态
        saved = {}
        for key, cb_dict in [('req', self._chart_required), ('xtr', self._chart_extra)]:
            for k, cb in cb_dict.items():
                saved[k] = cb.isChecked()

        # 清除旧的类别 QGroupBox (保留 left_box/right_box 的 header)
        vbox = self._chart_scroll_vbox
        # vbox 结构: splitter(scroll_left + scroll_right) + out_grp + stretch
        splitter = vbox.itemAt(0).widget()
        if splitter is None:
            return
        scroll_left = splitter.widget(0)
        scroll_right = splitter.widget(1)
        left_box = scroll_left.widget()
        right_box = scroll_right.widget()
        if left_box is None or right_box is None:
            return
        left_outer = left_box.layout()
        right_outer = right_box.layout()
        # 清除内部旧类别 (保留 header: hdr_l + sep_l / hdr_r + sep_r)
        while left_outer.count() > 2:
            item = left_outer.takeAt(2)
            if item.widget():
                item.widget().hide(); item.widget().deleteLater()
        while right_outer.count() > 2:
            item = right_outer.takeAt(2)
            if item.widget():
                item.widget().hide(); item.widget().deleteLater()

        grp_list = []

        for cat_name, keys in categories.items():
            # ── 左列: 本类别 ──
            cat_left = QGroupBox(cat_name)
            cat_left.setCheckable(True); cat_left.setChecked(True)
            cat_left.setStyleSheet("""
                QGroupBox { font-weight: bold; padding-top: 16px; }
                QGroupBox::indicator { width: 14px; height: 14px; margin-right: 4px; }
            """)
            cat_left.setCursor(Qt.PointingHandCursor)
            cat_left_ly = QVBoxLayout(cat_left); cat_left_ly.setSpacing(3)
            self._collapse_map[cat_name] = {"grp": cat_left, "hidden": False}

            self._add_select_all_row(self._chart_required, keys, cat_left_ly)
            for key in keys:
                self._add_chart_checkbox_row(key, labels, self._chart_required, cat_left_ly,
                                              checked=saved.get(key, False))
            cat_left_ly.addStretch()
            left_outer.addWidget(cat_left)

            # ── 右列: 本类别 ──
            cat_right = QGroupBox(cat_name)
            cat_right.setCheckable(True); cat_right.setChecked(True)
            cat_right.setStyleSheet("""
                QGroupBox { font-weight: bold; padding-top: 16px; }
                QGroupBox::indicator { width: 14px; height: 14px; margin-right: 4px; }
            """)
            cat_right.setCursor(Qt.PointingHandCursor)
            cat_right_ly = QVBoxLayout(cat_right); cat_right_ly.setSpacing(3)

            self._add_select_all_row(self._chart_extra, keys, cat_right_ly)
            for key in keys:
                self._add_chart_checkbox_row(key, labels, self._chart_extra, cat_right_ly,
                                              checked=saved.get(key, False))
            cat_right_ly.addStretch()
            right_outer.addWidget(cat_right)

            grp_list.append(cat_left); grp_list.append(cat_right)

            def make_toggle_l(g=cat_left, name=cat_name):
                def toggle(checked):
                    self._collapse_map[name]["hidden"] = not checked
                    for _g in grp_list:
                        if _g is not g and _g.title() == name:
                            _g.setChecked(checked)
                return toggle
            cat_left.toggled.connect(make_toggle_l(cat_left, cat_name))
            def make_toggle_r(g=cat_right, name=cat_name):
                def toggle(checked):
                    for _g in grp_list:
                        if _g is not g and _g.title() == name:
                            _g.setChecked(checked)
                return toggle
            cat_right.toggled.connect(make_toggle_r(cat_right, cat_name))

        self._chart_grp_list = grp_list
        self._chart_grp_list = [g for g in grp_list]  # 用于引用,不需要插入 vbox

    def _add_chart_checkbox_row(self, key: str, labels: dict, target_dict: dict,
                                  layout: QVBoxLayout, checked: bool = False):
        """统一的图表 checkbox 行 — setup + rebuild 共用。"""
        row = QHBoxLayout()
        cb = QCheckBox(labels.get(key, key))
        cb.setChecked(checked)
        cb.toggled.connect(lambda: self._sync_to_mw())
        row.addWidget(cb)
        target_dict[key] = cb
        if key.startswith("pattern_3d_"):
            btn = QPushButton("⚙ " + self.tr("参数")); btn.setFixedWidth(80)
            btn.clicked.connect(lambda checked, k=key: self._show_a3d_param_dialog(k))
            row.addWidget(btn)
        elif key.startswith("chart_") and "_freq" in key:
            btn = QPushButton("⚙ " + self.tr("参数")); btn.setFixedWidth(80)
            btn.clicked.connect(lambda checked, k=key: self._show_bclass_param_dialog(k))
            row.addWidget(btn)
        elif key in ("cut_2d_polar", "cut_2d_rect", "cut_azimuth_polar", "cut_azimuth_rect"):
            btn = QPushButton("⚙ " + self.tr("参数")); btn.setFixedWidth(85)
            btn.clicked.connect(lambda checked, k=key: self._show_cut_param_dialog(k))
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)

    def _show_a3d_param_dialog(self, chart_key: str):
        """A 类 3D 方向图参数设置 — DPI + 采样精度 + 图表列表(每视角=一个图表)。"""
        from src.chart_config import ChartConfig
        label_map = ChartConfig.chart_labels()
        label = label_map.get(chart_key, chart_key)

        # 视角对 → 图表列表格式: [(el, az), ...]
        _pairs: list = [[el, az] for el, az in self._view_angle_pairs] if self._view_angle_pairs else [[30.0, -60.0]]
        _selected_idx = [0]

        dlg = QDialog(self)
        dlg.setWindowTitle(label + " " + self.tr("参数设置"))
        dlg.setMinimumSize(520, 480)
        layout = QVBoxLayout(dlg)

        form = QFormLayout()
        spin_dpi = QSpinBox()
        spin_dpi.setRange(72, 600); spin_dpi.setValue(getattr(self, '_dpi', 150))
        form.addRow(self.tr("DPI:"), spin_dpi)

        spin_step = QSpinBox()
        spin_step.setRange(1, 30); spin_step.setValue(int(getattr(self, '_step_deg', 5)))
        spin_step.setSuffix("°")
        spin_step.setToolTip(self.tr("3D 采样精度: 1°=最细, 30°=最快"))
        form.addRow(self.tr("采样精度:"), spin_step)
        layout.addLayout(form)

        # ── 图表列表 ──
        chart_grp = QGroupBox(self.tr("图表列表（每视角 = 一张 3D 图）"))
        chart_layout = QHBoxLayout(chart_grp)
        chart_list = QListWidget()
        chart_list.setMaximumHeight(100)

        def _rebuild_chart_list():
            chart_list.clear()
            for i, (el, az) in enumerate(_pairs):
                chart_list.addItem(f"图表 {i+1}: el={el:.0f}°, az={az:.0f}°")
            if _selected_idx[0] >= chart_list.count():
                _selected_idx[0] = chart_list.count() - 1
            if _selected_idx[0] >= 0 and chart_list.count() > 0:
                chart_list.setCurrentRow(_selected_idx[0])

        _rebuild_chart_list()
        chart_layout.addWidget(chart_list, 1)

        btn_col = QVBoxLayout()
        btn_add = QPushButton("+")
        btn_add.setFixedWidth(30)
        btn_add.clicked.connect(lambda: (_pairs.append([30.0, -60.0]), _rebuild_chart_list()))
        btn_col.addWidget(btn_add)
        btn_del = QPushButton("✕")
        btn_del.setFixedWidth(30)
        btn_del.clicked.connect(lambda: (
            _pairs.pop(_selected_idx[0]) if len(_pairs) > 1 and 0 <= _selected_idx[0] < len(_pairs) else None,
            _rebuild_chart_list()))
        btn_col.addWidget(btn_del)
        btn_col.addStretch()
        chart_layout.addLayout(btn_col)
        layout.addWidget(chart_grp)

        chart_list.currentRowChanged.connect(lambda i: _selected_idx.__setitem__(0, i) if i >= 0 else None)

        # ── 编辑选中图表 ──
        edit_grp = QGroupBox(self.tr("编辑选中图表的视角"))
        edit_form = QFormLayout(edit_grp)

        def _get_current():
            idx = _selected_idx[0]
            if 0 <= idx < len(_pairs):
                return _pairs[idx]
            return _pairs[0] if _pairs else [30.0, -60.0]

        spin_el = QDoubleSpinBox()
        spin_el.setRange(-90, 90); spin_el.setDecimals(0); spin_el.setSuffix("°")
        spin_az = QDoubleSpinBox()
        spin_az.setRange(-180, 180); spin_az.setDecimals(0); spin_az.setSuffix("°")

        def _refresh_edit():
            cur = _get_current()
            spin_el.blockSignals(True); spin_az.blockSignals(True)
            spin_el.setValue(cur[0]); spin_az.setValue(cur[1])
            spin_el.blockSignals(False); spin_az.blockSignals(False)

        spin_el.valueChanged.connect(lambda v: (_get_current().__setitem__(0, v), _rebuild_chart_list()))
        spin_az.valueChanged.connect(lambda v: (_get_current().__setitem__(1, v), _rebuild_chart_list()))
        chart_list.currentRowChanged.connect(lambda i: _refresh_edit())

        edit_form.addRow(self.tr("仰角:"), spin_el)
        edit_form.addRow(self.tr("方位角:"), spin_az)
        _refresh_edit()
        layout.addWidget(edit_grp)
        freq_picker = self._add_frequency_picker(layout, 'a')
        layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            setattr(self, '_dpi', spin_dpi.value()), self._sync_selected_frequencies(freq_picker.get_selected(), 'a'),
            setattr(self, '_step_deg', float(spin_step.value())),
            self._view_angle_pairs.clear(),
            [self._view_angle_pairs.append((float(el), float(az))) for el, az in _pairs],
            self._sync_to_mw(),
            dlg.accept()))
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    def _show_bclass_param_dialog(self, chart_key: str):
        """B 类频率曲线参数设置 — 图表列表 + 频段间隔 + 双Y轴。"""
        from src.chart_config import ChartConfig
        label_map = ChartConfig.chart_labels()
        chart_label = label_map.get(chart_key, chart_key)

        # 图表列表: 从持久存储恢复
        if not hasattr(self, '_b_class_charts'):
            self._b_class_charts = {}
        _charts: list = self._b_class_charts.get(chart_key)
        if not _charts:
            _charts = [{"label": chart_label, "freq_start": 0, "freq_end": 0}]
        else:
            _charts = [dict(c) for c in _charts]  # deep copy
        _selected_idx = [0]

        dlg = QDialog(self)
        dlg.setWindowTitle(chart_label + " " + self.tr("参数设置"))
        dlg.setMinimumSize(520, 480)
        layout = QVBoxLayout(dlg)

        # 从 OutputConfig 读取当前值
        az = getattr(self._mw, '_output_config', None) if self._mw else None
        cur_gap = az.freq_gap_mhz if az else 10
        cur_dual = az.dual_y_enabled if az else False

        # ── 图表列表 ──
        chart_grp = QGroupBox(self.tr("图表列表（每图表 = 一条独立曲线）"))
        chart_layout = QHBoxLayout(chart_grp)
        chart_list = QListWidget()
        chart_list.setMaximumHeight(100)

        def _rebuild_chart_list():
            chart_list.clear()
            for i, ch in enumerate(_charts):
                label = ch.get("label", f"图表 {i+1}")
                if ch.get("freq_start") and ch.get("freq_end"):
                    label += f" ({ch['freq_start']}-{ch['freq_end']} MHz)"
                chart_list.addItem(label)
            if _selected_idx[0] >= chart_list.count():
                _selected_idx[0] = chart_list.count() - 1
            if _selected_idx[0] >= 0 and chart_list.count() > 0:
                chart_list.setCurrentRow(_selected_idx[0])

        _rebuild_chart_list()
        chart_layout.addWidget(chart_list, 1)

        btn_col = QVBoxLayout()
        btn_add = QPushButton("+")
        btn_add.setFixedWidth(30)
        btn_add.clicked.connect(lambda: (
            _charts.append({"label": f"{chart_label} #{len(_charts)+1}", "freq_start": 0, "freq_end": 0}),
            _rebuild_chart_list()))
        btn_col.addWidget(btn_add)
        btn_del = QPushButton("✕")
        btn_del.setFixedWidth(30)
        btn_del.clicked.connect(lambda: (
            _charts.pop(_selected_idx[0]) if len(_charts) > 1 and 0 <= _selected_idx[0] < len(_charts) else None,
            _rebuild_chart_list()))
        btn_col.addWidget(btn_del)
        btn_col.addStretch()
        chart_layout.addLayout(btn_col)
        layout.addWidget(chart_grp)

        chart_list.currentRowChanged.connect(lambda i: _selected_idx.__setitem__(0, i) if i >= 0 else None)

        # ── 编辑选中图表 ──
        edit_grp = QGroupBox(self.tr("编辑选中图表"))
        edit_form = QFormLayout(edit_grp)

        def _get_current():
            idx = _selected_idx[0]
            if 0 <= idx < len(_charts):
                return _charts[idx]
            return _charts[0]

        edit_label = QLineEdit()
        edit_label.setPlaceholderText(chart_label)
        spin_fs = QSpinBox(); spin_fs.setRange(0, 100000); spin_fs.setSuffix(" MHz"); spin_fs.setSpecialValueText("全频段")
        spin_fe = QSpinBox(); spin_fe.setRange(0, 100000); spin_fe.setSuffix(" MHz"); spin_fe.setSpecialValueText("全频段")

        def _refresh_edit():
            cur = _get_current()
            edit_label.blockSignals(True); spin_fs.blockSignals(True); spin_fe.blockSignals(True)
            edit_label.setText(cur.get("label", ""))
            spin_fs.setValue(cur.get("freq_start", 0)); spin_fe.setValue(cur.get("freq_end", 0))
            edit_label.blockSignals(False); spin_fs.blockSignals(False); spin_fe.blockSignals(False)

        edit_label.textChanged.connect(lambda t: (_get_current().__setitem__("label", t), _rebuild_chart_list()))
        spin_fs.valueChanged.connect(lambda v: (_get_current().__setitem__("freq_start", v), _rebuild_chart_list()))
        spin_fe.valueChanged.connect(lambda v: (_get_current().__setitem__("freq_end", v), _rebuild_chart_list()))
        chart_list.currentRowChanged.connect(lambda i: _refresh_edit())

        edit_form.addRow(self.tr("名称:"), edit_label)
        edit_form.addRow(self.tr("频段起:"), spin_fs)
        edit_form.addRow(self.tr("频段止:"), spin_fe)
        _refresh_edit()
        layout.addWidget(edit_grp)

        # ── 全局参数 ──
        global_grp = QGroupBox(self.tr("全局参数"))
        global_form = QFormLayout(global_grp)
        spin_gap = QSpinBox(); spin_gap.setRange(0, 999); spin_gap.setValue(cur_gap)
        spin_gap.setToolTip(self.tr("0=不打断单轴；>0=相邻频点差超此值时分段绘制"))
        global_form.addRow(self.tr("频段间隔 (MHz):"), spin_gap)
        check_dual = QCheckBox(self.tr("启用双Y轴配对"))
        check_dual.setChecked(cur_dual)
        check_dual.setToolTip(self.tr("Efficiency%+Gain 和 Directivity+TRP 共用双Y轴"))
        global_form.addRow("", check_dual)
        layout.addWidget(global_grp)
        freq_picker = self._add_frequency_picker(layout, 'b')
        layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            self._b_class_charts.__setitem__(chart_key, _charts),
            setattr(az, 'freq_gap_mhz', spin_gap.value()) if az else None,
            setattr(az, 'dual_y_enabled', check_dual.isChecked()) if az else None,
            self._sync_to_mw(), self._sync_selected_frequencies(freq_picker.get_selected(), 'b'),
            dlg.accept()))
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    def _open_data_angle_popup(self, target: str):
        """打开天线参数页的角度配置弹窗 (统一数据源)。"""
        # 找到 AntennaParamsPage 并调用其 _show_angle_popup
        ant_page = getattr(self._mw, '_antenna_params_page', None) if self._mw else None
        if ant_page and hasattr(ant_page, '_show_angle_popup'):
            ant_page._show_angle_popup(target)
        self._sync_to_mw()

    def _show_chart_angle_popup(self, chart_key: str, is_left: bool = True):
        """已过时 — 使用 _open_data_angle_popup 代替 (统一角度配置)"""
        target = "ar" if chart_key == "chart_ar_freq" else "gain"
        self._open_data_angle_popup(target)

    def _show_view_angle_popup(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("多视角"))
        dlg.setMinimumSize(500, 400)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(self.tr("添加多组 (仰角, 方位角) 视角对:")))
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels([self.tr("仰角 (°)"), self.tr("方位角 (°)")])
        layout.addWidget(table)
        from ui.layout_utils import auto_size_dialog
        auto_size_dialog(dlg, 520, 460)
        btn_row = QHBoxLayout()
        btn_add = QPushButton(self.tr("+ 添加"))
        btn_add.clicked.connect(lambda: (table.insertRow(table.rowCount()),
            table.setItem(table.rowCount()-1, 0, QTableWidgetItem("30")),
            table.setItem(table.rowCount()-1, 1, QTableWidgetItem("-60"))))
        btn_row.addWidget(btn_add)
        btn_del = QPushButton(self.tr("删除选中"))
        btn_del.clicked.connect(lambda: table.removeRow(table.currentRow()) if table.currentRow() >= 0 else None)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            self._view_angle_pairs.clear(),
            [self._view_angle_pairs.append(
                (float(table.item(r,0).text() if table.item(r,0) else 30),
                 float(table.item(r,1).text() if table.item(r,1) else -60))
            ) for r in range(table.rowCount())],
            self._sync_to_mw(), dlg.accept()))
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    def _show_cut_param_dialog(self, chart_key: str = "cut_2d_polar"):
        """2D 切面图参数弹窗 — 参照 azimuth 角度弹窗模式。"""
        import copy

        is_azimuth = "azimuth" in chart_key
        angle_label = "Theta" if is_azimuth else "Phi"
        default_angle = 30.0 if is_azimuth else 0.0
        entry_attr = f"_{chart_key}_entries"

        current = getattr(self._mw, '_chart_config_required', None) if self._mw else None
        raw = getattr(current, chart_key + '_entries', None) if current else None
        if raw:
            _entries: list = copy.deepcopy(raw)  # [(param, [angles]), ...]
        else:
            _entries = []

        dlg = QDialog(self)
        fmt_name = "直角坐标" if "rect" in chart_key else "极坐标"
        dir_name = "方位面" if is_azimuth else "俯仰面"
        dlg.setWindowTitle(self.tr(f"{fmt_name}{dir_name}切面图参数"))
        dlg.setMinimumSize(560, 520)
        layout = QVBoxLayout(dlg)

        # ── 图表列表 ──
        chart_grp = QGroupBox(self.tr("图表列表"))
        chart_lo = QHBoxLayout(chart_grp)
        chart_list = QListWidget()
        chart_list.setMaximumHeight(100)
        _sel_idx = [0]

        def _rebuild_list():
            chart_list.clear()
            for i, e in enumerate(_entries):
                pname = {"gain": "Gain", "ar": "AR", "rhcp": "RHCP", "lhcp": "LHCP"}.get(e[0], e[0])
                ang = ", ".join(f"{a:.0f}°" for a in sorted(set(e[1]))) if e[1] else "(空)"
                chart_list.addItem(f"图表 {i+1}: {pname} — {ang}")
            if _sel_idx[0] >= chart_list.count():
                _sel_idx[0] = max(0, chart_list.count() - 1)
            if chart_list.count() > 0:
                chart_list.setCurrentRow(_sel_idx[0])

        _rebuild_list()
        chart_lo.addWidget(chart_list, 1)
        btn_col = QVBoxLayout()
        btn_add_chart = QPushButton("+"); btn_add_chart.setFixedWidth(30)
        btn_add_chart.clicked.connect(lambda: (
            _entries.append((cmb_param.currentData(), [])), _rebuild_list()))
        btn_col.addWidget(btn_add_chart)
        btn_del_chart = QPushButton("✕"); btn_del_chart.setFixedWidth(30)
        btn_del_chart.clicked.connect(lambda: (
            _entries.pop(_sel_idx[0]) if len(_entries) > 1 and 0 <= _sel_idx[0] < len(_entries) else None,
            _rebuild_list()))
        btn_col.addWidget(btn_del_chart); btn_col.addStretch()
        chart_lo.addLayout(btn_col)
        layout.addWidget(chart_grp)
        chart_list.currentRowChanged.connect(lambda i: (_sel_idx.__setitem__(0, i), _refresh_editor()) if i >= 0 else None)

        def _get_current():
            idx = _sel_idx[0]
            if 0 <= idx < len(_entries):
                return _entries[idx]
            return _entries[0] if _entries else ("gain", [])

        # ── 参数选择 ──
        param_row = QHBoxLayout()
        param_row.addWidget(QLabel(self.tr("天线参数:")))
        cmb_param = QComboBox()
        for key, defn in [("gain", "Gain"), ("ar", "AR"), ("rhcp", "RHCP"), ("lhcp", "LHCP")]:
            cmb_param.addItem(defn, key)
        param_row.addWidget(cmb_param)
        param_row.addStretch()
        layout.addLayout(param_row)

        # ── 角度编辑区 ──
        edit_grp = QGroupBox(self.tr(f"编辑选中图表的 {angle_label} 角度"))
        edit_lo = QVBoxLayout(edit_grp)
        tags_lo = QVBoxLayout()

        def _refresh_editor():
            while tags_lo.count():
                item = tags_lo.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            cur = _get_current()
            cur_angles = cur[1] if cur else []
            # 同步下拉框
            for i in range(cmb_param.count()):
                if cmb_param.itemData(i) == cur[0]:
                    cmb_param.setCurrentIndex(i); break
            if cur_angles:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
                scroll.setMaximumHeight(100)
                tags = QWidget()
                fl = FlowLayout(tags)
                for a in sorted(set(cur_angles)):
                    row_w = QWidget()
                    h = QHBoxLayout(row_w); h.setContentsMargins(2, 1, 2, 1); h.setSpacing(2)
                    h.addWidget(QLabel(f"{a:.0f}°"))
                    btn_x = QPushButton("✕"); btn_x.setFixedSize(20, 20)
                    btn_x.clicked.connect(lambda checked, angle=a: (
                        _get_current()[1].remove(angle), _refresh_editor(), _rebuild_list()))
                    h.addWidget(btn_x); h.addStretch()
                    fl.addWidget(row_w)
                scroll.setWidget(tags)
                tags_lo.addWidget(scroll)
        _refresh_editor()
        edit_lo.addLayout(tags_lo)

        # 添加角度
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel(self.tr(f"添加 {angle_label} 角度:")))
        spin_angle = QDoubleSpinBox()
        spin_angle.setRange(-180, 360); spin_angle.setValue(default_angle)
        spin_angle.setSuffix("°"); spin_angle.setDecimals(0)
        add_row.addWidget(spin_angle)
        btn_add_angle = QPushButton(self.tr("添加"))
        btn_add_angle.clicked.connect(lambda: (
            _get_current()[1].append(spin_angle.value()),
            _refresh_editor(), _rebuild_list(),
        ))
        add_row.addWidget(btn_add_angle)
        add_row.addStretch()
        edit_lo.addLayout(add_row)

        # 批量生成
        batch_row = QHBoxLayout()
        spin_start = QDoubleSpinBox(); spin_start.setRange(-180, 360)
        spin_start.setValue(0); spin_start.setSuffix("°"); spin_start.setDecimals(0)
        spin_end = QDoubleSpinBox(); spin_end.setRange(-180, 360)
        spin_end.setValue(90); spin_end.setSuffix("°"); spin_end.setDecimals(0)
        spin_step = QDoubleSpinBox(); spin_step.setRange(1, 180)
        spin_step.setValue(10); spin_step.setSuffix("°"); spin_step.setDecimals(0)
        batch_row.addWidget(QLabel(self.tr("起:"))); batch_row.addWidget(spin_start)
        batch_row.addWidget(QLabel(self.tr("止:"))); batch_row.addWidget(spin_end)
        batch_row.addWidget(QLabel(self.tr("步:"))); batch_row.addWidget(spin_step)
        btn_gen = QPushButton(self.tr("生成"))
        btn_gen.clicked.connect(lambda: (
            [_get_current()[1].append(float(a)) for a in
             np.linspace(spin_start.value(), spin_end.value(),
                         max(1, int((spin_end.value()-spin_start.value())/
                                    max(1, spin_step.value()))+1))
             if float(a) not in _get_current()[1]],
            _refresh_editor(), _rebuild_list(),
        ))
        batch_row.addWidget(btn_gen); batch_row.addStretch()
        edit_lo.addLayout(batch_row)
        layout.addWidget(edit_grp)

        # ── 参数更新 ──
        btn_upd = QPushButton(self.tr("更新选中图表参数"))
        btn_upd.clicked.connect(lambda: (
            _get_current().__setitem__(0, cmb_param.currentData()),
            _rebuild_list(),
        ))
        layout.addWidget(btn_upd)

        # ── DPI ──
        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel(self.tr("DPI:")))
        spin_dpi = QSpinBox(); spin_dpi.setRange(72, 600)
        spin_dpi.setValue(getattr(current, 'dpi', 150) if current else 150)
        dpi_row.addWidget(spin_dpi); dpi_row.addStretch()
        layout.addLayout(dpi_row)
        freq_picker = self._add_frequency_picker(layout, 'c')

        # ── 按钮: OK/Cancel 后保存 (避免 lambda 闭包) ──
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        if dlg.exec() == QDialog.Accepted:
            setattr(self, entry_attr, list(_entries))
            setattr(self, '_dpi', spin_dpi.value())
            self._sync_to_mw()
            self._sync_selected_frequencies(freq_picker.get_selected(), 'c')

    def _show_2d_phi_angle_popup(self):
        """弹出 2D 俯仰面切面 Phi 角度选择窗口 — 图表列表模式（每 phi = 一个图表）。"""
        import copy
        _charts: list = copy.deepcopy(self._cut_2d_phi_angles) if self._cut_2d_phi_angles else [0.0, 90.0]
        # 兼容旧格式: 平列表转为图表列表（每角度一个图表）
        if _charts and not isinstance(_charts[0], list):
            _charts = [[float(a)] for a in _charts]
        _selected_idx = [0]

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("选择俯仰面切图 Phi 角度"))
        dlg.setMinimumSize(520, 480)
        layout = QVBoxLayout(dlg)

        # ── 图表列表 ──
        chart_grp = QGroupBox(self.tr("图表列表（每图表 = 一张切面图）"))
        chart_layout = QHBoxLayout(chart_grp)
        chart_list = QListWidget()
        chart_list.setMaximumHeight(100)

        def _rebuild_chart_list():
            chart_list.clear()
            for i, ch in enumerate(_charts):
                if ch:
                    label = f"图表 {i+1}: φ={ch[0]:.0f}°"
                else:
                    label = f"图表 {i+1}: (空)"
                chart_list.addItem(label)
            if _selected_idx[0] >= chart_list.count():
                _selected_idx[0] = chart_list.count() - 1
            if _selected_idx[0] >= 0 and chart_list.count() > 0:
                chart_list.setCurrentRow(_selected_idx[0])

        _rebuild_chart_list()
        chart_layout.addWidget(chart_list, 1)

        btn_col = QVBoxLayout()
        btn_add = QPushButton("+")
        btn_add.setFixedWidth(30)
        btn_add.clicked.connect(lambda: (_charts.append([0.0]), _rebuild_chart_list()))
        btn_col.addWidget(btn_add)
        btn_del = QPushButton("✕")
        btn_del.setFixedWidth(30)
        btn_del.clicked.connect(lambda: (
            _charts.pop(_selected_idx[0]) if len(_charts) > 1 and 0 <= _selected_idx[0] < len(_charts) else None,
            _rebuild_chart_list()))
        btn_col.addWidget(btn_del)
        btn_col.addStretch()
        chart_layout.addLayout(btn_col)
        layout.addWidget(chart_grp)

        chart_list.currentRowChanged.connect(lambda i: _selected_idx.__setitem__(0, i) if i >= 0 else None)

        # ── 编辑选中图表 ──
        edit_grp = QGroupBox(self.tr("编辑选中图表的 Phi 角度"))
        edit_layout = QVBoxLayout(edit_grp)

        def _get_current():
            idx = _selected_idx[0]
            if 0 <= idx < len(_charts):
                return _charts[idx]
            return _charts[0] if _charts else [0.0]

        spin_phi = QDoubleSpinBox()
        spin_phi.setRange(0, 360); spin_phi.setDecimals(1); spin_phi.setSuffix("°")

        def _refresh_edit():
            cur = _get_current()
            spin_phi.blockSignals(True)
            spin_phi.setValue(cur[0] if cur else 0.0)
            spin_phi.blockSignals(False)

        spin_phi.valueChanged.connect(lambda v: (
            (_get_current().__setitem__(0, v) if _get_current() else _get_current().append(v)),
            _rebuild_chart_list()))
        chart_list.currentRowChanged.connect(lambda i: _refresh_edit())
        _refresh_edit()

        phi_row = QHBoxLayout()
        phi_row.addWidget(QLabel(self.tr("Phi:")))
        phi_row.addWidget(spin_phi)
        phi_row.addStretch()
        edit_layout.addLayout(phi_row)

        # 步进批量生成（追加到选中图表）
        step_grp = QGroupBox(self.tr("步进批量生成"))
        step_layout = QHBoxLayout(step_grp)
        spin_start = QDoubleSpinBox()
        spin_start.setRange(0, 360); spin_start.setDecimals(1); spin_start.setSuffix("°"); spin_start.setValue(0)
        spin_end = QDoubleSpinBox()
        spin_end.setRange(0, 360); spin_end.setDecimals(1); spin_end.setSuffix("°"); spin_end.setValue(180)
        spin_step = QDoubleSpinBox()
        spin_step.setRange(1, 90); spin_step.setDecimals(1); spin_step.setSuffix("°"); spin_step.setValue(45)
        step_layout.addWidget(QLabel(self.tr("起:"))); step_layout.addWidget(spin_start)
        step_layout.addWidget(QLabel(self.tr("止:"))); step_layout.addWidget(spin_end)
        step_layout.addWidget(QLabel(self.tr("步:"))); step_layout.addWidget(spin_step)
        btn_gen = QPushButton(self.tr("生成"))
        btn_gen.clicked.connect(lambda: (
            [_charts.append([float(a)]) for a in
             np.linspace(spin_start.value(), spin_end.value(),
                         max(1, int((spin_end.value()-spin_start.value())/max(1, spin_step.value()))+1))
             if not any(abs(float(a) - c[0]) < 0.01 for c in _charts)],
            _rebuild_chart_list()))
        step_layout.addWidget(btn_gen); step_layout.addStretch()
        edit_layout.addWidget(step_grp)
        layout.addWidget(edit_grp)
        freq_picker = self._add_frequency_picker(layout, 'c')
        layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            self._cut_2d_phi_angles.clear(),
            self._cut_2d_phi_angles.extend([ch[0] for ch in _charts if ch]),
            self._sync_to_mw(), self._sync_selected_frequencies(freq_picker.get_selected(), 'c'),
            dlg.accept()))
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()
        dlg.exec()
        self._sync_to_mw()


    def _add_frequency_picker(self, layout: QVBoxLayout, cat: str = "a"):
        """构建频点选择组件 — 下级弹窗模式。返回 picker adapter。"""
        freq_grp = QGroupBox(self.tr("频点选择"))
        freq_lo = QVBoxLayout(freq_grp)

        # 加载全部频点
        all_freqs = set()
        ds_map = getattr(self._mw, '_cached_datasource_map', None) if self._mw else None
        if ds_map:
            for ds in ds_map.values():
                if hasattr(ds, 'frequencies'):
                    all_freqs.update(ds.frequencies)
        if not all_freqs and self._mw and getattr(self._mw, '_data_file_paths', None):
            from src.datasource import DataSource
            for fp in self._mw._data_file_paths[:3]:
                try:
                    ds = DataSource.from_path(fp)
                    if hasattr(ds, 'frequencies'):
                        all_freqs.update(ds.frequencies)
                except Exception:
                    pass
        all_freqs = sorted(all_freqs)

        # 已选频点
        cfg = getattr(self._mw, '_chart_config_required', None) if self._mw else None
        _selected = list(getattr(cfg, f"selected_frequencies_{cat}", [])) if cfg else []

        # 摘要显示
        row = QHBoxLayout()
        self._freq_summary_label = QLabel()
        self._freq_summary_label.setStyleSheet("color: #888; font-size: 10pt;")
        row.addWidget(self._freq_summary_label, 1)

        btn_open = QPushButton(self.tr("选择频点..."))
        def _open_dialog():
            from ui.widgets import FrequencyPickerDialog
            dlg = FrequencyPickerDialog(all_freqs, _selected, parent=self)
            if dlg.exec() == QDialog.Accepted:
                _selected.clear()
                _selected.extend(dlg.get_selected())
                self._update_freq_summary()
        btn_open.clicked.connect(_open_dialog)
        row.addWidget(btn_open)
        freq_lo.addLayout(row)

        def _update_summary():
            if _selected:
                if len(_selected) <= 8:
                    self._freq_summary_label.setText(
                        self.tr("已选: ") + ", ".join(f"{f:.0f} MHz" for f in _selected))
                else:
                    self._freq_summary_label.setText(
                        self.tr(f"已选 {len(_selected)} 个频点"))
            else:
                self._freq_summary_label.setText(self.tr("(全部频点)"))

        self._update_freq_summary = _update_summary
        _update_summary()

        layout.addWidget(freq_grp)

        # Adapter: 提供 get_selected() 接口兼容旧调用
        class _Adapter:
            def get_selected(self):
                return list(_selected)
        return _Adapter()

    def _sync_selected_frequencies(self, freqs: list[float], cat: str = "a"):
        """同步频点到 ChartConfig。cat: 'a'=A类, 'b'=B类, 'c'=C类"""
        attr = f"selected_frequencies_{cat}"
        if not self._mw:
            return
        if hasattr(self._mw, '_chart_config_required') and self._mw._chart_config_required:
            setattr(self._mw._chart_config_required, attr, list(freqs))
        if hasattr(self._mw, '_chart_config_extra') and self._mw._chart_config_extra:
            setattr(self._mw._chart_config_extra, attr, list(freqs))

    # ── 公共接口 ──

    def get_chart_config(self) -> tuple:
        """返回 (chart_config_required, chart_config_extra)。"""
        from src.chart_config import ChartConfig

        def _build(required_map, extra_map, gain_angles, gain_ranges, ar_angles, ar_ranges):
            cfg = ChartConfig()
            for key in ChartConfig.all_chart_keys():
                setattr(cfg, key, required_map.get(key, QCheckBox()).isChecked())
            cfg.elev = getattr(self, '_elev', 30.0)
            cfg.azim = getattr(self, '_azim', -60.0)
            cfg.dpi = getattr(self, '_dpi', 150)
            cfg.step_deg = self._parse_step_deg()
            cfg.embed_in_excel = False  # 图表统一到 Word
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

# ═══════════════════════════════════════════════════════════════
# Docx 模板 SDT 工具箱
# ═══════════════════════════════════════════════════════════════

class DocxTemplateToolbox(QDialog):
    """.docx 模板分析 + SDT tag 推荐 + 插入。"""

    def __init__(self, parent=None, docx_path=""):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Docx 模板 SDT 工具箱"))
        self.resize(1000, 700)
        self.setMinimumSize(800, 550)
        self._docx_path = docx_path
        self._positions = []
        self._setup_ui()
        if docx_path and Path(docx_path).exists():
            self._edit_path.setText(docx_path)
            self._scan()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        grp = QGroupBox(self.tr("Word 模板"))
        gr = QHBoxLayout(grp)
        self._edit_path = QLineEdit()
        self._edit_path.setPlaceholderText(self.tr("选择 .docx 模板文件..."))
        gr.addWidget(self._edit_path, 1)
        btn_browse = QPushButton(self.tr("浏览..."))
        btn_browse.clicked.connect(self._browse)
        gr.addWidget(btn_browse)
        btn_scan = QPushButton(self.tr("扫描"))
        btn_scan.clicked.connect(self._scan)
        gr.addWidget(btn_scan)
        layout.addWidget(grp)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            self.tr("#"), self.tr("位置"), self.tr("类型"), self.tr("示例文本"),
            self.tr("推荐 Tag"), self.tr("确认 Tag"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 40)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._table.setColumnWidth(1, 150)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._table.setColumnWidth(2, 70)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self._table.setColumnWidth(4, 160)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self._table.setColumnWidth(5, 160)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

        self._lbl_summary = QLabel("")
        layout.addWidget(self._lbl_summary)

        btn_row = QHBoxLayout()
        btn_rule = QPushButton(self.tr("规则自动匹配"))
        btn_rule.clicked.connect(self._rule_match)
        btn_row.addWidget(btn_rule)
        btn_llm = QPushButton(self.tr("LLM 智能推荐"))
        btn_llm.clicked.connect(self._llm_suggest)
        btn_row.addWidget(btn_llm)
        btn_row.addStretch()
        btn_insert = QPushButton(self.tr("插入 SDT 并保存"))
        btn_insert.setStyleSheet("font-weight:bold;")
        btn_insert.clicked.connect(self._insert_and_save)
        btn_row.addWidget(btn_insert)
        btn_close = QPushButton(self.tr("关闭"))
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择 Word 模板"), "",
            self.tr("Word 文档 (*.docx)"))
        if path:
            if path.lower().endswith('.doc') and not path.lower().endswith('.docx'):
                QMessageBox.warning(self, self.tr("格式不支持"),
                    self.tr("不支持 .doc 格式。请用 Word 另存为 .docx 后再使用。"))
                return
            self._edit_path.setText(path)
            self._docx_path = path
            self._scan()

    def _scan(self):
        path = self._edit_path.text().strip()
        if not path or not Path(path).exists():
            return
        try:
            from src.docx_sdt_inserter import scan_docx
            self._positions = scan_docx(path)
        except Exception as e:
            QMessageBox.warning(self, self.tr("扫描失败"), str(e))
            return
        self._populate_table()
        tables = sum(1 for p in self._positions if "table" in p.pos_type)
        images = sum(1 for p in self._positions if p.pos_type == "image")
        self._lbl_summary.setText(
            self.tr("共 {} 个表格, {} 张图片").format(tables, images))

    def _populate_table(self):
        self._table.setRowCount(len(self._positions))
        for i, p in enumerate(self._positions):
            self._table.setItem(i, 0, QTableWidgetItem(str(p.index + 1)))
            self._table.setItem(i, 1, QTableWidgetItem(p.location))
            self._table.setItem(i, 2, QTableWidgetItem(p.pos_type))
            self._table.setItem(i, 3, QTableWidgetItem(p.sample_text[:80]))
            self._table.setItem(i, 4, QTableWidgetItem(p.suggested_tag))
            self._table.setItem(i, 5, QTableWidgetItem(p.confirmed_tag))

    def _rule_match(self):
        try:
            from src.llm_tagger import rule_based_suggest
            n = rule_based_suggest(self._positions)
        except Exception as e:
            QMessageBox.warning(self, self.tr("匹配失败"), str(e))
            return
        self._populate_table()
        self._lbl_summary.setText(
            self.tr("规则匹配: {}/{} 个已推荐").format(n, len(self._positions)))

    def _llm_suggest(self):
        from src.config_manager import get_config_manager
        cfg = get_config_manager()
        llm = getattr(cfg.config, 'llm', None)
        if not llm or not llm.enabled:
            reply = QMessageBox.question(self, self.tr("LLM 未配置"),
                self.tr("尚未配置 AI API。是否打开系统设置？"),
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                p = self.parent()
                while p and not hasattr(p, '_data_file_paths'):
                    p = p.parent()
                from ui.dialogs import SystemSettingsDialog
                SystemSettingsDialog(p).exec()
            return
        try:
            from src.llm_tagger import suggest_tags_with_llm
            n = suggest_tags_with_llm(
                self._positions, llm.api_base,
                getattr(llm, '_api_key', ''), llm.model)
        except Exception as e:
            QMessageBox.warning(self, self.tr("LLM 失败"), str(e))
            return
        self._populate_table()
        self._lbl_summary.setText(self.tr("LLM: {} 个新推荐").format(n))

    def _insert_and_save(self):
        for i in range(self._table.rowCount()):
            item5 = self._table.item(i, 5)
            if item5 and item5.text().strip():
                self._positions[i].confirmed_tag = item5.text().strip()
            else:
                item4 = self._table.item(i, 4)
                if item4 and item4.text().strip():
                    self._positions[i].confirmed_tag = item4.text().strip()
        confirmed = [p for p in self._positions if p.confirmed_tag.strip()]
        if not confirmed:
            QMessageBox.information(self, self.tr("提示"),
                self.tr("请先确认至少一个 SDT tag。"))
            return
        out_path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存带 SDT 的模板"),
            str(Path(self._docx_path).parent /
                (Path(self._docx_path).stem + "_SDT.docx")),
            self.tr("Word 文档 (*.docx)"))
        if not out_path:
            return
        try:
            from src.docx_sdt_inserter import insert_sdt_tags
            insert_sdt_tags(self._docx_path, self._positions, out_path)
        except Exception as e:
            QMessageBox.warning(self, self.tr("插入失败"), str(e))
            return
        msg = self.tr("已插入 {} 个 SDT tag 到:").format(len(confirmed))
        QMessageBox.information(self, self.tr("完成"), msg + "\n" + out_path)

# ═══════════════════════════════════════════════════════════════
# Word 模板分屏预览对话框
# ═══════════════════════════════════════════════════════════════




class WordTemplatePreviewDialog(QDialog):
    """Word 模板分屏预览: 左=文档 + 右=SDT Tag 树。"""

    def __init__(self, parent, path: str, existing_tags: set, positions: list,
                 multi_antenna_cfg=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Word 模板预览 — SDT 标注与配置"))
        self.resize(1000, 700)
        self.setMinimumSize(800, 500)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self._path = path
        self._existing_tags = existing_tags
        self._positions = positions
        self._multi_cfg = multi_antenna_cfg
        self._custom_tags = self._load_custom_tags()
        self._setup_ui()
        self._build_document_view()
        self._build_tag_tree()

    def _setup_ui(self):
        layout = QVBoxLayout(self); layout.setSpacing(6)
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel(f"📄 {Path(self._path).name}"))
        hdr.addStretch()
        n_sugg = len([p for p in self._positions if p.suggested_tag])
        self._lbl_summary = QLabel(self.tr("已设定:{0} | 建议:{1}").format(len(self._existing_tags), n_sugg))
        hdr.addWidget(self._lbl_summary)
        layout.addLayout(hdr)
        splitter = QSplitter(Qt.Horizontal); splitter.setChildrenCollapsible(False)
        self._doc_browser = QTextBrowser(); self._doc_browser.setOpenExternalLinks(False)
        self._doc_browser.setObjectName("wordPreviewBrowser")
        # 跟随系统主题
        from src.config_manager import get_config_manager
        cfg = get_config_manager()
        is_dark = cfg.config.theme == "dark"
        bg = "#1e1e1e" if is_dark else "#ffffff"
        fg = "#d4d4d4" if is_dark else "#000000"
        self._doc_browser.setStyleSheet(f"QTextBrowser {{ background-color: {bg}; color: {fg}; border: none; }}")
        self._theme_bg = bg
        self._theme_fg = fg
        splitter.addWidget(self._doc_browser)
        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(4,0,0,0); rl.setSpacing(4)
        ant_row = QHBoxLayout()
        ant_row.addWidget(QLabel(self.tr("当前天线:")))
        self._cmb_antenna = QComboBox(); self._cmb_antenna.addItem("", "")
        if self._multi_cfg:
            for ant in self._multi_cfg.antennas:
                self._cmb_antenna.addItem(f"{ant.name} ({['无源','有源发射','有源接收'][ant.test_mode]})", ant.name)
        self._cmb_antenna.currentIndexChanged.connect(self._on_antenna_changed)
        ant_row.addWidget(self._cmb_antenna, 1); rl.addLayout(ant_row)
        self._edit_search = QLineEdit(); self._edit_search.setPlaceholderText(self.tr("搜索 tag..."))
        self._edit_search.textChanged.connect(self._on_search); rl.addWidget(self._edit_search)
        self._tag_tree = QTreeWidget(); self._tag_tree.setHeaderLabels([self.tr("SDT Tag")])
        self._tag_tree.setAlternatingRowColors(True)
        self._tag_tree.itemDoubleClicked.connect(self._on_tag_double_clicked)
        rl.addWidget(self._tag_tree, 1)
        apply_row = QHBoxLayout()
        btn_apply = QPushButton("✅ " + self.tr("应用选中 Tag"))
        btn_apply.setStyleSheet("font-weight:bold;color:#2e7d32;")
        btn_apply.clicked.connect(self._on_apply_selected_tag)
        apply_row.addWidget(btn_apply)
        btn_clear = QPushButton(self.tr("清除"))
        btn_clear.clicked.connect(self._on_clear_tag)
        apply_row.addWidget(btn_clear)
        rl.addLayout(apply_row)
        btn_add = QPushButton("+ " + self.tr("添加自定义字段...")); btn_add.clicked.connect(self._add_custom_tag)
        rl.addWidget(btn_add)
        self._lbl_selected = QLabel(self.tr("提示: 双击右侧 Tag 应用到文档")); self._lbl_selected.setStyleSheet("color:#666;font-size:9pt;")
        rl.addWidget(self._lbl_selected)
        splitter.addWidget(right); splitter.setSizes([550, 350]); layout.addWidget(splitter, 1)
        btn_row = QHBoxLayout()
        btn_rule = QPushButton(self.tr("🤖 规则自动匹配")); btn_rule.clicked.connect(self._rule_match)
        btn_row.addWidget(btn_rule)
        btn_save = QPushButton(self.tr("💾 保存到文件")); btn_save.setStyleSheet("font-weight:bold;")
        btn_save.clicked.connect(self._save); btn_row.addWidget(btn_save)
        btn_row.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.Close); btns.rejected.connect(self.close); btn_row.addWidget(btns)
        layout.addLayout(btn_row)

    def _build_document_view(self):
        """用 mammoth 将 docx 完整转为 HTML (保留 Word 原格式), 没安装时 fallback。"""
        try:
            try:
                import mammoth
                with open(self._path, 'rb') as f:
                    result = mammoth.convert_to_html(f)
                html = result.value
            except ImportError:
                html = self._build_document_view_fallback()
            bg = getattr(self, '_theme_bg', '#ffffff')
            header = '<div style="color:#888;font-size:9pt;margin-bottom:8px;">'
            header += '📄 ' + Path(self._path).name + ' — ' + str(len(self._existing_tags)) + ' SDT'
            header += ' <span style="color:#e65100;">(pip install mammoth 获得更好渲染)</span></div>'
            full = '<html><head><meta charset=utf-8><style>'
            full += 'body{font-family:Calibri,sans-serif;font-size:11pt;background:' + bg + ';color:inherit;}'
            full += '</style></head><body>' + header + html + '</body></html>'
            self._doc_browser.setHtml(full)
        except Exception as e:
            self._doc_browser.setPlainText("加载失败: " + str(e))

    def _build_document_view_fallback(self) -> str:
        """无 mammoth 时的简化 HTML 渲染。"""
        import zipfile; from lxml import etree
        NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        with zipfile.ZipFile(self._path, 'r') as zf:
            doc_xml = etree.parse(zf.open('word/document.xml'))
        body = doc_xml.getroot().find(f"{{{NS_W}}}body")
        if body is None: return "<p>无法解析</p>"
        parts = []
        tbl_idx = 0
        for child in body:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if tag == 'p':
                text = "".join(child.itertext()).strip()
                if text:
                    sdt = self._get_sdt_tag(child)
                    lbl = '<b>[' + sdt + ']</b> ' if sdt else ''
                    parts.append('<p>' + lbl + text + '</p>')
            elif tag == 'tbl':
                rows = list(child.iter(f"{{{NS_W}}}tr"))
                sdt = self._get_sdt_tag(child)
                suggestion = next((p.suggested_tag for p in self._positions if p.pos_type.startswith("table") and p.index==tbl_idx), "")
                tl = sdt or suggestion or "未设置"
                parts.append('<p>📊 <b>[' + tl + ']</b> — ' + str(len(rows)) + '行</p>')
                if rows:
                    cells = ["".join(c.itertext()).strip()[:20] for c in rows[0].iter(f"{{{NS_W}}}tc")]
                    parts.append('<p style="font-size:9pt;color:#888;">' + " | ".join(cells[:5]) + '</p>')
                tbl_idx += 1
        return '\n'.join(parts)

    def _get_sdt_tag(self, element):
        NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        p = element.getparent()
        if p is not None and p.tag == f"{{{NS_W}}}sdtContent":
            sdt_pr = p.getparent().find(f"{{{NS_W}}}sdtPr")
            if sdt_pr is not None:
                tag_el = sdt_pr.find(f"{{{NS_W}}}tag")
                if tag_el is not None: return tag_el.get(f"{{{NS_W}}}val")
        return None

    def _build_tag_tree(self):
        self._tag_tree.clear()
        from src.docx_exporter import DocxTemplateFiller
        reg = DocxTemplateFiller.load_registry()
        ant_name = self._cmb_antenna.currentData() or ""
        mode = 0
        if self._multi_cfg and ant_name:
            ac = self._multi_cfg.get_antenna(ant_name)
            if ac: mode = ac.test_mode
        chart_keys = set()
        if self._multi_cfg and ant_name:
            ac = self._multi_cfg.get_antenna(ant_name)
            if ac: chart_keys = set(ac.chart_keys)
        self._add_cat(self.tr("📋 项目信息"), reg.get("meta", {}))
        self._add_cat(self.tr("📊 数据表格"), reg.get("table", {}))
        self._add_cat(self.tr("🖼 图片"), reg.get("img", {}), chart_keys)
        self._add_cat(self.tr("🔄 循环组"), reg.get("img_group", {}))
        self._add_cat(self.tr("⚙ 测试配置"), reg.get("config", {}))
        cust = self._load_custom_tags()
        if cust: self._add_cat(self.tr("📝 自定义"), cust, set(), True)

    def _add_cat(self, name, items, filter_keys=None, is_custom=False):
        node = QTreeWidgetItem(self._tag_tree, [name]); node.setExpanded(True)
        node.setForeground(0, QColor("#1F4E79"))
        for key, desc in items.items():
            if filter_keys is not None and key not in filter_keys: continue
            it = QTreeWidgetItem(node)
            it.setText(0, f"📝 {key}" if is_custom else f"{key} — {desc}" if desc else key)
            it.setData(0, Qt.UserRole, key); it.setToolTip(0, desc)

    def _load_custom_tags(self):
        import json
        p = Path(__file__).parent.parent / "config" / "user_patterns.json"
        if p.exists():
            try: return json.loads(p.read_text(encoding='utf-8')).get("params", {})
            except: pass
        return {}

    def _on_antenna_changed(self, idx): self._build_tag_tree()

    def _on_search(self, text):
        for i in range(self._tag_tree.topLevelItemCount()):
            top = self._tag_tree.topLevelItem(i); visible = False
            for j in range(top.childCount()):
                c = top.child(j); show = not text or text.lower() in c.text(0).lower()
                c.setHidden(not show)
                if show: visible = True
            top.setHidden(not visible)

    def _on_tag_double_clicked(self, item, col):
        self._apply_tag(item)

    def _on_apply_selected_tag(self):
        """应用当前在树中选中的 Tag。"""
        items = self._tag_tree.selectedItems()
        if items:
            self._apply_tag(items[0])

    def _apply_tag(self, item):
        tag = item.data(0, Qt.UserRole)
        if not tag: return
        applied = 0
        for p in self._positions:
            if p.suggested_tag == tag or not p.confirmed_tag:
                p.confirmed_tag = tag
                applied += 1
        if applied:
            self._build_document_view()
        self._lbl_selected.setText(self.tr("✅ 已应用: {0} ({1} 处)").format(tag, applied))

    def _on_clear_tag(self):
        """清除所有通过双击/应用临时设置的 tag, 恢复建议状态。"""
        for p in self._positions:
            if p.confirmed_tag and not self._get_sdt_tag_for_position(p):
                p.confirmed_tag = ""
        self._build_document_view()
        self._lbl_selected.setText(self.tr("已清除临时标记, 恢复为建议状态"))

    def _get_sdt_tag_for_position(self, pos) -> str:
        import zipfile; from lxml import etree
        NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        try:
            with zipfile.ZipFile(self._path, 'r') as zf:
                doc_xml = etree.parse(zf.open('word/document.xml'))
            tables = list(doc_xml.getroot().iter(f"{{{NS_W}}}tbl"))
            if pos.index < len(tables):
                return self._get_sdt_tag(tables[pos.index])
        except Exception:
            pass
        return ""

    def _rule_match(self):
        from src.llm_tagger import rule_based_suggest
        n = rule_based_suggest(self._positions)
        self._build_document_view()
        self._lbl_summary.setText(self.tr("已设定:{0} | 建议:{1}").format(len(self._existing_tags), n))

    def _add_custom_tag(self):
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        key, ok = QInputDialog.getText(self, self.tr("添加自定义字段"), self.tr("SDT Tag 名称 (如 meta_car_model):"), QLineEdit.Normal, "")
        if not ok or not key.strip(): return
        desc, ok2 = QInputDialog.getText(self, self.tr("字段描述"), self.tr("描述 (如 车型):"), QLineEdit.Normal, "")
        if not ok2: return
        import json
        p = Path(__file__).parent.parent / "config" / "user_patterns.json"
        data = {}
        if p.exists():
            try: data = json.loads(p.read_text(encoding='utf-8'))
            except: pass
        data.setdefault("params", {})[key.strip()] = desc.strip()
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        self._custom_tags = self._load_custom_tags()
        self._build_tag_tree()

    def _save(self):
        for p in self._positions:
            if p.suggested_tag:
                p.confirmed_tag = p.suggested_tag
        from src.docx_sdt_inserter import insert_sdt_tags
        out = str(Path(self._path).parent / (Path(self._path).stem + "_SDT.docx"))
        insert_sdt_tags(self._path, self._positions, out)
        QMessageBox.information(self, self.tr("已保存"), self.tr("已应用 {0} 个 SDT tag 到:\n{1}").format(
            len([p for p in self._positions if p.confirmed_tag]), out))
