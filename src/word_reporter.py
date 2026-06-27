"""
Word 报告输出引擎
=================
将计算参数和图表填入 Word 模板 (.docx)。

定位方式（优先级）:
  1. 内容控件 (Content Control / SDT) → 按 tag 匹配
  2. 书签 (Bookmark) → 按名定位插图片
  3. 表格 (Table) → 列头识别（复用 classify_header）
  4. 占位符 ({{variable}}) → 搜索替换

所有定位信息在 fill 时收集并缓存，可在 GUI 预览。
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docx import Document
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml
from docx.shared import Inches, Cm, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH


# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════

class WordTemplateInfo:
    """模板扫描结果 — 用于 GUI 预览。"""
    def __init__(self):
        self.tables: List[dict] = []        # [{sheet_index, header_row, columns: [{col_type, text}]}]
        self.bookmarks: List[str] = []       # [bookmark_name, ...]
        self.content_controls: List[str] = []  # [tag_name, ...]
        self.placeholders: List[str] = []    # [var_name, ...]

    @property
    def has_content(self) -> bool:
        return bool(self.tables or self.bookmarks or self.content_controls or self.placeholders)


# ═══════════════════════════════════════════════════════════════
# Word 报告填充器
# ═══════════════════════════════════════════════════════════════

class WordReporter:
    """将天线参数报告填入 Word 模板。"""

    def __init__(self, template_path: str):
        self._doc = Document(template_path)
        self._template_path = template_path
        self._info = WordTemplateInfo()
        self._filled_count = 0  # 统计填入项

    # ── 模板扫描 ──────────────────────────────────────────

    def scan(self) -> WordTemplateInfo:
        """扫描模板，收集所有可填入位置的信息。"""
        self._scan_tables()
        self._scan_bookmarks()
        self._scan_content_controls()
        self._scan_placeholders()
        return self._info

    def _scan_tables(self):
        """扫描所有表格的列头。"""
        for ti, table in enumerate(self._doc.tables):
            if not table.rows:
                continue
            header_cells = table.rows[0].cells
            columns = []
            for ci, cell in enumerate(header_cells):
                text = cell.text.strip()
                if text:
                    from src.column_mapping import classify_header
                    col_type = classify_header(text)
                    columns.append({"index": ci, "text": text, "col_type": col_type})
                else:
                    columns.append({"index": ci, "text": "", "col_type": "unknown"})
            self._info.tables.append({
                "sheet_index": ti,
                "header_row": 0,
                "columns": columns,
            })

    def _scan_bookmarks(self):
        """扫描所有书签。"""
        for bookmark in self._doc.element.body.iter(qn('w:bookmarkStart')):
            name = bookmark.get(qn('w:name'), '')
            if name and name not in self._info.bookmarks:
                self._info.bookmarks.append(name)

    def _scan_content_controls(self):
        """扫描所有内容控件 (Structured Document Tags) 的 tag。"""
        for sdt in self._doc.element.body.iter(qn('w:sdt')):
            tag_el = sdt.find(qn('w:sdtPr') + '/' + qn('w:tag'))
            if tag_el is not None:
                tag_val = tag_el.get(qn('w:val'), '')
                if tag_val:
                    self._info.content_controls.append(tag_val)

    def _scan_placeholders(self):
        """扫描 {{variable}} 占位符。"""
        text = self._doc_text()
        for m in re.finditer(r'\{\{(\w+)\}\}', text):
            var = m.group(1)
            if var not in self._info.placeholders:
                self._info.placeholders.append(var)

    def _doc_text(self) -> str:
        """获取文档全部文字（含表格）。"""
        texts = []
        for para in self._doc.paragraphs:
            texts.append(para.text)
        for table in self._doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    texts.append(cell.text)
        return "\n".join(texts)

    # ── 填充表格 ──────────────────────────────────────────

    def fill_tables(self, sheet_results: Dict[str, List[Dict[str, Any]]],
                    progress_callback=None) -> int:
        """将计算结果填入模板中的表格。

        按顺序匹配:
          1. 表格列头检测 col_type
          2. sheet_name 匹配工作表名

        Returns:
            填入的行数
        """
        if not self._info.tables:
            self._scan_tables()

        total_rows = 0

        for ti, tinfo in enumerate(self._info.tables):
            if ti >= len(self._doc.tables):
                break
            table = self._doc.tables[ti]

            # 构建列映射: col_type → column index
            col_map: Dict[str, int] = {}
            for col in tinfo["columns"]:
                ct = col["col_type"]
                if ct != "unknown" and ct not in col_map:
                    col_map[ct] = col["index"]

            if not col_map:
                continue  # 没有可识别的列

            # 找匹配的数据
            sheet_names = list(sheet_results.keys())
            rows_data = None
            if ti < len(sheet_names):
                rows_data = sheet_results.get(sheet_names[ti])

            if not rows_data:
                continue

            header_row_idx = tinfo["header_row"]
            for ri, row_dict in enumerate(rows_data):
                row_idx = header_row_idx + 1 + ri
                # 确保表格有足够行
                while len(table.rows) <= row_idx:
                    table.add_row()

                for col_type, col_idx in col_map.items():
                    value = row_dict.get(col_type)
                    if value is None:
                        continue
                    cell = table.cell(row_idx, col_idx)
                    cell.text = str(round(value, 6) if isinstance(value, float) else value)

                total_rows += 1
                if progress_callback:
                    progress_callback(ri + 1, len(rows_data), f"填表 {ti+1}")

        self._filled_count += total_rows
        return total_rows

    # ── 填充内容控件 ──────────────────────────────────────

    def fill_content_controls(self, data: Dict[str, Any]) -> int:
        """按 tag 名匹配内容控件并填入值。

        data: {tag_name: value, ...}
        """
        count = 0
        for sdt in self._doc.element.body.iter(qn('w:sdt')):
            tag_el = sdt.find(qn('w:sdtPr') + '/' + qn('w:tag'))
            if tag_el is None:
                continue
            tag_val = tag_el.get(qn('w:val'), '')
            if tag_val not in data:
                continue

            value = data[tag_val]
            text = str(round(value, 6) if isinstance(value, float) else value)

            # 找到 sdtContent 中的第一个 run
            content = sdt.find(qn('w:sdtContent'))
            if content is None:
                continue
            run = content.find(qn('w:r'))
            if run is not None:
                t = run.find(qn('w:t'))
                if t is not None:
                    t.text = text
                    count += 1
                else:
                    # 没有 t → 创建一个
                    new_t = parse_xml(f'<w:t {nsdecls("w")} xml:space="preserve">{text}</w:t>')
                    run.append(new_t)
                    count += 1

        self._filled_count += count
        return count

    # ── 填充占位符 ────────────────────────────────────────

    def fill_placeholders(self, data: Dict[str, Any]) -> int:
        """搜索替换 {{variable}} 占位符。

        data: {var_name: value, ...}
        """
        count = 0
        for para in self._doc.paragraphs:
            for run in para.runs:
                for key, value in data.items():
                    placeholder = '{{' + key + '}}'
                    if placeholder in run.text:
                        val = str(round(value, 6) if isinstance(value, float) else value)
                        run.text = run.text.replace(placeholder, val)
                        count += 1

        # 也替换表格中的占位符
        for table in self._doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        for run in para.runs:
                            for key, value in data.items():
                                placeholder = '{{' + key + '}}'
                                if placeholder in run.text:
                                    val = str(round(value, 6) if isinstance(value, float) else value)
                                    run.text = run.text.replace(placeholder, val)
                                    count += 1

        self._filled_count += count
        return count

    # ── 插入图片（书签定位） ────────────────────────────────

    def insert_images_at_bookmarks(self, bookmark_images: Dict[str, bytes],
                                    max_width_inches: float = 5.5) -> int:
        """在书签位置插入图片（使用 tempfile + add_picture）。"""
        import tempfile
        from docx.shared import Inches

        body = self._doc.element.body
        bookmark_paras: Dict[str, int] = {}
        for el in body.iter():
            if el.tag == qn('w:bookmarkStart'):
                name = el.get(qn('w:name'), '')
                if name in bookmark_images:
                    parent = el.getparent()
                    if parent is not None:
                        for pi, para in enumerate(self._doc.paragraphs):
                            if para._element is parent:
                                bookmark_paras[name] = pi
                                break

        count = 0
        for name, para_idx in bookmark_paras.items():
            png_bytes = bookmark_images[name]
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            tmp.write(png_bytes)
            tmp.close()
            try:
                para = self._doc.paragraphs[para_idx]
                from docx.oxml import parse_xml
                from docx.oxml.ns import nsdecls
                img_para = parse_xml(f'<w:p {nsdecls("w")}></w:p>')
                para._element.addnext(img_para)

                handle_doc = Document()
                new_run = handle_doc.add_paragraph().add_run()
                new_run.add_picture(tmp.name, width=Inches(max_width_inches))

                for child in new_run._r:
                    img_para.append(child)
                count += 1
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

        self._filled_count += count
        return count
        svg_ns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image'
        from lxml import etree

        for name, para_idx in bookmarks.items():
            png_bytes = bookmark_images[name]
            from docx.shared import Inches
            import docx.opc.constants

            # 在书签段落后面插入新段落+图片
            para = self._doc.paragraphs[para_idx]

            # 用 PIL 获取图片尺寸
            from PIL import Image as PILImage
            import io as _io
            img_stream = _io.BytesIO(png_bytes)
            pil_img = PILImage.open(img_stream)
            img_width, img_height = pil_img.size
            aspect = img_height / img_width

            # 计算 EMU 尺寸
            width_emu = int(max_width_inches * 914400)
            height_emu = int(width_emu * aspect)

            # 添加图片部件并获取 rId
            image_part = self._doc.part.get_or_add_image(
                _io.BytesIO(png_bytes))

            # 构建 inline 图片 XML
            nsmap = {
                'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
                'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
                'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
                'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
            }

            inline = etree.SubElement(etree.Element('dummy'), '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline')
            extent = etree.SubElement(inline, '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent')
            extent.set('cx', str(width_emu))
            extent.set('cy', str(height_emu))

            graphic = etree.SubElement(inline, '{http://schemas.openxmlformats.org/drawingml/2006/main}graphic')
            graphic_data = etree.SubElement(graphic, '{http://schemas.openxmlformats.org/drawingml/2006/main}graphicData')
            graphic_data.set('uri', 'http://schemas.openxmlformats.org/drawingml/2006/picture')

            pic = etree.SubElement(graphic_data, '{http://schemas.openxmlformats.org/drawingml/2006/picture}pic')
            nvPicPr = etree.SubElement(pic, '{http://schemas.openxmlformats.org/drawingml/2006/picture}nvPicPr')
            cNvPr = etree.SubElement(nvPicPr, '{http://schemas.openxmlformats.org/drawingml/2006/picture}cNvPr')
            cNvPr.set('id', '0')
            cNvPr.set('name', f'{name}.png')

            blipFill = etree.SubElement(pic, '{http://schemas.openxmlformats.org/drawingml/2006/picture}blipFill')
            blip = etree.SubElement(blipFill, '{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
            blip.set('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed', rId)

            spPr = etree.SubElement(pic, '{http://schemas.openxmlformats.org/drawingml/2006/picture}spPr')
            xfrm = etree.SubElement(spPr, '{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm')
            off = etree.SubElement(xfrm, '{http://schemas.openxmlformats.org/drawingml/2006/main}off')
            off.set('x', '0')
            off.set('y', '0')
            ext = etree.SubElement(xfrm, '{http://schemas.openxmlformats.org/drawingml/2006/main}ext')
            ext.set('cx', str(width_emu))
            ext.set('cy', str(height_emu))
            prstGeom = etree.SubElement(spPr, '{http://schemas.openxmlformats.org/drawingml/2006/main}prstGeom')
            prstGeom.set('prst', 'rect')

            # 插入到书签段落后面
            from docx.oxml import parse_xml
            new_para = parse_xml(
                f'<w:p {nsdecls("w")}><w:r><w:drawing>'
                f'{etree.tostring(inline, encoding="unicode")}'
                f'</w:drawing></w:r></w:p>')
            para._element.addnext(new_para)
            count += 1

        self._filled_count += count
        return count

    # ── 通用填充 ──────────────────────────────────────────

    def fill_all(self, sheet_results: Dict[str, List[Dict]],
                 single_values: Optional[Dict[str, Any]] = None,
                 bookmark_images: Optional[Dict[str, bytes]] = None,
                 progress_callback=None) -> dict:
        """执行全部填充操作。

        Returns:
            {"tables": N, "controls": N, "placeholders": N, "images": N}
        """
        result = {"tables": 0, "controls": 0, "placeholders": 0, "images": 0}

        result["tables"] = self.fill_tables(sheet_results, progress_callback)

        if single_values:
            result["controls"] = self.fill_content_controls(single_values)
            result["placeholders"] = self.fill_placeholders(single_values)

        if bookmark_images:
            result["images"] = self.insert_images_at_bookmarks(bookmark_images)

        return result

    # ── 输出 ──────────────────────────────────────────────

    def save(self, output_path: str) -> str:
        """保存填充后的文档。"""
        os.makedirs(str(Path(output_path).parent), exist_ok=True)
        self._doc.save(output_path)
        return output_path

    @property
    def template_info(self) -> WordTemplateInfo:
        return self._info

    @property
    def filled_count(self) -> int:
        return self._filled_count
