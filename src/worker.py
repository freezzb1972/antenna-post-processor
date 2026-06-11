"""
后台处理 Worker
================
QThread 封装的异步处理任务，通过 Signal 与 GUI 通信。

信号：
  - progress(current, total, message) → 进度条 + 状态文字
  - log(message)                      → 日志输出
  - finished(sheet_results, images)   → 处理完成
  - error(message)                    → 处理异常
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal

from .lag_config import LagConfig
from .pipeline import PlotConfig, run_batch_pipeline


class ProcessingWorker(QObject):
    """后台天线参数处理 Worker。

    在 QThread 中运行，不阻塞 GUI。
    """

    progress = Signal(int, int, str)  # current, total, message
    log = Signal(str)                  # log line
    finished = Signal(object, object)  # sheet_results, pattern_images
    error = Signal(str)                # error message

    def __init__(
        self,
        csv_path: str,
        template_path: str,
        output_path: str,
        *,
        lag_config: Optional[LagConfig] = None,
        plot_config: Optional[PlotConfig] = None,
    ):
        super().__init__()
        self.csv_path = csv_path
        self.template_path = template_path
        self.output_path = output_path
        self.lag_config = lag_config
        self.plot_config = plot_config or PlotConfig()
        self._cancelled = False

    def cancel(self):
        """请求取消处理。"""
        self._cancelled = True

    def run(self):
        """在 QThread 中执行。"""
        try:
            if self._cancelled:
                self.log.emit("处理已取消")
                return

            results, images = run_batch_pipeline(
                csv_path=self.csv_path,
                template_path=self.template_path,
                output_path=self.output_path,
                lag_config_override=self.lag_config,
                plot_config=self.plot_config,
                progress_callback=self._on_progress,
                log_callback=self._on_log,
            )

            if not self._cancelled:
                self.finished.emit(results, images)

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.error.emit(f"{e}\n{tb}")

    def _on_progress(self, current: int, total: int, message: str):
        if not self._cancelled:
            self.progress.emit(current, total, message)

    def _on_log(self, message: str):
        if not self._cancelled:
            self.log.emit(message)
