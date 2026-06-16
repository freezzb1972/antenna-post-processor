---
name: gui-check
description: GUI 完整性守护 — widget 树、FormLayout、信号链路、ScrollArea、线程启动
---

# GUI 完整性守护 (/gui-check)

每次修改 `ui/main_window.py` 或 `ui/compiled/*.py` 后自动运行。
5 阶段检查，G1-G3 为 GATE（失败即停），G4-G5 为 WARN。

## 触发条件

- 修改 `ui/main_window.py` 后
- 修改 `ui/compiled/ui_main_window.py` 后
- 打包前
- 用户说 "检查 GUI" 或 "/gui-check"

## 自动调用

当 CLAUDE.md 检测到以下文件有变更时，会自动调用本 skill：

```
ui/main_window.py
ui/compiled/ui_main_window.py
```

## 验证阶段

### G1: Widget 树 (GATE)
检查关键 widget 存在性、可见性、最小尺寸：
- editOutputName, editOutputDir, btnStart 等必须可见
- editCsvPath, btnBrowseCsv 等必须隐藏
- _file_list_widget, _match_table 等必须非空

### G2: FormLayout (GATE)
扫描编译 UI 文件，确保每个 form layout row 的 LabelRole 和 FieldRole 成对出现。

### G3: 信号链路 (GATE)
验证 btnStart.clicked → _on_start → QThread → moveToThread → started.connect → thread.start() 完整链。

### G4: ScrollArea (WARN)
验证 tabFile 和 tabLag 的内容已包裹在 QScrollArea 中。

### G5: 线程冒烟 (GATE)
实例化 MainWindow → 模拟点击 Start → 验证 thread.isRunning()。

## 命令

```bash
python3 gui_integrity_check.py          # 完整检查
python3 gui_integrity_check.py --quick  # 仅 G1-G3 (5s)
python3 gui_integrity_check.py --json   # JSON 输出
```
