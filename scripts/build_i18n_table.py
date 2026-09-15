#!/usr/bin/env python3
"""从 .ts 生成运行时反查表 i18n/trans_table.json

为什么需要这个文件
==================
运行时切换语言时，I18nManager 要遍历 widget 树，把每个控件的**当前文本**
还原成源串，再查目标语言的译文。但控件大多是匿名创建的
(如 `QLabel(self.tr("Excel 参数模版:"))` 直接 addWidget)，事后拿不到源串。

- 中文态: zh_CN 是恒等翻译 (translation == source)，故「当前文本 == 源串」，无需表
- 英文态: 只能反查，而 QTranslator **不提供反向映射**，必须自己建表

而 .ts **不进 EXE** (antenna_post_processor.spec 只收 .qm)，所以表必须在构建期
生成、随包发布。

只存英文
========
zh_CN 恒等 → 源串本身即中文译文，不必存。表体积因此减半。

用法
====
    python3 scripts/build_i18n_table.py
由 scripts/update_i18n.sh 在 lrelease 之后自动调用。
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TS_PATH = ROOT / "i18n" / "app_en_US.ts"
OUT_PATH = ROOT / "i18n" / "trans_table.json"


def build(ts_path: Path) -> dict[str, dict[str, str]]:
    """解析 .ts → {context: {源串: 英文译文}}。

    跳过空译与 unfinished (未翻译) 条目 —— 缺失时运行时回退源串，
    比写入半成品译文安全。
    """
    root = ET.parse(ts_path).getroot()
    table: dict[str, dict[str, str]] = {}
    skipped = 0

    for ctx in root.iter("context"):
        name = ctx.findtext("name")
        if not name:
            continue
        entries: dict[str, str] = {}
        for msg in ctx.iter("message"):
            source = msg.findtext("source")
            node = msg.find("translation")
            if source is None or node is None:
                continue
            # type="unfinished" 或空内容 = 尚未翻译
            if node.get("type") == "unfinished" or not (node.text or "").strip():
                skipped += 1
                continue
            entries[source] = node.text
        if entries:
            table[name] = entries

    total = sum(len(v) for v in table.values())
    print(f"解析 {ts_path.name}: {len(table)} 个 context, {total} 条译文"
          f" (跳过 {skipped} 条未翻译)")
    return table


def main() -> int:
    if not TS_PATH.exists():
        print(f"错误: 找不到 {TS_PATH}", file=sys.stderr)
        print("请先运行 scripts/update_i18n.sh 生成 .ts", file=sys.stderr)
        return 1

    table = build(TS_PATH)
    OUT_PATH.write_text(
        json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"已写出 {OUT_PATH} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
