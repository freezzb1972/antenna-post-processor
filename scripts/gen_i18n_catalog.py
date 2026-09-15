#!/usr/bin/env python3
"""生成 ui/i18n_catalog.py —— 供 pyside6-lupdate 提取共享文本源

为什么需要它
============
lupdate 是**静态扫描器**, 只能提取写死在 `tr()` / `translate()` 调用里的字面量。
而有两类文案的真源在别处、以变量形式消费, lupdate 提取不到:

  - `src/chart_config.py:ChartConfig.chart_labels()` — 图表名/类别名
  - `ui/pages.py:AntennaParamsPage._COMMON_PARAMS` 等 — 参数类型标签
    (class body 裸元组, 连 self 都没有)

这些真源**不能原地改成返回译文**:
  - `src/pipeline.py:1350` 依赖 chart_labels() 的中文原值做报告标题匹配
  - `src/` 禁止 import Qt (架构铁律)

故在 UI 消费点翻译 (i18n_manager.tr_shared), 而本文件把源串**静态罗列**出来
让 lupdate 收进 .ts。

本文件**仅供 lupdate 扫描, 运行时不执行** —— 但保持语法正确以便被 import。
由 scripts/gen_i18n_catalog.py 生成, 勿手改。

用法: python3 scripts/gen_i18n_catalog.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ui" / "i18n_catalog.py"
sys.path.insert(0, str(ROOT))


def collect() -> dict[str, set]:
    """返回 {context: {字面量, ...}}。"""
    result: dict[str, set] = {"ChartConfig": set(), "AntennaParamsPage": set()}

    # ── 图表标签 + 类别名 ──
    from src.chart_config import ChartConfig

    result["ChartConfig"] |= set(ChartConfig.chart_labels().values())
    for mode in (0, 1, 2):
        for cat_name, keys in ChartConfig.chart_categories(mode).items():
            result["ChartConfig"].add(cat_name)
            result["ChartConfig"] |= {
                ChartConfig.chart_labels().get(k, k) for k in keys
            }

    # ── 参数类型标签 (class body 裸元组) ──
    from ui.pages import AntennaParamsPage

    for attr in ("_COMMON_PARAMS", "_TRP_PARAMS", "_TIS_PARAMS"):
        for entry in getattr(AntennaParamsPage, attr, []):
            # 结构: (key, label, ...) 或 (group_name, [entries]) —— 两者都收
            if isinstance(entry, (list, tuple)):
                for item in entry:
                    if isinstance(item, str):
                        result["AntennaParamsPage"].add(item)
                    elif isinstance(item, (list, tuple)):
                        result["AntennaParamsPage"] |= {
                            x for x in item if isinstance(x, str)
                        }
    return result


def render(table: dict[str, set]) -> str:
    lines = [
        '"""共享文本源目录 —— 仅供 pyside6-lupdate 静态提取, 运行时不执行。',
        "",
        "由 scripts/gen_i18n_catalog.py 生成, 勿手改。",
        "真源在 src/chart_config.py 与 ui/pages.py, 消费点用 i18n_manager.tr_shared()。",
        '"""',
        "",
        "from PySide6.QtCore import QCoreApplication",
        "",
        "",
        "def _catalog():",
        '    """下列调用只为让 lupdate 收录源串; 无运行时语义。"""',
    ]
    for ctx in sorted(table):
        entries = sorted(table[ctx])
        lines.append(f"    # ── {ctx} ({len(entries)} 条) ──")
        for s in entries:
            lines.append(f'    QCoreApplication.translate("{ctx}", {s!r})')
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    table = collect()
    OUT.write_text(render(table), encoding="utf-8")
    total = sum(len(v) for v in table.values())
    print(f"已写出 {OUT}")
    for ctx in sorted(table):
        print(f"  {ctx:20s} {len(table[ctx]):4d} 条")
    print(f"  合计 {total} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
