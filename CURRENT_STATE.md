# CURRENT STATE — 2026-06-27

**Source:** session 优化天线参数计算app
**Phase:** Design approved → Step 1 implementation starting (WSL → ARM handoff)
**Last commit:** `a5b7076` docs: 执行栏共享+预览处定位+同步循环防护 — review 修复
**Updated:** 2026-06-28

## Active plan
- **Design doc:** `docs/superpowers/specs/2026-06-27-master-detail-design.md` (19 sections)
- **Branch:** master

## Key decisions (17)

1. **Master-Detail 布局** — 左侧 QListWidget + 右侧 QStackedWidget 3 页切换 (EMQuest 风格)
2. **3 主标签页** — 处理设置 / 计算结果 / 图表查看（删 tabLag/tabPlot/tabCalc）
3. **Dialog → Widget 嵌入** — CalcParamsDialog→AntennaParamsPage, PlotConfigDialog→ChartSettingsPage, 实时同步
4. **Word 风格 Shell** — Shell 启动自动新建任务窗口, Ctrl+N 新建
5. **.ant 任务文件** — ZIP 打包(数据副本+配置+结果), 可选保存, 双击秒开
6. **模板预设管理整合** — 模板识别合并入, 工具菜单唯一入口
7. **数据修复重构** — 扫描→预览→选方法→执行
8. **路径损耗补偿独立** — PathLossDialog, 含 Re/Im 检测
9. **RSP 预设 → 工具菜单** — 从系统设置移出, 连接到实际对话框
10. **LLM 智能设置从文件菜单移除** (已在系统设置内)
11. **参数双层体系** — 必需参数: ReportPreviewDialog↔AntennaParamsPage 双向同步; full_report 仅面板
12. **公共模块提取** — `src/ui_utils.py`(纯函数) + `ui/widgets.py`(AnglePickerWidget 等)
13. **i18n 全覆盖** — self.tr() 包裹, 英文零中文
14. **菜单重组** — 文件(4) + 工具(8含3分组) + 窗口 + 帮助
15. **图表空状态** — 深色背景占位 (非白屏)
16. **执行栏** — 在 tabConfig 外部, 跨 3 主标签页共享
17. **同步防护** — blockSignals(True) 防级联更新循环

## Review findings (code-review agent)
- ✅ 执行栏位置: 确定在 tabConfig 外部共享
- ✅ 预览处: 明确为 ReportPreviewDialog (独立弹出对话框)
- ✅ 同步循环: 加 blockSignals 防护
- ✅ "预览处" 全部改为 ReportPreviewDialog 保持命名一致

## Files to modify
| 文件 | 改动 |
|------|------|
| `ui/main_window.py` | 重度重构 (~2387→~1800 行) |
| `ui/dialogs.py` | 2 Page + 3 Dialog 改造 |
| `ui/widgets.py` | **新建** |
| `src/ui_utils.py` | **新建** |
| `ui/rsp_picker_dialog.py` | 连接对话框 |
| `ui/template_recognizer.py` | 整合入预设管理 |
| `ui/compiled/ui_main_window.py` | **不改** |

## Status (2026-06-28)
- ✅ 设计审批通过
- ✅ 代码已推送 GitHub (a5b7076)
- 🔄 移交给 ARM 上的 Claude 继续实施
- 📋 ARM Claude 启动指令: 按设计文档第九章 5 步集成策略执行 Step 1

## ARM 端启动指令
```
git pull && 按照 docs/superpowers/specs/2026-06-27-master-detail-design.md
第 9 节「集成策略」执行 Step 1 — 建地基：
1. 创建 src/ui_utils.py（纯函数 build_param_summary_text + merge_params_from_columns）
2. 创建 ui/widgets.py（AnglePickerWidget + TemplateSourceRow + OutputSettingsGroup）
3. 验证: python3 gui_integrity_check.py
```
