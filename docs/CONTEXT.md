# 会话上下文 (2026-06-10)

## 项目目标

开发新应用：从 EMQuest 天线测试 CSV 数据计算车企要求的各项天线指标，输出格式化 Excel 报告。

与已有 `emquest-antenna-toolkit` 项目的关系：参考其计算逻辑，但是全新应用，面向车企客户需求。

## 数据源分析

### 1. 5G1_merged.csv（主数据源）

- 大小: 151MB, 190,059 行
- 格式: EMQuest 标准导出格式
- 结构:
  - `Theta Log Magnitude` (行3-38013): 105频点，111 Theta(0-110° step 1°)，360 Phi(0-359° step 1°)
  - `Theta Phase` (行38014-76024): 同上
  - `Phi Log Magnitude` (行76025-114035): 同上
  - `Phi Phase` (行114036-152046): 同上
- 频段:
  - Low: 690-960 MHz (30点)
  - Mid: 1710-2690 MHz (43点)
  - High: 3300-5000 MHz (32点)
- 总计: 105 频点，每个 section ~420万数据点，总计 ~1680万数据点

### 2. G1FinalSummary.xlsx

- 105 个 Sheet (每个频点一个，命名如 "690", "694", ...)
- 每个 Sheet: 1092行 × 112列
- 数据格式: Theta行 × Phi列 的 LogMag(dB) 矩阵
- 仅含 Theta Log Magnitude（无 Phase 数据，无 Phi LogMag）
- 与 5G1_merged.csv 数据一致（经对比验证）
- 可能是从 merged CSV 整理而来，但不确认同一次测试

### 3. 车企天线数据需求.csv

测试需求规格：

| 天线类型 | 频率范围 | 测试项 | 测试角度 |
|----------|----------|--------|----------|
| GNSS | 1559-1606MHz, 1164-1270MHz | LAG+AR (Passive & Active) | θ=0-80° step 10°, φ=0-360° step 1° |
| GNSS | 同上 | 2D/3D辐射方向图 | θ=0-180° step 5°, φ=0-360° step 1° |
| Cellular | 617-5000MHz 多段 | 60°-90° LAG | θ=60-90° step 2°, φ=0-360° step 1° |
| Cellular | 同上 | 2D/3D方向图+效率 | θ=0-180° step 5°, φ=0-360° step 1° |
| V2X | 5855-5925MHz | 特定角度 LAG | θ=80-100° step 1°, φ=0-360° step 1° |
| V2X | 同上 | 2D/3D方向图+效率 | θ=0-180° step 5°, φ=0-360° step 1° |

### 4. 输出模板 20260601乐来_SVW 5G1.xlsx

4 个 Sheet:

**5G1 & 5G2** (同一结构):
- θ Range: 0-110°, Step: 1°
- 频点: 690-960 (31点) + 1710-2170 (24点) + 2300-2400 (5点) + 2483-2690 (20点) + 3300-4200 (19点) + 4400-5000 (13点) = ~112 频点
- 列: Frequency | Directivity | Efficiency(%) | Efficiency(dB) | Gain | Theta=0-90 LAG | Theta=60-90 LAG | Theta=60 | Theta=70 | Theta=80 | Theta=90

**5G3**: 结构同上，频点 1710-5000MHz (~82点)

**5G4**: 多一列 Gain（重复），频点 1710-5000MHz (~82点)

## 关键设计决策

1. **LAG = 方位面平均增益**（用户确认）：固定 θ 上 Gain(φ) 的线性平均值
2. **主数据源 = 5G1_merged.csv**：含完整 Phase 数据，可计算 AR
3. **G1FinalSummary.xlsx 作为备用**：与 merged CSV 数据一致，格式更易处理
4. **AR 计算用 antenna_params.py:compute_axial_ratio()**：基于 Re/Im 原始数据，比 toolkit 版本更通用
5. **Directivity 用 antenna_params.py:compute_directivity()**：接受已标定的 gain 数组

## 待确认事项

- [ ] 5G1~5G4 各自对应哪个物理天线？
- [ ] 实际会有多少组输入数据？
- [ ] Theta=60/70/80/90 列是单点增益(峰值)还是该俯仰角的 LAG？
- [ ] 5G4 多出来的 "Gain" 列含义？
- [x] LAG 定义 → 方位面平均增益
- [x] 数据一致性 → G1FinalSummary = merged CSV 转置
