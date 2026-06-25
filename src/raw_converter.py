"""
Raw CSV 转换 & 合并工具
=======================
集成 Antennatools 的原始 EMQuest 数据转换、合并和路径损耗补偿功能。

数据转换:
  实部/虚部格式 CSV (线性域: Theta/Phi Real + Imaginary)
  → 对数域格式 CSV (LogMag + Phase + Total Power)

路径损耗补偿:
  加载 EMQuest 导出的 .rsp CSV 文件, 应用路径损耗校准
  公式: Gain(dBi) = S21(dB) - Response(dB)

数据合并:
  多个分段 CSV (如 0-334deg + 333-360deg)
  → 合并为完整 360° 覆盖 CSV
"""

from __future__ import annotations

import csv
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .rsp_calibration import (
    RspCoverageResult, _apply_rsp_calibration, _apply_rsp_phase,
    _apply_rsp_to_logmag, _parse_rsp_file, _rsp_freq_bounds,
    check_rsp_coverage, parse_rsp_csv, parse_rsp_phase,
)


# ═══════════════════════════════════════════════════════════
# 数据转换: 实部/虚部格式 CSV → 对数域标准格式 CSV
# ═══════════════════════════════════════════════════════════

def convert_aborted_to_normal(
    input_path: str,
    output_path: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """将实部/虚部格式 (线性域) CSV 转换为对数域标准格式。

    Args:
        input_path:  实部/虚部格式 CSV 路径。
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
        total_power = _combine_power_db(theta_logmag, phi_logmag)

    if progress_callback:
        progress_callback(3, 4, "写入输出文件...")

    _write_normal_csv(output_path, metadata, freqs, theta_angles, phi_angles,
                      theta_logmag, theta_phase, phi_logmag, phi_phase, total_power)

    if progress_callback:
        progress_callback(4, 4, "完成")

    return output_path


def _parse_streaming(path: str, section_names: Tuple[str, ...],
                     block_parser: Callable):
    """流式逐 section 解析 CSV，避免全量 Python 字符串加载。

    一次只持有一个 section 的 Python 行在内存中，
    处理完毕立即释放，消除 list(csv.reader(f)) 的 3-5x 内存膨胀。
    """
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        try:
            metadata = next(reader)[0] if reader else ""
        except StopIteration:
            return {}, "", [], [], []

    sections = {}
    all_freqs = set()
    theta_angles = []
    phi_angles = []
    current_section = None
    section_rows: List[List[str]] = []

    for row in reader:
        r0 = row[0].strip() if row else ''
        if r0 in section_names:
            if current_section and section_rows:
                sec_data, fas, tas, pas = block_parser(section_rows)
                sections[current_section] = sec_data
                all_freqs.update(fas)
                if tas: theta_angles = tas
                if pas: phi_angles = pas
                section_rows = []  # 立即释放当前 section 的 Python 字符串
            current_section = r0
            section_rows.append(row)
            continue
        if current_section:
            section_rows.append(row)

    if current_section and section_rows:
        sec_data, fas, tas, pas = block_parser(section_rows)
        sections[current_section] = sec_data
        all_freqs.update(fas)
        if tas: theta_angles = tas
        if pas: phi_angles = pas

    return sections, metadata, sorted(all_freqs), theta_angles, phi_angles


def _parse_aborted(path: str):
    """解析实部/虚部格式 (线性域) CSV (EMQuest aborted 数据)。"""
    return _parse_streaming(path,
        ('Theta Real', 'Theta Imaginary', 'Phi Real', 'Phi Imaginary'),
        _parse_section_block)


def _parse_standard(path: str):
    """解析标准 EMQuest CSV 格式 (Theta/Phi LogMag + Phase)。

    标准格式中 section 按频点分组，每个频点内按 phi 行展开
    (与 aborted 格式的 phi 外层 / freq 内层相反)。
    """
    return _parse_streaming(path,
        ('Theta Log Magnitude', 'Theta Phase', 'Phi Log Magnitude', 'Phi Phase'),
        _parse_standard_section_block)


def _parse_standard_section_block(block):
    """解析标准格式的一个 section 中的多频点块。

    标准格式结构:
      Section Header: Theta Log Magnitude,Frequency  (MHz),...
      Freq block: ,1154,Theta Angle  (?,0,1,2,...
                  ,,Phi Angle  (?,Response  (dB),...
                  ,,0,val0,val1,...
                  ,,1,val0,val1,...

    返回: (data_3d, frequencies, theta_angles, phi_angles)
      data_3d shape: (n_freqs, n_phi, n_theta)
    """
    # 找所有频点块起始行 (包含 "Theta Angle" 的行)
    freq_rows = []
    for j, row in enumerate(block):
        for cell in row:
            if 'Theta Angle' in cell:
                freq_rows.append(j)
                break

    if not freq_rows:
        return None, [], [], []

    # 从第一个频点块解析 theta angle
    theta_angles = []
    for v in block[freq_rows[0]][2:]:
        sv = v.strip()
        if sv:
            try:
                theta_angles.append(float(sv))
            except ValueError:
                pass

    if not theta_angles:
        return None, [], [], []

    n_theta = len(theta_angles)

    # 遍历每个频点块，解析 phi + 频点值
    # 去重: 某些文件可能同一频点出现多次 (如 Phi Phase 段重复写入)
    frequencies = []
    freq_seen = set()
    phi_to_idx = {}
    phi_order = []
    freq_to_phi_data = {}  # freq -> {phi_idx: [values]}

    for fi, fr in enumerate(freq_rows):
        # 频点值在第 2 列
        freq_val = None
        try:
            freq_val = float(block[fr][1].strip())
        except (ValueError, IndexError):
            pass
        if freq_val is None:
            continue

        # 跳过重复频点 (保留首次出现)
        if freq_val in freq_seen:
            continue
        freq_seen.add(freq_val)
        frequencies.append(freq_val)

        # phi 数据行从 fr+2 开始（跳过 phi 标题行）
        data_start = fr + 2
        data_end = freq_rows[fi + 1] if fi + 1 < len(freq_rows) else len(block)

        for r in range(data_start, data_end):
            row = block[r]
            if len(row) < 3:
                continue
            # phi 值在第 3 列 (index 2)
            phi_str = row[2].strip() if len(row) > 2 else ""
            if not phi_str:
                continue
            try:
                phi_val = float(phi_str)
            except ValueError:
                continue

            if phi_val not in phi_to_idx:
                phi_to_idx[phi_val] = len(phi_order)
                phi_order.append(phi_val)

            pi = phi_to_idx[phi_val]
            if freq_val not in freq_to_phi_data:
                freq_to_phi_data[freq_val] = {}
            if pi not in freq_to_phi_data[freq_val]:
                freq_to_phi_data[freq_val][pi] = [np.nan] * n_theta

            # 读 theta 值
            for ti in range(min(n_theta, len(row) - 3)):
                v = row[3 + ti].strip() if 3 + ti < len(row) else ""
                if v:
                    try:
                        freq_to_phi_data[freq_val][pi][ti] = float(v)
                    except ValueError:
                        pass

    if not frequencies or not phi_order:
        return None, [], [], []

    frequencies = sorted(set(frequencies))
    n_freqs = len(frequencies)
    n_phi = len(phi_order)
    phi_angles = sorted(phi_order)

    # 构建 3D 数组
    data = np.full((n_freqs, n_phi, n_theta), np.nan, dtype=np.float32)
    freq_to_data_idx = {f: i for i, f in enumerate(frequencies)}
    sorted_phi_to_idx = {p: i for i, p in enumerate(phi_angles)}

    for freq_val, phi_dict in freq_to_phi_data.items():
        fi = freq_to_data_idx.get(freq_val)
        if fi is None:
            continue
        for pi_orig, values in phi_dict.items():
            phi_val = phi_order[pi_orig]
            pi_sorted = sorted_phi_to_idx.get(phi_val)
            if pi_sorted is None:
                continue
            data[fi, pi_sorted, :] = values

    return data, frequencies, theta_angles, phi_angles


def _parse_section_block(block):
    """解析一个 section 的多 Phi 块。

    自动检测频点列位置: 通过解析频点标题行
    (包含 "Frequency" 的单元格) 确定频点列索引。
    """
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
        sv = v.strip()
        if sv:
            try:
                theta_angles.append(float(sv))
            except ValueError:
                pass

    if not theta_angles:
        return None, [], [], []

    # 自动检测频点列: 从第一个 phi 块的标题行查找 "Frequency"
    freq_col = 1  # 默认值 (兼容旧格式)
    header_row_idx = theta_rows[0] + 1
    if header_row_idx < len(block):
        header_row = block[header_row_idx]
        for ci, cell in enumerate(header_row):
            if 'Frequency' in cell:
                freq_col = ci
                break

    # 数据起始列: 频点列之后
    data_start_col = freq_col + 1

    phi_angles = []
    frequencies = []
    n_theta = len(theta_angles)

    for bi, tr in enumerate(theta_rows):
        phi = 0.0
        try:
            phi = float(block[tr][1].strip())
        except (ValueError, IndexError):
            pass
        phi_angles.append(phi)

        data_start = tr + 2
        data_end = theta_rows[bi + 1] if bi + 1 < len(theta_rows) else len(block)

        for r in range(data_start, data_end):
            row = block[r]
            if not row or len(row) <= freq_col:
                continue
            freq_str = row[freq_col].strip() if freq_col < len(row) else ""
            if not freq_str:
                continue
            try:
                freq = float(freq_str)
                if freq not in frequencies:
                    frequencies.append(freq)
            except ValueError:
                pass

    frequencies = sorted(set(frequencies))
    n_freqs = len(frequencies)
    n_phi = len(phi_angles)

    if n_freqs == 0:
        return None, [], [], []

    data = np.zeros((n_freqs, n_phi, n_theta), dtype=np.float32)
    freq_to_idx = {f: i for i, f in enumerate(frequencies)}

    for bi, tr in enumerate(theta_rows):
        data_start = tr + 2
        data_end = theta_rows[bi + 1] if bi + 1 < len(theta_rows) else len(block)
        for r in range(data_start, data_end):
            row = block[r]
            if not row or len(row) <= freq_col:
                continue
            freq_str = row[freq_col].strip() if freq_col < len(row) else ""
            if not freq_str:
                continue
            try:
                freq = float(freq_str)
            except ValueError:
                continue
            fi = freq_to_idx.get(freq)
            if fi is None:
                continue
            for ti in range(min(n_theta, len(row) - data_start_col)):
                v = row[data_start_col + ti].strip() if data_start_col + ti < len(row) else ""
                if v:
                    try:
                        data[fi, bi, ti] = float(v)
                    except ValueError:
                        pass

    return data, frequencies, theta_angles, phi_angles


def _to_logmag(real_data, imag_data):
    if real_data is None or imag_data is None: return None
    mag = np.sqrt(real_data**2 + imag_data**2)
    return 20.0 * np.log10(np.maximum(mag, 1e-15))


def _to_phase(real_data, imag_data):
    if real_data is None or imag_data is None: return None
    return np.degrees(np.arctan2(imag_data, real_data))


def _combine_power_db(theta_logmag, phi_logmag):
    """合并两极化功率: Total Power (dB) = 10*log10(10^(θ/10) + 10^(φ/10))."""
    if theta_logmag is None or phi_logmag is None:
        return None
    tp = np.power(10.0, theta_logmag / 10.0) + np.power(10.0, phi_logmag / 10.0)
    return 10.0 * np.log10(np.maximum(tp, 1e-15))



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

def _detect_format(path: str) -> str:
    """检测 CSV 文件格式: 'standard' | 'aborted' | 'unknown'。"""
    with open(path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if line.startswith('Theta Log Magnitude,') or \
               line.startswith('Theta Phase,') or \
               line.startswith('Phi Log Magnitude,') or \
               line.startswith('Phi Phase,'):
                return 'standard'
            if line.startswith('Theta Real,') or \
               line.startswith('Theta Imaginary,') or \
               line.startswith('Phi Real,') or \
               line.startswith('Phi Imaginary,'):
                return 'aborted'
    return 'unknown'


def _scan_file_meta(path: str) -> Tuple[str, List[float], List[float], List[float], str]:
    """快速扫描文件元数据 (fmt/phi/freq/theta/meta)，不解析数据值。

    同时自动检测文件格式 (aborted/standard)，无需单独调用 _detect_format。
    一次文件打开完成格式检测 + 元数据扫描。
    """
    phis: List[float] = []
    freqs: List[float] = []
    theta: List[float] = []
    metadata = ""
    fmt = 'unknown'

    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        try:
            metadata = next(reader)[0] if reader else ""
        except StopIteration:
            return fmt, phis, freqs, theta, metadata

        # 收集前导行直到第一个 section header，同时检测格式
        preamble = []
        for row in reader:
            r0 = row[0].strip() if row else ''
            if r0 in ('Theta Real', 'Theta Imaginary', 'Phi Real', 'Phi Imaginary'):
                fmt = 'aborted'; preamble.append(row); break
            if r0 in ('Theta Log Magnitude', 'Theta Phase', 'Phi Log Magnitude', 'Phi Phase'):
                fmt = 'standard'; preamble.append(row); break
            preamble.append(row)

        if fmt == 'unknown':
            return fmt, phis, freqs, theta, metadata

        # 回放前导行给格式专属扫描器 (扫描器期望从第一个 section header 开始)
        def _replay():
            for r in preamble:
                yield r
            for r in reader:
                yield r

        if fmt == 'aborted':
            _scan_aborted_meta(_replay(), phis, freqs, theta)
        elif fmt == 'standard':
            _scan_standard_meta(_replay(), phis, freqs, theta)

    return fmt, phis, freqs, theta, metadata


def _scan_aborted_meta(reader, phis, freqs, theta):
    """快速扫描 aborted 格式的元数据（仅第一个 section: Theta Real）。

    收集: 所有 phi 值 + 第一个 phi 块的频点/角度。
    """
    section_names = ('Theta Real', 'Theta Imaginary', 'Phi Real', 'Phi Imaginary')
    in_first_section = False
    freq_col = 1
    state = 'seek_phi'  # seek_phi → saw_phi → collect_freqs → phi_done

    for row in reader:
        r0 = row[0].strip() if row else ''

        if r0 in section_names:
            if r0 == 'Theta Real':
                in_first_section = True
                continue
            elif in_first_section:
                break  # 离开第一个 section
            continue

        if not in_first_section:
            continue

        # 检测 Theta Angle 行 (phi 块边界)
        is_theta_row = any('Theta Angle' in (c or '') for c in row)
        if is_theta_row:
            try:
                phis.append(float(row[1].strip()))
            except (ValueError, IndexError):
                phis.append(0.0)

            if state == 'collect_freqs':
                state = 'phi_done'  # 进入第二个 phi 块，停止收集频点
            elif state != 'phi_done':
                state = 'saw_phi'
                if not theta:
                    for v in row[2:]:
                        sv = v.strip()
                        if sv:
                            try:
                                theta.append(float(sv))
                            except ValueError:
                                pass
            continue

        # 频点标题行
        if state == 'saw_phi':
            for ci, cell in enumerate(row):
                if 'Frequency' in (cell or ''):
                    freq_col = ci
                    state = 'collect_freqs'
                    break
            continue

        # 频点数据行
        if state == 'collect_freqs':
            if len(row) > freq_col:
                try:
                    fv = float(row[freq_col].strip())
                    if 300 < fv < 10000:
                        freqs.append(fv)
                except (ValueError, IndexError):
                    pass


def _scan_standard_meta(reader, phis, freqs, theta):
    """快速扫描 standard 格式的元数据。"""
    in_first_section = False
    got_theta = False
    got_freqs = False

    for row in reader:
        r0 = row[0].strip() if row else ''

        if r0 in ('Theta Log Magnitude', 'Theta Phase', 'Phi Log Magnitude', 'Phi Phase'):
            if r0 == 'Theta Log Magnitude':
                in_first_section = True
            elif in_first_section:
                break
            continue

        if not in_first_section:
            continue

        # 检测 Theta Angle 行 → freq + theta
        for ci, cell in enumerate(row):
            if 'Theta Angle' in cell:
                if not theta:
                    for v in row[2:]:
                        sv = v.strip()
                        if sv:
                            try:
                                theta.append(float(sv))
                            except ValueError:
                                pass
                    got_theta = True
                # 频点在 col[1]
                try:
                    fv = float(row[1].strip())
                    if 300 < fv < 10000 and fv not in freqs:
                        freqs.append(fv)
                        got_freqs = True
                except (ValueError, IndexError):
                    pass
                break

        # 检测 phi 数据行 (col[2] 是 phi 值)
        if got_theta and len(row) > 2:
            try:
                pv = float(row[2].strip())
                if pv not in phis:
                    phis.append(pv)
            except (ValueError, IndexError):
                pass


def merge_csv_files(
    file_paths: List[str],
    output_path: Optional[str] = None,
    rsp_h_path: Optional[str] = None,
    rsp_v_path: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """合并多个分段测量 CSV 为完整 360° 覆盖文件。

    流程:
      1. 快速扫描所有文件元数据 (phi/freq/theta) → 确定合并顺序
      2. 按最小 φ 升序排列 (主段先处理，补全段覆盖重叠区)
      3. 逐文件解析→转换→校准→合并 (每文件处理完即释放内存)
      4. 向量化计算 Total Power → 写出

    Args:
        file_paths: 待合并的 CSV 文件路径列表。
        output_path: 输出路径 (默认: 第一个文件目录下 _merged.csv)。
        rsp_h_path: H-pol RSP 校准文件 (可选, 用于实部/虚部文件的 Phi 分量校准)。
        rsp_v_path: V-pol RSP 校准文件 (可选, 用于实部/虚部文件的 Theta 分量校准)。
        progress_callback: (current, total, message)。

    Returns:
        输出文件路径。
    """
    if output_path is None:
        p = Path(file_paths[0])
        output_path = str(p.parent / f"{p.stem.split('_')[0]}_merged.csv")

    # 加载 RSP 校准数据 (如有)
    rsp_h: Dict[float, float] = {}
    rsp_v: Dict[float, float] = {}
    rsp_h_phase: Dict[float, float] = {}
    rsp_v_phase: Dict[float, float] = {}
    has_rsp = False
    if rsp_h_path and Path(rsp_h_path).exists():
        rsp_h = parse_rsp_csv(rsp_h_path)
        rsp_h_phase = parse_rsp_phase(rsp_h_path)
        if rsp_h:
            has_rsp = True
    if rsp_v_path and Path(rsp_v_path).exists():
        rsp_v = parse_rsp_csv(rsp_v_path)
        rsp_v_phase = parse_rsp_phase(rsp_v_path)
        if rsp_v:
            has_rsp = True

    logmag_sections = ('Theta Log Magnitude', 'Theta Phase',
                       'Phi Log Magnitude', 'Phi Phase')

    # ═══════════════════════════════════════════════════════════════
    # Phase 1: 快速扫描所有文件 → 收集元数据 + 确定处理顺序
    # ═══════════════════════════════════════════════════════════════
    file_meta: list = []  # [(path, fmt, phis, freqs, theta, metadata)]
    all_phis: set = set()
    base_freqs: List[float] = []
    base_theta: List[float] = []
    base_metadata = ""

    for fp in file_paths:
        fmt, phis, freqs, theta, meta = _scan_file_meta(fp)
        file_meta.append((fp, fmt, phis, freqs, theta, meta))
        all_phis.update(phis)
        if not base_freqs and freqs:
            base_freqs = sorted(freqs)
        if not base_theta and theta:
            base_theta = theta
        if not base_metadata and meta:
            base_metadata = meta

    if not base_freqs or not base_theta:
        raise ValueError("未能从任何文件中解析到有效数据，请检查文件格式。")

    # 按最小 φ 升序排列 (主段先，补全段后)
    file_meta.sort(key=lambda x: min(x[2]) if x[2] else 0)

    # 构建合并后的 phi 索引
    valid_phis = [p for p in all_phis if 0.0 <= p < _PHI_MAX]
    merged_phis = sorted(valid_phis)
    n_phi = len(merged_phis)
    n_theta = len(base_theta)
    n_freqs = len(base_freqs)
    phi_to_idx = {p: i for i, p in enumerate(merged_phis)}

    has_aborted = any(fmt == 'aborted' for _, fmt, _, _, _, _ in file_meta)
    total = len(file_paths) + 2 + (1 if has_aborted and has_rsp else 0)
    step = 0

    # ═══════════════════════════════════════════════════════════════
    # Phase 2: 预分配合并数组 (float32, ~58MB total for 4 sections)
    # ═══════════════════════════════════════════════════════════════
    merged_sections = {}
    for sn in logmag_sections:
        merged_sections[sn] = np.full((n_freqs, n_phi, n_theta),
                                      np.nan, dtype=np.float32)

    # ═══════════════════════════════════════════════════════════════
    # Phase 3: 逐文件处理 (解析→转换→校准→合并→释放)
    # ═══════════════════════════════════════════════════════════════
    for fp, fmt, phis, _, _, _ in file_meta:
        if progress_callback:
            progress_callback(step, total, f"读取: {Path(fp).name}")
        step += 1

        # 解析文件 (流式 section-by-section)
        if fmt == 'standard':
            sections, _, _, _, _ = _parse_standard(fp)
            lm_sections = {sn: sections.get(sn) for sn in logmag_sections}
        elif fmt == 'aborted':
            sections, _, freqs, _, _ = _parse_aborted(fp)
            tr = sections.get('Theta Real')
            ti = sections.get('Theta Imaginary')
            pr = sections.get('Phi Real')
            pi = sections.get('Phi Imaginary')

            tl = _to_logmag(tr, ti)
            tp = _to_phase(tr, ti)
            pl = _to_logmag(pr, pi)
            pp = _to_phase(pr, pi)

            del tr, ti, pr, pi, sections  # 立即释放 Re/Im 数组

            if has_rsp:
                tl, tp, pl, pp = _apply_rsp_calibration(
                    tl, tp, pl, pp, freqs, rsp_h, rsp_v, rsp_h_phase, rsp_v_phase)

            lm_sections = {
                'Theta Log Magnitude': tl,
                'Theta Phase': tp,
                'Phi Log Magnitude': pl,
                'Phi Phase': pp,
            }
        else:
            raise ValueError(f"无法识别文件格式: {Path(fp).name}")

        # 合并当前文件的 phi 切片到总数组中
        if progress_callback:
            progress_callback(step, total, f"合并: {Path(fp).name}")

        for sn in logmag_sections:
            sdata = lm_sections.get(sn)
            if sdata is None:
                continue
            for pi_local, phi_val in enumerate(phis):
                if phi_val in phi_to_idx:
                    pi_merged = phi_to_idx[phi_val]
                    if pi_local < sdata.shape[1]:
                        nf = min(n_freqs, sdata.shape[0])
                        nt = min(n_theta, sdata.shape[2])
                        merged_sections[sn][:nf, pi_merged, :nt] = \
                            sdata[:nf, pi_local, :nt]

        del lm_sections  # 释放当前文件的内存

    # ═══════════════════════════════════════════════════════════════
    # Phase 4: 向量化计算 Total Power + 写出
    # ═══════════════════════════════════════════════════════════════
    if progress_callback:
        progress_callback(step, total, "写入输出文件...")
    step += 1

    tl = merged_sections.get('Theta Log Magnitude')
    tp = merged_sections.get('Theta Phase')
    pl = merged_sections.get('Phi Log Magnitude')
    pp = merged_sections.get('Phi Phase')

    total_p = None
    if tl is not None and pl is not None:
        tp_lin = np.power(10.0, tl / 10.0) + np.power(10.0, pl / 10.0)
        total_p = 10.0 * np.log10(np.maximum(tp_lin, 1e-15))

    _write_normal_csv(output_path, base_metadata, base_freqs, base_theta,
                      merged_phis, tl, tp, pl, pp, total_p)

    if progress_callback:
        progress_callback(total, total, "完成")

    return output_path


_PHI_MAX = 360.0  # Phi 值的有效上界 (不含)


# ═══════════════════════════════════════════════════════════
# 频率范围检查 (用于 RSP 覆盖率校验)
# ═══════════════════════════════════════════════════════════

def extract_freq_range(file_path: str) -> Optional[Tuple[float, float]]:
    """提取 CSV 文件的频率范围 (min, max MHz)。

    使用现有解析器获取频点列表，不做完整数据解析。
    适用于标准格式和实部/虚部格式。

    Args:
        file_path: CSV 文件路径。

    Returns:
        (min_freq, max_freq) 或 None (无法识别格式)。
    """
    try:
        fmt = _detect_format(file_path)
        if fmt == 'standard':
            _, _, freqs, _, _ = _parse_standard(file_path)
        elif fmt == 'aborted':
            _, _, freqs, _, _ = _parse_aborted(file_path)
        else:
            return None
        if freqs:
            return (min(freqs), max(freqs))
    except Exception:
        pass
    return None


def batch_check_rsp_coverage(
    file_paths: List[str],
    rsp_h: Dict[float, float],
    rsp_v: Dict[float, float],
    only_fmt: Optional[str] = None,
) -> RspCoverageResult:
    """批量检查 RSP 校准数据是否覆盖所有文件的频率范围。

    可由 _on_tool_calibrate 和 _on_tool_merge 共用。

    Args:
        file_paths: 待检查的 CSV 文件路径列表。
        rsp_h: H-pol RSP 校准数据。
        rsp_v: V-pol RSP 校准数据。
        only_fmt: 仅检查此格式的文件 ('standard'/'aborted')。
                  None = 检查所有文件。

    Returns:
        RspCoverageResult: ok=True 表示全部覆盖，warnings 列出具体问题。
    """
    result = RspCoverageResult()

    if rsp_h:
        result.rsp_h_bounds = f"{min(rsp_h.keys()):.0f} - {max(rsp_h.keys()):.0f} MHz"
    else:
        result.rsp_h_bounds = "—"
    if rsp_v:
        result.rsp_v_bounds = f"{min(rsp_v.keys()):.0f} - {max(rsp_v.keys()):.0f} MHz"
    else:
        result.rsp_v_bounds = "—"

    if not rsp_h and not rsp_v:
        return result  # 无 RSP 数据，无需检查

    for p in file_paths:
        if not Path(p).exists():
            continue

        # 格式过滤
        if only_fmt:
            try:
                if _detect_format(p) != only_fmt:
                    continue
            except Exception:
                continue

        freq_range = extract_freq_range(p)
        if freq_range is None:
            continue
        freqs = [freq_range[0], freq_range[1]]

        fname = Path(p).name
        if rsp_h:
            w = check_rsp_coverage(rsp_h, freqs)
            for msg in w:
                result.warnings.append(f"  • {fname}: H-pol — {msg}")
        if rsp_v:
            w = check_rsp_coverage(rsp_v, freqs)
            for msg in w:
                result.warnings.append(f"  • {fname}: V-pol — {msg}")

    result.ok = len(result.warnings) == 0
    return result


def apply_path_loss_calibration(
    input_path: str,
    rsp_h_path: Optional[str],
    rsp_v_path: Optional[str],
    output_path: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """对 CSV 文件应用路径损耗补偿 (RSP 校准)。

    公式: Gain(dBi) = S21(dB) - Response(dB)

    - Response 来自 EMQuest 导出的 .rsp CSV 文件
    - H-pol (Phi) 使用 rsp_h, V-pol (Theta) 使用 rsp_v
    - 支持对数域格式和实部/虚部格式输入

    Args:
        input_path: 输入 CSV 路径 (对数域或实部/虚部格式)。
        rsp_h_path: H-pol RSP CSV 路径 (可选)。
        rsp_v_path: V-pol RSP CSV 路径 (可选)。
        output_path: 输出路径 (默认: 同目录下 _calibrated.csv)。
        progress_callback: (current, total, message)。

    Returns:
        输出文件路径。
    """
    if output_path is None:
        p = Path(input_path)
        output_path = str(p.parent / f"{p.stem}_calibrated.csv")

    total = 5
    step = 0

    # Step 1: 加载 RSP 数据
    if progress_callback:
        progress_callback(step, total, "加载 RSP 校准数据...")
    step += 1

    rsp_h: Dict[float, float] = {}
    rsp_v: Dict[float, float] = {}
    rsp_h_phase: Dict[float, float] = {}
    rsp_v_phase: Dict[float, float] = {}
    if rsp_h_path and Path(rsp_h_path).exists():
        rsp_h = parse_rsp_csv(rsp_h_path)
        rsp_h_phase = parse_rsp_phase(rsp_h_path)
    if rsp_v_path and Path(rsp_v_path).exists():
        rsp_v = parse_rsp_csv(rsp_v_path)
        rsp_v_phase = parse_rsp_phase(rsp_v_path)

    has_cal = bool(rsp_h or rsp_v)
    if not has_cal:
        raise ValueError("未提供有效的 RSP 校准文件，无法进行路径损耗补偿。")

    # Step 2: 解析输入文件
    if progress_callback:
        progress_callback(step, total, "解析输入文件...")
    step += 1

    fmt = _detect_format(input_path)

    if fmt == 'aborted':
        # 先转换为标准格式 (无校准)
        if progress_callback:
            progress_callback(step, total, "转换实部/虚部格式...")
        sections, meta, freqs, theta, phis = _parse_aborted(input_path)
        # Real/Imag → LogMag/Phase
        tr = sections.get('Theta Real')
        ti = sections.get('Theta Imaginary')
        pr = sections.get('Phi Real')
        pi = sections.get('Phi Imaginary')
        tl = _to_logmag(tr, ti)
        tp = _to_phase(tr, ti)
        pl = _to_logmag(pr, pi)
        pp = _to_phase(pr, pi)
    elif fmt == 'standard':
        sections, meta, freqs, theta, phis = _parse_standard(input_path)
        tl = sections.get('Theta Log Magnitude')
        tp = sections.get('Theta Phase')
        pl = sections.get('Phi Log Magnitude')
        pp = sections.get('Phi Phase')
    else:
        raise ValueError(f"无法识别文件格式: {Path(input_path).name}")

    if tl is None:
        raise ValueError("未能解析到有效数据。")

    step += 1

    # Step 3: 过滤 phi >= 360 (先过滤再校准，避免对无效 phi 计算)
    valid_phis = [(i, p) for i, p in enumerate(phis) if 0.0 <= p < _PHI_MAX]
    out_phis = [p for _, p in valid_phis]
    out_indices = [i for i, _ in valid_phis]

    def _slice_phi(data_3d):
        """保留有效 phi 列。"""
        if data_3d is None:
            return None
        return data_3d[:, out_indices, :]

    # Step 4: 应用 RSP 校准 (幅度 + 相位)
    if progress_callback:
        progress_callback(step, total, "应用路径损耗补偿...")
    step += 1

    tl, tp, pl, pp = _apply_rsp_calibration(
        tl, tp, pl, pp, freqs, rsp_h, rsp_v, rsp_h_phase, rsp_v_phase)

    # Step 5: 过滤 phi + 写入输出
    if progress_callback:
        progress_callback(step, total, "写入输出文件...")
    step += 1

    tl_out = _slice_phi(tl)
    tp_out = _slice_phi(tp)
    pl_out = _slice_phi(pl)
    pp_out = _slice_phi(pp)
    total_p = _combine_power_db(tl_out, pl_out)

    _write_normal_csv(output_path, meta, freqs, theta, out_phis,
                      tl_out, tp_out, pl_out, pp_out, total_p)

    if progress_callback:
        progress_callback(total, total, "完成")

    return output_path


# ═══════════════════════════════════════════════════════════
# 批量格式检查 + 转换
# ═══════════════════════════════════════════════════════════

def batch_check_and_convert(
    file_paths: List[str],
    output_dir: Optional[str] = None,
    rsp_h_path: Optional[str] = None,
    rsp_v_path: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict:
    """批量检查文件格式，并将实部/虚部格式文件转换为对数域标准格式。

    Args:
        file_paths: 待检查的文件路径列表。
        output_dir: 输出目录 (默认: 与源文件同目录)。
        rsp_h_path: H-pol RSP 校准文件 (可选)。
        rsp_v_path: V-pol RSP 校准文件 (可选)。
        progress_callback: (current, total, message)。

    Returns:
        {
            'checked': [...],          # 所有文件的检查结果 {path, name, format, size_mb}
            'aborted': [...],          # 检测到的实部/虚部格式文件路径
            'converted': [{source, output, calibrated}],  # 成功转换
            'failed': [{source, error}],                  # 转换失败
        }
    """
    result: Dict = {
        'checked': [],
        'aborted': [],
        'converted': [],
        'failed': [],
    }
    if not file_paths:
        return result

    total = len(file_paths) + 2
    step = 0

    has_rsp = bool(
        (rsp_h_path and Path(rsp_h_path).exists()) or
        (rsp_v_path and Path(rsp_v_path).exists())
    )

    # Step 1: 检查所有文件格式
    if progress_callback:
        progress_callback(step, total, "检查文件格式...")
    step += 1

    for fp in file_paths:
        try:
            fmt = _detect_format(fp)
        except Exception:
            fmt = 'unknown'
        info = {
            'path': fp,
            'name': Path(fp).name,
            'format': fmt,
            'size_mb': round(os.path.getsize(fp) / (1024 * 1024), 1) if os.path.isfile(fp) else 0,
        }
        result['checked'].append(info)
        if fmt == 'aborted':
            result['aborted'].append(fp)

    if progress_callback:
        progress_callback(step, total,
            f"检测完成: {len(result['checked'])} 个文件, "
            f"{len(result['aborted'])} 个实部/虚部格式")
    step += 1

    # Step 2: 批量转换实部/虚部格式文件
    if result['aborted']:
        # 确保输出目录存在
        out_dir = Path(output_dir) if output_dir else None
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
        n = len(result['aborted'])
        for i, fp in enumerate(result['aborted']):
            p = Path(fp)
            out = str((Path(output_dir) if output_dir else p.parent) /
                      f"{p.stem}_converted.csv")
            try:
                if progress_callback:
                    progress_callback(step, total,
                        f"转换 [{i+1}/{n}]: {p.name}")
                convert_aborted_to_normal(fp, out,
                    progress_callback=lambda c, t, m: None)
                # 如有 RSP，叠加校准
                if has_rsp:
                    rsp_h = rsp_h_path if rsp_h_path and Path(rsp_h_path).exists() else None
                    rsp_v = rsp_v_path if rsp_v_path and Path(rsp_v_path).exists() else None
                    apply_path_loss_calibration(
                        out, rsp_h, rsp_v, out,
                        progress_callback=lambda c, t, m: None)
                result['converted'].append({
                    'source': fp,
                    'output': out,
                    'calibrated': has_rsp,
                })
            except Exception as e:
                result['failed'].append({'source': fp, 'error': str(e)})

    if progress_callback:
        ok = len(result['converted'])
        fail = len(result['failed'])
        progress_callback(total, total,
            f"完成: {ok} 个转换成功, {fail} 个失败")

    return result
