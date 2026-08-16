"""
AMEX_THEME — Platinum 365 dashboard design system
================================================================================
Single source of truth for colour, typography, chart styling and table styling.
Palette extracted from the official Amex PS deck (same values as the Canva deck).

Import this in app.py:  from amex_theme import *
================================================================================
"""

import plotly.graph_objects as go
import plotly.io as pio
import pandas as pd
import numpy as np

# ── PALETTE (locked) ─────────────────────────────────────────────────────────
NAVY      = "#0D2240"   # header band, dark callouts, table headers on dark
BLUE      = "#006FCF"   # brand blue — THE blue (never #0070C0)
BLUE_MID  = "#00539B"   # secondary fills, flow arrows
INDIGO    = "#162B73"   # sub-headers, emphasis text
CYAN      = "#00A3E0"   # data-viz second series
TINT      = "#DEEBF7"   # alternating table rows
TINT_2    = "#E8F1FB"   # lighter alternating / gridlines
GOLD      = "#C4A962"   # money accent — NPV / net value only
RED       = "#DC2626"   # the one number they should stare at
TEAL      = "#00B89F"   # positive / recovery
GREY      = "#6B7280"   # secondary text
GREY_DK   = "#374151"   # body text
PANEL     = "#F5F7FA"   # card background
PANEL_2   = "#FAFBFC"   # plot background
WHITE     = "#FFFFFF"

FONT = "Inter, Helvetica Neue, Helvetica, Arial, sans-serif"

# Cause -> colour. Mapped BY NAME so ordering changes never repaint the chart.
CAUSE_COLOURS = {
    "irrelevance": RED,       # the one you stare at — not nudgeable, needs L3 swap
    "awareness":   BLUE,
    "timing":      CYAN,
    "friction":    BLUE_MID,
    "structural":  GREY,
}

# Brand-consistent sequential scale for heatmaps (replaces RdYlGn)
AMEX_SCALE = [
    [0.00, WHITE],
    [0.25, TINT],
    [0.50, CYAN],
    [0.75, BLUE],
    [1.00, NAVY],
]

# ── PLOTLY TEMPLATE ──────────────────────────────────────────────────────────
_amex_template = go.layout.Template()
_amex_template.layout = go.Layout(
    font=dict(family=FONT, size=13, color=GREY_DK),
    title=dict(font=dict(family=FONT, size=17, color=NAVY), x=0, xanchor="left"),
    paper_bgcolor=WHITE,
    plot_bgcolor=PANEL_2,
    colorway=[BLUE, CYAN, BLUE_MID, GOLD, TEAL, INDIGO],
    xaxis=dict(gridcolor=TINT_2, linecolor=TINT, zerolinecolor=TINT,
               tickfont=dict(color=GREY_DK, size=12),
               title=dict(font=dict(color=NAVY, size=13))),
    yaxis=dict(gridcolor=TINT_2, linecolor=TINT, zerolinecolor=TINT,
               tickfont=dict(color=GREY_DK, size=12),
               title=dict(font=dict(color=NAVY, size=13))),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                font=dict(color=GREY_DK, size=12)),
    hoverlabel=dict(bgcolor=NAVY, font=dict(color=WHITE, family=FONT, size=12),
                    bordercolor=NAVY),
    margin=dict(l=60, r=30, t=60, b=50),
)
pio.templates["amex"] = _amex_template


def amex_layout(fig, title=None, height=450, **kw):
    """Apply the house template to any figure in one call."""
    fig.update_layout(template="amex", height=height, **kw)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(color=NAVY, size=17),
                                     x=0, xanchor="left"))
    return fig


# ── STREAMLIT CSS ────────────────────────────────────────────────────────────
# NOTE: Streamlit's *default* theme is dark with a red accent. If a page never
# overrides the base app shell (only individual custom divs), every native
# widget — st.metric, st.radio, st.header, st.dataframe, captions — stays on
# the dark theme and renders pale/invisible text on the light custom panels.
# That is what produced the "empty" black sidebar. Fixing this needs BOTH:
#   1) a `.streamlit/config.toml` with a light base theme (provided alongside
#      this file) so native widgets default to the right colours, and
#   2) this CSS, which explicitly restyles every native widget as a
#      belt-and-braces fix in case config.toml isn't picked up (e.g. some
#      hosting set-ups cache the old theme).
CSS = f"""
<style>
  html, body, [class*="css"] {{ font-family: {FONT}; }}

  /* ── force the light Amex shell everywhere, regardless of theme cache ── */
  .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"],
  [data-testid="stHeader"], [data-testid="stToolbar"] {{
      background: {WHITE} !important;
  }}
  .stApp, .stApp p, .stApp li, .stApp span, .stApp label {{ color: {GREY_DK}; }}
  /* NOTE: intentionally NOT forcing h1–h5 to navy globally — that overrode the
     white heading inside .amex-band (navy background) with !important,
     making the band title invisible (navy-on-navy). This app never uses
     native st.header/st.title, so no blanket rule is needed; .amex-band h1,
     .amex-callout etc. already set their own heading colours below. */

  .block-container {{ padding-top: 1.2rem; max-width: 1400px; }}

  /* ── native st.metric (kept for any leftover usage) ── */
  [data-testid="stMetric"] {{
      background: {WHITE}; border: 1px solid {TINT}; border-left: 4px solid {BLUE};
      border-radius: 6px; padding: 10px 14px 8px 14px;
  }}
  [data-testid="stMetricLabel"] p {{ color: {GREY} !important; font-size: 11px;
      font-weight: 600; text-transform: uppercase; letter-spacing: 0.6px; }}
  [data-testid="stMetricValue"] {{ color: {NAVY} !important; font-weight: 700; }}
  [data-testid="stMetricDelta"] {{ color: {TEAL} !important; }}

  /* ── captions / small text ── */
  [data-testid="stCaptionContainer"], .stCaption, small {{ color: {GREY} !important; }}

  /* ── dividers ── */
  hr {{ border-color: {TINT} !important; }}

  /* ── page-nav radio, restyled as a pill list ── */
  div[data-testid="stRadio"] > div[role="radiogroup"] {{ gap: 4px; }}
  div[data-testid="stRadio"] label {{
      background: {WHITE}; border: 1px solid {TINT}; border-radius: 6px;
      padding: 9px 12px !important; width: 100%; margin-bottom: 2px !important;
      transition: background .12s ease, border-color .12s ease;
  }}
  div[data-testid="stRadio"] label:hover {{ background: {TINT_2}; border-color: {BLUE}; }}
  div[data-testid="stRadio"] label div p {{ color: {NAVY} !important; font-size: 13.5px; font-weight: 600; }}
  div[data-testid="stRadio"] label:has(input:checked) {{
      background: {BLUE}; border-color: {BLUE};
      box-shadow: 0 2px 6px rgba(0,111,207,0.28);
  }}
  div[data-testid="stRadio"] label:has(input:checked) div p {{ color: {WHITE} !important; }}
  div[data-testid="stRadio"] label:has(input:checked) span {{ background-color: {WHITE} !important; }}

  /* ── buttons, selects, sliders, inputs ── */
  .stButton > button {{
      background: {BLUE}; color: {WHITE}; border: none; border-radius: 6px;
      font-weight: 600;
  }}
  .stButton > button:hover {{ background: {BLUE_MID}; color: {WHITE}; }}
  div[data-baseweb="select"] > div {{ border-color: {TINT} !important; background: {WHITE}; }}
  .stTextInput input, .stNumberInput input {{ border-color: {TINT} !important; color: {GREY_DK}; }}

  /* ── tabs ── */
  button[data-baseweb="tab"] {{ font-weight: 600; color: {GREY}; }}
  button[data-baseweb="tab"][aria-selected="true"] {{ color: {BLUE}; border-bottom-color: {BLUE} !important; }}
  div[data-baseweb="tab-highlight"] {{ background-color: {BLUE} !important; }}
  div[data-baseweb="tab-border"] {{ background-color: {TINT} !important; }}

  /* ── native dataframes / tables, if any remain ── */
  [data-testid="stDataFrame"] {{ border: 1px solid {TINT}; border-radius: 6px; }}

  /* ── alert boxes ── */
  div[data-testid="stAlert"] {{ border-radius: 6px; }}

  /* navy header band — matches slide 4/5 convention */
  .amex-band {{
      background: {BLUE};
      border-bottom: 3px solid {GOLD};
      padding: 18px 26px; margin: -8px 0 22px 0; border-radius: 4px;
  }}
  .amex-band h1 {{
      color: {GREY_DK}; font-size: 24px; font-weight: 900;
      margin: 0; letter-spacing: -0.3px;
  }}
  .amex-band p {{ color: {TINT}; font-size: 13px; margin: 6px 0 0 0; }}

  /* section label — navy bold, the column-header convention */
  .amex-section {{
      color: {NAVY}; font-size: 15px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.6px;
      border-left: 4px solid {BLUE}; padding-left: 10px;
      margin: 22px 0 12px 0;
  }}

  /* KPI cards */
  .amex-kpi {{
      background: {WHITE}; border: 1px solid {TINT};
      border-left: 4px solid {BLUE}; border-radius: 4px;
      padding: 14px 16px; height: 100%;
      box-shadow: 0 1px 2px rgba(13,34,64,0.06);
  }}
  .amex-kpi .lbl {{
      color: {GREY}; font-size: 11px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.7px; margin-bottom: 6px;
  }}
  .amex-kpi .val {{ color: {NAVY}; font-size: 26px; font-weight: 700; line-height: 1.1; }}
  .amex-kpi .sub {{ color: {GREY}; font-size: 11px; margin-top: 5px; }}
  .amex-kpi.gold {{ border-left-color: {GOLD}; }}
  .amex-kpi.gold .val {{ color: {GOLD}; }}
  .amex-kpi.red  {{ border-left-color: {RED}; }}
  .amex-kpi.red  .val {{ color: {RED}; }}
  .amex-kpi.teal {{ border-left-color: {TEAL}; }}
  .amex-kpi.teal .val {{ color: {TEAL}; }}

  /* navy callout — the "so what" box */
  .amex-callout {{
      background: {NAVY}; color: {WHITE}; border-radius: 4px;
      padding: 16px 20px; margin: 16px 0; font-size: 14px; line-height: 1.55;
      border-left: 4px solid {GOLD};
  }}
  .amex-callout b {{ color: {GOLD}; }}

  /* light insight panel */
  .amex-panel {{
      background: {PANEL}; border: 1px solid {TINT};
      border-radius: 4px; padding: 16px 20px; margin: 12px 0;
      font-size: 14px; line-height: 1.6; color: {WHITE};
  }}
  .amex-panel .src {{
      color: {GREY}; font-size: 11px; text-transform: uppercase;
      letter-spacing: 0.6px; margin-bottom: 8px; font-weight: 600;
  }}

  /* tables */
  table.amex {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  table.amex thead th {{
      background: {BLUE}; color: {WHITE}; font-weight: 600;
      text-align: left; padding: 9px 12px; border: none;
      text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px;
  }}
  table.amex tbody td {{ padding: 8px 12px; border-bottom: 1px solid {TINT}; color: {GREY_DK}; }}
  table.amex tbody tr:nth-child(even) {{ background: {TINT_2}; }}
  table.amex tbody tr:hover {{ background: {TINT}; }}
  table.amex td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  table.amex td.flag {{ color: {RED}; font-weight: 700; }}
  table.amex td.good {{ color: {TEAL}; font-weight: 600; }}

  /* chevron breadcrumb footer */
  .amex-chev {{ display: flex; gap: 6px; margin: 26px 0 8px 0; flex-wrap: wrap; }}
  .amex-chev span {{
      background: {TINT_2}; color: {BLUE_MID}; font-size: 11px; font-weight: 600;
      padding: 6px 14px; border-radius: 2px; text-transform: uppercase;
      letter-spacing: 0.5px;
  }}
  .amex-chev span.on {{ background: {BLUE}; color: {WHITE}; }}

  /* sidebar */
  section[data-testid="stSidebar"] {{
      background: {PANEL}; border-right: 1px solid {TINT};
  }}
  section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: 0.4rem; }}
  section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {{
      color: {NAVY}; font-size: 15px;
  }}
  section[data-testid="stSidebar"] .block-container {{ padding-top: 0; }}

  /* sidebar brand mark */
  .amex-brand {{
      text-align: center; padding: 20px 6px 16px 6px;
      border-bottom: 3px solid {GOLD}; margin-bottom: 16px;
      background: {NAVY}; border-radius: 0 0 8px 8px; margin: -1rem -1rem 16px -1rem;
      padding-left: 1rem; padding-right: 1rem;
  }}
  .amex-brand .mark {{ font-size: 26px; line-height: 1; }}
  .amex-brand .name {{
      color: {WHITE}; font-size: 18px; font-weight: 800;
      letter-spacing: -0.3px; margin-top: 6px;
  }}
  .amex-brand .tag {{
      color: {TINT}; font-size: 10.5px; text-transform: uppercase;
      letter-spacing: 0.7px; margin-top: 3px;
  }}

  /* sidebar mini section label */
  .amex-side-label {{
      color: {GREY}; font-size: 10.5px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.7px; margin: 16px 2px 8px 2px; padding-top: 10px;
      border-top: 1px solid {TINT};
  }}

  /* compact sidebar KPI card */
  .amex-kpi-sm {{
      background: {WHITE}; border: 1px solid {TINT}; border-left: 3px solid {BLUE};
      border-radius: 5px; padding: 8px 10px; margin-bottom: 8px;
  }}
  .amex-kpi-sm .lbl {{
      color: {GREY}; font-size: 9.5px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.5px; margin-bottom: 2px;
  }}
  .amex-kpi-sm .val {{ color: {NAVY}; font-size: 18px; font-weight: 700; line-height: 1.15; }}
  .amex-kpi-sm.gold {{ border-left-color: {GOLD}; }}
  .amex-kpi-sm.gold .val {{ color: {GOLD}; }}

  /* status pill (LLM connection etc.) */
  .amex-pill {{
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 11.5px; font-weight: 600; padding: 5px 10px;
      border-radius: 20px; width: 100%; box-sizing: border-box;
  }}
  .amex-pill .dot {{ width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }}
  .amex-pill.on  {{ background: rgba(0,184,159,0.12); color: {TEAL}; }}
  .amex-pill.on  .dot {{ background: {TEAL}; }}
  .amex-pill.off {{ background: {TINT_2}; color: {GREY}; }}
  .amex-pill.off .dot {{ background: {GREY}; }}
</style>
"""


# ── HTML COMPONENT BUILDERS ──────────────────────────────────────────────────
def band(title, subtitle=""):
    return f'<div class="amex-band"><h1>{title}</h1><p>{subtitle}</p></div>'


def section(label):
    return f'<div class="amex-section">{label}</div>'


def kpi(label, value, sub="", tone=""):
    """tone: '' (blue) | 'gold' (money) | 'red' (the stare number) | 'teal'."""
    return (f'<div class="amex-kpi {tone}"><div class="lbl">{label}</div>'
            f'<div class="val">{value}</div>'
            f'<div class="sub">{sub}</div></div>')


def brand(name="Platinum 365", tag="Benefit Utilisation Engine", mark="💳"):
    return (f'<div class="amex-brand"><div class="mark">{mark}</div>'
            f'<div class="name">{name}</div><div class="tag">{tag}</div></div>')


def side_label(label):
    return f'<div class="amex-side-label">{label}</div>'


def kpi_sm(label, value, tone=""):
    """Compact KPI card for narrow columns (sidebar)."""
    return (f'<div class="amex-kpi-sm {tone}"><div class="lbl">{label}</div>'
            f'<div class="val">{value}</div></div>')


def pill(label, on=True):
    cls = "on" if on else "off"
    return f'<div class="amex-pill {cls}"><span class="dot"></span>{label}</div>'


def callout(html):
    return f'<div class="amex-callout">{html}</div>'


def panel(html, source=""):
    src = f'<div class="src">{source}</div>' if source else ""
    return f'<div class="amex-panel">{src}{html}</div>'


def chevrons(steps, active):
    cells = "".join(
        f'<span class="{"on" if s == active else ""}">{s}</span>' for s in steps
    )
    return f'<div class="amex-chev">{cells}</div>'


def table(df, numeric_cols=None, flag=None, good=None, index_label=None):
    """
    Render a DataFrame in house style.
      numeric_cols : right-aligned, tabular numerals
      flag         : callable(row_label, col, value) -> True to paint the cell red
                     (convention: at most ONE red cell per table)
      good         : callable(row_label, col, value) -> True to paint teal
    """
    numeric_cols = numeric_cols or []
    cols = list(df.columns)
    head_cells = ""
    if index_label is not None:
        head_cells += f"<th>{index_label}</th>"
    head_cells += "".join(f"<th>{c}</th>" for c in cols)

    body = ""
    for idx, row in df.iterrows():
        body += "<tr>"
        if index_label is not None:
            body += f"<td><b>{idx}</b></td>"
        for c in cols:
            v = row[c]
            cls = "num" if c in numeric_cols else ""
            if flag and flag(idx, c, v):
                cls = (cls + " flag").strip()
            elif good and good(idx, c, v):
                cls = (cls + " good").strip()
            txt = v if isinstance(v, str) else (
                f"{v:,.2f}" if isinstance(v, (float, np.floating)) else f"{v:,}"
            )
            body += f'<td class="{cls}">{txt}</td>'
        body += "</tr>"

    return (f'<table class="amex"><thead><tr>{head_cells}</tr></thead>'
            f"<tbody>{body}</tbody></table>")


def inr(x, cr=False, dp=1):
    """₹ formatter. cr=True -> crores."""
    if pd.isna(x):
        return "—"
    if cr:
        return f"₹{x/1e7:,.{dp}f} Cr"
    return f"₹{x:,.0f}"