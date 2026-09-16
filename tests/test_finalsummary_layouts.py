"""FinalSummary 布局兼容性矩阵。

每个变体都把四段数据写成**唯一可辨识**的数值 (theta 幅度=100+, theta 相位=200+,
phi 幅度=300+, phi 相位=400+), 因此「读对了没有」是可以逐元素断言的, 而不是
只看 is not None。

背景: 旧实现的探测是「遇到第一个不符合的行/列就停」——
  n_phi  : 遇到无数据的行 → break
  n_theta: 遇到列缺口       → break
  section: 用 `row_idx > after_amp` 定位, 且找不到就继续向下抓住下一个 Phase 标签
这些假设在描述行数、空行数、标签文本略有差异的文件上会**静默**读错或读空。
"""

import os
import tempfile

import numpy as np
import openpyxl
import pytest

from src.finalsummary_reader import FinalSummarySource

NT_DEFAULT = 5
BASE = {"theta": 100.0, "theta_phase": 200.0, "phi": 300.0,
        "phi_phase": 400.0, "total": 500.0, "lhcp": 600.0, "rhcp": 700.0}


def _val(section: str, i: int, j: int) -> float:
    """第 i 个 phi 行、第 j 个 theta 列的值 —— 四段互不重叠, 可反查来源。"""
    return BASE[section] + i * 10 + j


def _expect(section: str, n_phi: int, n_theta: int) -> np.ndarray:
    return np.array([[_val(section, i, j) for j in range(n_theta)]
                     for i in range(n_phi)], dtype=np.float64)


def build(path: str, *, n_desc=2, n_phi=6, n_theta=NT_DEFAULT,
          blanks_after_header=0, blank_after_amp_rows=(), blank_in_phi_phase=False,
          blanks_before_phase_label=0, theta_phase_label="Phase",
          phi_phase_label="Phase", phi_label="Phi Polarization",
          header_gap_at=None, with_theta_phase=True, with_phi=True,
          with_phi_phase=True, trailing_blank_header_cols=0,
          trailing_total=False, trailing_cp_sections=False):
    """按给定布局写出 xlsx。所有数值由 _val() 决定, 与排版无关。"""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet(title="1000")
    r = 1

    for i in range(n_desc):
        ws.cell(r, 1, f"description line {i}")
        if trailing_blank_header_cols and i == 0:
            # 在很右侧写一个描述值 → 抬高 sheet 的 max_column,
            # 使表头行被 padding 出尾随空格子 (真实文件常见)
            ws.cell(r, 2 + n_theta + 2, "note")
        r += 1

    header_row = r
    ws.cell(r, 1, "Theta/Phi")
    for j in range(n_theta):
        col = 2 + j
        if header_gap_at is not None and j == header_gap_at:
            continue                      # 制造列缺口 (该格子留空)
        ws.cell(r, col, float(j * 10))
    r += 1
    r += blanks_after_header              # 表头与数据之间的空行

    def data_block(section, extra_blank_before=0, blank_after=()):
        nonlocal r
        for i in range(n_phi):
            if i in blank_after:
                r += 1                    # 数据块**内部**的空行
            ws.cell(r, 1, float(i * 10))   # 列 A = phi 角度
            for j in range(n_theta):
                ws.cell(r, 2 + j, _val(section, i, j))
            r += 1

    def labelled(section, label, blanks_after_label=0, blank_after=()):
        nonlocal r
        r += blanks_before_phase_label if section == "theta_phase" else 0
        ws.cell(r, 1, label)
        r += 1
        for _ in range(blanks_after_label):
            r += 1
        ws.cell(r, 1, "Theta/Phi")
        for j in range(n_theta):
            ws.cell(r, 2 + j, float(j * 10))
        r += 1
        data_block(section, blank_after=blank_after)

    data_block("theta", blank_after=blank_after_amp_rows)

    if with_theta_phase:
        labelled("theta_phase", theta_phase_label)

    if with_phi:
        labelled("phi", phi_label, blanks_after_label=1)   # label → Power → header → data

    if with_phi and with_phi_phase:
        labelled("phi_phase", phi_phase_label,
                 blank_after=(1,) if blank_in_phi_phase else ())

    def unknown_block():
        """真实文件里 Phi Phase 之后还有一个 'Total' 段 (总功率) —— 既非相位也非
        Phi Polarization。任何段识别都必须把它排除在外, 否则其数据会被并进上一段。"""
        nonlocal r
        r += 1
        ws.cell(r, 1, "Total"); r += 1
        ws.cell(r, 1, "Power"); r += 1
        ws.cell(r, 1, "Theta/Phi")
        for j in range(n_theta):
            ws.cell(r, 2 + j, float(j * 10))
        r += 1
        for i in range(n_phi):
            ws.cell(r, 1, float(i * 10))
            for j in range(n_theta):
                ws.cell(r, 2 + j, _val("total", i, j))
            r += 1

    def extra_block(label, base_key):
        nonlocal r
        r += 1
        ws.cell(r, 1, "Total"); r += 1
        ws.cell(r, 1, label); r += 1
        ws.cell(r, 1, "Theta/Phi")
        for j in range(n_theta):
            ws.cell(r, 2 + j, float(j * 10))
        r += 1
        for i in range(n_phi):
            ws.cell(r, 1, float(i * 10))
            for j in range(n_theta):
                ws.cell(r, 2 + j, _val(base_key, i, j))
            r += 1

    if trailing_total:
        unknown_block()
    if trailing_cp_sections:
        # 真实文件 (Ralab 583MB) 在 phi 相位之后还有其他段。'lhcpPhase'/'rhcpPhase'
        # 含 'phase' 子串, 用子串匹配会把它们误当成相位段并污染 phi_phase。
        extra_block("Axial Ratio", "total")
        extra_block("Polarization Tilt", "total")
        extra_block("lhcpLogMag", "lhcp")
        extra_block("lhcpPhase", "lhcp")
        extra_block("rhcpLogMag", "rhcp")
        extra_block("rhcpPhase", "rhcp")

    wb.save(path)
    wb.close()
    return header_row


# ── 变体表 ─────────────────────────────────────────────────────────
# (id, build() 关键字, 期望)  期望 = {段: True 精确匹配 | "nan" 同形状全 NaN | False 缺席}
_ALL = {"theta": True, "theta_phase": True, "phi": True, "phi_phase": True}


def _exp(**over):
    d = dict(_ALL)
    d.update(over)
    return d


LAYOUTS = [
    ("标准布局",                    dict(),                                        _exp()),
    ("描述行40(超旧30行扫描窗)",     dict(n_desc=40),                               _exp()),
    ("描述行120",                   dict(n_desc=120),                              _exp()),
    ("表头后1空行",                 dict(blanks_after_header=1),                   _exp()),
    ("表头后3空行",                 dict(blanks_after_header=3),                   _exp()),
    ("相位标签前1空行",             dict(blanks_before_phase_label=1),             _exp()),
    ("相位标签前3空行",             dict(blanks_before_phase_label=3),             _exp()),
    ("振幅段内插空行",              dict(blank_after_amp_rows=(2,)),               _exp()),
    ("振幅段内插2个空行",           dict(blank_after_amp_rows=(0, 3)),             _exp()),
    ("phi相位段内插空行",           dict(blank_in_phi_phase=True),                 _exp()),
    ("组合: 40描述行+空行+标签空行",  dict(n_desc=40, blanks_after_header=2,
                                          blank_after_amp_rows=(1,),
                                          blanks_before_phase_label=2),           _exp()),
    ("theta相位标签='Theta Phase'",  dict(theta_phase_label="Theta Phase"),         _exp()),
    ("theta相位标签='PHASE'",        dict(theta_phase_label="PHASE"),               _exp()),
    ("theta相位标签=' phase '",      dict(theta_phase_label=" phase "),             _exp()),
    ("theta相位标签='Phase (deg)'",  dict(theta_phase_label="Phase (deg)"),         _exp()),
    ("phi相位标签='Phi Phase'",      dict(phi_phase_label="Phi Phase"),             _exp()),
    ("phi标签='PHI POLARIZATION'",   dict(phi_label="PHI POLARIZATION"),            _exp()),
    ("phi标签='Phi  Polarization'",  dict(phi_label="Phi  Polarization"),           _exp()),
    ("n_phi=3",                     dict(n_phi=3),                                 _exp()),
    ("n_phi=1",                     dict(n_phi=1),                                 _exp()),
    ("n_theta=1",                   dict(n_theta=1),                               _exp()),
    ("表头有尾随空列",               dict(trailing_blank_header_cols=2),            _exp()),
    ("无theta相位段",               dict(with_theta_phase=False),                  _exp(theta_phase=False)),
    ("无phi段",                     dict(with_phi=False),                          _exp(phi="nan", phi_phase=False)),
    ("只有theta幅度",               dict(with_theta_phase=False, with_phi=False),   _exp(theta_phase=False, phi="nan", phi_phase=False)),
    ("尾部有未识别的 Total 段",      dict(trailing_total=True),                     _exp()),
    ("尾部Total + 空行 + 全段",      dict(trailing_total=True, n_desc=40,
                                          blanks_after_header=1),                   _exp()),
    ("尾部有圆极化/AR/Tilt 段",       dict(trailing_cp_sections=True),                _exp()),
    ("圆极化段 + 块内空行 + 无表头空行", dict(trailing_cp_sections=True,
                                          blank_after_amp_rows=(2,),
                                          blanks_after_header=2),                   _exp()),
]

_KEYMAP = {"theta": "theta_logmag", "theta_phase": "theta_phase",
           "phi": "phi_logmag", "phi_phase": "phi_phase"}


@pytest.mark.parametrize("name,kwargs,expect", LAYOUTS, ids=[c[0] for c in LAYOUTS])
def test_layout(name, kwargs, expect):
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    try:
        build(tmp.name, **kwargs)
        ds = FinalSummarySource(tmp.name)
        n_phi = kwargs.get("n_phi", 6)
        n_theta = kwargs.get("n_theta", NT_DEFAULT)
        result = ds.read_sections(0)

        for section, key in _KEYMAP.items():
            want = expect[section]
            got = result[key]

            if want is False:
                assert got is None, f"{name}: {section} 应缺席, 实际形状 {got.shape}"
                continue

            if want == "nan":
                assert got is not None, f"{name}: {section} 读成 None"
                assert got.shape == (n_phi, n_theta), \
                    f"{name}: {section} 形状 {got.shape} != {(n_phi, n_theta)}"
                assert np.all(np.isnan(got)), f"{name}: {section} 应为全 NaN (无该段数据)"
                continue

            exp = _expect(section, n_phi, n_theta)
            assert got is not None, f"{name}: {section} 读成 None"
            assert got.shape == exp.shape, \
                f"{name}: {section} 形状 {got.shape} != 期望 {exp.shape} (行/列被截断)"
            assert np.array_equal(got, exp), \
                f"{name}: {section} 数值不符; 首行读到 {got[0][:4].tolist()}, 期望 {exp[0][:4].tolist()}"
        ds.close()
    finally:
        os.unlink(tmp.name)


def test_theta_angle_vector_matches_columns():
    """theta 角度向量长度必须与矩阵列数一致, 否则下游布尔索引会错位。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    try:
        build(tmp.name)
        ds = FinalSummarySource(tmp.name)
        assert ds.theta_angles == [float(j * 10) for j in range(NT_DEFAULT)]
        assert len(ds.theta_angles) == ds.read_sections(0)["theta_logmag"].shape[1]
        assert ds.phi_angles == [float(i * 10) for i in range(6)]
        ds.close()
    finally:
        os.unlink(tmp.name)


def test_pipeline_surfaces_detection_notes():
    """布局告警必须经 pipeline 的日志出口到达用户。

    回归背景: detection_notes 最初只在「缺相位 且 请求了 AR」的分支里被读取,
    因此正常文件上产生的结构告警 (表头缺口 / 段行数不一致 / 标签被忽略) 全部被
    静默丢弃 —— 等于没有诊断。本测试锁住「任何结构异常都提示一次」这个行为。
    """
    from pathlib import Path

    from src.datasource import DataSource
    from src.pipeline import run_pipeline

    root = Path(__file__).resolve().parent.parent
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    out = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    out.close()
    try:
        build(tmp.name, header_gap_at=2)
        logs = []
        ds = DataSource.from_path(tmp.name)
        try:
            run_pipeline(datasource=ds,
                         template_path=str(root / "data" / "template_AFN_L1.xlsx"),
                         output_path=out.name,
                         log_callback=logs.append)
            assert ds.detection_notes, "前提不成立: 该布局本应产生探测告警"
            hits = [m for m in logs if "空缺列" in m and ds.source_name in m]
            assert hits, (f"探测告警未到达管线日志; notes={ds.detection_notes}, logs={logs}")
        finally:
            ds.close()
    finally:
        os.unlink(tmp.name)
        os.unlink(out.name)


def test_header_gap_is_reported_not_silently_truncated():
    """表头行列缺口属文件缺陷 —— 必须报告, 且不得静默把列数截断到缺口处。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    try:
        build(tmp.name, header_gap_at=2)
        ds = FinalSummarySource(tmp.name)
        assert ds.read_sections(0)["theta_logmag"].shape[1] == NT_DEFAULT, \
            "列数被截断到缺口处 (旧行为)"
        assert ds.detection_notes, "表头缺口未被报告"
        ds.close()
    finally:
        os.unlink(tmp.name)
