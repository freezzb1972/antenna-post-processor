---
name: project-overview
description: 天线参数后处理工具项目总览 — 目标、架构、技术栈
metadata: 
  node_type: memory
  type: project
  originSessionId: 0d038809-420b-4a1e-8631-c2bbd6c73f07
---

# 天线参数后处理工具 (Antenna Post-Processor)

## 项目目标
从 EMQuest 天线测试 CSV（151MB，105 频点 × 4 极化分量）计算车企要求的各项天线指标，输出格式化 Excel 报告，生成 3D 辐射方向图。

## 技术栈
- **语言**: Python 3.8+
- **GUI**: PySide6 + Qt Designer + qt-material (Material Design 主题)
- **计算**: NumPy 向量化（球面积分、复数运算）
- **Excel**: openpyxl（读写 + 图片嵌入）
- **绘图**: matplotlib（3D 球面方向图，Agg 后端）
- **i18n**: Qt Linguist（中英文双语，97 字符串）
- **打包**: PyInstaller --onefile → Windows .exe（80-120MB）

## 架构
```
main.py → ui/main_window.py (GUI)
           ↓ QThread
       src/worker.py → src/pipeline.py
                         ├── src/parser.py (CSV 流式索引)
                         ├── src/calculator.py (Gain/Dir/Eff/LAG/AR)
                         ├── src/plotter.py (3D 方向图)
                         └── src/exporter.py (Excel + 图片嵌入)
```

## 关键文件
- `src/parser.py`: byte-offset 索引，151MB 大文件流式读取
- `src/calculator.py`: 6 个核心计算函数，纯 NumPy
- `src/lag_config.py`: LAG 配置模型 + Excel 列头正则解析
- `src/pipeline.py`: 批处理管线，单 CSV → 多 Sheet
- `ui/main_window.py`: 主窗口逻辑，信号/槽，LAG 面板交互
- `antenna_post_processor.spec`: PyInstaller 打包配置

**Why:** 项目已完成全部代码实现，30 测试通过，E2E 验证通过（360行数据+360张3D图，59MB输出）。

**How to apply:** 参考此文件了解项目全貌，修改时注意模块间依赖关系。
