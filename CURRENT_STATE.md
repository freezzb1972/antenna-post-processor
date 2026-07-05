# CURRENT STATE — 2026-07-05 21:00

**Branch:** master  
**Last commit:** `4bca7f9` — fix: reduce polar auto-scale padding with ax.margins(y=0.05)

## Active plan
- GUI 重构 + 多天线架构 + 参数自动识别（本轮主要完成）
- Excel 模板识别 + Word 报告输出

## Key decisions (this session)

| # | Decision | Why |
|---|----------|-----|
| 1 | 参数识别全部迁移到 JSON | `param_patterns.json` (55参数) 唯一来源。GUI 可编辑。 |
| 2 | 角度提取统一为 `extract_angles_from_headers()` | Gain/AR/RHCP/CP-XPI 四个方法委托给通用函数 |
| 3 | -999 全部替换为 NaN | 不掩盖计算错误，Excel 显示 #NUM! |
| 4 | QGroupBox 间距根因是 QSplitter 撑大 | `setSizePolicy(Fixed)` 纵向，不是 QSS padding 问题 |
| 5 | Heckbert 不加中心 0 夹持 | 回退到原始算法，加 `ax.margins(y=0.05)` 收紧 |
| 6 | RHCP dB→linear 转换修复 | `compute_lag_single` 期望线性值，传了 dB |
| 7 | Gain azimuth 不要求 pk070 | pipeline 条件从 AND 改为 OR |
| 8 | 天线选择器在 MainWindow | 多天线串行 pipeline，结果/图表联动 |

## Files changed (~30 commits)

| File | Changes |
|------|---------|
| `src/lag_config.py` | `extract_angles_from_headers()` 通用函数 + 3 个 from_xxx 委托 |
| `src/excel_reader.py` | `_classify_by_param_patterns` 最优先分类器 |
| `src/param_patterns.json` | **新增** 55 参数 × aliases + negate/extra_req |
| `src/calculator.py` | -999 → NaN |
| `src/pipeline.py` | pk070 放宽; RHCP/CP-XPI dB→linear 转换 |
| `src/azimuth_config.py` | 删除 image_width_cm |
| `src/chart_config.py` | `auto_detect_charts()` |
| `src/renderer.py` | `ax.margins(y=0.05)` |
| `src/chart_word_writer.py` | 统一百分比宽度 |
| `src/scale_manager.py` | QGroupBox QSS 统一到 dynamic_qss |
| `ui/pages.py` | ChartSettingsPage 恢复; 预览 ⚙ 修复; PatternManagerDialog 重写 |
| `ui/widgets.py` | TemplateSourceRow 两级合并为单一下拉; DataFileSelector 紧凑 |
| `ui/main_window.py` | 多天线 pipeline; 天线选择器; _last_matches 同步 |
| `ui/graph_viewer.py` | 天线选择器 |
| `.claude/GUI_STYLE_AUDIT.md` | **新增** QSS 样式清单 |
| `memory/gui-debugging-lessons.md` | **新增** 6 条 GUI 调试教训 |
| `memory/param-recognition-rules.md` | **新增** 参数识别原则 |

## E2E verified
- SuZhong 模板 + No1_withamp 数据: 139 rows × 417 images
- RHCP/AR/Gain 角度全部 [0,30,60,80] 正确提取

## Open questions
- AR 极坐标大跨度 (5~55dB) 是否分图? — Not blocker
- `_COLUMN_CLASSIFIERS` lambda 是否完全删除? — 保留兜底
- 输出区是否改回"另存为"按钮? — 当前 Chrome 风格 QLineEdit

## 关键教训 (写入项目记忆)
1. 间距大先查 sizePolicy，不是 QSS
2. QSS 生效顺序: theme → custom_qss → dynamic_qss
3. 数据源必须单一
4. 信号递归导致静默崩溃
5. 删除 property 注意孤立的 @property
6. 先诊断再修改 (加 print 确认值)
7. RHCP 正则要求 `at` → 实际列头没有 → 匹配失败
