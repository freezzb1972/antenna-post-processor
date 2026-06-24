"""
EMQuest JSON 数据读取器
=======================
实现 DataSource 接口，从 EMQuest 导出的 JSON 文件读取天线测试数据。

JSON 结构 (EMQuest v1.18+):
  Test Information → 测试元数据 (方法/时间/参数/设备)
  Data → DataSetType →
    Raw Data → Format → Theta/Phi Real + Imaginary (复电场)
    Final Data → Format → Theta/Phi LogMag + Phase + Total Power
    Corrections → Correction Array → H/V 校准 + 功率

数据组织 (Final Data):
  {section: {Frequency (MHz): {freq: {Theta Angle (Degrees): {theta: {phi: value}}}}}}
  即 freq → theta → phi → response_value 的三层嵌套 dict。

内存策略:
  首次访问时完整解析 JSON (40-50 MB)，后续按索引读取。
  read_sections() 返回 numpy 数组 shape (n_phi, n_theta)。
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from .datasource import DataSource


class JsonDataSource(DataSource):
    """EMQuest JSON 数据源读取器。"""

    SECTION_MAP = {
        "theta_logmag": "Theta Log Magnitude",
        "theta_phase": "Theta Phase",
        "phi_logmag": "Phi Log Magnitude",
        "phi_phase": "Phi Phase",
    }

    def __init__(self, path: str):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"JSON 文件不存在: {path}")
        self._path = path
        self._parsed: Optional[dict] = None
        self._frequencies: List[float] = []
        self._theta_angles: List[float] = []
        self._phi_angles: List[float] = []
        self._indexed = False

    # ------------------------------------------------------------------
    # 懒加载 + 索引构建
    # ------------------------------------------------------------------

    def _ensure_loaded(self):
        """首次访问时加载 JSON 并构建索引。"""
        if self._parsed is not None:
            return

        with open(self._path, "r", encoding="utf-8") as f:
            self._parsed = json.load(f)

        # 提取 Final Data
        final = (
            self._parsed.get("Data", {})
            .get("DataSetType", {})
            .get("Final Data", {})
            .get("Format", {})
        )
        if not final:
            raise ValueError(f"JSON 文件缺少 Final Data: {self._path}")

        # 从第一个可用 section 提取频率列表
        tl_section = final.get("Theta Log Magnitude", {}).get("Frequency  (MHz)", {})
        if not tl_section:
            raise ValueError("JSON 文件缺少 Theta Log Magnitude 数据")

        self._frequencies = sorted([float(k) for k in tl_section.keys()])

        # 从第一个频率的第一个 theta 键获取 theta 和 phi 角度
        freq0 = _freq_key(self._frequencies[0])
        theta_dict = tl_section[freq0].get("Theta Angle  (Degrees)", {})
        if not theta_dict:
            raise ValueError("JSON 文件缺少 Theta Angle 数据")

        # Theta 角度：字典的键（排除非数字键如 'Theta Angle  (Degrees)'）
        theta_keys = [k for k in theta_dict.keys() if _is_numeric_key(k)]
        self._theta_angles = sorted([float(k) for k in theta_keys])

        # Phi 角度：从第一个 theta 的 phi 字典提取（排除 'Phi Angle  (Degrees)' 头行和 wrap 值 > 360）
        theta0_key = _theta_key(self._theta_angles[0])
        phi_dict = theta_dict[theta0_key]
        phi_raw = [k for k in phi_dict.keys() if _is_numeric_key(k)]
        phi_vals = sorted([float(p) for p in phi_raw])
        # 去 wrap: 保留 [0, 360] 范围，去除 > 360 的 wrap 值
        self._phi_angles = [p for p in phi_vals if 0.0 <= p <= 360.0]
        # 若去重后为空（如 349-360 段混合了 709），保留所有唯一模 360 值
        if not self._phi_angles:
            seen = set()
            for p in phi_vals:
                mod = p % 360.0
                if mod not in seen:
                    seen.add(mod)
                    self._phi_angles.append(mod)
            self._phi_angles.sort()

        self._indexed = True

    # ------------------------------------------------------------------
    # Public API (DataSource 接口)
    # ------------------------------------------------------------------

    @property
    def frequencies(self) -> List[float]:
        self._ensure_loaded()
        return list(self._frequencies)

    @property
    def theta_angles(self) -> List[float]:
        self._ensure_loaded()
        return list(self._theta_angles)

    @property
    def phi_angles(self) -> List[float]:
        self._ensure_loaded()
        return list(self._phi_angles)

    @property
    def num_frequencies(self) -> int:
        self._ensure_loaded()
        return len(self._frequencies)

    @property
    def num_theta(self) -> int:
        self._ensure_loaded()
        return len(self._theta_angles)

    @property
    def num_phi(self) -> int:
        self._ensure_loaded()
        return len(self._phi_angles)

    def read_sections(self, freq_index: int) -> Dict[str, Optional[np.ndarray]]:
        """读取指定频率的 4 个 section 数据。

        Returns:
            {
                "theta_logmag": np.ndarray (n_phi, n_theta),
                "theta_phase":  np.ndarray (n_phi, n_theta),
                "phi_logmag":   np.ndarray (n_phi, n_theta),
                "phi_phase":    np.ndarray (n_phi, n_theta),
            }
        """
        self._ensure_loaded()

        if freq_index < 0 or freq_index >= len(self._frequencies):
            raise IndexError(
                f"频率索引 {freq_index} 超出范围 [0, {len(self._frequencies)})"
            )

        freq_key = _freq_key(self._frequencies[freq_index])
        final = self._parsed["Data"]["DataSetType"]["Final Data"]["Format"]

        n_phi = len(self._phi_angles)
        n_theta = len(self._theta_angles)
        result: Dict[str, Optional[np.ndarray]] = {}

        for out_key, section_name in self.SECTION_MAP.items():
            section = final.get(section_name, {})
            freq_data = section.get("Frequency  (MHz)", {}).get(freq_key, {})
            theta_data = freq_data.get("Theta Angle  (Degrees)", {})

            if not theta_data:
                result[out_key] = None
                continue

            arr = np.full((n_phi, n_theta), np.nan, dtype=np.float64)

            for ti, theta_val in enumerate(self._theta_angles):
                theta_key = _theta_key(theta_val)
                phi_dict = theta_data.get(theta_key, {})
                if not phi_dict:
                    continue

                for pi, phi_val in enumerate(self._phi_angles):
                    phi_key = _phi_key(phi_val)
                    raw_val = phi_dict.get(phi_key)
                    if raw_val is None:
                        # 尝试 float key 格式
                        raw_val = phi_dict.get(phi_val)
                    if raw_val is not None:
                        try:
                            arr[pi, ti] = float(raw_val)
                        except (ValueError, TypeError):
                            pass

            result[out_key] = arr

        return result

    # ------------------------------------------------------------------
    # 元数据提取 (供未来测试报告使用)
    # ------------------------------------------------------------------

    def get_metadata(self) -> dict:
        """提取测试元数据: 方法、时间、设备、参数等。"""
        self._ensure_loaded()
        ti = self._parsed.get("Test Information", {})

        params = ti.get("Parameters", {})
        op = ti.get("Operator/Comments", {})
        equip = ti.get("paEquipmentList", {})

        return {
            "test_method": ti.get("szTestMethod", ""),
            "app_version": ti.get("szAppVersion", ""),
            "parm_file": ti.get("szParmFileName", ""),
            "test_time": op.get("szTestTime", ""),
            "test_end_time": op.get("szTestEndTime", ""),
            "elapsed_time": op.get("szTestElapsedTime", ""),
            "operator": op.get("szOperator", ""),
            "temperature": op.get("szTemperature", ""),
            "humidity": op.get("szHumidity", ""),
            "iut_manufacturer": equip.get("szIUTManufacturer", ""),
            "iut_model": equip.get("szIUTModel", ""),
            "iut_serial": equip.get("szIUTSerialNo", ""),
            "iut_type": equip.get("szIUTType", ""),
            "iut_frame": equip.get("szIUTFrame", ""),
            # 测试参数
            "phi_range": (
                params.get("dLowerLimit", ""),
                params.get("dUpperLimit", ""),
            ),
            "phi_step": params.get("dStepSize", ""),
            "theta_range": (
                params.get("dLowerLimit2", ""),
                params.get("dUpperLimit2", ""),
            ),
            "theta_step": params.get("dStepSize2", ""),
            "polarization": params.get("iChannelPolarization", ""),
            "pattern_type": params.get("iPatternType", ""),
            "frequency_count": len(self._frequencies),
            "theta_count": len(self._theta_angles),
            "phi_count": len(self._phi_angles),
        }


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _is_numeric_key(s: str) -> bool:
    """检查字符串是否为数值键。"""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _freq_key(freq: float) -> str:
    """频率 → JSON 键。处理整数频率的 '1549' vs '1549.0' 歧义。"""
    if freq == int(freq):
        return str(int(freq))
    return str(freq)


def _theta_key(theta: float) -> str:
    """Theta 角度 → JSON 键。"""
    if theta == int(theta):
        return str(int(theta))
    return str(theta)


def _phi_key(phi: float) -> str:
    """Phi 角度 → JSON 键。"""
    # 优先使用整数键
    key_int = str(int(phi))
    # 也尝试带一位小数的格式 (如 '349.0')
    key_float = f"{phi:.1f}" if phi == int(phi) else str(phi)
    return key_int  # 返回首选键，调用方需处理 fallback
