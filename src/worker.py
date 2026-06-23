"""
后台处理 Worker
================
QThread 封装的异步处理任务，通过 Signal 与 GUI 通信。
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from PySide6.QtCore import QObject, Signal
from .lag_config import LagConfig
from .plot_config import PlotConfig
from .chart_config import ChartConfig
from .pipeline import run_pipeline, run_batch_pipeline
from .datasource import DataSource


class ProcessingWorker(QObject):
    """后台天线参数处理 Worker。"""

    progress = Signal(int, int, str)
    log = Signal(str)
    finished = Signal(object, object)
    error = Signal(str)

    def __init__(
        self,
        csv_path: str = "",
        template_path: str = "",
        output_path: str = "",
        *,
        datasource: Optional[DataSource] = None,
        datasource_map: Optional[Dict[str, DataSource]] = None,
        sheet_mode_map: Optional[Dict[str, int]] = None,
        lag_config: Optional[LagConfig] = None,
        plot_config: Optional[PlotConfig] = None,
        full_report_path: Optional[str] = None,
        extrapolate_theta: bool = False,
        freq_source: str = "datasource",
        trim_start: int = 0,
        trim_end: int = 0,
        robust_peak: bool = False,
        extra_params: Optional[set] = None,
        chart_config_obj: Optional[ChartConfig] = None,
        ar_lag_config: Optional[LagConfig] = None,
        nh_custom_angles: Optional[List[float]] = None,
        ar_output_db: bool = True,
        worksheet_naming_mode: int = 0,
    ):
        super().__init__()
        self.csv_path = csv_path
        self.template_path = template_path
        self.output_path = output_path
        self.datasource = datasource
        self.datasource_map = datasource_map
        self.sheet_mode_map = sheet_mode_map or {}
        self.lag_config = lag_config
        self.ar_lag_config = ar_lag_config
        self.plot_config = plot_config or PlotConfig()
        self.full_report_path = full_report_path
        self.extrapolate_theta = extrapolate_theta
        self.freq_source = freq_source
        self.trim_start = trim_start
        self.trim_end = trim_end
        self.robust_peak = robust_peak
        self.extra_params = extra_params
        self.chart_config_obj = chart_config_obj
        self.nh_custom_angles = nh_custom_angles
        self.ar_output_db = ar_output_db
        self.worksheet_naming_mode = worksheet_naming_mode
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _is_cancelled(self) -> bool:
        return self._cancelled

    def run(self):
        try:
            if self._cancelled:
                self.log.emit("处理已取消")
                return

            kwargs = dict(
                template_path=self.template_path,
                output_path=self.output_path,
                lag_config_override=self.lag_config,
                ar_lag_config_override=self.ar_lag_config,
                sheet_mode_map=self.sheet_mode_map,
                plot_config=self.plot_config,
                full_report_path=self.full_report_path,
                extrapolate_theta=self.extrapolate_theta,
                freq_source=self.freq_source,
                trim_start=self.trim_start,
                trim_end=self.trim_end,
                chart_config_obj=self.chart_config_obj,
                robust_peak=self.robust_peak,
                extra_params=self.extra_params,
                nh_custom_angles=self.nh_custom_angles,
                ar_output_db=self.ar_output_db,
                worksheet_naming_mode=self.worksheet_naming_mode,
                cancel_callback=self._is_cancelled,
                progress_callback=self._on_progress,
                log_callback=self._on_log,
            )

            if self.datasource_map:
                results = run_pipeline(datasource_map=self.datasource_map, **kwargs)
            elif self.datasource:
                results = run_pipeline(datasource=self.datasource, **kwargs)
            else:
                results = run_batch_pipeline(csv_path=self.csv_path, **kwargs)

            if not self._cancelled:
                self.finished.emit(results, {})

        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")

    def _on_progress(self, current, total, message):
        if not self._cancelled:
            self.progress.emit(current, total, message)

    def _on_log(self, message):
        if not self._cancelled:
            self.log.emit(message)
