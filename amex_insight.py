"""
AMEX_INSIGHT — Member drilldown reasoning layer
================================================================================
Two halves, in line with the project principle "classical ML computes,
LLM communicates":

  1. recommend_modules()  — deterministic. Reads the member's UNSPENT categories
                            out of gap_causes, maps them onto the Layer 3 module
                            pool, applies observable behaviour multipliers and
                            returns a ranked, value-capped pick-2 recommendation.
                            Runs with no API key, no internet, zero latency.

  2. member_narrative()   — optional. Hands those numbers to Gemini to write the
                            RM-facing paragraph. Falls back to a deterministic
                            template that states the SAME numbers, so the tab is
                            never empty.

Nothing here invents a figure. Every number the LLM sees is passed in.
================================================================================
"""

import os
import json
import pandas as pd
import numpy as np

CACHE_FILE = "llm_cache.csv"

# ── CATEGORY -> LAYER 3 MODULE AFFINITY ──────────────────────────────────────
# Weight = share of the unspent value in that category that the module can
# plausibly re-home. Rows do not need to sum to 1: a category can be partly
# unrecoverable (that is the honest reading of irrelevance gap).
MODULE_AFFINITY = {
    "Travel":      {"M1": 0.55, "M5": 0.15, "M3": 0.10},
    "Hotel":       {"M1": 0.40, "M2": 0.25, "M5": 0.15},
    "Dining":      {"M2": 0.70, "M5": 0.15},
    "Lifestyle":   {"M5": 0.40, "M2": 0.25, "M1": 0.20},
    "Service":     {"M6": 0.65, "M4": 0.20},
    "Retention":   {"M3": 0.30, "M6": 0.25},
    "Protection":  {"M4": 0.55, "M6": 0.25},
    "Digital":     {"M3": 0.60},
    "Engagement":  {},          # answered by Layer 2, not a module swap
    "Acquisition": {},
    "Earn":        {},
}

MODULE_RATIONALE = {
    "M1": "unspent travel and hotel entitlement re-homed into ground mobility, "
          "which is used year-round rather than only on trips",
    "M2": "dining entitlement currently lost to the enrolment gate, delivered "
          "without a registration step",
    "M3": "e-commerce and big-ticket behaviour that the card earns on but does "
          "not currently reward with a benefit",
    "M4": "a household-level benefit that does not depend on travel frequency",
    "M5": "lifestyle entitlement that failed on relevance, swapped for an "
          "occasion-based one",
    "M6": "service and concierge value converted into recurring at-home usage",
}


def _flag(row, col, default=False):
    v = row.get(col, default)
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v) if pd.notna(v) else default


def behaviour_multipliers(member):
    """Observable-signal multipliers. Returns {module: (mult, [reasons])}."""
    mult = {m: 1.0 for m in ["M1", "M2", "M3", "M4", "M5", "M6"]}
    why = {m: [] for m in mult}

    def bump(m, factor, reason):
        mult[m] *= factor
        why[m].append(reason)

    ecom = float(member.get("ecom_share", 0) or 0)
    if _flag(member, "big_ticket_buyer") or ecom >= 0.70:
        bump("M3", 1.35, "big-ticket / high e-commerce share")
    if _flag(member, "enrolled_dining"):
        bump("M2", 1.25, "already enrolled in dining")
    else:
        bump("M2", 1.10, "dining value blocked by the enrolment gate")
    if not _flag(member, "is_golfer"):
        bump("M5", 1.15, "non-golfer — golf entitlement is a relevance write-off")
    if float(member.get("intl_trips_year", 0) or 0) >= 3:
        bump("M1", 1.20, "frequent international traveller")
    if float(member.get("age", 0) or 0) >= 40:
        bump("M4", 1.20, "age band where preventive health converts")
    if float(member.get("tenure_months", 0) or 0) >= 48:
        bump("M6", 1.15, "mature tenure — household services retain")
    if float(member.get("app_sessions_month", 0) or 0) >= 4:
        bump("M3", 1.10, "high app engagement")
    return mult, why


def recommend_modules(customer_id, member, member_gaps, registry, top_n=2,
                      active_only=True):
    """
    Deterministic Layer 3 recommendation from the member's own unspent value.

    member       : one row of customers (Series)
    member_gaps  : gap_causes rows for this member (customer_id, category,
                   gap_value, cause, utilisation_pct, benefit_id, nudgeable)
    registry     : benefit_registry sheet
    active_only  : True = only the four ACTIVE modules can be an activation call,
                   RESERVE modules (M1/M5) are labelled swap candidates instead.
                   This is the pick-2-of-4 model from Tab 3.

    Returns (ranked_df, unspent_df, why_dict)
    """
    modules = registry[registry["layer"] == 3].copy()
    face = dict(zip(modules["benefit_id"], modules["face_post_inr"]))
    names = dict(zip(modules["benefit_id"], modules["name"]))
    status = dict(zip(modules["benefit_id"], modules["status"]))

    # 1. Unspent value by category (this is the "unspent categories" view)
    if len(member_gaps):
        unspent = (member_gaps.groupby("category")
                   .agg(unspent_inr=("gap_value", "sum"),
                        benefits=("benefit_id", "nunique"),
                        top_cause=("cause", lambda s: s.value_counts().index[0]),
                        avg_util=("utilisation_pct", "mean"))
                   .sort_values("unspent_inr", ascending=False)
                   .reset_index())
    else:
        unspent = pd.DataFrame(columns=["category", "unspent_inr", "benefits",
                                        "top_cause", "avg_util"])

    # 2. Raw score: unspent value routed through the affinity map
    raw = {m: 0.0 for m in face}
    contrib = {m: [] for m in face}
    for _, r in unspent.iterrows():
        weights = MODULE_AFFINITY.get(r["category"], {})
        for m, w in weights.items():
            if m in raw:
                v = float(r["unspent_inr"]) * w
                raw[m] += v
                contrib[m].append((r["category"], v))

    # 3. Behaviour multipliers
    mult, why = behaviour_multipliers(member)

    rows = []
    for m in face:
        scored = raw[m] * mult.get(m, 1.0)
        # Honest cap: a module cannot re-home more value than its own face value
        addressed = min(scored, float(face[m]))
        drivers = sorted(contrib[m], key=lambda t: -t[1])[:2]
        rows.append({
            "module_id": m,
            "module": names[m],
            "status": status[m],
            "face_value_inr": int(face[m]),
            "unspent_matched_inr": int(round(scored)),
            "addressable_inr": int(round(addressed)),
            "coverage_pct": round(100 * addressed / face[m], 1) if face[m] else 0.0,
            "driver_categories": ", ".join(c for c, _ in drivers) if drivers else "—",
            "behaviour_signal": "; ".join(why.get(m, [])) or "no distinguishing signal",
        })

    # Rank on the UNCAPPED match. Ranking on the capped figure makes every
    # module tie at 100% for a high-gap member and destroys the ordering.
    ranked = (pd.DataFrame(rows)
              .sort_values(["unspent_matched_inr", "addressable_inr"],
                           ascending=False)
              .reset_index(drop=True))
    ranked["capped_at_face"] = ranked["unspent_matched_inr"] > ranked["face_value_inr"]

    eligible = ranked["status"].eq("ACTIVE") if active_only else pd.Series(
        True, index=ranked.index)
    call, picked = [], 0
    for i in range(len(ranked)):
        if not eligible.iloc[i]:
            call.append("SWAP CANDIDATE")
        elif picked < top_n:
            call.append("ACTIVATE")
            picked += 1
        else:
            call.append("ALTERNATE")
    ranked["recommendation"] = call

    # ACTIVATE rows first, then ALTERNATE, then the reserve pool
    order = {"ACTIVATE": 0, "ALTERNATE": 1, "SWAP CANDIDATE": 2}
    ranked = (ranked.assign(_o=ranked["recommendation"].map(order))
              .sort_values(["_o", "unspent_matched_inr"], ascending=[True, False])
              .drop(columns="_o").reset_index(drop=True))
    return ranked, unspent, why


# ── GEMINI LAYER (optional) ──────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are an assistant to an American Express Platinum Card relationship manager
in India.

Write a 4-5 sentence briefing for ONE member, covering in order:
  (1) the size and shape of their unused benefit value,
  (2) which spend categories it is stranded in and the dominant root cause,
  (3) which two Layer 3 modules they should activate and why those two,
  (4) what changes for the member once they do.

Rules:
- Use ONLY figures present in the JSON. Never invent, round up, or estimate.
- Name modules exactly as given in the JSON.
- Analytical, professional tone. Plain paragraph, no bullets, no headings.
- Do not say "based on the data" or hedge.
- If the JSON has no gap and no modules, output INSUFFICIENT_DATA.
"""

MODEL_CANDIDATES = [
    os.environ.get("GEMINI_MODEL", "").strip() or None,
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]


def gemini_available(api_key=None):
    key = api_key or os.environ.get("GOOGLE_AI_API_KEY", "")
    if not key:
        return False, "No GOOGLE_AI_API_KEY set"
    try:
        import google.generativeai  # noqa: F401
        return True, "ready"
    except Exception as e:
        return False, f"google-generativeai not installed ({e})"


def call_gemini(payload, api_key=None):
    """Returns (text, model_used) or (None, error_string)."""
    key = api_key or os.environ.get("GOOGLE_AI_API_KEY", "")
    if not key:
        return None, "no api key"
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
    except Exception as e:
        return None, f"sdk error: {e}"

    prompt = (f"{SYSTEM_PROMPT}\n\nMember data:\n"
              f"{json.dumps(payload, indent=2, default=str)}\n\n"
              f"Write the briefing:")

    last_err = "unknown"
    for name in [m for m in MODEL_CANDIDATES if m]:
        try:
            model = genai.GenerativeModel(name)
            resp = model.generate_content(prompt)
            text = (resp.text or "").strip()
            if text and "INSUFFICIENT_DATA" not in text.upper():
                return text, name
            last_err = "model returned empty / INSUFFICIENT_DATA"
        except Exception as e:
            last_err = str(e)
            continue
    return None, last_err


# ── DETERMINISTIC FALLBACK NARRATIVE ─────────────────────────────────────────
CAUSE_ANSWER = {
    "awareness":   "L2.1 Value Ledger, which makes the entitlement visible before it lapses",
    "timing":      "L2.1 Value Ledger alerts plus the L2.2 Progressive Milestone Ladder",
    "friction":    "L2.3 Big-Ticket Digital Advantage, which removes the registration step",
    "irrelevance": "a Layer 3 module swap, since nudging cannot fix a relevance failure",
    "structural":  "no design change — this portion is not addressable",
}


def template_narrative(payload):
    """Same numbers, no API. Reads as an RM note, not a template."""
    p = payload
    picks = p.get("recommended_modules", [])
    cats = p.get("unspent_by_category", [])[:2]
    cause = p.get("dominant_cause", "awareness")

    s1 = (f"{p['customer_id']} is a {p['archetype']} on the {p['spend_tier']} tier "
          f"with {p['tenure_months']} months of tenure, running "
          f"₹{p['annual_spend_inr']:,} of annual spend at "
          f"{p['utilisation_pct']}% benefit utilisation — leaving "
          f"₹{p['total_unspent_inr']:,} of paid-for value unconsumed.")

    if cats:
        cat_txt = " and ".join(
            f"{c['category']} (₹{c['unspent_inr']:,}, mostly {c['top_cause']})"
            for c in cats)
        s2 = (f"The value is stranded mainly in {cat_txt}; across the whole card "
              f"the largest cause by value is {cause}, which the design answers "
              f"with {CAUSE_ANSWER.get(cause, 'a Layer 2 intervention')}.")
    else:
        s2 = "No category-level gap is recorded for this member."

    if picks:
        def _worth(p):
            if p.get("capped_at_face"):
                return (f"absorbs its full ₹{p['face_value_inr']:,} face value "
                        f"(₹{p['unspent_matched_inr']:,} of unspent value matched "
                        f"against it)")
            return (f"absorbs ₹{p['addressable_inr']:,}, {p['coverage_pct']}% of its "
                    f"₹{p['face_value_inr']:,} face value")

        p1 = picks[0]
        s3 = (f"On the pick-2-of-4 activation model, {p1['module']} is the first "
              f"activation: it {_worth(p1)}, driven by {p1['driver_categories']}")
        if len(picks) > 1:
            p2 = picks[1]
            s3 += f", with {p2['module']} second — it {_worth(p2)} on {p2['driver_categories']}"
        sig = p1.get("behaviour_signal", "")
        if sig and sig != "no distinguishing signal":
            s3 += f"; the behavioural read is {sig}"
        s3 += "."
        total = sum(x["addressable_inr"] for x in picks)
        s4 = (f"Activating both converts roughly ₹{total:,} of currently invisible "
              f"entitlement into benefits this member actually touches, without "
              f"moving the ₹20,000 per-card ceiling.")
    else:
        s3 = "No Layer 3 module scores above zero for this member's gap profile."
        s4 = "Hold at Layer 2 and re-test after one Value Ledger cycle."

    return " ".join([s1, s2, s3, s4])


def build_payload(customer_id, member, member_gaps, ranked, unspent,
                  member_nudges=None, top_n=2):
    """The single JSON the LLM (or the template) is allowed to see."""
    total_unspent = int(member_gaps["gap_value"].sum()) if len(member_gaps) else 0
    dominant = "structural"
    if len(member_gaps):
        dominant = (member_gaps.groupby("cause")["gap_value"].sum()
                    .sort_values(ascending=False).index[0])

    picks = []
    if len(ranked):
        act = ranked[ranked["recommendation"] == "ACTIVATE"]
        picks = (act if len(act) else ranked).head(top_n).to_dict("records")
    for p in picks:
        for k in ("face_value_inr", "unspent_matched_inr", "addressable_inr"):
            p[k] = int(p[k])
        p["capped_at_face"] = bool(p.get("capped_at_face", False))

    nudges = []
    if member_nudges is not None and len(member_nudges):
        for _, r in member_nudges.nlargest(3, "net_value_inr").iterrows():
            nudges.append({
                "benefit_id": str(r["benefit_id"]),
                "cause": str(r["cause"]),
                "expected_recovery_inr": int(r["expected_recovery_inr"]),
                "net_value_inr": int(r["net_value_inr"]),
            })

    return {
        "customer_id": str(customer_id),
        "archetype": str(member.get("archetype", "—")),
        "spend_tier": str(member.get("spend_tier", "—")),
        "tenure_months": int(member.get("tenure_months", 0) or 0),
        "annual_spend_inr": int(member.get("annual_spend", 0) or 0),
        "utilisation_pct": float(round(member.get("utilisation_pct", 0) or 0, 1)),
        "total_unspent_inr": total_unspent,
        "dominant_cause": str(dominant),
        "unspent_by_category": [
            {"category": r["category"],
             "unspent_inr": int(r["unspent_inr"]),
             "top_cause": str(r["top_cause"])}
            for _, r in unspent.iterrows()
        ],
        "recommended_modules": picks,
        "top_nudges": nudges,
    }


# ── CACHE ────────────────────────────────────────────────────────────────────
def load_cache(path=CACHE_FILE):
    try:
        df = pd.read_csv(path)
        return dict(zip(df["customer_id"].astype(str), df["text"]))
    except Exception:
        return {}


def save_cache(cache, path=CACHE_FILE):
    try:
        pd.DataFrame({"customer_id": list(cache.keys()),
                      "text": list(cache.values())}).to_csv(path, index=False)
        return True
    except Exception:
        return False


def member_narrative(payload, stored=None, cache=None, api_key=None, use_llm=False):
    """
    Resolution order:
      1. Phase 6 stored diagnosis (llm_diagnoses.csv)
      2. session cache (previously generated live)
      3. live Gemini call, only if use_llm=True and a key exists
      4. deterministic template — always available
    Returns (text, source_label).
    """
    cid = payload["customer_id"]
    if stored:
        return stored, "Phase 6 · stored LLM diagnosis"
    if cache and cid in cache:
        return cache[cid], "Gemini · cached this session"
    if use_llm:
        text, info = call_gemini(payload, api_key=api_key)
        if text:
            if cache is not None:
                cache[cid] = text
                save_cache(cache)
            return text, f"Gemini · {info} (live)"
        return (template_narrative(payload),
                f"Rule-based fallback — Gemini unavailable ({info})")
    return template_narrative(payload), "Rule-based engine (no API call)"
