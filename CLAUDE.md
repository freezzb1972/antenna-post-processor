# CLAUDE.md

## 项目：天线参数后处理程序 (Antenna Post-Processor)

从 EMQuest 天线测试 CSV 数据计算车企要求的各项天线指标，输出 Excel 报告。

### 输入数据

| 文件 | 格式 | 描述 |
|------|------|------|
| `*_merged.csv` | EMQuest 导出 CSV (151MB) | 4 section: Theta/Phi LogMag + Phase，105 频点 × 360 Phi × 111 Theta |
| `G1FinalSummary.xlsx` | Excel（每频点一个 Sheet） | Theta LogMag 转置版（Theta行 × Phi列），同源数据 |
| `车企天线数据需求.csv` | CSV | 客户测试需求规格 |

### 输出模板

`20260601乐来_SVW 5G1.xlsx` — 4 Sheet (5G1~5G4)，每 Sheet 列：
- Frequency | Directivity | Efficiency(%) | Efficiency(dB) | Gain | LAG(0-90°) | LAG(60-90°) | Theta=60 | Theta=70 | Theta=80 | Theta=90

### 核心计算

| 参数 | 定义 | 已有实现 |
|------|------|----------|
| Peak Gain (dBi) | 全空间峰值增益 | `antenna_params.py:compute_gain_dbi()` |
| Directivity (dBi) | 球面积分 D = 4π·U_max/P_rad | `antenna_params.py:compute_directivity()` |
| Efficiency (%) | η = 10^((G-D)/10) × 100 | 需从 Gain + Directivity 推算 |
| LAG (dB) | 固定俯仰角 θ 上方位面 0-360° 平均增益 | **新实现** |
| Axial Ratio (dB) | 极化椭圆长轴/短轴 | `antenna_params.py:compute_axial_ratio()` |

### LAG 计算方式

固定俯仰角 θ，方位角 φ 0-360° 扫描的增益曲线 Gain(φ)|θ=const：
- **LAG_mean**：该切片 360° 平均增益（客户确认方式）
- LAG(0-90°)：θ=0~90° 所有切片的平均增益的均值
- LAG(60-90°)：θ=60~90° 所有切片的平均增益的均值

### 依赖

- Python 3.8+
- `openpyxl`（Excel 读写）
- 标准库：csv, math, json

### 设计注意事项

1. 数据源：5G1_merged.csv 是主要数据源（含 Phase 数据，可算 AR）
2. G1FinalSummary.xlsx 只含 Theta LogMag，无法算 AR
3. 151MB CSV 加载需要内存优化（考虑分 section 流式读取）
4. 一个输入 CSV 对应多个天线 Sheet（5G1~5G4），频段分配不同
5. 实际会有多组天线测试数据，每组产生一个输出 Excel
6. GUI: PySide6 + Qt Designer + qt-material (dark_teal)，pyside6-uic 编译 .ui → .py，**禁止手动编辑编译产物**
7. i18n: Qt Linguist .ts → .qm，运行时 QEvent.LanguageChange → retranslateUi
8. 模板列头识别用**正则**不用 LLM（列头高度结构化，正则足够）
9. 5G4 Sheet 有两个 "Gain" 列 — columns 用 List 存储而非 Dict
