---
name: batch-report
description: 批量出天线测试报告 — 从 merged CSV 生成天线参数+方位图+中间数据
---

# /batch-report — 批量天线报告生成

从 merged CSV 数据源批量生成天线参数 Excel 报告、方位图 Word 报告、中间数据文件。
逻辑与桌面 App 完全一致，调用相同的 `run_pipeline()` 函数。

## 触发条件

用户要求批量出报告，或提到 "出AFN报告"、"生成天线报告"、"批量处理 merged CSV"。

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 数据文件 | `*_merged.csv` 或 `*_withAMP.csv` 路径列表 | 必填 |
| 模板 | 模板 .xlsx 路径 | 必填 |
| angles | Theta 角度列表 | [0,10,20,30,40,50,60,70] |
| pk070 | 是否生成 Gain 0-70° Pk 图 | True |
| rhcp | 是否生成 RHCP 方位图 | False |
| lhcp | 是否生成 LHCP 方位图 | False |
| show_caption | 是否显示图片题注 | False |
| image_width | 图片宽度 (cm) | 8.5 |
| gap_mhz | B 类频段间隙阈值 (MHz) | 10 |
| dual_y | B 类双 Y 轴配对 | False |
| dir_extrap | Directivity 外推方法 | linear |

## 实现

```python
from src.datasource import DataSource
from src.pipeline import run_pipeline
from src.azimuth_config import AzimuthReportConfig

for csv_path in csv_files:
    ds = DataSource.from_path(csv_path)
    az = AzimuthReportConfig()
    az.chart_output_dir = os.path.dirname(csv_path)
    az.chart_output_filename = f'{stem}_图表报告.docx'
    az.data_gain_output_dir = os.path.dirname(csv_path)
    az.data_gain_output_filename = f'{stem}_Gain.xlsx'
    az.cut_azimuth_polar = True
    az.cut_azimuth_polar_pk070 = pk070
    az.cut_azimuth_polar_rhcp = rhcp
    az.cut_azimuth_polar_lhcp = lhcp
    az.azimuth_cut_angles = angles
    az.show_caption = show_caption
    az.image_width_cm = image_width
    az.freq_gap_mhz = gap_mhz
    az.dual_y_enabled = dual_y

    run_pipeline(
        datasource=ds,
        template_path=template,
        output_path=f'{dir}/{stem}_天线报告.xlsx',
        azimuth_config=az,
        dir_extrap_method=dir_extrap,
        out_excel=True, out_word=True, out_data=True,
    )
```

## 输出（每个数据源）

```
{stem}_天线报告.xlsx      — 天线参数 Excel
{stem}_图表报告.docx      — 方位图 Word (每频点一行两图)
{stem}_Gain.xlsx         — Gain 中间数据
{stem}_GainPk070.xlsx    — Gain 0-70° Pk 中间数据
```
