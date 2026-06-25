"""
数据质量检测与修复模块
====================
检测天线测量数据中损坏的 phi 位置，通过插值从相邻正常 phi 修复。

检测:
  - ABORTED 格式: filename/metadata 检测 + 幅度模式分析
  - 标准格式: 局部连续性 + MAD 离群检测
  - 手动指定: 用户直接给出要修复的 phi 索引

修复:
  - 逆距离加权 K 近邻插值 (K=4，左右各2)
  - 同时修复 4 个 section (Theta/Phi Real+Imaginary)
  - 输出为标准 LogMag/Phase 格式 CSV
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np


# ═══════════════════════════════════════════════════════════
# 检测
# ═══════════════════════════════════════════════════════════

def detect_phi_anomalies(
    sections: Dict[str, np.ndarray],
    is_aborted: bool = True,
    q25_threshold: float = 0.72,
) -> List[int]:
    """检测损坏的 phi 位置。

    对 ABORTED 格式:
        用 25% 分位数的 mag(phi)/mag(phi-1) 比值检测幅度下降。
        若连续 >3 个 phi 的 Q25 < threshold → 标记段。
        返回所有疑似段中的 phi 索引。

    对标准格式:
        MAD 离群检测 + 局部连续性检查。
    """
    if is_aborted:
        return _detect_aborted_pattern(sections, q25_threshold=q25_threshold)
    else:
        return _detect_standard_outliers(sections)


def _detect_aborted_pattern(
    sections: Dict[str, np.ndarray],
    q25_threshold: float = 0.72,
) -> List[int]:
    """检测 ABORTED 格式的 phi 损坏模式。

    策略: 检测 `mag(pi) / mag(pi-1)` 的 25% 分位数 < threshold
    的连续段 > MIN_RUN 个 phi → 标记为损坏。
    """
    MIN_RUN = 4
    re_sec = sections.get('Theta Real')
    im_sec = sections.get('Theta Imaginary')
    if re_sec is None or im_sec is None:
        return []
    n_freq, n_phi, n_theta = re_sec.shape
    if n_phi < 4:
        return []

    mag_all = np.sqrt(re_sec**2 + im_sec**2)

    # 计算 Q25 比值
    q25_ratios = np.full(n_phi - 1, np.nan)
    for pi in range(1, n_phi):
        m_prev = mag_all[:, pi - 1, :].ravel()
        m_curr = mag_all[:, pi, :].ravel()
        valid = (m_prev > 1e-15) & np.isfinite(m_prev) & np.isfinite(m_curr)
        if np.sum(valid) > 10:
            ratios = m_curr[valid] / m_prev[valid]
            q25_ratios[pi - 1] = np.percentile(ratios, 25)

    # 找连续低比值段
    bad_areas = []
    run_start = None
    for pi in range(len(q25_ratios)):
        if np.isfinite(q25_ratios[pi]) and q25_ratios[pi] < q25_threshold:
            # q25_ratios[pi] is for transition phi+1/phi
            # low ratio means phi+1 might be bad
            if run_start is None:
                run_start = pi
        else:
            if run_start is not None and (pi - run_start) >= MIN_RUN:
                bad_areas.append((run_start + 1, pi + 1))
            run_start = None

    if run_start is not None and (n_phi - 1 - run_start) >= MIN_RUN:
        bad_areas.append((run_start + 1, n_phi))

    if not bad_areas:
        return []

    # 标记所有坏段中的 phi
    bad_phis = set()
    for start, end in bad_areas:
        for p in range(start, end):
            bad_phis.add(p)

    return sorted(bad_phis)


def _detect_standard_outliers(sections: Dict[str, np.ndarray]) -> List[int]:
    """标准格式 MAD 离群检测。"""
    bad_phis = set()

    for sec_name in ('Theta Log Magnitude', 'Theta Phase',
                     'Phi Log Magnitude', 'Phi Phase'):
        data = sections.get(sec_name)
        if data is None or data.ndim != 3:
            continue
        n_freq, n_phi, n_theta = data.shape
        if n_phi < 3:
            continue

        for fi in range(n_freq):
            for ti in range(n_theta):
                vals = data[fi, :, ti]
                valid = np.isfinite(vals)
                if np.sum(valid) < 3:
                    continue
                phi_valid = np.where(valid)[0]
                vals_valid = vals[valid]
                median = np.median(vals_valid)
                mad = np.median(np.abs(vals_valid - median))
                if mad < 1e-15:
                    continue
                threshold = 4.0 * mad / 0.6745  # 4-sigma

                for pi in phi_valid:
                    left_good = None
                    for d in range(1, 6):
                        if pi - d >= 0 and valid[pi - d]:
                            left_good = pi - d
                            break
                    right_good = None
                    for d in range(1, 6):
                        if pi + d < n_phi and valid[pi + d]:
                            right_good = pi + d
                            break
                    if left_good is not None and right_good is not None:
                        local_mean = (vals[left_good] + vals[right_good]) / 2.0
                        if abs(vals[pi] - local_mean) > threshold:
                            bad_phis.add(int(pi))

    return sorted(bad_phis)


# ═══════════════════════════════════════════════════════════
# 修复
# ═══════════════════════════════════════════════════════════

def repair_phi_interpolation(
    sections: Dict[str, np.ndarray],
    bad_phis: List[int],
    k_neighbors: int = 4,
    max_search: int = 20,
) -> Dict[str, np.ndarray]:
    """逆距离加权 K 近邻插值修复。

    对每个坏 phi，找 K 个最近正常 phi，加权平均修复。

    Args:
        sections: section_name → 3D array (n_freq, n_phi, n_theta)。
        bad_phis: 要修复的 phi 索引。
        k_neighbors: 使用的近邻数。
        max_search: 最大搜索距离 (phi 步数)。

    Returns:
        修复后的 sections dict。
    """
    if not bad_phis:
        return sections

    repaired = {}
    bad_set = set(bad_phis)

    for sec_name, data in sections.items():
        if data is None or data.ndim != 3:
            repaired[sec_name] = data
            continue

        n_freq, n_phi, n_theta = data.shape
        out = data.copy()

        for phi in bad_phis:
            if phi < 0 or phi >= n_phi:
                continue

            # 找 K 个最近正常 phi
            neighbors = []
            for d in range(1, max_search + 1):
                for side in (-d, d):
                    p = phi + side
                    if 0 <= p < n_phi and p not in bad_set:
                        neighbors.append((p, abs(d)))
                        if len(neighbors) >= k_neighbors:
                            break
                if len(neighbors) >= k_neighbors:
                    break

            if not neighbors:
                continue

            weights = np.array([1.0 / (dist + 1e-10) for _, dist in neighbors])
            weights /= weights.sum()

            for fi in range(n_freq):
                for ti in range(n_theta):
                    values = []
                    valid_weights = []
                    for (np_idx, _), w in zip(neighbors, weights):
                        v = data[fi, np_idx, ti]
                        if np.isfinite(v):
                            values.append(v)
                            valid_weights.append(w)
                    if values:
                        valid_weights = np.array(valid_weights)
                        valid_weights /= valid_weights.sum()
                        out[fi, phi, ti] = sum(v * w for v, w in zip(values, valid_weights))

        repaired[sec_name] = out

    return repaired


# ═══════════════════════════════════════════════════════════
# 一键流程
# ═══════════════════════════════════════════════════════════

def auto_detect_and_repair(
    csv_path: str,
    output_path: Optional[str] = None,
    k_neighbors: int = 4,
    q25_threshold: float = 0.72,
    max_search: int = 20,
    force_phis: Optional[List[int]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict:
    """检测+修复 CSV 文件中的 phi 损坏数据。

    Args:
        csv_path: 输入 CSV 路径。
        output_path: 输出路径 (默认: *_repaired.csv)。
        k_neighbors: 修复近邻数。
        q25_threshold: Q25 比值门限。
        max_search: 修复搜索距离。
        force_phis: 手动指定的坏 phi 列表 (跳过自动检测)。
        progress_callback: (current, total, message)。

    Returns:
        {input, output, format, total_phis, bad_phis, repaired_count, ...}
    """
    from .raw_converter import _detect_format, _parse_aborted, _parse_standard

    if output_path is None:
        p = Path(csv_path)
        output_path = str(p.parent / f"{p.stem}_repaired.csv")

    result = {
        'input': csv_path,
        'output': output_path,
        'bad_phis': [],
        'total_phis': 0,
        'format': 'unknown',
    }

    def _log(c, t, m):
        if progress_callback:
            progress_callback(c, t, m)

    _log(0, 5, "检测文件格式...")
    fmt = _detect_format(csv_path)
    result['format'] = fmt

    if fmt not in ('aborted', 'standard'):
        _log(5, 5, f"格式不支持: {fmt}")
        return result

    _log(1, 5, f"解析文件 ({fmt})...")
    if fmt == 'aborted':
        sections, meta, freqs, theta, phis = _parse_aborted(csv_path)
    else:
        sections, meta, freqs, theta, phis = _parse_standard(csv_path)

    result['total_phis'] = len(phis)
    result['theta_count'] = len(theta)
    result['freq_count'] = len(freqs)

    if len(phis) < 3:
        _log(5, 5, "phi 不足 3 个，跳过")
        return result

    # 检测
    if force_phis is not None:
        bad_phis = sorted([p for p in force_phis if 0 <= p < len(phis)])
        result['detection_method'] = 'manual'
    else:
        _log(2, 5, "检测损坏 phi...")
        bad_phis = detect_phi_anomalies(
            sections, is_aborted=(fmt == 'aborted'),
            q25_threshold=q25_threshold)
        result['detection_method'] = 'auto'

    result['bad_phis'] = bad_phis

    if not bad_phis:
        _log(5, 5, "未发现损坏")
        return result

    # 修复
    _log(3, 5, f"修复 {len(bad_phis)}/{len(phis)} phi (K={k_neighbors})...")
    repaired_sections = repair_phi_interpolation(
        sections, bad_phis, k_neighbors=k_neighbors, max_search=max_search)

    # 输出
    _log(4, 5, "写入输出文件...")
    _write_repaired_csv(output_path, meta, freqs, theta, phis,
                        repaired_sections, is_aborted=(fmt == 'aborted'))

    result['repaired_count'] = len(bad_phis)
    _log(5, 5, f"完成: 修复 {len(bad_phis)} 个 phi")
    return result


# ═══════════════════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════════════════

def _write_repaired_csv(
    path: str, metadata: str, freqs: List[float],
    theta: List[float], phi: List[float],
    sections: Dict[str, np.ndarray],
    is_aborted: bool,
) -> None:
    """写出修复后的标准格式 CSV。"""
    n_freqs = len(freqs)
    n_theta = len(theta)
    n_phi = len(phi)
    n_cols = 1 + 1 + n_theta

    if is_aborted:
        tr = sections.get('Theta Real')
        ti = sections.get('Theta Imaginary')
        pr = sections.get('Phi Real')
        pi = sections.get('Phi Imaginary')
        tl = _to_logmag(tr, ti)
        tp = _to_phase(tr, ti)
        pl = _to_logmag(pr, pi)
        pp = _to_phase(pr, pi)
    else:
        tl = sections.get('Theta Log Magnitude')
        tp = sections.get('Theta Phase')
        pl = sections.get('Phi Log Magnitude')
        pp = sections.get('Phi Phase')

    total_p = None
    if tl is not None and pl is not None:
        tp_lin = np.power(10.0, tl / 10.0) + np.power(10.0, pl / 10.0)
        total_p = 10.0 * np.log10(np.maximum(tp_lin, 1e-15))

    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow([metadata])
        for sname, sdata in [
            ("Theta Log Magnitude", tl), ("Theta Phase", tp),
            ("Phi Log Magnitude", pl), ("Phi Phase", pp),
            ("Total Power", total_p),
        ]:
            if sdata is None:
                continue
            w.writerow(["Format"] + [""] * (n_cols - 1))
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


def _to_logmag(data, imag_data):
    if data is None or imag_data is None:
        return None
    mag = np.sqrt(data ** 2 + imag_data ** 2)
    return 20.0 * np.log10(np.maximum(mag, 1e-15))


def _to_phase(data, imag_data):
    if data is None or imag_data is None:
        return None
    return np.degrees(np.arctan2(imag_data, data))
