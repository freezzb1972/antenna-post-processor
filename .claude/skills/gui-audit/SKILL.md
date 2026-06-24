# /gui-audit — GUI 完整性审计

## 何时使用

- 新增/修改 UI 元素后
- 发现 UI bug 后（防止同类问题）
- 每次 release 打包前

## 审计清单

### 1. 可见性检查

```bash
python3 -c "
from ui.main_window import MainWindow
import sys; from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
w = MainWindow(app)

# 检查所有 tab 的可见性
tc = w.ui.tabConfig
for i in range(tc.count()):
    print(f'Tab[{i}]: \"{tc.tabText(i)}\" visible={tc.isTabVisible(i)}')

# 检查所有隐藏的 widget
import gc
for name in dir(w.ui):
    obj = getattr(w.ui, name, None)
    if hasattr(obj, 'isVisible') and not obj.isVisible():
        print(f'HIDDEN: {name}')

# 检查动态 widget
for name in dir(w):
    if name.startswith('_') and hasattr(getattr(w, name, None), 'isVisible'):
        obj = getattr(w, name)
        if not obj.isVisible() and hasattr(obj, 'objectName'):
            print(f'HIDDEN: {name} ({obj.objectName()})')
"
```

### 2. 布局完整性检查

每个可见 widget 必须满足：
- `geometry().width() > 50` — 不是被压缩到看不见
- `geometry().x() + geometry().width() < parent.width()` — 不超出父窗口右边界
- `visibleRegion().boundingRect().width() > 20` — 可见区域实际有像素

```bash
python3 -c "
from ui.main_window import MainWindow
import sys; from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
w = MainWindow(app)
w.show(); app.processEvents()

# Check dynamic widgets for clipping
for attr in ['_cmb_naming_mode', '_btn_auto_match']:
    obj = getattr(w, attr, None)
    if obj and obj.isVisible():
        geo = obj.geometry()
        vr = obj.visibleRegion().boundingRect()
        print(f'{attr}: geometry={geo.width()}x{geo.height()} visible={vr.width()}x{vr.height()}')
        if geo.width() < 50:
            print(f'  ⚠ WARNING: widget too narrow!')
        if vr.width() < 20:
            print(f'  ⚠ WARNING: widget clipped/not visible!')
"
```

### 3. 重复 UI 同步检查

当同一个功能有两套 UI（主窗口选项卡 + 对话框）时：
- [ ] 两套 UI 包含相同的核心控件
- [ ] 对话框 _load_state 和 _on_accept 正确双向同步
- [ ] 没有控件只在一套 UI 中存在

检查方法：
```bash
# 对比主窗口和对话框的关键属性
grep -n '_cmb_naming_mode\|_worksheet_naming_mode\|_lag_config\|_ar_lag_config' \
  ui/main_window.py ui/dialogs.py
```

### 4. 自动检测→自动应用检查

凡是系统自动检测到的配置（模板参数、角度等），必须：
- [ ] 自动应用到主窗口状态变量（无需人工点 OK）
- [ ] 在日志中记录 "从模板自动更新: ..."
- [ ] 用户手动修改后不被覆盖（比较新旧值）

## 历史问题模式

| # | 问题 | 根因 | 预防规则 |
|---|------|------|---------|
| 1 | 命名选项不可见 | tabFile 被 _hide_settings_tabs 隐藏 | **规则1**: 高频 UI 不隐藏 |
| 2 | 命名选项在右边缘 | stretch spacer 推到 x=866 | **规则2**: 控件前不加大 stretch |
| 3 | 单文件命名模式无效 | expanded=list(sheets_info) 无条件覆盖 | **代码审查**: 检查分支覆盖 |
| 4 | 模板参数不自动应用 | 检测和应用分两步 | **规则4**: 检测即应用 |
| 5 | 对话框缺命名选项 | 两套 UI 不同步 | **规则3**: 双 UI 同步 |
| 6 | 陈旧数据残留 | 匹配表不清 + [] falsy bug | 另见 stale-data skill |

## 回归测试

```bash
python3 gui_integrity_check.py
python3 -m pytest tests/ -q -x
```
