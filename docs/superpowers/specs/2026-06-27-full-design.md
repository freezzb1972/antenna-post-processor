# Antenna Post-Processor — 完整设计文档

**日期:** 2026-06-27
**最近提交:** `e007d10` feat: PlotConfigDialog折叠展开功能

---

## 一、架构设计

### 1.1 分层架构

```
┌─────────────────────────────────────────────────────┐
│                    UI 层 (ui/)                       │
│  main_window.py  dialogs.py  template_recognizer.py  │
│  graph_viewer.py  window_manager.py                 │
├─────────────────────────────────────────────────────┤
│                 公共模块 (src/)                       │
│  column_mapping.py  — 统一列头分类/预设管理           │
│  word_reporter.py   — Word 报告输出引擎              │
│  excel_reader.py    — Excel 模板解析                  │
│  worker.py          — 异步处理 + 多步进并行           │
│  pipeline.py        — 计算管线                        │
├─────────────────────────────────────────────────────┤
│                  数据层 (src/)                        │
│  datasource.py     — DataSource 接口 + Resampled     │
│  parser.py         — CSV 解析                        │
│  calculator.py     — 核心算法 (Gain/Dir/Eff/LAG/AR)  │
│  exporter.py       — Excel 模板填充                  │
├─────────────────────────────────────────────────────┤
│                  配置 (config/)                       │
│  column_patterns.json  — 列头规则 (唯一主规则源)      │
│  full_report_columns.json — 报告列定义                │
│  templates.json        — 模板预设                     │
└─────────────────────────────────────────────────────┘
```

**设计意图:** 逻辑与界面强制分离。`src/` 层绝对纯净（不 import PySide6），输入输出只用标准类型 + 文件路径，进度通过回调。未来可平滑替换 GUI 框架（如换 C# WPF 只需重写 `ui/` 层）。

---

## 二、多窗口架构

### 2.1 设计决策

**问题:** 用户需要同时处理多个计算任务、对比不同数据源的结果。

**候选方案:**
| 方案 | 描述 | 结论 |
|------|------|------|
| A | 启动器面板 + 独立工作窗口 | ❌ 单任务时需开两个窗口 |
| B | Tab 脱离模式 | ❌ 窗口之间共享数据，不独立 |
| C | **主窗口即首窗口 + Ctrl+N 新建** | ✅ 选此方案 |

**最终选择 (C):**
- 首次启动 = 一个窗口，和之前完全一样
- Ctrl+N / 文件→新建窗口 → 创建独立 QMainWindow
- 关闭最后窗口不退出 App (`setQuitOnLastWindowClosed(False)`)
- 每个窗口有独立的文件设置、参数结果、图形展示、Worker 线程

### 2.2 菜单重组

```
之前: 文件 | 设置 | 处理 | 工具 | 帮助
之后: 文件 | 窗口 | 工具 | 帮助
```

- **移除**「设置」和「处理」菜单 — 所有设置项移入窗口内的参数设置区
- **新增**「窗口」菜单 — 新建窗口 + 窗口清单（点击切换/✕关闭）
- **文件**菜单 — 新建窗口/系统设置/保存结果/关闭窗口

### 2.3 取舍理由

| 取舍 | 选择 | 理由 |
|------|------|------|
| 窗口隔离 vs 资源共享 | 完全隔离 | 避免陈旧数据污染，每个 worker 独立 |
| quitOnLastWindowClosed | False | 关了所有窗口仍可以 Ctrl+N |
| WindowManager | 单例 Observer | 统一管理窗口生命周期和菜单同步 |

---

## 三、工具菜单重构

### 3.1 设计决策

**问题:** 5 个工具全用向导式（弹窗套弹窗），用户反馈"不知道要点多少次"。

**候选方案:**
| 方案 | 描述 |
|------|------|
| 向导式 | 每步一个弹窗，用户一路 Next |
| **二级窗体式** | 一个对话框，所有设置一目了然，一键执行 ✅ |

**改动:**
| 工具 | 原弹窗数 | 现风格 |
|------|---------|--------|
| 数据合并 | 14 次 | MergeDialog — 选文件+RSP校准+输出 一个窗 |
| 数据检查+转换 | 12 次 | BatchCalibrateDialog — 三合一 |
| 路径损耗补偿 | 10 次 | 同上统一窗 |
| 步进重采样 | Comma输入 | Checkbox多选+预览表+自定义输入 |
| 数据修复 | 双弹窗 | RepairDialog — 文件+模式一个窗 |

### 3.2 取舍理由

- 减少了约 300 行 `QMessageBox.question/warning` 代码
- 用户操作路径: `点击菜单 → 一个窗体 → 调整 → 执行`，不需要在弹窗间跳转
- 与 EMQuest 的设计理念一致：一个对话框完成所有设置

---

## 四、多步进同时计算

### 4.1 算法设计

**问题:** 用户想从同一源文件同时提取多个步进（2°, 5°, 10°...）的数据并计算。

**核心创新 — ResampledDataSource:**
```python
class ResampledDataSource(DataSource):
    """零拷贝步进重采样 — numpy stride view，不分配新内存。"""
    def read_sections(self, freq_index):
        data = self._base.read_sections(freq_index)  # 只读一次
        return {k: arr[::stride, ::stride] for k, arr in data.items()}  # view
```

### 4.2 性能目标

| 指标 | 串行 (之前) | 并行 (现在) | 加速比 |
|------|-----------|-----------|--------|
| 3 个步进 | 3×单步进时间 | ~1.2×单步进时间 | ~2.5x |
| 6 个步进 | 6×单步进时间 | ~1.5×单步进时间 | ~4x |

### 4.3 并行度适配

```python
cpu_count = os.cpu_count() or 2
max_workers = max(1, min(len(tasks), cpu_count - 1, 6))
```

| CPU | 并行线程 |
|-----|---------|
| 1-2 核 | 1 (串行) |
| 4 核 | 3 线程 |
| 8+ 核 | 最多 6 线程 |

自动适配，无需用户配置。

### 4.4 取舍理由

- **ThreadPoolExecutor vs multiprocessing:** 选线程。NumPy 运算释放 GIL，真正的多核加速。进程开销更大且通信复杂。
- **临时文件合并 vs 内存合并:** 选临时文件。各步进独立写入临时 .xlsx，最后合并到一个 workbook。避免跨线程共享复杂状态。
- **max_workers 上限 6:** 再多线程收益递减（瓶颈在 NumPy + Excel 写入）。

---

## 五、列头规则统一管理

### 5.1 设计决策

**问题:** 规则散落在三处 — `excel_reader.py` 硬编码、`column_patterns.json` 关键词、`column_mapping.py` 精简版。用户新增列头只能改代码。

**方案演进:**
| 阶段 | 规则源 | 用户可编辑? |
|------|--------|-----------|
| 之前 | 内置函数为主，JSON 为补充 | ❌ 改不了 |
| V1 | JSON 优先，内置保底 | ⚠ 可以但得手动写 JSON |
| **V2** | **JSON 为唯一主规则源 + GUI 自动学习** | ✅ 下拉改类型→点保存 |

### 5.2 自动学习流程

```
用户打开模板识别工具
  → 加载模板，自动识别列头
  → 未识别的列 → 手动下拉选类型
  → 点「💾 保存」
      → 自动从列头文本提取关键词
      → 自动推断 negate 排除词
      → 写入 column_patterns.json (builtin: false, 高优先级)
      → 下次同类列头自动识别 ✅
```

### 5.3 规则匹配优先级

JSON 顺序 = 优先级，先匹配者胜。每条规则支持四种匹配：
1. **regex** — 正则匹配（用于 LAG/AR 等复杂模式）
2. **exact** — 精确匹配 compact form
3. **keywords** — 所有关键词都出现 (AND)
4. **negate** — 排除规则（命中则跳过本条）

### 5.4 取舍理由

- **关键词 AND 而非 OR:** OR 导致 "db" 关键词命中所有带 "dB" 的列头（如 Efficiency(dB)、TRP(dB)），误识别率过高。
- **内置函数保留保底:** JSON 覆盖 95%+ 场景，剩余 3 个边缘 case（如 `Tot. Rad. Pwr.` 缩写）由内置函数兜底。
- **builtin:true/false 标记:** 用户规则优先。内置规则随 App 分发。JSON 可独立分享，无需重新打包。

---

## 六、分类引擎统一

### 6.1 之前的问题

三个文件维护了三套相似但不完全一致的分分类逻辑：
- `template_recognizer.py:_classify()` — 81 行完整链
- `column_mapping.py:_classify_full_static()` — 40 行精简版
- `excel_reader.py:_parse_sheet()` — 行内硬编码

### 6.2 统一后

```python
# src/column_mapping.py
def classify_header(raw_header: str) -> str:
    """统一入口：JSON 优先 → 内置函数 → regex 保底"""
```

调用者：
- `template_recognizer._classify()` — 81行 → 3行调用
- `_detect_excel_columns()` — 简化，复用
- `chart_config._classify_column_text()` — 可复用

---

## 七、Word 报告输出引擎

### 7.1 定位方法设计

**问题:** Word 是流式文档，不像 Excel 有固定网格。如何准确填入数据和图片？

**四层定位策略（优先级:精确度）:**

| 方法 | 精度 | 用户操作 | 适用 |
|------|------|---------|------|
| **内容控件(SDT)** | 精确 | 插入控件设 tag 名 | 单值 |
| **书签** | 精确 | 插入书签命名 | 图片插入 |
| **表格列头** | 自动 | 画表格写列头名 | 数据表 |
| **{{占位符}}** | 文本 | 直接写进段落 | 段落内数值 |

### 7.2 为什么要内容控件而非 Word 域

| 方式 | 优点 | 缺点 |
|------|------|------|
| Word `{ MERGEFIELD }` | Word 原生 | 需要数据库连接，python-docx 操作复杂 |
| Word `{ DOCVARIABLE }` | 简单 | F9 刷新后才能看到值 |
| **内容控件 (SDT)** | **精确边界，python-docx可操作** | 需 Word 2013+ |
| 书签 | 稳定 | 容易被编辑破坏 |

选择内容控件 + 书签的混合方案。内容控件用于精确单值填充，书签用于图片定位。

### 7.3 自动行扩展

```python
while len(table.rows) <= row_idx:
    table.add_row()
```

不限行数，数据 N 行自动生成 N 行。与 Excel 行为一致。

### 7.4 取舍理由

- **python-docx 而非手动写 XML:** python-docx 抽象了 90% 的 OOXML 复杂性，只有内容控件和书签操作需要直触 XML。
- **tempfile + add_picture() 而非手构 XML:** add_picture 是 python-docx 内建方法，生成的 XML 稳定。手构 XML 容易遗漏命名空间或属性导致 Word 报错。

---

## 八、测试报告预览

### 8.1 设计意图

让用户在运行计算之前能看到模板列头识别结果，并修正。

**GUI 位置:** 文件设置区 →「📋 测试报告预览」可折叠面板

```
模板: [...] [浏览] [🔍 识别列头]
┌── 列映射表 ──────────────────────┐
│ A  Frequency     → 频率    [▾]  │
│ B  Peak Gain     → 峰值增益 [▾]  │
│ C  ???           → 未知    [▾]  │ ← 用户下拉修正
└────────────────────────────────┘
[💾 保存为模板预设]
```

---

## 九、GUI 更新目标

### 9.1 已完成

| 更新 | 目的 |
|------|------|
| 单行工具栏 | 减少工具栏行数，常用功能保留，不常用的进 ⚙ 设置对话框 |
| 工具二级窗体 | 替换向导式弹窗，一个窗体完成所有设置 |
| 报告预览面板 | 运行前确认列映射 |
| 分类折叠展开 | 减少图形配置面板高度 |
| i18n 全覆盖 | 266条 zh_CN + 256条 en_US 翻译 |

### 9.2 原则

- **控件可见性优先:** 宁可折叠/展开也不把功能藏进深层菜单
- **一个任务一个窗体:** 工具类功能统一用 `ToolDialog` 模式
- **预览 > 执行:** 运行前让用户看到将要发生的事情（列映射、文件预览、步进预览）

---

## 十、模型路由配置

### 10.1 Paseo 配置 (`~/.paseo/config.json`)

```json
{
  "agents": {
    "providers": {
      "claude": {
        "env": {
          "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-pro",
          "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-flash",
          "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-v4-flash",
          "CLAUDE_CODE_DISABLE_CLASSIFIER": "false"
        }
      }
    }
  }
}
```

### 10.2 路由策略

| 任务难度 | Tier | 模型 | 成本 |
|---------|------|------|------|
| 简单 (grep/read/小edit) | Haiku | flash | 💰 低 |
| 中等 (调试/小功能) | Sonnet | flash | 💰 低 |
| 复杂 (架构/设计/大重构) | Opus | v4-pro | 💰💰 高 |

---

## 十一、项目约束

- `src/` 层禁止 import PySide6
- 所有计算值 `round(val, 6)`
- 新配置保存到外部 JSON 文件（不写入 EXE）
- 所有 UI 文本必须用 `self.tr()` 包裹
  - 新增 UI 后需: `pyside6-lupdate` → 翻译 → `pyside6-lrelease`
