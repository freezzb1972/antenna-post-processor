"""
NF2FF 工具函数
==============
阶数估算、坐标转换、球面网格生成。
"""

import numpy as np


def estimate_n_max(freq_mhz: float, radius_m: float, margin: int = 10) -> int:
    """根据工作频率和天线外接球半径估算截断阶数 N_max.

    N = ceil(k × a) + margin
    其中 k = 2π/λ 是波数, a 是天线的外接球半径。

    注意: 当 n > kr 时, 球 Hankel 函数指数增长 (evanescent modes),
    导致矩阵严重病态。实际应用中 N_max 不应超过 kr + margin。

    参考: IEEE 1720-2012, Hansen "Spherical Near-Field Antenna Measurements"

    Args:
        freq_mhz: 频率 (MHz).
        radius_m: 天线外接球半径 (m). 通常取天线最大物理尺寸.
        margin: 安全裕量 (默认 10, 建议 ≥5).

    Returns:
        N_max: 截断阶数 (整数).
    """
    c = 299792458.0
    wavelength = c / (freq_mhz * 1e6)
    k = 2.0 * np.pi / wavelength
    n_raw = int(np.ceil(k * radius_m)) + margin
    # 硬上限: 防止 evanescent 模式爆炸
    return min(n_raw, 15)  # 安全默认, 实际使用时可手动覆盖


def spherical_grid(theta_deg: np.ndarray, phi_deg: np.ndarray):
    """生成球面网格坐标, 返回 (theta_mesh, phi_mesh) 弧度.

    Args:
        theta_deg: theta 角度数组 (度), 1D.
        phi_deg: phi 角度数组 (度), 1D.

    Returns:
        theta_rad: 2D theta 网格 (弧度).
        phi_rad: 2D phi 网格 (弧度).
    """
    theta_rad = np.deg2rad(theta_deg)
    phi_rad = np.deg2rad(phi_deg)
    return np.meshgrid(theta_rad, phi_rad, indexing='ij')
