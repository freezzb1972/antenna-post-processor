"""
NF2FF — 球面近远场变换独立模块
================================
支持截断球面测量数据 (θ ∈ [0°, 110°]) 的矩阵反演法近远场变换,
输出完整 θ ∈ [0°, 180°] 远场方向图。

核心算法:
  1. 传输矩阵构建 (sw_matrix.py) — 基于球面矢量波函数
  2. 矩阵反演求解 (solve.py) — scipy.lstsq + Tikhonov 正则化
  3. 远场合成 (farfield.py) — Q_coeff → E_far(180°)
  4. 探头校准 (probe_cal.py) — 多探头阵列幅度/相位补偿

使用:
    from src.nf2ff import NF2FF
    nf2ff = NF2FF(freq_mhz=2450.0, radius_m=0.5, n_max=None)
    e_far = nf2ff.transform(e_theta_near, e_phi_near, theta_deg, phi_deg)

注意:
  - 输入 theta 必须是 colatitude (0-180°), 截断输入也按此处理
  - 返回远场覆盖完整的 θ ∈ [0°, 180°]
"""

from .probe import ProbeCorrection
from .probe_cal import ProbeCalibration
from .transform import NF2FF
