"""PPT export — fixed IndexError + robust null handling."""
import io
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.chart.data import ChartData

def rgb(h):
    h = h.lstrip('#')
    return RGBColor(int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))

NAVY="0B2545"; TEAL="0D9488"; WHITE="FFFFFF"

class PPTService:
    def __init__(self, svc): self.svc = svc

    def generate(self, company_id: str) -> bytes:
        data = self.svc.get_dashboard_data(company_id)
        if not data:
            data = {}
        prs = Presentation()
        prs.slide_width  = Inches(13.33)
        prs.slide_height = Inches(7.5)
        blank = prs.slide_layouts[6]
        self._title_slide(prs, blank, company_id, data)
        self._kpi_slide(prs, blank, data)
        self._revenue_slide(prs, blank, data)
        self._cost_slide(prs, blank, data)
        self._altman_slide(prs, blank, data)
        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue()

    def _txt(self, slide, text, x, y, w, h, size=12, bold=False, color=WHITE, align="left"):
        """Add text box — robust against empty text."""
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        p  = tf.paragraphs[0]
        p.alignment = {"left":1,"center":2,"right":3}.get(align, 1)
        run = p.add_run()        # always add_run, never index runs[0]
        run.text = str(text) if text is not None else ""
        run.font.size  = Pt(size)
        run.font.bold  = bold
        run.font.color.rgb = rgb(color)
        return tb

    def _rect(self, slide, x, y, w, h, fill):
        s = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
        s.line.fill.background()
        return s

    def _fmt(self, v, decimals=0):
        if v is None: return "—"
        try:
            return f"{float(v):,.{decimals}f}"
        except Exception:
            return str(v)

    # ── Slides ────────────────────────────────────────────────────────

    def _title_slide(self, prs, layout, company_id, data):
        s = prs.slides.add_slide(layout)
        self._rect(s, 0, 0, 13.33, 7.5, NAVY)
        self._rect(s, 0, 0, 0.08, 7.5, TEAL)
        self._txt(s, "FINANCIAL ANALYTICS SUMMARY", 0.5, 0.7, 9, 0.4, size=10, color=TEAL)
        self._txt(s, company_id, 0.5, 1.3, 9, 1.4, size=44, bold=True)
        years = data.get("years", [])
        period = f"{years[-1]} — {years[0]}" if len(years) >= 2 else (years[0] if years else "")
        self._txt(s, period, 0.5, 3.0, 9, 0.5, size=14, color=TEAL)
        rev = (data.get("kpis") or {}).get("revenue", {}).get("value")
        if rev:
            self._txt(s, f"Revenue: {self._fmt(rev)} INR Mn", 0.5, 3.7, 9, 0.4, size=13, color="AABBCC")

    def _kpi_slide(self, prs, layout, data):
        s = prs.slides.add_slide(layout)
        s.background.fill.solid(); s.background.fill.fore_color.rgb = rgb("F8FAFC")
        self._rect(s, 0, 0, 13.33, 1.1, NAVY)
        self._txt(s, "Key Financial Metrics", 0.3, 0.18, 12, 0.7, size=22, bold=True)
        kpis = data.get("kpis") or {}
        cards = [
            ("Revenue",       (kpis.get("revenue") or {}).get("value"),  "INR Mn",  TEAL),
            ("EBITDA",        (kpis.get("ebitda")  or {}).get("value"),  "INR Mn",  "2563EB"),
            ("PAT",           (kpis.get("pat")     or {}).get("value"),  "INR Mn",  "059669"),
            ("EBITDA Margin", (kpis.get("ebitda")  or {}).get("margin"), "%",       "7C3AED"),
            ("Altman Z",      (kpis.get("altman_z") or {}).get("value"), "",        "D97706"),
            ("Current Ratio", (kpis.get("current_ratio") or {}).get("value"), "",  "0891B2"),
        ]
        for i, (label, val, unit, color) in enumerate(cards):
            col, row = i % 3, i // 3
            x, y = 0.3 + col * 4.3, 1.4 + row * 2.7
            self._rect(s, x, y, 4.0, 2.3, color)
            self._txt(s, label, x+0.15, y+0.15, 3.7, 0.4, size=11, color="DDDDDD")
            disp = self._fmt(val, 2 if unit=="" else 0)
            self._txt(s, disp, x+0.15, y+0.6, 3.7, 0.9, size=26, bold=True)
            if unit: self._txt(s, unit, x+0.15, y+1.6, 3.7, 0.4, size=10, color="AAAAAA")

    def _revenue_slide(self, prs, layout, data):
        s = prs.slides.add_slide(layout)
        s.background.fill.solid(); s.background.fill.fore_color.rgb = rgb("F8FAFC")
        self._rect(s, 0, 0, 13.33, 1.1, NAVY)
        self._txt(s, "Revenue & EBITDA Trend", 0.3, 0.18, 12, 0.7, size=22, bold=True)
        trend   = data.get("trend") or {}
        rev_raw = sorted(trend.get("Revenue from Operations", []), key=lambda x: x["year"])
        ebd_raw = sorted(trend.get("EBITDA", []), key=lambda x: x["year"])
        if not rev_raw:
            self._txt(s, "No trend data available", 4, 3, 6, 0.5, size=14, color="888888", align="center")
            return
        cd = ChartData()
        cd.categories = [r["year"] for r in rev_raw]
        cd.add_series("Revenue", [r["value"] or 0 for r in rev_raw])
        if ebd_raw:
            cd.add_series("EBITDA", [r["value"] or 0 for r in ebd_raw])
        c = s.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            Inches(0.5), Inches(1.3), Inches(12.3), Inches(5.8), cd
        ).chart
        c.has_title = False
        c.has_legend = True

    def _cost_slide(self, prs, layout, data):
        s = prs.slides.add_slide(layout)
        s.background.fill.solid(); s.background.fill.fore_color.rgb = rgb("F8FAFC")
        self._rect(s, 0, 0, 13.33, 1.1, NAVY)
        self._txt(s, "Cost Structure", 0.3, 0.18, 12, 0.7, size=22, bold=True)
        cost = [c for c in (data.get("cost_structure") or []) if c.get("value")]
        if not cost:
            self._txt(s, "No cost data available", 4, 3, 6, 0.5, size=14, color="888888", align="center")
            return
        cd = ChartData()
        cd.categories = [c["item"].split(" ")[0] for c in cost[:7]]
        cd.add_series("INR Mn", [c["value"] or 0 for c in cost[:7]])
        c = s.shapes.add_chart(
            XL_CHART_TYPE.PIE,
            Inches(0.5), Inches(1.3), Inches(12.3), Inches(5.8), cd
        ).chart
        c.has_title  = False
        c.has_legend = True

    def _altman_slide(self, prs, layout, data):
        s = prs.slides.add_slide(layout)
        s.background.fill.solid(); s.background.fill.fore_color.rgb = rgb("F8FAFC")
        self._rect(s, 0, 0, 13.33, 1.1, NAVY)
        self._txt(s, "Altman Z Score — Bankruptcy Risk", 0.3, 0.18, 12, 0.7, size=22, bold=True)
        z_info = (data.get("kpis") or {}).get("altman_z") or {}
        z     = z_info.get("value")
        zone  = z_info.get("zone", "unknown")
        color = "059669" if zone=="safe" else ("D97706" if zone=="grey" else "DC2626")
        if z:
            self._rect(s, 4, 1.5, 5.33, 2.8, color)
            self._txt(s, f"Z = {z:.2f}", 4, 2.0, 5.33, 1.1, size=48, bold=True, align="center")
            self._txt(s, f"{zone.upper()} ZONE", 4, 3.2, 5.33, 0.7, size=18, bold=True, align="center")
        zones = [("Safe Zone Z>2.99","059669"),("Grey Zone 1.81-2.99","D97706"),("Distress Z<1.81","DC2626")]
        for i,(lbl,c) in enumerate(zones):
            self._rect(s, 0.3+i*4.3, 5.2, 4.0, 0.5, c)
            self._txt(s, lbl, 0.3+i*4.3, 5.2, 4.0, 0.5, size=11, bold=True, align="center")
