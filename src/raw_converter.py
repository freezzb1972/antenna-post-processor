"""
Raw CSV 转换 & 合并工具
=======================
集成 Antennatools 的原始 EMQuest 数据转换和合并功能。

数据转换:
  原始 aborted CSV (Theta Real/Imag, Phi Real/Imag)
  → 标准 CSV (Theta/Phi LogMag + Phase + Total Power)

数据合并:
  多个分段 CSV (如 0-334deg + 333-360deg)
  → 合并为完整 360° 覆盖 CSV
"""

from __future__ import annotations

import csv
import math
import os
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np


# ═══════════════════════════════════════════════════════════
# 数据转换: aborted CSV → normal CSV
# ═══════════════════════════════════════════════════════════

def convert_aborted_to_normal(
    input_path: str,
    output_path: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """将 EMQuest aborted CSV 转换为标准格式。

    Args:
        input_path:  aborted CSV 路径。
        output_path: 输出路径 (默认: 同目录下 _converted.csv)。
        progress_callback: (current, total, message)。

    Returns:
        输出文件路径。
    """
    if output_path is None:
        p = Path(input_path)
        output_path = str(p.parent / f"{p.stem}_converted.csv")

    if progress_callback:
        progress_callback(0, 4, "读取原始文件...")

    # 解析原始文件
    sections, metadata, freqs, theta_angles, phi_angles = _parse_aborted(input_path)

    if progress_callback:
        progress_callback(1, 4, "转换数据格式...")

    # 构建标准格式输出
    n_theta = len(theta_angles)
    n_phi = len(phi_angles)
    n_freqs = len(freqs)

    # 转换: Re/Im → LogMag/Phase
    theta_real = sections.get("Theta Real")
    theta_imag = sections.get("Theta Imaginary")
    phi_real = sections.get("Phi Real")
    phi_imag = sections.get("Phi Imaginary")

    theta_logmag = _to_logmag(theta_real, theta_imag) if theta_real is not None else None
    theta_phase = _to_phase(theta_real, theta_imag) if theta_real is not None else None
    phi_logmag = _to_logmag(phi_real, phi_imag) if phi_real is not None else None
    phi_phase = _to_phase(phi_real, phi_imag) if phi_real is not None else None

    if progress_callback:
        progress_callback(2, 4, "计算 Total Power...")

    # Total Power = theta_power + phi_power
    total_power = None
    if theta_logmag is not None and phi_logmag is not None:
        tp = np.power(10.0, theta_logmag / 10.0) + np.power(10.0, phi_logmag / 10.0)
        total_power = 10.0 * np.log10(np.maximum(tp, 1e-15))

    if progress_callback:
        progress_callback(3, 4, "写入输出文件...")

    _write_normal_csv(output_path, metadata, freqs, theta_angles, phi_angles,
                      theta_logmag, theta_phase, phi_logmag, phi_phase, total_power)

    if progress_callback:
        progress_callback(4, 4, "完成")

    return output_path


def _parse_aborted(path: str):
    """解析 aborted CSV 格式。"""
    with open(path, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))

    metadata = rows[0][0] if rows else ""

    section_names = ('Theta Real', 'Theta Imaginary', 'Phi Real', 'Phi Imaginary')
    sec_start = {}
    for i, row in enumerate(rows):
        if row and row[0].strip() in section_names:
            sec_start[row[0].strip()] = i

    sections = {}
    all_freqs = set()
    theta_angles = []
    phi_angles = []

    for sn, start in sec_start.items():
        # Find next section boundary
        next_starts = [s for n, s in sec_start.items() if s > start]
        end = min(next_starts) if next_starts else len(rows)

        sec_data, fas, tas, pas = _parse_section_block(rows[start:end])
        sections[sn] = sec_data
        all_freqs.update(fas)
        if tas: theta_angles = tas
        if pas: phi_angles = pas

    freqs = sorted(all_freqs)
    return sections, metadata, freqs, theta_angles, phi_angles


def _parse_section_block(block):
    """解析一个 section 的多 Phi 块。"""
    theta_rows = []
    for j, r in enumerate(block):
        for c in r:
            if 'Theta Angle' in c:
                theta_rows.append(j)
                break

    if not theta_rows:
        return None, [], [], []

    theta_angles = []
    for v in block[theta_rows[0]][2:]:
        if v.strip():
            try: theta_angles.append(float(v))
            except ValueError: pass

    phi_angles = []
    frequencies = []
    n_theta = len(theta_angles)

    for bi, tr in enumerate(theta_rows):
        phi = 0.0
        try: phi = float(block[tr][1].strip())
        except (ValueError, IndexError): pass
        phi_angles.append(phi)

        data_start = tr + 2
        data_end = theta_rows[bi + 1] if bi + 1 < len(theta_rows) else len(block)

        for r in range(data_start, data_end):
            if not block[r] or not block[r][1].strip():
                continue
            try:
                freq = float(block[r][1].strip())
                if freq not in frequencies:
                    frequencies.append(freq)
            except ValueError:
                pass

    frequencies = sorted(set(frequencies))
    n_freqs = len(frequencies)
    n_phi = len(phi_angles)

    data = np.zeros((n_freqs, n_phi, n_theta))
    freq_to_idx = {f: i for i, f in enumerate(frequencies)}

    for bi, tr in enumerate(theta_rows):
        data_start = tr + 2
        data_end = theta_rows[bi + 1] if bi + 1 < len(theta_rows) else len(block)
        for r in range(data_start, data_end):
            if not block[r] or not block[r][1].strip():
                continue
            try:
                freq = float(block[r][1].strip())
            except ValueError:
                continue
            fi = freq_to_idx.get(freq)
            if fi is None: continue
            for ti in range(min(n_theta, len(block[r]) - 2)):
                v = block[r][2 + ti].strip() if 2 + ti < len(block[r]) else ""
                if v:
                    try: data[fi, bi, ti] = float(v)
                    except ValueError: pass

    return data, frequencies, theta_angles, phi_angles


def _to_logmag(real_data, imag_data):
    if real_data is None or imag_data is None: return None
    mag = np.sqrt(real_data**2 + imag_data**2)
    return 20.0 * np.log10(np.maximum(mag, 1e-15))


def _to_phase(real_data, imag_data):
    if real_data is None or imag_data is None: return None
    return np.degrees(np.arctan2(imag_data, real_data))


def _write_normal_csv(path, metadata, freqs, theta, phi,
                      tl, tp, pl, pp, total):
    """写出标准 EMQuest CSV 格式。"""
    n_freqs = len(freqs)
    n_theta = len(theta)
    n_phi = len(phi)
    n_cols = 1 + 1 + n_theta  # row_label + frequency + theta values

    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow([metadata])

        sections = [
            ("Theta Log Magnitude", tl),
            ("Theta Phase", tp),
            ("Phi Log Magnitude", pl),
            ("Phi Phase", pp),
            ("Total Power", total),
        ]

        for sname, sdata in sections:
            if sdata is None: continue
            w.writerow(["Format", ""] + [""] * (n_cols - 2))
            w.writerow([sname, "Frequency  (MHz)"] + [""] * (n_cols - 2))

            for fi in range(n_freqs):
                w.writerow(["", f"{freqs[fi]:.6f}", "Theta Angle  (deg)"] + theta)
                w.writerow(["", "", "Phi Angle  (deg)"] + ["Response  (dB)"] * n_theta)
                for pi in range(n_phi):
                    row = ["", "", f"{phi[pi]:.6f}"]
                    for ti in range(n_theta):
                        v = sdata[fi, pi, ti]
                        row.append(f"{v:.6f}" if np.isfinite(v) else "")
                    w.writerow(row)
                if fi < n_freqs - 1:
                    w.writerow([""] * n_cols)
            w.writerow([""] * n_cols)


# ═══════════════════════════════════════════════════════════
# 数据合并: 多个分段 CSV → 完整 360° CSV
# ═══════════════════════════════════════════════════════════

def merge_csv_files(
    file_paths: List[str],
    output_path: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """合并多个分段测量 CSV 为完整 360° 覆盖文件。

    典型场景: 0-334deg.csv + 333-360deg.csv → merged_0-360.csv

    Args:
        file_paths: 待合并的 CSV 文件路径列表。
        output_path: 输出路径 (默认: 第一个文件目录下 _merged.csv)。
        progress_callback: (current, total, message)。

    Returns:
        输出文件路径。
    """
    if output_path is None:
        p = Path(file_paths[0])
        output_path = str(p.parent / f"{p.stem.split('_')[0]}_merged.csv")

    total = len(file_paths) + 2
    step = 0

    # 读所有文件
    all_data = []
    all_phis = set()
    base_metadata = ""
    base_freqs = []
    base_theta = []
    section_names = []

    for fp in file_paths:
        if progress_callback:
            progress_callback(step, total, f"读取: {Path(fp).name}")
        step += 1

        sections, meta, freqs, theta, phis = _parse_aborted(fp)
        all_data.append(sections)
        all_phis.update(phis)
        if not base_freqs: base_freqs = freqs
        if not base_theta: base_theta = theta
        if not section_names and sections:
            section_names = [k for k in sections.keys()]
        base_metadata = meta

    merged_phis = sorted(all_phis)
    n_phi = len(merged_phis)
    phi_to_idx = {p: i for i, p in enumerate(merged_phis)}

    if progress_callback:
        progress_callback(step, total, "合并数据...")
    step += 1

    # 合并各 section
    n_theta = len(base_theta)
    n_freqs = len(base_freqs)
    merged_sections = {}

    for sn in section_names:
        merged = np.full((n_freqs, n_phi, n_theta), np.nan)
        for si, sections in enumerate(all_data):
            sdata = sections.get(sn)
            if sdata is None: continue
            _, _, _, phis = _parse_file_phis(file_paths[si])
            for pi_local, phi_val in enumerate(phis):
                if phi_val in phi_to_idx:
                    pi_merged = phi_to_idx[phi_val]
                    n_rows = min(sdata.shape[1], n_phi)
                    if pi_local < n_rows:
                        merged[:, pi_merged, :] = sdata[:, pi_local, :]
        merged_sections[sn] = merged

    if progress_callback:
        progress_callback(step, total, "写入输出文件...")
    step += 1

    # 拆分 Real/Imag → LogMag/Phase
    theta_real = merged_sections.get("Theta Real")
    theta_imag = merged_sections.get("Theta Imaginary")
    phi_real = merged_sections.get("Phi Real")
    phi_imag = merged_sections.get("Phi Imaginary")

    tl = _to_logmag(theta_real, theta_imag)
    tp = _to_phase(theta_real, theta_imag)
    pl = _to_logmag(phi_real, phi_imag)
    pp = _to_phase(phi_real, phi_imag)
    total_p = None
    if tl is not None and pl is not None:
        tp_lin = np.power(10.0, tl / 10.0) + np.power(10.0, pl / 10.0)
        total_p = 10.0 * np.log10(np.maximum(tp_lin, 1e-15))

    _write_normal_csv(output_path, base_metadata, base_freqs, base_theta,
                      merged_phis, tl, tp, pl, pp, total_p)

    if progress_callback:
        progress_callback(total, total, "完成")

    return output_path


def _parse_file_phis(path: str):
    """快速读取文件的 phi angle 列表。"""
    with open(path, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    phis = set()
    for row in rows:
        for cell in row:
            if 'Theta Angle' in cell:
                theta_row_idx = rows.index(row)
                for r in rows[theta_row_idx + 2:]:
                    if r and r[1].strip():
                        for c in r[2:]:
                            if 'Theta Angle' in c:
                                # find next theta row
                                pass
        break
    return [], [], []
