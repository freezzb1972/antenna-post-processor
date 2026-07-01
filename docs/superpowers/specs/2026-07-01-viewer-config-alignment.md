# 图表查看 & 图表配置 — 架构对齐设计

**状态:** 讨论完成，待实现
**日期:** 2026-07-01

## 核心设计决策

### 1. 层级关系

```
图表查看 (GraphViewer) = 全集  (能算的都算，能看的都看)
  └── 图表配置 (ChartConfig) = 子集 (从全集中勾选哪些写入报告)
```

### 2. 预览先于出报告

```
加载数据 → [👁 预览] → 仅计算(3-5s) → 查看器交互确认 → [📄 出报告] → 全套导出(90s)
```

- 预览阶段跳过: openpyxl 写入、Matplotlib 渲染、Word 生成
- 计算阶段全量计算所有参数 (不受 ChartConfig 限制)
- 天线参数页 LAG 角度变更 → 强制重新预览
- 图表配置页角度/DPI/布局变更 → 仅影响报告，不需重新预览

### 3. GUI 按钮变更

```
当前: [▶ 开始处理] [⏹ 停止]
改为: [👁 预览] [📄 出报告] [⏹ 停止]
```

状态机:

| 状态 | 预览按钮 | 出报告按钮 | 停止按钮 |
|------|---------|-----------|---------|
| IDLE | 可用 | 禁用 | 禁用 |
| PREVIEWING | 禁用 | 禁用 | 可用 |
| READY | 可用 | 可用 | 禁用 |
| EXPORTING | 禁用 | 禁用 | 可用 |

### 4. ChartConfig 降级

- 从控制"计算哪些参数" → 降级为控制"出哪些图表到报告"
- pipeline 始终全量计算，ChartConfig 布尔字段仅影响 exporter/word_writer
- 查看器不依赖 ChartConfig，直接读取计算结果

### 5. pipeline 拆分

| 步骤 | compute_only | full_export |
|------|-------------|-------------|
| 读模板 + 列头解析 | ✅ | ✅ |
| 构建任务队列 | ✅ | ✅ |
| 加载原始数据 | ✅ | ✅ |
| 公式计算 (Gain/Dir/Eff/LAG/AR/...) | ✅ | ✅ |
| 3D/2D/方位面渲染 (Matplotlib) | ❌ | ✅ |
| Excel 写入 (openpyxl) | ❌ | ✅ |
| 完整报告 | ❌ | ✅ |
| Word 图表报告 | ❌ | ✅ |
| 中间数据 Excel | ❌ | ✅ |

### 6. 数据陈旧检测 (选项 B — 简化)

天线参数页的 LAG 角度/算法选项变更 → READY → IDLE，强制重新预览。
图表配置页和输出路径变更 → 不触发重新预览。

### 7. 参数回传 (选项 B)

查看器有"应用当前角度到图表配置"按钮，单向回传，不改天线参数。

## 图表配置新增

- `pattern_3d_etheta` — E_θ 分量 3D 方向图 (A 类)
- `pattern_3d_ephi` — E_φ 分量 3D 方向图 (A 类)
- 仅 A 类 3D，不加 C 类 2D 切面和方位面

## 查看器新增

- **"2D Cuts" 模式**（与 "3D Pattern" / "Freq Curves" 并列）
- 俯仰面: 选 Phi 角 → Gain/AR/E_θ/E_φ vs Theta, Polar/Rect 切换
- 方位面: 选多 Theta 角 → Gain/AR vs Phi, 多曲线叠加
- **"应用当前角度到图表配置"** 按钮 (选项 B)

## full_report 修复

- 完整报告和主报告**共用同一套计算结果和图表生成函数**
- 两者各自有参数选择范围 (模板列 / full_report_columns.json)，但共用 ChartConfig 控制出图
- 修复: `export_full_report` 调用 `_embed_pattern_images` + `_add_charts`，嵌入图表

## Word 输出布局 — 批量模式 + 图表选择排序

- **模式 A (按频点)**: 第 1 频点全部图 → 第 2 频点全部图 → ...
- **模式 B (按图表类型)**: 第 1 类图全频点 → 第 2 类图全频点 → ...
- 子对话框 "Word 输出设置": 模式切换 + 图表勾选 + 上下移动排序
- 默认全选，顺序 A → C → 方位 → B
- 恢复默认按钮

## B 类频点曲线出 Word

- 当前 B 类是 openpyxl ScatterChart → 仅 Excel
- Word 需要 PNG → 新增 `render_freq_curve_png()` (Matplotlib Cartesian line chart)
- 一图一参数: x 轴 = 频率 (MHz), y 轴 = 参数值, 一个参数一条线
- 横坐标刻度数自动适配频点数量, 纵坐标范围自动适配数据范围
- figure size 默认合适, 不截断图例和轴标签
- 作为新图片组加入 chart_word_writer

## 实现待办

- [ ] pipeline 拆分 `compute_only` vs `full_export`
- [ ] GUI 按钮改造: `[预览] [出报告] [停止]` + 状态机
- [ ] ChartConfig 新增 `pattern_3d_etheta` / `pattern_3d_ephi`
- [ ] 查看器补齐 Freq Curves (TRP/NHPRP/EIRP/AvgGain)
- [ ] 查看器新增 "2D Cuts" 模式
- [ ] 查看器新增 "应用角度到图表配置" 按钮
- [ ] 数据陈旧检测 + 状态机互锁
- [ ] full_report 嵌入图表
## 中间数据扩展

- 俯仰面: Gain/AR/E_θ/E_φ × 每 Phi → worksheet=频率, 列=Phi角, 行=Theta
- 方位面: Gain/AR/E_θ/E_φ × 每 Theta → worksheet=频率, 列=Theta角, 行=Phi
- 频点曲线不需要（主 Excel 已有）
- 输出设置用下级窗体，不占用主输出页面空间

## 实现待办 (更新)

- [ ] pipeline 拆分 `compute_only` vs `full_export`
- [ ] GUI 按钮改造: `[预览] [出报告] [停止]` + 状态机
- [ ] ChartConfig 新增 `pattern_3d_etheta` / `pattern_3d_ephi`
- [ ] 查看器补齐 Freq Curves
- [ ] 查看器新增 "2D Cuts" 模式
- [ ] 查看器 "应用角度到图表配置" 按钮
- [ ] 数据陈旧检测 + 互锁
- [ ] full_report 嵌入图表
- [ ] B 类频点曲线出 Word (新增 `render_freq_curve_png`)
- [ ] Word 输出布局: 批量模式 + 图表选择排序
- [ ] 中间数据扩展: 俯仰面 + 方位面 × 4 数据源, 下级窗体设置
- [ ] USER_GUIDE 新增第 25 章: Word 模板报告 (书签/循环/SDT 使用说明)
- [ ] 生成示例 Word 模板 .docx, 供用户下载修改
