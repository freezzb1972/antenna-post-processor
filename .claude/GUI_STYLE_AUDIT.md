# GUI 样式审计清单

**最后更新**: 2026-07-05  
**目的**: 修改 GUI 样式时查此清单，避免多处覆盖互相冲突。

---

## QSS 生效顺序（后覆盖前）

```
1. Qt 系统主题 (theme_manager.py → app.setStyleSheet)
2. _make_custom_qss() (main_window.py:1593)
3. dynamic_qss() (scale_manager.py:65)      ← 最后生效，优先级最高
```

---

## 一、全局 QSS（影响所有同类控件）

### 1.1 dynamic_qss() — scale_manager.py:65-139

**唯一控制点**，放开这里改：

| 控件 | 属性 | 当前值 |
|------|------|--------|
| QWidget | font-size | 缩放后 |
| QPushButton | font-size, min-height, min-width, padding | 缩放后 |
| QLineEdit/QComboBox/QSpinBox | font-size, min-height, min-width, padding | 缩放后 |
| **QGroupBox** | font-size, border, border-radius, font-weight, padding-top, margin-top | 缩放后 |
| **QGroupBox::title** | font-size, subcontrol-origin, left, padding | 缩放后 |
| QTabBar::tab | font-size, padding | 缩放后 |
| QTabWidget::pane | padding | 缩放后 |
| QTableWidget/QListWidget | font-size | 缩放后 |
| QHeaderView::section | font-size, padding | 缩放后 |
| QMenu/QMenuBar | font-size, padding | 缩放后 |
| QToolTip | font-size, padding | 缩放后 |
| QStatusBar | font-size | 缩放后 |
| QCheckBox/QRadioButton | font-size, spacing | 缩放后 |
| QLabel | font-size | 缩放后 |
| QScrollBar | height/width | 缩放后 |
| QSplitter::handle | width, height | 缩放后 |
| QDialog | min-width | 缩放后 |

### 1.2 _make_custom_qss() — main_window.py:1593

| 控件 | 属性 |
|------|------|
| QPlainTextEdit | border-radius, font-family |
| QPushButton#btnStart | font-weight, letter-spacing |
| QPushButton#btnStop | font-weight |

### 1.3 theme_manager.py:61 — 暗色主题指示器

仅暗色主题生效。包含 `QCheckBox::indicator`, `QRadioButton::indicator`, `QGroupBox::indicator`, `QMenu::separator`。

---

## 二、页面级内联 QGroupBox 样式（覆盖全局 QSS）

这些在各自 widget 上通过 `setStyleSheet()` 设置，**优先级高于全局 QSS**。

| 文件:行 | 控件类型 | 样式 | 说明 |
|---------|---------|------|------|
| pages.py:2930 | checkable QGroupBox | `font-weight:bold; padding-top:16px` | 图表配置页折叠分组 |
| pages.py:2931 | QGroupBox::indicator | `width:14; height:14` | 折叠箭头 |
| pages.py:3549 | checkable QGroupBox | 同上 | 图表配置页(rebuild) |
| dialogs.py:1565 | checkable QGroupBox | 同上 | 计算参数对话框 |
| dialogs.py:1566-1568 | QGroupBox::indicator | 同上 + unchecked | 计算参数对话框 |

> ⚠️ 这些 `padding-top: 16px` 覆盖了全局 `padding-top: 4px`。不要改全局值来调整折叠 QGroupBox。

---

## 三、其他内联 setStyleSheet（不影响全局）

纯装饰性，互不冲突：

| 文件 | 控件 | 作用 |
|------|------|------|
| main_window.py:426 | nav_list | 导航项间距 |
| main_window.py:495 | params_display | 参数面板背景 |
| main_window.py:1970-2015 | label/header/btn | 参数展示标签样式 |
| pages.py:801-809 | summary/btn | 预览对话框按钮 |
| pages.py:1796/1807/2182 | btn_del | 角度删除按钮 padding:0 |
| pages.py:4297 | doc_browser | Word 预览背景色 |
| widgets.py:72 | title (AnglePicker) | 粗体 |
| widgets.py:505 | lbl_match_status | padding |
| widgets.py:575 | lbl_count (FreqPicker) | 颜色 |
| graph_viewer.py:327/336/521/721/724/1002 | 各标签 | 颜色/背景 |
| dialogs.py:多处 | btn_del/label | 颜色/字体 |

---

## 四、布局间距（非 QSS，Python setContentsMargins/setSpacing）

| 文件:行 | 位置 | 值 |
|---------|------|-----|
| pages.py:157 | left_widget (输入) | margins=(0,0,0,0), spacing=1 |
| pages.py:170 | Excel模板 | margins=(4,0,4,0), spacing=1 |
| pages.py:195 | Word模板 | margins=(4,0,4,0), spacing=1 |
| pages.py:255 | right_widget (输出) | margins=(0,0,8,0), spacing=1 |
| pages.py:261 | 输出设置 QGroupBox | margins=(4,0,4,0), spacing=1 |
| widgets.py:463 | DataFileSelector QGroupBox | margins=(4,0,4,0), spacing=1 |
| main_window.py:406 | h_layout (sidebar+page) | margins=(0,0,12,0) |

---

## 五、QSS 修改快速指南

| 要改什么 | 改哪里 |
|---------|--------|
| 所有 QGroupBox 边框/圆角/标题间距 | `scale_manager.py` dynamic_qss() |
| 所有按钮/输入框/表格字体大小 | `scale_manager.py` dynamic_qss() |
| 启动/停止按钮样式 | `main_window.py` _make_custom_qss() |
| 日志区字体 | `main_window.py` _make_custom_qss() |
| 可折叠 QGroupBox 的折叠箭头 | 各自的 `setStyleSheet()` (pages.py/dialogs.py) |
| 某页特定控件颜色/字体 | 该控件自己的 `setStyleSheet()` |
| 控件间距/内边距 | 该容器的 `setContentsMargins`/`setSpacing` |

## 六、常见踩坑

1. **改 QGroupBox 样式没生效** → 检查 `dynamic_qss()` 是否覆盖了你的值
2. **可折叠 QGroupBox 高度异常** → 它在 `setStyleSheet` 中有自己的 `padding-top: 16px`
3. **setStyleSheet() 会重置 min-width** → main_window.py:255 有注释，需在 QSS 后重新 setMinimumWidth
4. **scale_manager.py QSS 用 `{{ }}` 双花括号** → 因为外层是 f-string，`{` 需要转义为 `{{`
