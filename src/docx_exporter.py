"""
Word 模板填充器 — SDT Tag 绑定
================================
基于 python-docx，通过 SDT (Structured Document Tag) 的 tag 属性
匹配数据位置，支持三种填充模式：

  A. 文本替换 — 单值 SDT 内容替换
  B. 表格填充 — 识别表头 → 按频点复制行 → 填入数据
  C. 图片替换 — SDT 占位图替换为 Matplotlib PNG

用法:
    filler = DocxTemplateFiller("template.docx")
    filler.fill_text("meta_customer", "安费诺")
    filler.fill_table("table_gain_L1", rows, col_map)
    filler.fill_image("img_3d_gain_L1", "/tmp/gain_3d.png", width_cm=8)
    filler.save("output.docx")
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Cm, Inches, Pt, RGBColor
from lxml import etree

# ── XML 命名空间 ──
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
NS_WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"

SDT_TAG = qn("w:tag")
SDT_VAL = qn("w:val")
SDT_CONTENT = qn("w:sdtContent")
SDT_PROP = qn("w:sdtPr")


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _extract_text(element) -> str:
    """递归提取元素内所有文本。"""
    return "".join(element.itertext()).strip()


def _make_run(text: str, font_name: str = "Calibri", font_size: int = 10,
              bold: bool = False, color: str = None) -> etree.Element:
    """创建 <w:r> 元素。"""
    r = etree.SubElement(etree.Element("dummy"), qn("w:r"))
    r_props = etree.SubElement(r, qn("w:rPr"))
    etree.SubElement(r_props, qn("w:rFonts")).set(qn("w:ascii"), font_name)
    etree.SubElement(r_props, qn("w:sz")).set(qn("w:val"), str(font_size * 2))
    if bold:
        etree.SubElement(r_props, qn("w:b"))
    if color:
        etree.SubElement(r_props, qn("w:color")).set(qn("w:val"), color)
    t = etree.SubElement(r, qn("w:t"))
    t.text = str(text)
    t.set(qn("xml:space"), "preserve")
    return r


# ═══════════════════════════════════════════════════════════════
# 列映射
# ═══════════════════════════════════════════════════════════════

@dataclass
class ColumnMapping:
    """表格列映射: 列头 → 管线参数 key。"""
    col_index: int        # 列号 (0-based)
    header_text: str      # 原始列头文本
    param_key: str        # 管线参数 key (如 "lag_single_30")
    angle: float | None = None   # 提取的角度值 (如 30.0)
    is_range: bool = False       # 是否为范围参数


def build_col_map(headers: list[str]) -> dict[int, ColumnMapping]:
    """从表头行自动构建列映射。

    利用 excel_reader.py 的 classify_column() 识别列类型，
    从列头文本提取角度值。
    """
    from src.excel_reader import classify_column
    from src.lag_config import _RE_LAG_SINGLE, _RE_LAG_RANGE

    _RE_AR_S = re.compile(
        r"(?:AR|Axial\s*Ratio)\s+at\s+(?:Theta|θ)\s*[=＝]\s*(\d+\.?\d*)",
        re.IGNORECASE)
    _RE_AR_R = re.compile(
        r"(?:AR|Axial\s*Ratio)\s+at\s+(?:Theta|θ)\s*[=＝]\s*(\d+\.?\d*)\s*[-–—~]\s*(\d+\.?\d*)",
        re.IGNORECASE)

    col_map = {}
    for ci, h in enumerate(headers):
        ctype = classify_column(h)
        if ctype is None or ctype == "unknown":
            continue

        angle = None
        is_range = False

        # 提取角度
        if ctype in ("lag_single", "ar_single"):
            rx = _RE_LAG_SINGLE if ctype == "lag_single" else _RE_AR_S
            m = rx.search(h)
            if m:
                angle = float(m.group(1))
        elif ctype in ("lag_range", "ar_range"):
            is_range = True
            rx = _RE_LAG_RANGE if ctype == "lag_range" else _RE_AR_R
            m = rx.search(h)
            if m:
                angle = (float(m.group(1)), float(m.group(2)))

        param_key = ctype
        if angle is not None:
            if is_range:
                param_key = f"{ctype}_{int(angle[0])}_{int(angle[1])}"
            else:
                param_key = f"{ctype}_{int(angle)}"

        col_map[ci] = ColumnMapping(
            col_index=ci, header_text=h, param_key=param_key,
            angle=angle, is_range=is_range)

    return col_map


# ═══════════════════════════════════════════════════════════════
# 核心填充器
# ═══════════════════════════════════════════════════════════════

class DocxTemplateFiller:
    """SDT Tag 绑定的 Word 模板填充器。"""

    # Tag 注册表 (懒加载)
    _registry: dict | None = None

    @classmethod
    def load_registry(cls) -> dict:
        """加载 SDT Tag 注册表。"""
        if cls._registry is not None:
            return cls._registry
        import json
        reg_path = Path(__file__).parent.parent / 'config' / 'sdt_tag_registry.json'
        if reg_path.exists():
            with open(reg_path, encoding='utf-8') as f:
                cls._registry = json.load(f)
        else:
            cls._registry = {}
        return cls._registry

    @classmethod
    def get_all_tags(cls) -> list[str]:
        """获取注册表中所有 tag 名称（展平，含参数占位符展开）。"""
        reg = cls.load_registry()
        all_tags = []
        for cat in ('meta', 'config', 'data', 'table', 'chart', 'img'):
            for key, desc in reg.get(cat, {}).items():
                # 展开参数化 tag
                if '{angle}' in key:
                    for a in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]:
                        all_tags.append(f"{cat}_{key.format(angle=a)}")
                elif '{lo}' in key:
                    all_tags.append(f"{cat}_{key.format(lo=0, hi=70)}")
                elif '{edge}' in key:
                    for e in [45, 30, 22.5]:
                        all_tags.append(f"{cat}_{key.format(edge=int(e))}")
                else:
                    all_tags.append(f"{cat}_{key}")
        return sorted(all_tags)

    @classmethod
    def validate_tag(cls, tag: str) -> tuple[bool, str]:
        """验证 tag 是否在注册表中。返回 (is_valid, description)。"""
        reg = cls.load_registry()
        parts = tag.split('_', 1)
        if len(parts) < 2:
            return False, ""
        cat, rest = parts[0], parts[1]
        cat_dict = reg.get(cat, {})

        def _try_match(key: str):
            if key in cat_dict:
                return (True, cat_dict[key])
            import re as _re
            for pattern, desc in cat_dict.items():
                if '{' in pattern:
                    regex = (pattern
                        .replace('{angle}', r'\d+')
                        .replace('{lo}', r'\d+')
                        .replace('{hi}', r'\d+')
                        .replace('{edge}', r'\d+'))
                    if _re.fullmatch(regex, key):
                        return (True, desc)
            return (False, "")

        # 直接匹配
        ok, desc = _try_match(rest)
        if ok:
            return True, desc

        # 频段后缀剥离
        known_bands = {'L1', 'L5', 'WIDE', 'LOW', 'MID', 'HIGH', 'AMP', 'NOAMP'}
        key = rest
        for _ in range(3):
            rparts = key.rsplit('_', 1)
            if len(rparts) > 1 and rparts[-1].upper() in known_bands:
                key = rparts[0]
            else:
                break
            ok, desc = _try_match(key)
            if ok:
                return True, desc

        return False, f"未注册: '{tag}' (类别={cat})"

    def __init__(self, template_path: str | Path):
        self.template_path = Path(template_path)
        if not self.template_path.exists():
            raise FileNotFoundError(f"模板不存在: {template_path}")
        self.doc = Document(str(template_path))
        self._sdt_map: dict[str, etree.Element] = {}
        self._warnings: list[str] = []
        self._scan()

    # ── 扫描 ──

    def _scan(self):
        """扫描文档中所有 SDT，按 tag 建立索引。"""
        self._sdt_map.clear()
        body = self.doc.element.body
        for sdt in body.iter(f"{{{NS_W}}}sdt"):
            sdt_pr = sdt.find(f"{{{NS_W}}}sdtPr")
            if sdt_pr is None:
                continue
            tag_el = sdt_pr.find(f"{{{NS_W}}}tag")
            if tag_el is None:
                continue
            tag_val = tag_el.get(f"{{{NS_W}}}val")
            if tag_val:
                self._sdt_map[tag_val] = sdt

    def list_tags(self) -> list[str]:
        """列出模板中所有 tag（调试和校验用）。"""
        return sorted(self._sdt_map.keys())

    def get_warnings(self) -> list[str]:
        return self._warnings

    # ── 模式 A: 文本替换 ──

    def fill_text(self, tag: str, value: Any, fmt: str = None):
        """单值 SDT 文本替换。

        Args:
            tag: SDT tag 名称
            value: 要填入的值 (str/int/float/None)
            fmt: 格式化字符串，如 "{:.2f} dBi"。None 则用 str(value)
        """
        sdt = self._sdt_map.get(tag)
        if sdt is None:
            self._warnings.append(f"Tag '{tag}' not found in template")
            return

        content = sdt.find(f"{{{NS_W}}}sdtContent")
        if content is None:
            self._warnings.append(f"Tag '{tag}': no sdtContent")
            return

        # 格式化
        if value is None:
            text = "—"
        elif fmt:
            try:
                text = fmt.format(value)
            except (ValueError, TypeError):
                text = str(value)
        elif isinstance(value, float):
            text = f"{value:.2f}"
        else:
            text = str(value)

        # 找到第一个 <w:p> 中的第一个 <w:r>，替换其 <w:t>
        first_p = content.find(f"{{{NS_W}}}p")
        if first_p is not None:
            first_r = first_p.find(f"{{{NS_W}}}r")
            if first_r is not None:
                first_t = first_r.find(f"{{{NS_W}}}t")
                if first_t is not None:
                    first_t.text = text
                    first_t.set(qn("xml:space"), "preserve")
                    return

        # 回退: 清空 content 并写入新段落
        for child in list(content):
            content.remove(child)
        p = etree.SubElement(content, qn("w:p"))
        r = _make_run(text)
        p.append(r)

    def fill_batch(self, data: dict[str, Any]):
        """批量填充: {tag: value, ...}。value 为 None 的跳过。"""
        for tag, value in data.items():
            if value is not None and value != "":
                self.fill_text(tag, value)

    # ── 模式 B: 表格填充 ──

    def fill_table(self, tag: str, rows: list[dict[str, Any]],
                   col_map: dict[int, ColumnMapping] = None,
                   freq_col: int = 0,
                   style_row: int = None):
        """表格行模板填充：保留样式，按数据行复制。

        Args:
            tag: SDT tag 名称 (标记整表)
            rows: 数据行列表，每个 dict 的 key 对应 col_map 中的 param_key
            col_map: 列映射 (0-based col_index → ColumnMapping)
            freq_col: 频点列号 (0-based)
            style_row: 样式模板行号 (1-based, 相对于表体。None=第一数据行)
        """
        sdt = self._sdt_map.get(tag)
        if sdt is None:
            self._warnings.append(f"Tag '{tag}' not found in template")
            return

        # 找到 SDT 内的 <w:tbl>
        tbl = sdt.find(f".//{{{NS_W}}}tbl")
        if tbl is None:
            self._warnings.append(f"Tag '{tag}': no table found")
            return

        # 收集表行
        trs = list(tbl.iter(f"{{{NS_W}}}tr"))
        if len(trs) < 2:
            self._warnings.append(f"Tag '{tag}': table has <2 rows")
            return

        # 表头行
        header_row = trs[0]

        # 自动构建列映射
        if col_map is None:
            headers = []
            for tc in header_row.iter(f"{{{NS_W}}}tc"):
                headers.append(_extract_text(tc))
            col_map = build_col_map(headers)
            if not col_map:
                self._warnings.append(
                    f"Tag '{tag}': unable to auto-build col_map from headers: {headers}")

        # 样式模板行
        style_idx = style_row if style_row is not None else 1
        if style_idx >= len(trs):
            self._warnings.append(
                f"Tag '{tag}': style_row {style_idx} out of range ({len(trs)} rows)")
            return
        template_row = trs[style_idx]

        # 清除旧数据行（保留表头）
        for tr in trs[1:]:
            tbl.remove(tr)

        # 按频点写入
        for ri, row_data in enumerate(rows):
            new_tr = etree.SubElement(tbl, qn("w:tr"))
            # 复制模板行的属性 (如 trPr/高度)
            tr_pr = template_row.find(f"{{{NS_W}}}trPr")
            if tr_pr is not None:
                new_tr.append(etree.fromstring(etree.tostring(tr_pr)))

            template_cells = list(template_row.iter(f"{{{NS_W}}}tc"))
            num_cols = len(template_cells)

            for ci in range(num_cols):
                new_tc = etree.SubElement(new_tr, qn("w:tc"))

                # 复制单元格属性 (宽度、边框、背景色等)
                if ci < len(template_cells):
                    tc_pr = template_cells[ci].find(f"{{{NS_W}}}tcPr")
                    if tc_pr is not None:
                        new_tc.append(etree.fromstring(etree.tostring(tc_pr)))

                # 填入值
                p = etree.SubElement(new_tc, qn("w:p"))

                if ci == freq_col:
                    val = row_data.get("frequency", row_data.get("freq", ""))
                    if isinstance(val, float):
                        val = f"{val:.0f}"
                    elif val is None:
                        val = ""
                elif ci in col_map:
                    cm = col_map[ci]
                    val = row_data.get(cm.param_key)
                    if val is not None and isinstance(val, float):
                        val = f"{val:.2f}"
                    elif val is None:
                        val = ""
                else:
                    val = ""

                r = _make_run(str(val))
                p.append(r)

    def auto_fill_table(self, tag: str, pipeline_result: dict,
                        freq_list: list[float] = None):
        """自动填充表格: 自动识别列头 + 从 pipeline 结果提取数据。

        Args:
            tag: SDT tag
            pipeline_result: run_pipeline() 返回的结果 dict
            freq_list: 频点列表 (None 则从结果中推断)
        """
        sdt = self._sdt_map.get(tag)
        if sdt is None:
            self._warnings.append(f"Tag '{tag}' not found")
            return

        tbl = sdt.find(f".//{{{NS_W}}}tbl")
        if tbl is None:
            self._warnings.append(f"Tag '{tag}': no table")
            return

        trs = list(tbl.iter(f"{{{NS_W}}}tr"))
        if len(trs) < 2:
            return

        # 识别表头
        headers = []
        for tc in trs[0].iter(f"{{{NS_W}}}tc"):
            headers.append(_extract_text(tc))
        col_map = build_col_map(headers)

        # 从结果提取数据行
        if freq_list is None:
            # 推断频点
            all_keys = set()
            for sheet_results in pipeline_result.values():
                for row in sheet_results:
                    all_keys.add(row.get("frequency"))
            freq_list = sorted(all_keys)

        rows = []
        for freq in freq_list:
            row_data = {"frequency": freq}
            # 从各个 sheet 结果中查找该频点的数据
            found = False
            for sheet_results in pipeline_result.values():
                for r in sheet_results:
                    if r.get("frequency") == freq:
                        found = True
                        for cm in col_map.values():
                            if cm.param_key in r:
                                row_data[cm.param_key] = r[cm.param_key]
                            # 也尝试原始 col_type key
                            if cm.angle is not None:
                                base_key = cm.param_key.rsplit("_", 1)[0]
                                if base_key in r:
                                    row_data[cm.param_key] = r[base_key]
            if found:
                rows.append(row_data)

        self.fill_table(tag, rows, col_map)

    # ── 模式 C: 图片替换 ──

    def fill_image(self, tag: str, image_data: bytes | str | Path,
                   width_cm: float = 8.0, height_cm: float = None):
        """SDT 图片占位替换。

        Args:
            tag: SDT tag
            image_data: PNG 文件路径 或 bytes
            width_cm: 图片宽度 (cm)，高度自动按比例
            height_cm: 图片高度 (cm)，None 则自动
        """
        sdt = self._sdt_map.get(tag)
        if sdt is None:
            self._warnings.append(f"Tag '{tag}' not found in template")
            return

        content = sdt.find(f"{{{NS_W}}}sdtContent")
        if content is None:
            self._warnings.append(f"Tag '{tag}': no sdtContent")
            return

        # 读取图片数据
        if isinstance(image_data, (str, Path)):
            image_descriptor = str(image_data)
        elif isinstance(image_data, bytes):
            image_descriptor = io.BytesIO(image_data)
        else:
            self._warnings.append(f"Tag '{tag}': invalid image_data type")
            return

        # 清空 SDT 内容
        for child in list(content):
            content.remove(child)

        # 用 python-docx 的 new_pic_inline 创建图片（自动处理 part 和 rId）
        inline_shape = self.doc.part.new_pic_inline(
            image_descriptor,
            width=Cm(width_cm),
            height=Cm(height_cm) if height_cm else None,
        )

        # 构建段落包含图片
        p = etree.SubElement(content, qn('w:p'))
        r = etree.SubElement(p, qn('w:r'))
        drawing = etree.SubElement(r, qn('w:drawing'))
        drawing.append(inline_shape)

    # ── 输出 ──

    def save(self, output_path: str | Path):
        """保存填充后的文档。"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(str(output_path))

    def warn_count(self) -> int:
        return len(self._warnings)
