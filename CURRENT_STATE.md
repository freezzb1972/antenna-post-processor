# CURRENT STATE — 2026-09-15 21:54

**Source:** session `6158e3f2` (2026-09-15 10:20–13:46 UTC) — 该会话在 13:40 因 **"Prompt is too long"** 死亡, 上下文溢出前**未能产出本文件**。
**本次 distillation** 由外部会话读 JSONL 转录 (2.8 MB) 完成, 并顺手回收了两个它没来得及读的结果 (GUI 批次失败名单 + 基线比对)。

**Branch:** master · **基线提交:** `ce1fb9d` (fix: test_pipeline 过期测试 + GraphDataTab 陈旧数据)
其上 1 个 distill 提交 = 本文件所在提交 (未 push)。**此处故意不写自己的哈希** —— distill 提交每次 amend 都会换哈希, 写死必然自指过期 (本行曾写 `12a7363`, 即被 amend 前的旧值)。用 `git log -1` 取当前值。
工作区: 仅 ` D .claude/skills/gui-vision` + 未跟踪产物, 无待提交源码。

---

## A. 本次会话 (6158e3f2) 完成的工作 — 8 个提交, 全部已 push

```
ce1fb9d  fix: 修复 test_pipeline 两个过期测试 + GraphDataTab 陈旧数据
ec94b4d  fix(charts): 图形数据页静默空白 — 有图表时补存 _raw_data + 空数据显式提示
8d559e9  fix(gui): SplashScreen 补 close() — 修复许可无效时 EXE 启动即崩溃
590c762  fix(help): 语义索引只加载本地缓存模型, 不再联网下载阻塞界面
ef9fd3c  fix(gui): 线程安全停止 + 门禁脚本修复 + manifest 补齐
b0c04fe  fix(gui): changeEvent 防御窗口销毁期的 LanguageChange 广播
9d14597  fix(i18n): 语言设定持久化 — 启动读配置 + 切换写回配置
ee6a800  ← 基线 (本节改动之前)
```

## Decisions made (why) — 只记非显而易见的部分

1. **语言"没生效"是三件被混在一起的事** —— ①**运行时切换**(设置里点按钮)**一直是好的**(`changeEvent`→`retranslateUi`); ②**启动初始语言**只跟系统 locale, 从未读配置; ③**持久化**从未写入。
   Windows 上**永远发现不了**(系统 locale 本就是中文, 重启后自然还是中文); 到 WSL `LANG=C.UTF-8` → `QLocale.system().name()=="C"` → 落 en_US 才现形。**不是回归, 从 v1.0.0 就潜伏**。
   - 附带纠正: `antenna_config.json` 里的 `"language": "zh_CN"` **不是"用户设的", 是恒定默认值** —— QSettings 键从未被写过, `s.value("language","zh_CN")` 永远返回默认。看到配置里写着 zh_CN 会误判"已生效"。
   - 修法 3 处: `main.py` 传 `cfg_mgr.config.language`; `i18n/i18n_manager.py` init 支持显式语言(无对应 .qm 时回退系统 locale); `ui/dialogs.py` `_on_toggle_lang` 写回 config + `save()`。

2. **`retranslateUi` 崩溃 = 异步事件撞上已回收的 C++ 对象**。`LanguageChange` 由 `installTranslator` **异步投递**, 窗口销毁期间事件仍会到达, 此时子 widget 的 C++ 对象已被 Qt 回收 → `RuntimeError: libshiboken: Internal C++ object (QLabel) already deleted`。
   用 `try/except RuntimeError` 防御(只吞 RuntimeError, 不吞别的)。

3. **`_on_stop` 会崩程序** —— 此前 `quit()` → `wait(3000)` **不检查返回值** → `self._thread = None` → 仍在运行的 QThread 被 GC → Qt `abort`。这就是用户 EXE 截图里的 `QThread: Destroyed while thread is still running`。
   提取 `_stop_thread_safely()` (quit → wait → 超时 terminate 兜底), 与 `closeEvent` 共用(相似度 >80% 按项目规则必须合并)。

4. **`SemanticIndex.build()` 挂死 — 第一版诊断是错的**。初判"在下载 470MB 模型"**不成立**: 主模型目录**已缓存**, 缺的是它引用的**底层 transformer 子模型**; 且基于错误判断写的第一版修复(运行时设 `HF_HUB_OFFLINE=1`)**完全无效** —— `huggingface_hub` 在**模块导入时**就把该变量读成常量(`constants.py:185`), 运行时设置太晚。
   **必须用运行时参数 `local_files_only=True`** (SentenceTransformer 5.6.1 支持)。修复后 build() 从"无限挂起" → **5.82s 正常降级到 BM25**。
   - 真实影响: `HelpDialog._on_search` 是**同步**调用 → 真机上首次勾"语义搜索"点搜索会**冻住整个界面**。

5. **`SplashScreen.close()` 缺失 —— 开发模式分支掩盖的 EXE 专属崩溃**。`SplashScreen` 是包装类(不继承 QWidget), 只代理 `advance()`/`finish()`, 缺 `close()`; `main.py` 在许可校验失败时调 `splash.close()` 转激活流程 → `AttributeError`。
   `python3 main.py` **永远走不到那行**(非 frozen 时免许可直接 `return True`), 所以本地/offscreen 都测不出。**基线逐字复现了截图里的错误**。
   - 触发条件: 试用 `trial_start: 2026-07-12` + `trial_days: 60` → **2026-09-10 到期**, 会话当天已过期 4 天, 于是第一次走到该行。

6. **图形数据页静默空白 —— 两个开关无耦合**。「启用图表查看」只管**显示**, 「中间数据输出」才控制 pipeline 是否存矩阵(`store_matrices=out_data`)。
   用户**取消勾选中间数据、保留图表查看**时: pipeline 只存 `_chart_*`(合成增益), 不存 `_raw_data` → `extract_graph_data` 只读 `_raw_data` → `if raw is None: continue` → **静默跳过全部数据, 页面空白且零提示**。
   - 默认路径本来是通的 —— `_auto_check_output_flags()` 在"有图表"时会**自动勾上**中间数据。
   - 修法(用户选 A+B): **A** 在生产端 `pipeline.py` 的 `if store_matrices or want_render:` 分支内补存 `_raw_data` —— **不在消费端回退**, 因为 `_chart_*` 没有分量和相位, 回退会让 E_θ/E_φ/相位图仍然空白; **B** `GraphDataTab` 拿到空数据时显式提示。

7. **测试套件的两个"卡死"根因不同**:
   - `test_e2e_features.py` 卡死 = 上面第 4 条(联网下载)。
   - `gui_integrity_check.py` 卡死 = **门禁脚本自己缺 `QMessageBox` mock** —— 它模拟点「开始」但没勾任何输出类型, `_on_start` 弹**模态框**没人接(offscreen 下无人点确定) → 永久挂起。**产品代码这行是对的**, 是脚本缺 mock; 补上勾选后暴露脚本清理段 `wait(3000)` 不检查返回值 → SIGABRT。两处都修在脚本里。

8. **PyInstaller 不能交叉编译**。在 WSL 跑 `pyinstaller` 只产出 **ELF Linux 二进制**(且产物名无 `.exe`) —— 这不是"失败", 是必然。
   要出 Windows EXE 必须用 Windows 的 Python: `/mnt/d/Python312/python.exe -m PyInstaller ...`(从 WSL 可直接调, 但**必须在 `/mnt/d/...` 下执行**, 否则 Windows 程序看到 `\\wsl$\` UNC 路径会出问题)。
   - **PKG 阶段之后终端不再输出是正常现象**, 不是卡住 —— 用 `dist/` 产物时间戳 + `EXE-00.toc` 判断完成。

9. **`build.bat` 会毁掉 Ralab 许可** —— 它第 1 步跑 `generate_trial_config.py`, 而该脚本末尾会**重新生成并覆盖 `license.json`**(写成 "Trial User" 试用版)。**打包必须跳过 build.bat**。

10. **Ralab 许可走"独立文件 + 内嵌"双轨** —— 单独文件交付让**续期只发一个 json、不用重发 EXE**; 内嵌让客户**零配置**。两者并存(spec 已配 `datas=(license.json, '.')`; onefile 模式下 `auto_load()` 第一步就查 `sys._MEIPASS`, **优先级高于** EXE 同级目录和用户主目录)。
    - ⚠️ 搜索路径是**固定文件名** `license.json` / `license.key` / `.antenna_license` / `~/.antenna_pp_license.json` —— 归档名 `license_Ralab_2027-09-15.json` **不会生效**, 交付件必须叫 `license.json`。

## B. 许可 / 交付状态 (用户实际用途: 交付客户 Ralab)

| 项 | 值 |
|---|---|
| 客户 | **Ralab** |
| 有效期 | 2026-09-15 → **2027-09-15** (365 天) |
| 机器绑定 | **无**(拿到客户 machine ID 后可补签绑定版) |
| 验签 | PASS (ECDSA P-256) |
| 交付件 | `output/deliver_Ralab/license.json` (整个 `output/` 已被 .gitignore 忽略) |
| 归档件 | `output/license_Ralab_2027-09-15.json` |
| 内嵌用 | 项目根 `license.json` **已被替换成 Ralab 版** |
| 试用备份 | `license.json.trial_backup` = Trial User / 2026-07-30 |

⚠️ **`license.json.trial_backup` 不在 .gitignore 里** —— `.gitignore:17` 是精确匹配 `license.json`(**无通配符**), 所以备份文件出现在 `git status` 未跟踪列表, `git add -A` 会把它提进仓库。建议 `mv` 到 `output/` 或加一行 `license.json.*`。

## C. 已构建的产物 (已核实)

- `dist/AntennaPostProcessor1.4.exe` — **PE32+ Windows GUI x86-64** ✅, Sep 15 19:53 构建, 内嵌 `license.json` = **281 字节 = Ralab 版** ✅ (证法: `archive_viewer -l` 列表条目大小)
  - 构建时间晚于 `8d559e9`(SplashScreen 修复) → **含该修复** (据时间推断, 未逐字节验证)
  - 但**早于** `ec94b4d` / `ce1fb9d` → **不含**图形数据页修复和测试修复
- `dist/AntennaPostProcessor`(144 MB, 无扩展名 Linux 产物)已被删除
- 历史版本 `- 副本.exe` / `1.1` / `1.2` / `1.3` 均未被触碰

## D. 测试状况 (关键 — 死掉会话没来得及汇报的部分)

| 批次 | 用例数 | 结果 |
|---|---|---|
| `test_e2e_features.py` 单独跑 | 24 | ✅ 24 passed (266s) |
| 纯逻辑批次 (8 个文件) | 177 | ✅ 175 passed, 2 failed → **2 个已修** |
| **GUI 批次 (5 个文件)** | **175** | ❌ **timeout 2700s 在 49% (85/175) 被杀**, 累积 7 F + 1 E |
| 最初全量 | ~311 | ❌ timeout 3000s 在 40% 被杀 |
| GUI 批次复跑 (会话末) | — | ❌ 仍 timeout 在 41% 被杀 → **确认该批次在 WSL 下跑不完, 非偶发** |

**GUI 批次的 7 个失败 —— 名字原本拿不到**(`-q` 只在跑完时打印, 而它被 timeout 杀了)。
本次 distillation 用 `--collect-only` 复现收集顺序(无随机化插件, 顺序稳定)反查位置, 再实跑复现:

| # | 用例 | 真实原因 |
|---|---|---|
| 31 | `test_gui.py::TestTemplateReadOnly::test_template_persists_across_restart` | `assert '' == '/test/persis...template.xlsx'` 模板路径未持久化 |
| 39 | `test_gui_e2e.py::TestFileInput::test_csv_filter_in_dialog` | `PermissionError: [Errno 13] '/output'` ← **测试硬编码绝对路径** |
| 41 | `test_gui_e2e.py::TestFileInput::test_template_not_excel_shows_warning` | 期望含 '模板'/'Excel', 实得 '请至少选择一种输出类型...' |
| 49 | `test_gui_e2e.py::TestProgressBar::test_progress_bar_updates` | `'[5%] 处理中...' == '处理中...'` 进度标签格式变了 |
| 51 | `test_gui_e2e.py::TestProgressBar::test_progress_zero` | `assert 100 == 0` |
| 70 | `test_gui_health.py::TestLayoutGeometry::test_no_widget_overlap_in_main_area` | `RuntimeError: libshiboken: QPushButton already deleted` |
| 84 | `test_gui_health.py::TestPerformanceBaseline::test_mainwindow_creation_time` | 性能基线, **对负载敏感 → flaky**(复跑时通过) |

**基线比对已完成**(死掉会话承诺过但没做): 在 `ee6a800`(本轮改动之前)用 git worktree 重跑同样 6 个可复现用例 → **6 failed, 与当前完全一致**。
→ **这 6 个 GUI 失败全部是既有问题, 与本会话 8 个提交无关。本轮无回归。**

**顺带暴露一个真 bug(未修)**: `src/feedback_client.py` `resend_queue()` 抛 `FileNotFoundError: ~/.antenna/feedback_queue.jsonl` —— 未捕获的**后台线程异常**。
同函数 149 行**有** `if not _QUEUE_PATH.exists(): return` 守卫, 所以这是 **TOCTOU 竞态** —— 并发调用时一个 `unlink()`(168 行)删掉了另一个正在 `read_text()` 的文件。

## E. Files touched (本会话 8 个提交)

- `i18n/i18n_manager.py` — init 支持显式语言 + 无 .qm 时回退系统 locale
- `main.py:157` — `I18nManager.init(app, cfg_mgr.config.language)`
- `ui/dialogs.py` — `_on_toggle_lang` 写回 config + `save()`
- `ui/main_window.py` — ① `changeEvent` 加 RuntimeError 防御 ② 提取 `_stop_thread_safely()`(2717 行)
- `ui/splash_screen.py:63` — 补 `close()`
- `src/help_engine.py:200` — `local_files_only=True`(去掉无效的 HF_HUB_OFFLINE)
- `src/pipeline.py:580` — `want_render` 时也存 `_raw_data`
- `ui/graph_viewer.py` — `GraphDataTab` 空数据提示 + 补 `load_data()`(修陈旧数据)
- `tests/test_pipeline.py` — 2 个过期测试
- `gui_integrity_check.py` / `verify-manifest.json` — 门禁修复 + manifest 补齐

## F. Open questions

1. **GUI 批次剩余 90 个用例从未跑过**(49% 之后被 timeout 杀掉)。`test_gui.py` / `test_gui_e2e.py` / `test_gui_health.py` 的大部分未覆盖。**Blocker? No** —— 但是"未知的未知"。
2. **发给 Ralab 的 EXE 需要重新打包** —— 当前 `1.4.exe` 缺 `ec94b4d`(图形数据页)+ `ce1fb9d`。**Blocker? Yes(交付前)**。
3. **`graph_viewer.py` i18n 缺口** —— 该文件 `tr()` 仅 1 处, **裸文本 98 处**, 且**不在 `.ts` 扫描范围**(只收录 9 个 ui 文件)。对照 `ui/dialogs.py` 有 **207 处**同样裸文本(它已在扫描范围内却仍是裸的)→ **项目级技术债, 建议单独立项**, 不要顺手塞进功能修复。**Blocker? No**。
4. **`feedback_client.resend_queue` TOCTOU 竞态** —— 已定位未修。**Blocker? No**。
5. **3D 重构批 C-3 (查看器 GUI) 仍挂起** —— 见 G 节, 自 2026-07-11 起待用户拍板。
6. **TIS 完整指标** —— 待用户提供灵敏度数据样本(镜像 TRP)。已记 `tis-metrics-todo`。

## G. 遗留计划 — 3D 方向图统一重构 (进行到 C-3, 自 2026-07-11 挂起)

详细进度见记忆 `3d-refactor-progress`(每会话自动加载, 含每 commit SHA + C-3 逐条)。

**已完成并 push**: 批A(半径公共函数修形状+去笛卡尔轴+roll) `0067255` · B-1(视角三元组/DYN/per-instance) `c798386`
· B-2(相位/TotalPower数据+修rhcp降采样bug) `026c0b3` · B-3(报告3D弹窗roll/DYN/7预设) `8248719`
· 修复(模式切换崩溃+DYN自动) `f8e3403` · 模式映射对齐EMQuest `c77e6ab` · C-1(注册表pattern_types) `8a7343e`
· C-2(查看器10类型+3×3/2×2+1布局) `59fae0f`。

**下一步 = 批C-3 (`ui/graph_viewer.py`, 最大剩余块)**:
per-子图数据类型下拉 · 切2D工具(3D→极/直角2D, 点选子图→工具栏) · 勾选修复(不整片禁用) ·
6→7预设下拉+roll数值框 · 联动↔分别控制 · 删死代码(`_build_ctrl_bar`/`_phase2_bar`/`_anim_bar`) · 相位类型渲染。

**3D 关键决策 (why)**:
1. 半径用**标准算法**(峰值-DYN归一), **DYN 默认自动自适应**(`dyn_auto=True` —— 报告里看不到数据, 难设具体值)。
2. 视角三元组 (el/az/roll), 周期 360; **报告 per-instance**(每图表独立视角, 走 `ChartInstance.params` + `image_key`)。
3. 数据类型**统一注册表**(`pattern_types` 11 类); 无相位 → AR/RHCP/LHCP/CP-XPI/相位类**优雅降级**。
4. 三测试模式(对齐 EMQuest 页 366-369): 无源 gain/Eθ/Eφ/AR + 频率曲线; 发射+EIRP 去频率曲线; TIS 只 gain/Eθ/Eφ。
5. 查看器与报告 3D **共用 `build_3d_surface`** → 所见即所得。

## H. Next actions (1–3)

1. **重新打包 Windows EXE 交付 Ralab**(当前 HEAD `ce1fb9d`, 含全部 8 个修复):
   ```bash
   cd /mnt/d/cc/antenna-post-processor          # 必须在 /mnt/d 下执行
   /mnt/d/Python312/python.exe -m PyInstaller antenna_post_processor.spec --clean --noconfirm
   ```
   ⛔ **不要跑 `build.bat`** —— 它会用试用许可覆盖 `license.json`。
   **验证**: 把 `dist/AntennaPostProcessor.exe` 单独放进**空目录**运行 → 不弹激活框 = 内嵌成功; 或 `archive_viewer -l` 查包内 `license.json` 是否为 **281 字节**。
2. **补跑 GUI 批次剩余 90 个用例** —— 建议加 `-v`(逐用例打印名字), 这样即便再超时也能知道卡在哪/失败在哪, 而不是像这次只能靠 `--collect-only` 反查。
3. **决定是否处理 feedback_client 竞态 / graph_viewer i18n 技术债**(建议后者单独立项)。

## I. Discarded (noise)

- ❌ 死掉会话的**第一版**语义索引诊断("在下载 470MB 模型")—— **错的**; 以及基于它的第一版修复(`HF_HUB_OFFLINE=1`)—— **无效**(模块导入时已求值)。真因见 Decisions #4。
- ❌ "全量 311 用例" —— 是估计值; GUI 批次实测 **175**(先前说的 134 也不对)。全量实际收集数未核实。
- ❌ 时长估计"25–35 分钟" → 实测差得远(按当时速度全量约 125 分钟)。测试受 CPU/IO 竞争影响极大, **不要给估时**。
- ❌ `grep -a "Ralab" dist/AntennaPostProcessor` 判断内嵌 —— **无效**(CArchive 压缩, 对照组也找不到); 正确方法 `archive_viewer -l` 看条目大小。
- ❌ `archive_viewer` 的 `X` 提取命令需要交互输入文件名, 脚本里输入序列易错 → 改用 `-l` 列表模式。
- ❌ 门禁 segfault(退出码 139)—— 是后台测试抢内存所致, 清理后重跑 **12 项全绿**; 不是代码问题。
- ❌ 同进程内创建两个 `QApplication` 导致 splash 端到端验证失败 —— 脚本自身问题, 拆开跑即通过。
- ❌ `verify-manifest.json` 用 `json.load`+`dump` 整体重写 → 打乱既非字母序的 `dynamic_widgets` 列表, 产生 17+/14- 无谓 diff → 改回**只追加不重排**。
- ❌ gui-vision 对"有无坐标轴/形状"给自相矛盾答案 → 不可靠, 改用数值证明(极/赤道 R 比)+ 代码确定性(`set_axis_off`)。(旧)
- ❌ matplotlib 3.11: `cm.get_cmap` 移除 → 用 `matplotlib.colormaps[...]`; CJK 需显式注册字体文件(雅黑)。(旧)
- ❌ push 数次 TLS 超时 → 重试成功。(旧)

---

### WSL 环境备忘 (本次会话确认, 对后续调试有用)

```bash
cd /mnt/d/cc/antenna-post-processor && python3 main.py     # WSLg 直接出窗口
LANG=zh_CN.UTF-8 python3 main.py                          # 强制中文界面 (Qt 自解析 LANG, 不需要系统装 locale)
QT_QPA_PLATFORM=xcb python3 main.py                       # 万一 Wayland 渲染有问题时切 X11
QT_QPA_PLATFORM=offscreen python3 gui_integrity_check.py  # 无头跑门禁
QT_QPA_PLATFORM=offscreen python3 gui_integrity_check.py --quick   # 仅 G1-G3, 不跑真实 pipeline
```

WSLg 图形 ✅ · Python 3.12.3 (系统 Python, 依赖在 `~/.local`) · 依赖全齐 · 中文输入法**不可用**(无 fcitx/ibus)。
`license.json` / `trial_config.json` 按 **CWD** 找 → **必须在项目根目录运行**。
