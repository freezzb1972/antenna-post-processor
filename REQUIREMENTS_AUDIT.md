# 需求审计: 已实现 vs 未实现 (2026-07-05)

## 来源追溯

所有需求来自用户在本会话+上会话中提出的要求和讨论。下面对照每项需求检查实现状态。

---

## 一、图表配置 GUI 重构 (上会话 7 点)

| # | 需求 | 状态 | 说明 |
|---|------|------|------|
| 1 | 移除 Gain vs Freq / AR vs Freq 的角度按钮 | ❌ | 这两个是 2D 频率曲线，不需要角度。当前仍显示 `⚙ 参数` 按钮（Step 3 中改为参数按钮，但用户原本要求去掉） |
| 2 | C 类改名: "俯仰面切面图" → "2D 切面图" | ❌ | `src/chart_config.py:chart_categories()` 仍是 "C 类: 俯仰面切面图" |
| 3 | "方位面极坐标切面" → "极坐标方位面切面图" | ❌ | GUI label 未改 |
| 4 | 角度设置 GUI 重构: 支持多图表 (+按钮) | ❌ | 角度弹窗仍为「单角度+范围+步进」老三样，无图表级分组 |
| 4b | CP-XPI 加入图表 | ❌ | azimuth section 无 CP-XPI checkbox |
| 5 | 天线参数角度按钮同行 (checkbox 同排) | ❌ | 角度按钮仍在 checkbox 下方独立行 |
| 6 | 命名统一 (Gain/增益, AR/轴比/Axial Ratio) | ❌ | 天线参数页用 "Axial Ratio"，图表用 "轴比" |
| 7 | (讨论确认) | — | 已讨论 |

## 二、后续讨论中的补充需求

| # | 需求 | 状态 | 说明 |
|---|------|------|------|
| 8 | A 类 3D 图加 `⚙ 参数` 按钮 (同行) | ❌ | A 类图表无参数按钮 |
| 9 | DPI + 采样精度 移入参数对话框 | ❌ | 仍在主页"视角参数"区 |
| 10 | "角度设置" 对话框改名 "参数设置" | ❌ | 弹窗标题仍是 "XXX 角度配置" |
| 11 | 参数名称中英文切换 + tooltip | ❌ | 无实现 |
| 12 | 所有角度设置 GUI 统一为参数设置 (含角度+频点+DPI) | ⚠️ 部分 | 方位面弹窗加了频点选择，但 A 类未做 |

## 三、chart mode 同步问题

| # | 需求 | 状态 | 说明 |
|---|------|------|------|
| 13 | ChartSettingsPage 加 test mode selector | ✅ | commit `e12d04f` |
| 14 | azimuth 控件随 mode 切换重建 | ✅ | `_build_azimuth_section` 提取，`_rebuild_chart_categories` 调用 |

## 四、多天线架构

| # | 需求 | 状态 | 说明 |
|---|------|------|------|
| 15 | MainWindow 天线选择器 | ✅ | commit `e12d04f` |
| 16 | Per-antenna 配置存储 (AntennaConfig) | ✅ | `_antenna_configs` dict |
| 17 | 切换天线 → save/load 配置 | ✅ | `_save_current_antenna_config` / `_load_antenna_config` |
| 18 | 天线选择器联动 file entries | ✅ | `_refresh_antenna_selector` |
| 19 | Pipeline 接收 per-antenna config | ⚠️ 部分 | Worker 接收 `antenna_configs`, pipeline 未使用 |
| 20 | 多天线并行处理 | ❌ | `_on_one_click` 未改为循环 antenna |

## 五、频点选择

| # | 需求 | 状态 | 说明 |
|---|------|------|------|
| 21 | FrequencyPickerWidget | ✅ | commit `4b4eb50`, `ui/widgets.py` |
| 22 | 集成到 azimuth 参数对话框 | ✅ | `_show_azimuth_angle_popup` |
| 23 | 集成到 A 类参数对话框 | ❌ | A 类无参数对话框 |
| 24 | `ChartConfig.selected_frequencies` 字段 | ✅ | `src/chart_config.py` |
| 25 | Pipeline 频点过滤 | ❌ | 只存了字段，未在生成时过滤 |

## 六、结果/图表查看器多天线

| # | 需求 | 状态 | 说明 |
|---|------|------|------|
| 26 | 结果 tab 天线选择器 | ✅ | commit `4b4eb50` |
| 27 | 图表 tab 天线选择器 | ✅ | GraphViewer `set_antenna_list` |
| 28 | 联动 checkbox | ✅ | 两个 tab 都有 `☑ 联动` |
| 29 | 数据层选择 (最终参数/中间数据/原始数据) | ⚠️ 部分 | 下拉框已添加，但只实现了"最终参数" |
| 30 | `_antenna_results` 按天线存储 | ✅ | `main_window.py` |

## 七、Bug 修复 (本次)

| # | 问题 | 状态 | 说明 |
|---|------|------|------|
| 31 | TemplateSourceRow.set_path 缺失 | ✅ | commit `e807f14` |
| 32 | 天线下拉不填充 | ✅ | `_refresh_antenna_selector` 调用链修复 |
| 33 | set_path 递归崩溃 | ✅ | commit `77bba7e` |
| 34 | 模板参数与天线配置断连 | ✅ | commit `beebf96` |

## 八、Image Tag 相关 (上会话遗留)

| # | 需求 | 状态 | 说明 |
|---|------|------|------|
| 35 | 20 个图片 tag 定义 | ❌ | `config/sdt_tag_registry.json` 未更新 |
| 36 | VBA 侧边栏更新 | ❌ | 仍用旧 12 类 tag |
| 37 | AFN 模板重做 | ❌ | 未生成 |

---

## 总结

| 类别 | 总数 | 已完成 | 未完成 |
|------|------|--------|--------|
| GUI 重构 (命名/按钮/对话框) | 12 | 0 | 12 |
| 多天线架构 | 6 | 5 | 1 |
| 频点选择 | 5 | 3 | 2 |
| 结果/图表查看器 | 5 | 4 | 1 |
| Bug 修复 | 4 | 4 | 0 |
| Image Tag | 3 | 0 | 3 |
| **合计** | **35** | **16** | **19** |

## 优先级建议

**P0 (核心缺失, 无此功能不可用)**:
- #4 角度设置 GUI 重构 (多图表支持)
- #19/#20 Pipeline per-antenna 处理
- #2/#3/#6 命名统一

**P1 (重要, 影响使用体验)**:
- #1 移除频率曲线角度按钮
- #5 天线参数角度按钮同行
- #8/#9 A 类 3D 参数按钮 + DPI 移入
- #10 "角度"→"参数" 改名
- #25 Pipeline 频点过滤
- #29 中间数据/原始数据显示

**P2 (增强, 可后续迭代)**:
- #4b CP-XPI 图表
- #11 中英文切换
- #35/#36/#37 Image tag 体系更新
