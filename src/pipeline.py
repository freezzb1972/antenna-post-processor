"""
批处理管线 (v2)
================
协调 datasource → extrapolate → calculator → plotter → exporter。

支持:
  - 任意 DataSource (MergedCSV / FinalSummary)
  - 内存中 Theta 外推 (无中间文件)
  - 逐频点处理 (峰值内存 ~2MB/频点)
  - 可选多进程并行
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .calculator import (
    compute_axial_ratio,
    compute_directivity,
    compute_efficiency,
    compute_lag_at_angles,
    compute_lag_ranges,
    compute_nhprp,
    compute_peak_eirp,
    compute_total_gain_linear,
    compute_trp,
)
import copy
import re

from .datasource import DataSource
from .excel_reader import ColumnInfo, SheetInfo, read_template
from .exporter import export_results
from .lag_config import LagConfig
from .parser import MergedCSVParser
from .plot_config import PlotConfig
from .report_exporter import export_full_report


# ---------------------------------------------------------------------------
# Theta 外推 (pipeline 层)
# ---------------------------------------------------------------------------

def extrapolate_theta(
    theta_deg: np.ndarray,
    data: np.ndarray,  # (n_phi, n_theta)
    method: str = "linear",
) -> Tuple[np.ndarray, np.ndarray]:
    """将 Theta 范围外推到 0-180°。

    Args:
        theta_deg: 原始 Theta 角度 (°)。
        data:      数据矩阵 (n_phi, n_theta)。
        method:    'linear' | 'constant' | 'mirror'。

    Returns:
        (new_theta_deg, new_data)，new_data 形状 (n_phi, n_new)。
    """
    max_t = theta_deg[-1]
    if max_t >= 179:
        return theta_deg.copy(), data.copy()

    n_phi, n_theta = data.shape
    dtheta = theta_deg[1] - theta_deg[0] if len(theta_deg) > 1 else 1.0

    new_theta = list(theta_deg)
    t = max_t + dtheta
    while t <= 180.01:
        new_theta.append(round(t, 6))
        t += dtheta

    n_new = len(new_theta)
    new_data = np.zeros((n_phi, n_new), dtype=np.float64)
    new_data[:, :n_theta] = data

    if method == "constant":
        tail_avg = np.mean(data[:, -10:], axis=1)
        new_data[:, n_theta:] = tail_avg[:, np.newaxis]

    elif method == "mirror":
        for i in range(n_new - n_theta):
            mirror_idx = n_theta - 2 - i
            idx = mirror_idx if mirror_idx >= 0 else 0
            new_data[:, n_theta + i] = data[:, idx]

    elif method == "linear":
        tail_n = min(10, n_theta)
        xv = theta_deg[-tail_n:]
        n = len(xv)
        sx = float(np.sum(xv))
        sxx = float(np.sum(xv * xv))
        denom_ok = n > 1 and sxx * n - sx * sx != 0
        for pi in range(n_phi):
            yv = data[pi, -tail_n:]
            sy = float(np.sum(yv))
            sxy = float(np.sum(xv * yv))
            if denom_ok:
                slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
                intercept = (sy - slope * sx) / n
                if slope > 0:
                    slope = 0; intercept = sy / n
                peak = float(np.max(yv))
                floor = peak - 40
                for i in range(n_theta, n_new):
                    val = slope * new_theta[i] + intercept
                    val = min(val, yv[-1])
                    new_data[pi, i] = max(val, floor)

    return np.array(new_theta), new_data


# ---------------------------------------------------------------------------
# 单频点处理
# ---------------------------------------------------------------------------

def _process_one_frequency(
    raw: Dict[str, Optional[np.ndarray]],
    freq: float,
    theta_deg: np.ndarray,
    lag_config: LagConfig,
    *,
    do_extrapolate: bool = False,
    robust_peak: bool = False,
) -> Dict[str, Any]:
    """处理单个频点: 外推 → 计算 → 返回结果行。"""
    theta_lm = raw["theta_logmag"]
    phi_lm = raw["phi_logmag"]

    # Theta 外推 (仅在用户启用且数据不足 175° 时)
    need_extrap = do_extrapolate and theta_deg[-1] < 175
    if need_extrap:
        theta_orig = theta_deg.copy()  # 保存原始范围，仅用于 Phase 外推
        new_theta, theta_lm = extrapolate_theta(theta_deg, theta_lm, "linear")
        _, phi_lm = extrapolate_theta(theta_deg, phi_lm, "linear")
        theta_deg = new_theta

    theta_rad = np.deg2rad(theta_deg)

    # Gain
    gain_linear, peak_dbi = compute_total_gain_linear(theta_lm, phi_lm, robust=robust_peak)

    # Directivity
    directivity_dbi = compute_directivity(gain_linear, theta_rad)

    # Efficiency
    eff_pct, eff_db = compute_efficiency(peak_dbi, directivity_dbi)

    # TRP / NHPRP / Peak EIRP（有源测试指标，CTIA 标准）
    trp_dbm = compute_trp(gain_linear, theta_rad)
    nhprp_45 = compute_nhprp(gain_linear, theta_rad, 45.0)
    nhprp_30 = compute_nhprp(gain_linear, theta_rad, 30.0)
    peak_eirp = compute_peak_eirp(gain_linear)

    row: Dict[str, Any] = {
        "frequency": freq,
        "directivity": round(directivity_dbi, 6),
        "efficiency_pct": round(eff_pct, 6),
        "efficiency_db": round(eff_db, 6),
        "gain": round(peak_dbi, 6),
        "trp": round(trp_dbm, 2),
        "nhprp_45": round(nhprp_45, 2),
        "nhprp_30": round(nhprp_30, 2),
        "peak_eirp": round(peak_eirp, 2),
    }

    # Axial Ratio (仅当有 Phase 数据时)
    tp = raw.get("theta_phase")
    pp = raw.get("phi_phase")
    if tp is not None and pp is not None:
        try:
            if need_extrap:
                _, tp = extrapolate_theta(theta_orig, tp, "constant")
                _, pp = extrapolate_theta(theta_orig, pp, "constant")
            ar = compute_axial_ratio(theta_lm, tp, phi_lm, pp)
            if ar is not None and ar.size > 0:
                # AR 返回线性值 (EMQuest 格式)，取前5个 phi 均值
                row["axial_ratio"] = round(float(np.mean(ar[0, :5])), 6)
        except Exception as e:
            row["axial_ratio_error"] = str(e)

    # LAG 单角度
    singles = lag_config.singles_sorted
    if singles:
        lag_singles = compute_lag_at_angles(gain_linear, theta_deg, singles)
        for angle, val in lag_singles.items():
            row[f"lag_single_{angle}"] = round(val, 6)

    # LAG 范围
    ranges = lag_config.ranges_sorted
    if ranges:
        lag_ranges = compute_lag_ranges(gain_linear, theta_deg, ranges)
        for (lo, hi), val in lag_ranges.items():
            row[f"lag_range_{lo}_{hi}"] = round(val, 6)

    return row


# ---------------------------------------------------------------------------
# 查找最近频点
# ---------------------------------------------------------------------------

def _find_closest_freq(csv_freqs: List[float], target: float, tol=5.0) -> Optional[int]:
    if not csv_freqs:
        return None
    best_idx = int(np.argmin([abs(f - target) for f in csv_freqs]))
    return best_idx if abs(csv_freqs[best_idx] - target) <= tol else None


# ---------------------------------------------------------------------------
# 模板工作表自动扩增
# ---------------------------------------------------------------------------

def _derive_sheet_name(reference_name: str, target_key: str) -> str:
    """从参考工作表名推导新工作表名。

    "5G1" + key="G2" → "5G2"
    "Antenna_G1" + key="G3" → "Antenna_G3"
    """
    m = re.search(r'G\d+', reference_name, re.IGNORECASE)
    tk = re.search(r'G\d+', target_key, re.IGNORECASE)
    if m and tk:
        return reference_name[:m.start()] + tk.group(0).upper() + reference_name[m.end():]
    return target_key


def _expand_template_sheets(
    sheets_info: List[SheetInfo],
    datasource_map: Dict[str, DataSource],
    freq_source: str = "datasource",
) -> List[SheetInfo]:
    """当模板工作表数少于数据源数时，用第一个 sheet 为模板克隆其余 sheet。

    Args:
        sheets_info:    read_template() 返回的原始列表。
        datasource_map: {sheet_name: DataSource}。
        freq_source:    "datasource" → 新 sheet 用数据源频点；
                        "template" → 新 sheet 用模板最近邻匹配。

    Returns:
        扩展后的 SheetInfo 列表。
    """
    if len(sheets_info) < 2:
        return list(sheets_info)

    ref = sheets_info[0]
    matched_names = {si.name for si in sheets_info}
    existing_ds_names = set(datasource_map.keys())

    # 找出有 datasource 但没对应 sheet 的名称
    unmatched = existing_ds_names - matched_names
    if not unmatched:
        return list(sheets_info)

    expanded = list(sheets_info)

    for ds_name in sorted(unmatched):
        # 从 datasource 名称提取 key
        from .sheet_file_matcher import extract_key
        key = extract_key(ds_name).lstrip("0123456789")
        new_name = _derive_sheet_name(ref.name, key)

        # 深拷贝列头结构
        new_columns = [
            ColumnInfo(
                col_letter=c.col_letter,
                col_index=c.col_index,
                raw_header=c.raw_header,
                normalized_header=c.normalized_header,
                col_type=c.col_type,
            )
            for c in ref.columns
        ]

        ds = datasource_map[ds_name]
        if freq_source == "template":
            frequencies = list(ref.frequencies)
        else:
            frequencies = list(ds.frequencies)

        new_si = SheetInfo(
            name=new_name,
            header_row=ref.header_row,
            data_start_row=ref.data_start_row,
            data_end_row=ref.data_start_row + len(frequencies) - 1,
            columns=new_columns,
            frequencies=frequencies,
            lag_config=copy.deepcopy(ref.lag_config),
            theta_range=ref.theta_range,
        )
        expanded.append(new_si)

    return expanded


# ---------------------------------------------------------------------------
# 管线助手 — 任务收集 / 数据加载+计算
# ---------------------------------------------------------------------------

def _collect_tasks(
    sheets_info: List[Any],
    datasource: Optional[DataSource],
    datasource_map: Optional[Dict[str, DataSource]],
    freq_source: str = "datasource",
    trim_start: int = 0,
    trim_end: int = 0,
    log_cb=None,
) -> List[Tuple[str, float, int, Any, DataSource]]:
    """收集所有 (sheet_name, freq, csv_idx, lag_cfg, ds) 任务。"""
    use_multi = datasource_map is not None
    tasks: List[Tuple[str, float, int, Any, DataSource]] = []

    if use_multi:
        original_sheets = {si.name for si in sheets_info}
        all_ds_names = set(datasource_map.keys())
        expanded_names = all_ds_names - original_sheets
    else:
        expanded_names = set()

    for si in sheets_info:
        ds: Optional[DataSource] = datasource_map.get(si.name) if use_multi else datasource
        if ds is None:
            if use_multi:
                _log(log_cb, f"  ⚠ {si.name}: 无匹配数据源 — 跳过")
            continue

        is_expanded = si.name in expanded_names if use_multi else False
        use_ds_freqs = (is_expanded and freq_source == "datasource")

        if not use_ds_freqs:
            # 先尝试最近邻匹配（模板频点 → 数据源频点）
            dsfreqs = ds.frequencies
            match_count = 0
            for freq in si.frequencies:
                idx = _find_closest_freq(dsfreqs, freq)
                if idx is not None:
                    tasks.append((si.name, freq, idx, si.lag_config, ds))
                    match_count += 1
            # 如果一个都没匹配上，回退到数据源频点
            if match_count == 0 and dsfreqs:
                _log(log_cb, f"  ↻ {si.name}: 模板频点无匹配 → 使用数据源全部 {len(dsfreqs)} 个频点")
                use_ds_freqs = True

        if use_ds_freqs:
            dsfreqs = ds.frequencies
            for idx, freq in enumerate(dsfreqs):
                tasks.append((si.name, freq, idx, si.lag_config, ds))

    # ---- 频点裁剪 (trim_start/trim_end) ----
    if trim_start > 0 or trim_end > 0:
        # 按 sheet 分组、按 freq 排序后裁剪首尾
        from collections import OrderedDict
        grouped: Dict[str, list] = OrderedDict()
        for t in tasks:
            grouped.setdefault(t[0], []).append(t)
        tasks = []
        for sn, group in grouped.items():
            group.sort(key=lambda x: x[1])  # 按 freq 排序
            end = len(group) - trim_end if trim_end > 0 else len(group)
            trimmed = group[trim_start:end]
            if trimmed:
                tasks.extend(trimmed)
            if trim_start > 0 or trim_end > 0:
                removed = len(group) - len(trimmed)
                if removed > 0:
                    _log(log_cb, f"  ✂ {sn}: 去除 {removed} 个频点 (前{trim_start}后{trim_end})")

    _log(log_cb, f"共 {len(tasks)} 个待处理频点")
    return tasks


def _load_and_compute(
    tasks: List[Tuple[str, float, int, Any, DataSource]],
    sheets_info: List[Any],
    extrapolate_theta: bool,
    robust_peak: bool,
    parallel: int,
    cancel_callback=None,
    progress_callback=None,
    log_callback=None,
) -> Dict[str, List[Dict[str, Any]]]:
    """加载原始数据并执行计算，返回 sheet_results。"""
    total = len(tasks)
    sheet_results: Dict[str, List[Dict[str, Any]]] = {si.name: [] for si in sheets_info}
    if total == 0:
        return sheet_results

    progress_max = total * 2 + 5

    # 阶段 A: 加载数据
    _log(log_callback, f"读取 {total} 个频点数据...")
    _report(progress_callback, 0, progress_max, f"读取中 0/{total}")
    compute_tasks = []
    for i, (sheet_name, freq, csv_idx, lag_cfg, task_ds) in enumerate(tasks):
        if cancel_callback and cancel_callback():
            break
        raw = task_ds.read_sections(csv_idx)
        theta_list = list(task_ds.theta_angles)
        compute_tasks.append((sheet_name, freq, raw, lag_cfg, theta_list, extrapolate_theta, robust_peak))
        if (i + 1) % 20 == 0 or (i + 1) == total:
            _report(progress_callback, i + 1, progress_max, f"读取中 {i + 1}/{total}")

    data_done = len(compute_tasks)
    _report(progress_callback, data_done, progress_max, "计算中...")

    # 阶段 B: 计算（支持并行）
    if parallel > 1 and data_done > 1:
        _log(log_callback, f"并行计算: {parallel} 进程 × {data_done} 频点")
        chunk_size = max(1, len(compute_tasks) // parallel)
        chunks = [compute_tasks[i:i + chunk_size] for i in range(0, len(compute_tasks), chunk_size)]
        with ProcessPoolExecutor(max_workers=parallel) as executor:
            futures = [executor.submit(_compute_chunk, chunk) for chunk in chunks]
            completed = 0
            for fut in futures:
                if cancel_callback and cancel_callback():
                    for f in futures:
                        f.cancel()
                    break
                for sheet_name, row in fut.result():
                    sheet_results[sheet_name].append(row)
                    completed += 1
                _report(progress_callback, data_done + completed, progress_max,
                        f"计算中 {completed}/{data_done}")
    else:
        _run_compute_serial(compute_tasks, sheet_results, data_done, progress_max,
                            cancel_callback, progress_callback)

    return sheet_results


def _run_compute_serial(
    compute_tasks, sheet_results, data_done, progress_max,
    cancel_callback, progress_callback,
):
    """串行逐频点计算（单进程或 parallel=1）。"""
    for i, (sheet_name, freq, raw, lag_cfg, theta_list, do_extrap, rpk) in enumerate(compute_tasks):
        if cancel_callback and cancel_callback():
            break
        try:
            theta_arr = np.array(theta_list)
            row = _process_one_frequency(raw, freq, theta_arr, lag_cfg, do_extrapolate=do_extrap, robust_peak=rpk)
            sheet_results[sheet_name].append(row)
        except Exception as e:
            sheet_results[sheet_name].append({"frequency": freq, "_error": str(e)})
        if (i + 1) % 10 == 0 or (i + 1) == data_done:
            _report(progress_callback, data_done + i + 1, progress_max,
                    f"计算中 {i + 1}/{data_done}")


def _close_datasources(
    use_multi: bool,
    datasource: Optional[DataSource],
    datasource_map: Optional[Dict[str, DataSource]],
):
    """安全关闭所有数据源。"""
    if use_multi and datasource_map:
        for ds in datasource_map.values():
            try:
                ds.close()
            except Exception:
                pass
    elif datasource:
        datasource.close()


# ---------------------------------------------------------------------------
# 主管线
# ---------------------------------------------------------------------------

def run_pipeline(
    datasource: Optional[DataSource] = None,
    template_path: str = "",
    output_path: str = "",
    *,
    datasource_map: Optional[Dict[str, DataSource]] = None,
    lag_config_override: Optional[LagConfig] = None,
    plot_config: Optional[PlotConfig] = None,
    full_report_path: Optional[str] = None,
    extrapolate_theta: bool = False,
    freq_source: str = "datasource",
    trim_start: int = 0,
    trim_end: int = 0,
    chart_config: Optional[Dict[str, bool]] = None,
    robust_peak: bool = False,
    parallel: int = 1,
    cancel_callback: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """执行完整处理管线。

    Args:
        datasource:          数据源 (单源模式，向后兼容)。
        template_path:       模板 Excel 路径。
        output_path:         输出 Excel 路径。
        datasource_map:      工作表名→DataSource 映射 (多源模式)。
                             为 None 时使用 datasource 参数 (单源模式)。
        lag_config_override: LAG 配置覆盖。
        plot_config:         3D 图配置 (默认: 不生成图)。
        full_report_path:    完整报告路径。
        extrapolate_theta:   Theta 外推开关。
        freq_source:         "datasource" 或 "template"。
                             当模板 sheet 数<数据源数时，新 sheet 的频点来源。
        parallel:            (保留参数，当前仅串行)。
        cancel_callback / progress_callback / log_callback: 同旧版。

    Returns:
        {sheet_name: [row_dict, ...]}
    """
    if plot_config is None:
        plot_config = PlotConfig(embed_in_excel=False)

    t0 = time.time()

    # ---- 0. 参数校验 ----
    if datasource_map is not None and datasource is not None:
        raise ValueError("datasource 和 datasource_map 互斥，只能提供一个")
    if datasource_map is None and datasource is None:
        raise ValueError("必须提供 datasource 或 datasource_map")
    use_multi_ds = datasource_map is not None

    # ---- 1. 读取模板 + LAG ----
    _log(log_callback, f"读取模板: {template_path}")
    sheets_info = read_template(template_path)
    for si in sheets_info:
        _log(log_callback, f"  {si.name}: {len(si.frequencies)} 频点")

    # ---- 1.5: 自动扩增工作表 (模板 sheet 数 < 数据源数) ----
    if use_multi_ds and len(sheets_info) < len(datasource_map):
        _log(log_callback, f"模板 {len(sheets_info)} 个工作表 → {len(datasource_map)} 个数据源，自动扩增...")
        sheets_info = _expand_template_sheets(sheets_info, datasource_map, freq_source)
        for si in sheets_info:
            _log(log_callback, f"  {si.name}: {len(si.frequencies)} 频点 (来源: {'数据源' if freq_source == 'datasource' else '模板'})")

    if lag_config_override is not None and not lag_config_override.is_empty():
        for si in sheets_info:
            si.lag_config = lag_config_override
        _log(log_callback, "使用用户指定的 LAG 配置")

    # ---- 2. 收集任务 + 加载数据 + 计算 ----
    tasks = _collect_tasks(sheets_info, datasource, datasource_map, freq_source, trim_start, trim_end, log_callback)
    sheet_results = _load_and_compute(
        tasks, sheets_info, extrapolate_theta, robust_peak, parallel,
        cancel_callback, progress_callback, log_callback,
    )
    _close_datasources(use_multi_ds, datasource, datasource_map)

    # ---- 3. 写入 Excel ----
    total = len(tasks)
    progress_max = total * 2 + 5
    _log(log_callback, f"写入输出: {output_path}")
    _report(progress_callback, progress_max - 3, progress_max, "写入 Excel...")

    export_results(
        template_path=template_path,
        output_path=output_path,
        sheet_results=sheet_results,
        pattern_images=None,
        sheets_info=sheets_info,
        chart_config=chart_config or {},
        log_callback=log_callback,
    )
    _report(progress_callback, progress_max - 1, progress_max, "Excel 写入完成")

    # ---- 4. 完整报告 (可选) ----
    if full_report_path:
        _log(log_callback, f"生成完整报告: {full_report_path}")
        export_full_report(
            output_path=full_report_path,
            sheet_results=sheet_results,
        )

    elapsed = time.time() - t0
    total_rows = sum(len(v) for v in sheet_results.values())
    _log(log_callback, f"✓ 完成: {total_rows} 行, {elapsed:.1f}s")
    _report(progress_callback, progress_max, progress_max, "完成")

    return sheet_results

# ---------------------------------------------------------------------------
# 向后兼容: 保留旧版 run_batch_pipeline
# ---------------------------------------------------------------------------

def run_batch_pipeline(
    csv_path: str,
    template_path: str,
    output_path: str,
    *,
    lag_config_override=None,
    plot_config=None,
    full_report_path=None,
    extrapolate_theta: bool = False,
    cancel_callback=None,
    progress_callback=None,
    log_callback=None,
):
    """旧版 pipeline: 接受 CSV 路径，内部创建 MergedCSVParser。"""
    ds = MergedCSVParser(csv_path)
    return run_pipeline(
        datasource=ds,
        template_path=template_path,
        output_path=output_path,
        lag_config_override=lag_config_override,
        plot_config=plot_config,
        full_report_path=full_report_path,
        extrapolate_theta=extrapolate_theta,
        cancel_callback=cancel_callback,
        progress_callback=progress_callback,
        log_callback=log_callback,
    )


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _log(cb, msg):
    if cb: cb(msg)


def _report(cb, cur, tot, msg):
    if cb: cb(cur, tot, msg)


# ---------------------------------------------------------------------------
# 并行计算 worker（模块级，可 pickle，纯 numpy 数学）
# ---------------------------------------------------------------------------

def _compute_chunk(
    compute_tasks: List[Tuple[str, float, Dict[str, Any], Any, List[float], bool]],
) -> List[Tuple[str, Dict[str, Any]]]:
    """子进程中处理一批频点的纯计算任务。不读文件。

    每个任务: (sheet_name, freq, raw_data, lag_cfg, theta_list, extrapolate_theta)
    """
    import numpy as np
    results = []
    for sheet_name, freq, raw, lag_cfg, theta_list, do_extrap, rpk in compute_tasks:
        try:
            theta_raw = np.array(theta_list)
            row = _process_one_frequency(raw, freq, theta_raw, lag_cfg,
                                         do_extrapolate=do_extrap, robust_peak=rpk)
            results.append((sheet_name, row))
        except Exception as e:
            results.append((sheet_name, {"frequency": freq, "_error": str(e)}))
    return results
