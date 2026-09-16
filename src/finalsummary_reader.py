"""
FinalSummary.xlsx 直接读取器 (v3)
=================================
实现 DataSource 接口，从 FinalSummary Excel 逐频点读取数据。

核心不变点：
  - 列 = Theta 坐标（一行连续数值）
  - 行 = Phi 坐标（列 A 数值递增）
  - Theta 表头行之前可能有若干描述行（名称/类型等）

自动探测结构，不硬编码任何行号/列数/phi 计数。
"""

from __future__ import annotations

import os
import re
from collections import OrderedDict

import numpy as np
import openpyxl

from .datasource import DataSource


class _LRUDict(OrderedDict):
    """定长 LRU 缓存: 超过 maxsize 时自动淘汰最久未使用的条目。
    每次访问自动将条目标记为最近使用 (move_to_end)。
    """

    def __init__(self, maxsize: int = 128):
        super().__init__()
        self._maxsize = maxsize

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if len(self) > self._maxsize:
            self.popitem(last=False)

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value


# 段标签匹配 —— 一律用词边界, 避免 lhcpPhase / rhcpLogMag 之类的段名误命中
_RE_PHASE = re.compile(r'\bphase\b')
_RE_PHI_POL = re.compile(r'\bpolar\w*\b.*\bphi\b|\bphi\b.*\bpolar\w*\b')


def _is_numeric(v) -> bool:
    """检查值是否可解释为数值（兼容 openpyxl read_only 返回字符串）。"""
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v)
            return True
        except ValueError:
            return False
    return False


def _to_float(v):
    """将值转为 float（兼容 openpyxl read_only 返回字符串）。"""
    if v is None:
        return None
    if _is_numeric(v):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


class FinalSummarySource(DataSource):
    """从 FinalSummary.xlsx 逐频点读取天线测试数据。v3 完全自适应。"""

    def __init__(self, path: str, cache_size: int = 512):
        """Args:
            path:       FinalSummary .xlsx 路径
            cache_size: LRU 缓存的最大频点数。默认 512 覆盖宽频测试场景。
                        顺序读完全部频点即弃的调用方 (如 FinalSummary→CSV 转换器)
                        应传 1 —— 它自己持有全部矩阵, 再缓存一份纯属内存翻倍。
        """
        self._path = path
        # read_only=True: 流式惰性解析, 只解析实际访问到的 sheet。
        # read_only=False 会把**全部** sheet 一次性读进内存 —— 实测 118MB/105 sheet
        # 的文件耗时 179s、内存 +4.9GB; 583MB/139 sheet 的文件推算约 15min / 24GB,
        # 足以打爆内存并冻结界面。本类全部读取均走 iter_rows() 流式接口, 兼容该模式。
        self._wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

        # ---- 频点列表（数字命名的 sheet，排除 Cplx/AxR/Original 等汇总 sheet） ----
        self._freqs: list[float] = []
        for sn in self._wb.sheetnames:
            try:
                self._freqs.append(float(sn))
            except ValueError:
                pass
        if not self._freqs:
            self._wb.close()
            raise ValueError(f"在 {self._path} 中未找到数字命名的频点 Sheet")
        self._freqs.sort()

        # ---- 结构扫描: 一次遍历定位表头与各 section 的数据行 ----
        # 不假设行连续、不限制描述行数、不依赖「标签行号 + 固定偏移」——
        # 详见 _scan_layout()。旧实现会在描述行 >30 / 表头后有空行 / 块内有空行 /
        # 标签文本有差异 / 表头有列缺口 时**静默**读空或读错。
        sn0 = _freq_sheet_name(self._freqs[0])
        ws0 = self._wb[sn0]
        layout = self._scan_layout(ws0)

        self._section_rows: dict[str, list[int]] = layout['sections']
        self._theta_header_row = layout['header_row'] or 0
        self._n_theta = layout['n_theta']
        self._detection_notes: list[str] = layout['notes']

        theta_rows = self._section_rows['theta']
        if not theta_rows:
            self._wb.close()
            raise ValueError(
                f"{self._path} 的 sheet '{sn0}' 中未定位到 Theta 幅度数据块 "
                f"(表头行={layout['header_row']}, 列数={self._n_theta})"
            )
        self._n_phi = len(theta_rows)

        # ---- 兼容属性: section 起始行 (0 = 该段不存在) ----
        # 注意: 段内可能含空行, 起始行不再是「连续 n_phi 行」的起点;
        #       真正驱动读取的是 _section_rows 的行号列表。
        self._theta_start_row = theta_rows[0]
        self._theta_phase_start = (self._section_rows['theta_phase'] or [0])[0]
        self._phi_pol_start = (self._section_rows['phi'] or [0])[0]
        self._phi_phase_start = (self._section_rows['phi_phase'] or [0])[0]
        self._has_phase = bool(self._section_rows['theta_phase'])
        self._has_phi_pol = bool(self._section_rows['phi'])

        # ---- θ/φ 角度: 只取第一段的, 全部段共用 ----
        #
        # 假设: 同一文件内各段的角度轴一致 —— 它们是同一次测试的不同极化/幅度/相位
        # (转台角度相同), 由**测量过程**保证, 不由文件格式保证。此处**不做跨段比对**。
        # 若某段角度确实不同, 该段的矩阵数据会挂上错误的角度标签且不报错。
        # 但真出现这种文件, 说明文件本身已损坏 (相位对不上幅度的角度), 任何分析
        # 都无意义 —— 属于应当排查数据源的情况, 不是需要兼容的格式变体。
        self._theta: list[float] = layout['theta_angles']
        self._phi: list[float] = []
        for r in theta_rows:
            v = layout['col_a'].get(r)
            self._phi.append(v if v is not None else float(len(self._phi)))

        # ---- 各段行数不一致 = 文件结构异常, 必须显式提示 ----
        _counts = {k: len(v) for k, v in self._section_rows.items() if v}
        if len(set(_counts.values())) > 1:
            self._detection_notes.append(
                "各段数据行数不一致 (" +
                ", ".join(f"{k}={n}" for k, n in _counts.items()) + ")"
            )

        # ---- 缓存 (LRU) ----
        self._cache: _LRUDict = _LRUDict(maxsize=max(1, int(cache_size)))

    @staticmethod
    def _scan_layout(ws) -> dict:
        """一次遍历定位表头与各 section 的数据行 (不依赖相邻行/固定偏移)。

        行分类规则 (只依赖单个行的内容, 与前后行无关):
          数据行 = 列 A 为数值或空, 且 B 列起有数值
          表头行 = 列 A 为文本、B 列起有数值, 且是遇到的**第一个**这种行
                   (判据: 列 A 含 'theta', 或数值列数 >= 3)
          标签行 = 其余所有「列 A 为文本」的行 —— 含各段自己的 'Theta/Phi'
                   表头行 (分类不中 → 不改变当前段) 与 'Power'/'Total' 等
          空行   = 列 A 为空且 B 列起无数值 → 一律忽略

        段归属由「最近一次见到的标签」决定。因此:
          - 描述行数不受限 (不设扫描窗口)
          - 表头与数据之间的空行、数据块**内部**的空行都不影响行号列表
          - 标签文本按关键字匹配 (大小写/前后缀/多余空格均容忍)
          - n_theta 取表头行最后一个数值列的位置, 不被中间缺口截断

        读取端按行号列表逐行取值 (`_read_matrices_by_rows`), 不假设行连续。

        Returns:
            {'header_row': int|None, 'n_theta': int, 'theta_angles': list[float],
             'sections': {段名: [行号]}, 'col_a': {行号: phi 角度|None},
             'notes': [str]}
        """
        max_r = ws.max_row or 2000
        notes: list[str] = []
        sections: dict[str, list[int]] = {
            'theta': [], 'theta_phase': [], 'phi': [], 'phi_phase': [],
        }
        col_a_map: dict[int, float | None] = {}

        header_row: int | None = None
        n_theta = 0
        angle_slots: list[float | None] = []

        current = 'theta'          # 段归属; 表头之前的数据不存在
        phi_pol_seen = False
        data_started = False
        ignored: list[tuple[int, str]] = []

        for row_idx, row in enumerate(
            ws.iter_rows(min_row=1, max_row=max_r, values_only=True), start=1
        ):
            col_a = row[0] if len(row) > 0 else None
            a_numeric = _is_numeric(col_a)
            nums = [(i, v) for i, v in enumerate(row[1:])
                    if v is not None and _is_numeric(v)]

            # ── 列 A 是文本 → 表头行 (仅第一个) 或 标签行 ──
            if isinstance(col_a, str) and col_a.strip() and not a_numeric:
                norm = col_a.strip().lower()

                # 表头只认第一个: 判据是列 A 含 'theta' (或右侧数值足够多)。
                # 各段自己的 "Theta/Phi" 表头行、以及形如 'Phase' 的段标签,
                # 都会落到下面的标签分支, 不会被误当成表头。
                if header_row is None and nums:
                    strong = 'theta' in norm
                    if strong or len(nums) >= 3:
                        header_row = row_idx
                        n_theta = nums[-1][0] + 1
                        angle_slots = [None] * n_theta
                        for i, v in nums:
                            if 0 <= i < n_theta:
                                angle_slots[i] = float(v)
                        if not strong:
                            notes.append(
                                f"表头行 (第 {row_idx} 行) 列 A 为 '{col_a.strip()}', "
                                f"不含 'theta' 关键字, 已按表头处理"
                            )
                        continue

                # 标签行。**当前段已收到数据 → 该标签宣告本段结束**,
                # 这一点至关重要: 真实文件在 Phi Phase 之后还有 'Total' 段
                # (行 1462 'Total' → 'Power' → 'Theta/Phi' → 数据)。若不让标签
                # 关闭当前段, Total 的数据会被并进 phi_phase, 该段行数直接翻倍。
                if current and sections[current]:
                    current = None

                # 用**词边界**匹配, 不用子串 —— 真实文件里还有 lhcpPhase /
                # rhcpPhase 等段 (圆极化), 子串匹配会把它们误当成相位段,
                # 其 360 行数据会被并进 phi_phase。
                if _RE_PHI_POL.search(norm):
                    phi_pol_seen = True
                    current = 'phi'
                elif _RE_PHASE.search(norm):
                    if data_started:
                        # Phi Polarization 之前的 Phase = theta 相位; 之后 = phi 相位
                        current = 'phi_phase' if phi_pol_seen else 'theta_phase'
                    else:
                        # 出现在任何数据块之前 → 不是段标签 (如描述行里的字样)
                        ignored.append((row_idx, col_a.strip()))
                # 其它标签 (如 'Power'/'Total') → current 保持 None, 其后数据不被收集
                continue

            # ── 数据行 (列 A 为空或数值, B+ 有数值) ──
            if nums:
                if header_row is None or current is None:
                    continue        # 表头之前, 或位于未被识别的段中
                sections[current].append(row_idx)
                data_started = True
                col_a_map[row_idx] = float(col_a) if a_numeric else None
            # ── 空行: 忽略 ──

        if header_row is None:
            notes.append("未定位到 Theta 表头行 (列 A 含 'theta' 且右侧有数值的行)")
        else:
            missing = sum(1 for v in angle_slots if v is None)
            if missing:
                notes.append(
                    f"表头行 (第 {header_row} 行) 有 {missing} 个空缺列, theta 角度不完整"
                )

        for r, txt in ignored:
            notes.append(f"第 {r} 行的 '{txt}' 标签出现在任何数据块之前, 已忽略")

        return {
            'header_row': header_row,
            'n_theta': n_theta,
            'theta_angles': [v for v in angle_slots if v is not None],
            'sections': sections,
            'col_a': col_a_map,
            'notes': notes,
        }

    @property
    def detection_notes(self) -> list[str]:
        """结构探测中的异常提示; 空列表 = 一切正常 (见 DataSource.detection_notes)。"""
        return list(self._detection_notes)

    @property
    def source_name(self) -> str:
        return os.path.basename(self._path)

    @property
    def frequencies(self) -> list[float]:
        return list(self._freqs)

    @property
    def theta_angles(self) -> list[float]:
        return list(self._theta)

    @property
    def phi_angles(self) -> list[float]:
        return list(self._phi)

    def read_batch(self, freq_indices: list[int]) -> dict[float, dict[str, np.ndarray | None]]:
        """批量读取多个频点数据 — 复用打开的 workbook 与 LRU 缓存。

        与 read_sections() 的区别: 缺失的频点 sheet 直接跳过, 不抛异常。
        """
        result: dict[float, dict[str, np.ndarray | None]] = {}
        for idx in freq_indices:
            freq = self._freqs[idx]
            try:
                tl, pl, tp_data, pp_data = self._read_freq(freq)
            except KeyError:
                continue
            result[freq] = {
                "theta_logmag": tl,
                "theta_phase": tp_data,
                "phi_logmag": pl,
                "phi_phase": pp_data,
            }
        return result

    def _read_freq(self, freq: float) -> tuple:
        """取一个频点的 4 个矩阵 (命中 LRU 缓存则直接返回)。

        read_sections() / read_batch() 共用, 保证两条路径读取行为一致。

        Returns:
            (theta_logmag, phi_logmag, theta_phase, phi_phase)
        Raises:
            KeyError: 该频点 sheet 不存在
        """
        if freq in self._cache:
            return self._cache[freq]

        sn = _freq_sheet_name(freq)
        if sn not in self._wb.sheetnames:
            raise KeyError(f"Frequency {freq} MHz not found in {self._path}")

        tl, pl, tp_data, pp_data = self._read_freq_matrices(self._wb[sn])
        self._cache[freq] = (tl, pl, tp_data, pp_data)
        return tl, pl, tp_data, pp_data

    def _read_freq_matrices(self, ws) -> tuple:
        """单趟 iter_rows 读取该频点 sheet 的全部 section。

        按 _section_rows 的行号列表单趟读取 (见 _read_matrices_by_rows) ——
        既不重复解析 XML, 也不假设行连续。

        不做 clipping — CTIA/EMQuest 标准无此要求。

        Returns:
            (theta_logmag, phi_logmag, theta_phase, phi_phase)
            phase 段缺失 → None; phi 幅度段缺失 → 全 NaN 矩阵 (与旧行为一致)。
        """
        mats = _read_matrices_by_rows(ws, self._section_rows, self._n_theta)
        tl = mats['theta']
        pl = mats['phi']
        if pl is None:
            pl = np.full_like(tl, float('nan'))
        return tl, pl, mats['theta_phase'], mats['phi_phase']

    def read_sections(self, freq_index: int) -> dict[str, np.ndarray | None]:
        freq = self._freqs[freq_index]
        tl, pl, tp_data, pp_data = self._read_freq(freq)
        return {
            "theta_logmag": tl,
            "theta_phase": tp_data,
            "phi_logmag": pl,
            "phi_phase": pp_data,
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


# ---------------------------------------------------------------------------
# 模块级工具
# ---------------------------------------------------------------------------

def _freq_sheet_name(freq: float) -> str:
    """频率值 → sheet 名："1154.0"→"1154" """
    return str(int(freq)) if freq == int(freq) else str(freq)


def _read_matrices_by_rows(ws, rows_by_section: dict, n_cols: int) -> dict:
    """按**行号列表**读取各 section —— 不假设行连续, 因此容忍块内空行。

    openpyxl 的 iter_rows() 每次调用都从第 1 行重新解析 XML, 故本函数一次遍历
    同时填充全部 section (旧实现逐段各解析一遍, 实测 2.46x 差距)。

    行号来自 FinalSummarySource._scan_layout()。矩阵第 k 行取自该段行号列表的
    第 k 个元素, 与数值实际所在行号解耦 —— 因此段内空行不会造成行错位。

    多线程在此无效 (实测反而慢 1.1~1.4x): 解析全程持 GIL, 且所有 sheet 共享
    同一个 zipfile 句柄 (ReadOnlyWorksheet._get_source → parent._archive.open,
    zipfile._SharedFile 内部有锁) → 底层读取被串行化并产生竞争开销。

    Args:
        ws:              openpyxl worksheet (read_only 或普通), 行号自 1 开始
        rows_by_section: {段名: [行号]}; 空列表表示该段不存在
        n_cols:          每段的列数 (ntheta, 自 B 列起算)

    Returns:
        {段名: (len(行号), n_cols) float64 ndarray 或 None}
        空单元格 / 非数值 → NaN —— 与逐段读取语义一致。
    """
    out: dict = {k: None for k in rows_by_section}
    valid = {k: r for k, r in rows_by_section.items() if r}
    if not valid:
        return out

    for k, rows in valid.items():
        out[k] = np.full((len(rows), n_cols), float('nan'), dtype=np.float64)

    target: dict[int, tuple[str, int]] = {}
    for k, rows in valid.items():
        for pos, r in enumerate(rows):
            target[r] = (k, pos)

    row_lo, row_hi = min(target), max(target)
    # iter_rows(min_row=row_lo) 的首行即 row_lo 且逐行连续:
    #   read_only → _cells_by_row 对缺失行补空行
    #   普通 Worksheet → range(min_row, max_row+1) 逐行取 cell
    for row_idx, row in enumerate(
        ws.iter_rows(min_row=row_lo, max_row=row_hi,
                     min_col=2, max_col=1 + n_cols, values_only=True),
        start=row_lo,
    ):
        hit = target.get(row_idx)
        if hit is None:
            continue
        mat = out[hit[0]]
        pos = hit[1]
        for ti, v in enumerate(row[:n_cols]):
            if v is None:
                continue
            try:
                mat[pos, ti] = float(v)
            except (ValueError, TypeError):
                pass
    return out


def _read_matrix(ws, start_row: int, n_rows: int, n_cols: int) -> np.ndarray:
    """读取单个连续的 n_rows × n_cols 矩阵 (自 B 列起算)。

    保留原签名。多段场景请用 _read_matrices_by_rows(), 否则每段都要重解析 XML。
    """
    rows = list(range(start_row, start_row + n_rows))
    return _read_matrices_by_rows(ws, {'m': rows}, n_cols)['m']
