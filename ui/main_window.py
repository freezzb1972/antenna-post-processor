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
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QEvent, QSettings, Qt, QThread
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

from i18n.i18n_manager import I18nManager
from src.lag_config import LagConfig
from src.pipeline import PlotConfig
from src.worker import ProcessingWorker
from ui.compiled.ui_main_window import Ui_MainWindow


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """天线参数后处理工具主窗口。"""

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

    def _connect_signals(self):
        """连接所有信号/槽。"""
        # 文件浏览
        self.ui.btnBrowseCsv.clicked.connect(self._on_browse_csv)
        self.ui.btnBrowseTemplate.clicked.connect(self._on_browse_template)
        self.ui.btnBrowseOutput.clicked.connect(self._on_browse_output)

        # LAG 快捷按钮
        quick_buttons = [
            (self.ui.btnQuick0, 0.0),
            (self.ui.btnQuick30, 30.0),
            (self.ui.btnQuick60, 60.0),
            (self.ui.btnQuick70, 70.0),
            (self.ui.btnQuick80, 80.0),
            (self.ui.btnQuick90, 90.0),
        ]
        for btn, angle in quick_buttons:
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
            self, self.tr("选择 EMQuest CSV 文件"), "",
            self.tr("CSV 文件 (*.csv);;所有文件 (*)")
        )
        if path:
            self.ui.editCsvPath.setText(path)
            self._settings.setValue("csv_path", path)

    def _on_browse_template(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择模板 Excel 文件"), "",
            self.tr("Excel 文件 (*.xlsx);;所有文件 (*)")
        )
        if path:
            self.ui.editTemplatePath.setText(path)
            self._settings.setValue("template_path", path)

    def _on_browse_output(self):
        path = QFileDialog.getExistingDirectory(
            self, self.tr("选择输出目录"), ""
        )
        if path:
            self.ui.editOutputDir.setText(path)
            self._settings.setValue("output_dir", path)

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
        self._lag_config.add_single(angle)
        self._sync_quick_buttons()
        self._update_lag_display()

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
        btn_map = {
            0.0: self.ui.btnQuick0,
            30.0: self.ui.btnQuick30,
            60.0: self.ui.btnQuick60,
            70.0: self.ui.btnQuick70,
            80.0: self.ui.btnQuick80,
            90.0: self.ui.btnQuick90,
        }
        for angle, btn in btn_map.items():
            btn.setChecked(angle in self._lag_config.single_angles)

    def _update_lag_display(self):
        """刷新已配置项文字。"""
        singles = self._lag_config.singles_sorted
        ranges = self._lag_config.ranges_sorted

        if singles:
            self.ui.lblConfigSingles.setText(
                self.tr("单角度：") + ", ".join(f"{a}°" for a in singles)
            )
        else:
            self.ui.lblConfigSingles.setText(self.tr("单角度：—"))

        if ranges:
            self.ui.lblConfigRanges.setText(
                self.tr("角度范围：") + ", ".join(f"({lo}°-{hi}°)" for lo, hi in ranges)
            )
        else:
            self.ui.lblConfigRanges.setText(self.tr("角度范围：—"))

    # ==================================================================
    # 运行控制
    # ==================================================================

    def _on_start(self):
        """启动后台处理。"""
        csv_path = self.ui.editCsvPath.text()
        template_path = self.ui.editTemplatePath.text()
        output_dir = self.ui.editOutputDir.text() or str(Path.cwd() / "output")
        output_name = self.ui.editOutputName.text() or "antenna_report.xlsx"

        # 验证
        if not csv_path or not Path(csv_path).exists():
            QMessageBox.warning(self, self.tr("警告"), self.tr("请选择有效的 CSV 输入文件。"))
            return
        if not template_path or not Path(template_path).exists():
            QMessageBox.warning(self, self.tr("警告"), self.tr("请选择有效的模板 Excel 文件。"))
            return

        os.makedirs(output_dir, exist_ok=True)
        output_path = str(Path(output_dir) / output_name)

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
        self.ui.logOutput.append(f"[{ts}] {message}")
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
