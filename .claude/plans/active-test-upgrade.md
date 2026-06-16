# 有源测试 (Active TRP) 功能升级架构规划

## 现状

管线支持：无源天线测试（Gain/Directivity/Efficiency/LAG）
数据格式：FinalSummary 新旧格式均可读取
新数据：有源测试，FinalSummary 中的 Power 为 EIRP (dBm)

## CTIA 公式（摘自 CTIA 01.90 Section 3.3-3.4）

### TRP 离散球面积分

```
TRP_lin = 1/2 × Σ(i=0..N-1) w_i × cut_i

cut_i = 1/M × Σ(j=0..M-1) [EIRP_θ(θ_i,φ_j) + EIRP_φ(θ_i,φ_j)]  (mW)

w_i = c_i / N,   c_i = {1 当 i=0 或 i=N-1; 2 其他}
```

### NHPRP 近地平线部分辐射功率

NHPRP ±45°：θ ∈ [45°, 135°] 
NHPRP ±30°：θ ∈ [60°, 120°]

Partial segment edge weight: w_partial = cos(θ_edge) − 1 + Σ(regular weights)

### EIRP 峰值

```
EIRP_peak = max_θ,φ [10×log₁₀(10^(EIRP_θ/10) + 10^(EIRP_φ/10))]  (dBm)
```

### Gain at Theta=0~70

```
LAG(0-70) = 10×log₁₀( mean_{θ∈[0,70], φ∈[0,360)} [10^(Gain_total/10)] )  (dB)
```

---

## 实施步骤

### Step 1: 新增计算函数 (`src/calculator.py`)

新增 3 个函数，复用现有球面积分框架：

| 函数 | 公式 | 输入 | 输出 |
|------|------|------|------|
| `compute_trp(eirp_linear, theta_rad)` | CTIA Sec 3.3 | (n_phi, n_theta) 线性 mW | TRP (dBm) |
| `compute_nhprp(eirp_linear, theta_rad, edge_deg)` | CTIA Sec 3.4 | (n_phi, n_theta) + 边界角度 | NHPRP (dBm) |
| `compute_peak_eirp(eirp_linear)` | 峰值检测 | (n_phi, n_theta) 线性 mW | Peak EIRP (dBm) |

关键：使用 Clenshaw-Curtis 权重系数，与 CTIA 精确对应。
约 60 行新增代码。

### Step 2: 管线集成 (`src/pipeline.py`)

在 `_process_one_frequency()` 中增加有源指标计算：

```python
row["trp"] = round(compute_trp(gain_linear, theta_rad), 2)
row["nhprp_45"] = round(compute_nhprp(gain_linear, theta_rad, 45.0), 2)
row["nhprp_30"] = round(compute_nhprp(gain_linear, theta_rad, 30.0), 2)
row["peak_eirp"] = round(compute_peak_eirp(gain_linear), 2)
row["lag_range_0_70"] = round(compute_lag_ranges(gain_linear, theta_deg, [(0,70)])[(0,70)], 6)
```

约 5 行新增。

### Step 3: 模板列头识别 (`src/excel_reader.py` + `src/exporter.py`)

新增列头识别规则：
- "TRP (dBm)" → col_type="trp"
- "NHPRP +/-45 (dBm)" → col_type="nhprp_45"
- "NHPRP +/-30 (dBm)" → col_type="nhprp_30"

约 15 行新增。

### Step 4: 报告模板 (`data/template_AFN_L1.xlsx`)

两个 Sheet：

```
┌─ 无源测试 ───────────────────────────────────┐
│ Antenna Passive Test Report                   │
│ Frequency (MHz) | Gain (dBi) | Efficiency (%) │
│ 1154  | 6.50  | 75.20                         │
└───────────────────────────────────────────────┘

┌─ 有源TRP测试 ──────────────────────────────────────────────┐
│ Antenna Active TRP Test Report                             │
│ Frequency (MHz) | Peak EIRP (dBm) | TRP (dBm) |            │
│ NHPRP +/-45 (dBm) | NHPRP +/-30 (dBm) |                    │
│ Gain at Theta=0~70 (dB)                                   │
│ 1154  | 29.95  | 21.10  | 19.03  | 17.10  | 9.50          │
└────────────────────────────────────────────────────────────┘
```

列头正则：
- `TRP` / `Total Radiated Power` → trp
- `NHPRP` + `45` → nhprp_45 
- `NHPRP` + `30` → nhprp_30
- `Peak EIRP` → peak_eirp
- `Gain at Theta=0~70` → lag_range_0_70（已有）

### Step 5: 工作频段过滤

新增频段配置 + 过滤逻辑。用户指定工作频段（如 1164-1224 MHz），
管线只输出该范围内的频点。

约 30 行新增（pipeline 中的简单 filter）。

### Step 6: 图/曲线生成

- 无源测试：Efficiency (%) vs Frequency (MHz) — XY 散点折线图
- 有源测试：Gain at Theta=0~70 (dB) vs Frequency — XY 散点折线图
- 有源测试：TRP/NHPRP vs Frequency — 多线图

使用 openpyxl chart 模块（不依赖 matplotlib），
在 `src/exporter.py` 中写入 Excel 图表对象。

约 60 行新增。

### Step 7: 集成测试 + E2E

- 用 AFN L1 数据跑完管线
- 验证 TRP 与 Summary.xlsx 预计算值偏差 < 0.1 dB
- 验证 NHPRP 与 Summary.xlsx 一致

---

## 改动文件清单

| 文件 | 改动类型 | 估计行数 |
|------|---------|:---:|
| `src/calculator.py` | 新增 3 函数 | +60 |
| `src/pipeline.py` | 集成调用 | +10 |
| `src/excel_reader.py` | 列头识别 | +15 |
| `src/exporter.py` | 写入 + 图表 | +80 |
| `data/template_AFN_L1.xlsx` | 新模板 | 重建 |
| `tests/test_calculator.py` | 单元测试 | +40 |
| **总计** | | **~205 行** |

---

## 验证标准

每个 Step 完成后验证：

| Step | 验证 |
|------|------|
| 1 | `pytest tests/test_calculator.py -q` 全部通过 |
| 2 | 单频点输出有 trp/nhprp 字段且值合理 |
| 3 | 模板列头能正确识别 "TRP (dBm)" 等 |
| 4 | Excel 输出符合 CTIA RA.3-1 格式 |
| 5 | 仅输出工作频段内频点 |
| 6 | .xlsx 文件包含图表 |
| 7 | TRP/NHPRP 与 Summary.xlsx 偏差 < 0.1 dB |
