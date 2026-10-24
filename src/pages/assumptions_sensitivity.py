from __future__ import annotations

import pandas as pd
import streamlit as st

from ..figures import avoided_range_figure, ramp_lead_figure
from ..ui import chart_with_download, page_header, raw_table


def render_assumptions_sensitivity(config, data, analysis, ramp: pd.DataFrame, scenario_key: tuple) -> None:
    page_header(
        "Assumptions & Sensitivity | Evidence before confidence",
        "CASE-STATED, DERIVED FROM CASE and MY ASSUMPTION remain separate; case-marked rows await source-text verification.",
        "One-click controls change the live scenario and export; detection lead is recomputed without inventing alerts.",
    )
    initial, notice, root_profile, capture, closure_probability, qc_share = scenario_key
    case_rows = len(config.case) + sum(
        int(frame["source"].eq("CASE-STATED").sum()) for frame in config.tables.values() if "source" in frame
    )
    cards = st.columns(4)
    cards[0].metric("Initial DP QC ramp", f"{initial:.1f}×", "Editable; 4× peak stays DP QC")
    cards[1].metric("Closure probability", f"{closure_probability:.0%}", f"Buffer break-even {analysis['best_buffer']['break_even_closure_probability']:.2%}")
    cards[2].metric("QC summer share", f"{qc_share:.0%}", "GT/MT resized proportionally")
    cards[3].metric("Case rows verified", "0", f"{case_rows} await original case text")
    st.caption(f"Compiled assumption output: {len(data['assumptions'])} unique rows. Current root-cause profile: {root_profile}; capture multiplier: {capture:.2f}×; planner notice: {notice}.")
    left, right = st.columns(2)
    with left:
        chart_with_download(ramp_lead_figure(ramp), "initial_ramp_lead", "initial_ramp_lead.png")
    with right:
        chart_with_download(avoided_range_figure(analysis["avoided_range"]), "sensitivity_avoided_range", "sensitivity_avoided_range.png")
    st.info("Use the sidebar’s **Scenario & one-click sensitivity** panel to change root-cause split, capture, closure probability, QC share, initial ramp and planner notice. Avoided loss is assumption-based, not simulated; detection sensitivity is a synthetic back-test.")

    with st.expander("Ramp sensitivity raw results and no-alert rows"):
        raw_table(ramp, 240)
        st.caption("Blank Red dates mean Red did not trigger. No alert date or avoided-loss benefit is interpolated through missing alerts.")

    with st.expander("Current scenario settings and buffer result"):
        settings = pd.DataFrame([
            {"input": "Initial DP QC multiplier", "value": initial, "output": f"Amber {analysis['avoided']['first_amber']}; lead {analysis['avoided']['alert_lead_days']:.0f}d"},
            {"input": "Planner notice", "value": notice, "output": f"Red {analysis['avoided']['first_red']}; confirmation {analysis['avoided']['red_confirmation_lead_days']:.0f}d"},
            {"input": "Root-cause profile", "value": root_profile, "output": f"BASE avoided ₹{analysis['avoided']['base_cr']:.6f} cr"},
            {"input": "Capture multiplier", "value": capture, "output": f"Effective BASE capture {analysis['avoided']['base_effective_capture_rate']:.2%}"},
            {"input": "Closure probability", "value": closure_probability, "output": f"+{analysis['best_buffer']['buffer_weeks']:.0f}w; objective ₹{analysis['best_buffer']['expected_total_cost_cr']:.6f} cr"},
            {"input": "QC share", "value": qc_share, "output": "Deterministic channel demand and write-off allocation regenerated"},
        ])
        raw_table(settings, 240)
        raw_table(analysis["buffer_table"], 260)

    with st.expander("Source lineage and case-text verification"):
        st.warning("Original case text has not been supplied. Every case-marked row remains `VERIFIED_AGAINST_CASE_TEXT=N`; paste the original text before any row is marked Y.")
        case_frame = pd.DataFrame({"case_key": list(config.case), "value": list(config.case.values())})
        case_frame["source"] = case_frame["case_key"].map(lambda key: "DERIVED FROM CASE" if key == "annual_bottles" else "CASE-STATED")
        case_frame["VERIFIED_AGAINST_CASE_TEXT"] = "N"
        raw_table(case_frame, 330)
        lineage = []
        for table_name, frame in config.tables.items():
            source_column = next((column for column in ["source", "share_source", "cover_source"] if column in frame), None)
            if source_column is None:
                continue
            id_column = frame.columns[0]
            for row in frame.itertuples():
                lineage.append({
                    "table": table_name,
                    "row": getattr(row, id_column),
                    "source": getattr(row, source_column),
                    "VERIFIED_AGAINST_CASE_TEXT": getattr(row, "VERIFIED_AGAINST_CASE_TEXT", "N"),
                })
        raw_table(pd.DataFrame(lineage), 340)

    with st.expander("Compiled assumptions register"):
        assumptions = data["assumptions"]
        left, right = st.columns(2)
        category = left.selectbox("Category", ["ALL"] + sorted(assumptions["category"].unique()))
        source = right.selectbox("Source", ["ALL"] + sorted(assumptions["source"].unique()))
        visible = assumptions.copy()
        if category != "ALL":
            visible = visible[visible["category"] == category]
        if source != "ALL":
            visible = visible[visible["source"] == source]
        raw_table(visible, 420)
