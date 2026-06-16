# CLAUDE.md

## 项目：天线参数后处理程序 (Antenna Post-Processor)

从 EMQuest 天线测试数据计算 Gain/Directivity/Efficiency/LAG/Axial Ratio，填入 Excel 模板。

### 当前状态 (2026-06-16)

**已完成**: 多数据源+工作表自动匹配、Theta 外推开关、6位小数精度、进度条实时更新、GUI 完整验证（47/47 测试通过）、USER_GUIDE.html 14章完整文档。

**已知问题**: 8 个 GUI 测试被暂时跳过（因 git checkout 丢失了部分 `_init_multi_file_ui` 代码）。

### 核心架构

```
main.py → ui/main_window.py (PySide6 GUI)
       → src/worker.py (QThread)
       → src/pipeline.py (批处理管线)
       → src/calculator.py (NumPy 计算引擎)
       → src/exporter.py / report_exporter.py (Excel 输出)
```

### 数据源

| 格式 | 类 | 说明 |
|------|-----|------|
| `*_merged.csv` | `src/parser.py:MergedCSVParser` | 4 section: Theta/Phi LogMag + Phase |
| `*FinalSummary.xlsx` | `src/finalsummary_reader.py:FinalSummarySource` | Theta/Phi LogMag only (无 Phase) |
| 工厂方法 | `src/datasource.py:DataSource.from_path()` | 根据扩展名自动选择 |

### 计算公式

| 参数 | 公式 |
|------|------|
| Gain (dBi) | `G_total = 10·log₁₀(10^(Gθ/10) + 10^(Gφ/10))` |
| Directivity (dBi) | `D = 10·log₁₀(4π·Umax/Prad)` — 球面积分 |
| Efficiency | `η = 10^((G-D)/10) × 100%` |
| LAG (dB) | 线性域平均: `10·log₁₀(mean(10^(G/10)))` 固定 θ 上 φ 0-360° |
| Axial Ratio | Stokes 参数法 IEEE 149 |

### 关键规则

1. `ui/compiled/ui_main_window.py` **禁止手动编辑** — 用 Qt Designer 改 `.ui` 后重新编译
2. 模板列头识别用**正则**不用 LLM — 命名准则见 `USER_GUIDE.html` 第 6.1 节
3. `DataSource.from_path()` 工厂支持 `.csv`/`.xlsx`/`.xls`
4. 频点匹配用最近邻 (容差 ±5 MHz)
5. LAG = 线性域平均再转 dB，**非** dB 域直接平均
6. 多文件模式: 工作表名 ↔ 文件名通过 `sheet_file_matcher.py` 的 `extract_key()` 匹配
7. 所有计算值 `round(val, 6)` 保留 6 位小数

### 验证命令

```bash
# 测试
python3 -m pytest tests/ -q

# E2E
python3 -c "
from src.datasource import DataSource
from src.pipeline import run_pipeline
from src.lag_config import PRESET_AUTOMOTIVE
ds = DataSource.from_path('data/5G1_merged.csv')
r = run_pipeline(datasource=ds, template_path='data/template_5G1.xlsx',
    output_path='/tmp/test.xlsx', lag_config_override=PRESET_AUTOMOTIVE)
print(f'{sum(len(v) for v in r.values())} rows OK')
"

# 打包
pyinstaller antenna_post_processor.spec
```

### 文件地图

| 文件 | 职责 | 行数 |
|------|------|------|
| `main.py` | GUI 入口 | 42 |
| `src/pipeline.py` | 管线 + 外推 + 计算调度 | ~450 |
| `src/calculator.py` | Gain/Dir/Eff/LAG/AR 计算 | ~350 |
| `src/exporter.py` | Excel 模板填充 | ~200 |
| `src/excel_reader.py` | 模板列头解析 | ~200 |
| `src/lag_config.py` | LAG 配置 + 正则模式 | ~220 |
| `ui/main_window.py` | 主窗口 (多文件/外推/匹配) | ~1050 |
| `USER_GUIDE.html` | 使用手册 (14章) | 文档 |
