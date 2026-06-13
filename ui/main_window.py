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
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from i18n.i18n_manager import I18nManager
from src.lag_config import LagConfig
from src.pipeline import PlotConfig
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

        # ---- 状态 ----
        self._lag_config = LagConfig(
            single_angles=[60, 70, 80, 90],
            ranges=[(0, 90), (60, 90)],
        )
        self._thread: Optional[QThread] = None
        self._worker: Optional[ProcessingWorker] = None
        self._running = False
        self._settings = QSettings("AntennaPP", "AntennaPostProcessor")

        # ---- 初始化 ----
        self._init_theme_selector()
        self._apply_custom_qss()
        self._init_file_paths()
        self._connect_signals()
        self._update_lag_display()
        self._log(self.tr("天线参数后处理工具已启动"))
        self._log(self.tr("默认 LAG 配置: 单角度 [60°, 70°, 80°, 90°], 范围 [(0-90°), (60-90°)]"))

    # ==================================================================
    # 初始化
    # ==================================================================

    def _init_file_paths(self):
        """从 QSettings 恢复上次路径。"""
        csv_path = self._settings.value("csv_path", "")
        template_path = self._settings.value("template_path", "")
        output_dir = self._settings.value("output_dir", str(Path.cwd() / "output"))

        if csv_path and Path(csv_path).exists():
            self.ui.editCsvPath.setText(csv_path)
        if template_path and Path(template_path).exists():
            self.ui.editTemplatePath.setText(template_path)
        if output_dir:
            self.ui.editOutputDir.setText(output_dir)

        self.ui.editOutputName.setText("antenna_report.xlsx")

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
        """加载自定义 QSS 微调样式（不破坏 qt-material 主题）。"""
        qss = """
        /* 圆角卡片风格 — GroupBox 标题增强 */
        QGroupBox {
            border: 1px solid rgba(128, 128, 128, 60);
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 16px;
            font-weight: bold;
            font-size: 12px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }
        /* 按钮悬停过渡 */
        QPushButton {
            border-radius: 4px;
            padding: 4px 12px;
            transition: background-color 0.2s;
        }
        QPushButton:hover {
            border: 1px solid rgba(128, 128, 128, 100);
        }
        /* 日志输出区 */
        QPlainTextEdit {
            border-radius: 6px;
            border: 1px solid rgba(128, 128, 128, 50);
            font-family: "Consolas", "Courier New", monospace;
            font-size: 11px;
        }
        /* 进度条圆角 */
        QProgressBar {
            border-radius: 4px;
            text-align: center;
            height: 18px;
        }
        QProgressBar::chunk {
            border-radius: 3px;
        }
        /* Tab 标签 */
        QTabWidget::pane {
            border-radius: 6px;
        }
        QTabBar::tab {
            border-radius: 4px;
            padding: 6px 16px;
        }
        /* 输入框 */
        QLineEdit, QDoubleSpinBox, QSpinBox {
            border-radius: 4px;
            padding: 3px 6px;
        }
        /* 主题选择下拉框 */
        QComboBox {
            border-radius: 4px;
            padding: 3px 8px;
            min-width: 140px;
        }
        /* 开始按钮高亮 */
        QPushButton#btnStart {
            font-size: 14px;
            font-weight: bold;
            letter-spacing: 1px;
        }
        """
        self.app.setStyleSheet(self.app.styleSheet() + qss)
        csv_path = self._settings.value("csv_path", "")
        template_path = self._settings.value("template_path", "")
        output_dir = self._settings.value("output_dir", str(Path.cwd() / "output"))

        if csv_path and Path(csv_path).exists():
            self.ui.editCsvPath.setText(csv_path)
        if template_path and Path(template_path).exists():
            self.ui.editTemplatePath.setText(template_path)
        if output_dir:
            self.ui.editOutputDir.setText(output_dir)

        self.ui.editOutputName.setText("antenna_report.xlsx")

    def _connect_signals(self):
        """连接所有信号/槽。"""
        # 主题切换
        self.ui.cmbThemeSelector.currentIndexChanged.connect(self._on_theme_changed)

        # 文件浏览
        self.ui.btnBrowseCsv.clicked.connect(self._on_browse_csv)
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

    def _on_browse_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择 EMQuest CSV 文件"),
            self._settings.value("csv_path", ""),
            self.tr("CSV 文件 (*.csv);;Excel 文件 (*.xlsx *.xls);;所有文件 (*)")
        )
        if path:
            self.ui.editCsvPath.setText(path)
            self._settings.setValue("csv_path", path)

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
        self._log(self.tr(f"添加单角度: {angle}°"))

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
        self._log(self.tr(f"添加 LAG 范围: ({lo}°-{hi}°)"))

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
                    self._log(self.tr(f"从模板加载: {len(sheets)} 个工作表"))
                    for si in sheets:
                        self._log(f"  {si.name}: 单角度={si.lag_config.singles_sorted}, 范围={si.lag_config.ranges_sorted}")
                else:
                    self._log(self.tr("模板中未检测到 LAG 列"))
        except Exception as e:
            QMessageBox.critical(self, self.tr("错误"), self.tr(f"读取模板失败: {e}"))

    def _on_clear_config(self):
        self._lag_config.clear()
        self._sync_quick_buttons()
        self._update_lag_display()
        self._log(self.tr("LAG 配置已清空"))

    def _on_save_preset(self):
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存 LAG 预设"), "lag_preset.json",
            self.tr("JSON 文件 (*.json)")
        )
        if path:
            self._lag_config.save_preset(Path(path))
            self._log(self.tr(f"预设已保存: {path}"))

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
                self._log(self.tr(f"预设已加载: {path}"))
            except Exception as e:
                QMessageBox.critical(self, self.tr("错误"), self.tr(f"加载预设失败: {e}"))

    def _sync_quick_buttons(self):
        """同步快捷按钮选中状态。"""
        for angle, btn_attr in self._QUICK_ANGLES.items():
            btn = getattr(self.ui, btn_attr)
            btn.setChecked(angle in self._lag_config.single_angles)

    def _update_lag_display(self):
        """刷新已配置项 — 每项带删除按钮。"""
        layout = self.ui.configItemsLayout
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
                h = QHBoxLayout(row)
                h.setContentsMargins(8, 3, 0, 3)
                h.setSpacing(8)
                lbl = QLabel(f"  {a}°")
                lbl.setStyleSheet("font-size: 13px;")
                btn = QPushButton(" ✕ ")
                btn.setFixedHeight(26)
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
                h = QHBoxLayout(row)
                h.setContentsMargins(8, 3, 0, 3)
                h.setSpacing(8)
                lbl = QLabel(f"  ({lo}° - {hi}°)")
                lbl.setStyleSheet("font-size: 13px;")
                btn = QPushButton(" ✕ ")
                btn.setFixedHeight(26)
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
        """启动后台处理。"""
        csv_path = self.ui.editCsvPath.text().strip()
        template_path = self.ui.editTemplatePath.text().strip()
        output_dir = self.ui.editOutputDir.text().strip() or str(Path.cwd() / "output")
        output_name = self.ui.editOutputName.text().strip() or "antenna_report.xlsx"

        # 验证
        if not csv_path:
            QMessageBox.warning(self, self.tr("警告"), self.tr("请选择 CSV 输入文件。"))
            return
        if not Path(csv_path).exists():
            QMessageBox.warning(self, self.tr("警告"),
                self.tr(f"CSV 文件不存在:\n{csv_path}"))
            return
        if not template_path:
            QMessageBox.warning(self, self.tr("警告"), self.tr("请选择模板 Excel 文件。"))
            return
        if not Path(template_path).exists():
            QMessageBox.warning(self, self.tr("警告"),
                self.tr(f"模板文件不存在:\n{template_path}"))
            return

        os.makedirs(output_dir, exist_ok=True)
        output_path = str(Path(output_dir) / output_name)

        # 完整报告路径
        full_report_path: Optional[str] = None
        if self.ui.checkFullReport.isChecked():
            path_text = self.ui.editFullReportPath.text().strip()
            full_report_path = path_text if path_text else str(Path(output_dir) / "full_report.xlsx")

        # 构建 PlotConfig
        plot_config = PlotConfig(
            elev=self.ui.spinElev.value(),
            azim=self.ui.spinAzim.value(),
            dpi=self.ui.spinDpi.value(),
            embed_in_excel=self.ui.checkEmbedExcel.isChecked(),
            save_png_folder=str(Path(output_dir) / "png") if self.ui.checkSavePng.isChecked() else None,
        )

        # 清理上次
        self.ui.logOutput.clear()
        self.ui.progressBar.setValue(0)
        self.ui.lblProgressMsg.setText(self.tr("启动中..."))

        # 创建 Worker + Thread
        self._thread = QThread(self)
        self._worker = ProcessingWorker(
            csv_path=csv_path,
            template_path=template_path,
            output_path=output_path,
            lag_config=self._lag_config,
            plot_config=plot_config,
            full_report_path=full_report_path,
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
        self._log(self.tr(f"▶ 开始处理: {csv_path}"))
        self._log(self.tr(f"  模板: {template_path}"))
        self._log(self.tr(f"  输出: {output_path}"))
        if full_report_path:
            self._log(self.tr(f"  完整报告: {full_report_path}"))

    def _on_stop(self):
        """停止处理。"""
        if self._worker:
            self._worker.cancel()
        self._log(self.tr("⏹ 用户请求停止..."))
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

        # 统计
        total_rows = sum(len(v) for v in results.values())
        total_imgs = sum(len(v) for v in images.values())
        self._log(self.tr(f"\n{'='*50}"))
        self._log(self.tr(f"✓ 全部完成! 共 {len(results)} 个工作表, {total_rows} 行数据"))
        if total_imgs:
            self._log(self.tr(f"  生成 {total_imgs} 张 3D 方向图"))
        self._update_status()

    def _on_error(self, message: str):
        self._running = False
        self.ui.btnStart.setEnabled(True)
        self.ui.btnStop.setEnabled(False)
        self._log(self.tr(f"✗ 错误: {message}"))
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

    def closeEvent(self, event):
        """窗口关闭时停止线程。"""
        if self._running and self._worker:
            self._worker.cancel()
            self._thread.quit()
            self._thread.wait(3000)
        event.accept()
