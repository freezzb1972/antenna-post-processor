---
name: batch-report
description: 批量出天线测试报告 — 从 merged CSV 生成天线参数 Excel + 方位图 Word + 中间数据。触发条件：用户要求批量出报告、生成天线报告、出AFN/ETS报告、处理 merged CSV、生成图表报告。即使只提"出报告"或"生成数据"，也应主动询问是否需要批量处理。
---

# /batch-report — 批量天线报告生成

从 merged CSV 数据源批量生成天线参数 Excel 报告、方位图 Word 报告、中间数据文件。
逻辑与桌面 App 完全一致，调用相同的 `run_pipeline()` 函数。

## 触发条件

用户要求批量出报告，或提到 "出报告"、"生成天线报告"、"批量处理 CSV"、
"生成图表报告"、"出AFN报告"、"出ETS报告"、"出方位图"。

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 数据文件 | `*_merged.csv` 路径列表 | 必填 |
| 模板 | 模板 .xlsx 路径 | 必填 |
| 输出目录 | 报告输出目录 | 数据文件所在目录 |
| angles | Theta 角度列表 | [0, 30, 60, 80] |
| chart_types | 图表类型: gain/ar/rhcp/lhcp | gain, ar, rhcp |
| show_pkgain | Pkgain vs 频率曲线 | True |
| word_columns | Word 每行图片列数 | 2 |
| image_width_pct | 图片宽度(列宽%) | 90 |
| show_caption | 图片上方题注 | True |
| dir_extrap | Directivity 外推方法 | none |

## 输入文件格式

支持的 CSV 格式:
- **EMQuest merged CSV**: 4 section (Theta/Phi LogMag + Phase)，`DataSource.from_path()` 自动识别
- **FinalSummary .xlsx**: 同理

## 输出

```
{stem}_天线报告.xlsx      — 天线参数 Excel (Gain/Directivity/RHCP/AR/LAG)
{stem}_图表报告.docx      — 方位图 Word (每频点 2 列等大, Gain→AR→RHCP→Pkgain)
{stem}_中间数据.xlsx      — 方位面原始矩阵数据
```

## 实现

```python
import sys, os, io
sys.path.insert(0, "/mnt/d/cc/antenna-post-processor")

# ═══ Monkey-patch: 极坐标 margins(0) + 自然刻度 (不强制从0) ═══
import numpy as _np
import src.renderer as _rmod

def _patched_render_azimuth_polar(
    self, phi_deg, curves, freq_mhz, *,
    antenna_name="", dpi=150, ylabel="Gain (dBi)",
    title="", ticks_override=None,
):
    import matplotlib.pyplot as _plt
    phi_rad = _np.deg2rad(phi_deg)
    colors = ["#E74C3C", "#2980B9", "#27AE60", "#F39C12",
              "#8E44AD", "#1ABC9C", "#E67E22", "#2C3E50"]
    linestyles = ["-", "--", "-.", ":"]
    fig, ax = _plt.subplots(subplot_kw={"projection": "polar"},
                            dpi=dpi, figsize=(7, 7))
    sc = sorted(curves, key=lambda x: x[0])
    phi_c = _np.empty(len(phi_rad) + 1)
    phi_c[:-1] = phi_rad; phi_c[-1] = phi_rad[0] + 2 * _np.pi
    for i, (ta, g1d) in enumerate(sc):
        c = colors[i % len(colors)]
        ls = linestyles[(i // len(colors)) % len(linestyles)]
        gc = _np.empty(len(g1d) + 1); gc[:-1] = g1d; gc[-1] = g1d[0]
        ax.plot(phi_c, gc, color=c, linestyle=ls, linewidth=1.2,
                label=f"θ={ta:.0f}°")
    ax.set_theta_zero_location("N"); ax.set_theta_direction(-1)
    ax.set_thetagrids(range(0, 360, 30),
                      labels=[f"{d}°" for d in range(0, 360, 30)], fontsize=10)
    ax.set_title(title or f"{freq_mhz:.0f}MHz - {ylabel}", fontsize=12, pad=12)
    ax.grid(True, alpha=0.4)
    ax.autoscale_view(); ax.margins(y=0)  # 核心: 不强制从0
    if ticks_override:
        ax.set_ylim(ticks_override[0], ticks_override[-1])
        ax.set_yticks(ticks_override)
        ax.set_yticklabels([_rmod._tick_label(v) for v in ticks_override], fontsize=10)
        ax.set_rlabel_position(15)
        ax.annotate(_rmod._tick_label(ticks_override[0]),
                    xy=(_np.deg2rad(15), ticks_override[0]),
                    fontsize=10, ha='center', va='center', color='#555555')
    if len(sc) > 1:
        ang = _np.deg2rad(45)
        ax.legend(loc="lower left", fontsize=9, framealpha=0.6,
                  bbox_to_anchor=(.5 + _np.cos(ang)/2, .5 + _np.sin(ang)/2))
    fig.subplots_adjust(left=0.08, right=0.92, top=0.92, bottom=0.08)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi); buf.seek(0); _plt.close(fig)
    return buf

_rmod.MatplotlibRenderer.render_azimuth_polar = _patched_render_azimuth_polar

# ═══ 业务代码 ═══
from src.datasource import DataSource
from src.pipeline import run_pipeline
from src.azimuth_config import AzimuthReportConfig
from src.chart_config import ChartConfig
from src.chart_plan import expand_to_instances, ChartCategory

OUTPUT_DIR = "/path/to/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

for csv_path in csv_files:
    stem = os.path.splitext(os.path.basename(csv_path))[0]
    ds = DataSource.from_path(csv_path)

    az = AzimuthReportConfig()
    az.cut_azimuth_polar = "gain" in chart_types
    az.cut_azimuth_polar_ar = "ar" in chart_types
    az.cut_azimuth_polar_rhcp = "rhcp" in chart_types
    az.azimuth_cut_angles = [angles]         # list-of-lists: 每子列表=一个图表
    az.azimuth_cut_angles_ar = [angles]
    az.azimuth_cut_angles_rhcp = [angles]
    az.word_layout_mode = "side_by_side"
    az.word_columns = word_columns
    az.word_image_width_pct = image_width_pct
    az.show_caption = show_caption
    az.antenna_name = stem
    az.chart_output_dir = OUTPUT_DIR
    az.chart_output_filename = f"{stem}_图表报告.docx"
    az.data_output_dir = OUTPUT_DIR
    az.data_output_filename = f"{stem}_中间数据.xlsx"

    cc = ChartConfig()
    cc.chart_gain_freq = show_pkgain  # Pkgain vs Frequency

    instances = expand_to_instances(cc, az)
    # 标签对齐 pipeline 内部 _label_for_image_key
    _IMG_KEY_MAP = {
        "azimuth_polar": "Gain Azimuth Cut",
        "azimuth_polar_ar": "AR Azimuth Cut",
        "azimuth_polar_rhcp": "RHCP Azimuth Cut",
    }
    for ci in instances:
        if ci.category == ChartCategory.Z_AZIMUTH:
            ci.label = _IMG_KEY_MAP.get(ci.image_key, ci.label)
            ci.sort_order = 0
        elif ci.category == ChartCategory.B_FREQ:
            ci.sort_order = 100  # Pkgain 放最后

    run_pipeline(
        datasource=ds,
        template_path=template_path,
        output_path=os.path.join(OUTPUT_DIR, f"{stem}_天线报告.xlsx"),
        chart_config_obj=cc,
        azimuth_config=az,
        out_excel=True, out_word=True, out_data=True,
        chart_instances=instances,
        freq_source="datasource",
        ar_output_db=True,
    )
    ds.close()
```

## 注意事项

- **Monkey-patch 必须**: `margins(y=0)` 修复极坐标 AR 曲线被压到中心的问题
- **多天线**: 每个 CSV 单独调用 `run_pipeline()`，避免多源模式下同频点图片覆盖
- **Word 图片顺序**: `sort_order` 控制 — Z 类方位图=0 在前，B 类 Pkgain=100 在后
- **ETS 兼容**: `src/calculator.py` CP 分解已改为 `E_RHCP = (E_θ + jE_φ)/√2` (ETS convention)
- **Directivity**: 默认 `dir_extrap_method="none"` 不额外推 theta
