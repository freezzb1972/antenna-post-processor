---
name: user-preferences
description: 关键设计决策记录
---

# 关键设计决策

## 模板识别：正则 vs LLM

- **决策：用正则，不用 LLM**
- 原因：列头高度结构化（`Theta=60`, `Theta=0-90 LAG`），变化范围有限
- 容错：全角→半角转换、空格/换行规范化
- 兜底：GUI 手动映射列

## LAG 计算方式

- **方位面平均增益**（客户确认）：固定 θ 上 Gain(φ) 的线性平均值

## GUI 开发约束

- Qt Designer 设计 .ui → pyside6-uic 编译为 .py
- **不要**手动编辑编译后的 .py 文件
- 翻译字符串用 `self.tr()` 标记
