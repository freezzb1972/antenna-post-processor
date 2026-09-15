#!/usr/bin/env python3
"""漏包守卫: 找出 ui/ 下未包 tr() 的中文字面量

背景
====
本项目 UI 文本必须用 self.tr() / QCoreApplication.translate() 包裹, 否则不进
翻译体系 —— 界面在英文模式下仍是中文。历史上这条规则靠人工遵守, 于是
ui/graph_viewer.py 积压了约 128 处裸中文 (全文仅 1 处 tr), 直到 2026-09 才清理。

这是**非阻塞的告警工具**, 由 scripts/update_i18n.sh 末尾调用。
不要把它的输出当成"必须清零"—— 日志、正则、内部状态串本就不该 tr。

判定规则
========
报出「含中文的字符串字面量, 且未紧跟 tr(/translate(」, 并排除:
  - docstring
  - 注释行
  - 日志/调试 (_log/logger/print)
  - 语言名 (中文/English —— 翻译它反而错)
  - 明显是数据键的值 (纯英文混排且无中文的已天然排除)

用法: python3 scripts/check_i18n.py [--all]
  --all  连注释与 docstring 一并列出 (默认只看可疑项)
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"

LIT = re.compile(
    r'"(?:[^"\\]|\\.)*"'      # 双引号字面量
    r"|'(?:[^'\\]|\\.)*'"    # 单引号字面量
)
CJK = re.compile(r"[一-鿿]")
SKIP_LINE = re.compile(r"_log|logger|print\(|_btn_lang")


def classbody_lines(tree: ast.AST) -> set:
    """class body 里赋值语句的行号 —— 那里没有 self, 必须用 QCoreApplication.translate。"""
    out = set()
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for stmt in cls.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for n in ast.walk(stmt):
                if hasattr(n, "lineno"):
                    out.add(n.lineno)
    return out


def scan(path: Path) -> list:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    try:
        cb = classbody_lines(ast.parse(text))
    except SyntaxError:
        cb = set()

    hits = []
    open_tr_depth = 0        # 跨行 tr( 的括号深度
    for i, line in enumerate(lines, start=1):
        s = line.strip()
        if s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
            continue
        if SKIP_LINE.search(line):
            continue
        # 同行内出现过 tr( / translate( 且位于字面量之前 -> 视为已包
        # (用「之前出现过」而非「紧邻」, 否则 translate("Ctx", "...") 这种
        #  第二参数会被误报 —— i18n_catalog.py 整文件都是这种形态)
        tr_positions = [mm.start() for mm in re.finditer(r"\b(tr|translate)\(", line)]
        for m in LIT.finditer(line):
            lit = m.group(0)
            if not CJK.search(lit):
                continue
            if any(pos < m.start() for pos in tr_positions):
                continue          # 已包 (同行)
            if open_tr_depth > 0:
                continue          # 已包 (跨行, 如 self.tr(\n  "...") )
            kind = ("class body: ①在消费点翻译(推荐, 见 ThemeManager 主题名) "
                    "或 ②改用 QCoreApplication.translate —— "
                    "切勿原地包 translate, import 期求值会冻结译文"
                    if i in cb else "UI 文案?")
            hits.append((i, lit[:56], kind))
        # 维护跨行 tr( 深度 (粗略: 只数括号)
        _seg = line
        _d = 0
        for ch in _seg:
            if ch == "(":
                _d += 1
            elif ch == ")":
                _d -= 1
        if re.search(r"\b(tr|translate)\(", line):
            open_tr_depth = max(0, open_tr_depth + _d)
        elif open_tr_depth > 0:
            open_tr_depth = max(0, open_tr_depth + _d)
    return hits


def main() -> int:
    total = 0
    for path in sorted(UI_DIR.glob("*.py")):
        if path.name in ("__init__.py", "i18n_catalog.py"):
            continue   # i18n_catalog 是生成物, 全为 translate() 调用
        hits = scan(path)
        if not hits:
            continue
        print(f"\n{path.relative_to(ROOT)}  ({len(hits)} 处)")
        for ln, lit, kind in hits[:40]:
            print(f"   {ln:5d}  {lit:58s}  {kind}")
        if len(hits) > 40:
            print(f"   ... 另有 {len(hits) - 40} 处")
        total += len(hits)

    if total:
        print(f"\n合计 {total} 处未包 tr() 的中文字面量。")
        print("逐个判断: UI 文案 → 包 tr(); 日志/正则/内部状态串 → 忽略。")
    else:
        print("✅ 未发现未包 tr() 的 UI 中文字面量")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
