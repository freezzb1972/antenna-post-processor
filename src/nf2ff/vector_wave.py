"""
矢球波函数模块
==============
IEEE 1720 标准球面矢量波函数 M_nm, N_nm 及其远场渐近形式。

球面矢量波函数是球坐标系中麦克斯韦方程组的本征解，
是球面近远场变换的正确基函数。
"""

from __future__ import annotations

import numpy as np
from scipy.special import lpmv, sph_harm_y, spherical_jn, spherical_yn


def _associated_legendre_derivative(n: int, m: int, x: np.ndarray) -> np.ndarray:
    """计算连带勒让德函数 P_n^m(x) 对 x 的导数 dP/dx.

    递推公式: dP_n^m/dx = (n·x·P_n^m - (n+m)·P_{n-1}^m) / (x²-1)
    """
    if m > n:
        return np.zeros_like(x)

    m_abs = abs(m)
    pn = lpmv(m_abs, n, x)  # P_n^{|m|}(x)
    if n == 0:
        return np.zeros_like(x)
    pn_1 = lpmv(m_abs, n - 1, x)  # P_{n-1}^{|m|}(x)

    denom = x ** 2 - 1.0
    denom[np.abs(denom) < 1e-15] = 1e-15  # 避免除零 (θ=0,π)
    dp = (n * x * pn - (n + m) * pn_1) / denom
    return dp


def vector_spherical_harmonics_theta_phi(
    n: int, m: int, theta: np.ndarray, phi: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """计算矢量球谐函数的 θ 和 φ 分量。

    定义 (IEEE 1720, 时谐因子 e^{-jωt}):
      X_nm(θ,φ) = (1/√{n(n+1)}) · [∂Y/∂θ · θ̂ + (im/sinθ)·Y · φ̂]

    其中 Y = Y_n^m(θ,φ) 是标量球谐函数 (sph_harm_y).

    Args:
        n: degree (≥1).
        m: order (-n ≤ m ≤ n).
        theta: colatitude (弧度), shape (n_theta,) or meshgrid.
        phi: azimuth (弧度).

    Returns:
        (X_theta, X_phi): θ 和 φ 分量, 同 shape.
    """
    if n == 0:
        return np.zeros_like(theta, dtype=complex), np.zeros_like(phi, dtype=complex)

    norm = 1.0 / np.sqrt(n * (n + 1))

    # 标量球谐 Y_n^m
    Y = sph_harm_y(n, m, phi, theta)

    # dY/dθ — 球谐对角度的导数
    # Y_n^m(θ,φ) ∝ P_n^m(cosθ) · e^{imφ}
    # dY/dθ = -sinθ · (dP_n^m(cosθ)/d(cosθ)) · e^{imφ} · N_nm (where N = normalization)
    # 使用 dP/dx 通过递推关系计算
    cost = np.cos(theta)
    abs_m = abs(m)
    P = lpmv(abs_m, n, cost)  # 连带勒让德 P_n^{|m|}
    dP = _associated_legendre_derivative(n, abs_m, cost)

    # 归一化因子 (同 sph_harm_y 的归一化, 用 |m|)
    from scipy.special import factorial
    abs_m = abs(m)
    nf = np.sqrt((2 * n + 1) / (4 * np.pi) * factorial(n - abs_m) / factorial(n + abs_m))
    dY_dtheta = -nf * np.sin(theta) * dP * np.exp(1j * m * phi)

    # X_theta = norm · dY/dθ
    X_theta = norm * dY_dtheta

    # X_phi = norm · (im/sinθ) · Y  (m≠0); for m=0, X_phi=0
    sin_theta = np.sin(theta)
    eps = 1e-15
    if m == 0:
        X_phi = np.zeros_like(Y, dtype=complex)
    else:
        safe_sin = np.where(np.abs(sin_theta) < eps, np.sign(sin_theta + eps) * eps, sin_theta)
        X_phi = norm * (1j * m / safe_sin) * Y

    return X_theta, X_phi


def build_vector_transfer_matrix(
    theta_deg: np.ndarray,
    phi_deg: np.ndarray,
    n_max: int,
    k: float,
    radius_m: float,
    return_norms: bool = False,
) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """构建矢量传输矩阵: E_measured = A · Q.

    Args:
        theta_deg: theta 角度 (度), 1D.
        phi_deg: phi 角度 (度), 1D.
        n_max: 截断阶数.
        k: 波数 (rad/m).
        radius_m: 测量球面半径 (m).
        return_norms: 如果 True, 返回 (A, norms) 其中 norms 是逆归一化因子.

    Returns:
        A: 复数矩阵 (2×N_meas, 2×N_modes), 或 (A, norms)."""
    theta = np.deg2rad(theta_deg)
    phi = np.deg2rad(phi_deg)
    tm, pm = np.meshgrid(theta, phi, indexing='ij')
    n_theta = len(theta_deg)
    n_phi = len(phi_deg)
    n_meas = n_theta * n_phi
    n_modes = n_max * (n_max + 2)
    A = np.zeros((2 * n_meas, 2 * n_modes), dtype=complex)
    norms = np.ones(2 * n_modes, dtype=float)

    kr = k * radius_m
    # 预计算径向函数 (n_max 已限制 ≤ kr+5, 不会爆炸)
    h2_n = np.zeros(n_max + 1, dtype=complex)
    for n in range(0, n_max + 1):
        h2_n[n] = spherical_jn(n, kr) - 1j * spherical_yn(n, kr)

    mode_idx = 0
    for n in range(1, n_max + 1):
        h2 = h2_n[n]
        for m in range(-n, n + 1):
            Xt, Xp = vector_spherical_harmonics_theta_phi(n, m, tm, pm)
            te_theta = h2 * Xt.ravel()
            te_phi   = h2 * Xp.ravel()

            A[:n_meas, 2*mode_idx]   = te_theta
            A[n_meas:, 2*mode_idx]   = te_phi
            norms[2*mode_idx] = abs(h2)

            A[:n_meas, 2*mode_idx+1] = te_theta * 1j
            A[n_meas:, 2*mode_idx+1] = te_phi * 1j
            norms[2*mode_idx+1] = abs(h2)

            mode_idx += 1

    if return_norms:
        return A, norms
    return A


def synthesize_farfield_vector(
    q_coeffs: np.ndarray,
    theta_far_deg: np.ndarray,
    phi_far_deg: np.ndarray,
    n_max: int,
    k: float,
) -> tuple[np.ndarray, np.ndarray]:
    """从球波系数合成矢量远场 (IEEE 1720 渐近形式).

    远场渐近 (r→∞):
      E_θ = (e^{-jkr}/kr) · Σ j^{n+1} · [Q_TE·X_θ + Q_TM·X_φ]
      E_φ = (e^{-jkr}/kr) · Σ j^{n+1} · [Q_TE·X_φ - Q_TM·X_θ]

    返回归一化远场 (去掉 e^{-jkr}/r 因子, 保留 1/k 尺度).

    Args:
        q_coeffs: 球波系数 (2*n_modes,) — 物理系数 (非归一化).
        theta_far_deg, phi_far_deg: 远场角度.
        n_max: 截断阶数.
        k: 波数.

    Returns:
        (e_theta_far, e_phi_far): 远场 (已缩放, 不含 R 因子).
    """
    theta = np.deg2rad(theta_far_deg)
    phi = np.deg2rad(phi_far_deg)
    tm, pm = np.meshgrid(theta, phi, indexing='ij')
    n_theta_f = len(theta_far_deg)
    n_phi_f = len(phi_far_deg)
    scale = 1.0  # 远场尺度 (径向归一化已取消, 直接用原始系数)

    e_theta = np.zeros((n_theta_f, n_phi_f), dtype=complex)
    e_phi = np.zeros((n_theta_f, n_phi_f), dtype=complex)

    mode_idx = 0
    for n in range(1, n_max + 1):
        phase = 1j ** (n + 1) * scale
        for m in range(-n, n + 1):
            Xt, Xp = vector_spherical_harmonics_theta_phi(n, m, tm, pm)
            q_te = q_coeffs[2 * mode_idx]
            q_tm = q_coeffs[2 * mode_idx + 1]
            e_theta += phase * (q_te * Xt + 1j * q_tm * Xp)
            e_phi   += phase * (q_te * Xp - 1j * q_tm * Xt)
            mode_idx += 1

    return e_theta, e_phi
