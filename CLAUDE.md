# CLAUDE.md

## 项目：天线参数后处理程序 (Antenna Post-Processor)

从 EMQuest 天线测试数据计算 Gain/Directivity/Efficiency/LAG/Axial Ratio，填入 Excel 模板。

### 当前状态 (2026-06-21)

**已完成**: 多数据源+工作表自动匹配、Theta 外推开关、6位小数精度、进度条实时更新、
GUI 完整验证 (71/71 测试通过, 0 skipped)、USER_GUIDE.html 14章完整文档、
AR 计算修复 (移除 clipping)、模板预设管理系统、启动闪屏、图表开关统一、字体缩放修复、
统一配置管理 (antenna_config.json)、30天试用系统 (HMAC + 4层冗余)、
图表子选择 (Gain/AR 多曲线+角度弹窗)、增强3D查看器 (旋转预设+色图+导出)、
Excel 图表平滑曲线 + 轴标签修复、角度弹窗 UX 修复 (add/delete 不关闭对话框)。

**验证清单**: `verify-manifest.json` — 27 特性, 26 verified (96%), 1 partial (nf2ff 待标定数据)。
  Manifest 自动维护规则见 verify-py skill (Phase 0), 对所有项目通用。

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

### 陈旧数据防护（2026-06-23 审计总结）

**陈旧数据 bug 比崩溃更危险** — 第一次运行正确，用户误以为功能正常，但第二次运行会悄悄混入第一次的数据。

#### 五类反模式（代码审查必须检查）

| # | 反模式 | 检测信号 | 修复方式 |
|---|--------|---------|---------|
| 1 | **懒初始化一次后不刷新** | `if self._x is None: init` 无对应的重置为 `None` | 在状态变更点（换模板、清文件）重置为 `None` |
| 2 | **找到已存在对象直接返回** | `find existing → return` 无 update | 若存在则更新数据，或删除后重建 |
| 3 | **忘记设标志位** | 状态三元组 (True/False/未设置) | 构造函数设初始值，所有分支检查 |
| 4 | **同名状态变量不同步** | `_mode` / `_test_mode` / `_current_mode` | 单一数据源，其他只读代理 |
| 5 | **异常路径跳过清理** | 资源获取/释放之间无 `try/finally` | 始终用 `try/finally` 保护 close/disconnect |

#### 必检场景

修改以下方法时，强制问自己 3 个问题：
- **load / refresh / update**: 新数据会完全覆盖旧状态吗？（检查 `clear()` 是否在所有分支）
- **browse / select**: 路径变化后，依赖该路径的所有缓存都失效了吗？
- **error handler**: 异常路径是否设置了 `_data_stale` / 执行了 cleanup？

#### 自动化防线

```bash
# 双次运行一致性测试 — 最直接的陈旧数据检测
python3 -m pytest tests/test_e2e_features.py::TestStaleDataProtection -v
```

### 开发工作流（自动编排）

使用 `/dev-flow` 编排器自动协调 23 个技能，按照 6 阶段工作流推进：

```
DESIGN → PLAN → DEVELOP → VERIFY → COMMIT → MANAGE
```

| 命令 | 作用 |
|------|------|
| `/dev-flow start` | 开始新功能（→ DESIGN 阶段） |
| `/dev-flow next` | 推进到下一阶段 |
| `/dev-flow check` | 运行当前阶段质量检查 |
| `/dev-flow status` | 查看当前状态 |

**自动钩子**（已配置在 `.claude/settings.json`）：
- Edit/Write 累计 ≥5 次 → 建议运行 `/dev-flow check`
- 修改 `ui/*.py` → 提醒运行 `gui-check`
- 修改 `*.spec` → 提醒运行 `size-gate`
- pytest 运行后 → 自动更新统计
- PreCompact → 自动检测 distill-vs-compact 时序; 未 distill 则阻塞, Claude 自动 distill 后放行

**状态文件**：`.claude/dev-flow.json`（跟踪阶段、文件修改计数、检查点计数）

### 质量门禁（自动触发）

修改以下文件后，**必须**运行对应的 harness。Harness 已内置在项目中，
对**任意 Python 项目**使用 `--init` 可生成项目配置，之后自动适配。

| 触发文件 | Skill | 命令 |
|---------|-------|------|
| `ui/main_window.py` | `/gui-check` | `python3 gui_integrity_check.py` |
| `ui/compiled/ui_main_window.py` | `/gui-check` | `python3 gui_integrity_check.py` |
| `*.spec` | `/size-gate` | `python3 build_size_gate.py --spec-only` |
| PyInstaller 构建后 | `/size-gate` | `python3 build_size_gate.py` |
| 任何 `.py` 变更 | E2E | `python3 _e2e_verify.py` |

### Agent 自动行为规则（本会话生效，跨会话 CLAUDE.md 加载后生效）

以下规则告诉 Claude Code agent **在每次 Edit/Write 操作后自动执行**，
无需用户明确指令。用户只提需求，agent 自动完成全流程。

#### A. 自动质量门禁

| 触发条件 | 自动执行 |
|---------|---------|
| 修改了 `ui/*.py` 或 `ui/dialogs.py` | `python3 gui_integrity_check.py` |
| 修改了任何 `.py` 文件 | `python3 -m pytest tests/ -q -x` (后台运行) |
| 修改了 `src/pipeline.py` | `python3 -m pytest tests/ -q -x -k "e2e or pipeline"` |
| 新增/修改 UI 控件 | `/gui-audit` — 检查控件是否可见/被裁剪/布局正确 |

#### B. 自动开发流程

| 用户行为 | Agent 自动响应 |
|---------|---------------|
| 提出新功能需求 | → 自动 `EnterPlanMode`, 设计后请求批准 |
| 需求模糊/有多种方案 | → 自动 `AskUserQuestion` 澄清 |
| 写完代码 | → 自动运行质量门禁 → 通过后 `git commit` |
| 对话结束前 | → 自动 `git status` 检查遗漏文件 |

#### C. 代码审查自动检查（每次写代码前自查）

| 检查项 | 方法 |
|--------|------|
| 陈旧数据: 新修改的方法是否正确清理旧状态? | 对照 Claude.md 五类反模式 |
| 双 UI 同步: 是否新增了只在一边存在的控件? | grep 关键属性名两边对比 |
| 隐藏元素: 是否新增了 `setVisible(False)` 或 `hide()`? | 必须写理由 |

#### D. 禁止行为

- ❌ 不自动 `pyinstaller` 打包 (需等用户确认)
- ❌ 不跳过质量门禁直接提交
- ❌ 修改超过 3 个文件不先写计划

#### E. 会话管理

| 触发条件 | 自动执行 |
|---------|---------|
| **每次 `git commit` 后** | 检查是否需要更新 `CURRENT_STATE.md`（新增 ≥3 个 commits 则更新） |
| **累计 Edit/Write ≥ 30 次** (本会话) | suggest-compact.js 提示考虑 compact |
| **累计 Edit/Write ≥ 60 次** (本会话) | suggest-compact.js 提示 distill + compact |
| **累计 Edit/Write ≥ 120 次** (本会话) | suggest-compact.js 严重警告 |
| **解决问题消耗 > 5 轮尝试** | 自动 distill，防止噪声积累 |
| **用户说 "好了/可以了/完成"** | 检查 `git status`，确保没有遗漏文件 |
| **PreCompact hook 被阻止 (exit 2)** | 自动运行 `/distill-session` → 下次压缩自动放行 |

> **注意**: Agent 无法直接读取上下文使用率。用 project `.claude/.compact_counter` 的 Edit/Write 次数代替（session-aware: 2h 无活动自动重置）。
> **PreCompact 自动 distill 流程 (ticket 模型)**: distill → touch `.claude/.distill-done` (发通行证) → PreCompact hook 消费通行证 (rm) → 放行 → 下次 compact 无通行证 → exit 2 阻止 → Claude auto-distill → 发新通行证 → 放行。
> **distill-session skill**: Step 3 结束后必须 `touch .claude/.distill-done` 发通行证。

对**任意 Python 项目**使用这些 skill：
```bash
# 初始化（首次）
python3 ~/.claude/global-skills/python/gui-check/gui_integrity_check.py --init    # 生成 .gui-check.json
python3 ~/.claude/global-skills/python/size-gate/build_size_gate.py --init        # 生成 .size-gate.json
# 编辑 .gui-check.json / .size-gate.json 定制规则
# 正常运行
python3 ~/.claude/global-skills/python/gui-check/gui_integrity_check.py
python3 ~/.claude/global-skills/python/size-gate/build_size_gate.py --spec-only
```

### 技能管理体系（三阶架构）

本项目使用 **三阶技能体系**：`~/.claude/global-skills/` 集中管理所有技能，项目 `.claude/skills/` 纯软链按需加载。

```
全局 ~/.claude/skills/          ← 5 个通用技能（跨项目自动加载）
  browse, careful, context-save, context-restore, init-project

全局 ~/.claude/global-skills/   ← 90+ 技能集中管理（7 个分类）
  superpowers/ (26)  everything/ (45)  python/ (3)
  network/ (5)        homelab/ (5)     security/ (2)
  misc/ (26)

本项目 .claude/skills/          ← 按需软链 23 个
  通过 /dev-flow 自动编排调用
```

| 层 | 位置 | 加载方式 |
|---|------|---------|
| **核心** | `~/.claude/skills/` | 全局自动加载（4个通用技能） |
| **库** | `~/.claude/global-skills/` | 集中管理，项目按需软链 |
| **项目** | `.claude/skills/` | 纯软链，声明项目依赖 |

钩子路径已统一更新为 `~/.claude/global-skills/...`，插件（claude-api）通过 `enabledPlugins` 控制。

新项目初始化：使用 `/init-project` 引导讨论 → 自动匹配 → 配置技能/插件/MCP。

### 验证命令

```bash
# 测试
python3 -m pytest tests/ -q

# GUI 完整性
python3 gui_integrity_check.py

# 体积门禁
python3 build_size_gate.py

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
