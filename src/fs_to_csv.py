"""
FinalSummary .xlsx → merged CSV 转换器
=====================================
将 FinalSummary 格式的 Excel 转换为项目标准 merged CSV，
供 MergedCSVParser 直接读取。

读取复用 FinalSummarySource —— 与出报告走**同一条读取路径**，因此探测规则
与读出的数值保证一致，不再各自维护一套解析实现。

历史: 本模块曾自带一套结构探测 + 逐段读取 (section 外层 × 频点内层), 存在
两个问题: (1) 每个频点 sheet 被重复解析 4 遍; (2) phi 角度用 `range(n_phi)`
合成, 对非 1° 步进的文件 (2°/5°) 写出的角度轴完全错误。

GUI 和 CLI 共用同一入口: convert_fs_to_csv(src_path, out_path, progress_cb)
"""

from __future__ import annotations

import os
from collections.abc import Callable

import numpy as np

from .finalsummary_reader import FinalSummarySource
from .raw_converter import _write_normal_csv


def convert_fs_to_csv(
    src_path: str,
    out_path: str | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> str:
    """将 FinalSummary .xlsx 转换为 merged CSV。

    Args:
        src_path: 源 FinalSummary .xlsx 路径
        out_path: 输出 .csv 路径, 默认在同目录生成 `{stem}_merged.csv`
        progress_callback: (current, total, message) 进度回调

    Returns:
        输出 .csv 文件路径
    """
    if out_path is None:
        stem = os.path.splitext(os.path.basename(src_path))[0]
        # strip trailing .json if present
        if stem.endswith('.json'):
            stem = stem[:-5]
        out_path = os.path.join(os.path.dirname(src_path), f"{stem}_merged.csv")

    def _report(cur, tot, msg):
        if progress_callback:
            progress_callback(cur, tot, msg)

    _report(0, 1, "打开 workbook...")

    # cache_size=1: 本函数顺序读完每个频点即弃, 自己持有全部矩阵,
    # 再让 reader 缓存一份纯属内存翻倍 (139 频点 × 4 段 ≈ 178MB)。
    # read_only=True 由 FinalSummarySource 保证: read_only=False 会把全部
    # sheet 同时驻留内存 —— 实测 583MB / 139 sheet 必 OOM (本机总内存 11GB)。
    src = FinalSummarySource(src_path, cache_size=1)
    tp = pp = None
    try:
        freqs = src.frequencies
        n_freqs = len(freqs)
        theta_vals = src.theta_angles
        all_phi = src.phi_angles

        # phi=360° 与 phi=0° 重合 → 丢弃 >=360 的行。
        # 用真实角度值判断 (而非假定最后一行就是 360), 与 pipeline 的
        # 角度域标准化 `phi_mask = _pa < 360.0` 保持一致。
        keep = [i for i, p in enumerate(all_phi) if p < 360.0]
        phi_vals = [all_phi[i] for i in keep]

        n_theta, n_phi = len(theta_vals), len(keep)
        if n_theta == 0 or n_phi == 0:
            raise ValueError(f"{src_path}: 未读到有效的 theta/phi 角度轴")

        def _blank() -> np.ndarray:
            return np.full((n_freqs, n_phi, n_theta), np.nan, dtype=np.float64)

        tl, pl = _blank(), _blank()
        has_theta_phase = has_phi_phase = False

        for fi in range(n_freqs):
            sec = src.read_sections(fi)
            tl[fi] = sec["theta_logmag"][keep, :]
            pl[fi] = sec["phi_logmag"][keep, :]
            if sec["theta_phase"] is not None:
                if not has_theta_phase:
                    has_theta_phase, tp = True, _blank()
                tp[fi] = sec["theta_phase"][keep, :]
            if sec["phi_phase"] is not None:
                if not has_phi_phase:
                    has_phi_phase, pp = True, _blank()
                pp[fi] = sec["phi_phase"][keep, :]
            _report(fi + 1, n_freqs + 1, f"读取中... ({fi + 1}/{n_freqs})")
    finally:
        src.close()

    _report(n_freqs, n_freqs + 1, "写入 CSV...")
    _write_normal_csv(
        out_path,
        f"File Name: {os.path.basename(src_path)} (converted from FinalSummary)",
        freqs, theta_vals, phi_vals, tl, tp, pl, pp, None,
    )

    _report(n_freqs + 1, n_freqs + 1, "完成")
    return out_path
