"""
Word 模板 SDT 准备工具
======================
为现有 .docx 模板自动插入 SDT 内容控件，或生成带 SDT 的副本。

用法:
    # 分析模式: 列出模板中所有可识别的内容
    python scripts/prepare_docx_template.py --analyze template.docx

    # 生成模式: 自动为表格和占位区域包裹 SDT
    python scripts/prepare_docx_template.py --prepare template.docx --output template_sdt.docx

    # 交互模式: 逐步确认每个 SDT tag
    python scripts/prepare_docx_template.py --interactive template.docx
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# ═══════════════════════════════════════════════════════════════
# 分析器
# ═══════════════════════════════════════════════════════════════

def analyze_template(template_path: str) -> dict:
    """分析模板，返回所有可识别的内容位置。"""
    doc = Document(template_path)
    body = doc.element.body
    results = {
        "tables": [],
        "text_blocks": [],
        "images": [],
        "existing_sdt": [],
    }

    # 已有 SDT
    for sdt in body.iter(f"{{{NS_W}}}sdt"):
        sdt_pr = sdt.find(f"{{{NS_W}}}sdtPr")
        if sdt_pr is not None:
            tag = sdt_pr.find(f"{{{NS_W}}}tag")
            if tag is not None:
                results["existing_sdt"].append(tag.get(f"{{{NS_W}}}val", ""))

    # 表格分析
    tbl_index = 0
    for tbl in body.iter(f"{{{NS_W}}}tbl"):
        trs = list(tbl.iter(f"{{{NS_W}}}tr"))
        if not trs:
            continue
        # 第一行文本
        first_row_texts = []
        for tc in trs[0].iter(f"{{{NS_W}}}tc"):
            first_row_texts.append("".join(tc.itertext()).strip())

        row_count = len(trs)
        all_text = "".join(tbl.itertext())

        # 判断表格类型
        table_type = "unknown"
        if any("Frequency" in t or "频率" in t for t in first_row_texts):
            table_type = "data_table"
        elif row_count <= 10:
            table_type = "metadata_table"

        results["tables"].append({
            "index": tbl_index,
            "rows": row_count,
            "headers": first_row_texts,
            "type": table_type,
            "sample_text": all_text[:200],
        })
        tbl_index += 1

    # 图片
    for blip in body.iter(f"{{http://schemas.openxmlformats.org/drawingml/2006/main}}blip"):
        embed = blip.get(f"{{http://schemas.openxmlformats.org/officeDocument/2006/relationships}}embed")
        if embed:
            results["images"].append(embed)

    return results


def suggest_tags(results: dict) -> list[dict]:
    """根据分析结果建议 SDT tag 名称。"""
    suggestions = []

    for tbl in results["tables"]:
        if tbl["type"] == "metadata_table":
            for cell_text in tbl["headers"]:
                if cell_text and len(cell_text) > 1:
                    tag = "meta_" + re.sub(r"[^a-zA-Z0-9_]", "_", cell_text.lower())[:40]
                    suggestions.append({
                        "type": "text",
                        "tag": tag,
                        "location": f"Table {tbl['index']+1}",
                        "current_text": cell_text,
                    })
        elif tbl["type"] == "data_table":
            tag = f"table_data_{tbl['index']+1}"
            suggestions.append({
                "type": "table",
                "tag": tag,
                "location": f"Table {tbl['index']+1} ({tbl['rows']} rows)",
                "headers": tbl["headers"],
            })

    for i, img in enumerate(results["images"]):
        suggestions.append({
            "type": "image",
            "tag": f"img_{i+1}",
            "location": f"Image {i+1}",
        })

    return suggestions


# ═══════════════════════════════════════════════════════════════
# 命令行接口
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Word 模板 SDT 准备工具")
    parser.add_argument("template", help="模板 .docx 文件路径")
    parser.add_argument("--analyze", action="store_true", help="分析模板并建议 tag")
    parser.add_argument("--output", "-o", help="输出文件路径")
    args = parser.parse_args()

    if not Path(args.template).exists():
        print(f"Error: file not found: {args.template}")
        sys.exit(1)

    if args.analyze:
        results = analyze_template(args.template)
        suggestions = suggest_tags(results)

        print(f"\n=== 模板分析: {args.template} ===")
        print(f"已有 SDT: {len(results['existing_sdt'])}")
        for tag in results["existing_sdt"]:
            print(f"  - {tag}")

        print(f"\n表格: {len(results['tables'])}")
        for tbl in results["tables"]:
            print(f"  Table {tbl['index']+1}: {tbl['type']} ({tbl['rows']} rows)")
            if tbl["headers"]:
                print(f"    Headers: {tbl['headers'][:5]}...")

        print(f"\n图片: {len(results['images'])}")

        print(f"\n=== SDT Tag 建议 ===")
        for s in suggestions:
            print(f"  [{s['type']:6s}] {s['tag']:30s} → {s['location']}")
            if "current_text" in s:
                print(f"         value: {s['current_text'][:60]}")
            if "headers" in s:
                print(f"         headers: {s['headers'][:5]}...")


if __name__ == "__main__":
    main()
