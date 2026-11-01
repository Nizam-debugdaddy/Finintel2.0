import traceback, aiosqlite
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from typing import Optional
from app.services.service_factory import get_fresh_service
from app.db.sqlite_db import DB

router = APIRouter()

async def _log_export(company_id: str, fmt: str, status: str, path: str = "", err: str = ""):
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT INTO export_log(company_id,format,status,file_path,error_msg) VALUES(?,?,?,?,?)",
                (company_id, fmt, status, path, err[:500])
            )
            await db.commit()
    except Exception:
        pass

@router.post("/excel/{company_id}")
async def export_excel(
    company_id: str,
    period: Optional[str] = Query(None),
    report_type: str = Query("consolidated"),
):
    svc = get_fresh_service()
    try:
        out_path = svc.generate_excel(company_id, report_type=report_type)
        await _log_export(company_id, "excel", "success", str(out_path))
        return FileResponse(
            str(out_path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"Output_Analysis_{company_id}.xlsx"
        )
    except Exception as e:
        detail = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}"
        await _log_export(company_id, "excel", "failed", err=detail)
        raise HTTPException(500, f"Excel export failed: {type(e).__name__}: {e}")

@router.post("/ppt/{company_id}")
async def export_ppt(
    company_id: str,
    period: Optional[str] = Query(None),
    report_type: str = Query("consolidated"),
):
    svc = get_fresh_service()
    try:
        from app.services.ppt_service import PPTService
        ppt_bytes = PPTService(svc).generate(company_id)
        await _log_export(company_id, "ppt", "success")
        return Response(
            ppt_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f"attachment; filename=Summary_{company_id}.pptx"}
        )
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        await _log_export(company_id, "ppt", "failed", err=detail)
        raise HTTPException(500, f"PPT export failed: {detail}")

@router.post("/pdf/{company_id}")
async def export_pdf(
    company_id: str,
    period: Optional[str] = Query(None),
    report_type: str = Query("consolidated"),
):
    """
    Generate PDF for a company.
    Returns binary application/pdf — the frontend validates the %PDF magic bytes
    before saving; a 500 JSON error is distinguishable from valid PDF bytes.
    """
    svc = get_fresh_service()
    try:
        from app.services.pdf_service import PDFService
        pdf_bytes = PDFService(svc).generate(
            company_id,
            period=period,
            report_type=report_type,
        )
        await _log_export(company_id, "pdf", "success")
        return Response(
            pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=Report_{company_id}.pdf",
                "Content-Length": str(len(pdf_bytes)),
            }
        )
    except Exception as e:
        detail = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-600:]}"
        await _log_export(company_id, "pdf", "failed", err=detail)
        # Return 500 so frontend can distinguish from valid PDF
        raise HTTPException(500, f"PDF export failed: {type(e).__name__}: {e}")

@router.get("/logs/{company_id}")
async def export_logs(company_id: str):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM export_log WHERE company_id=? ORDER BY created_at DESC LIMIT 20",
            (company_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/cost-structure-ppt")
async def export_cost_structure_ppt(request: Request):
    """
    Builds a native editable PowerPoint 100% stacked column chart.
    Changes (v33): Cr instead of Mn for revenue, no gridlines, no header,
    larger managerial insight text, footer with data source, no collisions.
    """
    import tempfile, traceback as tb, math
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.chart.data import ChartData
    from pptx.enum.text import PP_ALIGN
    from pptx.oxml.ns import qn
    from lxml import etree
    import copy

    try:
        payload  = await request.json()
        bars     = payload.get("bars", [])
        title    = payload.get("title",    "Cost Structure Analysis")
        subtitle = payload.get("subtitle", "")
        mode     = payload.get("mode",     "dashboard")
        is_peer  = (mode == "peer")

        # ── Full company names for professional presentation ────────────────
        COMPANY_NAMES = {
            "SUN":       "Sun Pharmaceutical Industries Ltd",
            "CIPLA":     "Cipla Ltd",
            "DRL":       "Dr. Reddy's Laboratories Ltd",
            "LUPIN":     "Lupin Ltd",
            "AUROBINDO": "Aurobindo Pharma Ltd",
        }
        # Expand any ticker found in the title into its full corporate name
        display_title = title
        for tk, full in COMPANY_NAMES.items():
            if tk in display_title:
                display_title = display_title.replace(tk, full)
                break

        if not bars:
            raise HTTPException(400, "bars array is required")

        N = len(bars)

        # ── Segment stack order (bottom→top) ─────────────────────────────────
        STACK = [
            ("Others",                  (0x92, 0x40, 0x0E)),
            ("Transportation",          (0xB4, 0x53, 0x09)),
            ("Manpower",                (0xD9, 0x77, 0x06)),
            ("Power & Fuel",            (0xF5, 0x9E, 0x0B)),
            ("Raw Material Cost",       (0xFB, 0xBF, 0x24)),
            ("Interest & Depreciation", (0xFC, 0xD3, 0x4D)),
            ("Operational PBT",         (0xFD, 0xE6, 0x8A)),
        ]
        ALIASES = {
            "Remaining Expenses":          "Others",
            "Rest in Other Expenses":      "Others",
            "Consumables":                 "Others",
            "Finance Costs":               "Interest & Depreciation",
            "Depreciation & Amortization": "Interest & Depreciation",
        }

        def resolve(raw: dict) -> dict:
            out = {k: 0.0 for k, _ in STACK}
            for k, v in raw.items():
                dk = ALIASES.get(k, k)
                if dk in out:
                    out[dk] += float(v or 0)
            # Keep positive segments, AND Operational PBT even when negative (loss
            # years) so it can be drawn below the zero line.
            return {k: v for k, v in out.items()
                    if v > 0 or (k == "Operational PBT" and v != 0)}

        # ── Use ACTUAL % values for both heights and labels ──────────────────
        # This matches the web chart exactly: no redistribution, no min-height.
        # Loss years naturally have cost stacks > 100 %; the Y-axis is set
        # dynamically to accommodate them.
        LBL_SIZE = 11

        bar_actual = [resolve(b.get("segments", {})) for b in bars]

        # ── ChartData — actual % values as both heights and data points ──────
        # Absent segments are None (blank point) rather than 0 to avoid stray
        # "0.0%" labels at segment boundaries.
        chart_data = ChartData()
        chart_data.categories = [b["barKey"] for b in bars]
        series_segs = []
        for seg_name, _ in STACK:
            raw = [bar_actual[i].get(seg_name) for i in range(N)]
            if any(v is not None and abs(v) > 1e-9 for v in raw):
                chart_data.add_series(
                    seg_name,
                    tuple(round(v, 3) if v is not None else None for v in raw),
                )
                series_segs.append(seg_name)

        # ── Slide dimensions ─────────────────────────────────────────────────
        SLIDE_W = Inches(13.33)
        SLIDE_H = Inches(8.50)   # expanded to fit legend row

        # ── Layout zones (top→bottom) ────────────────────────────────────────
        TITLE_Y     = 0.16
        INSIGHT_Y   = 0.48
        INSIGHT_H   = 0.65   # taller insight block
        SUBTITLE_Y  = INSIGHT_Y + INSIGHT_H + 0.08
        SEP_Y       = SUBTITLE_Y + 0.28 + 0.04
        REV_LABEL_Y = SEP_Y + 0.09
        CHART_TOP_F = REV_LABEL_Y + 0.32
        OVAL_Y      = 6.55   # pushed down → chart gets more height
        YR_LABEL_Y  = OVAL_Y + 0.446 + 0.06
        LEGEND_Y    = YR_LABEL_Y + 0.30 + 0.10   # row-1 of legend
        LEGEND_Y2   = LEGEND_Y + 0.32             # row-2 of legend (0.28 row-height + 0.04 gap)
        FOOTER_Y    = LEGEND_Y2 + 0.32 + 0.06    # footer below both legend rows

        CHART_LEFT  = 0.45
        CHART_W     = 12.40
        CHART_H     = OVAL_Y - CHART_TOP_F - 0.05   # fills space between rev labels and ovals

        # EBITDA label and oval geometry
        OVAL_W      = 0.812
        OVAL_H      = 0.446

        # Bar x-position formula
        PLOT_LEFT_M = 0.596 + (6 - N) * 0.034
        PLOT_W      = 11.712 - (6 - N) * 0.077
        bar_slot    = PLOT_W / N

        def bar_center(i: int) -> float:
            return 0.45 + PLOT_LEFT_M + bar_slot * (i + 0.5)

        def oval_left(i: int) -> float:
            return bar_center(i) - OVAL_W / 2

        def rev_label_left(i: int) -> float:
            return bar_center(i) - 1.273 / 2

        # ── Build presentation ────────────────────────────────────────────────
        prs = Presentation()
        prs.slide_width  = SLIDE_W
        prs.slide_height = SLIDE_H
        slide = prs.slides.add_slide(prs.slide_layouts[6])   # blank

        DARK   = RGBColor(0x1B, 0x2A, 0x4A)
        GRAY   = RGBColor(0x64, 0x74, 0x8B)
        GREEN  = RGBColor(0x05, 0x96, 0x69)
        ORANGE = RGBColor(0xEA, 0x58, 0x0C)
        SLATE  = RGBColor(0x64, 0x74, 0x8B)

        # ─────────────────────────────────────────────────────────────────────
        # 1. MANAGERIAL INSIGHT (large, prominent, no header label prefix)
        # ─────────────────────────────────────────────────────────────────────
        def _fmt_pct(v): return f"{v:.1f}%"
        def _seg_of(b, key):
            return resolve(b.get("segments", {})).get(key, 0.0)

        annual   = [b for b in bars if not b.get("isAverage")]
        avg_bar  = next((b for b in bars if b.get("isAverage")), None)
        ref_bar  = avg_bar or (annual[-1] if annual else bars[-1])

        insight_parts = []
        try:
            if not is_peer:
                # Company name from the expanded display title
                comp_name = display_title.split("—")[-1].strip() if "—" in display_title else display_title
                # Report type: first segment of subtitle before "·"
                rep_type = subtitle.split("·")[0].strip().lower() if subtitle else "consolidated"

                # Average RM % and PBT % across all annual bars
                rm_vals  = [v for v in [_seg_of(b, "Raw Material Cost") for b in annual] if v > 0]
                pbt_vals = [v for v in [_seg_of(b, "Operational PBT")   for b in annual] if v > 0]
                rm_avg_pct  = sum(rm_vals)  / len(rm_vals)  if rm_vals  else None
                pbt_avg_pct = sum(pbt_vals) / len(pbt_vals) if pbt_vals else None

                # Revenue CAGR across annual bars
                rev_entries = [(b["barKey"], b["revenue"]) for b in annual
                               if b.get("revenue") and b["revenue"] > 0]
                cagr_str = None
                if len(rev_entries) >= 2:
                    n_periods = len(rev_entries) - 1
                    cagr_val  = (rev_entries[-1][1] / rev_entries[0][1]) ** (1 / n_periods) - 1
                    cagr_str  = f"{cagr_val * 100:.2f} %"

                # Build single-sentence insight
                insight = f"RM cost for {comp_name} ({rep_type})"
                if rm_avg_pct is not None:
                    insight += f" is {rm_avg_pct:.1f} % of revenue"
                if pbt_avg_pct is not None:
                    insight += (f" and it is operating at {pbt_avg_pct:.1f} % PBT margin"
                                f" in the last {len(annual)} years")
                if cagr_str:
                    insight += f"; top line has grown CAGR @ {cagr_str}."
                else:
                    insight += "."
                insight_parts.append(insight)
            else:
                if annual:
                    best = max(annual, key=lambda b: _seg_of(b, "Operational PBT"))
                    avg_pbt = _seg_of(avg_bar, "Operational PBT") if avg_bar else None
                    s = (f"{best['barKey']} leads peer profitability with "
                         f"{_fmt_pct(_seg_of(best, 'Operational PBT'))} Operational PBT margin")
                    if avg_pbt is not None:
                        s += f" vs. industry average of {_fmt_pct(avg_pbt)}"
                    s += " — indicating superior cost management."
                    insight_parts.append(s)
                    rms = [(b["barKey"], _seg_of(b, "Raw Material Cost")) for b in annual]
                    lo = min(rms, key=lambda t: t[1]); hi = max(rms, key=lambda t: t[1])
                    insight_parts.append(
                        f"RM intensity ranges from {_fmt_pct(lo[1])} ({lo[0]}) "
                        f"to {_fmt_pct(hi[1])} ({hi[0]}) — "
                        f"highlighting procurement differentiation across peers.")
                if avg_bar and avg_bar.get("ebitdaMargin") is not None:
                    insight_parts.append(
                        f"Industry average EBITDA margin stands at "
                        f"{_fmt_pct(avg_bar['ebitdaMargin'])}.")
        except Exception:
            pass

        insight_text = "  ".join(insight_parts) if insight_parts else (
            "Review cost composition trends to identify procurement savings opportunities."
        )

        # ── 0. Compact professional title line (company / FY context) ───────
        ttl_box = slide.shapes.add_textbox(
            Inches(0.50), Inches(TITLE_Y),
            Inches(12.33), Inches(0.34)
        )
        ttl_p = ttl_box.text_frame.paragraphs[0]
        ttl_p.alignment = PP_ALIGN.CENTER
        ttl_r = ttl_p.add_run()
        ttl_r.text = display_title
        ttl_r.font.size  = Pt(17)
        ttl_r.font.bold  = True
        ttl_r.font.color.rgb = DARK

        ins_box = slide.shapes.add_textbox(
            Inches(0.50), Inches(INSIGHT_Y),
            Inches(12.33), Inches(INSIGHT_H)
        )
        ins_tf = ins_box.text_frame
        ins_tf.word_wrap = True
        ins_p  = ins_tf.paragraphs[0]
        ins_r  = ins_p.add_run()
        ins_r.text = insight_text
        ins_r.font.size  = Pt(14)
        ins_r.font.bold  = False
        ins_r.font.italic = True
        ins_r.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)   # deep navy-blue

        # ─────────────────────────────────────────────────────────────────────
        # 2. Subtitle (company / period metadata — no bold header)
        # ─────────────────────────────────────────────────────────────────────
        sub_box = slide.shapes.add_textbox(
            Inches(0.45), Inches(SUBTITLE_Y),
            Inches(12.0), Inches(0.30)
        )
        sub_tf  = sub_box.text_frame
        sub_p   = sub_tf.paragraphs[0]
        sub_r   = sub_p.add_run()
        sub_r.text = subtitle
        sub_r.font.size  = Pt(13)
        sub_r.font.bold  = False
        sub_r.font.color.rgb = DARK

        # ─────────────────────────────────────────────────────────────────────
        # 3. Thin separator line below subtitle
        # ─────────────────────────────────────────────────────────────────────
        sep = slide.shapes.add_connector(
            1,
            Inches(0.50),    Inches(SEP_Y),
            Inches(12.83),   Inches(SEP_Y),
        )
        sep.line.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)
        sep.line.width = Pt(0.5)

        # ─────────────────────────────────────────────────────────────────────
        # 4. "Ops Revenue" left label — ALL slides, Calibri 12pt,
        #    vertically aligned with the revenue number row (REV_LABEL_Y)
        #    and left-edge aligned with the "EBITDA %" label below it.
        # ─────────────────────────────────────────────────────────────────────
        ops_box = slide.shapes.add_textbox(
            Inches(0.50), Inches(REV_LABEL_Y),
            Inches(1.10), Inches(0.30)
        )
        ops_tf = ops_box.text_frame; ops_tf.word_wrap = False
        ops_r  = ops_tf.paragraphs[0].add_run()
        ops_r.text = "Ops Revenue"
        ops_r.font.name  = "Calibri"
        ops_r.font.size  = Pt(12)
        ops_r.font.bold  = False
        ops_r.font.color.rgb = DARK

        # ─────────────────────────────────────────────────────────────────────
        # 5. Revenue labels — INR Cr (÷10 from Mn sent by frontend)
        # ─────────────────────────────────────────────────────────────────────
        for i, b in enumerate(bars):
            rv_mn = b.get("revenue")
            if rv_mn and float(rv_mn) > 0:
                rv_cr  = float(rv_mn) / 10   # convert Mn → Cr
                label  = f"₹{rv_cr:,.0f} Cr"
                tx = slide.shapes.add_textbox(
                    Inches(rev_label_left(i)), Inches(REV_LABEL_Y),
                    Inches(1.273), Inches(0.30)
                )
                tf  = tx.text_frame
                tf.word_wrap = False
                par = tf.paragraphs[0]
                par.alignment = PP_ALIGN.CENTER
                run = par.add_run()
                run.text = label
                run.font.size  = Pt(12)
                run.font.bold  = True
                run.font.color.rgb = DARK

        # ── Pre-compute dynamic Y scale (used for axis + leader-line coords) ──
        _mc, _mp = 100.0, 0.0
        for _r in bar_actual:
            _p = _r.get("Operational PBT", 0.0)
            if _p < 0:
                _mc = max(_mc, sum(v for k, v in _r.items() if k != "Operational PBT" and v > 0))
                _mp = min(_mp, _p)
        Y_MAX   = math.ceil((_mc + 3) / 5) * 5 if _mc > 100.5 else 100
        Y_MIN   = math.floor((_mp - 2) / 5) * 5 if _mp < -0.5  else 0
        Y_RANGE = Y_MAX - Y_MIN

        # ─────────────────────────────────────────────────────────────────────
        # 6. Native COLUMN_STACKED chart
        # ─────────────────────────────────────────────────────────────────────
        cf = slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_STACKED,   # absolute (not 100%): supports below-zero PBT
            Inches(CHART_LEFT), Inches(CHART_TOP_F),
            Inches(CHART_W),    Inches(CHART_H),
            chart_data,
        )
        chart = cf.chart

        # Colour each series; override EVERY data label to the ACTUAL percentage so
        # the floored display heights never change the printed numbers. Negative PBT
        # gets a "-x.x%" label on its below-zero box.
        color_map = {k: c for k, c in STACK}
        for si, seg_name in enumerate(series_segs):
            ser = chart.series[si]
            r, g, b2 = color_map[seg_name]
            ser.format.fill.solid()
            ser.format.fill.fore_color.rgb = RGBColor(r, g, b2)
            is_pale = (r >= 0xF0)
            lbl_rgb = RGBColor(0x78, 0x35, 0x0F) if is_pale else RGBColor(0xFF, 0xFF, 0xFF)
            ser.data_labels.show_value = True
            ser.data_labels.font.size  = Pt(LBL_SIZE)
            ser.data_labels.font.bold  = True
            try:
                ser.data_labels.font.color.rgb = lbl_rgb
            except Exception:
                pass
            for i in range(N):
                actual = bar_actual[i].get(seg_name)
                if actual is None or abs(actual) < 1e-9:
                    continue
                # Small positive segments get an external leader line — blank the
                # native label so it doesn't overlap with the shape we draw later.
                is_small = (actual > 0 and actual < 5.0)
                try:
                    dl = ser.points[i].data_label
                    if is_small:
                        dl.text_frame.text = ""
                    else:
                        dl.text_frame.text = f"{actual:.1f}%"
                        for para in dl.text_frame.paragraphs:
                            for run in para.runs:
                                run.font.size = Pt(LBL_SIZE)
                                run.font.bold = True
                                run.font.color.rgb = lbl_rgb
                except Exception:
                    pass

        chart.has_legend = False

        # Hide category axis labels (we draw our own textboxes below ovals)
        try:
            ca = chart.category_axis
            ca.tick_labels.font.size = Pt(1)
            ca.tick_labels.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        except Exception:
            pass

        # Y axis — use pre-computed scale
        try:
            va = chart.value_axis
            va.maximum_scale = float(Y_MAX)
            va.minimum_scale = float(Y_MIN)
            va.tick_labels.font.size = Pt(11)
        except Exception:
            pass

        # ── REMOVE GRIDLINES from chart XML ──────────────────────────────────
        try:
            chart_part = chart.part
            cNS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
            for gl_tag in ("majorGridlines", "minorGridlines"):
                for gl_el in chart_part._element.findall(f".//{{{cNS}}}{gl_tag}"):
                    gl_el.getparent().remove(gl_el)
        except Exception:
            pass

        # ─────────────────────────────────────────────────────────────────────
        # 6b. Leader-line callouts for small segments (< 5 % of revenue)
        #     Drawn as PowerPoint shapes overlaid on the chart — mirrors the
        #     web SVG diagonal-line leader approach.
        # ─────────────────────────────────────────────────────────────────────
        LEADER_THRESHOLD = 5.0       # % below which we draw a leader
        LEADER_STEP_IN   = 0.30      # inches from bar right-edge to label col
        LEADER_SP_IN     = 0.135     # min vertical gap between label centres
        # Estimated plot-area margins within the chart bounding box
        PTOP  = 0.20    # chart_top  → Y_MAX axis line
        PBOT  = 0.32    # Y_MIN axis line → chart_bottom
        PH    = CHART_H - PTOP - PBOT   # usable plot height in inches
        # PowerPoint default gapWidth ≈ 219 % → bars fill ~31 % of slot
        # half-bar-width ≈ 15.5 % of slot
        BAR_HW = bar_slot * 0.155

        def _ypx(pct):
            """Slide y-coordinate (inches) for a given % on the value axis."""
            return CHART_TOP_F + PTOP + (Y_MAX - pct) / Y_RANGE * PH

        _base_y = _ypx(0)    # y-coordinate of the 0 % line

        try:
            for bi, (b, res) in enumerate(zip(bars, bar_actual)):
                pbt      = res.get("Operational PBT", 0.0)
                x_right  = bar_center(bi) + BAR_HW   # slide x of bar right-edge
                seg_color_map = {k: RGBColor(*c) for k, c in STACK}

                # Accumulate cumulative % bottom→top and collect leaders
                leaders = []
                cum = 0.0
                for seg_name, _ in STACK:
                    v = res.get(seg_name, 0.0)
                    if seg_name == "Operational PBT" or v <= 0:
                        continue
                    if v < LEADER_THRESHOLD:
                        mid_pct = cum + v / 2
                        leaders.append({
                            "midY":   _ypx(mid_pct),
                            "labelY": _ypx(mid_pct),
                            "text":   f"{v:.1f}%",
                            "color":  seg_color_map[seg_name],
                        })
                    cum += v

                # De-overlap: push labels down from top, clamp to stay above 0 % line
                leaders.sort(key=lambda l: l["midY"])
                prev_y = -math.inf
                for l in leaders:
                    l["labelY"] = max(l["midY"], prev_y + LEADER_SP_IN)
                    prev_y = l["labelY"]
                if leaders and leaders[-1]["labelY"] > _base_y - 0.04:
                    shift = leaders[-1]["labelY"] - (_base_y - 0.04)
                    for l in leaders:
                        l["labelY"] -= shift

                # Draw each cost leader
                for l in leaders:
                    xs, ys = x_right + 0.01, l["midY"]
                    xe, ye = x_right + LEADER_STEP_IN, l["labelY"]
                    # Anchor dot
                    dot = slide.shapes.add_shape(
                        9, Inches(xs - 0.025), Inches(ys - 0.025),
                        Inches(0.05), Inches(0.05))
                    dot.fill.solid(); dot.fill.fore_color.rgb = l["color"]
                    dot.line.color.rgb = l["color"]; dot.line.width = Pt(0)
                    # Diagonal connector
                    conn = slide.shapes.add_connector(
                        1, Inches(xs), Inches(ys),
                        Inches(xe - 0.02), Inches(ye))
                    conn.line.color.rgb = l["color"]
                    conn.line.width = Pt(0.75)
                    # Label
                    tb = slide.shapes.add_textbox(
                        Inches(xe), Inches(ye - 0.09),
                        Inches(0.36), Inches(0.18))
                    rn = tb.text_frame.paragraphs[0].add_run()
                    rn.text = l["text"]
                    rn.font.size = Pt(9); rn.font.bold = True
                    rn.font.color.rgb = DARK

                # Negative PBT leader (if the loss box is too thin for inside label)
                if pbt < -0.01:
                    pbt_top_y = _base_y
                    pbt_bot_y = _ypx(pbt)
                    pbt_h_in  = pbt_bot_y - pbt_top_y
                    pbt_mid_y = (pbt_top_y + pbt_bot_y) / 2
                    if pbt_h_in < 0.16:
                        xe = x_right + LEADER_STEP_IN
                        conn2 = slide.shapes.add_connector(
                            1, Inches(x_right), Inches(pbt_mid_y),
                            Inches(xe - 0.02), Inches(pbt_mid_y))
                        conn2.line.color.rgb = RGBColor(0xB4, 0x53, 0x09)
                        conn2.line.width = Pt(0.75)
                        tb2 = slide.shapes.add_textbox(
                            Inches(xe), Inches(pbt_mid_y - 0.09),
                            Inches(0.38), Inches(0.18))
                        rn2 = tb2.text_frame.paragraphs[0].add_run()
                        rn2.text = f"{pbt:.1f}%"
                        rn2.font.size = Pt(9); rn2.font.bold = True
                        rn2.font.color.rgb = RGBColor(0x92, 0x40, 0x0E)
        except Exception:
            pass   # leader lines are best-effort; don't fail the whole PPT

        # ─────────────────────────────────────────────────────────────────────
        # 7. "EBITDA %" left label
        # ─────────────────────────────────────────────────────────────────────
        ebl = slide.shapes.add_textbox(
            Inches(0.50), Inches(OVAL_Y),
            Inches(1.10), Inches(0.30)
        )
        ebl_r = ebl.text_frame.paragraphs[0].add_run()
        ebl_r.text = "EBITDA %"
        ebl_r.font.size  = Pt(12)
        ebl_r.font.bold  = True
        ebl_r.font.color.rgb = GREEN

        # ─────────────────────────────────────────────────────────────────────
        # 8. EBITDA ovals + bar-key labels below
        # ─────────────────────────────────────────────────────────────────────
        for i, b in enumerate(bars):
            em     = b.get("ebitdaMargin")
            is_avg = bool(b.get("isAverage", False))
            barkey = b.get("barKey", "")

            if em is not None:
                oval = slide.shapes.add_shape(
                    9,   # OVAL
                    Inches(oval_left(i)), Inches(OVAL_Y),
                    Inches(OVAL_W), Inches(OVAL_H),
                )
                if is_avg:
                    oval.fill.solid()
                    oval.fill.fore_color.rgb = RGBColor(0xFF, 0xF7, 0xED)
                    oval.line.color.rgb      = RGBColor(0xF9, 0x73, 0x16)
                    txt_color = ORANGE
                else:
                    oval.fill.solid()
                    oval.fill.fore_color.rgb = RGBColor(0xF0, 0xFD, 0xF4)
                    oval.line.color.rgb      = RGBColor(0x05, 0x96, 0x69)
                    txt_color = GREEN

                oval.line.width = Pt(1.5)
                tf = oval.text_frame; tf.word_wrap = False
                par = tf.paragraphs[0]; par.alignment = PP_ALIGN.CENTER
                run = par.add_run()
                run.text = f"{float(em):.1f}"
                run.font.size = Pt(13); run.font.bold = True
                run.font.color.rgb = txt_color

            # Bar-key label below oval
            yr_box = slide.shapes.add_textbox(
                Inches(oval_left(i) - 0.15), Inches(YR_LABEL_Y),
                Inches(OVAL_W + 0.30), Inches(0.28),
            )
            yr_tf = yr_box.text_frame; yr_tf.word_wrap = False
            yr_par = yr_tf.paragraphs[0]; yr_par.alignment = PP_ALIGN.CENTER
            yr_run = yr_par.add_run()
            yr_run.text = barkey
            yr_run.font.size = Pt(12)
            yr_run.font.bold = True
            yr_run.font.color.rgb = ORANGE if is_avg else DARK

        # ─────────────────────────────────────────────────────────────────────
        # 9. Legend — 2 rows, 11 pt, color swatches + labels (top-of-stack → bottom)
        # Row 1: first 4 items;  Row 2: remaining items
        # ─────────────────────────────────────────────────────────────────────
        LEGEND_ORDER = list(reversed(STACK))   # STACK is bottom-to-top; reverse for display

        active_segs = set()
        for res in bar_actual:
            active_segs.update(k for k, v in res.items() if abs(v) > 0)
        leg_items = [(name, rgb) for name, rgb in LEGEND_ORDER if name in active_segs]

        if leg_items:
            total_w  = 12.33
            SWATCH_W = 0.20
            SWATCH_H = 0.20
            GAP      = 0.07
            ROW_H    = 0.28   # height of each legend row

            ROW1_N = min(4, len(leg_items))
            ROW2_N = len(leg_items) - ROW1_N

            for idx, (seg_name, rgb) in enumerate(leg_items):
                if idx < ROW1_N:
                    row_y   = LEGEND_Y
                    n_in_row = ROW1_N
                    row_idx  = idx
                else:
                    row_y   = LEGEND_Y2
                    n_in_row = ROW2_N
                    row_idx  = idx - ROW1_N

                item_w = total_w / n_in_row
                item_x = 0.50 + row_idx * item_w

                swatch = slide.shapes.add_shape(
                    1,
                    Inches(item_x),
                    Inches(row_y + (ROW_H - SWATCH_H) / 2),
                    Inches(SWATCH_W),
                    Inches(SWATCH_H),
                )
                swatch.fill.solid()
                swatch.fill.fore_color.rgb = RGBColor(*rgb)
                swatch.line.color.rgb      = RGBColor(*rgb)
                swatch.line.width          = Pt(0)

                lbl_box = slide.shapes.add_textbox(
                    Inches(item_x + SWATCH_W + GAP),
                    Inches(row_y),
                    Inches(item_w - SWATCH_W - GAP - 0.04),
                    Inches(ROW_H),
                )
                lbl_tf = lbl_box.text_frame
                lbl_tf.word_wrap = False
                lbl_p  = lbl_tf.paragraphs[0]
                lbl_r  = lbl_p.add_run()
                lbl_r.text           = seg_name
                lbl_r.font.size      = Pt(11)
                lbl_r.font.bold      = False
                lbl_r.font.color.rgb = DARK

        # ─────────────────────────────────────────────────────────────────────
        # 10. Footer — data source
        # ─────────────────────────────────────────────────────────────────────
        footer_box = slide.shapes.add_textbox(
            Inches(0.50), Inches(FOOTER_Y),
            Inches(12.33), Inches(0.22)
        )
        ft_tf = footer_box.text_frame
        ft_p  = ft_tf.paragraphs[0]
        ft_r  = ft_p.add_run()
        ft_r.text = "Data Source: Refinitiv Eikon  |  Procurement Analytics Team, Sun Pharma"
        ft_r.font.size  = Pt(10)
        ft_r.font.italic = True
        ft_r.font.color.rgb = SLATE

        # ─────────────────────────────────────────────────────────────────────
        # 10. Save and return
        # ─────────────────────────────────────────────────────────────────────
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pptx") as tmp:
            prs.save(tmp.name)
            tmp_path = tmp.name

        slug = (title.replace(" ", "_")
                     .replace("—", "")
                     .replace("  ", "_")
                     .strip("_"))[:45]
        return FileResponse(
            tmp_path,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=f"{slug}.pptx",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"PPT generation failed: {e}\n{tb.format_exc()}")
