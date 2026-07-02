"""
多探头阵列校准模块
==================
补偿多探头系统中各探头的幅度和相位不一致性。
"""

from __future__ import annotations

import numpy as np


class ProbeCalibration:
    """多探头阵列校准补偿。

    多探头环形架 (如 Satimo 类型) 中各探头由于制造公差、
    线缆差异等原因, 存在幅度和相位偏差。
    通过标准参考天线测量得到校准系数, 应用到原始数据上。

    Usage:
        cal = ProbeCalibration.from_boresight(e_measured, expected_gain_dbi=10.0)
        e_calibrated = cal.apply(e_raw)
    """

    def __init__(self, cal_coeffs: np.ndarray):
        """
        Args:
            cal_coeffs: 复数校准系数, shape (n_probes,).
                        每个探头一个复数乘性因子 a·e^{jφ}.
        """
        self._coeffs = np.array(cal_coeffs, dtype=complex)

    @classmethod
    def from_boresight(cls, e_measured: np.ndarray,
                        expected_gain_dbi: float = 0.0) -> ProbeCalibration:
        """从 boresight 方向测量数据估计校准系数。

        假设 boresight 方向各探头应有相同的响应 (全向参考天线),
        计算归一化系数 = expected / measured。

        Args:
            e_measured: 测量复电场 (n_probes,).
            expected_gain_dbi: 参考天线在该方向的期望增益 (dBi).

        Returns:
            ProbeCalibration 实例.
        """
        expected_mag = 10.0 ** (expected_gain_dbi / 20.0)
        ref = np.mean(e_measured)
        coeffs = expected_mag * ref / e_measured
        return cls(coeffs)

    @classmethod
    def from_file(cls, path: str) -> ProbeCalibration:
        """从校准文件加载系数 (CSV: probe_index, amplitude_dB, phase_deg)."""
        data = np.loadtxt(path, delimiter=",", skiprows=1)
        amp_db = data[:, 1]
        phase_deg = data[:, 2]
        amp_lin = 10.0 ** (amp_db / 20.0)
        phase_rad = np.deg2rad(phase_deg)
        coeffs = amp_lin * np.exp(1j * phase_rad)
        return cls(coeffs)

    def apply(self, e_raw: np.ndarray) -> np.ndarray:
        """应用校准系数到原始测量数据。

        Args:
            e_raw: 原始复电场, shape (..., n_probes) 或 (n_probes,).

        Returns:
            校准后的复电场, 同 shape.
        """
        return e_raw * self._coeffs

    def apply_polarization(self, e_theta: np.ndarray,
                            e_phi: np.ndarray) -> tuple:
        """分别对 Theta 和 Phi 极化应用校准系数。

        Args:
            e_theta: Theta 极化 (n_theta, n_probes).
            e_phi: Phi 极化 (n_theta, n_probes).

        Returns:
            (e_theta_cal, e_phi_cal).
        """
        return self.apply(e_theta), self.apply(e_phi)

    def save(self, path: str):
        """保存校准系数到文件."""
        amp_db = 20.0 * np.log10(np.abs(self._coeffs))
        phase_deg = np.rad2deg(np.angle(self._coeffs))
        data = np.column_stack([np.arange(len(self._coeffs)), amp_db, phase_deg])
        np.savetxt(path, data, delimiter=",", header="probe,amp_dB,phase_deg",
                   fmt=["%d", "%.4f", "%.2f"], comments="")
