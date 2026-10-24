"""Explainable risk register and human-only approval workflow."""
from __future__ import annotations

from typing import Literal

import pandas as pd

from .config import AppConfig


Decision = Literal["APPROVE", "REJECT", "MODIFY"]


def build_risk_register(
    config: AppConfig,
    causal_metrics: dict[str, float | str],
    attribution: pd.DataFrame,
    launch_status: str,
    copacker_expected_benefit_cr: float = 0.0,
) -> pd.DataFrame:
    """Create risks with explanation, value, action, owner and escalation.

    Values can overlap across risks; ``value_overlap_group`` prevents a UI from
    presenting their sum as incremental benefit.
    """
    impact = attribution.set_index("root_cause_id")
    notice = pd.Timestamp(config.assumption("A007"))
    try:
        red_date = pd.Timestamp(str(causal_metrics["first_red_date"]))
    except (ValueError, TypeError):
        try:
            red_date = pd.Timestamp(str(causal_metrics["first_amber_date"]))
        except (ValueError, TypeError):
            red_date = config.viral_start

    def values(cause: str) -> tuple[float, float, float]:
        row = impact.loc[cause]
        return float(row["low_economic_impact_cr"]), float(row["economic_impact_cr"]), float(row["high_economic_impact_cr"])

    alert_available = str(causal_metrics["first_red_date"]) != "Not triggered" or str(causal_metrics["first_amber_date"]) != "Not triggered"
    rows = []

    def add(risk_id: str, area: str, title: str, what: str, why: str, severity: str,
            value: tuple[float, float, float], action: str, owner: str, approver: str,
            deadline: pd.Timestamp, overlap: str) -> None:
        low, base, high = value
        rows.append({
            "risk_id": risk_id,
            "area": area,
            "title": title,
            "what_fired": what,
            "why_fired": why,
            "severity": severity,
            "amount_low_cr": low,
            "amount_base_cr": base,
            "amount_high_cr": high,
            "recommended_action": action,
            "owner_role": owner,
            "approver_role": approver,
            "required_approver_role": approver,
            "peak_season_tradeoff": risk_id in {"R002", "R003", "R004", "R005", "R006"},
            "approval_chain": "Planner → S&OP Lead → COO (COO required for this peak trade-off)" if risk_id in {"R002", "R003", "R004", "R005", "R006"} else "Planner → S&OP Lead",
            "deadline": deadline,
            "status": "PROPOSED",
            "execution_status": "NOT_EXECUTED_HUMAN_DECISION_ONLY",
            "value_overlap_group": overlap,
        })

    add(
        "R001", "DEMAND", "Viral QC spike detected before planner notice",
        f"DP QC Red on {causal_metrics['first_red_date']}; planners noticed {causal_metrics['planner_notice_date']}" if alert_available else "No DP QC alert fired; feed is missing or thresholds did not trigger",
        f"Daily marketing signal reached planners after month-end; sensing lead={causal_metrics['sensing_lead_days']:.0f} days; stock-outs also censor sales",
        "RED" if alert_available else "AMBER", values("LATE_SENSING"),
        "Assign one demand-planner owner; ingest QC daily; reforecast bottles and BOM pulp weekly; log GT proxy uncertainty" if alert_available else "Restore QC feed, label proxy-only demand and widen uncertainty; do not claim an early alert",
        "Demand Planner", "S&OP Lead", red_date + pd.Timedelta(days=int(config.number("A066"))), "LATE_SENSING",
    )
    add(
        "R002", "DEMAND + SUPPLY", "Dragon Passion launch-readiness gate",
        f"Launch gate={launch_status}; imported dragonfruit lead=49d; notice=14d",
        f"Notice-to-lead gap={causal_metrics['launch_lead_gap_days']:.0f}d; every BOM pulp must cover lead time + buffer before release",
        "RED" if launch_status == "BLOCKED" else "GREEN", values("LAUNCH_HANDOFF"),
        "Hold launch release until imported-pulp cover meets 56d gate; agree marketing/procurement handoff SLA and qualify backup pulp",
        "Launch Planner + Procurement", "COO", config.launch_date, "LAUNCH_HANDOFF",
    )
    add(
        "R003", "SUPPLY + TRANSPORT", "Single-source passionfruit on fragile highway",
        f"One qualified supplier and one road; 60% annual closure likelihood; cover {causal_metrics['closure_old_mix_cover_weeks']:.2f}→{causal_metrics['closure_demand_weighted_cover_weeks']:.2f} weeks on current demand",
        "Viral demand consumes usable cover before the 21-day closure; emergency air is 5× normal cost",
        "RED", values("ROUTE_SINGLE_SOURCE"),
        "COO to approve frozen buffer and alternate-supplier qualification; arm cover-below-lead+buffer and route triggers before peak",
        "Procurement Lead + Supply Planner", "COO", config.closure_start - pd.Timedelta(days=int(config.number("A027"))), "ROUTE_SINGLE_SOURCE",
    )
    add(
        "R004", "INVENTORY + DISTRIBUTION", "Depot allocation uses stale mix",
        "Overstock and short depot profiles coexist; weekly sheets use last-year mix and 21-day cover",
        "Current demand mix differs after viral launch; transfers take 2–4 days and cost ₹1.50/bottle",
        "RED", values("STALE_DEPOT_MIX"),
        "Upload depot sheets weekly; rank current-mix cover; approve only transfers with positive contribution after ₹1.50/bottle cost",
        "Depot Planner", "COO", notice + pd.Timedelta(days=int(config.case["transfer_min_days"])), "STALE_DEPOT_MIX",
    )
    add(
        "R005", "SUPPLY", "Co-packer decision has a two-week clock",
        "In-house summer utilisation is 95%; only 5% headroom remains and no mid-season line can be added",
        "Co-packer adds at most 10%, costs +25%, and cannot solve a pulp shortage; notice must precede eligible volume by 14 days",
        "AMBER", (0.0, float(copacker_expected_benefit_cr), float(copacker_expected_benefit_cr)),
        "Issue conditional notice only when the weekly plan shows capacity unmet after pulp is secured; S&OP must compare premium with contribution",
        "Supply Planner", "COO", red_date, "CAPACITY_ONLY_NO_ROUTE_OVERLAP",
    )
    add(
        "R006", "INVENTORY", "Buffer must not violate MT/QC shelf-life rule",
        "Bottled juice has 90-day life but MT/QC require 60 days remaining; only 30 days of MT/QC prebuild is permissible",
        "Finished-goods prebuild cannot carry structural summer buffer and can worsen write-offs; frozen pulp lasts six months",
        "AMBER", values("STALE_DEPOT_MIX"),
        "Hold approved structural buffer in frozen pulp; cap MT/QC prebuild at 30 days and show shelf-life exceptions in weekly S&OP",
        "Inventory Planner", "COO", config.summer_start, "STALE_DEPOT_MIX",
    )
    return pd.DataFrame(rows).sort_values("risk_id").reset_index(drop=True)


def empty_approval_log() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "log_id", "risk_id", "decision", "previous_status", "new_status", "actor_role",
        "approver_role", "owner_role", "action", "comment", "modified_action", "timestamp",
        "peak_season_tradeoff", "execution_status",
    ])


def apply_decision(
    risks: pd.DataFrame,
    log: pd.DataFrame | None,
    risk_id: str,
    decision: Decision,
    actor_role: str,
    comment: str = "",
    modified_action: str | None = None,
    timestamp: str | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return updated copies; never executes a supply/demand transaction."""
    if decision not in {"APPROVE", "REJECT", "MODIFY"}:
        raise ValueError("Decision must be APPROVE, REJECT or MODIFY")
    if not actor_role.strip():
        raise ValueError("Actor/approver role is required")
    if actor_role not in {"Planner", "S&OP Lead", "COO"}:
        raise ValueError("Role must be Planner, S&OP Lead or COO")
    if decision == "MODIFY" and not (modified_action and modified_action.strip()):
        raise ValueError("MODIFY requires replacement action text")
    updated = risks.copy()
    matches = updated.index[updated["risk_id"] == risk_id]
    if len(matches) != 1:
        raise KeyError(f"Unknown or duplicate risk {risk_id}")
    idx = matches[0]
    previous = str(updated.at[idx, "status"])
    required_approver = str(updated.at[idx, "approver_role"]) if "approver_role" in updated else ""
    peak_tradeoff = bool(updated.at[idx, "peak_season_tradeoff"]) if "peak_season_tradeoff" in updated else False
    if decision == "APPROVE" and required_approver and actor_role != required_approver:
        raise ValueError(f"{risk_id} requires approval by {required_approver}")
    if decision == "APPROVE" and peak_tradeoff and actor_role != "COO":
        raise ValueError(f"{risk_id} is a peak-season trade-off and requires COO approval")
    new_status = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "MODIFY": "PROPOSED_MODIFIED"}[decision]
    if decision == "MODIFY":
        updated.at[idx, "recommended_action"] = modified_action.strip()
    updated.at[idx, "status"] = new_status
    updated.at[idx, "execution_status"] = "NOT_EXECUTED_HUMAN_DECISION_ONLY"
    entry = {
        "log_id": 1 if log is None or log.empty else int(log["log_id"].max()) + 1,
        "risk_id": risk_id,
        "decision": decision,
        "previous_status": previous,
        "new_status": new_status,
        "actor_role": actor_role,
        "approver_role": actor_role if decision == "APPROVE" else required_approver,
        "owner_role": str(updated.at[idx, "owner_role"]) if "owner_role" in updated else "Planner",
        "action": str(updated.at[idx, "recommended_action"]),
        "comment": comment.strip(),
        "modified_action": modified_action.strip() if modified_action else "",
        "timestamp": pd.Timestamp(timestamp) if timestamp is not None else pd.Timestamp.now(),
        "peak_season_tradeoff": peak_tradeoff,
        "execution_status": "NOT_EXECUTED_HUMAN_DECISION_ONLY",
    }
    updated_log = empty_approval_log() if log is None else log.copy()
    entry_frame = pd.DataFrame([entry])
    updated_log = entry_frame if updated_log.empty else pd.concat([updated_log, entry_frame], ignore_index=True)
    return updated, updated_log


def approval_summary(risks: pd.DataFrame) -> dict[str, int]:
    counts = risks["status"].value_counts()
    return {
        "proposed": int(counts.get("PROPOSED", 0) + counts.get("PROPOSED_MODIFIED", 0)),
        "approved": int(counts.get("APPROVED", 0)),
        "rejected": int(counts.get("REJECTED", 0)),
        "executed": 0,
    }
