---
name: user-preferences
description: 用户偏好与决策记录 — GUI、打包、i18n、LLM使用决策
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0d038809-420b-4a1e-8631-c2bbd6c73f07
---

# 用户偏好与关键决策

## 交付形式
- **编译为单文件 .exe**（PyInstaller --onefile --windowed）
- Windows 平台交付给车企客户
- 用户在自己的 Windows 机器上打包

## GUI 设计
- **PySide6 + Qt Designer** 可视化设计 .ui 文件
- **qt-material** Material Design 主题（dark_teal 默认）
- Qt Designer 设计，pyside6-uic 编译为 .py
- **不要**每次手动编辑编译后的 .py 文件

## 中英文 i18n
- Qt Linguist 标准流程（.ts → .qm）
- 运行时动态切换（QEvent.LanguageChange → retranslateUi）
- 按钮切换中/英，初始跟随系统 locale

## 模板识别：正则 vs LLM
- **决策：用正则，不用 LLM**
- 原因：列头高度结构化（`Theta=60`, `Theta=0-90 LAG`），变化范围有限
- 容错：全角→半角转换、空格/换行规范化
- 兜底：GUI 手动映射列

## 数据处理
- LAG 计算方式：**方位面平均增益**（客户确认）
- 主数据源：5G1_merged.csv（含 Phase，可算 AR）
- 模板驱动：自动读取 Excel 列头 → 识别参数需求

**Why:** 用户明确要求的交付形式和设计选择，后续修改必须遵循。

**How to apply:** 所有新功能需支持 exe 打包，GUI 改动在 Qt Designer 中完成，翻译字符串用 self.tr() 标记。
