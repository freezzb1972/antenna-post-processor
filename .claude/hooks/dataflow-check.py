#!/usr/bin/env python3
"""Pre-commit: 数据流完整性检查

检查项:
  1. 硬编码空列表 + "由 xxx 独立管理" 注释 — 常见删字段残留
  2. ChartConfig 字段是否在消费者端 (plotter/cut_param) 有读取
  3. entries 字段在 plotter 中是否被正确读取 (不是硬编码空)

用法:
  python3 .claude/hooks/dataflow-check.py
"""

import ast, sys, os, re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ═══════════════════════════════════════════════════════════════
# 检查 1: 硬编码空列表 + 转移职责注释
# ═══════════════════════════════════════════════════════════════

def check_hardcoded_empty_with_comment(filepath: str) -> list[str]:
    """检测 = [] 或 = {} 后面跟 '由 xxx 管理' 注释的硬编码。"""
    errors = []
    try:
        with open(filepath) as f:
            lines = f.readlines()
    except Exception:
        return errors

    for i, line in enumerate(lines):
        # 匹配: xxx = []  # 由 yyy 管理
        if re.search(r'=\s*(?:\[\]|{})\s*#.*(?:由|from|独立管理|handled by)', line):
            errors.append(
                f"HARDCODED EMPTY at {filepath}:{i+1}: "
                f"'{line.strip()}' — 可能是删字段残留, 请验证消费者端是否正常读取"
            )
    return errors


# ═══════════════════════════════════════════════════════════════
# 检查 2: entries 字段在消费者端的读取
# ═══════════════════════════════════════════════════════════════

def _find_field_reads(filepath: str, field_name: str) -> list[str]:
    """在文件中搜索字段的读取位置。"""
    try:
        with open(filepath) as f:
            content = f.read()
    except Exception:
        return []

    patterns = [
        f"getattr(..., '{field_name}'",
        f".{field_name}",
        f"['{field_name}']",
        f'["{field_name}"]',
        f"'{field_name}'",
    ]
    found = []
    for line_no, line in enumerate(content.split('\n'), 1):
        if field_name in line and not line.strip().startswith('#') and not line.strip().startswith('"'):
            found.append(f"  {filepath}:{line_no}: {line.strip()[:80]}")
    return found


def check_entries_consumed() -> list[str]:
    """验证 ChartConfig 的 entries 字段在 plotter/cut_param 中有读取。"""
    errors = []

    # ChartConfig 中定义的 entries 字段
    entry_fields = [
        "cut_2d_polar_entries",
        "cut_2d_rect_entries",
        "cut_azimuth_polar_entries",
        "cut_azimuth_rect_entries",
    ]

    consumer_files = [
        str(PROJECT_ROOT / "src" / "plotter.py"),
        str(PROJECT_ROOT / "src" / "cut_param.py"),
    ]

    for field in entry_fields:
        total_reads = 0
        for cf in consumer_files:
            reads = _find_field_reads(cf, field)
            total_reads += len(reads)

        if total_reads == 0:
            errors.append(
                f"UNCONSUMED FIELD: '{field}' defined in ChartConfig "
                f"but never read in plotter.py or cut_param.py — data will be silently dropped"
            )

    return errors


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    all_errors = []

    # Check 1: hardcoded empties
    for f in ["src/plotter.py", "src/cut_param.py", "src/pipeline.py", "ui/pages.py"]:
        path = str(PROJECT_ROOT / f)
        if os.path.exists(path):
            all_errors.extend(check_hardcoded_empty_with_comment(path))

    # Check 2: entries consumed
    all_errors.extend(check_entries_consumed())

    if all_errors:
        print(f"\n❌ 数据流完整性检查: {len(all_errors)} 个问题\n")
        for e in all_errors:
            print(f"  • {e}")
        print()
        return 1

    print("✅ 数据流完整性检查: 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
