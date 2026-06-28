# CURRENT STATE — 2026-06-28 22:30

**Source:** session 天线后处理 Step 2-5 实施
**Phase:** All 5 steps complete ✅
**Last commit:** `12e907e` build: Step 1 建地基 — 公共模块提取
**Updated:** 2026-06-28

## Active plan
- **Design doc:** `docs/superpowers/specs/2026-06-27-master-detail-design.md` 第九章 5 步集成策略
- **Branch:** master
- **Progress:** ██████████ Step 1-5/5 done

## Completed

### Step 1 — 地基 (commit `12e907e`)
- 公共模块提取: `TemplateSourceRow`, `OutputSettingsGroup`, `AngleConfigGroup` 等可复用 widget

### Step 2 — 抽页面 `ui/pages.py` (~1800 行)
- `FileSettingsPage` — 模板/数据文件/匹配表/输出设置
- `AntennaParamsPage` — 天线参数配置（CalcParamsDialog → QWidget）
- `ChartSettingsPage` — 图表配置（PlotConfigDialog → QWidget）
- 每个 Page 独立可显示（无 parent 用本地状态，有 parent 读 MainWindow 属性）
- **Signal:** `params_changed()` + `chart_config_changed()`

### Step 3 — 搭框架 `ui/main_window.py`
- `_build_parameter_tab()`: 左侧 QListWidget（140px） + 右侧 QStackedWidget + 3 Page
- `_extract_execution_bar()`: 进度条/日志/按钮移至 rootVBox（跨标签共享）
- `_hide_settings_tabs()`: 删除 tabLag/tabPlot/tabCalc，重命名为 📐处理设置 / 📊计算结果 / 📈图表查看

### Step 4 — 接数据 `ui/main_window.py` + `ui/pages.py`
- `_on_start()` 委派到 FileSettingsPage
- `AntennaParamsPage._sync_to_mw()` / `ChartSettingsPage._sync_to_mw()` 实时写 MainWindow 属性
- **跨测试 C++ GC 防护**: `try/except RuntimeError`

### Step 5 — 清扫 (本轮完成)
- 删除 7 个废弃方法: `_hide_old_tab_content`, `_show_data_source_dialog`, `_show_calc_params_dialog`, `_show_plot_config_dialog`, `_init_param_overview`, `_init_report_preview` + 4 个预览回调
- 清理 `_connect_signals` 中 10 个 LAG 按钮旧信号连接
- `_on_start` 改用 `AntennaParamsPage.get_current_params()` 读取参数
- `_log_current_params` 优先从页面读取，保留后备
- `_update_status` 扩展到显示 AR + Gain 双行概要
- manifest 同步更新

## Key decisions

| # | Decision | Why |
|---|----------|-----|
| 1 | Page 直接读写 MainWindow 属性 | 不用内部状态+signal 双重模式，MainWindow 是唯一数据源 |
| 2 | _hide_settings_tabs 用固定索引 | `_make_tab_scrollable` 包裹 QWidget 进 QScrollArea 导致 `indexOf` 失效 |
| 3 | 隐藏旧内容不销毁 C++ 对象 | `setParent(None)` 导致子控件 C++ 对象被销毁，改用 `hide()` + `takeAt()` |
| 4 | 跨测试 C++ GC 防护 | 前测试 MainWindow GC 回收时子控件 C++ 对象先于 Python wrapper 销毁 |

## Files changed (this cycle)

| File | Lines | Change |
|------|-------|--------|
| `ui/pages.py` | ~1800 | **NEW** — 3 Page classes |
| `ui/main_window.py` | -41 net | Methods deleted + _on_start/log/status refactored |
| `ui/widgets.py` | +30 | Optional callback params to constructors |
| `verify-manifest.json` | +8/-6 | Synced with deleted methods and added widgets |

## Verification status

| Check | Result |
|-------|--------|
| Core tests (30) | 30/30 ✅ |
| E2E features (20) | 20/20 ✅ |
| GUI integrity (G1-G9) | 8/9 ✅ (G4 ScrollArea pre-existing) |

## Next steps

- **[ ]** 后续增强: 角度弹窗 UX 确认、多步进页面化

