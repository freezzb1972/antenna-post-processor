# CURRENT STATE — 2026-09-16（性能修复轮）

**Branch:** master · **基线:** `1bcb4ab` · 其上 **7 个提交**（`241160c` / `a25fe83` 待 push）。
工作区: 仅 `antenna_config.json`（用户配置，刻意不提交）+ 一批未跟踪的新文件。

---

## A. 本轮工作 — 7 个提交

```
a25fe83  refactor(ui): 移除指向已废弃控件的 3 处死调用 — 消除 AttributeError 隐患
241160c  docs: 状态固化 — 补充 UI 重构遗留死代码项 (F-1) 与测试假绿经过 (A-5)
478cdd2  test(smoke): 替换 TestConfigTabButtons 为弹窗测试 — 原类测的全是已废弃控件
818c156  fix(tests): 修 smoke 套件 3 处测试自身缺陷 — 断言恒真 / import 错路径 / 传参错
3fd8d88  perf(src): FinalSummary→CSV 转换改流式 — 583MB 文件从 OOM 到 4.4 分钟
ea54fd5  perf(src,ui): 大 Excel 数据加载提速 100 倍 — read_only 流式 + 频点延迟加载
79cdc59  fix: 修 4 处真 bug — 目录当文件、窗口销毁残留、测试契约与模态挂死
1bcb4ab  ← 基线
```

**起点是一个用户报告**：「点击图表配置的参数设置，没有响应；7 月份的版本没有这个问题。」

追下去发现是**三个独立缺陷叠加**，且都与「用户实际用的是 583MB 的 FinalSummary.xlsx」有关。

### A-1 真正的根因：openpyxl 全量加载

`openpyxl.load_workbook(read_only=False)` 会把**全部** sheet 一次性解析成 Python 对象。
用户文件的实测数据：

| | 118MB / 105 sheet | 583MB / 139 sheet |
|---|---|---|
| 解压后 | 627 MB | **3088 MB** |
| `read_only=False` | 101.6~179s，内存 +4.9GB | 推算 ~15min / ~24GB |
| `read_only=True` | 0.35~0.9s，内存 +7MB | **3.0s / +7MB** |

**本机总内存仅 11GB + 4GB swap** —— 所以原实现不是「慢」，而是**必然被 OOM Killer 杀掉**。
用户看到的「没响应」实际是进程消失的前兆。

### A-2 三条触发路径（都指向同一个加载函数）

1. **点「参数设置」** —— `ChartSettingsPage._add_frequency_picker` 在**构造时**读数据：
   缓存为空时对前 3 个数据文件调 `DataSource.from_path`。而每次打开参数弹窗都会
   构建该组件 → 同步解析大文件、界面零反馈地冻结。
   > 修法（`ea54fd5`）：频点收集抽出为 `_load_all_frequencies()`，改为**点「选择频点...」时**
   > 才调用。弹窗秒开。

2. **点「预览」** —— 走 `build_datasource_map` → `FinalSummarySource.__init__`。
   > 修法：`src/finalsummary_reader.py` 改 `read_only=True`（见 B 节判据）。

3. **工具菜单「FinalSummary 转 CSV」** —— `src/fs_to_csv.py` 同样 `read_only=False`。
   > 修法（`3fd8d88`）：改流式。583MB 从 OOM 降到 4.4 分钟 / 220MB。

### A-3 「出报告快很多」其实是刻意设计（已向用户澄清）

```python
_on_preview():  self._cached_datasource_map = None; _do_run(compute_only=True)   # 清缓存→加载
_on_export():   if state != READY: 弹「请先预览」; return
                _do_run(compute_only=False, reuse_datasource=True)                # 复用预览的数据
```

**「出报告」强制要求先预览，且复用预览已加载的数据源，自己根本不加载。**
所以「出报告快」是必然的 —— 真正要等的只有「预览」那一次。

### A-4 顺带修掉的 4 处真 bug（`79cdc59`）

- `src/task_package.py`：路径校验 `exists()` → `is_file()`。目录也满足 `exists()`，
  会让 `_file_hash` 走 `open(目录)` 抛 `IsADirectoryError` 进 Qt 事件循环；
  **模板路径为空时 `Path("") == Path(".")`，保存任务包即崩**。
- `ui/window_manager.py`：窗口销毁改用**身份比较**（`w is not window`）。
  `list.remove` 走 `__eq__`，对已销毁的 PySide 对象比较会抛 `RuntimeError`
  → 移除被跳过 → 窗口永久留在 `_windows` → 内存不释放，且
  `_update_all_window_menus` 退化为 **O(n²)**（实测测试套件越跑越慢）。
- `tests/test_gui_e2e.py`：`getOpenFileNames` 桩改为返回 `(list, str)` 契约
  （原返回 str 会让调用方逐字符当路径 → `PermissionError`）。
- `tests/test_gui_smoke.py`：打桩 `QMessageBox.about` / `QDialog.exec` ——
  offscreen 下静态模态与嵌套事件循环无人关闭，**实测挂死 20 分钟**。

### A-5 测试假绿清理（`818c156` + `478cdd2`）

起因：smoke 套件每次都有 4 个用例 SKIPPED（`btnQuick0 not visible`）。
追查发现根因在**产品侧的 UI 重构**，并牵出一整类假绿测试。

**产品侧真相**：`MainWindow._hide_settings_tabs()` 把原 6 个 tab 重组为 3 个
（处理设置 / 计算结果 / 图表查看），`tabLag`/`tabPlot`/`tabCalc` 被 `removeTab`
移除。注释写着「控件对象保持存活，Step 5 清扫」—— **该清扫至今未做**。

`removeTab` 只摘标签不删对象，且 `_make_tab_scrollable` 会把页 reparent 进
`QScrollArea`，所以：
- `ui.tabLag` 变成**空壳**（`findChildren` = 0），真正的内容在另一个匿名 QWidget 里
- 那些控件不在任何 tab 中（实测 `tabConfig.indexOf(该页) == -1`），**永不显示**

**测试侧后果**：`TestConfigTabButtons` 的 21 个用例全部建立在死控件上 ——
4 个 `pytest.skip("not visible")` 永远跳过，其余写成
`if btn.isVisible() and btn.isEnabled(): btn.click()`，静默略过点击且无任何断言，
函数跑完即 PASSED。**没有一个真正验证过行为。**

**处理**：删除该类，改为覆盖重构后的真实入口
`AntennaParamsPage._show_angle_popup` 弹窗。弹窗是模态的 → 打桩 `QDialog.exec`
并在打桩函数内捕获 dialog 对象（它是函数局部变量，返回后即失去引用），
再对控件做真实点击 + `isVisible()` 断言（防止再次退化为假绿）。
弹窗结构按**实测**确定而非按源码猜测：汇总组「已配置: N 个单角度, M 个范围」
+「添加单角度」(`+ 添加`) / 「步进批量生成」(生成) / 「角度范围」(添加范围)
+ 顶层 确定/取消。用例数 89 → **73**。

> **教训**：`if 控件.isVisible(): 点击()` 这种写法等于没有测试。
> 见到 `skip("not visible")` 或 `if ...isVisible()` 包住的点击，先问「它真的会可见吗」。

---

## B. 大文件加载性能（后续维护必读）

### 判据：一段 openpyxl 代码能否用 read_only

| 取数方式 | read_only 兼容 | |
|---|---|---|
| `iter_rows()` / `iter_cols()` 顺序读 | ✅ | 本项目两个文件恰好全是这种 |
| `ws['B5']` / `ws.cell(row, col)` 随机访问 | ❌ | 不支持 |

> `_probe_structure` 的注释本就写着「不使用 `ws.cell()` — 全用 `iter_rows()` 流式读」，
> 说明这段代码**原本就是照 read_only 写的**，只是一直传着 `read_only=False`。
> 所以这是**一行改动**换百倍提速，不是重构。

### read_only 下没有额外代价（实测，反直觉）

- `iter_rows()` **只解析到 `max_row` 就停止**，不会读完整个 XML。
  实测 22.3MB 的 sheet 读 361 行仅 **0.17s**；同一 sheet 连续 4 次 `iter_rows` 共 0.69s。
  → 所以 `fs_to_csv` 那 4 个 section 各遍历一遍全部频点，**不需要合并遍历的重构**。
- `max_row` / `max_column` **照常可用**（取自 worksheet 的 dimension 记录，
  不触发全表扫描；583MB 文件上访问耗时 0.00s）。

### 验证方式（改这类代码时必须做）

与 `read_only=False` 的结果**逐字段/逐元素对比**；转换类工具再对比**输出 sha256**。
本轮四项全过：结构逐字段一致 · `read_batch` 矩阵逐元素相同（含 NaN 位置）·
转换输出 sha256 相同 · 端到端 CSV 解析后逐值吻合。

### 用户文件位置（复现用）

`/mnt/d/CC/Ralab Test Data/2026-9-16/2#with amp.xlsx` —— 583MB / 139 sheet / 1154-1292 MHz。
同目录有 `~$` 锁文件，说明可能正被 Excel 打开。

---

## C. i18n 机制（上一轮完成，仍有效）

架构：`控件当前文本 ──反查(context,文本)──> 源串 ──forward──> 新语言文本`

- **`i18n/trans_table.json`** 是**构建期产物**，**必须随包发布**（spec datas 已加）：
  `.ts` 不进 EXE，而 `QTranslator` 不提供反向映射。
- **接入点** `I18nManager.switch()` 内**同步**执行 —— 不用 `changeEvent`，因为
  `installTranslator` 投递 LanguageChange 是**异步**的，依赖它会出现「切换完成但界面未刷新」
  的窗口期（这正是旧测试假通过的成因）。
- **覆盖 11 类文本载体**；刻意不碰 `QLineEdit.text()` / QTextEdit / 表格数据单元格
  （改了会破坏用户数据）。
- **最终规模**：40 context / 1666 条英文译文 / 同 context 内反向碰撞 **0**。
- 运行时守卫 `_load_table()` 发现同 context 反向碰撞会 `log.warning` —— 看到请立即查译文。

工具：
```bash
python3 scripts/check_i18n.py      # 漏包守卫（现报 180 处，绝大多数是正当项：模块级表/文件名/f-string）
bash scripts/update_i18n.sh        # lupdate → lrelease → 生成反查表 → 漏包检查
```

> **做下拉框前必查**：它按 `itemData` 还是 `currentText()` 消费？
> 按 text 的必须先改成 data，否则翻译会**静默破坏功能**（选了没反应）。
> 已在 `VIEW_PRESETS`、`_cmb_ai_mode`、`ThemeManager` 三处遇到同一模式。

---

## D. 踩过的坑（都是实际发生过的）

| # | 坑 | 现象 | 正解 |
|---|---|------|------|
| 1 | **class body 无 self** | `class X: NAME = self.tr("...")` → **导入即 NameError**。`py_compile` 查不出 | ①在消费点翻译 或 ②`QCoreApplication.translate("X", ...)` |
| 2 | **class body 包 translate 会冻结** | import 期求值，那时 QApplication 还没建，译文被**冻结**，切语言失效 | 在**消费点**用 `tr_shared(name, "Ctx")` |
| 3 | **显示名与内部键混用 → 功能失效** | 切语言后显示名被反查改写 → `name not in VIEW_PRESETS` → **选预设无任何效果** | 显示名进 `itemText`、内部键进 `itemData`，查找用 `currentData()` |
| 4 | **`.ts` 含换行的源串是跨行的** | 行级改写脚本把译文写进**别的条目**，5 处静默错译 | 跨行感知解析（累积到 `</source>`） |
| 5 | **lupdate 是静态扫描器** | `self.tr(VAR)` 提取不到（重扫报 "0 new"） | 字面量写在调用点；动态来源用 `ui/i18n_catalog.py` |
| 6 | **`self.tr(self.tr(...))` 双重嵌套** | 内层已译，外层把译文当源串再翻 | 一层即可 |
| 7 | **`.ts` 不进 EXE** | 运行时读不到 | 反查表走构建期 JSON + spec datas |
| 8 | **门禁/测试在资源争抢下会假死** | 门禁被 900s timeout 杀掉，同一份代码随后干净跑完 | 跑前确认无残留后台任务；`python3 -u` + 直写文件，别用 `\| tail` |
| 9 | **批量写译文要转义 `"`** | 下次 lupdate 规范化成 `&quot;`，产生无谓 churn | 写入时一并转义 |
| 10 | **隐式字符串拼接会被逐行包裹拆散** | `"A\n"` / `"B"` 各包一层 → 变两个参数 → SyntaxError | 先按「字面量间只有空白」分组成段，整段包一层 |
| 11 | **`.ui` 与 `compiled/` 已不同步** | 重编译会让 `hButtons` 挂错父 → `_extract_execution_bar()` 抛「QLayout already has a parent」→ **MainWindow 构造直接失败** | **在两者对齐前不要重编译 UI** |
| 12 | **反查候选降级顺序会影响带点的缩写** | `'Contract No.:'` 激进剥离丢掉 `.:` → 还原不回中文 | 候选顺序：精确 → 去 HTML → **只剥行尾冒号** → 剥首尾非文字 → 抽中文核心 |
| 13 | **`pgrep -f` / `pkill -f` 会匹配到自己** | `pkill -f "xxx"` 把执行它的 shell 自己杀了（exit 144）；`pgrep -f "a\\\|b"` 在 ERE 下静默匹配不到 | 杀进程先 `pgrep` 取 PID 再 `kill`；等待循环改用 `until grep -q <标志> <日志>` |
| 14 | **`self.tr` 用在没有 `self` 的地方** | ①模块级/普通函数 ②**`def` 行的参数默认值** —— 默认值在定义时求值。都 `py_compile` 通过、**运行才 NameError** | 非方法内用 `QCoreApplication.translate`；默认值改 `None` + 函数体内取 |
| 15 | **字符串前缀会被吞进 `self.tr`** | `r"[a-z]+"` → `rself.tr("[a-z]+")` —— 语法合法、运行 NameError | 包裹脚本跳过 `r`/`f`/`b`/`u` 前缀 |
| 16 | **`processEvents()` 不处理 DeferredDelete** | 控件数每次 +1，像泄漏 | 判断对象是否收敛必须用真实事件循环（`QEventLoop` + `QTimer.singleShot(0, quit)`） |
| 17 | **`qtbot.addWidget` + `dlg.deleteLater()` 双重管理**（本轮新增） | addWidget 已登记对象，teardown 会再 close 一次；手动 deleteLater 先销毁 C++ 对象 → `Internal C++ object already deleted`。**该错误还会让下一个用例 setup 失败**（`previous item was not torn down properly`） | 只交给 pytest-qt 托管，别手动 deleteLater。本轮 5 条失败/错误里有 2 条是这一个根因的连锁反应 |
| 18 | **`or True` 型假测试**（本轮新增） | `assert X.called or True` —— 既没打桩（原生函数没有 `.called`，取属性即抛 `AttributeError`），`or True` 又让断言恒真 | 见到 `or True` 立即当作「没有断言」处理 |
| 19 | **pkill 之后要确认进程真死**（本轮新增） | `pkill -f` 返回 144 是**它杀了自己的 shell**，不代表目标已死；曾遗留一个 5.7GB 的 python 进程 | 用 `ps aux --sort=-%mem` 复核 |

---

## E. 交付阻塞项

**给 Ralab 的 EXE 需要重打包** —— 现行版本缺少本轮 4 个提交。
本轮的性能修复**对交付影响很大**：原来 583MB 的生产文件是必然 OOM 的。

```bash
cd /mnt/d/cc/antenna-post-processor && \
/mnt/d/Python312/python.exe -m PyInstaller antenna_post_processor.spec --clean --noconfirm
```

⚠️ **不要用 `build.bat`** —— 它会跑 `generate_trial_config.py`，把 `license.json`
覆盖成试用许可，冲掉 Ralab 的正式许可（备份在 `license.json.trial_backup`）。

⚠️ **打包前确认 `i18n/trans_table.json` 是最新的**（`bash scripts/update_i18n.sh` 生成）。

---

## F. 未决项

1. **UI 重构遗留的死代码清理（注释里的「Step 5 清扫」）** —— 详见 A-5。
   `_hide_settings_tabs()` 移除了 tabLag/tabPlot/tabCalc，但清扫没做，
   一整套控件与操作它们的代码仍在空转：

   | 实体 | 产品代码引用 |
   |---|---|
   | `configItemsWidget` + `_update_lag_display()`（`ui/main_window.py:2179`） | 6 处 |
   | `_QUICK_ANGLES` + `btnQuick*` + `_sync_quick_buttons()`（`ui/main_window.py:76` / `:2173`） | 15 处 |
   | `btnAddCustomAngle` 等 7 个操作按钮 | **0 处**（纯孤儿） |

   **实测规模**：死子树 **49 个控件**（17 按钮 / 4 分组 / 9 标签 / 6 数值框），
   占 MainWindow 总控件数 819 的 **6.0%**。
   **实测开销**：`_sync_quick_buttons` **0.01ms/次**、`_update_lag_display`
   **0.13ms/次** —— 性能影响可忽略；功能上当前不报错、无副作用传播。

   > ⚠ **定时炸弹仍在 —— 此处我曾误判，特此更正**：`_sync_quick_buttons` 里是
   > `getattr(self.ui, btn_attr)`，**无默认值**。`a25fe83` 只移除了 `mw.` 前缀的
   > 3 处**跨对象**调用（`pages.py` ×2、`dialogs.py` ×1），**漏了 `self.` 前缀的
   > 类内调用** —— `ui/main_window.py` 里还有 **13 处**，其中多处是活的：
   >
   > | 调用点所在方法 | 状态 |
   > |---|---|
   > | `__init__` (:180) | ✅ 活 |
   > | `_auto_update_angle_config_from_template` (:1984) | ✅ **活 —— 7 处调用点**（模板变更时触发） |
   > | `_remove_single` / `_remove_range` (:2266 / :2271) | ✅ 活（`_update_lag_display` 内部创建的删除按钮所连接） |
   > | `_on_language_changed` (:3287) | ✅ 活（I18nManager 调用） |
   > | `_on_load_from_template` / `_on_clear_config` / `_on_load_preset` | ❌ 死（0 调用点） |
   > | `_toggle_quick_angle` / `_add_custom_angle` / `_on_step_generate` / `_on_add_range` | ❌ 死（0 外部调用者） |
   >
   > **教训**：grep 调用点必须同时查 `mw.` 与 `self.` 两种前缀，
   > 只查前者会漏掉全部类内调用 —— 这就是我误判「隐患已消失」的原因。

   **剩余待做**（真正的死代码本体，非紧急）：
   - 两个方法本体：`_sync_quick_buttons()` / `_update_lag_display()`
   - `compiled/ui_main_window.py` 里那 49 个控件定义与 4 个 groupbox

   > ✅ **无阻塞，可以做了**。曾以为「删控件定义必须改 `.ui` 重编译，而 `.ui` 与
   > `compiled` 不同步」——**该判断有误，已实测推翻**：`157a2d8`（2026-09-16 04:20）
   > 已恢复同步，重编译产物与现有 `compiled/` **逐字节一致**（`CLAUDE.md` 里那段
   > 「先别重编译」的警告当时已过时，现已同步更正）。
   > 仍须遵守：改 `.ui` → `pyside6-uic` 重编译 → 跑 `gui_integrity_check.py` 验证。

   **清理进度**：
   - ✅ **7 个零引用按钮已删除** —— `btnAddCustomAngle` / `btnStepGenerate` /
     `btnAddRange` / `btnLoadFromTemplate` / `btnClearConfig` / `btnSavePreset` /
     `btnLoadPreset`。做法：从 `.ui` 删定义行 → `pyside6-uic` 重编译。
     验证：MainWindow 构造正常 · 7 个按钮已从 `ui` 对象消失 · 保留控件
     （`configItemsWidget` / `spinCustomAngle` / `btnQuick0` / `groupConfigured`）
     完好 · `gui_integrity_check.py` 12 项全过 · tabConfig 仍是 3 个 tab。
   - ⏳ **其余 42 个控件**（`btnQuick*` ×10 / 6 数值框 / 9 标签 / 4 分组 / 其他）
     —— 与 `_QUICK_ANGLES`、两个方法本体绑定，**必须与 Python 侧同批删**
     （含上面那 13 处 `self.` 调用点）。
   - ⚠ **4 个 groupbox 不能单独删**：它们内部还有**有引用**的子控件 ——
     `groupConfigured` 含 `configItemsWidget`，`groupQuickSingle` / `groupStepGen` /
     `groupRange` 各含 spinbox。只能连子控件一并处理。
   - ⚠ 另注：`_init_quick_angle_buttons()`（`ui/main_window.py:208`）会**动态创建**
     `btnQuick10/20/40/50` 四个按钮（不在 `.ui` 里），且**创建后不连接任何槽** ——
     它们同样是纯装饰，清理时极易漏掉。

   **Blocker? No**

2. **~~`test_gui_e2e.py` 的 `configItemsWidget` 用例~~** —— **已在 `a25fe83` 处理**。
   原 `TestLagDisplayVisibility` 的 4 个用例中，3 个测的是已 removeTab 的孤儿控件
   （`configItemsWidget` 的 label 样式、tabLag 里 6 个 QDoubleSpinBox 与
   `_QUICK_ANGLES` 按钮的对比度），已随产品调用点一并删除；类改名
   `TestGlobalStyleSheet`，保留唯一有效的 `test_custom_qss_applied`。
   e2e 用例数 27 → 24（24 passed）。
   > 若日后要为**新界面**补「暗色主题可见性」覆盖，应针对 `AntennaParamsPage`
   > 的角度 widget 与 `_show_angle_popup` 弹窗，而非这批死控件。
   > 已扫描确认 `test_gui_smoke.py` / `test_gui.py` 无孤儿控件。

3. **`_sync_to_mw()` 零测试覆盖** —— 它被 **10+ 处信号连接**调用（改图表配置、
   频率源、外推选项、稳健模式等都会触发），是图表配置同步的核心路径，
   但 `tests/` 里**完全没有覆盖**。本轮改它时只能靠手写脚本实测验证。
   **Blocker? No**（但值得补：这是本轮唯一改到却无回归保护的真实路径）

4. **完整 smoke 套件需再跑一次** —— 本轮已跑过全量（**85 passed / 0 failed /
   0 errors**，2880s），但那是**替换测试类之前**的数字。替换后用例数为 73，
   应重跑确认。**Blocker? No**

5. **`feedback_client.resend_queue` TOCTOU 竞态** —— 已定位未修。**Blocker? No**
6. **3D 重构批 C-3（查看器 GUI）** —— 见记忆 `3d-refactor-progress`，自 2026-07-11 挂起。
7. **TIS 完整指标** —— 待用户提供灵敏度数据（镜像 TRP）。见记忆 `tis-metrics-todo`。
8. **`ui/dialogs.py` 两处 CSS 被误包 `tr()`** —— 应把 `tr()` 去掉。
9. **`RAGSettingsDialog` 硬编码英文 `"Model:"`** —— `ui/dialogs.py:2222`。
10. **`ui/shell_window.py`** —— 死代码，全项目无实例化点。

---

## G. 验证基线

```bash
python3 gui_integrity_check.py                                   # 12 项
python3 -m pytest tests/test_finalsummary_reader.py -q           # 27 用例（改数据源必跑）
python3 -m pytest tests/test_pipeline.py tests/test_e2e_features.py -q   # 88 用例
python3 -m pytest tests/test_gui_e2e.py -q                       # 27 用例
python3 -m pytest tests/test_gui.py -q                           # 10 用例
python3 -m pytest tests/test_gui_smoke.py -q                     # 73 用例（全量约 48 分钟）
python3 -m pytest tests/test_e2e_features.py::TestThemeI18n -q    # 7 用例（含 i18n 碰撞守护）
```

**改 `src/finalsummary_reader.py` / `src/fs_to_csv.py` 时**：必须补做「与 `read_only=False`
逐字段/逐元素对比」，见 B 节。

**改 i18n 时**：`TestThemeI18n::test_language_switch_refreshes_widget_text` 断言的是
**真实控件文本**，不是 manager 字段。**做证伪验证**：移走 `i18n/trans_table.json` 时它必须变红。

**写 GUI 测试时**（A-5 的教训）：禁止用
`if 控件.isVisible() and 控件.isEnabled(): 控件.click()` 这种写法 —— 不可见就静默略过，
函数跑完即 PASSED，等于没有测试。也不要依赖 `pytest.skip("not visible")` 来表达
「这个控件可能不显示」，那会把**产品缺陷伪装成环境限制**。
正确做法：先确认控件**应该**可见（必要时显式切 Nav/Tab），再断言其可见性并点击。

**判断控件是否已废弃**（本轮用的方法）：
```python
# 祖先链里若有 tabwidget 的 stacked widget, 且该页 indexOf == -1 → 已 removeTab, 永不显示
def orphan(x):
    cur = x
    while cur is not None:
        p = cur.parentWidget()
        if p is None: return False
        if p.objectName() == 'qt_tabwidget_stackedwidget':
            tw = p.parentWidget()
            if isinstance(tw, QTabWidget) and tw.indexOf(cur) == -1:
                return True
        cur = p
    return False
```
> 注意 `ui.tabLag` 这类引用**不可靠**：`_make_tab_scrollable` 会 reparent，
> 原 widget 会变成空壳（`findChildren` = 0），真正内容在匿名容器里。
