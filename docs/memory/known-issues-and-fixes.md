---
name: known-issues-and-fixes
description: 已知问题与修复记录 — 5G4双Gain列bug、列头解析、column类型修复
metadata: 
  node_type: memory
  type: project
  originSessionId: 0d038809-420b-4a1e-8631-c2bbd6c73f07
---

# 已知问题与修复

## 1. 5G4 双 Gain 列 Bug（已修复）
**问题**: 5G4 有两个 "Gain" 列（Col E 和 Col F），但 `excel_reader.py` 用 dict 存储 columns，
键为 normalized_header，导致第二个 Gain 列覆盖第一个，只有一个被写入。

**修复**:
- `SheetInfo.columns`: `Dict[str, ColumnInfo]` → `List[ColumnInfo]`
- `excel_reader.py`: `columns[norm] = cinfo` → `columns.append(cinfo)`
- `exporter.py`: `info.columns.values()` → `info.columns`（list 迭代）
- `tests/test_excel_reader.py`: 同步更新

**验证**: 5G4 Row 9 Col E(7.75), Col F(7.75) — 两个 Gain 列均正确。

## 2. 列头规范化
全角括号 `（%）` → 半角 `(%)`、换行符 `\n` → 空格，通过 `normalize_header()` 处理。

## 3. LAG 列头检测优先级
先检测范围（`数字-数字`），再检测单角度（`Theta=数字`），避免 "0-90" 中的 "0" 被误识别为单角度。

## 4. Windows 打包注意事项
- 需要 Windows 环境本地运行 pyinstaller
- spec 文件已配置：console=False, excludes 减少体积
- matplotlib backend 必须用 Agg（非交互式），避免 TkAgg 依赖

**Why:** 记录关键 bug 和修复，避免后续重复踩坑。

**How to apply:** 修改 Excel 模板读取逻辑时，注意支持重复列头。
