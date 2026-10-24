from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from ..figures import (
    attribution_waterfall,
    avoided_range_figure,
    buffer_figure,
    causal_map_figure,
    depot_cover_heatmap,
    impact_figure,
)
from ..ui import (
    ACCENT,
    NAVY,
    STATUS_COLORS,
    chart_with_download,
    cr,
    millions,
    page_header,
    raw_table,
    render_tile,
    style_figure,
)


def render_control_tower(config, data, analysis, mode: str = "Last summer replay") -> None:
    next_plan = mode == "Next summer plan"
    page_header(
        "Pulp Riot | Summer Control Tower",
        "Five areas, one data model. Traffic lights guide human review; nothing executes automatically.",
        "Next-summer decision: review the 2-week frozen-pulp option and its working-capital gate." if next_plan
        else f"Last-summer replay: first Amber gave {analysis['avoided']['alert_lead_days']:.0f} days of reaction lead; supply and demand failures reinforced each other.",
    )
    daily = data["daily_sales"]
    summer = daily[daily["season"] == "SUMMER"]
    lost_revenue = float(summer["lost_sales_bottles"].sum()) * float(config.case["price_per_bottle"]) / 10_000_000
    best = analysis["best_buffer"]
    cards = st.columns(4)
    if next_plan:
        cards[0].metric("Recommended buffer", f"+{best['buffer_weeks']:.0f} weeks", best["recommended_strategy"].replace("_", " "))
        cards[1].metric("Expected annual cost", cr(best["expected_total_cost_cr"], 3), "Carry + loss + air premium")
        cards[2].metric("BASE avoided loss", cr(analysis["avoided"]["base_cr"]), "Assumption-based, not simulated")
        cards[3].metric("Selected year-1 cost", cr(analysis["budget_summary"]["total_cost_cr"]), f"Cap {cr(analysis['budget_summary']['budget_cap_cr'])}")
    else:
        cards[0].metric("Summer latent demand", f"{int(summer['true_demand_bottles'].sum()) / 10_000_000:.2f} cr bottles", "Realised sales shown separately")
        cards[1].metric("Lost revenue", cr(lost_revenue), "8% stock-out censoring")
        cards[2].metric("Economic impact", cr(analysis["attribution"]["economic_impact_cr"].sum()), "Contribution + air + write-offs")
        cards[3].metric("Amber reaction lead", f"{analysis['avoided']['alert_lead_days']:.0f} days", f"Red confirmation {analysis['avoided']['red_confirmation_lead_days']:.0f} days")
    st.caption("Volume convention: 9.6 cr is latent summer demand; 8.832 cr is realised sales after censoring. Avoided loss is assumption-based, not simulated.")

    tiles = analysis["tiles"]
    columns = st.columns(5)
    for column, (_, tile) in zip(columns, tiles.iterrows()):
        with column:
            render_tile(tile)

    left, right = st.columns(2)
    if next_plan:
        with left:
            chart_with_download(buffer_figure(analysis["buffer_table"], best), "tower_plan_buffer", "control_tower_buffer.png")
        with right:
            chart_with_download(impact_figure(analysis["budget_impact"]), "tower_plan_impact", "control_tower_impact.png")
    else:
        with left:
            flavor = summer.groupby("flavor_id", as_index=False).agg(
                latent=("true_demand_bottles", "sum"), realised=("sales_bottles", "sum")
            )
            plot = flavor.melt(id_vars="flavor_id", value_vars=["latent", "realised"], var_name="measure", value_name="bottles")
            fig = px.bar(
                plot, x="flavor_id", y="bottles", color="measure", barmode="group",
                color_discrete_map={"latent": ACCENT, "realised": NAVY},
                labels={"flavor_id": "Flavor", "bottles": "Summer bottles", "measure": ""},
            )
            chart_with_download(style_figure(fig, 400, "Latent demand vs realised sales"), "tower_demand_sales", "latent_vs_sales.png")
        with right:
            chart_with_download(depot_cover_heatmap(analysis["cover"]), "tower_depot_cover", "depot_cover_heatmap.png")

    with st.expander("Human-review depot transfers and lane economics"):
        transfers = analysis["transfers"]
        if transfers.empty:
            st.success("No positive-net-benefit transfers in the latest complete snapshot.")
        else:
            st.caption("Origins retain 21-day cover. Recovered contribution uses 70% realisation and deducts ₹1.50/bottle. Lane and vehicle feasibility still require review.")
            columns = ["flavor_id", "origin_depot_id", "destination_depot_id", "transfer_bottles", "transit_days", "transfer_cost_cr", "expected_recovered_contribution_cr", "net_expected_benefit_cr", "decision"]
            raw_table(transfers[columns])
            st.metric("Suggested net benefit — not additive to avoided loss", cr(transfers["net_expected_benefit_cr"].sum()))
    with st.expander("Assumptions and raw control-tower tables"):
        st.write("GT has no outlet-level feed. Depot cover uses corrected trailing demand; stale stock cannot originate a transfer. Buffer principal is a separate COO decision.")
        raw_table(analysis["cover"])


def render_what_went_wrong(config, data, analysis) -> None:
    page_header(
        "What Went Wrong | Loss anatomy and avoidable fraction",
        "Case totals are separated from assumed root-cause allocation and capture rates.",
        "₹23.9456 cr economic impact is reconciled; only an assumption-based fraction is potentially avoidable.",
    )
    attribution = analysis["attribution"]
    writeoff = analysis["writeoff_reconciliation"].iloc[0]
    daily = data["daily_sales"]
    summer = daily[daily["season"] == "SUMMER"]
    lost_revenue = float(summer["lost_sales_bottles"].sum()) * float(config.case["price_per_bottle"]) / 10_000_000
    cards = st.columns(4)
    cards[0].metric("Lost revenue — context", cr(lost_revenue), "Not added to contribution")
    cards[1].metric("Economic impact", cr(attribution["economic_impact_cr"].sum()), "₹14.7456 + ₹3.20 + ₹6.00 cr")
    cards[2].metric("Uncalibrated aging value", cr(float(writeoff["uncalibrated_aging_value_cr"]), 4), f"Calibration gap {cr(float(writeoff['calibration_gap_cr']), 4)}")
    cards[3].metric("BASE avoided loss", cr(analysis["avoided"]["base_cr"]), f"{analysis['avoided']['base_effective_capture_rate']:.1%} effective capture")
    left, right = st.columns(2)
    with left:
        chart_with_download(attribution_waterfall(attribution), "loss_waterfall", "loss_attribution_waterfall.png")
    with right:
        chart_with_download(avoided_range_figure(analysis["avoided_range"]), "loss_avoided_range", "avoided_loss_range.png")
    st.warning("Avoided loss = case-total allocation × assumed capture rates. It is **assumption-based, not simulated**, not a confidence interval, and not additive with action-level savings.")
    with st.expander("Root-cause shares, LOW/BASE/HIGH capture rates and evidence"):
        display = attribution[[
            "root_cause", "lost_contribution_cr", "air_freight_cr", "writeoff_discount_cr", "economic_impact_cr",
            "low_capture", "base_capture", "high_capture", "avoided_loss_low_cr", "avoided_loss_base_cr",
            "avoided_loss_high_cr", "evidence", "source", "VERIFIED_AGAINST_CASE_TEXT",
        ]]
        raw_table(display, 360)
    with st.expander("Write-off calibration and FIFO aging evidence"):
        raw_table(analysis["writeoff_reconciliation"])
        raw_table(data["depot_writeoffs"], 360)


def render_links(config, data, analysis) -> None:
    page_header(
        "Causal Link Map | Demand ↔ Supply",
        "Quantified edges explain the two-way failure; edge units remain explicit.",
        "Viral demand consumed pulp resilience; shortages then censored the very sales signal used for planning.",
    )
    metrics = analysis["causal_metrics"]
    cards = st.columns(4)
    cards[0].metric("DP QC viral ramp", "4.0× in 14 days", "DP QC only")
    cards[1].metric("Passion pulp uplift", f"+{metrics['viral4_pulp_requirement_uplift_pct']:.1f}%", "Viral 4× scenario")
    cards[2].metric("Usable cover", f"{metrics['closure_old_mix_cover_weeks']:.2f} → {metrics['closure_demand_weighted_cover_weeks']:.2f} wks", "Old mix → current demand")
    cards[3].metric("Launch lead gap", f"{metrics['launch_lead_gap_days']:.0f} days", f"{metrics['imported_dragonfruit_lead_days']:.0f}d lead vs {metrics['launch_notice_days']:.0f}d notice")
    chart_with_download(causal_map_figure(analysis["causal_edges"]), "causal_link_map", "causal_link_map.png")
    st.caption(f"Demand-side edges are teal; supply-side edges are red. {millions(metrics['stockout_censored_bottles'])} bottles ({metrics['stockout_censoring_share']:.1%}) are censored from realised sales.")
    with st.expander("Quantified edge register and source flags"):
        raw_table(analysis["causal_edges"], 380)
    with st.expander("Assumptions behind the map"):
        st.write("The 4× uplift applies only to DP QC. GT/MT spillover is 50% of the uplift above baseline and is an assumption. Rival shelf-space value is not quantified.")
