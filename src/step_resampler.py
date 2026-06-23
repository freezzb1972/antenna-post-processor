"""
EMQuest Merged CSV 步进重采样器
===============================
将原始测量数据按指定角度步长重采样，生成相同格式的 CSV 文件。
用于研究不同测试步进对天线参数精度的影响。

输入: merged CSV（任意 theta/phi 步进）
输出: 相同格式的 CSV（指定的 theta/phi 步进）
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, List, Optional, Tuple


def resample_merged_csv(
    input_path: str,
    output_path: str,
    theta_step_deg: float,
    phi_step_deg: float,
    *,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """将 merged CSV 重采样到指定步进。

    Args:
        input_path:        源 CSV 路径
        output_path:       输出 CSV 路径
        theta_step_deg:    目标 theta 步进（度），如 5.0
        phi_step_deg:      目标 phi 步进（度），如 5.0
        progress_callback:  (current, total, message)

    Returns:
        输出文件路径
    """
    # 读取全部数据
    sections_data, theta_angles, phi_angles, sfreqs = _read_all(input_path)
    section_freqs = sfreqs  # dict: section_name → [freqs]

    # 计算索引步长
    orig_theta_step = round(theta_angles[1] - theta_angles[0], 6) if len(theta_angles) > 1 else 1.0
    orig_phi_step = phi_angles[1] - phi_angles[0] if len(phi_angles) > 1 else 1.0

    theta_stride = max(1, int(round(theta_step_deg / orig_theta_step)))
    phi_stride = max(1, int(round(phi_step_deg / orig_phi_step)))

    new_theta = theta_angles[::theta_stride]
    new_phi = phi_angles[::phi_stride]

    # 使用第一个 section 的频点数作为 total
    first_section = list(section_freqs.values())[0]
    total = len(first_section) * 4
    current = 0

    # 写入输出
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        section_names = [
            "Theta Log Magnitude",
            "Theta Phase",
            "Phi Log Magnitude",
            "Phi Phase",
        ]

        for si, sname in enumerate(section_names):
            # 写入 section header
            f.write(f"{sname},\n")

            if sname not in sections_data:
                continue

            blocks = sections_data[sname]
            freqs = section_freqs.get(sname, [])

            for fi, data_2d in enumerate(blocks):
                if fi >= len(freqs):
                    continue
                freq = freqs[fi]
                # 频点标题行
                theta_str = ",".join([""] + [str(freq)] + ["Theta Angle  (?"] + [f"{t}" for t in new_theta])
                # theta 值以数字形式，不带单位
                theta_str_simple = ",".join([""] + [str(freq)] + ["Theta Angle"] + [f"{t}" for t in new_theta])
                f.write(f"{theta_str_simple}\n")

                # Phi 标题行
                phi_str = ",".join([""] + [""] + ["Phi / Response"] + [f"{t}" for t in new_theta])
                f.write(f"{phi_str}\n")

                # 数据行: 每行一个 phi
                for pi in range(0, len(phi_angles), phi_stride):
                    if pi >= len(data_2d):
                        break
                    phi_val = phi_angles[pi]
                    row_data = data_2d[pi]
                    # 提取重采样后的 theta 值
                    sampled_vals = [row_data[ti] for ti in range(0, len(theta_angles), theta_stride)]
                    vals_str = ",".join([f"{v:.6f}" for v in sampled_vals])
                    f.write(f",,{phi_val:.6f},{vals_str}\n")

                current += 1
                if progress_callback:
                    progress_callback(current, total,
                        f"处理中 {sname} freq={freq:.0f}MHz")

    return output_path


def _read_all(input_path: str) -> Tuple[dict, list, list, dict]:
    """读取 merged CSV 全部数据到内存。

    Returns:
        (sections_data, theta_angles, phi_angles, section_freqs)
        sections_data: {section_name: [[phi_data_2d_per_freq], ...]}
        section_freqs: {section_name: [freq_values]}
    """
    encoding = "utf-8-sig"

    section_names_set = {
        "Theta Log Magnitude", "Theta Phase",
        "Phi Log Magnitude", "Phi Phase",
    }

    sections_data = {s: [] for s in section_names_set}
    section_freqs = {s: [] for s in section_names_set}
    theta_angles = []
    phi_angles = []

    current_section = None
    current_freq_idx = -1
    section_freq_idx = {s: -1 for s in section_names_set}
    in_block = False

    with open(input_path, "r", encoding=encoding, newline="") as f:
        for line in f:
            stripped = line.strip()

            # Section header
            section_found = None
            for sn in section_names_set:
                if stripped.startswith(sn + ",") or stripped == sn:
                    section_found = sn
                    break
            if section_found:
                current_section = section_found
                in_block = False
                continue

            if current_section is None:
                continue

            # Frequency block start: ",<freq>,Theta Angle..."
            if _is_freq_start(stripped):
                freq = _parse_freq(stripped)
                if freq is not None:
                    section_freqs[current_section].append(freq)
                    section_freq_idx[current_section] += 1
                    current_freq_idx = section_freq_idx[current_section]
                    if current_section == "Theta Log Magnitude" and not theta_angles:
                        theta_angles = _parse_theta_from_header(stripped)
                    sections_data[current_section].append([])
                    in_block = True
                continue

            # Phi header: ",,Phi / Response..."
            if in_block and stripped.startswith(",,") and "Phi" in stripped:
                continue

            # Data line: ",,<phi>,<val0>,..."
            if in_block and stripped.startswith(",,"):
                phi, values = _parse_data_line(stripped)
                if phi is not None and current_freq_idx >= 0:
                    if current_section == "Theta Log Magnitude" and phi not in phi_angles:
                        phi_angles.append(phi)
                    sd = sections_data[current_section]
                    if current_freq_idx < len(sd):
                        sd[current_freq_idx].append(values)
                continue

    return sections_data, theta_angles, phi_angles, section_freqs


def _is_freq_start(line: str) -> bool:
    if not line.startswith(","):
        return False
    parts = line.split(",")
    if len(parts) < 3:
        return False
    try:
        float(parts[1].strip())
        return "Theta Angle" in line
    except (ValueError, IndexError):
        return False


def _parse_freq(line: str) -> Optional[float]:
    parts = line.split(",")
    if len(parts) >= 2:
        try:
            return float(parts[1].strip())
        except (ValueError, IndexError):
            pass
    return None


def _parse_theta_from_header(line: str) -> List[float]:
    parts = line.split(",")
    vals = []
    for part in parts[3:]:
        part = part.strip()
        try:
            vals.append(float(part))
        except (ValueError, IndexError):
            pass
    return vals


def _parse_data_line(line: str) -> Tuple[Optional[float], List[float]]:
    parts = line.split(",")
    if len(parts) < 3:
        return None, []
    try:
        phi = float(parts[2].strip())
    except (ValueError, IndexError):
        return None, []
    vals = []
    for part in parts[3:]:
        try:
            vals.append(float(part.strip()))
        except (ValueError, IndexError):
            vals.append(0.0)
    return phi, vals


def batch_resample(
    input_path: str,
    output_dir: str,
    steps: List[float],
    *,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> List[str]:
    """批量重采样：对同一源文件生成多个步进的输出。

    Args:
        input_path:   源 CSV 路径
        output_dir:   输出目录
        steps:        目标步进列表（度），如 [5.0, 10.0, 15.0]
        progress_callback: (current, total, message)

    Returns:
        输出文件路径列表
    """
    os.makedirs(output_dir, exist_ok=True)
    stem = Path(input_path).stem

    outputs = []
    total = len(steps)
    for i, step in enumerate(steps):
        step_str = str(int(step)) if step == int(step) else str(step).replace(".", "p")
        out_name = f"{stem}_step{step_str}deg.csv"
        out_path = str(Path(output_dir) / out_name)

        if progress_callback:
            progress_callback(i, total, f"重采样 step={step}° → {out_name}")

        resample_merged_csv(input_path, out_path, step, step)
        outputs.append(out_path)

    if progress_callback:
        progress_callback(total, total, f"完成: {len(outputs)} 个文件")
    return outputs
