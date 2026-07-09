#!/usr/bin/env python3
"""Pre-commit: 数据流完整性检查

检查项:
  1. 硬编码检测: 消费者文件中 = []/False/None + 转移职责注释
  2. 字段消费覆盖: ChartConfig 字段自动提取 → 验证 writer + reader 路径
"""

import ast, os, re, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ═══════════════════════════════════════════════════════════════
# 检查 1: 硬编码残留检测 (泛化)
# ═══════════════════════════════════════════════════════════════

_HARDCODE_PATTERNS = [
    # pattern → 说明
    (r'=\s*(?:\[\]|{}|None|False)\s*#.*(?:由|from|独立管理|handled|elsewhere|else where)', "空值+转移职责注释"),
    (r'=\s*\[\s*0\.0\s*,\s*90\.0\s*\]\s*#.*default', "硬编码默认角度"),
    (r'=\s*\[\s*30\.0\s*,\s*60\.0\s*\]\s*#.*default', "硬编码默认角度"),
]


def check_hardcoded_defaults(filepath: str) -> list[str]:
    """检测消费者文件中的硬编码默认值模式。"""
    errors = []
    try:
        with open(filepath) as f:
            lines = f.readlines()
    except Exception:
        return errors

    for i, line in enumerate(lines):
        for pattern, desc in _HARDCODE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                errors.append(
                    f"HARDCODED {desc} at {filepath}:{i+1}: {line.strip()}"
                )
                break
    return errors


# ═══════════════════════════════════════════════════════════════
# 检查 2: 字段消费覆盖率 (自动提取, 泛化)
# ═══════════════════════════════════════════════════════════════

def _extract_public_fields(filepath: str, class_name: str) -> set[str]:
    """提取 dataclass 的公开字段名。"""
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read())
    except Exception:
        return set()

    fields = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if not item.target.id.startswith('_'):
                        fields.add(item.target.id)
    return fields


def _find_references(filepath: str, field_name: str) -> int:
    """在文件中搜索字段名的引用次数(排除注释行)。"""
    try:
        with open(filepath) as f:
            lines = f.readlines()
    except Exception:
        return 0

    count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if field_name in stripped:
            count += 1
    return count


def check_field_coverage() -> list[str]:
    """自动提取 ChartConfig 字段, 验证 writer + reader 路径。"""
    errors = []

    chart_cfg = str(PROJECT_ROOT / "src" / "chart_config.py")
    fields = _extract_public_fields(chart_cfg, "ChartConfig")
    if not fields:
        return ["Cannot extract ChartConfig fields"]

    # Writer: pages.py _sync_to_mw
    pages_py = str(PROJECT_ROOT / "ui" / "pages.py")
    # Readers: plotter, cut_param, pipeline
    readers = [
        str(PROJECT_ROOT / "src" / "plotter.py"),
        str(PROJECT_ROOT / "src" / "cut_param.py"),
        str(PROJECT_ROOT / "src" / "pipeline.py"),
    ]

    # 向后兼容字段 (已废弃, 不需要 reader)
    _DEPRECATED = {"cut_2d_phi_angles", "cut_2d_theta_angles", "cut_2d_params"}
    check_fields = {f for f in fields
                    if ("entries" in f or f.startswith("cut_"))
                    and f not in _DEPRECATED}

    for field in sorted(check_fields):
        writer_count = _find_references(pages_py, field)
        reader_count = sum(_find_references(rf, field) for rf in readers)

        if writer_count == 0 and reader_count == 0:
            continue  # 可能是旧字段, 跳过
        if writer_count == 0:
            errors.append(f"MISSING WRITER: '{field}' not written in pages.py _sync_to_mw")
        if reader_count == 0:
            errors.append(f"MISSING READER: '{field}' not read in plotter/cut_param/pipeline — data silently dropped")

    return errors


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    all_errors = []

    # Check 1: hardcoded defaults
    for f in ["src/plotter.py", "src/cut_param.py", "src/pipeline.py"]:
        path = str(PROJECT_ROOT / f)
        if os.path.exists(path):
            all_errors.extend(check_hardcoded_defaults(path))

    # Check 2: field coverage
    all_errors.extend(check_field_coverage())

    if all_errors:
        print(f"\n❌ 数据流完整性: {len(all_errors)} 个问题\n")
        for e in all_errors:
            print(f"  • {e}")
        print()
        return 1

    print("✅ 数据流完整性: 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
