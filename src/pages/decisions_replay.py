from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from ..figures import avoided_range_figure, buffer_figure, replay_cover_figure
from ..recommendations import apply_decision, approval_summary, empty_approval_log
from ..replay import replay_as_of
from ..ui import STATUS_COLORS, chart_with_download, cr, page_header, raw_table, style_figure


def _persist_workflow(risks: pd.DataFrame, log: pd.DataFrame) -> None:
    output = Path("outputs")
    output.mkdir(exist_ok=True)
    risks.to_csv(output / "risk_register.csv", index=False)
    log.to_csv(output / "approval_log.csv", index=False)


def _decide(risk_id: str, decision: str, actor: str, comment: str, modified: str | None = None) -> None:
    try:
        risks, log = apply_decision(
            st.session_state.risk_register,
            st.session_state.approval_log,
            risk_id,
            decision,
            actor,
            comment,
            modified,
        )
        st.session_state.risk_register = risks
        st.session_state.approval_log = log
        _persist_workflow(risks, log)
        st.session_state.workflow_message = f"{risk_id}: {decision} recorded. No transaction executed."
    except (ValueError, KeyError) as error:
        st.session_state.workflow_message = f"Decision not recorded: {error}"


def render_recommendations(config, data, analysis) -> None:
    page_header(
        "Recommendations | Human decisions and approval evidence",
        "Every recommendation has a value range, owner, deadline and explicit approver. Approval never executes a transaction.",
        "Planner → S&OP Lead → COO: COO approval is mandatory for peak-season trade-offs; execution remains zero.",
    )
    if "risk_register" not in st.session_state:
        st.session_state.risk_register = analysis["risks"].copy()
    if "approval_log" not in st.session_state:
        st.session_state.approval_log = empty_approval_log()
    if st.session_state.get("workflow_message"):
        st.info(st.session_state.pop("workflow_message"))
    risks = st.session_state.risk_register
    summary = approval_summary(risks)
    cards = st.columns(4)
    cards[0].metric("Proposed / modified", summary["proposed"])
    cards[1].metric("Approved", summary["approved"])
    cards[2].metric("Rejected", summary["rejected"])
    cards[3].metric("Executed", summary["executed"], "Always zero")
    status_counts = risks["status"].value_counts().rename_axis("status").reset_index(name="risks")
    fig = px.bar(
        status_counts, x="status", y="risks", color="status", text="risks",
        color_discrete_map={"PROPOSED": STATUS_COLORS["AMBER"], "PROPOSED_MODIFIED": STATUS_COLORS["AMBER"], "APPROVED": STATUS_COLORS["GREEN"], "REJECTED": STATUS_COLORS["RED"]},
        labels={"risks": "Risk recommendations", "status": ""},
    )
    fig.update_layout(showlegend=False)
    chart_with_download(style_figure(fig, 330, "Approval status | decisions only, no execution"), "approval_status", "approval_status.png")
    st.caption("₹ values overlap by root-cause group; never sum risk-card values. A modification is a new proposal, not an approval.")

    for risk in risks.itertuples():
        peak = bool(getattr(risk, "peak_season_tradeoff", False))
        with st.expander(f"{risk.risk_id} | {risk.severity} | {risk.title} | {cr(risk.amount_base_cr)} at stake", expanded=risk.severity == "RED"):
            if peak:
                st.warning("PEAK-SEASON TRADE-OFF — COO approval required")
            st.write(f"**What fired:** {risk.what_fired}")
            st.write(f"**Why:** {risk.why_fired}")
            values = st.columns(4)
            values[0].markdown(f"**LOW**  \n{cr(risk.amount_low_cr)}")
            values[1].markdown(f"**BASE**  \n{cr(risk.amount_base_cr)}")
            values[2].markdown(f"**HIGH**  \n{cr(risk.amount_high_cr)}")
            values[3].markdown(f"**STATUS**  \n{risk.status}")
            st.write(f"**Owner:** {risk.owner_role}  |  **Required approver:** {risk.approver_role}  |  **Deadline:** {pd.Timestamp(risk.deadline).date()}")
            st.caption(f"{risk.approval_chain}. Overlap group: {risk.value_overlap_group}. Execution: {risk.execution_status}")
            action = st.text_area("Current / modified recommended action", value=risk.recommended_action, key=f"action_{risk.risk_id}", height=90)
            comment = st.text_input("Decision comment", key=f"comment_{risk.risk_id}")
            roles = ["Planner", "S&OP Lead", "COO"]
            actor = st.selectbox(
                "Role recording the decision", roles,
                index=roles.index(risk.approver_role) if risk.approver_role in roles else 0,
                key=f"actor_{risk.risk_id}",
            )
            buttons = st.columns(3)
            buttons[0].button("APPROVE", key=f"approve_{risk.risk_id}", type="primary", on_click=_decide, args=(risk.risk_id, "APPROVE", actor, comment))
            buttons[1].button("REJECT", key=f"reject_{risk.risk_id}", on_click=_decide, args=(risk.risk_id, "REJECT", actor, comment))
            buttons[2].button("MODIFY", key=f"modify_{risk.risk_id}", on_click=_decide, args=(risk.risk_id, "MODIFY", actor, comment, action))

    with st.expander("Approval audit log | approver, action and timestamp"):
        log = st.session_state.approval_log
        if log.empty:
            st.info("No decisions recorded yet. Every risk remains proposed and unexecuted.")
        else:
            raw_table(log.sort_values("log_id", ascending=False), 360)
        st.caption("Session decisions are also written to outputs/risk_register.csv and outputs/approval_log.csv. No purchase, production, launch or transfer is executed.")


def render_replay(config, data, analysis, mode: str = "Last summer replay") -> None:
    next_plan = mode == "Next summer plan"
    page_header(
        "Scenario Replay | What happened vs with the model" if not next_plan else "Next Summer Plan | Approval-ready action checklist",
        "Counterfactual actions remain recommendations; avoided loss is assumption-based, not simulated.",
        "Use the timeline to limit past knowledge and compare actual events with recommendations." if not next_plan
        else "Convert replay lessons into a human-approved checklist; last-summer dates are not presented as next-year commitments.",
    )
    avoided = analysis["avoided"]
    cards = st.columns(4)
    cards[0].metric("First Amber", avoided["first_amber"])
    cards[1].metric("First Red", avoided["first_red"], f"{avoided['red_confirmation_lead_days']:.0f}d confirmation lead")
    cards[2].metric("Amber reaction lead", f"{avoided['alert_lead_days']:.0f}d", f"Planner notice {avoided['planner_notice']}")
    cards[3].metric("Air timing", f"{avoided['air_days_earlier']:.0f}d earlier", "Counterfactual trigger")

    if next_plan:
        st.subheader("Action checklist — no automatic execution")
        plan = analysis["replay_actions"][["area", "with_the_model", "owner", "approver", "decision_status"]].copy()
        plan.columns = ["Area", "Recommended action", "Owner", "Approver", "Status"]
        raw_table(plan, 390)
        left, right = st.columns(2)
        with left:
            chart_with_download(buffer_figure(analysis["buffer_table"], analysis["best_buffer"]), "next_plan_buffer", "next_plan_buffer.png")
        with right:
            chart_with_download(avoided_range_figure(analysis["avoided_range"]), "next_plan_avoided_range", "next_plan_avoided_range.png")
    else:
        selected = st.slider(
            "Timeline — show information available by this date",
            min_value=config.summer_start.to_pydatetime(), max_value=config.summer_end.to_pydatetime(),
            value=config.closure_start.to_pydatetime(), step=pd.Timedelta(days=1).to_pytimedelta(), format="YYYY-MM-DD",
        )
        selected = pd.Timestamp(selected)
        filtered = replay_as_of(analysis["replay_daily"], analysis["replay_actions"], selected)
        actions = filtered["actions_to_date"]
        left, right = st.columns(2)
        with left:
            st.error("WHAT ACTUALLY HAPPENED")
            raw_table(actions[["date", "area", "what_actually_happened"]], 330)
        with right:
            st.success("WITH THE MODEL — RECOMMENDATIONS, NOT EXECUTIONS")
            raw_table(actions[["date", "area", "with_the_model", "approver", "decision_status"]], 330)
        with st.expander("Next three timeline actions — planning visibility only"):
            raw_table(filtered["upcoming_actions"][["date", "area", "with_the_model", "approver"]], 180)
        left, right = st.columns(2)
        with left:
            chart_with_download(replay_cover_figure(analysis["replay_daily"], selected, config.closure_start), "replay_cover", "replay_cover.png")
        with right:
            chart_with_download(avoided_range_figure(analysis["avoided_range"]), "replay_avoided_range", "replay_avoided_range.png")
        st.caption("The buffer line is a static stress-test, not a resimulated physical balance. The 3 May route/weather input is manual; there is no weather API or landslide prediction.")
    st.info(
        f"**Basis:** {avoided['estimation_basis']}. LOW/BASE/HIGH effective capture: "
        f"{avoided['low_effective_capture_rate']:.1%} / {avoided['base_effective_capture_rate']:.1%} / {avoided['high_effective_capture_rate']:.1%}. "
        "Action savings and transfers are not added again. The earlier air scenario uses a 20% cost-reduction assumption."
    )
