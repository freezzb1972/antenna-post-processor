"""
多天线配置页面
==============
左侧: 天线列表
右侧: 当前天线的详细配置 (参数 + 图表 + SDT后缀)
底部: 预览/出报告按钮
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter,
    QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from ui.main_window import MainWindow

from src.multi_antenna import (
    AntennaConfig, MultiAntennaConfig, export_to_excel, extract_antenna_name,
    import_from_excel,
)
from src.lag_config import LagConfig


class MultiAntennaPage(QWidget):
    """多天线配置页面。"""

    config_changed = Signal()

    def __init__(self, parent=None, mw: "MainWindow" = None):
        super().__init__(parent)
        self._mw = mw
        self._config = MultiAntennaConfig()
        self._current_antenna_idx = -1
        self._param_checkboxes: dict[str, QCheckBox] = {}
        self._chart_checkboxes: dict[str, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── 左侧: 天线列表 ──
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        ll.addWidget(QLabel("<b>" + self.tr("天线列表") + "</b>"))
        self._antenna_list = QListWidget()
        self._antenna_list.currentRowChanged.connect(self._on_antenna_selected)
        ll.addWidget(self._antenna_list, 1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton(self.tr("+ 添加"))
        btn_add.clicked.connect(self._add_antenna)
        btn_row.addWidget(btn_add)
        btn_del = QPushButton(self.tr("删除"))
        btn_del.clicked.connect(self._del_antenna)
        btn_row.addWidget(btn_del)
        ll.addLayout(btn_row)

        btn_import = QPushButton(self.tr("📥 从 Excel 导入"))
        btn_import.clicked.connect(self._import_excel)
        ll.addWidget(btn_import)
        btn_export = QPushButton(self.tr("📤 导出到 Excel"))
        btn_export.clicked.connect(self._export_excel)
        ll.addWidget(btn_export)

        splitter.addWidget(left)

        # ── 右侧: 天线详情 ──
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)

        # 天线名称 + 文件 + SDT后缀
        info_grp = QGroupBox(self.tr("基本信息"))
        info_form = QFormLayout(info_grp)
        self._edit_name = QLineEdit()
        self._edit_name.textChanged.connect(lambda: self._sync_to_config())
        info_form.addRow(self.tr("天线名称:"), self._edit_name)
        self._edit_files = QLineEdit()
        self._edit_files.setPlaceholderText(self.tr("数据文件, 分号分隔"))
        info_form.addRow(self.tr("数据文件:"), self._edit_files)
        sd_row = QHBoxLayout()
        self._edit_suffix = QLineEdit()
        self._edit_suffix.setPlaceholderText("如 _L1_amp")
        self._edit_suffix.textChanged.connect(lambda: self._sync_to_config())
        sd_row.addWidget(self._edit_suffix)
        self._lbl_tag_preview = QLabel("")
        self._lbl_tag_preview.setStyleSheet("color: #888;")
        sd_row.addWidget(self._lbl_tag_preview)
        info_form.addRow(self.tr("SDT 后缀:"), sd_row)
        self._cmb_mode = QComboBox()
        self._cmb_mode.addItem(self.tr("无源天线"), 0)
        self._cmb_mode.addItem(self.tr("有源发射 TRP"), 1)
        self._cmb_mode.addItem(self.tr("有源接收 TIS"), 2)
        self._cmb_mode.currentIndexChanged.connect(lambda: self._sync_to_config())
        info_form.addRow(self.tr("测试模式:"), self._cmb_mode)
        rl.addWidget(info_grp)

        # Word 模板
        word_grp = QGroupBox(self.tr("Word 报告模板"))
        word_layout = QVBoxLayout(word_grp)
        word_row = QHBoxLayout()
        self._edit_word_tpl = QLineEdit()
        self._edit_word_tpl.setPlaceholderText(self.tr("选择带 SDT tag 的 .docx 模板..."))
        word_row.addWidget(self._edit_word_tpl, 1)
        btn_browse_word = QPushButton(self.tr("浏览..."))
        btn_browse_word.clicked.connect(self._browse_word)
        word_row.addWidget(btn_browse_word)
        btn_scan_sdt = QPushButton(self.tr("🔍 检查 SDT"))
        btn_scan_sdt.clicked.connect(self._scan_sdt_tags)
        word_row.addWidget(btn_scan_sdt)
        btn_sdt_tool = QPushButton(self.tr("🛠 SDT 工具箱"))
        btn_sdt_tool.clicked.connect(self._open_sdt_toolbox)
        word_row.addWidget(btn_sdt_tool)
        word_layout.addLayout(word_row)
        self._lbl_sdt_status = QLabel("")
        self._lbl_sdt_status.setStyleSheet("color: #888; font-size: 9pt;")
        word_layout.addWidget(self._lbl_sdt_status)
        rl.addWidget(word_grp)

        # 参数 + 图表 tabs
        tabs = QTabWidget()

        # 天线参数 Tab
        param_tab = QWidget()
        param_layout = QVBoxLayout(param_tab)
        from ui.pages import AntennaParamsPage
        for grp_name, items in AntennaParamsPage._COMMON_PARAMS[:10]:
            grp = QGroupBox(grp_name)
            gl = QVBoxLayout(grp)
            gl.setSpacing(2)
            for key, label in items:
                cb = QCheckBox(label)
                cb.toggled.connect(lambda: self._sync_to_config())
                self._param_checkboxes[key] = cb
                gl.addWidget(cb)
            param_layout.addWidget(grp)
        param_tab2 = QWidget()
        tabs.addTab(param_tab, self.tr("天线参数"))

        # 图表 Tab
        chart_tab = QWidget()
        chart_scroll = QVBoxLayout(chart_tab)
        from src.chart_config import ChartConfig
        labels = ChartConfig.chart_labels()
        for cat_name, keys in ChartConfig.chart_categories(0).items():
            grp = QGroupBox(cat_name)
            gl = QVBoxLayout(grp)
            gl.setSpacing(2)
            for key in keys:
                cb = QCheckBox(labels.get(key, key))
                cb.toggled.connect(lambda: self._sync_to_config())
                self._chart_checkboxes[key] = cb
                gl.addWidget(cb)
            chart_scroll.addWidget(grp)
        tabs.addTab(chart_tab, self.tr("图表配置"))

        rl.addWidget(tabs, 1)

        # 角度快捷设置
        angle_grp = QGroupBox(self.tr("角度配置"))
        angle_layout = QHBoxLayout(angle_grp)
        for target, label in [("gain", "Gain ⚙"), ("ar", "AR ⚙"),
                               ("rhcp", "RHCP ⚙"), ("cpxpi", "CP-XPI ⚙")]:
            btn = QPushButton(label)
            btn.setFixedWidth(80)
            btn.clicked.connect(lambda checked, t=target: self._open_angle_popup(t))
            angle_layout.addWidget(btn)
        angle_layout.addStretch()
        rl.addWidget(angle_grp)

        splitter.addWidget(right)
        splitter.setSizes([200, 500])
        layout.addWidget(splitter)

    def _on_antenna_selected(self, idx: int):
        self._current_antenna_idx = idx
        self._load_antenna(idx)

    def _load_antenna(self, idx: int):
        if idx < 0 or idx >= len(self._config.antennas):
            return
        ant = self._config.antennas[idx]
        self._edit_name.blockSignals(True)
        self._edit_name.setText(ant.name)
        self._edit_name.blockSignals(False)
        self._edit_files.setText("; ".join(ant.data_files))
        self._edit_suffix.setText(ant.sdt_suffix)
        idx2 = self._cmb_mode.findData(ant.test_mode)
        if idx2 >= 0: self._cmb_mode.setCurrentIndex(idx2)
        for key, cb in self._param_checkboxes.items():
            cb.setChecked(key in ant.required_params)
        for key, cb in self._chart_checkboxes.items():
            cb.setChecked(key in ant.chart_keys)
        self._update_tag_preview()

    def _sync_to_config(self):
        idx = self._current_antenna_idx
        if idx < 0 or idx >= len(self._config.antennas):
            return
        ant = self._config.antennas[idx]
        ant.name = self._edit_name.text().strip()
        ant.data_files = [f.strip() for f in self._edit_files.text().split(";") if f.strip()]
        ant.sdt_suffix = self._edit_suffix.text().strip()
        ant.test_mode = self._cmb_mode.currentData() or 0
        ant.required_params = {k for k, cb in self._param_checkboxes.items() if cb.isChecked()}
        ant.chart_keys = [k for k, cb in self._chart_checkboxes.items() if cb.isChecked()]
        if idx < self._antenna_list.count():
            self._antenna_list.item(idx).setText(ant.name or f"天线 {idx+1}")
        self._update_tag_preview()
        self.config_changed.emit()

    def _update_tag_preview(self):
        suffix = self._edit_suffix.text().strip()
        if suffix:
            self._lbl_tag_preview.setText(f"→ table_data{suffix}, img_group{suffix}")
        else:
            self._lbl_tag_preview.setText("")

    def _add_antenna(self):
        ant = self._config.add_antenna(f"天线 {len(self._config.antennas)+1}")
        item = QListWidgetItem(ant.name)
        self._antenna_list.addItem(item)
        self._antenna_list.setCurrentRow(len(self._config.antennas)-1)

    def _del_antenna(self):
        idx = self._current_antenna_idx
        if idx >= 0:
            self._config.remove_antenna(idx)
            self._antenna_list.takeItem(idx)

    def _open_angle_popup(self, target: str):
        """打开角度配置弹窗 (委托给 MainWindow 的 AntennaParamsPage)。"""
        if self._mw:
            ant_page = getattr(self._mw, '_antenna_params_page', None)
            if ant_page and hasattr(ant_page, '_show_angle_popup'):
                ant_page._show_angle_popup(target)

    def _import_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("导入测试计划"), "",
            self.tr("Excel 文件 (*.xlsx *.xls)"))
        if not path: return
        try:
            self._config = import_from_excel(path)
            self._refresh_list()
            QMessageBox.information(self, self.tr("导入完成"),
                self.tr("已导入 {} 个天线配置").format(len(self._config.antennas)))
        except Exception as e:
            QMessageBox.warning(self, self.tr("导入失败"), str(e))

    def _export_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("导出测试计划"), "antenna_test_plan.xlsx",
            self.tr("Excel 文件 (*.xlsx)"))
        if not path: return
        try:
            export_to_excel(self._config, path)
            QMessageBox.information(self, self.tr("导出完成"), self.tr("已保存到:\n{}").format(path))
        except Exception as e:
            QMessageBox.warning(self, self.tr("导出失败"), str(e))

    def _refresh_list(self):
        self._antenna_list.clear()
        for ant in self._config.antennas:
            self._antenna_list.addItem(ant.name)

    def _browse_word(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("选择 Word 模板"), "",
                                               self.tr("Word 文档 (*.docx)"))
        if path: self._edit_word_tpl.setText(path)

    def _scan_sdt_tags(self):
        path = self._edit_word_tpl.text().strip()
        if not path or not Path(path).exists():
            QMessageBox.warning(self, self.tr("错误"), self.tr("请先选择 Word 模板文件。"))
            return
        try:
            from src.docx_exporter import DocxTemplateFiller
            filler = DocxTemplateFiller(path)
            tags = filler.list_tags()
            tag_str = ", ".join(tags) if tags else self.tr("(无 SDT tag)")
            self._lbl_sdt_status.setText(self.tr("SDT Tags ({0}): {1}").format(len(tags), tag_str[:200]))
        except Exception as e:
            self._lbl_sdt_status.setText(self.tr("读取失败: {0}").format(str(e)))

    def _open_sdt_toolbox(self):
        from ui.template_recognizer import DocxTemplateToolbox
        path = self._edit_word_tpl.text().strip()
        dlg = DocxTemplateToolbox(self, path if path and Path(path).exists() else "")
        dlg.exec()

    def get_config(self) -> MultiAntennaConfig:
        return self._config
