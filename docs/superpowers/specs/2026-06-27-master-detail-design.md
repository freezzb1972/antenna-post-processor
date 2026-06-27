# UI 重构设计：Master-Detail 参数设置

**日期:** 2026-06-27
**基于 ARM 设计意图:** `docs/superpowers/specs/2026-06-27-full-design.md`

---

## 一、背景与问题

ARM 合并后，`tabConfig` 有 5 个可见标签页：
- 文件设置（塞满参数概览、频点、算法、多步进、报告预览）
- LAG 参数配置（与 CalcParamsDialog 功能重复）
- 3D 图形（与 PlotConfigDialog 功能重复）
- 参数结果
- 图形展示

加上空壳 tabCalc（已移除），共 6 个模块。ARM 设计文档的意图是把所有设置归入一个"参数设置"主标签页，但实现未完成。

**核心问题：** 同样的角度配置在 tabLag 和 CalcParamsDialog 各实现了一遍，图形配置在 tabPlot 和 PlotConfigDialog 各实现了一遍，用户需要在多处操作同一份数据，状态不同步。

---

## 二、目标

```
5 标签页 → 3 标签页 (处理设置 / 计算结果 / 图表查看)
Master-Detail 布局: 左侧导航 (固定) + 右侧 QStackedWidget (3页切换) + 底部执行栏 (共享)
只保留一套角度配置、一套图形配置
所有 UI 文本 self.tr() 包裹，中英文完整切换
```

---

## 三、最终布局

```
┌─ QTabWidget: 3 标签页 ───────────────────────────────────────────┐
│ 📐 处理设置  │  📊 计算结果  │  📈 图表查看                        │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ 左侧导航 (固定 ~140px) ─┬─ 右侧内容 (QStackedWidget) ────────┐│
│  │                          │                                     ││
│  │ ▸ 📂 输入输出            │ page[0]: FileSettingsPage          ││
│  │                          │ ┌ 模板文件 ─────────────────────┐  ││
│  │   📡 天线参数            │ │ 模板: [path] [浏览] [📋 预览] │  ││
│  │                          │ │ 来源: [内置模板▾] [从电脑选择] │  ││
│  │   📊 图表配置            │ └────────────────────────────────┘  ││
│  │                          │ ┌ 数据文件 ─────────────────────┐  ││
│  │                          │ │ [添加文件][清除选中][全部清除] │  ││
│  │                          │ │ [文件列表 table]              │  ││
│  │                          │ │ [匹配表 table]                │  ││
│  │                          │ │ [自动匹配] 命名:[▾]          │  ││
│  │                          │ │ ☑ 效率曲线 ☑ 增益曲线        │  ││
│  │                          │ └────────────────────────────────┘  ││
│  │                          │ ┌ 输出设置 ─────────────────────┐  ││
│  │                          │ │ 目录: [path] [浏览]          │  ││
│  │                          │ │ 文件名: [name]               │  ││
│  │                          │ │ ☑ 保存任务包 (.ant)         │  ││
│  │                          │ │   💡 下次双击秒开，不重算   │  ││
│  │                          │ │ ☐ 完整报告: [path] [浏览]    │  ││
│  │                          │ └────────────────────────────────┘  ││
│  │                          │                                     ││
│  │                          │ page[1]: AntennaParamsPage          ││
│  │                          │ (原 CalcParamsDialog → QWidget)     ││
│  │                          │ - 测试模式选择 (无源/TRP/TIS)       ││
│  │                          │ - 参数组勾选 (报告 + full_report)   ││
│  │                          │ - Gain 角度 (AnglePickerWidget)     ││
│  │                          │ - AR 角度 (AnglePickerWidget)       ││
│  │                          │ - 频点设置 + 算法选项                ││
│  │                          │ - 多步进选择                         ││
│  │                          │                                     ││
│  │                          │ page[2]: ChartSettingsPage           ││
│  │                          │ (原 PlotConfigDialog → QWidget)     ││
│  │                          │ - 图表类别选择 (3类可折叠)           ││
│  │                          │ - 视角参数 (仰角/方位角/DPI)         ││
│  │                          │ - 输出方式 (嵌入Excel/保存PNG)       ││
│  └──────────────────────────┴─────────────────────────────────────┘│
│                                                                   │
│  ┌─ 底部执行栏 (固定，所有页面共享) ──────────────────────────────┐│
│  │ [==================进度条==================] 处理中...          ││
│  │ [日志输出区                                        ]          ││
│  │                                   [▶ 开始处理] [⏹ 停止]       ││
│  └───────────────────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────────────────┘
```

---

## 四、命名规范

| 原名称 | 新名称 | 说明 |
|--------|--------|------|
| tabConfig 第0个: 文件设置 | 📐 处理设置 | Process Settings |
| tabConfig 第1个: 参数结果 | 📊 计算结果 | Calculation Results |
| tabConfig 第2个: 图形展示 | 📈 图表查看 | Chart Viewer |
| 左侧导航项1 | 📂 输入输出 | Input/Output |
| 左侧导航项2 | 📡 天线参数 | Antenna Parameters |
| 左侧导航项3 | 📊 图表配置 | Chart Configuration |
| CalcParamsDialog | AntennaParamsPage (QWidget) | 嵌入右侧面板 |
| PlotConfigDialog | ChartSettingsPage (QWidget) | 嵌入右侧面板 |

**i18n:** 所有标题用 `self.tr()` 包裹，emoji 仅在中文模式下显示（通过 i18n 翻译控制）。

---

## 五、任务文件 .ant（可选存档）

### 5.1 设计目的
计算完成后可选保存 `.ant` 任务包，下次双击秒开看结果，避免重算。`☑ 保存任务包` 复选框默认勾选，用户可按需取消以节省磁盘空间。

### 5.2 文件格式
`.ant` = ZIP 包，包含：
```
task_5G1_20260627.ant
├─ task.json         元数据 + 配置快照 + 计算结果
├─ data/             原始数据文件副本
│   ├─ 5G1_merged.csv
│   └─ 5G1_FS.xlsx
└─ template/         模板副本
    └─ template_5G1.xlsx
```

### 5.3 打开方式
```
Shell 启动页:
┌────────────────────────────────────┐
│  最近任务                          │
│  ├ task_5G1_20260627.ant  昨天    │
│  ├ Calibration.ant        6/25    │
│  └ ...                             │
│  [📂 打开任务包...] [🆕 新建任务]  │
└────────────────────────────────────┘
```

打开 `.ant` 后：
- 原始数据未变（hash 校验）→ 直接显示缓存结果
- 原始数据已变 → 提示 "原始数据已更新，是否重新计算？"
- 原始数据缺失 → 提示 "数据文件已移动，请查找"

### 5.4 与报告的关系
- `.ant` 自包含（单文件，不丢失关联）
- 测试报告 `antenna_report.xlsx` 仍单独保存（发给客户用）
- 原始 CSV/Excel 文件不受影响

### 5.5 成本节省
| 操作 | 无 .ant | 有 .ant | 节省 |
|------|---------|---------|------|
| 打开上次任务 | 选文件+配置+计算 2~3min | 双击 2s | ~100% |
| 客户要看上次报告数据 | 重算 2min | 双击 2s | ~100% |
| 对比两个任务结果 | 两窗口重算 4min | 双击两个 2s | ~100% |

---

## 六、组件树

```
MainWindow (QMainWindow)
└─ tabConfig (QTabWidget, 3 tabs)
   ├─ tab[0]: "处理设置" ← Master-Detail 新布局
   │   ├─ QHBoxLayout (左右分栏)
   │   │   ├─ navList (QListWidget, fixed width ~140px)
   │   │   │   ├─ "输入输出"
   │   │   │   ├─ "天线参数"
   │   │   │   └─ "图表配置"
   │   │   └─ pageStack (QStackedWidget, stretch=1)
   │   │       ├─ FileSettingsPage   (QWidget, 索引 0)
   │   │       ├─ AntennaParamsPage  (QWidget, 索引 1)
   │   │       └─ ChartSettingsPage  (QWidget, 索引 2)
   │   └─ executionBar (QWidget, fixed bottom)
   │       ├─ progressBar + lblProgressMsg
   │       ├─ logOutput (QPlainTextEdit)
   │       └─ btnStart + btnStop
   ├─ tab[1]: "计算结果" ← 保持现有 tabResults
   └─ tab[2]: "图表查看" ← 保持现有 tabCharts
```

**删除:** tabLag, tabPlot, tabCalc（及其内所有 widget）

---

## 七、数据流

```
                    MainWindow (数据 Owner)
                    ┌────────────────────────────────┐
                    │ _required_params (set)          │ ← 报告必需参数
                    │ _extra_params (set)             │ ← full_report 额外
                    │ _lag_config (LagConfig)         │ ← LAG 角度
                    │ _ar_lag_config (LagConfig)      │ ← AR 角度
                    │ _test_mode (int: 0/1/2)         │ ← 测试模式
                    │ _freq_source (str)              │ ← 频点来源
                    │ _trim_start/end (int)           │ ← 去除频点
                    │ _extrapolate (bool)             │ ← Theta外推
                    │ _robust_peak (bool)             │ ← 鲁棒峰值
                    │ _ar_output_db (bool)            │ ← AR输出格式
                    │ _step_values (List[float])      │ ← 多步进
                    │ _skip_original (bool)           │ ← 跳过原始
                    │ _chart_config_required/extra    │ ← 图表配置
                    │ _plot_elev/_azim/_dpi (float)   │ ← 视角参数
                    │ _embed_in_excel (bool)          │ ← 嵌入Excel
                    │ _save_png (bool)                │ ← 保存PNG
                    │ _template_path (str)            │ ← 模板路径
                    │ _data_file_paths (list)         │ ← 数据文件
                    │ _output_dir/_output_name (str)  │ ← 输出
                    │ _mode_states (list[dict])       │ ← 三模式独立状态
                    └───────┬────────────────────────┘
                            │ 实时读写 + Qt Signals
               ┌────────────┼────────────────────┐
               ▼            ▼                    ▼
         FileSettings  AntennaParams       ChartSettings
            Page          Page                Page
         (输入输出)    (天线参数)          (图表配置)

双向同步: 预览处 ≡ AntennaParamsPage (通过 MainWindow 属性中转)
          _required_params 同步
          _extra_params 仅在 AntennaParamsPage 配置

底部状态: _update_param_summary() 聚合所有属性 → 冻结摘要显示
执行:    _on_start() 读取所有属性 → run_pipeline()
```

**同步规则:**
1. 每个 Page 直接读写 `self.window()._xxx` 属性
2. 写属性后 emit 信号 → 其他 Page 感知变化自动刷新
3. 报告预览处改 `_required_params` → emit → AntennaParamsPage 自动更新
4. full_report (`_extra_params`) 仅在 AntennaParamsPage 配置

---

## 八、公共模块提取

### `src/ui_utils.py` (新建 — 零 Qt 依赖)

```
build_param_summary_text(mode, required, extra, lag_cfg, ar_cfg) → str
  构建天线参数摘要字符串
  调用者: MainWindow._update_param_summary, 三个Page的状态栏

merge_params_from_columns(column_types: set) → set
  从模板列类型推断需要的计算参数
  调用者: 预览处, AntennaParamsPage
```

### `ui/widgets.py` (新建 — 可含 Qt)

```
AnglePickerWidget(QWidget)
  可复用角度选择组件:
  - 快捷单角度按钮 (0~90°, 可选中)
  - 步进批量生成 (起/止/步)
  - 范围添加 (起/止)
  - 已配置项 FlowLayout 标签
  - signal: angle_changed(LagConfig)
  使用: AntennaParamsPage 实例化 2 个 (Gain角度 + AR角度)

TemplateSourceRow(QWidget)
  模板来源选择行: [内置模板 ▾] [从电脑选择...] [📋 预览报告]
  使用: FileSettingsPage, ReportPreviewDialog

OutputSettingsGroup(QGroupBox)
  输出目录 + 文件名 + 完整报告路径
  使用: FileSettingsPage
```

---

## 九、参数体系

| 参数类型 | 配置入口 | 数据属性 | 用途 |
|---------|---------|---------|------|
| 报告必需参数 | 预览处 **AND** AntennaParamsPage | `_required_params` | 填入测试报告模板 |
| full_report 额外参数 | **仅** AntennaParamsPage | `_extra_params` | 实验室人员独立完整报告 |

**同步:** 预览处改参数 → 写 `_required_params` → emit signal → AntennaParamsPage 实时刷新
**隔离:** full_report 只在 AntennaParamsPage 显示和配置，预览处不可见

---

## 十、集成策略 (5 步渐进)

### Step 1 — 建地基（不破坏现有功能）
- 新建 `src/ui_utils.py` + `ui/widgets.py`
- 新增 MainWindow 数据属性
- 新增 `_update_param_summary()`
- 验证: 现有功能不受影响 → `python3 gui_integrity_check.py`

### Step 2 — 抽页面
- 创建 `FileSettingsPage` ← 从 groupInput + `_init_multi_file_ui` + groupOutput 抽
- 创建 `AntennaParamsPage` ← 从 CalcParamsDialog 改 (QDialog → QWidget)
- 创建 `ChartSettingsPage` ← 从 PlotConfigDialog 改 (QDialog → QWidget)
- 验证: 每个 Page 独立可显示

### Step 3 — 搭框架
- `_build_parameter_tab()` 构建 Master-Detail 布局
- `_hide_settings_tabs()` 删除 tabLag/tabPlot/tabCalc
- 只用 3 个标签页
- 验证: GUI 结构正确，导航切换正常 → `python3 gui_integrity_check.py`

### Step 4 — 接数据
- Page 读写 MainWindow 属性 → 实时同步 (无 OK/Cancel)
- 预览处 ↔ AntennaParamsPage 双向同步
- `_on_start()` 从属性读取
- 验证: 设置参数 → 运行 → 结果正确

### Step 5 — 清扫
- 删除废弃方法 (~15个)
- 清理 `_connect_signals` 中的 LAG/Plot 信号
- 更新 `_log_current_params` / `_update_status`
- 验证: `python3 -m pytest tests/ -q -x` + `python3 gui_integrity_check.py`

---

## 十一、Shell + 任务窗口 (Word 风格)

### 11.1 架构决策

采用 Word 风格: Shell 窗口只做管理入口，每个天线任务是一个独立窗口。

```
┌─ Shell (轻量) ───────────┐  ┌─ 任务窗口: '5G1_20260627' ────┐
│ 菜单栏                    │  │ 菜单栏 (精简)                 │
│                           │  │ ┌─ Master-Detail ───────────┐ │
│ 最近任务                  │  │ │ 左导航 │ 右内容          │ │
│ ├ 5G1.ant      昨天      │  │ │ 输入输出│                │ │
│ ├ Calibration.ant 6/25   │  │ │ 天线参数│                │ │
│ └ ...                     │  │ │ 图表配置│                │ │
│                           │  │ └─────────────────────────┘ │
│ [📂 打开任务包...]        │  │ ┌ 底部执行栏 ──────────────┐ │
│ [🆕 新建任务]    Ctrl+N   │  │ │ 进度/日志/[▶开始][⏹停止]│ │
└───────────────────────────┘  │ └─────────────────────────┘ │
                               └─────────────────────────────┘
```

### 11.2 启动行为
- Shell 启动 → 自动新建一个空白任务窗口（直接可用）
- 关闭所有任务窗口 → Shell 退出
- Ctrl+N → 新建任务窗口
- 任务窗口名称 = 模板名+日期（如 `5G1_20260627`）

### 11.3 与现有 WindowManager 的关系
- 复用 ARM 的 `ui/window_manager.py` (单例 Observer)
- Shell = WindowManager 的管理器（控制 quitOnLastWindowClosed）
- 每个任务窗口通过 WindowManager 注册

---

## 十二、模板预设管理整合

### 12.1 现状
- "模板识别..." 独立存在于工具菜单
- "模板预设管理" 可能散落在不同位置
- 功能重复: 都做列头检测 + 预览修正

### 12.2 统一后
```
模板预设管理 (工具菜单唯一入口)
├─ 已保存预设列表 (厂商分组)
├─ [新建识别...] → 打开Excel → 自动检测 → 预览+修正 → 输入厂商/名称 → 保存
├─ [编辑] → 预览修正 → 更新
└─ [删除]

输入输出页面 (快捷入口)
├─ 选定模板 → 自动识别 → 📋 预览 → 人工调整
└─ [保存为模板预设] → 调出保存界面(厂商+名称) → 存入同一位置
```

### 12.3 菜单调整
```
工具 →                          移除独立的"模板识别..."
  ...
  数据修复...
  ───────────────
  模板预设管理...                 ← 唯一入口
  EMQuest 数据导出...
```

### 12.4 技术实现
- 两处调用同一公共函数 (来自 `src/column_mapping.py`)
- 存入同一预设存储 (`config/templates.json` + `config/column_patterns.json`)
- 预览修正调同一 ReportPreviewDialog

---

## 十三、数据修复重构

### 13.1 问题
- 点击"数据修复"可能因 z-order 导致对话框弹到主窗口背后
- RepairDialog 无扫描预览步骤，选文件直接执行修复
- 用户不知道检测出多少坏点、用什么方法修复
- 修复方法存在但不可见（MAD/Q25/KNN/手动）

### 13.2 改造方案
参考 BatchCalibrateDialog 的扫描-预览-执行模式:

```
RepairDialog (新设计)
├─ [📂 添加数据文件...] [清除]
├─ [文件列表]
├─ [🔍 扫描数据质量]              ← 新增扫描按钮
├─ 扫描结果表:                     ← 新增
│   │ 文件 │ 格式 │ 坏点phi数 │ 坏点位置 │ 建议方法 │
│   │ a.csv │ 标准 │ 3个     │ 12,15,18 │ MAD+KNN  │
│   │ b.csv │ 异常 │ 6个     │ 5-10     │ Q25+KNN  │
├─ 修复方法选择:                   ← 新增方法说明
│   ○ MAD 异常检测 — 中位数绝对偏差，适合标准格式
│   ○ Q25 比率检测 — 四分位数比率，适合异常终止格式
│   ○ KNN 插值修复 — 逆距离加权K近邻插值
│   ○ 手动指定 phi — 直接输入需修复的位置
├─ [▶ 执行修复] [关闭]
```

### 13.3 技术实现
- 复用 `src/data_quality.py` 中的 `detect_phi_anomalies()` 做扫描
- `auto_detect_and_repair()` 已有全部逻辑，仅需包装扫描步骤
- 修复 `z-order` 问题: 所有对话框创建后调用 `dlg.raise_()` + `dlg.activateWindow()`

---

## 十四、路径损耗补偿独立

### 14.1 问题
- "数据检查与转换"和"路径损耗补偿"打开同一个 `BatchCalibrateDialog`
- 两个不同的功能用一个对话框，用户困惑

### 14.2 拆分方案

| 工具 | 对话框 | 职责 |
|------|--------|------|
| 数据检查与转换 | BatchCalibrateDialog | 扫描格式 → 显示结果 → Re/Im 转 LogMag |
| 路径损耗补偿 | PathLossDialog (新) | 选文件 + RSP → 检查格式 → 执行补偿 |

### 14.3 PathLossDialog 设计
```
PathLossDialog
├─ 文件选择区
│   ├─ [添加CSV文件...] [清除]
│   └─ [文件列表]
├─ RSP 校准文件
│   ├─ H-pol: [path] [浏览] [从预设选择... ▾]
│   └─ V-pol: [path] [浏览] [从预设选择... ▾]
├─ [🔍 检查兼容性]               ← 扫描: 格式 + 频率覆盖
│   └─ 结果: "3 文件为对数域 ✓ | 1 文件为实部/虚部 ⚠ 需先转换"
├─ 处理选项
│   ├─ ☑ 自动转换实部/虚部文件 (必须先转换为对数域)
│   └─ ☑ 应用路径损耗补偿
├─ [▶ 执行] [关闭]
```

### 14.4 实部/虚部处理逻辑
- RSP 补偿只能对 LogMag/Phase（对数域）做，不能直接对 Re/Im 做
- 发现有 Re/Im 文件 → 勾选"自动转换" → 先 `_to_logmag()` + `_to_phase()` → 再 `apply_path_loss_calibration()`
- 未勾选转换 → 跳过该文件并警告

---

## 十五、RSP 校准预设管理

### 15.1 问题
- RSP 预设管理在"系统设置"中，但它是操作工具而非应用配置
- `RspPickerDialog` 已经写好了但**从未被使用** — 预设和对话框是断开的
- `BatchCalibrateDialog` 和 `MergeDialog` 都用 `QFileDialog` 手动浏览，不走预设

### 15.2 调整
```
系统设置 → 只留: 字体 / 主题 / 语言 / LLM API（纯配置）
RSP 预设管理 → 移到 工具菜单

工具 →
  ...
  模板预设管理...
  校准预设管理...          ← RSP预设（从系统设置移出）
  EMQuest 数据导出...
```

### 15.3 连接预设到对话框
- PathLossDialog 和 MergeDialog 添加 [从预设选择... ▾] 下拉框
- 选中预设后自动填充 H-pol/V-pol 路径
- 复用 `RspPickerDialog` 组件（目前已实现但未使用）

---

## 十六、菜单最终结构

```
文件 →
  新建窗口  Ctrl+N
  ─────────────
  系统设置...
  ─────────────
  保存结果...  Ctrl+S
  ─────────────
  关闭窗口  Ctrl+W

工具 →
  数据检查与转换...        ← 仅格式检测+转换
  路径损耗补偿...          ← 独立对话框 (PathLossDialog)
  数据合并...
  步进重采样...
  ─────────────
  数据修复...              ← 扫描→预览→选方法→执行
  ─────────────
  模板预设管理...           ← 模板识别合并入
  校准预设管理...           ← RSP预设（从系统设置移出）
  ─────────────
  EMQuest 数据导出...

窗口 →
  新建窗口
  ─────────────
  [窗口列表...]

帮助 →
  使用说明  F1
  许可管理...
  关于...
```

**变动:**
- 移除: 文件→LLM智能设置（已在系统设置内）
- 拆分: 数据检查与转换 ≠ 路径损耗补偿（独立对话框）
- 移出: RSP 预设管理（系统设置 → 工具菜单）
- 合并: 模板识别 → 模板预设管理

---

## 十七、国际化 (i18n)

**所有** 标签标题、GUI 标题、菜单标题、状态文本 必须 `self.tr()` 包裹，英文模式零中文。

新增文本来源:
- 标签页标题 (3个)
- 左侧导航项 (3个)
- FileSettingsPage 内部标签 (~20个)
- AntennaParamsPage 内部标签 (~50个)
- ChartSettingsPage 内部标签 (~15个)
- 底部状态栏文本 (~5个)
- 菜单项标题 (4个文件菜单)

**新增字符串后执行:**
```bash
pyside6-lupdate ui/main_window.py ui/widgets.py ui/dialogs.py -ts i18n/app_zh_CN.ts i18n/app_en_US.ts
# 在 en_US.ts 中补充英文翻译
pyside6-lrelease i18n/app_zh_CN.ts -qm i18n/app_zh_CN.qm
pyside6-lrelease i18n/app_en_US.ts -qm i18n/app_en_US.qm
```

---

## 十八、需修改的文件

| 文件 | 改动 | 说明 |
|------|------|------|
| `ui/main_window.py` | **重度重构** | 布局重建、菜单重组、方法增删、信号重连 |
| `ui/dialogs.py` | 重度改动 | CalcParamsDialog→AntennaParamsPage, PlotConfigDialog→ChartSettingsPage, 新增 ReportPreviewDialog, 新增 PathLossDialog, 重构 RepairDialog |
| `ui/widgets.py` | **新建** | 可复用 Qt 组件 (AnglePickerWidget, TemplateSourceRow, OutputSettingsGroup) |
| `src/ui_utils.py` | **新建** | 公共纯函数 |
| `ui/rsp_picker_dialog.py` | 中等改动 | 连接到实际对话框，添加 [从预设选择] 功能 |
| `ui/compiled/ui_main_window.py` | **不改** | 编译 UI 不变 |
| `ui/template_recognizer.py` | 小改 | 整合入模板预设管理 |
| `src/rsp_preset_manager.py` | 小改 | 暴露 API 供对话框调用 |

---

## 十九、验证清单

| # | 验证项 | 方法 |
|---|-------|------|
| 1 | 启动后只有 3 标签页 | 目视 |
| 2 | 左侧导航切换，右侧内容跟随 | 点击三项 |
| 3 | 天线参数页改参数 → _on_start 读到正确值 | 改角度 → 运行 → 检查结果 |
| 4 | 图表配置页改视角 → 图表按新参数生成 | 改 DPI → 运行 → 检查图表 |
| 5 | 预览处改参数 → 天线参数页面自动刷新 | 开预览改 → 切到天线参数页 |
| 6 | full_report 仅在面板可配置 | 预览处看不到 full_report |
| 7 | 底部执行栏始终可见 | 添加多文件 → 底部固定 |
| 8 | 拖拽文件到窗口仍有效 | 拖 CSV 文件到窗口 |
| 9 | 内置模板下拉 + 从电脑选择正常 | 两者各试一次 |
| 10 | 多窗口 (Ctrl+N) 仍正常 | Ctrl+N → 两窗口独立 |
| 11 | 切换英文后无中文 | 切换语言 → 遍历所有页面 |
| 12 | 数据修复: 扫描→显示结果→选方法→执行 | 拿异常CSV测试完整流程 |
| 13 | 路径损耗补偿: 独立对话框 | 检查文件+选RSP+执行补偿 |
| 14 | 路径损耗: Re/Im文件正确提示先转换 | 拿Re/Im文件测试 |
| 15 | RSP预设管理在工具菜单可用 | 打开→创建→选择预设 |
| 16 | RSP预设连接到对话框(路径损耗+合并) | 对话框中选预设→自动填路径 |
| 17 | 文件菜单无LLM智能设置 | 目视 |
| 18 | 图表空状态非白屏 | 启动→切到图表查看标签 |
| 19 | GUI 完整性检查通过 | `python3 gui_integrity_check.py` |
| 20 | E2E 测试通过 | `python3 -m pytest tests/ -q -x` |
