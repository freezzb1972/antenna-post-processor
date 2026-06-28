# CURRENT STATE — 2026-06-29 00:00

**Source:** session 2026-06-28 模型路由配置 + 上次会话后续
**Last commit:** `90dcab7` feat: 差值表与差值图表分开控制(两个复选框)
**Updated:** 2026-06-29

## Active plan
- Master-Detail refactor 后续: UI修复+功能完善基本完成
- **Branch:** master
- **Progress:** 主要功能全部完成

## Completed (previous sessions, cumulative)

### UI 修复
- 天线参数窗体: 弹窗 → 内联展开(QStackedWidget), QSplitter左右可调
- 执行栏: 左=天线参数面板, 右=日志, QSplitter可调
- 输入输出页: 左右分栏+垂直分栏
- 移除qt-material → Fusion+QPalette(4精选主题), 灰字修复

### Codex 审查修复 (11/20 bugs)
- #1/#3/#4/#5/#6/#9/#10/#11/#13/#17/#18

### 菜单
- 文件→打开/保存/另存/打印/退出, 窗口列表+✕关闭按钮

### 图表
- Gain/AR vs Frequency 图表: X/Y轴自动刻度, 标记统一红色, 平滑线深色
- 多步进差值比较表+差值散点图(Y=0基线)
- 差值表/图分开控制(两个复选框)
- 交互式 PivotChart: PageField 参数/步进角度下拉筛选, 单一图表联动更新, 可右键插入切片器
- PivotTable 异常时自动回退到静态图表

## Key decisions (this session)

| # | Decision | Why |
|---|----------|-----|
| 6 | Agent 分级路由: haiku→flash, opus→pro | `CLAUDE_CODE_SUBAGENT_MODEL` 会锁定所有 agent 为同一模型，删掉后用 `ANTHROPIC_DEFAULT_*_MODEL` 实现 per-tier 路由 |
| 7 | CC Switch 非必须 | Claude Code 自带 `ANTHROPIC_DEFAULT_*_MODEL` 路由，直连 DeepSeek 即可 |
| 8 | 主会话用 pro (1M 上下文) | 大任务 1M 上下文效率更高，agent 按需分 flash/pro |
| 9 | 差值图表用 PivotTable PageField 替代静态多图表 | openpyxl 无 Slicer API，PageField 下拉功能等价，用户可右键 PivotTable → 插入切片器转换 |

## Model routing configuration (final)

```
~/.claude/settings.json env:
  ANTHROPIC_MODEL = deepseek-v4-pro              (主会话)
  ANTHROPIC_DEFAULT_OPUS_MODEL = deepseek-v4-pro (L3 agent)
  ANTHROPIC_DEFAULT_SONNET_MODEL = deepseek-v4-flash
  ANTHROPIC_DEFAULT_HAIKU_MODEL = deepseek-v4-flash (L2 agent)
  ANTHROPIC_BASE_URL = https://api.deepseek.com/anthropic (直连)
  ⚠️ 不能设 CLAUDE_CODE_SUBAGENT_MODEL
```

| 级别 | 模型 | Agent |
|------|------|-------|
| L1 | pro (主会话) | 不 spawn |
| L2 | pro (主会话) | 不 spawn |
| L3 | haiku→flash / opus→pro | spawn agent |

## Synced to ARM

- `~/.claude/CLAUDE.md` — 全局规则(含路由)
- `~/.claude/settings.json` — 模型配置
- `~/.claude/projects/` — 所有项目记忆
- `~/.paseo/config.json` — Paseo daemon 配置(对齐 WSL)
- `~/projects/antenna-post-processor/` — 项目 CLAUDE.md + settings.json
- Memory: `task-based-agent-routing.md` 从天线项目移至网络项目

## Files changed (all sessions, cumulative)

| File | Change |
|------|--------|
| `ui/main_window.py` | 天线参数内联/执行栏分栏/菜单/按钮对齐 |
| `ui/pages.py` | 角度弹窗重写/输入输出分栏/差值复选框 |
| `ui/widgets.py` | OutputSettingsGroup set_directory |
| `src/worker.py` | 步进差值比较表+图表 (_add_diff_sheet) |
| `src/exporter.py` | 图表X/Y轴自动刻度/标记颜色/smooth |
| `src/column_mapping.py` | LAG正则修复 |
| `config/column_patterns.json` | LAG前缀正则 |
| `ui/theme_manager.py` | qt-material → Fusion+QPalette |
| `ui/window_manager.py` | 窗口列表+关闭按钮 |
| `ui/graph_viewer.py` | 移除硬编码灰字color |
| `~/.claude/CLAUDE.md` | Agent分级路由规则 |
| `~/.claude/settings.json` | 模型配置(直连DeepSeek, per-tier路由) |

## Verification

| Check | Result |
|-------|--------|
| Core tests (30) | 30/30 ✅ |
| E2E features (24) | 24/24 ✅ |
| GUI integrity (G1-G9) | 8/9 ✅ |
| Agent routing (haiku→flash, opus→pro) | ✅ 已验证 |

## Open issues

- Edit 工具对含 Unicode 文件首次匹配总失败, 需直接用 Bash+Python

## Discarded (noise)
- CC Switch 代理路由尝试: 不是必须的, Claude Code 自带路由
- agent frontmatter model=haiku 测试: 被 CLAUDE_CODE_SUBAGENT_MODEL 覆盖, frontmatter model 无效
- Agent 的 model 参数测试(sonnet/opus/haiku): 被 CLAUDE_CODE_SUBAGENT_MODEL 全部转为 pro
- `unset CLAUDE_CODE_SUBAGENT_MODEL` 无效: 运行时环境在会话启动时固化
