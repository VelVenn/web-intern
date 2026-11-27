"""Generate a formal Word (.docx) report strictly following 附件4-报告撰写提纲及规范.pdf."""

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
FINAL = ROOT / "results" / "final"
FIGDIR = FINAL / "figures"
MD_PATH = FINAL / "report.md"
OUT_DOCX = FINAL / "report.docx"

# Fonts (Windows Word renders SimSun/SimHei/KaiTi natively; macOS maps smoothly too)
FONT_SONG = "宋体"
FONT_HEI = "黑体"
FONT_KAI = "楷体"
FONT_EN = "Times New Roman"


def set_run_font(run, cn_font: str, size_pt: float, bold: bool = False, color=None):
    run.font.name = FONT_EN
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), FONT_EN)
    rFonts.set(qn("w:hAnsi"), FONT_EN)
    rFonts.set(qn("w:cs"), FONT_EN)
    rFonts.set(qn("w:eastAsia"), cn_font)


def format_paragraph(p, line_spacing=1.5, before_pt=0, after_pt=0, first_line_chars=0, align=None):
    pf = p.paragraph_format
    pf.line_spacing = line_spacing
    pf.space_before = Pt(before_pt)
    pf.space_after = Pt(after_pt)
    if align is not None:
        p.alignment = align
    if first_line_chars > 0:
        pPr = p._p.get_or_add_pPr()
        ind = pPr.find(qn("w:ind"))
        if ind is None:
            ind = OxmlElement("w:ind")
            pPr.append(ind)
        ind.set(qn("w:firstLineChars"), str(int(first_line_chars * 100)))


def add_mixed_runs(p, text: str, cn_font=FONT_SONG, size_pt=12.0, base_bold=False):
    """Parse **bold**, `code`, and inline $math$ cleanly into Word runs."""
    # Convert simple inline LaTeX to clean Unicode math for Word readability
    def clean_math(m):
        s = m.group(1)
        s = s.replace(r"\mathrm{", "").replace(r"\text{", "").replace(r"\ ", " ")
        s = s.replace(r"\le", "≤").replace(r"\ge", "≥").replace(r"\times", "×")
        s = s.replace(r"\beta", "β").replace(r"\approx", "≈").replace(r"\in", "∈")
        s = s.replace(r"\{", "{").replace(r"\}", "}").replace(r"\_", "_")
        s = s.replace("G_i", "Gi").replace("}", "")
        return s

    text = re.sub(r"\$([^$]+)\$", clean_math, text)
    # Remove backticks around identifiers
    text = text.replace("`", "")

    # Split on **...**
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    for part in parts:
        if not part:
            continue
        is_bold = base_bold
        content = part
        if part.startswith("**") and part.endswith("**"):
            is_bold = True
            content = part[2:-2]
        # Handle citation superscripts like [1] or [1,7]
        subparts = re.split(r"(\[[0-9,]+\])", content)
        for sp in subparts:
            if not sp:
                continue
            r = p.add_run(sp)
            set_run_font(r, cn_font, size_pt, bold=is_bold)
            if re.fullmatch(r"\[[0-9,]+\]", sp) and not p.text.startswith("["):
                r.font.superscript = True


def add_page_number_footer(section):
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run()
    set_run_font(r, FONT_SONG, 10.5)
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    r._r.append(fld_begin)
    r._r.append(instr)
    r._r.append(fld_sep)
    r._r.append(fld_end)


def style_three_line_table(table):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        '<w:top w:val="single" w:sz="12" w:space="0" w:color="000000"/>'
        '<w:bottom w:val="single" w:sz="12" w:space="0" w:color="000000"/>'
        '<w:insideH w:val="none"/>'
        '<w:left w:val="none"/>'
        '<w:right w:val="none"/>'
        '<w:insideV w:val="none"/>'
        "</w:tblBorders>"
    )
    tblPr.append(borders)
    # Add thin bottom border to header row
    for cell in table.rows[0].cells:
        tcPr = cell._tc.get_or_add_tcPr()
        tcBorders = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
            "</w:tcBorders>"
        )
        tcPr.append(tcBorders)


def add_empty_line(doc):
    p = doc.add_paragraph()
    format_paragraph(p, line_spacing=1.5, before_pt=0, after_pt=0)
    r = p.add_run("")
    set_run_font(r, FONT_SONG, 12.0)


def add_equation(doc, text: str, num: str):
    p = doc.add_paragraph()
    format_paragraph(p, line_spacing=1.5, before_pt=3, after_pt=3, align=WD_ALIGN_PARAGRAPH.CENTER)
    r1 = p.add_run(f"{text}        （{num}）")
    set_run_font(r1, FONT_SONG, 12.0)


def add_table(doc, caption: str, headers: list[str], rows: list[list[str]]):
    add_empty_line(doc)
    cp = doc.add_paragraph()
    format_paragraph(cp, line_spacing=1.5, before_pt=0, after_pt=2, align=WD_ALIGN_PARAGRAPH.CENTER)
    cr = cp.add_run(caption)
    set_run_font(cr, FONT_SONG, 11.0, bold=True)

    tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
    style_three_line_table(tbl)

    for j, h in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = cell.paragraphs[0]
        format_paragraph(p, line_spacing=1.2, before_pt=2, after_pt=2, align=WD_ALIGN_PARAGRAPH.CENTER)
        add_mixed_runs(p, h.replace("<br>", "\n"), FONT_SONG, 10.0, base_bold=True)

    for i, row in enumerate(rows, 1):
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 and len(headers) <= 3 else WD_ALIGN_PARAGRAPH.CENTER
            format_paragraph(p, line_spacing=1.2, before_pt=2, after_pt=2, align=align)
            add_mixed_runs(p, val.replace("<br>", "\n"), FONT_SONG, 10.0, base_bold=False)

    add_empty_line(doc)


def add_figure(doc, img_rel: str, caption: str):
    add_empty_line(doc)
    img_path = FINAL / img_rel
    p = doc.add_paragraph()
    format_paragraph(p, line_spacing=1.0, before_pt=0, after_pt=2, align=WD_ALIGN_PARAGRAPH.CENTER)
    run = p.add_run()
    run.add_picture(str(img_path), width=Inches(5.8))

    cp = doc.add_paragraph()
    format_paragraph(cp, line_spacing=1.5, before_pt=2, after_pt=0, align=WD_ALIGN_PARAGRAPH.CENTER)
    cr = cp.add_run(caption)
    set_run_font(cr, FONT_SONG, 11.0)
    add_empty_line(doc)


def build_docx():
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Cm(2.4)
    sec.bottom_margin = Cm(2.4)
    sec.left_margin = Cm(2.4)
    sec.right_margin = Cm(2.4)
    add_page_number_footer(sec)

    # Set Normal style base
    normal = doc.styles["Normal"]
    normal.font.name = FONT_EN
    normal.font.size = Pt(12.0)
    normal.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    normal._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT_SONG)

    lines = MD_PATH.read_text(encoding="utf-8").splitlines()
    i = 0
    in_refs = False
    pending_table_caption = None

    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line == "---":
            continue

        # Main Title (# ...)
        if line.startswith("# "):
            p = doc.add_paragraph()
            format_paragraph(p, line_spacing=1.5, before_pt=6, after_pt=12, align=WD_ALIGN_PARAGRAPH.CENTER)
            r = p.add_run(line[2:].strip())
            set_run_font(r, FONT_HEI, 18.0, bold=True)
            continue

        # Level-1 headings (## ...)
        if line.startswith("## "):
            heading = line[3:].strip()
            if heading == "摘要":
                p = doc.add_paragraph()
                format_paragraph(p, line_spacing=1.5, before_pt=6, after_pt=6, align=WD_ALIGN_PARAGRAPH.CENTER)
                # 4-char spacing between 摘 and 要 per 附件4
                r = p.add_run("摘\u3000\u3000\u3000\u3000要")
                set_run_font(r, FONT_HEI, 14.0, bold=True)
            elif heading == "参考文献":
                in_refs = True
                add_empty_line(doc)
                p = doc.add_paragraph()
                format_paragraph(p, line_spacing=1.5, before_pt=6, after_pt=6, align=WD_ALIGN_PARAGRAPH.CENTER)
                # 1-char spacing between characters per 附件4
                r = p.add_run("参 考 文 献")
                set_run_font(r, FONT_HEI, 14.0, bold=True)
            else:
                p = doc.add_paragraph()
                format_paragraph(p, line_spacing=1.5, before_pt=6, after_pt=0, align=WD_ALIGN_PARAGRAPH.LEFT)
                r = p.add_run(heading)
                set_run_font(r, FONT_HEI, 14.0, bold=True)
            continue

        # Level-2 headings (### ...)
        if line.startswith("### "):
            heading = line[4:].strip()
            p = doc.add_paragraph()
            format_paragraph(p, line_spacing=1.5, before_pt=4, after_pt=0, align=WD_ALIGN_PARAGRAPH.LEFT)
            r = p.add_run(heading)
            set_run_font(r, FONT_HEI, 12.0, bold=True)
            continue

        # Level-3 headings (#### ...): Kaiti 12pt left-aligned per 附件4
        if line.startswith("#### "):
            heading = line[5:].strip()
            p = doc.add_paragraph()
            format_paragraph(p, line_spacing=1.5, before_pt=2, after_pt=0, align=WD_ALIGN_PARAGRAPH.LEFT)
            r = p.add_run(heading)
            set_run_font(r, FONT_KAI, 12.0, bold=False)
            continue

        # Numbered sub-items on their own line like （1）慢开始阶段
        if re.fullmatch(r"（\d+）[^。；：]+", line):
            p = doc.add_paragraph()
            format_paragraph(p, line_spacing=1.5, before_pt=0, after_pt=0, first_line_chars=2)
            r = p.add_run(line)
            set_run_font(r, FONT_SONG, 12.0, bold=False)
            continue

        # Keywords line
        if line.startswith("**关键词：**"):
            kw_text = line.replace("**关键词：**", "").strip()
            # Replace double spaces with 2 full-width spaces (2-char spacing per 附件4)
            kw_items = re.split(r"\s{2,}", kw_text)
            p = doc.add_paragraph()
            format_paragraph(p, line_spacing=1.5, before_pt=4, after_pt=12, align=WD_ALIGN_PARAGRAPH.LEFT)
            r0 = p.add_run("关键词：")
            set_run_font(r0, FONT_HEI, 12.0, bold=True)
            r1 = p.add_run("\u3000\u3000".join(kw_items))
            set_run_font(r1, FONT_SONG, 12.0)
            continue

        # Display equations $$...$$
        if line.startswith("$$") and line.endswith("$$"):
            eq = line[2:-2].strip()
            tag_m = re.search(r"\\tag\{([^}]+)\}", eq)
            tag = tag_m.group(1) if tag_m else ""
            if tag == "1":
                eq_txt = "rtt_inflation = (当前窗口平均 RTT / 连接历史最小 RTT) − 1"
            elif tag == "2":
                eq_txt = "ssthresh = MSS × max(2, floor(β × cwnd / MSS))"
            elif tag == "3":
                eq_txt = "J = (Σ Gi)² / (n × Σ Gi²)"
            else:
                eq_txt = eq
            add_equation(doc, eq_txt, tag)
            continue

        # Figure markdown line ![...](path) followed by <p align="center">图X ...</p>
        if line.startswith("!["):
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line)
            if m:
                cap_default, img_rel = m.group(1), m.group(2)
                caption = cap_default
                # Look ahead for <p align="center">图...
                j = i
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and lines[j].strip().startswith('<p align="center">图'):
                    caption = re.sub(r"<[^>]+>", "", lines[j].strip()).strip()
                    i = j + 1
                add_figure(doc, img_rel, caption)
            continue

        # Table caption <p align="center">表...
        if line.startswith('<p align="center">表'):
            pending_table_caption = re.sub(r"<[^>]+>", "", line).strip()
            continue

        # Markdown table block
        if line.startswith("|"):
            tbl_lines = [line]
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl_lines.append(lines[i].strip())
                i += 1
            headers = [c.strip() for c in tbl_lines[0].strip("|").split("|")]
            rows = []
            for tl in tbl_lines[2:]:
                rows.append([c.strip() for c in tl.strip("|").split("|")])
            add_table(doc, pending_table_caption or "表", headers, rows)
            pending_table_caption = None
            continue

        # Sub-headings like **（1）...** (treat as Level-3 Kaiti 12pt bold or indented lead-in)
        if re.fullmatch(r"\*\*（\d+）[^*]+\*\*", line):
            p = doc.add_paragraph()
            format_paragraph(p, line_spacing=1.5, before_pt=2, after_pt=0, align=WD_ALIGN_PARAGRAPH.LEFT)
            r = p.add_run(line[2:-2])
            set_run_font(r, FONT_KAI, 12.0, bold=True)
            continue

        # References lines
        if in_refs and re.match(r"^\[\d+\]", line):
            p = doc.add_paragraph()
            format_paragraph(p, line_spacing=1.5, before_pt=0, after_pt=0, align=WD_ALIGN_PARAGRAPH.LEFT)
            p.paragraph_format.left_indent = Cm(0.75)
            p.paragraph_format.first_line_indent = Cm(-0.75)
            add_mixed_runs(p, line, FONT_SONG, 12.0)
            continue

        # Bullet / numbered list items
        if line.startswith("- ") or re.match(r"^\d+\.\s+", line):
            clean_item = line[2:].strip() if line.startswith("- ") else line
            prefix = "● " if line.startswith("- ") else ""
            p = doc.add_paragraph()
            format_paragraph(p, line_spacing=1.5, before_pt=0, after_pt=0, first_line_chars=2)
            add_mixed_runs(p, prefix + clean_item, FONT_SONG, 12.0)
            continue

        # Normal body paragraph (first-line indent 2 Chinese chars)
        p = doc.add_paragraph()
        format_paragraph(p, line_spacing=1.5, before_pt=0, after_pt=0, first_line_chars=2)
        add_mixed_runs(p, line, FONT_SONG, 12.0)

    doc.save(str(OUT_DOCX))
    print(f"Saved {OUT_DOCX} ({OUT_DOCX.stat().st_size} bytes)")


if __name__ == "__main__":
    build_docx()
