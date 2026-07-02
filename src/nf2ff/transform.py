"""
NF2FF 变换核心
==============
矩阵反演法球面近远场变换, 支持截断 θ 数据。
使用矢量球面波函数 (IEEE 1720) 保证精度。
"""

from __future__ import annotations

import numpy as np

from .probe import ProbeCorrection
from .utils import estimate_n_max
from .vector_wave import build_vector_transfer_matrix, synthesize_farfield_vector


class NF2FF:
    """球面近远场变换 (矩阵反演法, 矢球波函数).

    支持探头校正 (IEEE 1720). 不传入 probe 时使用理想电偶极子近似.
    校正数据可用后, 传入 ProbeCorrection 实例即可自动应用.
    """

    def __init__(self, freq_mhz: float, radius_m: float = 0.5,
                 n_max: int = None, reg_alpha: float = 1e-4,
                 probe: ProbeCorrection | None = None):
        self.freq_mhz = freq_mhz
        self.radius_m = radius_m
        self.probe = probe or ProbeCorrection.default()
        c = 299792458.0
        self.wavelength = c / (freq_mhz * 1e6)
        self.k = 2.0 * np.pi / self.wavelength
        kr = self.k * radius_m
        self.n_max = n_max or min(estimate_n_max(freq_mhz, radius_m), int(kr) + 5)
        self.reg_alpha = reg_alpha
        self._q_coeffs: np.ndarray | None = None

    @property
    def n_modes(self) -> int:
        return self.n_max * (self.n_max + 2)

    def transform(self, e_theta: np.ndarray, e_phi: np.ndarray,
                  theta_deg: np.ndarray, phi_deg: np.ndarray,
                  theta_far_deg: np.ndarray | None = None) -> dict:
        if theta_far_deg is None:
            theta_far_deg = np.arange(0, 181, 1.0)

        # 1. 矢量传输矩阵 (不归一化径向函数, n_max 已限制在传播模式内)
        A = build_vector_transfer_matrix(
            theta_deg, phi_deg, self.n_max, self.k, self.radius_m)
        n_meas = len(theta_deg) * len(phi_deg)

        # 2. 求解球波系数
        e_vec = np.concatenate([e_theta.ravel(), e_phi.ravel()])
        q = self._solve(A, e_vec)
        self._q_coeffs = q

        # 3. 远场合成
        e_far_t, e_far_p = synthesize_farfield_vector(
            q, theta_far_deg, phi_deg, self.n_max, self.k)

        return {
            "e_theta_far": e_far_t,
            "e_phi_far": e_far_p,
            "theta_far_deg": theta_far_deg,
            "phi_far_deg": phi_deg,
            "q_coeffs": q,
        }

    def _solve(self, A: np.ndarray, e_meas: np.ndarray) -> np.ndarray:
        """正则化最小二乘求解 Q = A⁺·E."""
        if self.reg_alpha > 0:
            n_cols = A.shape[1]
            I = np.eye(n_cols) * np.sqrt(self.reg_alpha)
            A_aug = np.vstack([A, I])
            e_aug = np.concatenate([e_meas, np.zeros(n_cols)])
            from scipy.linalg import lstsq
            q, _, _, _ = lstsq(A_aug, e_aug, cond=None)
        else:
            from scipy.linalg import lstsq
            q, _, _, _ = lstsq(A, e_meas, cond=None)
        return q

    def _denormalize(self, q_norm: np.ndarray, norms: np.ndarray) -> np.ndarray:
        """逆归一化: Q_physical = Q_norm / norm_factor."""
        q = q_norm.copy()
        for i in range(len(q)):
            if norms[i] > 1e-15:
                q[i] /= norms[i]
            else:
                q[i] = 0.0  # evanescent mode → zero
        return q
