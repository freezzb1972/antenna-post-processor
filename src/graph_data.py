"""
图形数据提取与降采样模块
========================
从处理管线结果中提取方向图数据，降采样到适合可视化的精度。

全量数据: 361 phi × 111 theta = 40,071 点/频点
降采样:   默认 5° 步进 → 73 phi × 23 theta ≈ 1,679 点（交互旋转流畅）
"""

from __future__ import annotations

import numpy as np


def extend_theta_to_180(data: np.ndarray, theta_arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """将截断 theta (如 0-110°) 延伸到 180°，用指数衰减填充后半球。"""
    if theta_arr[-1] >= 179:
        return data, theta_arr
    # 生成扩展 theta: 在最后一个测量角之后，以 2° 步进到 180°
    last_theta = theta_arr[-1]
    extra_steps = np.arange(last_theta + 2, 181, 2)
    if len(extra_steps) == 0:
        return data, theta_arr
    # 后半球填充值: 从最后一个测量值衰减 20dB 到 -40dB
    last_val = data[:, -1]  # (n_phi,) — 110° 处的值
    decay = np.linspace(0, 20, len(extra_steps))  # 线性衰减 0→20dB
    pad_values = last_val[:, np.newaxis] - decay[np.newaxis, :]  # (n_phi, n_extra)
    pad_values = np.maximum(pad_values, -40)  # 不低于 -40dB
    new_data = np.hstack([data, pad_values])
    new_theta = np.concatenate([theta_arr, extra_steps])
    return new_data, new_theta


def _extend_hold(data: np.ndarray, theta_arr: np.ndarray) -> np.ndarray:
    """相位延伸到 180°: 后半球用最后测量值常数保持 (不做 dB 衰减)。返回 (n_phi, n_theta_ext)。"""
    if theta_arr[-1] >= 179:
        return data
    extra_steps = np.arange(theta_arr[-1] + 2, 181, 2)
    if len(extra_steps) == 0:
        return data
    pad = np.repeat(data[:, -1:], len(extra_steps), axis=1)
    return np.hstack([data, pad])


def downsample_pattern(
    data_2d: np.ndarray,
    theta_angles: np.ndarray,
    phi_angles: np.ndarray,
    step_deg: float = 5.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """将 (n_phi, n_theta) 方向图降采样到指定步进。

    Args:
        data_2d: 原始数据 (n_phi, n_theta).
        theta_angles: theta 角度 (度), 1D.
        phi_angles: phi 角度 (度), 1D.
        step_deg: 目标步进 (度).

    Returns:
        (data_ds, theta_ds, phi_ds): 降采样后的数据和角度.
    """
    theta_idx = np.arange(0, len(theta_angles), max(1, int(step_deg)))
    phi_idx = np.arange(0, len(phi_angles), max(1, int(step_deg)))
    return data_2d[phi_idx][:, theta_idx], theta_angles[theta_idx], phi_angles[phi_idx]


def extract_graph_data(
    results: dict[str, list[dict]],
    step_deg: float = 5.0,
) -> dict[float, dict[str, np.ndarray]]:
    """从处理结果中提取每个频点的图形数据。

    Args:
        results: run_pipeline 返回的 {sheet_name: [row_dict, ...]}.
        step_deg: 降采样步进.

    Returns:
        {freq_mhz: {"theta": ndarray, "phi": ndarray,
                     "gain_db": ndarray, "theta_db": ndarray,
                     "phi_db": ndarray, "ar_linear": ndarray}}
    """

    output: dict[float, dict[str, np.ndarray]] = {}

    for rows in results.values():
        if not rows:
            continue
        for row in rows:
            freq = row.get("frequency")
            if freq is None:
                continue
            raw = row.get("_raw_data")
            theta_full = row.get("_theta_angles")
            phi_full = row.get("_phi_angles")

            if raw is None or theta_full is None or phi_full is None:
                continue

            theta_arr = np.array(theta_full)
            phi_arr = np.array(phi_full)
            tl = np.array(raw.get("theta_logmag", np.zeros((len(phi_arr), len(theta_arr)))))
            pl = np.array(raw.get("phi_logmag", np.zeros((len(phi_arr), len(theta_arr)))))

            # Compute total gain in dB
            gain_lin = 10.0 ** (tl / 10.0) + 10.0 ** (pl / 10.0)
            gain_db = 10.0 * np.log10(np.maximum(gain_lin, 1e-15))

            # Extend theta to 180° for visual completeness (visual only)
            tl_ext, theta_ext = extend_theta_to_180(tl, theta_arr)
            pl_ext, _ = extend_theta_to_180(pl, theta_arr)
            gain_db_ext, _ = extend_theta_to_180(gain_db, theta_arr)

            # AR / 相位 (需相位数据)
            tp = raw.get("theta_phase")
            pp = raw.get("phi_phase")
            ar_ext = None
            tphase_ext = None
            pphase_ext = None
            if tp is not None and pp is not None:
                tp_arr = np.array(tp)
                pp_arr = np.array(pp)
                mag_t = np.power(10.0, tl / 20.0)
                mag_p = np.power(10.0, pl / 20.0)
                e_t = mag_t * np.exp(1j * np.deg2rad(tp_arr))
                e_p = mag_p * np.exp(1j * np.deg2rad(pp_arr))
                # 约定统一 calculator: RHCP = (E_θ + jE_φ)/√2 (AR 对 R/L 交换对称, 值不变)
                e_rhcp = (e_t + 1j * e_p) / np.sqrt(2)
                e_lhcp = (e_t - 1j * e_p) / np.sqrt(2)
                denom = np.abs(np.abs(e_rhcp) - np.abs(e_lhcp))
                denom = np.maximum(denom, 1e-15)
                ar_lin_raw = (np.abs(e_rhcp) + np.abs(e_lhcp)) / denom
                ar_ext, _ = extend_theta_to_180(ar_lin_raw, theta_arr)
                # 相位图: 后半球常数保持延伸 (不做 dB 衰减)
                tphase_ext = _extend_hold(tp_arr, theta_arr)
                pphase_ext = _extend_hold(pp_arr, theta_arr)

            # Downsample (on extended data to 180°)
            gain_ds, theta_ds, phi_ds = downsample_pattern(gain_db_ext, theta_ext, phi_arr, step_deg)
            tl_ds, _, _ = downsample_pattern(tl_ext, theta_ext, phi_arr, step_deg)
            pl_ds, _, _ = downsample_pattern(pl_ext, theta_ext, phi_arr, step_deg)
            ar_ds = None
            if ar_ext is not None:
                ar_ds, _, _ = downsample_pattern(ar_ext, theta_ext, phi_arr, step_deg)

            output[freq] = {
                "theta": theta_ds,
                "phi": phi_ds,
                "gain_db": gain_ds,
                "theta_db": tl_ds,
                "phi_db": pl_ds,
                "total_power": gain_ds,          # 总功率图 = 总增益形状 (派生)
                "ar_linear": ar_ds,
            }
            # 相位图 (仅有相位数据时)
            if tphase_ext is not None:
                output[freq]["theta_phase"], _, _ = downsample_pattern(tphase_ext, theta_ext, phi_arr, step_deg)
            if pphase_ext is not None:
                output[freq]["phi_phase"], _, _ = downsample_pattern(pphase_ext, theta_ext, phi_arr, step_deg)
            # RHCP/LHCP/CP-XPI: 从 row 读取 (pipeline 已算), 延伸到 180° 再降采样 (与 gain 对齐)
            rhcp_g = row.get("_rhcp_gain")
            lhcp_g = row.get("_lhcp_gain")
            cp_xpi = row.get("_cp_xpi")
            if rhcp_g is not None:
                _ext, _ = extend_theta_to_180(np.array(rhcp_g), theta_arr)
                output[freq]["rhcp_db"], _, _ = downsample_pattern(_ext, theta_ext, phi_arr, step_deg)
            if lhcp_g is not None:
                _ext, _ = extend_theta_to_180(np.array(lhcp_g), theta_arr)
                output[freq]["lhcp_db"], _, _ = downsample_pattern(_ext, theta_ext, phi_arr, step_deg)
            if cp_xpi is not None:
                _ext, _ = extend_theta_to_180(np.array(cp_xpi), theta_arr)
                output[freq]["cpxpi_db"], _, _ = downsample_pattern(_ext, theta_ext, phi_arr, step_deg)

    return output
