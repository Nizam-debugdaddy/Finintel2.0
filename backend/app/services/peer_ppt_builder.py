"""
peer_ppt_builder.py — Builds peer comparison PPT matching the CIPLA template format.

Template structure (from Summary_CIPLA.pptx analysis):
  Slide 1: Title — teal accent bar left, company name, date range
  Slide 2: Key Financial Metrics — dark navy header, 6 KPI cards (colored boxes)
  Slide 3: Cost Structure — chart image
  Slide 4: Revenue & Trend — bar+line chart
  Slide 5: Altman Z — gauge-style with zone bands
"""
from __future__ import annotations
import io
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── Brand palette (from CIPLA template) ───────────────────────────────────────
C_NAVY   = RGBColor(0x0B, 0x25, 0x45)
C_TEAL   = RGBColor(0x0D, 0x94, 0x88)
C_WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
C_LIGHT  = RGBColor(0xF8, 0xFA, 0xFC)
C_SLATE  = RGBColor(0x64, 0x74, 0x8B)

# KPI card colors (matches slide 2 of CIPLA template)
KPI_COLORS = [
    RGBColor(0x0D, 0x94, 0x88),  # teal   — Revenue
    RGBColor(0x25, 0x63, 0xEB),  # blue   — EBITDA
    RGBColor(0x05, 0x96, 0x69),  # green  — PAT
    RGBColor(0x7C, 0x3A, 0xED),  # purple — EBITDA Margin
    RGBColor(0xD9, 0x77, 0x06),  # amber  — Altman Z
    RGBColor(0x08, 0x91, 0xB2),  # cyan   — Current Ratio
]

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.50)


def _add_rect(slide, left, top, width, height, fill_rgb=None, line_rgb=None):
    shape = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))
    if fill_rgb:
        shape.fill.solid(); shape.fill.fore_color.rgb = fill_rgb
    else:
        shape.fill.background()
    if line_rgb:
        shape.line.color.rgb = line_rgb
        shape.line.width = Pt(1)
    else:
        shape.line.fill.background()
    return shape


def _add_text(slide, left, top, width, height, text, size, bold=False,
              color=None, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    p  = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color or C_NAVY
    return tb


def _add_picture(slide, img_bytes: bytes, left, top, width, height):
    buf = io.BytesIO(img_bytes)
    slide.shapes.add_picture(buf, Inches(left), Inches(top), Inches(width), Inches(height))


def _slide_header(slide, title: str, subtitle: str = ""):
    """Dark navy header bar matching the CIPLA template."""
    _add_rect(slide, 0, 0, 13.33, 1.1, C_NAVY)
    _add_text(slide, 0.3, 0.12, 12.5, 0.55, title, 22, bold=True, color=C_WHITE)
    if subtitle:
        _add_text(slide, 0.3, 0.64, 12.5, 0.32, subtitle, 10, color=RGBColor(0xAD,0xD8,0xE6))


def build_peer_ppt(
    companies: list[str],
    period: str,
    report_type: str,
    cost_data: dict,
    metric_table: dict,
    metrics: list[str],
    cost_png_abs: bytes,
    cost_png_pct: bytes,
    metric_png: bytes,
) -> bytes:
    """
    Build a peer comparison PPT matching the CIPLA template format.

    Slides:
      1. Title slide — companies + period
      2. Key Financial Metrics — KPI cards per company
      3. Cost Structure — absolute stacked bar image
      4. Cost Structure — % Revenue/Total Cost image
      5. Multi-Metric KPI Comparison chart
    """
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H
    blank = prs.slide_layouts[6]   # completely blank

    # ── SLIDE 1: Title ─────────────────────────────────────────────
    s1 = prs.slides.add_slide(blank)
    # Teal accent stripe on left (matches CIPLA template)
    _add_rect(s1, 0, 0, 0.08, 7.5, C_TEAL)
    _add_text(s1, 0.5, 0.7, 9, 0.34, "FINANCIAL ANALYTICS SUMMARY — PEER COMPARISON",
              9, bold=False, color=C_TEAL)
    cos_str = "  ·  ".join(companies)
    _add_text(s1, 0.5, 1.3, 12, 1.2, cos_str, 32, bold=True, color=C_NAVY)
    _add_text(s1, 0.5, 3.0, 9, 0.5, period, 16, bold=False, color=C_TEAL)
    _add_text(s1, 0.5, 6.9, 9, 0.4, "FinIntel Financial Analytics Platform",
              9, color=C_SLATE)

    # ── SLIDE 2: KPI Cards ─────────────────────────────────────────
    s2 = prs.slides.add_slide(blank)
    _slide_header(s2, "Key Financial Metrics", f"{period}  ·  {', '.join(companies)}")

    kpi_keys = [
        ("Revenue",              "revenue",        "value",  "INR Mn"),
        ("EBITDA",               "ebitda",         "value",  "INR Mn"),
        ("PAT",                  "pat",            "value",  "INR Mn"),
        ("EBITDA Margin",        "ebitda",         "margin", "%"),
        ("Altman Z Score",       "altman_z",       "value",  ""),
        ("Current Ratio",        "current_ratio",  "value",  "Ratio"),
    ]

    card_w = 4.0; card_h = 2.3
    col_positions = [0.3, 4.6, 8.9]
    row_positions = [1.4, 4.1]
    card_idx = 0

    for ri, row_top in enumerate(row_positions):
        for ci, col_left in enumerate(col_positions):
            if card_idx >= len(kpi_keys): break
            label, kpi_k, sub_k, unit = kpi_keys[card_idx]
            color = KPI_COLORS[card_idx % len(KPI_COLORS)]

            _add_rect(s2, col_left, row_top, card_w, card_h, color)

            _add_text(s2, col_left+0.15, row_top+0.15, card_w-0.3, 0.4,
                      label, 11, bold=False, color=C_WHITE)

            # Aggregate: for multi-company, show first company that has data
            vals = []
            for co in companies:
                tbl = metric_table.get(label, metric_table.get(kpi_k, {}))
                v = tbl.get(co) if isinstance(tbl, dict) else None
                if v is not None: vals.append(v)

            val_str = f"{vals[0]:,.0f}" if vals else "—"
            _add_text(s2, col_left+0.15, row_top+0.6, card_w-0.3, 0.77,
                      val_str, 28, bold=True, color=C_WHITE)
            if vals and len(companies) > 1:
                extra = "  /  ".join(
                    f"{companies[i]}: {vals[i]:,.0f}" for i in range(min(len(vals), 3))
                )
                _add_text(s2, col_left+0.15, row_top+1.45, card_w-0.3, 0.45,
                          extra, 7, color=C_WHITE)
            elif unit:
                _add_text(s2, col_left+0.15, row_top+1.45, card_w-0.3, 0.34,
                          unit, 10, color=C_WHITE)
            card_idx += 1

    # ── SLIDE 3: Cost Structure (Absolute) ─────────────────────────
    s3 = prs.slides.add_slide(blank)
    _slide_header(s3, "Cost Structure Comparison — Absolute (INR Mn)",
                  f"{period}  ·  {', '.join(companies)}")
    if cost_png_abs:
        _add_picture(s3, cost_png_abs, 0.3, 1.15, 12.7, 6.1)

    # ── SLIDE 4: Cost Structure (% Revenue) ────────────────────────
    s4 = prs.slides.add_slide(blank)
    _slide_header(s4, "Cost Composition — % of Revenue",
                  f"{period}  ·  {', '.join(companies)}")
    if cost_png_pct:
        _add_picture(s4, cost_png_pct, 0.3, 1.15, 12.7, 6.1)

    # ── SLIDE 5: Multi-Metric KPI ──────────────────────────────────
    s5 = prs.slides.add_slide(blank)
    _slide_header(s5, "Multi-Metric KPI Comparison",
                  f"{period}  ·  Metrics: {', '.join(metrics[:5])}")
    if metric_png:
        _add_picture(s5, metric_png, 0.3, 1.15, 8.8, 5.8)

    # Compact table on the right (slide 5)
    tbl_left = 9.3; tbl_top = 1.15; col_w = 1.0; row_h = 0.32
    n_rows = len(metrics) + 1; n_cols = len(companies) + 1
    tbl = s5.shapes.add_table(
        n_rows, n_cols,
        Inches(tbl_left), Inches(tbl_top),
        Inches(col_w * n_cols), Inches(row_h * n_rows)
    ).table
    # Header
    tbl.cell(0, 0).text = "Metric"
    for ci, co in enumerate(companies):
        tbl.cell(0, ci+1).text = co
    for ci in range(n_cols):
        p = tbl.cell(0, ci).text_frame.paragraphs[0]
        p.runs[0].font.bold = True; p.runs[0].font.size = Pt(8)
        p.runs[0].font.color.rgb = C_NAVY
    # Rows
    for ri, metric in enumerate(metrics):
        tbl.cell(ri+1, 0).text = metric[:20]
        tbl.cell(ri+1, 0).text_frame.paragraphs[0].runs[0].font.size = Pt(7)
        for ci, co in enumerate(companies):
            v = metric_table.get(metric, {}).get(co)
            txt = f"{v:,.1f}" if v is not None else "—"
            cell = tbl.cell(ri+1, ci+1)
            cell.text = txt
            cell.text_frame.paragraphs[0].runs[0].font.size = Pt(7)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
