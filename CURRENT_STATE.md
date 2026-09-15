# CURRENT STATE — 2026-09-16

**Source:** 会话承接自 `fbf97c7`（上一轮 distill 的状态固化）。
**Branch:** master · **基线:** `fbf97c7` · 其上 9 个提交，**全部已 push**（HEAD = origin）。
工作区: 仅 `scripts/check_i18n.py` / `scripts/update_i18n.sh` 待提交（本次收口产物）。

---

## A. 本次会话完成的工作 — 9 个提交

```
09e9615  feat(i18n): RspPickerDialog + 主题下拉接入翻译（P4）
08fc2fe  feat(i18n): graph_viewer.py 接入翻译 + 修 3 个 bug（P4 第 1 个文件）
d23f543  feat(i18n): SystemSettingsDialog 接入翻译 + 补 254 条英文译文
dccd705  feat(i18n): 拼接串降级 + 共享文本源接入
3ec9e86  feat(i18n): 通用重翻译刷新器 — 切语言即时刷新全部常驻界面
098df38  feat(i18n): 反查表生成与打包 — 运行时语言切换的基础设施
53ffe78  fix(i18n): switch() 先校验 .qm 再动现状 + 修每次切换的 QTranslator 泄漏
fff0aa4  chore: 同步 verify-manifest 控件/模块清单
2df5113  fix(gui): takeRow 替代 removeRow — 修复语言切换只翻译前 5 行
fbf97c7  ← 基线
```

**两条主线**:

1. **`2df5113`** —— 起点。修一个「悬垂引用」bug: `formInput.removeRow(1)` 会**删除**该行
   控件, 但 `self.ui.lblTemplate` / `btnBrowseTemplate` 的包装器还挂着, 而 compiled
   `retranslateUi:530` 仍对它们 setText → **每次切语言都在此抛错并中断整个函数**,
   后面几百行控件永不翻译。实测 51 个带文本控件只成功翻译 1 个。
   > 修法: `takeRow()`(只摘除不删除)。详见记忆 `dangling-widget-breaks-retranslate`。

2. **`53ffe78` → `09e9615`** —— 语言切换机制的**全量重建**。原状是「只有 `.ui` 生成的
   MainWindow 控件会刷新」, 3 个常驻页面 + GraphViewer + 手写导航/按钮全部停在旧语言。

---

## B. i18n 机制 (新增, 后续维护必读)

### 架构

```
控件当前文本 ──反查(context, 文本)──> 源串 ──forward(context, 源串)──> 新语言文本
```

- **`i18n/trans_table.json`** —— 构建期产物, 由 `scripts/build_i18n_table.py` 从
  `app_en_US.ts` 生成 (context 键控, 仅存英译; zh_CN 恒等故不存)。
  **必须随包发布** (spec datas 已加): `.ts` 不进 EXE, 而 `QTranslator` 不提供反向映射。
- **`I18nManager._refresh_all(app, from, to)`** —— 遍历 `topLevelWidgets`, 对每棵子树:
  ① `_refresh_widget_tree` 重翻手写控件 ② `ui.retranslateUi` 重翻 `.ui` 控件
  ③ 对**子树中每个** widget 调 `_on_language_changed()` 钩子 (动态文案重算)。
  > ③ 必须遍历整棵子树 —— GraphViewer/GraphDataTab 是子控件, 只调顶层够不到它们。
- **接入点**: `I18nManager.switch()` 内**同步**执行。不用 `changeEvent`, 因为
  `installTranslator` 投递 LanguageChange 是**异步**的 —— 依赖它会让「切换完成」与
  「界面已刷新」之间出现窗口期, 调用方和测试都可能读到旧语言 (这正是旧测试假通过的成因)。

### 覆盖的文本载体 (11 类)

QLabel / QAbstractButton / QGroupBox / QLineEdit **placeholder** / QWidget toolTip /
QComboBox item / QTabWidget tab / QListWidgetItem / QTableWidget **表头** / QAction /
QAbstractSpinBox 前后缀 / 窗口标题。

**刻意不碰**: `QLineEdit.text()`、QTextEdit/QPlainTextEdit、QTableWidget **数据单元格**、
editable combo 的 lineEdit —— 改了会破坏用户数据。

### 反查碰撞 (设计要点)

- zh_CN 是**恒等翻译** → 中文态下「控件文本 == 源串」, 零碰撞。
- 英文态靠 **context 优先**反查。实测同 context 内碰撞当前 = **0 条**。
- 跨 context 兜底 (`_reverse_flat`): 仅当候选**唯一**才采用, ≥2 则放弃并 debug。
- 守护测试 `tests/test_e2e_features.py::TestThemeI18n::test_no_reverse_collision_within_context`
  —— 新增译文一旦引入同 context 碰撞即变红。

### 拼接串降级

`"📂 " + self.tr("输入输出")` / `"<b>" + tr(...) + "</b>"` / `"NHPRP / NHPIS " + tr(...)`
使控件文本 ≠ 源串。引擎内建候选降级: 精确 → 去 HTML 标签 → 剥首尾非文字字符 →
首个中文到结尾。命中后把核心替换回原文, 前后缀完整保留。

> **关键**: 拼接成分在**两个方向上不对称**。zh 态 `"📂 输入输出"` 剥前缀即可;
> en 态 `"📂 Input/Output"` 里没有中文可抽, 只能靠剥首尾非文字字符。
> 只做「抽中文核心」会让 en→zh 还原失败 (实测还原率掉到 5/7)。

---

## C. 踩过的坑 (下个会话务必先读, 都是实际发生过的)

| # | 坑 | 现象 | 正解 |
|---|---|------|------|
| 1 | **class body 无 self** | `class X: NAME = self.tr("...")` → **导入即 NameError**。`py_compile` 查不出 (语法合法) | ①在消费点翻译(推荐) 或 ②`QCoreApplication.translate("X", ...)` |
| 2 | **class body 包 translate 会冻结** | 在 `ThemeManager.ALL_THEMES` 里包 translate → import 期求值, 那时 QApplication 还没建, 译文被**冻结**, 语言切换失效 | 在**消费点**用 `tr_shared(name, "ThemeManager")` |
| 3 | **显示名与内部键混用 → 功能失效** | `VIEW_PRESETS` 的英文键既作字典键又作下拉显示文本, 查找用 `currentText()`。切语言后显示名被反查改写成 `'前'` → `name not in VIEW_PRESETS` → **选预设无任何效果** | 显示名进 `itemText`、内部键进 `itemData`, 查找用 `currentData()` |
| 4 | **`.ts` 含换行的源串是跨行的** | 行级改写脚本假设 `<source>...</source>` 同行 → 跨行时指针停留在上一条, 把译文写进**别的条目**, 造成 5 处静默错译 | 跨行感知解析 (累积到 `</source>`); 见 `scripts/build_i18n_table.py` 与提交 `d23f543` |
| 5 | **lupdate 是静态扫描器** | `self.tr(VAR)` 提取不到 (重扫报 "0 new") | 字面量必须写在调用点; 动态来源用 `ui/i18n_catalog.py` 登记 |
| 6 | **`self.tr(self.tr(...))` 双重嵌套** | 内层已翻译, 外层把译文当源串再翻 | 一层即可 |
| 7 | **`.ts` 不进 EXE** | 运行时读不到 `.ts` | 反查表走构建期 JSON 产物 + spec datas |
| 8 | **门禁/测试在资源争抢下会假死** | 门禁曾被 900s timeout 杀掉, 同一份代码随后干净跑完 ~50s | 跑前确认无残留后台任务; 用 `python3 -u` + 直写文件, 别用管道 (`| tail` 会丢缓冲) |
| 9 | **批量写入译文时要转义 `"`** | 只转义 `<`/`>`/`&` 时, 下次 lupdate 会把 `"` 规范化成 `&quot;`, 产生 1 行无谓 churn (功能无影响) | 写入时把 `"` 也转义为 `&quot;`, 或接受 lupdate 自愈 |

### 运行时守卫

`I18nManager._load_table()` 在发现**同 context 内反向碰撞**时会 `log.warning`。
**这不是装饰** —— `d23f543` 那次就是它报出了 5 处静默错译。看到该告警请立即查译文。

---

## D. 剩余工作 — P4 字面量清扫

**工具已就绪**:

```bash
python3 scripts/check_i18n.py          # 漏包守卫, 列出所有未包 tr() 的中文字面量
bash scripts/update_i18n.sh            # lupdate → lrelease → 生成反查表 → 漏包检查
```

> `update_i18n.sh` 本次已重写: 旧版只扫 3 个文件 (**照跑会丢掉约 61% 译文条目**),
> 且硬编码本 checkout 不存在的 `.venv`。新版含完整清单 + PATH/Windows 双工具链回退。

**进度** (本次已完成 4 个文件):

| 文件 | 状态 | 待新增译文 |
|---|---|---|
| `ui/graph_viewer.py` | ✅ 完成 | — |
| `ui/rsp_picker_dialog.py` | ✅ 完成 | — |
| `ui/theme_manager.py` | ✅ 完成(消费点翻译) | — |
| `ui/window_manager.py` / `ui/splash_screen.py` | ✅ 无 UI 字面量 | — |
| **`ui/dialogs.py`** | ⬜ 未做 | ~196 |
| **`ui/pages.py`** | ⬜ 未做 | ~140 |
| `ui/widgets.py` | ⬜ 未做 | ~37 |
| `main.py` | ⬜ 未做 | ~21 |

**`scripts/check_i18n.py` 当前报 439 处** (含日志/正则等不该 tr 的, 实际低于此)。

### 开工前必做

`dialogs.py` / `pages.py` 里下拉框最多, 是**坑 #3 的高发区**。每个下拉框先确认:
**它是按 `itemData` 还是按 `currentText()` 查找?** 按 text 的必须先改成 data,
否则翻译会静默破坏功能 (选了没反应)。

### 包裹脚本

`/tmp/wrap_file.py` (临时, 未入库) 已具备: docstring/日志/语言名跳过、
f-string 识别、**class body AST 守卫** (坑 #1)。若 /tmp 被清, 按上述规则重写即可。

---

## E. 交付阻塞项

**给 Ralab 的 EXE 需要重打包** —— 现行 `1.4.exe` 缺少本次全部 9 个提交
(以及上一轮的 `ec94b4d` / `ce1fb9d`)。

```bash
cd /mnt/d/cc/antenna-post-processor && \
/mnt/d/Python312/python.exe -m PyInstaller antenna_post_processor.spec --clean --noconfirm
```

⚠️ **不要用 `build.bat`** —— 它会跑 `generate_trial_config.py`, 把 `license.json`
覆盖成试用许可, 冲掉 Ralab 的正式许可 (备份在 `license.json.trial_backup`)。

⚠️ **打包前确认 `i18n/trans_table.json` 是最新的** (随包发布, 缺失则运行时切换
退化为单向)。`bash scripts/update_i18n.sh` 会生成它。

---

## F. 其他未决项 (承接自上一轮, 状态未变)

1. **`feedback_client.resend_queue` TOCTOU 竞态** —— 已定位未修。`src/feedback_client.py`
   149 行有 `if not _QUEUE_PATH.exists(): return` 守卫, 而 168 行有 `unlink()` →
   并发时一个删掉另一个正在 `read_text()` 的文件。**Blocker? No**。
2. **GUI 批次剩余用例** —— `test_gui.py` / `test_e2e_features.py` 本会话已全过;
   `test_gui_e2e.py` / `test_gui_smoke.py` 的部分用例仍未覆盖。**Blocker? No**。
   > 跑法: 加 `-v` 并直接写文件, 别用 `| tail` (见坑 #8)。
3. **3D 重构批 C-3 (查看器 GUI)** —— 见记忆 `3d-refactor-progress`, 自 2026-07-11 挂起。
4. **TIS 完整指标** —— 待用户提供灵敏度数据 (镜像 TRP)。见记忆 `tis-metrics-todo`。
5. **`ui/dialogs.py` 两处 CSS 被误包 `tr()`** —— `"font-size: 18px; font-weight: bold;"`
   与 `"font-weight: bold; font-size: 14px;"`。本次刻意**未**为它们编译文 (那是错误的
   tr 用法)。应把 `tr()` 去掉。
6. **`RAGSettingsDialog` 硬编码英文 `"Model:"`** —— `ui/dialogs.py:2222`。同类问题已在
   `SystemSettingsDialog` 修掉 (`:2501`), 此处未动 (超出当时范围)。

---

## G. 验证基线 (修改 i18n 相关代码后必须全绿)

```bash
python3 gui_integrity_check.py                          # 12 项
python3 -m pytest tests/test_gui.py -q                  # 10 用例
python3 -m pytest tests/test_e2e_features.py::TestThemeI18n -q   # 7 用例 (含碰撞守护)
```

`TestThemeI18n::test_language_switch_refreshes_widget_text` 断言的是**真实控件文本**
(QPushButton/QLabel/QCheckBox/QTabWidget), 不是 manager 字段 —— 旧版只断言
`current_language()` 被赋值, 对界面是否真变零覆盖, 是这个缺陷长期潜伏的原因。
**做证伪验证**: 移走 `i18n/trans_table.json` 时该测试必须变红。
