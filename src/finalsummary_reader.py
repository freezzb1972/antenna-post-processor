"""
FinalSummary.xlsx 直接读取器
=============================
实现 DataSource 接口，从 FinalSummary Excel 逐频点读取数据，
不产生任何中间文件。

Fixed structure:
  R3:   "Theta/Phi | Theta0 | Theta1 | ..." (Theta 角度 0–110°, 111 列)
  R4–R363:  Theta Polarization data (Phi 0–359, 360 行)
  R366: "Phi Polarization"
  R367: "Theta/Phi | ..."
  R368–R727: Phi Polarization data (Phi 0–359, 360 行)
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import openpyxl

from .datasource import DataSource

_THETA_POL_START = 4
_PHI_POL_START = 368
_N_PHI = 360
_THETA_HEADER_ROW = 3


class FinalSummarySource(DataSource):
    """从 FinalSummary.xlsx 逐频点读取天线测试数据。"""

    def __init__(self, path: str):
        self._path = path
        self._wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

        # ---- 频点列表 ----
        self._freqs: List[float] = []
        for sn in self._wb.sheetnames:
            try:
                self._freqs.append(float(sn))
            except ValueError:
                pass
        if not self._freqs:
            self._wb.close()
            raise ValueError(f"在 {self._path} 中未找到数字命名的频点 Sheet")

        self._freqs.sort()

        # ---- 从第一个 sheet 读取几何信息 ----
        ws0 = self._wb[str(int(self._freqs[0])) if self._freqs[0] == int(self._freqs[0])
                        else self._wb.sheetnames[0]]
        self._theta: List[float] = []
        for row in ws0.iter_rows(min_row=_THETA_HEADER_ROW, max_row=_THETA_HEADER_ROW,
                                  values_only=True):
            for v in row[1:]:
                if v is not None:
                    try:
                        self._theta.append(float(v))
                    except (ValueError, TypeError):
                        pass

        self._phi = [float(i) for i in range(_N_PHI)]

        # ---- 缓存：sheet_name -> (theta_lm, phi_lm) ----
        self._cache: Dict[float, tuple] = {}

    @property
    def frequencies(self) -> List[float]:
        return list(self._freqs)

    @property
    def theta_angles(self) -> List[float]:
        return list(self._theta)

    @property
    def phi_angles(self) -> List[float]:
        return self._phi

    def read_sections(self, freq_index: int) -> Dict[str, Optional[np.ndarray]]:
        freq = self._freqs[freq_index]

        if freq in self._cache:
            tl, pl = self._cache[freq]
        else:
            sn = str(int(freq)) if freq == int(freq) else str(freq)
            if sn not in self._wb.sheetnames:
                raise KeyError(f"Frequency {freq} MHz not found in {self._path}")
            ws = self._wb[sn]

            tl = _read_matrix(ws, _THETA_POL_START, _N_PHI, len(self._theta))
            pl = _read_matrix(ws, _PHI_POL_START, _N_PHI, len(self._theta))
            self._cache[freq] = (tl, pl)

        return {
            "theta_logmag": tl,
            "theta_phase": None,   # FinalSummary 无 Phase
            "phi_logmag": pl,
            "phi_phase": None,
        }

    def close(self):
        if self._wb:
            self._wb.close()
            self._wb = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _read_matrix(ws, start_row: int, n_rows: int, n_cols: int) -> np.ndarray:
    """从 sheet 中读 n_rows × n_cols 矩阵。"""
    data = np.zeros((n_rows, n_cols), dtype=np.float64)
    rows = ws.iter_rows(min_row=start_row, max_row=start_row + n_rows - 1,
                        min_col=2, max_col=1 + n_cols, values_only=True)
    for pi, row in enumerate(rows):
        if pi >= n_rows:
            break
        for ti, v in enumerate(row):
            if ti >= n_cols:
                break
            try:
                data[pi, ti] = float(v) if v is not None else -999.0
            except (ValueError, TypeError):
                data[pi, ti] = -999.0
    return data
