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
        self._parsed: dict | None = None
        self._frequencies: list[float] = []
        self._theta_angles: list[float] = []
        self._phi_angles: list[float] = []
        self._indexed = False

    # ------------------------------------------------------------------
    # 懒加载 + 索引构建
    # ------------------------------------------------------------------

    def _ensure_loaded(self):
        """首次访问时加载 JSON 并构建索引。"""
        if self._parsed is not None:
            return

        with open(self._path, encoding="utf-8") as f:
            self._parsed = json.load(f)

        data_root = self._parsed.get("Data", {})

        # 检测数据格式
        if "DataSetType" in data_root:
            # v1.18+: Data → DataSetType → Final Data → Format
            final = data_root["DataSetType"].get("Final Data", {}).get("Format", {})
            if not final:
                raise ValueError(f"JSON v18+ 文件缺少 Final Data: {self._path}")
            tl_section = final.get("Theta Log Magnitude", {}).get("Frequency  (MHz)", {})
            if not tl_section:
                raise ValueError("JSON 文件缺少 Theta Log Magnitude 数据")
        elif "Polarization" in data_root:
            # v1.12: Data → Polarization → Horizontal1/Vertical1/Total
            # 旧版无频率列表 — 从 Frequency Range 推导单频点
            freq_info = self._parsed.get("Test Information", {}).get("Frequency Range", {})
            start = freq_info.get("dStartFreqMHz")
            stop = freq_info.get("dStopFreqMHz")
            if start and stop:
                # 单频点或窄带扫描 — 取中心频率
                self._frequencies = [float(start)]
            else:
                self._frequencies = [0.0]
            # 从 Polarization 数据提取 theta/phi 角度
            pol = data_root["Polarization"]
            first_pol = pol.get("Horizontal1") or pol.get("Vertical1") or {}
            theta_keys = [k for k in first_pol.keys() if _is_numeric_key(k)]
            self._theta_angles = sorted([float(k) for k in theta_keys])
            self._phi_angles = [0.0]  # 单轴测量，无 phi 维度
            self._indexed = True
            return
        else:
            raise ValueError(f"JSON 文件格式不支持: {self._path}")

        # v1.18+ 流程
        tl_section = final.get("Theta Log Magnitude", {}).get("Frequency  (MHz)", {})

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
    def frequencies(self) -> list[float]:
        self._ensure_loaded()
        return list(self._frequencies)

    @property
    def theta_angles(self) -> list[float]:
        self._ensure_loaded()
        return list(self._theta_angles)

    @property
    def phi_angles(self) -> list[float]:
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

    def read_sections(self, freq_index: int) -> dict[str, np.ndarray | None]:
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
        result: dict[str, np.ndarray | None] = {}

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
        """提取测试元数据: 方法、时间、设备、参数、用户字段等。

        兼容 EMQuest v1.12 (Polarization) 和 v1.18+ (DataSetType) 两种数据格式。
        """
        self._ensure_loaded()
        ti = self._parsed.get("Test Information", {})
        md = {}

        # ── 基础 ──
        params = ti.get("Parameters", {})
        op = ti.get("Operator/Comments", {})
        equip = ti.get("paEquipmentList", {})
        freq_range = ti.get("Frequency Range", {})

        # ── 被测件 ──
        for k in ("szIUTManufacturer", "szIUTModel", "szIUTSerialNo", "szIUTType", "szIUTFrame"):
            v = equip.get(k, "").strip()
            if v:
                md[k[3:].lower()] = v  # → manufacturer, model, serialno, type, frame

        # ── 操作员/时间 ──
        for k in ("szOperator", "szOpComments", "szTestTime", "szTestEndTime",
                  "szTestElapsedTime", "szTemperature", "szHumidity"):
            v = op.get(k, "").strip()
            if v:
                key = k[2:].lower() if k.startswith("sz") else k.lower()
                md[key] = v

        # ── 测试方法 ──
        for k in ("szTestMethod", "szAppVersion", "szParmFileName"):
            v = ti.get(k, "").strip()
            if v:
                md["test_method" if k == "szTestMethod" else
                   "app_version" if k == "szAppVersion" else "parm_file"] = v

        # ── 频率范围 ──
        fs = freq_range.get("dStartFreqMHz")
        fe = freq_range.get("dStopFreqMHz")
        if fs is not None and fe is not None:
            try:
                md["freq_start_mhz"] = float(fs)
                md["freq_stop_mhz"] = float(fe)
                md["freq_range"] = f"{fs} - {fe} MHz"
            except (ValueError, TypeError):
                pass
        fc = freq_range.get("Frequency List(MHz)")
        if isinstance(fc, list) and fc:
            md["freq_list"] = fc

        # ── 测试参数 ──
        for k in ("dLowerLimit", "dUpperLimit", "dStepSize",
                  "dLowerLimit2", "dUpperLimit2", "dStepSize2"):
            v = params.get(k)
            if v is not None:
                md[k] = v
        for k in ("iChannelPolarization", "iPatternType"):
            v = params.get(k, "").strip()
            if v:
                md[k] = v

        # ── 设备 ──
        eq = ti.get("Equipment", {})
        if isinstance(eq, dict):
            for k in ("szPositioner1", "szPositioner2", "szEquipSelect"):
                v = eq.get(k, "").strip()
                if v:
                    md[k[2:].lower()] = v

        # ── User Defined 1-12 ──
        ud = ti.get("User Defined", {})
        if isinstance(ud, dict):
            labels_str = ud.get("szUserDefinedLabels", "")
            labels = [l.strip() for l in labels_str.split("|")] if labels_str else []
            for i in range(1, 13):
                key = f"szUserDefString_{i:02d}"
                val = ud.get(key, "").strip()
                if val:
                    label = labels[i-1] if i-1 < len(labels) else f"UF{i}"
                    md[f"user_{i}"] = val
                    md[f"user_{i}_label"] = label

        # ── 数据格式 ──
        data = self._parsed.get("Data", {})
        if "DataSetType" in data:
            md["data_format"] = "v18+"
        elif "Polarization" in data:
            md["data_format"] = "v12"

        # ── 频点/角度计数 ──
        md["frequency_count"] = len(self._frequencies)
        md["theta_count"] = len(self._theta_angles)
        md["phi_count"] = len(self._phi_angles)

        return {k: v for k, v in md.items() if v not in (None, "", 0)}


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

