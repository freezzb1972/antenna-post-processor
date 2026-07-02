"""
探头校正模块 (Wigner d 函数 + 探头系数)
========================================
IEEE 1720 球面近远场变换的探头校正组件。

当校准数据可用时:
  1. 测量已知标准天线 → 反求探头系数 R_s
  2. 填入 ProbeCorrection(R_theta, R_phi)
  3. NF2FF 自动应用校正

未填入时: 使用理想电偶极子近似 (R_1=1, R_s=0 for s>1).
"""

from __future__ import annotations

import numpy as np


def wigner_d_small(n: int, m: int, theta_rad: np.ndarray) -> np.ndarray:
    """Wigner d_{mn}(θ) — 坐标旋转函数，连接探头坐标系与AUT坐标系。

    定义: d_{mn}(θ) = Σ_k (-1)^k · C · (cos θ/2)^{...} · (sin θ/2)^{...}
    递推实现，避免阶乘溢出。

    Args:
        n: 球谐阶数 (≥0).
        m: order (-n ≤ m ≤ n).
        theta_rad: 极角 (弧度).

    Returns:
        d 函数值, 同 theta shape.
    """
    # 简化实现: 对于小 n (≤10), 直接计算
    # 对于较大的 n, 使用递推关系
    abs_m = abs(m)
    costh = np.cos(theta_rad)
    sinth2 = np.sin(theta_rad / 2.0) ** 2

    # d_{m,n} = d_{|m|,n} 的递推 (从 d_{0,0}=1 开始)
    # 使用标准递推公式 (IEEE 1720 Annex C)
    d = np.zeros((n + 1, n + 1) + theta_rad.shape, dtype=float)

    # d_{0,0} = 1
    d[0, 0] = 1.0

    for nn in range(1, n + 1):
        # d_{0,nn} 从 d_{0,nn-1} 递推
        d[0, nn] = costh * d[0, nn - 1]

    # 递推 d_{m,n} for m > 0
    for mm in range(1, n + 1):
        for nn in range(mm, n + 1):
            if nn == mm:
                d[mm, nn] = (1 + costh) / 2.0 * np.sqrt(
                    (2 * nn + 1) / (2 * nn)) * d[mm - 1, nn - 1]
            else:
                # 通用递推
                denom = np.sqrt(nn * nn - mm * mm)
                num = (2 * nn - 1) * costh * d[mm, nn - 1]
                if nn > mm + 1:
                    num -= np.sqrt((nn - 1) ** 2 - mm ** 2) * d[mm, nn - 2]
                d[mm, nn] = num / denom

    if m >= 0:
        return d[abs_m, n]
    else:
        # d_{-m,n} = (-1)^m · d_{m,n}
        return (-1) ** abs_m * d[abs_m, n]


class ProbeCorrection:
    """探头校正系数。

    探头响应由其球波展开的复系数 R_s 描述:
      R_1 = TE 模式响应 (magnetic dipole)
      R_2 = TM 模式响应 (electric dipole)

    理想电偶极子: R_1 = 0, R_2 = 1.
    实际探头: 由校准测量获得。

    Usage:
        # 无校准数据 (默认)
        probe = ProbeCorrection.default()

        # 有校准数据后
        probe = ProbeCorrection(r_te=np.array([0.1, 0.05, ...]),
                                r_tm=np.array([0.95, 0.03, ...]))
    """

    def __init__(self, r_te: np.ndarray | None = None,
                 r_tm: np.ndarray | None = None):
        """
        Args:
            r_te: TE 探头系数 (s=1), shape (s_max,). None = 理想电偶极子.
            r_tm: TM 探头系数 (s=2), shape (s_max,). None = 理想电偶极子.
        """
        self.r_te = np.array(r_te) if r_te is not None else np.array([0.0, 1.0])
        self.r_tm = np.array(r_tm) if r_tm is not None else np.array([0.0, 1.0])
        self.s_max = max(len(self.r_te), len(self.r_tm))

    @classmethod
    def default(cls) -> ProbeCorrection:
        """理想电偶极子探头 (开放式波导近似)."""
        return cls()

    @classmethod
    def from_calibration(cls, cal_path: str) -> ProbeCorrection:
        """从校准文件加载探头系数 (CSV: s, Re{R_te}, Im{R_te}, Re{R_tm}, Im{R_tm})."""
        data = np.loadtxt(cal_path, delimiter=",", skiprows=1)
        r_te = data[:, 1] + 1j * data[:, 2]
        r_tm = data[:, 3] + 1j * data[:, 4]
        return cls(r_te=r_te, r_tm=r_tm)

    def apply(self, n: int) -> tuple[complex, complex]:
        """获取第 n 阶的探头系数 (R_te, R_tm).

        若 n 超出已校准范围, 返回 0 (高阶模式探头响应衰减).
        """
        if n < len(self.r_te):
            r_te = self.r_te[n]
        else:
            r_te = 0.0
        if n < len(self.r_tm):
            r_tm = self.r_tm[n]
        else:
            r_tm = 0.0
        return r_te, r_tm
