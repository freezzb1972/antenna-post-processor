---
name: known-issues-and-fixes
description: 已知问题与修复记录
---

# 已知问题与修复

## 1. 5G4 双 Gain 列 Bug（已修复）

**问题**: 5G4 有两个 "Gain" 列（Col E 和 Col F），`excel_reader.py` 用 dict 存储 columns，键为 normalized_header，导致第二个 Gain 列覆盖第一个，只有一个被写入。

**修复**: `SheetInfo.columns` 从 `Dict[str, ColumnInfo]` 改为 `List[ColumnInfo]`，支持重复列头。

## 2. 列头规范化

全角括号 `（%）` → 半角 `(%)`、换行符 `\n` → 空格，通过 `normalize_header()` 处理。

## 3. LAG 列头检测优先级

先检测范围（`数字-数字`），再检测单角度（`Theta=数字`），避免 "0-90" 中的 "0" 被误识别为单角度。
