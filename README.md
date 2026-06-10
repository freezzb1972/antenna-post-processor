# 天线参数后处理程序 (Antenna Post-Processor)

车企天线 OTA 测试数据自动分析工具。从 EMQuest 测试系统导出的 CSV 数据，计算 Directivity、Efficiency、Gain、LAG 等天线指标，输出格式化 Excel 报告。

## 项目状态

**阶段**: 需求分析完成，待实现

## 数据流

```
EMQuest 导出 CSV (5G1_merged.csv, 151MB)
    │
    ├── Theta Log Magnitude (105频点 × 360 Phi × 111 Theta)
    ├── Theta Phase
    ├── Phi Log Magnitude
    └── Phi Phase
         │
         ▼
    [天线参数计算]
    ├── Peak Gain (dBi)
    ├── Directivity (dBi) — 球面积分
    ├── Efficiency (%) — 从 Gain 和 Directivity
    ├── LAG (dB) — 固定俯仰角方位面平均增益
    └── Axial Ratio (dB) — 极化椭圆
         │
         ▼
    [Excel 输出]
    └── 20260601乐来_SVW 5G1.xlsx (4 Sheet: 5G1~5G4)
```

## 目录结构

```
antenna-post-processor/
├── CLAUDE.md          # 项目上下文（Claude Code 自动加载）
├── README.md          # 本文件
├── data/              # 输入文件样本和需求
│   ├── 车企天线数据需求.csv
│   └── template_5G1.xlsx       # 输出模板
├── docs/              # 设计文档和上下文
│   └── CONTEXT.md              # 完整会话上下文
└── src/               # 源代码（待实现）
```

## 参考项目

已有的 EMQuest 分析工具：https://github.com/freezzb1972/emquest-antenna-toolkit

可复用的计算函数位于 `antenna_params.py`：
- `compute_gain_dbi()` — 增益校准
- `compute_axial_ratio()` — 轴比
- `compute_directivity()` — 方向性系数
- `compute_beamwidth()` — 波束宽度
