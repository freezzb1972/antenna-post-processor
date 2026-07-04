"""
Docx SDT 插入工具
=================
在现有 .docx 模板中自动包裹 <w:sdt> 内容控件。
支持三种目标: 表格、段落中的占位文本、图片。

用法:
    from src.docx_sdt_inserter import scan_docx, insert_sdt_tags
    positions = scan_docx("template.docx")
    insert_sdt_tags("template.docx", positions, "template_sdt.docx")
"""

from __future__ import annotations

import copy
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

TAG = f"{{{NS_W}}}tag"
VAL = f"{{{NS_W}}}val"
SDT = f"{{{NS_W}}}sdt"
SDT_PR = f"{{{NS_W}}}sdtPr"
SDT_CONTENT = f"{{{NS_W}}}sdtContent"
TBL = f"{{{NS_W}}}tbl"
P = f"{{{NS_W}}}p"
R = f"{{{NS_W}}}r"
T = f"{{{NS_W}}}t"
TR = f"{{{NS_W}}}tr"
TC = f"{{{NS_W}}}tc"


# ═══════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class DocxPosition:
    """模板中一个可插入 SDT 的位置。"""
    index: int                            # 序号
    pos_type: str                         # "table" | "text" | "image"
    location: str                         # 位置描述: "Table 13 (62 rows)"
    sample_text: str = ""                 # 示例文本 (前 100 字符)
    suggested_tag: str = ""               # 推荐 SDT tag
    confirmed_tag: str = ""               # 用户确认的 tag
    element_path: str = ""                # XML 路径 (用于插入)
    row_count: int = 0                    # 仅 table


# ═══════════════════════════════════════════════════════════════
# Docx 扫描器
# ═══════════════════════════════════════════════════════════════

def scan_docx(template_path: str) -> list[DocxPosition]:
    """扫描 .docx 模板，返回所有可插入 SDT 的位置列表。"""
    with ZipFile(template_path, 'r') as zf:
        doc_xml = etree.parse(zf.open('word/document.xml'))

    root = doc_xml.getroot()
    positions = []
    idx = 0

    # ── 扫描表格 ──
    tables = list(root.iter(TBL))
    for ti, tbl in enumerate(tables):
        rows = list(tbl.iter(TR))
        if not rows:
            continue
        # 表头行文本
        header_texts = []
        for tc in rows[0].iter(TC):
            header_texts.append("".join(tc.itertext()).strip())
        sample = " | ".join(h for h in header_texts[:5] if h)[:100]

        pos_type = "table"
        # 识别表格类型
        all_text = "".join(tbl.itertext())
        if any(w in all_text for w in ["Frequency", "PKGain", "Gain at Theta", "AR at Theta",
                                        "Efficiency", "Directivity"]):
            pos_type = "table_data"
        elif len(rows) <= 10:
            pos_type = "table_meta"

        tag_suggestion = _suggest_tag_for_table(ti, header_texts, all_text, len(rows))

        positions.append(DocxPosition(
            index=idx, pos_type=pos_type,
            location=f"Table {ti+1} ({len(rows)} rows)",
            sample_text=sample,
            suggested_tag=tag_suggestion,
            element_path=f"//w:tbl[{ti+1}]",
            row_count=len(rows),
        ))
        idx += 1

    # ── 扫描图片 ──
    img_count = 0
    for blip in root.iter(f"{{http://schemas.openxmlformats.org/drawingml/2006/main}}blip"):
        embed = blip.get(f"{{{NS_R}}}embed")
        if embed:
            positions.append(DocxPosition(
                index=idx, pos_type="image",
                location=f"Image {img_count+1}",
                suggested_tag=f"img_{img_count+1}",
            ))
            img_count += 1
            idx += 1

    return positions


def _suggest_tag_for_table(ti: int, headers: list[str], all_text: str, rows: int) -> str:
    """根据表格内容推荐 SDT tag。"""
    # 从注册表查找
    try:
        from src.docx_exporter import DocxTemplateFiller
        registry = DocxTemplateFiller.load_registry()
    except Exception:
        registry = {}

    # 表头匹配
    if "Frequency" in all_text or "频率" in all_text:
        if "Gain at Theta" in all_text or "LAG" in all_text:
            return "table_gain"
        if "AR at Theta" in all_text:
            return "table_ar"
        if "Efficiency" in all_text or "效率" in all_text:
            return "table_efficiency"
        if "Directivity" in all_text:
            return "table_directivity"

    if rows <= 10:
        return "meta_info"

    return f"table_{ti+1}"


# ═══════════════════════════════════════════════════════════════
# SDT 插入
# ═══════════════════════════════════════════════════════════════

def insert_sdt_tags(template_path: str, positions: list[DocxPosition],
                    output_path: str) -> str:
    """在模板中插入 SDT tag。

    对 confirmed_tag 非空的 position 包裹 <w:sdt>。
    返回输出路径。
    """
    # 复制并修改
    shutil.copy2(template_path, output_path)

    confirmed = [p for p in positions if p.confirmed_tag.strip()]
    if not confirmed:
        return output_path

    with ZipFile(output_path, 'a') as zf:
        zf.writestr = lambda *a, **kw: None  # no direct zip write
        pass

    # 使用 temp ZIP 修改
    tmp_path = output_path + ".tmp"
    with ZipFile(template_path, 'r') as zin, ZipFile(tmp_path, 'w', ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'word/document.xml':
                data = _inject_sdts(data, confirmed)
            zout.writestr(item, data)

    shutil.move(tmp_path, output_path)
    return output_path


def _inject_sdts(xml_bytes: bytes, positions: list[DocxPosition]) -> bytes:
    """在 document.xml 中注入 SDT 标签。"""
    root = etree.fromstring(xml_bytes)
    body = root.find(f"{{{NS_W}}}body")
    if body is None:
        return xml_bytes

    tables = list(body.iter(TBL))
    for pos in positions:
        if pos.pos_type.startswith("table") and pos.index < len(tables):
            tbl = tables[pos.index]
            _wrap_in_sdt(tbl, pos.confirmed_tag)

    return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                          standalone=True)


def _wrap_in_sdt(element, tag_val: str):
    """给元素包裹 <w:sdt>。"""
    parent = element.getparent()
    if parent is None:
        return
    idx = list(parent).index(element)

    sdt = etree.Element(SDT)
    sdt_pr = etree.SubElement(sdt, SDT_PR)
    tag_el = etree.SubElement(sdt_pr, TAG)
    tag_el.set(VAL, tag_val)
    sdt_content = etree.SubElement(sdt, SDT_CONTENT)

    parent.remove(element)
    sdt_content.append(element)
    parent.insert(idx, sdt)
