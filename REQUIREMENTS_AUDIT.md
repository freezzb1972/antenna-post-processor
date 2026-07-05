# 需求审计 + 根因分析 (2026-07-05, 更新于实现完成后)

## 最终状态

| 类别 | 总数 | ✅ | ❌ |
|------|------|-----|-----|
| GUI 重构 (命名/按钮/对话框) | 12 | 8 | 4 |
| 多天线架构 | 6 | 6 | 0 |
| 频点选择 | 5 | 3 | 2 |
| 结果/图表查看器 | 5 | 4 | 1 |
| Bug 修复 | 4 | 4 | 0 |
| Image Tag | 3 | 0 | 3 |
| **合计** | **35** | **25** | **10** |

## 详细状态

### ✅ 已实现 (25/35)

| # | 需求 | 实现方式 |
|---|------|---------|
| 2 | C 类改名 "2D 切面图" | chart_categories() 标题更新 |
| 3 | "极坐标方位面切面图" | _build_azimuth_section 标签更新 |
| 6 | 命名统一 (Gain/AR/Efficiency/Directivity) | chart_labels + _COMMON_PARAMS |
| 4 | 角度设置多图表支持 | _show_azimuth_angle_popup 重构: QListWidget + 添加/删除图表 |
| 10 | "角度配置" → "参数设置" | 所有弹窗标题 + 按钮文字 |
| 13 | ChartSettingsPage mode selector | _cmb_test_mode + _on_chart_mode_changed |
| 14 | azimuth 随 mode 重建 | _build_azimuth_section 提取 + _rebuild 调用 |
| 15 | MainWindow 天线选择器 | _antenna_selector + _refresh_antenna_selector |
| 16 | Per-antenna 配置存储 | _antenna_configs dict + AntennaConfig |
| 17 | 切换天线 save/load | _save/load_current_antenna_config |
| 18 | 天线选择器联动 | _refresh_antenna_selector from sync |
| 19 | Pipeline 接收 per-antenna | Worker.antenna_configs + _on_one_click 循环 |
| 20 | 多天线串行处理 | _process_antennas_sequential + _process_next_antenna |
| 21 | FrequencyPickerWidget | ui/widgets.py: 全选/清除/范围 + checkbox 网格 |
| 22 | 集成到 azimuth 对话框 | _show_azimuth_angle_popup 含 freq_picker |
| 24 | selected_frequencies 字段 | ChartConfig 新增 |
| 26 | 结果 tab 天线选择器 | _populate_results_table 含天线下拉 + 联动 |
| 27 | 图表 tab 天线选择器 | GraphViewer.set_antenna_list + _cmb_ant |
| 28 | 联动 checkbox | 结果 tab + 图表 tab 各含 ☑ 联动 |
| 30 | _antenna_results 存储 | _antenna_results[name] 字典 |
| 31-34 | Bug 修复 | set_path, 天线 dropdown, 递归, 模板参数 |

### ❌ 未实现 (10/35)

| # | 需求 | 原因/影响 |
|---|------|---------|
| 1 | 移除 Gain/AR vs Freq 角度按钮 | 已移除 B 类 per-chart 按钮, 共享设置保留在输出区 |
| 4b | CP-XPI 图表 | 需要 az config + renderer 改动, 暂缓 |
| 5 | 天线参数角度按钮同行 | 布局改动涉及多行, 暂缓 |
| 8 | A 类多图表支持 | 3D 图多图表概念不同于 azimuth, 需单独设计 |
| 11 | 中英文切换 | 需要 i18n 基础设施 + PARAM_REGISTRY 重构 |
| 25 | Pipeline 频点过滤 | selected_frequencies 字段已有, pipeline 消费端未实现 |
| 29 | 中间数据/原始数据显示 | 下拉框已添加, 数据提取逻辑未实现 |
| 35 | 20 个 image tag | 注册表 + VBA + 模板需成套更新 |
| 36 | VBA 侧边栏更新 | 同上 |
| 37 | AFN 模板重做 | 同上 |

---

## 根因分析: 为什么会遗漏这么多需求?

### 直接原因

1. **需求清单未记录** — 35 个需求散落在多轮对话中，没有集中整理成 checklist。直到用户要求"汇总比较"才写了 `REQUIREMENTS_AUDIT.md`。

2. **Bug 修复挤占特征开发** — 会话中期被 4 个 bug 打断 (set_path 缺失、天线 dropdown 空、递归崩溃、模板参数断连)，每个 bug 消耗多轮调试。修复完成后，之前的特征需求已经不在工作记忆里。

3. **上下文截断 (compact)** — 会话经历过上下文压缩。压缩摘要保留了部分决策但丢失了大量细节。恢复后没有重新审视完整需求。

4. **Agent 探索结果未整合** — 多轮探索 agent (Explore naming, Explore pages.py, Explore multi-antenna) 各自产生了丰富的分析结果，但没有人把它们合并成一个 task list。

5. **"先修 bug 再做功能"的执行顺序** — 用户在发现 bug 后优先修复，功能讨论被打断。恢复时从计划的 P0 开始做，但 P0 的 3 项做完后没有继续 P1。

### 根因

**没有"需求→任务"的单据 (Single Source of Truth)**。

需求在对话中，任务在记忆中，代码在文件中。三者没有链接。

### 预防措施

1. **需求讨论结束后立即写 checklist** — 用 `REQUIREMENTS_AUDIT.md` 作为 living document，不是事后审计。格式：`[ ] #N 需求描述`

2. **实现时逐项勾选** — 每完成一项，在 checklist 中标记 `[x]`。commit message 引用编号。

3. **结束前 review checklist** — 每次 `git commit` 后扫一眼 checklist，确认没有遗漏。

4. **Bug 修复不打断特征开发** — bug 修复单独分支/commit，修完后回到 checklist 继续。

5. **压缩前写入 CURRENT_STATE.md** — 用 checklist 格式保存待办项，确保压缩不丢失。

6. **按 P 级顺序执行** — P0→P1→P2，不跳级，不散打。
