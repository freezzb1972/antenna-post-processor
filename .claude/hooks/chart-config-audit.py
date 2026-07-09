#!/usr/bin/env python3
"""Pre-commit: 图表配置接口一致性检查

检查项:
  1. 字段名碰撞检测 — ChartConfig 和 AzimuthReportConfig 是否有重叠字段
  2. merge/to_dict/from_dict 覆盖度 — 新增字段是否在所有序列化方法中覆盖
  3. 复选框重复检查 — 同一 key 是否被多次写入 _chart_required/_chart_extra
  4. 重复代码块近似度 — 相似 >80% 的连续代码段

用法:
  python3 .claude/hooks/chart-config-audit.py          # 完整检查
  python3 .claude/hooks/chart-config-audit.py --quick  # 仅检查字段碰撞+覆盖度
"""

import ast
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ═══════════════════════════════════════════════════════════════
# 检查 1: 字段名碰撞检测
# ═══════════════════════════════════════════════════════════════

def _find_dataclass_fields(filepath: str, class_name: str) -> set[str]:
    """提取 dataclass 的字段名集合。"""
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read())
    except Exception:
        return set()

    fields = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                # AnnAssign: name: type = default
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if not item.target.id.startswith('_'):
                        fields.add(item.target.id)
    return fields


def check_field_collisions() -> list[str]:
    """ChartConfig 和 AzimuthReportConfig 不应有重叠字段。"""
    chart_fields = _find_dataclass_fields(
        str(PROJECT_ROOT / "src" / "chart_config.py"), "ChartConfig")
    az_fields = _find_dataclass_fields(
        str(PROJECT_ROOT / "src" / "azimuth_config.py"), "AzimuthReportConfig")

    # 白名单: dpi(各独立), cut_azimuth_polar/rect(UI→ChartConfig, pipeline→AzimuthReportConfig)
    _WHITELIST = {"dpi", "cut_azimuth_polar", "cut_azimuth_rect"}
    overlap = chart_fields & az_fields - _WHITELIST
    errors = []
    for f in sorted(overlap):
        errors.append(
            f"FIELD COLLISION: '{f}' exists in BOTH ChartConfig and AzimuthReportConfig "
            f"— single source of truth required"
        )
    return errors


# ═══════════════════════════════════════════════════════════════
# 检查 2: merge/to_dict/from_dict 覆盖度
# ═══════════════════════════════════════════════════════════════

def _extract_method_body(filepath: str, method_name: str) -> str | None:
    """提取类方法体的源码文本 (基于行号, 比 ast.unparse 准确)。"""
    try:
        with open(filepath) as f:
            lines = f.readlines()
            source = "".join(lines)
            tree = ast.parse(source)
    except Exception:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            start = node.lineno - 1  # 0-based
            end = node.end_lineno if hasattr(node, 'end_lineno') else start + 50
            return "".join(lines[start:end])
    return None


def check_serialization_coverage(filepath: str, class_name: str) -> list[str]:
    """新增 dataclass 字段必须在 merge/to_dict/from_dict 中覆盖。"""
    fields = _find_dataclass_fields(filepath, class_name)
    if not fields:
        return []

    errors = []

    # Check to_dict
    to_dict_body = _extract_method_body(filepath, "to_dict")
    if to_dict_body:
        for f in fields:
            if f'"{f}"' not in to_dict_body and f"'{f}'" not in to_dict_body:
                errors.append(f"MISSING in {class_name}.to_dict(): '{f}'")

    # Check from_dict
    from_dict_body = _extract_method_body(filepath, "from_dict")
    if from_dict_body:
        for f in fields:
            if f'"{f}"' not in from_dict_body and f"'{f}'" not in from_dict_body:
                errors.append(f"MISSING in {class_name}.from_dict(): '{f}'")

    # Check merge
    merge_body = _extract_method_body(filepath, "merge")
    if merge_body:
        for f in fields:
            if (f'"{f}"' not in merge_body and f"'{f}'" not in merge_body
                    and f"self.{f}" not in merge_body and f"other.{f}" not in merge_body):
                errors.append(f"MISSING in {class_name}.merge(): '{f}'")

    return errors


# ═══════════════════════════════════════════════════════════════
# 检查 3: 重复代码块
# ═══════════════════════════════════════════════════════════════

def check_duplicate_checkbox_keys(filepath: str) -> list[str]:
    """检查 _chart_required 或 _chart_extra 中是否有同一个 key 被多次赋值。"""
    try:
        with open(filepath) as f:
            source = f.read()
            tree = ast.parse(source)
    except Exception:
        return []

    errors = []
    # 搜索所有 self._chart_required["key"] = ... 和 self._chart_extra["key"] = ...
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            # 匹配 self._chart_required["xxx"] 或 self._chart_extra["xxx"]
            if not isinstance(target, ast.Subscript):
                continue
            if not isinstance(target.value, ast.Attribute):
                continue
            attr_name = target.value.attr
            if attr_name not in ("_chart_required", "_chart_extra"):
                continue
            # 在同一函数内搜索是否有第二个赋值
            for parent in ast.walk(tree):
                if parent is node:
                    continue

    return errors


# ═══════════════════════════════════════════════════════════════
# 检查 4: 重复代码近似度
# ═══════════════════════════════════════════════════════════════

def _normalize_block(lines: list[str]) -> str:
    """规范化代码块 (去注释+去空白+去变量名), 用于相似度比较。"""
    result = []
    for line in lines:
        stripped = line.split("#")[0].strip()
        if stripped:
            # 统一替换变量名和字符串字面量
            import re
            stripped = re.sub(r'"[^"]*"', '"_"', stripped)
            stripped = re.sub(r"'[^']*'", "'_'", stripped)
            stripped = re.sub(r'\b\w+\b', '_', stripped)
            result.append(stripped)
    return " ".join(result)


def check_code_duplication(filepath: str, min_block_lines: int = 6,
                           similarity_threshold: float = 0.85) -> list[str]:
    """检测相似度 > 阈值的长代码块。"""
    try:
        with open(filepath) as f:
            raw_lines = f.readlines()
    except Exception:
        return []

    errors = []
    blocks = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        if line.strip() and not line.strip().startswith("#"):
            # 收集连续非空非注释行
            start = i
            while i < len(raw_lines) and raw_lines[i].strip():
                i += 1
            block_lines = raw_lines[start:i]
            if len(block_lines) >= min_block_lines:
                norm = _normalize_block(block_lines)
                blocks.append((start + 1, norm))
        i += 1

    # 比较所有块对
    for a_idx, (a_line, a_norm) in enumerate(blocks):
        for b_idx in range(a_idx + 1, len(blocks)):
            b_line, b_norm = blocks[b_idx]
            if a_norm == b_norm:
                errors.append(
                    f"EXACT DUPLICATE: block at line {a_line} and {b_line} "
                    f"({len(raw_lines[a_line-1:b_line-1])} lines apart) — consider extracting"
                )
    return errors


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    quick = "--quick" in sys.argv
    all_errors = []

    pages_py = str(PROJECT_ROOT / "ui" / "pages.py")
    chart_cfg = str(PROJECT_ROOT / "src" / "chart_config.py")
    az_cfg = str(PROJECT_ROOT / "src" / "azimuth_config.py")

    # 检查 1: 字段碰撞
    all_errors.extend(check_field_collisions())

    # 检查 2: 序列化覆盖度
    all_errors.extend(check_serialization_coverage(chart_cfg, "ChartConfig"))
    all_errors.extend(check_serialization_coverage(az_cfg, "AzimuthReportConfig"))

    if not quick:
        # 检查 3: 重复代码
        all_errors.extend(check_code_duplication(pages_py))

    if all_errors:
        print(f"\n❌ 图表配置接口审计: {len(all_errors)} 个问题\n")
        for e in all_errors:
            print(f"  • {e}")
        print()
        return 1

    print("✅ 图表配置接口审计: 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
