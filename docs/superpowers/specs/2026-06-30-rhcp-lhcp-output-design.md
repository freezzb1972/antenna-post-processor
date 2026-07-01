# RHCP/LHCP 圆极化分量输出 — 需求记录

**状态:** 待客户确认  
**日期:** 2026-06-30

## 物理背景

- 圆极化天线分右旋 (RHCP) 和左旋 (LHCP)，由 E_θ 和 E_φ 的相位差决定
- E_RHCP = (E_θ - j·E_φ)/√2, E_LHCP = (E_θ + j·E_φ)/√2
- 三种数据源 (aborted CSV, merged CSV, FinalSummary Cplx) 本质上都有完整复电场信息，均可计算

## 当前状态

- `compute_axial_ratio()` 中已计算 `e_rhcp` / `e_lhcp`，仅作为 AR 中间量，未输出
- RHCP/LHCP Gain 未写入 Excel 模板

## 确认的输出方案 (方案 B+)

| 优先级 | 指标 | 说明 |
|--------|------|------|
| ⭐⭐⭐ | Boresight RHCP Gain | θ=0° 方向 RHCP 增益，GNSS 验收核心 |
| ⭐⭐⭐ | RHCP Gain at LAG angles | 对标 LAG/AR 角度体系 |
| ⭐⭐ | CP-XPI (RHCP - LHCP) | 极化纯度，与 AR 互补 |
| ⭐⭐ | Peak RHCP Gain | 对标已有 Peak Gain |

## 待确认

- 客户是否需要 LHCP Gain 对称输出
- 是否需要旋向翻转检测
- 是否需要 RHCP/LHCP TRP

## 实现路径

1. 修改 `calculator.py`: 新增 `compute_rhcp_lhcp_gain()` 函数
2. 修改 `pipeline.py`: 计算 boresight/peak/angle RHCP Gain + CP-XPI
3. 修改 `column_mapping.py`: 注册新列类型
4. 修改 `exporter.py`: 写入 Excel
5. 修改 `chart_config.py`: 支持 RHCP 图表（可选）
