#!/usr/bin/env python3
"""自动生成 FUNC_CATALOG.md — 项目中所有可复用函数的目录。

扫描 src/ 提取: 函数签名、docstring 摘要、参数、复用等级。
按模块分组，同类函数标记关联。

用法:
  python3 generate_func_catalog.py          # 生成 FUNC_CATALOG.md
  python3 generate_func_catalog.py --check  # 检查是否需要更新
  python3 generate_func_catalog.py --json   # JSON 输出 (供程序使用)
"""

import ast
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
CATALOG_PATH = ROOT / "FUNC_CATALOG.md"

# 这些模块不列入目录 (内部/实验性)
SKIP_MODULES = {"__init__", "activation_server", "license"}


def _extract_summary(docstring: str | None) -> str:
    """从 docstring 提取第一行作为摘要。"""
    if not docstring:
        return ""
    docstring = docstring.strip()
    # 去除参数/返回值描述，只取第一段
    lines = docstring.split("\n")
    summary = lines[0].strip()
    # 截断过长的摘要
    if len(summary) > 120:
        summary = summary[:117] + "..."
    return summary


def _classify_reusability(func_name: str, docstring: str, has_side_effects: bool) -> str:
    """判断函数复用等级: A(核心/高复用) B(模块级) C(内部)"""
    # A 级: 纯计算、无副作用、有明确 docstring
    if not has_side_effects and docstring:
        return "A"
    # B 级: 有 docstring 但有副作用
    if docstring:
        return "B"
    # C 级: 无 docstring 或纯内部
    return "C"


def _is_pure_function(node: ast.FunctionDef) -> bool:
    """判断函数是否为纯函数 (无副作用)。
    启发式: 不包含 open/print/write/save/load 等调用。
    """
    side_effect_calls = {
        "open", "print", "write", "save", "load", "dump", "dumps",
        "close", "delete", "remove", "mkdir", "rename", "chmod",
        "exec", "subprocess", "QMessageBox", "QFileDialog",
        "plt.", "show()", "imshow", "savefig",
    }
    source = ast.unparse(node)
    return not any(call in source for call in side_effect_calls)


def _find_related(func_name: str, all_funcs: dict) -> list:
    """查找名称相似的可能相关函数。"""
    related = []
    keywords = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", func_name)
    kw_set = {k.lower() for k in keywords if len(k) >= 3}
    # 移除太通用的词
    kw_set -= {"compute", "calculate", "write", "read", "process",
               "find", "build", "check", "parse", "extract", "from"}

    for mod, funcs in all_funcs.items():
        for f in funcs:
            if f["name"] == func_name:
                continue
            f_kw = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", f["name"])
            f_kw_set = {k.lower() for k in f_kw if len(k) >= 3}
            f_kw_set -= kw_set  # 不检查通用词
            overlap = kw_set & f_kw_set
            if len(overlap) >= 2:
                related.append(f"{f['name']} (in {mod})")
    return related[:5]  # 最多 5 个


def scan_functions() -> dict:
    """扫描 src/ 目录，提取所有函数信息。"""
    all_funcs: dict[str, list[dict]] = {}

    for py_file in sorted(SRC_DIR.glob("**/*.py")):
        rel = py_file.relative_to(SRC_DIR)
        module_name = str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")

        # 跳过实验性模块
        if any(s in module_name.split(".") for s in SKIP_MODULES):
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue

        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # 跳过私有函数 (以 _ 开头且不在 export 列表中)
                if node.name.startswith("_") and not node.name.startswith("__"):
                    continue

                docstring = ast.get_docstring(node)
                summary = _extract_summary(docstring)
                pure = _is_pure_function(node)
                reusability = _classify_reusability(node.name, summary, not pure)

                # 推断参数
                params = []
                for arg in node.args.args:
                    if arg.arg == "self":
                        continue
                    params.append(arg.arg)
                if node.args.vararg:
                    params.append(f"*{node.args.vararg.arg}")
                if node.args.kwarg:
                    params.append(f"**{node.args.kwarg.arg}")

                functions.append({
                    "name": node.name,
                    "params": params,
                    "summary": summary,
                    "reusability": reusability,
                    "pure": pure,
                    "line": node.lineno,
                })

        if functions:
            all_funcs[module_name] = functions

    # 补充关联关系
    for mod, funcs in all_funcs.items():
        for f in funcs:
            f["related"] = _find_related(f["name"], all_funcs)

    return all_funcs


def generate_markdown(all_funcs: dict) -> str:
    """生成 FUNC_CATALOG.md 内容。"""
    lines = []
    lines.append("# 函数目录 (Function Catalog)")
    lines.append("")
    lines.append(f"> 自动生成于 `generate_func_catalog.py`。覆盖 `src/` 下 {sum(len(v) for v in all_funcs.values())} 个公开函数。")
    lines.append("> 每次 `git commit` 后自动更新。")
    lines.append("")
    lines.append("## 复用等级")
    lines.append("")
    lines.append("| 等级 | 含义 | 使用规则 |")
    lines.append("|------|------|---------|")
    lines.append("| **A** | 纯函数，高复用 | 新功能优先复用。修改需参数化，不破坏已有调用。 |")
    lines.append("| **B** | 有副作用，模块级 | 同模块内复用。跨模块调用需评估。 |")
    lines.append("| **C** | 内部实现 | 不直接复用。但如果有 ≥2 个类似 C 级函数，应提取为 A 级。 |")
    lines.append("")

    # 按模块分组
    for module_name in sorted(all_funcs.keys()):
        funcs = all_funcs[module_name]
        lines.append(f"## {module_name}")
        lines.append("")
        lines.append("| Lv | 函数 | 参数 | 说明 | 关联 |")
        lines.append("|----|------|------|------|------|")

        for f in sorted(funcs, key=lambda x: (-ord(x["reusability"]), x["name"])):
            params_str = ", ".join(f["params"][:4])  # 最多显示 4 个参数
            if len(f["params"]) > 4:
                params_str += ", ..."
            if not params_str:
                params_str = "—"

            summary = f["summary"][:80] if f["summary"] else "—"

            related_str = ""
            if f["related"]:
                related_names = [r.split(" (in ")[0] for r in f["related"][:3]]
                related_str = " → ".join(f"`{n}`" for n in related_names)

            lines.append(f"| {f['reusability']} | `{f['name']}` | {params_str} | {summary} | {related_str} |")

        lines.append("")

    # 统计
    a_count = sum(1 for v in all_funcs.values() for f in v if f["reusability"] == "A")
    b_count = sum(1 for v in all_funcs.values() for f in v if f["reusability"] == "B")
    c_count = sum(1 for v in all_funcs.values() for f in v if f["reusability"] == "C")

    lines.append("---")
    lines.append(f"**统计**: A 级 {a_count} · B 级 {b_count} · C 级 {c_count} · 共 {a_count + b_count + c_count}")
    lines.append("")
    lines.append("> 💡 **写新函数前**：先在此目录搜索关键词，查看是否已有类似实现。")
    lines.append("> 搜索示例：`grep -i 'axial_ratio' FUNC_CATALOG.md`")

    return "\n".join(lines)


def main():
    all_funcs = scan_functions()

    if "--json" in sys.argv:
        print(json.dumps(all_funcs, indent=2, ensure_ascii=False))
        return

    md = generate_markdown(all_funcs)
    CATALOG_PATH.write_text(md, encoding="utf-8")

    total = sum(len(v) for v in all_funcs.values())
    a_count = sum(1 for v in all_funcs.values() for f in v if f["reusability"] == "A")
    print(f"FUNC_CATALOG.md updated: {total} functions ({a_count} A-level) across {len(all_funcs)} modules")


if __name__ == "__main__":
    main()
