# 图表查看 & 图表配置 — 架构对齐实现计划

## Context

统一图表查看器（GraphViewer）和图表配置（ChartConfig），新增预览-导出两阶段流程，补齐图表类型，泛化 Word 输出 + 模板支持。

设计文档: `docs/superpowers/specs/2026-07-01-viewer-config-alignment.md`

## Phase 1: 基础层

### 1a. ChartConfig 新增 E_θ/E_φ

| 文件 | 改动 |
|------|------|
| `src/chart_config.py` | 新增字段 `pattern_3d_etheta`, `pattern_3d_ephi`。更新 `all_chart_keys()`, `chart_labels()`, `chart_categories()`, `merge()`。更新 `has_any_a_class` 属性包含新字段。`_CHART_PATTERNS` 加 E_θ/E_φ 自动检测正则 |
| `src/plotter.py` | `generate_all_for_frequency()` 新增参数 `extra_patterns: Dict[str, np.ndarray] = {}` (key: 图表类型, value: dB 矩阵)。遍历渲染，避免逐个加命名参数 |
| `src/pipeline.py` | `_process_one_frequency()`: 构建 `extra_patterns = {"3d_etheta": raw["theta_logmag"], "3d_ephi": raw["phi_logmag"]}` 传递 |

### 1b. 查看器补齐 Freq Curves

已更新 `FREQ_CURVE_DEFS`。`ui/graph_viewer.py` 的 `_get_available_freq_curves()` 自动扫描结果匹配。无额外改动。

## Phase 2: pipeline 拆分

### 2a. compute_only vs full_export

| 文件 | 改动 |
|------|------|
| `src/pipeline.py` | 新增参数 `compute_only: bool = False`。True 时跳过 Matplotlib 渲染、Excel openpyxl 写入、Word 生成。`_process_one_frequency()` 始终存储 `row["_raw_data"]`（已有），不新增冗余顶层字段 |
| `src/worker.py` | 透传 `compute_only` 参数 |

## Phase 3: GUI 按钮改造

### 3a. 三按钮 + 状态机

| 文件 | 改动 |
|------|------|
| `ui/designer/main_window.ui` | Qt Designer: 删除 `btnStart`，新增 `btnPreview`(text="👁 预览") + `btnExport`(text="📄 出报告") + `btnStop`(已有)。编译 → `ui/compiled/ui_main_window.py` |
| `ui/main_window.py` | `_extract_execution_bar()`: `btn_row` 添加 `btnPreview`/`btnExport`/`btnStop`。`btnStart` 引用全部替换为 `btnPreview` 或 `btnExport`。新方法 `_enter_previewing()` / `_enter_ready()` / `_enter_exporting()`，复用 `_enter_busy()`/`_restore_start_button()` 模式。`_on_preview()`: worker(compute_only=True)。`_on_export()`: worker(compute_only=False)。状态机按钮互锁 |

### 3b. 数据陈旧检测

| 文件 | 改动 |
|------|------|
| `ui/main_window.py` | LAG 角度/算法参数/数据文件变更 → `_preview_state = IDLE`。图表配置/输出路径变更不触发。出报告前检查状态 |

## Phase 4: 查看器增强

### 4a. "2D Cuts" 模式

| 文件 | 改动 |
|------|------|
| `ui/graph_viewer.py` | 新增模式页签 "2D Cuts"。俯仰面 (Elevation Cut): Phi 滑块 + 数据源切换 (Gain/AR/E_θ/E_φ) + Polar/Rect 切换。方位面 (Azimuth Cut): Theta 多选 + Azimuth Polar 渲染。新增 `_draw_elevation_cut()` / `_draw_azimuth_cut()` 方法，复用 `extract_graph_data()` 的已有 data key (`theta_db`/`phi_db`/`gain_db`/`ar_linear`) |

### 4b. "应用角度到图表配置" 按钮

| 文件 | 改动 |
|------|------|
| `ui/graph_viewer.py` | 2D Cuts 工具栏新增按钮。读当前选中角度，写 `mw._chart_config_required.cut_2d_phi_angles` / `mw._azimuth_config.azimuth_cut_angles` |

## Phase 5: 报告层

### 5a. full_report 嵌入图表

| 文件 | 改动 |
|------|------|
| `src/report_exporter.py` | `export_full_report()` 接收 `pattern_images: Dict[str, Dict[float, BytesIO]]`。图片在 pipeline 端已渲染为 PNG，不重渲染。`_embed_report_images()` 循环嵌入 |
| `src/pipeline.py` | `export_full_report()` 调用时传递 `image_groups` |

### 5b. B 类频点曲线 PNG 渲染

| 文件 | 改动 |
|------|------|
| `src/renderer.py` | `BaseRenderer` 新增抽象方法 `render_freq_curve(freqs, values, label, ylabel, title) → BytesIO`。`MatplotlibRenderer` 实现: x=频率 MHz, y=参数值, 自动适配刻度/轴范围/图幅。`CloudRenderer` stub 委托 fallback |
| `src/pipeline.py` | `_export_charts()` 遍历 `row` dict，用 `_COLTYPE_TO_CHART` 映射找到 B 类参数 key，调用 `render_freq_curve()` 生成 PNG。B 类 key 统一前缀 `"B:"` 避免与 A/C 类冲突 (如 `"B: Efficiency vs Freq"`)。加入 `image_groups` |

### 5c. 中间数据扩展

| 文件 | 改动 |
|------|------|
| `src/azimuth_data_writer.py` → 重命名为 `src/intermediate_data_writer.py` | 泛化: 俯仰面 (worksheet=频率, 列=Phi角, 行=Theta) + 方位面 (列=Theta角, 行=Phi)。数据源: Gain/AR/E_θ/E_φ |
| `ui/pages.py` | FileSettingsPage 中间数据设置下级窗体扩展 |

## Phase 6: Word 模板模式

### 6a. 激活 WordReporter + 循环域

| 文件 | 改动 |
|------|------|
| `src/word_reporter.py` | 清理死代码 (307 行后 lxml 块)。新增 `_expand_loops()`: 配对 `loop_start_<key>`/`loop_end_<key>`，OXML 深拷贝展开。新增 `fill_metadata(metadata: dict)`: 包装已有 `fill_content_controls()` + `fill_placeholders()`，统一入口 |
| `src/pipeline.py` | 新增 `word_template_path` 参数。不为空时调用 WordReporter 替代 chart_word_writer |

### 6b. Word 输出布局设置

| 文件 | 改动 |
|------|------|
| `ui/pages.py` | FileSettingsPage 新增 "Word 输出设置..." 按钮 → 子对话框。模式切换 (按频点/按类型)、图表勾选排序、分页符、恢复默认 |
| `src/pipeline.py` | 图片收集函数: 遍历 `sheet_results`，提取 `row["_images"]`，合并 B 类 PNG。复用已有收集模式 |
| `src/chart_word_writer.py` | 接受排序后的 `image_groups` + 布局模式 |

### 6c. 布局抽象

`chart_word_writer` 和 `WordReporter` 共用布局描述结构:
```python
LayoutSpec = List[Tuple[str, float]]  # [(group_name, freq_mhz), ...]
```
两种模式通过遍历 `LayoutSpec` 实现，不各自硬编码循环逻辑。

## Phase 7: 文档

| 文件 | 改动 |
|------|------|
| `USER_GUIDE.html` | 新增第 25 章: Word 模板报告 (书签规则/循环语法/SDT 映射/完整图表 key 列表/示例) |
| `output/word_template_example.docx` | python-docx 生成示例模板，含封面 SDT + 书签 + 循环域 |

## Verification

1. `python3 -m pytest tests/ -q -x --deselect=tests/test_e2e_features.py --deselect=tests/test_gui_e2e.py` — 39 测试不退化
2. E2E: NO1_AMP_merged.csv → 预览 → 查看器 3D/2D/Freq Curves → 出报告 → 5 输出
3. 手动: 三按钮状态机互锁; 换文件后强制重新预览; Word 模板循环域展开正确
