"""
后台处理 Worker
================
QThread 封装的异步处理任务，通过 Signal 与 GUI 通信。
支持多步进同时计算模式。
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QObject, Signal
from .lag_config import LagConfig
from .plot_config import PlotConfig
from .chart_config import ChartConfig
from .pipeline import run_pipeline, run_batch_pipeline
from .datasource import DataSource, ResampledDataSource


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
        # 多步进参数
        step_values: Optional[List[float]] = None,
        skip_original: bool = False,
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
        self.step_values = step_values or []
        self.skip_original = skip_original
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

            # ── 多步进模式 ──
            if self.step_values:
                # 获取基础 DataSource（单文件或 map 首项）
                base = self.datasource
                if base is None and self.datasource_map:
                    base = next(iter(self.datasource_map.values()))
                if base is not None:
                    results = self._run_multi_step(base, **kwargs)
                else:
                    results = run_batch_pipeline(csv_path=self.csv_path, **kwargs)
            elif self.datasource_map:
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

    def _run_multi_step(self, base_ds: DataSource, **kwargs) -> Dict[str, list]:
        """多步进同时计算：源文件一次读取，各步进零拷贝重采样。"""
        import os
        import openpyxl
        from tempfile import NamedTemporaryFile

        # 原始步进
        orig_theta_step = round(
            base_ds.theta_angles[1] - base_ds.theta_angles[0], 6
        ) if len(base_ds.theta_angles) > 1 else 1.0
        orig_phi_step = round(
            base_ds.phi_angles[1] - base_ds.phi_angles[0], 6
        ) if len(base_ds.phi_angles) > 1 else 1.0

        # 确定要计算哪些步进
        steps_to_run = []
        if not self.skip_original:
            steps_to_run.append(("", base_ds))  # 原始步进，无后缀

        for step in sorted(self.step_values):
            theta_stride = max(1, int(round(step / orig_theta_step)))
            phi_stride = max(1, int(round(step / orig_phi_step)))
            suffix = f"_step{int(step)}"
            # 去重：不同 stride 的步进都计算
            resampled = ResampledDataSource(base_ds, theta_stride, phi_stride)
            steps_to_run.append((suffix, resampled))

        all_results = {}
        total_steps = len(steps_to_run)

        output_path = kwargs.pop("output_path", self.output_path)
        temp_dir = os.path.dirname(output_path) or "."
        os.makedirs(temp_dir, exist_ok=True)

        # 合并工作簿
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        for si, (suffix, ds) in enumerate(steps_to_run):
            if self._cancelled:
                break

            label = suffix[1:] if suffix else "原始步进"
            self.log.emit(f"📏 计算步进: {label}...")

            # 用临时文件跑单个步进
            with NamedTemporaryFile(suffix=".xlsx", dir=temp_dir, delete=False) as tf:
                tmp_out = tf.name

            try:
                kw = dict(kwargs)
                kw["output_path"] = tmp_out
                kw["progress_callback"] = lambda c, t, m, s=si, ts=total_steps: \
                    self._on_progress(s * 100 + c, ts * 100, m)

                results = run_pipeline(datasource=ds, **kw)

                # 把临时文件的 sheet 拷贝到合并工作簿
                twb = openpyxl.load_workbook(tmp_out, data_only=True)
                for ws in twb.worksheets:
                    new_name = (ws.title + suffix)[:31]  # Excel max 31 chars
                    nws = wb.create_sheet(title=new_name)
                    for row in ws.iter_rows():
                        for cell in row:
                            ncell = nws.cell(row=cell.row, column=cell.column)
                            ncell.value = cell.value
                            if cell.has_style:
                                ncell.font = cell.font
                                ncell.fill = cell.fill
                                ncell.alignment = cell.alignment
                                ncell.border = cell.border
                                ncell.number_format = cell.number_format
                    # 拷贝列宽
                    for col_letter, dim in ws.column_dimensions.items():
                        nws.column_dimensions[col_letter].width = dim.width
                    # 拷贝冻结窗格
                    if ws.freeze_panes:
                        nws.freeze_panes = ws.freeze_panes
                twb.close()
            finally:
                try:
                    os.unlink(tmp_out)
                except OSError:
                    pass

        # 保存合并工作簿
        wb.save(output_path)
        wb.close()

        return all_results

    def _on_progress(self, current, total, message):
        if not self._cancelled:
            self.progress.emit(current, total, message)

    def _on_log(self, message):
        if not self._cancelled:
            self.log.emit(message)
