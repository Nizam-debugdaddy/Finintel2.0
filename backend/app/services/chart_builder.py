"""
chart_builder.py — Generate chart images using matplotlib (no Chrome/kaleido required).
Used by the PPT export pipeline.
"""
from __future__ import annotations
import io, math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import FuncFormatter

# FinIntel brand colors
COST_COLORS = [
    "#1A56DB","#0D9488","#7C3AED","#D97706",
    "#DC2626","#059669","#0891B2","#EA580C","#8B5CF6","#64748B",
]
COMPANY_COLORS = [
    "#1A56DB","#0D9488","#7C3AED","#D97706",
    "#DC2626","#059669","#0891B2","#EA580C",
]
NAVY   = "#0B2545"
TEAL   = "#0D9488"
LIGHT  = "#F8FAFC"

COST_SEGMENTS = [
    "Raw Material Cost","Consumables","Power & Fuel","Transportation",
    "Manpower","Rest in Other Expenses","Finance Costs",
    "Depreciation & Amortization","Remaining Expenses","Operational PBT",
]


def _fmt_mn(x, _):
    if x >= 1_000_000: return f"{x/1_000_000:.1f}M"
    if x >= 1_000:     return f"{x/1_000:.0f}K"
    return f"{x:.0f}"


def make_cost_structure_chart(
    cost_data: dict,
    companies: list[str],
    period: str,
    unit: str = "absolute",   # absolute | pct_revenue | pct_total_cost
    width_in: float = 9.0,
    height_in: float = 4.8,
    dpi: int = 150,
) -> bytes:
    """Return PNG bytes of a stacked bar chart matching the CIPLA template style."""
    cos = [c for c in companies if cost_data.get(c)]
    if not cos:
        return _empty_chart(width_in, height_in, dpi, "No cost data")

    # Sort segments by average absolute value (largest at bottom)
    def avg_raw(seg):
        return sum(cost_data[c].get(seg, 0) or 0 for c in cos) / max(len(cos), 1)
    sorted_segs = sorted(COST_SEGMENTS, key=avg_raw)  # ascending → bottom first in stackplot

    def display_val(co, seg):
        d   = cost_data[co]
        raw = d.get(seg) or 0
        if unit == "pct_revenue":
            rv = d.get("_revenue") or 1
            return raw / rv * 100
        if unit == "pct_total_cost":
            tc = d.get("_total_cost") or d.get("_revenue") or 1
            return raw / tc * 100
        return raw

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    x      = np.arange(len(cos))
    bottom = np.zeros(len(cos))
    bars   = []
    labels = []
    for seg in sorted_segs:
        vals = np.array([display_val(co, seg) for co in cos], dtype=float)
        color = COST_COLORS[COST_SEGMENTS.index(seg) % len(COST_COLORS)]
        b = ax.bar(x, vals, bottom=bottom, color=color, width=0.55, label=seg)
        bottom += vals
        bars.append(b)
        labels.append(seg)

    ax.set_xticks(x)
    ax.set_xticklabels(cos, fontsize=11, fontweight="bold", color=NAVY)
    ax.tick_params(axis="x", which="both", bottom=False, top=False)
    ax.tick_params(axis="y", labelsize=9, color="#94A3B8")
    ax.set_title(f"Cost Structure — {period}", fontsize=13, fontweight="bold",
                 color=NAVY, pad=10)
    y_label = "INR Mn" if unit == "absolute" else ("% of Revenue" if unit == "pct_revenue" else "% of Total Cost")
    ax.set_ylabel(y_label, fontsize=9, color="#64748B")
    if unit == "absolute":
        ax.yaxis.set_major_formatter(FuncFormatter(_fmt_mn))

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#E2E8F0")
    ax.spines["bottom"].set_color("#E2E8F0")
    ax.yaxis.grid(True, color="#F1F5F9", linewidth=0.7)
    ax.set_axisbelow(True)

    # Totals on top of each bar
    for ci, co in enumerate(cos):
        total = sum(display_val(co, seg) for seg in sorted_segs)
        lbl   = f"{total/1000:.0f}K" if (unit == "absolute" and total >= 1000) else f"{total:.1f}{'%' if unit != 'absolute' else ''}"
        ax.text(ci, total + total * 0.01, lbl, ha="center", va="bottom",
                fontsize=8, color=NAVY, fontweight="bold")

    # Compact legend outside right
    ax.legend(handles=[mpatches.Patch(color=COST_COLORS[COST_SEGMENTS.index(s) % len(COST_COLORS)], label=s)
                       for s in reversed(sorted_segs)],
              loc="center left", bbox_to_anchor=(1.01, 0.5),
              fontsize=7, frameon=False)

    fig.tight_layout(rect=[0, 0, 0.78, 1])
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def make_multi_metric_chart(
    metric_table: dict,
    companies: list[str],
    metrics: list[str],
    period: str,
    width_in: float = 9.0,
    height_in: float = 4.5,
    dpi: int = 150,
) -> bytes:
    """Return PNG bytes of a grouped bar chart for multi-metric KPI comparison."""
    if not metrics or not companies:
        return _empty_chart(width_in, height_in, dpi, "No metric data")

    # Short display labels for x-axis
    short_labels = [m.replace(" from Operations","").replace(" Margin","M").replace(" %","") for m in metrics]

    n_metrics = len(metrics)
    n_cos     = len(companies)
    x         = np.arange(n_metrics)
    bar_w     = min(0.7 / max(n_cos, 1), 0.25)
    offsets   = np.linspace(-(n_cos-1)/2, (n_cos-1)/2, n_cos) * bar_w * 1.1

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    for ci, co in enumerate(companies):
        vals = [metric_table.get(m, {}).get(co) for m in metrics]
        vals = [float(v) if v is not None else 0.0 for v in vals]
        color = COMPANY_COLORS[ci % len(COMPANY_COLORS)]
        ax.bar(x + offsets[ci], vals, width=bar_w, color=color, label=co, alpha=0.88)

    ax.set_xticks(x)
    ax.set_xticklabels(short_labels, fontsize=10, fontweight="bold", color=NAVY, rotation=0)
    ax.tick_params(axis="x", which="both", bottom=False, top=False)
    ax.tick_params(axis="y", labelsize=9, color="#94A3B8")
    ax.set_title(f"KPI Comparison — {period}", fontsize=13, fontweight="bold", color=NAVY, pad=10)
    ax.set_ylabel("Value", fontsize=9, color="#64748B")
    ax.yaxis.set_major_formatter(FuncFormatter(_fmt_mn))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#E2E8F0")
    ax.spines["bottom"].set_color("#E2E8F0")
    ax.yaxis.grid(True, color="#F1F5F9", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=8, frameon=False)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def make_trend_chart(
    series: list[dict],
    years: list[str],
    metric_label: str,
    period: str,
    width_in: float = 9.0,
    height_in: float = 4.5,
    dpi: int = 150,
) -> bytes:
    """Return PNG bytes of a line chart for metric trend comparison."""
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    for ci, s in enumerate(series):
        vals  = [float(v) if v is not None else None for v in s["values"]]
        color = COMPANY_COLORS[ci % len(COMPANY_COLORS)]
        xs    = list(range(len(years)))
        # Drop None for line but mark gaps
        mask  = [v is not None for v in vals]
        xi    = [x for x, m in zip(xs, mask) if m]
        yi    = [v for v, m in zip(vals, mask) if m]
        ax.plot(xi, yi, color=color, marker="o", linewidth=2.5,
                markersize=7, label=s["company_id"])

    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years, fontsize=10, fontweight="bold", color=NAVY, rotation=0)
    ax.tick_params(axis="x", which="both", bottom=False, top=False)
    ax.tick_params(axis="y", labelsize=9)
    ax.set_title(f"{metric_label} Trend", fontsize=13, fontweight="bold", color=NAVY, pad=10)
    ax.set_ylabel(metric_label, fontsize=9, color="#64748B")
    ax.yaxis.set_major_formatter(FuncFormatter(_fmt_mn))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#E2E8F0")
    ax.spines["bottom"].set_color("#E2E8F0")
    ax.yaxis.grid(True, color="#F1F5F9", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", fontsize=9, frameon=False)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _empty_chart(w, h, dpi, msg):
    fig, ax = plt.subplots(figsize=(w, h), dpi=dpi)
    ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=14, color="#94A3B8",
            transform=ax.transAxes)
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
