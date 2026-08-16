"""
PLATINUM 365 — BENEFIT UTILISATION DASHBOARD  (v4, Amex-themed)
================================================================================
Fixes in this version
  1. go.Waterfall(marker=...) is invalid in Plotly -> increasing/decreasing/totals
  2. Waterfall arithmetic was wrong (headroom - cost + recovery labelled "total")
     -> two correct waterfalls: per-card budget, and portfolio value
  3. Member Drilldown had no LLM output at all -> new "Where the value is going"
     tab with unspent-category diagnosis + Layer 3 pick-2 recommendation
  4. 40,000-row selectbox -> filtered member picker + direct ID lookup
  5. Default Plotly palette -> Amex PS palette via amex_theme
Requires: amex_theme.py, amex_insight.py in the same folder.
Run:      streamlit run app.py
================================================================================
"""

import os
import warnings
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from amex_theme import (NAVY, BLUE, BLUE_MID, CYAN, GOLD, RED, TEAL, GREY, WHITE,
                        CSS, AMEX_SCALE, CAUSE_COLOURS, amex_layout, band, section,
                        kpi, callout, panel, chevrons, table, inr,
                        brand, side_label, kpi_sm, pill)
import amex_insight as ai

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Platinum 365 — Benefit Utilisation",
                   page_icon="💳", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

PAGES = ["Portfolio Overview", "Gap Diagnosis", "Propensity Explorer",
         "Nudge Optimizer", "Member Drilldown", "Data Quality"]

CEILING = 20_000
L2_L3_COMMITTED = 13_849
HEADROOM = CEILING - L2_L3_COMMITTED


# ── DATA ─────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading portfolio…")
def load_data():
    xf = "amex_benefit_utilisation_v3.xlsx"
    customers = pd.read_excel(xf, sheet_name="customers")
    registry = pd.read_excel(xf, sheet_name="benefit_registry")
    redemptions = pd.read_excel(xf, sheet_name="redemptions")
    gap_summary = pd.read_excel(xf, sheet_name="gap_summary")

    gap_causes = pd.read_csv("gap_causes.csv")
    propensity = pd.read_csv("propensity_scores.csv")
    nudge_recs = pd.read_csv("nudge_recommendations.csv")

    # nudgeable can arrive as bool or as the string "True"
    if gap_causes["nudgeable"].dtype == object:
        gap_causes["nudgeable"] = (gap_causes["nudgeable"].astype(str)
                                   .str.strip().str.lower()
                                   .isin(["true", "1", "yes"]))

    def maybe(path):
        try:
            return pd.read_csv(path)
        except Exception:
            return None

    return (customers, registry, redemptions, gap_summary, gap_causes,
            propensity, nudge_recs, maybe("nudge_copy.csv"),
            maybe("llm_diagnoses.csv"))


try:
    (customers_df, registry_df, redemptions_df, gap_summary_df, gap_causes_df,
     propensity_df, nudge_recs_df, nudge_copy_df, llm_diagnoses_df) = load_data()
except Exception as e:
    st.markdown(band("Platinum 365", "Data files not found"), unsafe_allow_html=True)
    st.error("Could not load the dashboard data files.")
    st.markdown("""**Required in the same folder as `app.py`:**
- `amex_benefit_utilisation_v3.xlsx` (Phase 1)
- `gap_causes.csv` (Phase 2) · `propensity_scores.csv` (Phase 3)
- `nudge_recommendations.csv` (Phase 4)
- Optional: `nudge_copy.csv` (Phase 5) · `llm_diagnoses.csv` (Phase 6)""")
    st.exception(e)
    st.stop()

# ── PRE-CALCULATIONS ─────────────────────────────────────────────────────────
total_gap = gap_summary_df["gross_gap"].sum()
addressable_gap = gap_summary_df["addressable_gap"].sum()
avg_gap_per_member = gap_summary_df["gross_gap"].mean()
avg_util = gap_summary_df["utilisation_pct"].mean()

archetype_gap = (gap_summary_df.groupby("archetype")
                 .agg(members=("customer_id", "count"),
                      gross_gap=("gross_gap", "sum"),
                      addressable_gap=("addressable_gap", "sum"),
                      utilisation_pct=("utilisation_pct", "mean"))
                 .sort_values("gross_gap", ascending=False))
archetype_gap["gross_gap_cr"] = archetype_gap["gross_gap"] / 1e7
archetype_gap["addr_gap_cr"] = archetype_gap["addressable_gap"] / 1e7

cause_totals = (gap_causes_df.groupby("cause")["gap_value"].sum()
                .sort_values(ascending=False))
nudgeable = gap_causes_df[gap_causes_df["nudgeable"]]
nudgeable_gap = nudgeable["gap_value"].sum()
non_nudgeable_gap = gap_causes_df.loc[~gap_causes_df["nudgeable"], "gap_value"].sum()

benefit_name_map = dict(zip(registry_df["benefit_id"], registry_df["name"]))
propensity_df["benefit_name"] = propensity_df["benefit_id"].map(benefit_name_map)

total_nudges = len(nudge_recs_df)
unique_members = nudge_recs_df["customer_id"].nunique()
total_cost = nudge_recs_df["expected_cost_inr"].sum()
total_recovery = nudge_recs_df["expected_recovery_inr"].sum()
net_value = nudge_recs_df["net_value_inr"].sum()
roi = (net_value / total_cost * 100) if total_cost > 0 else 0
avg_nudge_cost_per_member = total_cost / unique_members if unique_members else 0

validation = {}
for name, df, expected in [
    ("Customers", customers_df, ["customer_id", "archetype", "annual_spend",
                                 "spend_tier", "milestone_attained"]),
    ("Nudge recommendations", nudge_recs_df, ["customer_id", "benefit_id",
                                              "expected_cost_inr",
                                              "expected_recovery_inr",
                                              "net_value_inr"]),
    ("Gap summary", gap_summary_df, ["gross_gap", "addressable_gap",
                                     "utilisation_pct"]),
    ("Gap causes", gap_causes_df, ["customer_id", "benefit_id", "cause",
                                   "gap_value"]),
]:
    validation[name] = [c for c in expected if c not in df.columns]

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
st.sidebar.markdown(brand("Platinum 365", "Benefit Utilisation Engine"),
                    unsafe_allow_html=True)

page = st.sidebar.radio("View", PAGES, label_visibility="collapsed")

st.sidebar.markdown(side_label("Portfolio at a glance"), unsafe_allow_html=True)
r1c1, r1c2 = st.sidebar.columns(2)
r1c1.markdown(kpi_sm("Cardholders", f"{len(customers_df):,}"), unsafe_allow_html=True)
r1c2.markdown(kpi_sm("Benefits", f"{len(registry_df):,}"), unsafe_allow_html=True)
r2c1, r2c2 = st.sidebar.columns(2)
r2c1.markdown(kpi_sm("Gap records", f"{len(gap_causes_df):,}"), unsafe_allow_html=True)
r2c2.markdown(kpi_sm("Nudges", f"{len(nudge_recs_df):,}", tone="gold"),
              unsafe_allow_html=True)

st.sidebar.markdown(side_label("LLM Layer"), unsafe_allow_html=True)
api_key = os.environ.get("GOOGLE_AI_API_KEY", "")
try:
    api_key = api_key or st.secrets.get("GOOGLE_AI_API_KEY", "")
except Exception:
    pass
llm_ok, llm_msg = ai.gemini_available(api_key)
st.sidebar.markdown(
    pill("Gemini connected" if llm_ok else llm_msg, on=llm_ok),
    unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# 1 — PORTFOLIO OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
if page == "Portfolio Overview":
    st.markdown(band("Portfolio Overview",
                     "Benefit value issued vs benefit value consumed, "
                     "across the full Premier Card base"), unsafe_allow_html=True)

    c = st.columns(5)
    c[0].markdown(kpi("Members", f"{len(gap_summary_df):,}"), unsafe_allow_html=True)
    c[1].markdown(kpi("Gross Gap", inr(total_gap, cr=True),
                      "issued, not consumed", tone="red"), unsafe_allow_html=True)
    c[2].markdown(kpi("Addressable Gap", inr(addressable_gap, cr=True),
                      f"{addressable_gap/total_gap*100:.1f}% of gross"),
                  unsafe_allow_html=True)
    c[3].markdown(kpi("Gap / Member", inr(avg_gap_per_member)), unsafe_allow_html=True)
    c[4].markdown(kpi("Avg Utilisation", f"{avg_util:.1f}%", tone="gold"),
                  unsafe_allow_html=True)

    st.markdown(section("Gap by archetype"), unsafe_allow_html=True)
    worst = archetype_gap.index[0]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=archetype_gap.index, y=archetype_gap["gross_gap_cr"], name="Gross gap",
        marker_color=[RED if a == worst else BLUE for a in archetype_gap.index],
        hovertemplate="<b>%{x}</b><br>Gross gap: ₹%{y:.1f} Cr<extra></extra>"))
    fig.add_trace(go.Bar(
        x=archetype_gap.index, y=archetype_gap["addr_gap_cr"],
        name="Addressable gap", marker_color=CYAN,
        hovertemplate="<b>%{x}</b><br>Addressable: ₹%{y:.1f} Cr<extra></extra>"))
    amex_layout(fig, "Gross vs addressable gap by archetype", 430, barmode="group",
                xaxis_title="Archetype", yaxis_title="₹ Crores",
                hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(section("Archetype detail"), unsafe_allow_html=True)
    tbl = pd.DataFrame({
        "Members": archetype_gap["members"].map("{:,}".format),
        "Gross gap (₹ Cr)": archetype_gap["gross_gap_cr"].round(1),
        "Addressable (₹ Cr)": archetype_gap["addr_gap_cr"].round(1),
        "Utilisation %": archetype_gap["utilisation_pct"].round(1),
    })
    st.markdown(table(tbl, numeric_cols=list(tbl.columns), index_label="Archetype",
                      flag=lambda i, c, v: (i == worst and c == "Gross gap (₹ Cr)")),
                unsafe_allow_html=True)

    st.markdown(callout(
        f"<b>{inr(avg_gap_per_member)}</b> of benefit value sits unused on the "
        f"average card. Across the base that is <b>{inr(total_gap, cr=True)}</b> "
        f"issued and not felt — paid for by the fee, invisible at renewal."),
        unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 2 — GAP DIAGNOSIS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Gap Diagnosis":
    st.markdown(band("Gap Diagnosis",
                     "Why the value goes unconsumed — and which part a nudge "
                     "can actually move"), unsafe_allow_html=True)

    c = st.columns(4)
    c[0].markdown(kpi("Gross Gap", inr(cause_totals.sum(), cr=True)),
                  unsafe_allow_html=True)
    c[1].markdown(kpi("Nudgeable", inr(nudgeable_gap, cr=True),
                      f"{nudgeable_gap/cause_totals.sum()*100:.1f}% of gross",
                      tone="teal"), unsafe_allow_html=True)
    c[2].markdown(kpi("Not Nudgeable", inr(non_nudgeable_gap, cr=True),
                      "relevance / structural", tone="red"), unsafe_allow_html=True)
    top_cause = cause_totals.index[0]
    c[3].markdown(kpi("Dominant Cause", str(top_cause).capitalize(),
                      inr(cause_totals.iloc[0], cr=True)), unsafe_allow_html=True)

    left, right = st.columns(2)

    with left:
        st.markdown(section("Root cause split"), unsafe_allow_html=True)
        cause_pct = (cause_totals / cause_totals.sum() * 100).round(1)
        ct = pd.DataFrame({"Gap (₹ Cr)": (cause_totals / 1e7).round(1),
                           "Share %": cause_pct})
        ct.index = [str(i).capitalize() for i in ct.index]
        st.markdown(table(ct, numeric_cols=list(ct.columns), index_label="Cause",
                          flag=lambda i, c, v: (i.lower() == "irrelevance"
                                                and c == "Gap (₹ Cr)")),
                    unsafe_allow_html=True)
        st.markdown(panel(
            "Irrelevance is the one line a nudge cannot fix. That is the whole "
            "argument for a swappable Layer 3 — the member is holding a benefit "
            "they were never going to use.", "READ THIS ROW"), unsafe_allow_html=True)

    with right:
        st.markdown(section("Gap composition"), unsafe_allow_html=True)
        pie = go.Figure(go.Pie(
            labels=[str(c).capitalize() for c in cause_totals.index],
            values=cause_totals.values, hole=0.55, sort=False,
            marker=dict(colors=[CAUSE_COLOURS.get(str(c), GREY)
                                for c in cause_totals.index],
                        line=dict(color=WHITE, width=2)),
            textinfo="label+percent", textfont=dict(size=12),
            hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}"
                          "<extra></extra>"))
        amex_layout(pie, "Gap by root cause", 430, showlegend=False)
        pie.add_annotation(
            text=f"<b>{inr(cause_totals.sum(), cr=True)}</b><br>"
                 f"<span style='font-size:11px;color:{GREY}'>gross gap</span>",
            showarrow=False, font=dict(size=16, color=NAVY))
        st.plotly_chart(pie, use_container_width=True)

    st.markdown(section("Where the gap sits, by benefit"), unsafe_allow_html=True)
    by_benefit = (gap_causes_df.groupby("benefit_id")["gap_value"].sum()
                  .sort_values(ascending=True) / 1e7)
    fig = go.Figure(go.Bar(
        y=[benefit_name_map.get(b, b) for b in by_benefit.index],
        x=by_benefit.values, orientation="h", marker_color=BLUE_MID,
        hovertemplate="<b>%{y}</b><br>₹%{x:.1f} Cr<extra></extra>"))
    amex_layout(fig, "Unconsumed value by benefit (₹ Cr)", 520,
                xaxis_title="₹ Crores", margin=dict(l=250, r=30, t=60, b=50))
    st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# 3 — PROPENSITY EXPLORER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Propensity Explorer":
    st.markdown(band("Propensity Explorer",
                     "Out-of-fold LightGBM P(use) — who would consume what, "
                     "if the value were made visible"), unsafe_allow_html=True)

    c = st.columns(4)
    c[0].markdown(kpi("Scored Pairs", f"{len(propensity_df):,}"),
                  unsafe_allow_html=True)
    c[1].markdown(kpi("Mean P(use)", f"{propensity_df['propensity'].mean():.3f}"),
                  unsafe_allow_html=True)
    c[2].markdown(kpi("Std Dev", f"{propensity_df['propensity'].std():.3f}",
                      "spread = targeting power"), unsafe_allow_html=True)
    c[3].markdown(kpi("Range", f"{propensity_df['propensity'].min():.2f}–"
                               f"{propensity_df['propensity'].max():.2f}"),
                  unsafe_allow_html=True)

    st.markdown(section("Highest-propensity benefits"), unsafe_allow_html=True)
    bp = (propensity_df.groupby("benefit_name")["propensity"].mean()
          .sort_values(ascending=False).head(10))
    tb = pd.DataFrame({"Mean P(use)": bp.round(3)})
    st.markdown(table(tb, numeric_cols=["Mean P(use)"], index_label="Benefit",
                      good=lambda i, c, v: v >= 0.5), unsafe_allow_html=True)

    st.markdown(section("Propensity by benefit × spend tier"), unsafe_allow_html=True)
    pw = propensity_df.merge(customers_df[["customer_id", "spend_tier"]],
                             on="customer_id", how="left")
    hm = pw.pivot_table(index="benefit_name", columns="spend_tier",
                        values="propensity", aggfunc="mean")
    tier_order = [t for t in ["Underused", "Core", "Milestone", "High", "Whale"]
                  if t in hm.columns]
    if tier_order:
        hm = hm[tier_order]
    hm = hm.loc[hm.mean(axis=1).sort_values(ascending=False).index]

    fig = go.Figure(go.Heatmap(
        z=hm.values, x=list(hm.columns), y=list(hm.index), colorscale=AMEX_SCALE,
        text=np.round(hm.values, 2), texttemplate="%{text:.2f}",
        textfont=dict(size=11), zmin=0, zmax=float(np.nanmax(hm.values)),
        colorbar=dict(title=dict(text="P(use)", font=dict(color=NAVY)),
                      outlinewidth=0),
        hovertemplate="<b>%{y}</b><br>%{x}: %{z:.3f}<extra></extra>"))
    amex_layout(fig, "Propensity heatmap", 620, xaxis_title="Spend tier",
                margin=dict(l=250, r=30, t=60, b=50))
    st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# 4 — NUDGE OPTIMIZER   (the waterfall fix lives here)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Nudge Optimizer":
    st.markdown(band("Nudge Optimizer",
                     "Greedy knapsack under the ₹6,151 per-card headroom"),
                unsafe_allow_html=True)

    c = st.columns(5)
    c[0].markdown(kpi("Nudges", f"{total_nudges:,}"), unsafe_allow_html=True)
    c[1].markdown(kpi("Members Covered", f"{unique_members:,}",
                      f"{unique_members/len(customers_df)*100:.0f}% of base"),
                  unsafe_allow_html=True)
    c[2].markdown(kpi("Expected Recovery", inr(total_recovery, cr=True),
                      tone="teal"), unsafe_allow_html=True)
    c[3].markdown(kpi("Expected Cost", inr(total_cost, cr=True)),
                  unsafe_allow_html=True)
    c[4].markdown(kpi("Net Value", inr(net_value, cr=True), f"ROI {roi:,.0f}%",
                      tone="gold"), unsafe_allow_html=True)

    st.markdown(section("Per-card budget"), unsafe_allow_html=True)
    b = st.columns(4)
    b[0].markdown(kpi("Ceiling", f"₹{CEILING:,}", "PS S4 constraint 2"),
                  unsafe_allow_html=True)
    b[1].markdown(kpi("L2 + L3 Committed", f"₹{L2_L3_COMMITTED:,}",
                      "already in the design"), unsafe_allow_html=True)
    b[2].markdown(kpi("Headroom", f"₹{HEADROOM:,}", "available to nudge delivery"),
                  unsafe_allow_html=True)
    b[3].markdown(kpi("Avg Spent / Member", f"₹{avg_nudge_cost_per_member:,.0f}",
                      f"{avg_nudge_cost_per_member/HEADROOM*100:.0f}% of headroom "
                      f"used"), unsafe_allow_html=True)

    w1, w2 = st.columns(2)
    unused_pc = HEADROOM - avg_nudge_cost_per_member

    # ---- Waterfall A: per-card budget (this is the chart that used to error) --
    with w1:
        wf = go.Figure(go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "total", "relative", "total"],
            x=["Ceiling", "L2 + L3 committed", "Headroom", "Nudge spend",
               "Unused headroom"],
            y=[CEILING, -L2_L3_COMMITTED, 0, -avg_nudge_cost_per_member, 0],
            text=[f"₹{CEILING:,}", f"−₹{L2_L3_COMMITTED:,}", f"₹{HEADROOM:,}",
                  f"−₹{avg_nudge_cost_per_member:,.0f}", f"₹{unused_pc:,.0f}"],
            textposition="outside", cliponaxis=False,
            # Waterfall has NO `marker` property — colours go in these three:
            increasing=dict(marker=dict(color=TEAL)),
            decreasing=dict(marker=dict(color=RED)),
            totals=dict(marker=dict(color=GOLD, line=dict(color=NAVY, width=1))),
            connector=dict(line=dict(color=GREY, width=1, dash="dot")),
            hovertemplate="<b>%{x}</b><br>₹%{y:,.0f}<extra></extra>"))
        amex_layout(wf, "Per-card budget (₹ per card per year)", 440,
                    yaxis_title="₹ per card", showlegend=False)
        st.plotly_chart(wf, use_container_width=True)

    # ---- Waterfall B: portfolio value ---------------------------------------
    with w2:
        wf2 = go.Figure(go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "total"],
            x=["Expected recovery", "Nudge cost", "Net value"],
            y=[total_recovery / 1e7, -total_cost / 1e7, 0],
            text=[f"₹{total_recovery/1e7:,.1f} Cr", f"−₹{total_cost/1e7:,.1f} Cr",
                  f"₹{net_value/1e7:,.1f} Cr"],
            textposition="outside", cliponaxis=False,
            increasing=dict(marker=dict(color=TEAL)),
            decreasing=dict(marker=dict(color=RED)),
            totals=dict(marker=dict(color=GOLD, line=dict(color=NAVY, width=1))),
            connector=dict(line=dict(color=GREY, width=1, dash="dot")),
            hovertemplate="<b>%{x}</b><br>₹%{y:,.2f} Cr<extra></extra>"))
        amex_layout(wf2, "Portfolio value of the nudge programme", 440,
                    yaxis_title="₹ Crores", showlegend=False)
        st.plotly_chart(wf2, use_container_width=True)

    st.markdown(callout(
        f"Every ₹1 of nudge delivery returns <b>₹{roi/100:,.1f}</b> of recovered "
        f"benefit value, and the whole programme fits inside the ₹{HEADROOM:,} "
        f"that is left after Layer 2 and Layer 3 are funded."),
        unsafe_allow_html=True)

    st.markdown(section("Nudge economics by root cause"), unsafe_allow_html=True)
    bc = (nudge_recs_df.groupby("cause")
          .agg(nudges=("customer_id", "count"),
               cost=("expected_cost_inr", "sum"),
               recovery=("expected_recovery_inr", "sum"),
               net=("net_value_inr", "sum"))
          .sort_values("net", ascending=False))
    bc["ROI %"] = np.where(bc["cost"] > 0, bc["net"] / bc["cost"] * 100, 0)
    disp = pd.DataFrame({
        "Nudges": bc["nudges"].map("{:,}".format),
        "Cost (₹ Cr)": (bc["cost"] / 1e7).round(2),
        "Recovery (₹ Cr)": (bc["recovery"] / 1e7).round(2),
        "Net value (₹ Cr)": (bc["net"] / 1e7).round(2),
        "ROI %": bc["ROI %"].round(0),
    })
    disp.index = [str(i).capitalize() for i in disp.index]
    best = disp["ROI %"].idxmax()
    st.markdown(table(disp, numeric_cols=list(disp.columns), index_label="Cause",
                      good=lambda i, c, v: (i == best and c == "ROI %")),
                unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 5 — MEMBER DRILLDOWN   (LLM layer added here)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Member Drilldown":
    st.markdown(band("Member Drilldown",
                     "One card, one diagnosis, one Layer 3 activation plan"),
                unsafe_allow_html=True)

    diag_ids = (set(llm_diagnoses_df["customer_id"].astype(str))
                if llm_diagnoses_df is not None else set())

    # --- picker: filter first, never render 40,000 options -------------------
    f = st.columns([2, 2, 2, 3])
    arch_pick = f[0].selectbox(
        "Archetype", ["All"] + sorted(customers_df["archetype"].unique().tolist()))
    tier_pick = f[1].selectbox(
        "Spend tier", ["All"] + [t for t in ["Underused", "Core", "Milestone",
                                             "High", "Whale"]
                                 if t in set(customers_df["spend_tier"])])
    only_llm = f[2].checkbox("Only members with a stored Phase 6 diagnosis",
                             value=bool(diag_ids))
    typed = f[3].text_input("…or jump straight to a member ID",
                            placeholder="C00042")

    pool = customers_df.copy()
    if arch_pick != "All":
        pool = pool[pool["archetype"] == arch_pick]
    if tier_pick != "All":
        pool = pool[pool["spend_tier"] == tier_pick]
    if only_llm and diag_ids:
        pool = pool[pool["customer_id"].astype(str).isin(diag_ids)]

    options = pool["customer_id"].astype(str).tolist()[:400]
    if typed.strip():
        selected_member = typed.strip()
    elif options:
        selected_member = st.selectbox(
            f"Member — {len(pool):,} match this filter, showing first "
            f"{len(options)}", options)
    else:
        st.warning("No members match that filter.")
        st.stop()

    m_rows = customers_df[customers_df["customer_id"].astype(str) == selected_member]
    g_rows = gap_summary_df[
        gap_summary_df["customer_id"].astype(str) == selected_member]
    if m_rows.empty or g_rows.empty:
        st.warning(f"No profile found for `{selected_member}`.")
        st.stop()

    member = m_rows.iloc[0]
    member_gap = g_rows.iloc[0]
    member_causes = gap_causes_df[
        gap_causes_df["customer_id"].astype(str) == selected_member]
    member_prop = propensity_df[
        propensity_df["customer_id"].astype(str) == selected_member]
    member_nudges = nudge_recs_df[
        nudge_recs_df["customer_id"].astype(str) == selected_member]

    st.markdown(section(f"Profile · {selected_member}"), unsafe_allow_html=True)
    p = st.columns(4)
    p[0].markdown(kpi("Archetype", str(member.get("archetype", "—"))),
                  unsafe_allow_html=True)
    p[1].markdown(kpi("Spend Tier", str(member.get("spend_tier", "—")),
                      f"{int(member.get('tenure_months', 0))} months tenure"),
                  unsafe_allow_html=True)
    p[2].markdown(kpi("Annual Spend", inr(member.get("annual_spend", 0))),
                  unsafe_allow_html=True)
    p[3].markdown(kpi("Utilisation", f"{member_gap.get('utilisation_pct', 0):.1f}%",
                      f"unused: {inr(member_gap.get('gross_gap', 0))}", tone="red"),
                  unsafe_allow_html=True)

    # --- deterministic engine, always runs -----------------------------------
    active_only = st.checkbox(
        "Restrict activations to the four ACTIVE modules (pick-2-of-4 model); "
        "M1 / M5 shown as swap candidates", value=True)
    ranked, unspent, _why = ai.recommend_modules(
        selected_member, member, member_causes, registry_df, top_n=2,
        active_only=active_only)
    merged_member = {**member.to_dict(),
                     "utilisation_pct": member_gap.get("utilisation_pct", 0)}
    payload = ai.build_payload(selected_member, merged_member, member_causes,
                               ranked, unspent, member_nudges, top_n=2)

    t1, t2, t3, t4 = st.tabs(["Where the value is going", "Unspent categories",
                              "Benefit propensity", "Nudges"])

    # ---------- TAB 1: the LLM layer -----------------------------------------
    with t1:
        stored = None
        if llm_diagnoses_df is not None:
            hit = llm_diagnoses_df[
                llm_diagnoses_df["customer_id"].astype(str) == selected_member]
            if not hit.empty:
                stored = str(hit.iloc[0]["diagnosis_text"])

        if "llm_cache" not in st.session_state:
            st.session_state.llm_cache = ai.load_cache()

        gen = False
        if stored is None:
            cc = st.columns([1, 3])
            gen = cc[0].button("Generate with Gemini", type="primary",
                               disabled=not llm_ok, use_container_width=True)
            cc[1].markdown(
                f"<span style='color:{GREY};font-size:12px'>Phase 6 covers a "
                f"200-member sample, so most members have no stored paragraph. "
                f"The rule-based engine below always runs — Gemini is optional "
                f"polish, not a dependency.</span>", unsafe_allow_html=True)

        text, source = ai.member_narrative(
            payload, stored=stored, cache=st.session_state.llm_cache,
            api_key=api_key, use_llm=gen)
        st.markdown(panel(text, source), unsafe_allow_html=True)

        st.markdown(section("Recommended Layer 3 activation (pick 2)"),
                    unsafe_allow_html=True)
        rc = st.columns(2)
        act_rows = ranked[ranked["recommendation"] == "ACTIVATE"].head(2)
        if act_rows.empty:
            act_rows = ranked.head(2)
        for i, row in act_rows.reset_index(drop=True).iterrows():
            rc[i].markdown(kpi(
                f"Activation {i+1} · {row['module_id']}", row["module"],
                f"absorbs {inr(row['addressable_inr'])} of unspent value · "
                f"{row['coverage_pct']:.0f}% of its face value<br>"
                f"driven by {row['driver_categories']}",
                tone="gold" if i == 0 else ""), unsafe_allow_html=True)

        mtab = pd.DataFrame({
            "Module": ranked["module"].values,
            "Status": ranked["status"].values,
            "Face value (₹)": ranked["face_value_inr"].values,
            "Unspent matched (₹)": ranked["unspent_matched_inr"].values,
            "Value absorbed (₹)": ranked["addressable_inr"].values,
            "Coverage %": ranked["coverage_pct"].values,
            "Driven by": ranked["driver_categories"].values,
            "Call": ranked["recommendation"].values,
        }, index=ranked["module_id"].values)
        st.markdown(table(mtab,
                          numeric_cols=["Face value (₹)", "Unspent matched (₹)",
                                        "Value absorbed (₹)", "Coverage %"],
                          index_label="ID",
                          good=lambda i, c, v: (c == "Call" and v == "ACTIVATE")),
                    unsafe_allow_html=True)
        st.caption("Scoring: unspent value per category × module affinity × "
                   "observable behaviour multipliers. Ranked on the uncapped match, "
                   "reported capped at each module's own face value — a module "
                   "cannot re-home more value than it is worth. Deterministic: the "
                   "LLM only narrates these numbers, it never produces them.")

        if nudge_copy_df is not None:
            hit = nudge_copy_df[
                nudge_copy_df["customer_id"].astype(str) == selected_member]
            if not hit.empty:
                st.markdown(section("Push copy on file"), unsafe_allow_html=True)
                st.markdown(panel(f"“{hit.iloc[0]['nudge_copy']}”",
                                  f"Phase 5 · {hit.iloc[0]['benefit']} · "
                                  f"{hit.iloc[0]['cause']}"), unsafe_allow_html=True)

    # ---------- TAB 2: unspent categories ------------------------------------
    with t2:
        if unspent.empty:
            st.info("No gap records for this member.")
        else:
            u = unspent.copy()
            worst_cause = str(u["top_cause"].iloc[0])
            fig = go.Figure(go.Bar(
                x=u["unspent_inr"], y=u["category"], orientation="h",
                marker_color=[RED if str(c) == "irrelevance" else BLUE
                              for c in u["top_cause"]],
                text=[f"₹{v:,.0f}" for v in u["unspent_inr"]],
                textposition="auto",
                customdata=np.stack([u["top_cause"].astype(str),
                                     u["avg_util"].astype(float)], axis=-1),
                hovertemplate="<b>%{y}</b><br>Unspent: ₹%{x:,.0f}"
                              "<br>Top cause: %{customdata[0]}"
                              "<extra></extra>"))
            amex_layout(fig, "Unspent value by category", 400,
                        xaxis_title="₹ unused",
                        margin=dict(l=150, r=30, t=60, b=50))
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(fig, use_container_width=True)

            ud = pd.DataFrame({
                "Unspent (₹)": u["unspent_inr"].astype(int).values,
                "Benefits": u["benefits"].astype(int).values,
                "Dominant cause": u["top_cause"].astype(str).values,
                "Avg utilisation %": (u["avg_util"].astype(float) * 100).round(1).values,
            }, index=u["category"].values)
            st.markdown(table(ud, numeric_cols=["Unspent (₹)", "Benefits",
                                                "Avg utilisation %"],
                              index_label="Category",
                              flag=lambda i, c, v: (c == "Dominant cause"
                                                    and v == "irrelevance")),
                        unsafe_allow_html=True)
            st.caption(f"Red = irrelevance, which no nudge can fix. Dominant cause "
                       f"in the largest category is **{worst_cause}**.")

    # ---------- TAB 3: propensity --------------------------------------------
    with t3:
        if member_prop.empty:
            st.info("No propensity records for this member.")
        else:
            tp = member_prop.nlargest(8, "propensity").copy()
            tp["benefit_name"] = tp["benefit_id"].map(benefit_name_map)
            fig = go.Figure(go.Bar(
                x=tp["propensity"], y=tp["benefit_name"], orientation="h",
                marker_color=BLUE, text=[f"{v:.2f}" for v in tp["propensity"]],
                textposition="auto",
                hovertemplate="<b>%{y}</b><br>P(use): %{x:.3f}<extra></extra>"))
            amex_layout(fig, "Top benefits by modelled P(use)", 420,
                        xaxis_title="P(use)",
                        margin=dict(l=230, r=30, t=60, b=50))
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(fig, use_container_width=True)

    # ---------- TAB 4: nudges -------------------------------------------------
    with t4:
        if member_nudges.empty:
            st.info("No nudges cleared the ROI gate for this member.")
        else:
            tn = member_nudges.nlargest(5, "net_value_inr").copy()
            tn["benefit_name"] = tn["benefit_id"].map(benefit_name_map)
            nd = pd.DataFrame({
                "Cause": tn["cause"].astype(str).values,
                "Cost (₹)": tn["expected_cost_inr"].astype(int).values,
                "Recovery (₹)": tn["expected_recovery_inr"].astype(int).values,
                "Net value (₹)": tn["net_value_inr"].astype(int).values,
            }, index=tn["benefit_name"].values)
            top_net = int(nd["Net value (₹)"].max())
            st.markdown(table(nd, numeric_cols=["Cost (₹)", "Recovery (₹)",
                                                "Net value (₹)"],
                              index_label="Benefit",
                              good=lambda i, c, v: (c == "Net value (₹)"
                                                    and v == top_net)),
                        unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 6 — DATA QUALITY
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Data Quality":
    st.markdown(band("Data Quality",
                     "What the pipeline guarantees — and what it does not"),
                unsafe_allow_html=True)

    st.markdown(section("Completeness"), unsafe_allow_html=True)
    comp = pd.DataFrame(
        {"Rows": [f"{len(customers_df):,}", f"{len(gap_summary_df):,}",
                  f"{len(registry_df):,}", f"{len(gap_causes_df):,}",
                  f"{len(propensity_df):,}", f"{len(nudge_recs_df):,}"]},
        index=["Customers", "Gap summary", "Benefit registry", "Gap causes",
               "Propensity scores", "Nudge recommendations"])
    st.markdown(table(comp, numeric_cols=["Rows"], index_label="Dataset"),
                unsafe_allow_html=True)

    st.markdown(section("Schema validation"), unsafe_allow_html=True)
    vr = pd.DataFrame([{"Status": "PASS" if not miss else "FAIL",
                        "Missing columns": ", ".join(miss) if miss else "—"}
                       for miss in validation.values()],
                      index=list(validation.keys()))
    st.markdown(table(vr, index_label="Dataset",
                      flag=lambda i, c, v: (c == "Status" and v == "FAIL"),
                      good=lambda i, c, v: (c == "Status" and v == "PASS")),
                unsafe_allow_html=True)

    st.markdown(section("Tier distribution vs Excel target"), unsafe_allow_html=True)
    dist = customers_df["spend_tier"].value_counts(normalize=True)
    target = {"Underused": 0.18, "Core": 0.27, "Milestone": 0.30,
              "High": 0.17, "Whale": 0.08}
    rows = {}
    for t, exp in target.items():
        act = float(dist.get(t, 0))
        rows[t] = {"Actual %": round(act * 100, 1), "Target %": round(exp * 100, 1),
                   "Delta (pp)": round((act - exp) * 100, 1),
                   "Status": "PASS" if abs(act - exp) < 0.02 else "CHECK"}
    td = pd.DataFrame(rows).T
    st.markdown(table(td, numeric_cols=["Actual %", "Target %", "Delta (pp)"],
                      index_label="Tier",
                      flag=lambda i, c, v: (c == "Status" and v == "CHECK")),
                unsafe_allow_html=True)

    st.markdown(section("Known limitations"), unsafe_allow_html=True)
    iss = pd.DataFrame([
        {"Severity": "MEDIUM", "Issue": "Propensity ≠ incrementality",
         "Detail": "ROI assumes every nudged redemption is incremental; a "
                   "realistic range is 30–50%"},
        {"Severity": "LOW", "Issue": "Spend distribution",
         "Detail": "P(spend > ₹19L) = 39% continuous vs 55% tier-based"},
        {"Severity": "CLOSED", "Issue": "Budget semantics",
         "Detail": "Headroom stated as ₹6,151 = ₹20,000 − ₹13,849; the waterfall "
                   "no longer adds recovery to a budget line"},
    ], index=["Phase 3", "Phase 1", "Phase 4"])
    st.markdown(table(iss, index_label="Phase",
                      flag=lambda i, c, v: (c == "Severity" and v == "MEDIUM"),
                      good=lambda i, c, v: (c == "Severity" and v == "CLOSED")),
                unsafe_allow_html=True)

# ── FOOTER ───────────────────────────────────────────────────────────────────
st.markdown(chevrons([p.split()[0] for p in PAGES], page.split()[0]),
            unsafe_allow_html=True)
st.markdown(
    f"<div style='color:{GREY};font-size:11px;margin-top:6px'>"
    f"Platinum 365 · Benefit Utilisation Engine · synthetic 40,000-member "
    f"portfolio · ₹20,000 per-card ceiling, ₹13,849 committed, ₹6,151 headroom"
    f"</div>", unsafe_allow_html=True)
