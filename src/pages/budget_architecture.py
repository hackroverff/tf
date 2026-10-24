from __future__ import annotations

import plotly.express as px
import streamlit as st

from ..figures import impact_figure
from ..quality import data_model_links, feed_fallback_assessment
from ..ui import ACCENT, NAVY, STATUS_COLORS, chart_with_download, cr, page_header, raw_table, style_figure


def render_budget(config, data, analysis) -> None:
    page_header(
        "Budget & Impact | ≤₹2.5 cr first-year package",
        "Build, run, contingency, optional working capital and negative-ROI co-packing remain separate.",
        f"The selected package costs {cr(analysis['budget_summary']['total_cost_cr'])} and preserves {cr(analysis['budget_summary']['headroom_cr'])} of cap headroom.",
    )
    summary = analysis["budget_summary"]
    cards = st.columns(4)
    cards[0].metric("Selected year-1 budget", cr(summary["total_cost_cr"]), f"Cap {cr(summary['budget_cap_cr'])}")
    cards[1].metric("Cap headroom", cr(summary["headroom_cr"]))
    cards[2].metric("One-time build", cr(summary["one_time_build_cr"]))
    cards[3].metric("Run + contingency", cr(summary["year1_run_cr"]))
    st.progress(min(1.0, summary["total_cost_cr"] / summary["budget_cap_cr"]), text=f"Budget utilisation: {summary['total_cost_cr'] / summary['budget_cap_cr']:.1%} of ₹2.50 cr cap")
    budget = analysis["budget"]
    selected = budget[budget["selected"] == 1].sort_values("selected_cost_cr")
    left, right = st.columns(2)
    with left:
        fig = px.bar(
            selected, x="selected_cost_cr", y="line_item", orientation="h", color="cost_type",
            labels={"selected_cost_cr": "Selected cost (₹ cr)", "line_item": "", "cost_type": "Cost type"},
            color_discrete_sequence=[ACCENT, NAVY, "#7D9C9D"],
        )
        chart_with_download(style_figure(fig, 450, "Selected first-year line items"), "budget_line_items", "budget_line_items.png")
    with right:
        chart_with_download(impact_figure(analysis["budget_impact"]), "budget_impact", "budget_impact.png")
    st.caption("Payback is simple and undiscounted. Benefits are assumption-based, not simulated; optional supply benefits are not stacked onto the top-down range.")
    st.warning(f"Excluded: co-packer retainer {cr(summary['optional_copacker_cost_cr'])} and optional buffer principal {cr(analysis['best_buffer']['buffer_working_capital_cr'], 3)}. Hidden selected working capital = ₹0; buffer principal requires COO approval.")
    with st.expander("Budget table, LOW/BASE/HIGH impact and payback"):
        raw_table(budget, 330)
        raw_table(analysis["budget_impact"], 180)
    with st.expander("Eight-month roadmap and planner adoption"):
        raw_table(config.tables["roadmap"], 300)
        st.write("**Excel-first:** import/export every table and retain a weekly depot workbook. **Ownership:** one owner per alert with planner challenge rights. **Rollout:** read-only parallel run, fallback drills, vendor hypercare and weekly peak S&OP for 15 planners.")
    with st.expander("Budget assumptions"):
        st.write("Vendor-run IT, no internal data/AI hire, fixed plant capacity and no new mid-season line. Working capital is recoverable but separately approved; it is not hidden inside the selected package.")


def render_architecture(config, data, analysis) -> None:
    checks = data.get("reconciliation_checks")
    reconciliation_takeaway = (
        f"{checks['status'].eq('PASS').sum()}/{len(checks)} active-scenario generator checks pass"
        if checks is not None else "Active-scenario reconciliation is unavailable"
    )
    page_header(
        "Architecture & Data Quality | Resilience and scale",
        "Python 3.11, local CSVs, fixed seed, config-driven entities and explicit degradation paths.",
        f"{reconciliation_takeaway}; degraded feeds widen uncertainty and suppress transfers from unknown stock.",
    )
    quality = analysis["quality_checks"]
    counts = quality["status"].value_counts()
    cards = st.columns(4)
    cards[0].metric("Quality gates", len(quality))
    cards[1].metric("Pass", int(counts.get("PASS", 0)))
    cards[2].metric("Warnings", int(counts.get("WARN", 0)))
    cards[3].metric("Failures", int(counts.get("FAIL", 0)))
    status = counts.rename_axis("status").reset_index(name="checks")
    fig = px.bar(status, x="status", y="checks", color="status", text="checks", color_discrete_map=STATUS_COLORS, labels={"checks": "Automated checks", "status": ""})
    fig.update_layout(showlegend=False)
    chart_with_download(style_figure(fig, 320, "Data-quality gate status"), "data_quality_status", "data_quality_status.png")
    with st.expander("Quality-gate detail and 63-check generator reconciliation"):
        raw_table(quality, 340)
        checks = data.get("reconciliation_checks")
        if checks is not None:
            raw_table(checks, 360)
            st.caption(f"{checks['status'].eq('PASS').sum()} / {len(checks)} generator checks pass. Includes production→depot→sales conservation and write-off calibration arithmetic.")

    with st.expander("Graceful-fallback simulator"):
        left, right = st.columns(2)
        qc_available = left.checkbox("QC daily feed available", value=True)
        depot_available = right.checkbox("Latest depot workbook available", value=True)
        fallback, uncertainty = feed_fallback_assessment(qc_available, depot_available, config)
        st.markdown(f"**Scenario LOW/HIGH half-width:** ±{uncertainty:.0f}% (fresh ±20%; degraded ±40%)")
        raw_table(fallback, 220)
        if not qc_available or not depot_available:
            st.warning("Missing QC disables the detector; unknown depot stock cannot originate transfers. Stale/proxy labels and owner actions remain visible.")

    with st.expander("Shared data model and config-scaling evidence"):
        raw_table(data_model_links(), 260)
        st.write(f"Entities: **{len(config.tables['flavors'])} flavors · {len(config.tables['depots'])} depots · {config.tables['depots']['region'].nunique()} regions · {len(config.tables['channels'])} channels · {len(config.tables['pulps'])} pulps**.")
        st.success("Scaling tests add a flavor, depot and channel through config—including last-year mix and shelf-life rows—and regenerate the same reconciled 9.6 cr total without entity-specific code.")
        raw_table(analysis["depot_mismatch"], 320)

    with st.expander("Deployment and operating constraints"):
        st.write("**Laptop/open source:** Python 3.11, pandas, numpy, scipy, Plotly, Streamlit, openpyxl. **Vendor-run IT:** managed QC/Excel ingestion and small runtime for 15 planners. **No external APIs:** weather is a manual scenario input. **Excel:** one workbook contains raw data, config, model outputs, checks and approvals.")
        st.caption(f"{config.case['case_name']} | Currency {config.case['currency']} | Fixed seed 42 | No external service dependency")
