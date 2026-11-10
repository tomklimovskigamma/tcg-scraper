"""Weekly market chart: US market price of sealed product by set, as a PNG.

Needs matplotlib, which the system Python lacks: run this with the Homebrew
Python (see hermes/pokemon-market-chart.sh). The rest of the pipeline does not
import this module.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .history import History
from .classify import normalize

# Dark theme (Discord is dark by default). Palette validated for dark mode with
# the dataviz validator: lightness band, chroma, CVD separation, contrast.
SURFACE = "#1a1a19"
INK = "#f0efec"
INK_2 = "#c3c2b7"
MUTED = "#898781"
GRID = "#2c2c2a"
AXIS = "#383835"
SERIES = ["#3987e5", "#d95926", "#199e70"]  # fixed order: newest set first

PANELS = [("booster_box", "Booster Box"), ("etb", "Elite Trainer Box"),
          ("booster_bundle", "Booster Bundle"), ("booster", "Booster Pack")]
DAYS = 90
MAX_SETS = 3


def _t(text: str) -> str:
    """Escape dollar signs: matplotlib reads a pair of them as maths."""
    return text.replace("$", r"\$")


def pick_sets(history: History, since: str) -> list:
    """The newest sets that have price data, newest first, at most MAX_SETS."""
    seen = {}
    for ptype, _ in PANELS:
        for r in history.market_series(ptype, since):
            seen[r["set_name"]] = r["published_on"] or ""
    return [name for name, _ in sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:MAX_SETS]]


def _shelf(history: History, ptype: str, sets: list) -> Optional[float]:
    """Median Australian shelf price seen for this product type: charted sets first, else any set."""
    keys = {normalize(s) for s in sets}
    rows = history.shelf_prices(ptype)
    prices = sorted(r["price"] for r in rows if normalize(r["set_name"]) in keys) or sorted(r["price"] for r in rows)
    return prices[len(prices) // 2] if prices else None


def render(history: History, out: Path, today: date) -> Optional[Path]:
    """Draw the chart. Returns the file path, or None when there is nothing to plot."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    since = (today - timedelta(days=DAYS)).isoformat()
    fx = history.latest_fx()
    sets = pick_sets(history, since)
    if not sets:
        return None
    colour = {name: SERIES[i] for i, name in enumerate(sets)}
    unit = "A$" if fx else "US$"
    rate = fx or 1.0

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 7.6), dpi=160, facecolor=SURFACE)
    fig.subplots_adjust(left=0.06, right=0.82, top=0.80, bottom=0.11, hspace=0.42, wspace=0.85)

    for ax, (ptype, label) in zip(axes.flat, PANELS):
        ax.set_facecolor(SURFACE)
        rows = [r for r in history.market_series(ptype, since) if r["set_name"] in colour]
        ends = []
        for name in sets:
            pts = [(datetime.fromisoformat(r["date"]), r["usd"] * rate) for r in rows if r["set_name"] == name]
            if not pts:
                continue
            xs, ys = zip(*pts)
            ax.plot(xs, ys, color=colour[name], linewidth=2, solid_capstyle="round", solid_joinstyle="round")
            ax.plot(xs[-1], ys[-1], "o", color=colour[name], markersize=8, markeredgecolor=SURFACE,
                    markeredgewidth=2, clip_on=False, zorder=5)
            ends.append((ys[-1], name))
        shelf = _shelf(history, ptype, sets)
        ax.set_title(label, loc="left", color=INK, fontsize=11.5, fontweight="bold", pad=10)
        ax.grid(axis="y", color=GRID, linewidth=1)
        ax.grid(axis="x", visible=False)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=MUTED, length=0, labelsize=9)
        ax.set_xlim(datetime.fromisoformat(since), datetime.combine(today, datetime.min.time()))
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d %b"))
        decimals = 2 if ends and max(v for v, _ in ends) < 20 else 0
        ax.yaxis.set_major_formatter(lambda v, _p, d=decimals: _t(f"{unit}{v:,.{d}f}"))
        if not ends:
            ax.text(0.5, 0.5, "No price data yet", transform=ax.transAxes, ha="center", va="center", color=MUTED)
            continue
        values = [v for v, _ in ends] + [r["usd"] * rate for r in rows] + ([shelf] if shelf else [])
        lo, hi = min(values), max(values)
        pad = (hi - lo) * 0.15 or hi * 0.1
        ax.set_ylim(lo - pad, hi + pad)
        if shelf:
            # Reference line, not a series: muted ink, labelled in place.
            ax.axhline(shelf, color=MUTED, linewidth=1)
            ax.text(0.01, shelf, _t(f" AU shelf {unit}{shelf:,.2f}"), transform=ax.get_yaxis_transform(),
                    color=INK_2, fontsize=8.5, va="bottom", ha="left")
        # Direct end labels in text ink, nudged apart so they never overlap.
        gap = (hi - lo + 2 * pad) * 0.085
        placed = []
        for value, name in sorted(ends):
            y = value if not placed else max(value, placed[-1] + gap)
            placed.append(y)
            ax.annotate(_t(f"{unit}{value:,.{decimals}f}  {name}"), xy=(1.0, y), xycoords=("axes fraction", "data"),
                        xytext=(9, 0), textcoords="offset points", color=INK, fontsize=9, va="center",
                        annotation_clip=False)

    fig.text(0.06, 0.945, "Pokémon TCG sealed prices: US market, last 90 days", color=INK, fontsize=15,
             fontweight="bold", ha="left")
    note = (f"TCGplayer market price converted to Australian dollars at today's rate (US$1 = A${fx:.2f}). "
            "A guide only, not Australian resale value." if fx else
            "TCGplayer market price in US dollars. A guide only, not Australian resale value.")
    fig.text(0.06, 0.905, _t(note), color=INK_2, fontsize=9.5, ha="left")
    handles = [Line2D([0], [0], color=colour[n], linewidth=2, marker="o", markersize=7, label=n) for n in sets]
    legend = fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.052, 0.89), ncol=len(sets),
                        frameon=False, fontsize=10, handlelength=1.6, columnspacing=1.8)
    for text in legend.get_texts():
        text.set_color(INK)
    fig.text(0.06, 0.03, f"Source: TCGplayer via tcgcsv.com · {today.strftime('%-d %b %Y')}", color=MUTED,
             fontsize=8.5, ha="left")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


def caption(history: History, today: date) -> str:
    """One-line text to accompany the chart: the week's biggest mover among the charted sets."""
    since = (today - timedelta(days=8)).isoformat()
    sets = set(pick_sets(history, (today - timedelta(days=DAYS)).isoformat()))
    moves = []
    for ptype, label in PANELS:
        by_set = {}
        for r in history.market_series(ptype, since):
            if r["set_name"] in sets:
                by_set.setdefault(r["set_name"], []).append(r["usd"])
        for name, vals in by_set.items():
            if len(vals) >= 2 and vals[0] > 0:
                moves.append(((vals[-1] - vals[0]) / vals[0], f"{name} {label}"))
    head = "📈 **Weekly market check** · US market prices for sealed product"
    if not moves:
        return head
    change, what = max(moves, key=lambda m: abs(m[0]))
    if abs(change) < 0.02:
        return head + "\nPrices were flat this week."
    return head + f"\nBiggest move this week: {what}, {'up' if change > 0 else 'down'} {abs(change):.0%}."
