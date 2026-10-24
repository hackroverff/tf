from __future__ import annotations

import pandas as pd
import streamlit as st

from ..demand import first_alerts
from ..figures import (
    buffer_figure,
    capacity_figure,
    closure_figure,
    demand_alert_figure,
    reforecast_figure,
    scenario_figure,
)
from ..ui import chart_with_download, cr, page_header, raw_table


def render_demand(config, data, analysis) -> None:
    page_header(
        "Demand | Diagnose → Sense → Correct → Translate",
        "Daily QC sensing, weekly rolling reforecast, stock-out correction and BOM-pulp scenarios. GT remains a labelled proxy.",
        f"First Amber on {analysis['avoided']['first_amber']} created {analysis['avoided']['alert_lead_days']:.0f} days of reaction lead; Red confirmed on {analysis['avoided']['first_red']}.",
    )
    alerts = analysis["alerts"]
    dates = first_alerts(alerts, "DP")
    metrics = analysis["forecast_metrics"]
    latency_label = "Unavailable" if pd.isna(metrics["qc_planner_average_latency_days"]) else f"{metrics['qc_planner_average_latency_days']:.1f}d"
    cards = st.columns(4)
    cards[0].metric("First Amber", str(dates["AMBER"].date()) if dates["AMBER"] else "Not triggered", "Headline reaction signal")
    cards[1].metric("First Red", str(dates["RED"].date()) if dates["RED"] else "Not triggered", "Confirmation signal")
    cards[2].metric("Amber lead vs notice", f"{analysis['causal_metrics']['amber_lead_days']:.0f}d", f"Red {analysis['causal_metrics']['red_confirmation_lead_days']:.0f}d")
    cards[3].metric("QC planner latency", latency_label, f"Max {metrics['qc_planner_max_latency_days']}d" if not pd.isna(metrics["qc_planner_average_latency_days"]) else "QC feed missing")
    left, right = st.columns(2)
    with left:
        chart_with_download(
            demand_alert_figure(alerts, pd.Timestamp(config.assumption("A007")), data.get("event_calendar")),
            "demand_reaction_timeline", "demand_reaction_timeline.png",
        )
    with right:
        chart_with_download(reforecast_figure(analysis["reforecast"]), "weekly_reforecast", "weekly_reforecast.png")
    st.caption("Baselines are shifted one day and begin after the first active launch sales day. No alert is fabricated when thresholds do not fire.")

    with st.expander("Synthetic error footnote and censoring back-test"):
        st.caption(
            f"Footnote only: monthly flavor×depot WAPE is {metrics['forecast_wape']:.2%}; synthetic weekly reforecast WAPE is {analysis['reforecast_wape']:.2%}. "
            "These are synthetic error diagnostics, not a forecast-improvement or live-benefit claim. The operating claim is reaction lag: Amber versus planner notice."
        )
        c = analysis["censoring_metrics"]
        st.write(f"Stocked-out-row absolute error reduction: **{c['absolute_error_reduction_pct']:.1f}%**. Ground truth is used only for this synthetic back-test, never as an operational feature.")
        methods = analysis["corrected"].groupby(["censoring_method", "censoring_confidence"], as_index=False).agg(
            rows=("date", "size"), estimated_lost=("estimated_lost_demand_bottles", "sum")
        )
        raw_table(methods)
        raw_table(analysis["forecast_by_flavor"])

    with st.expander("Launch-readiness gate and raw BOM cover"):
        status = analysis["launch_status"]
        if status == "BLOCKED":
            st.error(f"**{status}** — DP launch cannot pass every BOM-pulp cover gate.")
        else:
            st.success(f"**{status}** — every BOM pulp passes.")
        raw_table(analysis["launch_gate"])

    with st.expander("Demand scenarios → bottles → frozen pulp"):
        chart_with_download(scenario_figure(analysis["bottle_scenarios"]), "demand_bottle_scenarios", "demand_bottle_scenarios.png")
        st.caption("BASE / VIRAL_2X / VIRAL_4X apply the multiplier to DP QC only. GT/MT receive 50% of the uplift above baseline (assumption). Ranges widen on degraded feeds.")
        raw_table(analysis["bottle_scenarios"], 360)
        raw_table(analysis["pulp_scenarios"], 360)
    with st.expander("Demand assumptions"):
        st.write("No GT outlet-level data are used. Distributor orders and QC spillover are proxies. The initial ramp and planner notice are editable in the sidebar; the 4× peak remains restricted to DP QC.")


def render_supply(config, data, analysis) -> None:
    page_header(
        "Supply | Exposure → Capacity → Buffer → Allocation",
        "Pulp, route and supplier constraints are solved separately from plant capacity. Allocation remains a COO decision.",
        f"+{analysis['best_buffer']['buffer_weeks']:.0f} weeks is the minimum-cost frozen-pulp option after expected air premium; co-packer output is jointly pulp-feasible.",
    )
    metrics = analysis["causal_metrics"]
    best = analysis["best_buffer"]
    cards = st.columns(4)
    cards[0].metric("Passion revenue exposure", "₹161.28 cr", "2.688 cr bottles | PP + DP")
    cards[1].metric("Demand-weighted cover", f"{metrics['closure_demand_weighted_cover_weeks']:.2f} wks", f"Old mix {metrics['closure_old_mix_cover_weeks']:.2f} wks")
    cards[2].metric("Buffer recommendation", f"+{best['buffer_weeks']:.0f} weeks", best["recommended_strategy"].replace("_", " "))
    cards[3].metric("Break-even probability", f"{best['break_even_closure_probability']:.2%}", f"Scenario p={float(config.case['passion_closure_probability']):.0%}")
    left, right = st.columns(2)
    with left:
        chart_with_download(closure_figure(analysis["closure_scenarios"]), "closure_duration_comparison", "closure_duration_comparison.png")
    with right:
        chart_with_download(buffer_figure(analysis["buffer_table"], best), "buffer_optimisation", "buffer_optimisation.png")
    st.info(
        f"**Air-only:** {cr(best['air_only_expected_total_cost_cr'], 4)} expected premium. **Selected buffer:** {cr(best['expected_total_cost_cr'], 4)} expected annual cost; "
        f"recommendation margin {cr(best['recommendation_margin_cr'], 4)}. Working capital {cr(best['buffer_working_capital_cr'], 4)} is separate from the ≤₹2.5 cr program budget."
    )
    if best["low_probability_caveat"]:
        st.warning("Low-probability caveat: scenario closure probability is below the option's break-even probability; do not pre-buy without COO review.")
    if best["small_margin_caveat"]:
        st.warning("Small-margin caveat: the recommendation is within ₹0.10 cr of an alternative or has less than ₹0.10 cr net expected benefit. Treat the ranking as unstable.")

    with st.expander("0–4 week options, 1/2/3-week closures and air-only comparison"):
        raw_table(analysis["buffer_table"], 300)
        raw_table(analysis["closure_scenarios"], 240)
        raw_table(pd.DataFrame([analysis["air_only"]]), 120)
        raw_table(analysis["supply_options"], 240)
        st.caption("The buffer objective conservatively includes expected contribution loss and expected air premium for residual shortage. Air-only is a separate strategy assuming all shortage can be air-freighted in time; normal pulp cost is common and excluded from incremental comparison.")

    with st.expander("Joint bottle + pulp weekly capacity plan", expanded=True):
        chart_with_download(capacity_figure(analysis["capacity_plan"]), "joint_capacity_plan", "joint_capacity_plan.png")
        viral = analysis["capacity_plan"][analysis["capacity_plan"]["scenario"] == "VIRAL_4X"]
        st.write(
            f"4× co-packer output: **{viral['copacker_used_bottles'].sum():,.0f} bottles**. "
            f"Would-be co-packer volume blocked by pulp: **{viral['pulp_limited_copacker_bottles'].sum():,.0f} bottles**. "
            f"Unmet scenario demand: **{viral['unmet_bottles'].sum():,.0f} bottles**."
        )
        st.caption("Opening pulp only; no unconfirmed inbound is credited. In-house draws pulp first and closing balances carry forward. 90-day bottled life − 60-day MT/QC minimum = 30-day maximum MT/QC prebuild.")
        raw_table(analysis["capacity_plan"], 360)

    with st.expander("Pulp-by-pulp exposure and shortage allocation"):
        exposure_columns = [
            "pulp_id", "single_source_flag", "single_route_flag", "summer_closure_probability", "lead_time_days",
            "current_cover_weeks", "baseline_cover_weeks", "dependent_flavors", "dependent_revenue_cr", "risk_flag",
        ]
        raw_table(analysis["exposure"][exposure_columns], 280)
        st.subheader(f"Shortage allocation — {analysis['allocation_date'].date()} | {analysis['available_passion_kg']:,.0f} kg")
        raw_table(analysis["allocation"], 260)
        st.error("HUMAN DECISION REQUIRED: contribution/kg, delisting risk and rival threat conflict. No allocation option is auto-selected or executed; peak trade-offs require COO.")
    with st.expander("Supply assumptions"):
        st.write("Annual closure probability and 1/2/3-week conditional weights are assumptions. Frozen pulp is the structural buffer; bottled prebuild is capped by channel shelf-life rules. GT has no case-stated cutoff and remains configurable.")
