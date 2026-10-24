"""Mar-Jun side-by-side scenario replay with conservative impact ranges."""
from __future__ import annotations

import pandas as pd

from .config import AppConfig
from .demand import first_alerts
from .links import build_causal_links


def build_scenario_replay(
    config: AppConfig,
    datasets: dict[str, pd.DataFrame],
    corrected_daily: pd.DataFrame,
    alerts: pd.DataFrame,
    attribution: pd.DataFrame,
    best_buffer_weeks: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float | str]]:
    """Return daily replay, action comparison and avoided-loss summary.

    "With model" rows are recommendations requiring approval, not claims that an
    action executed.  Avoided loss comes only from the top-down attribution to
    prevent adding overlapping action-level savings.
    """
    metrics, _ = build_causal_links(datasets, corrected_daily, alerts, config)
    dates = first_alerts(alerts, "DP")
    actual_amber = dates["AMBER"]
    actual_red = dates["RED"]
    amber = actual_amber or actual_red or config.viral_start
    red = actual_red or actual_amber or amber
    actionable = actual_amber or actual_red
    notice = pd.Timestamp(config.assumption("A007"))
    route_warning = pd.Timestamp(config.assumption("A048"))
    model_air = pd.Timestamp(config.assumption("A049"))
    buffer_date = pd.Timestamp(config.assumption("A050"))
    allocation_due = pd.Timestamp(config.assumption("A051"))
    air_actual = pd.Timestamp(config.assumption("A012"))
    air_option = config.tables["supply_options"].set_index("option_id").loc["AIR_TRIGGER"]
    model_air_cost = float(config.case["air_freight_cost_cr"]) * (1.0 - float(air_option["air_cost_reduction"]))

    actions = [
        {
            "date": config.launch_date,
            "area": "LAUNCH",
            "what_actually_happened": "DP launched with two-week procurement notice and no BOM-wide readiness gate",
            "with_the_model": "BLOCK imported-dragonfruit gate until 56d cover; COO/S&OP records launch exception if approved",
            "owner": "Launch Planner + Procurement",
            "approver": "S&OP Lead",
            "value_basis": "35d notice/lead gap; no invented launch-loss precision",
            "decision_status": "HUMAN_REQUIRED",
        },
        {
            "date": amber,
            "area": "DEMAND",
            "what_actually_happened": "QC signal stayed with marketing; no planner action",
            "with_the_model": "First Amber: named demand planner validates stock-outs and starts daily watch" if actual_amber is not None else "No Amber under current data/thresholds; inspect QC feed and detector governance",
            "owner": "Demand Planner",
            "approver": "S&OP Lead",
            "value_basis": f"Amber {amber.date()} vs notice {notice.date()}" if actual_amber is not None else "No alert timestamp; uncertainty widened",
            "decision_status": "RECOMMENDED_NOT_EXECUTED",
        },
        {
            "date": red,
            "area": "DEMAND + SUPPLY",
            "what_actually_happened": f"Planners noticed only on {notice.date()} after distributor shortages",
            "with_the_model": "First Red: translate signal to weekly bottles/pulp; issue conditional co-packer notice (eligible +14d) and prepare allocation options" if actual_red is not None else "No Red under current data/thresholds; do not claim early sensing or issue automatic capacity action",
            "owner": "Demand + Supply Planners",
            "approver": "S&OP Lead",
            "value_basis": f"{(notice - red).days}d earlier sensing; co-packer notice is conditional on pulp availability" if actionable is not None else "No actionable alert; sensing lead is zero/unavailable",
            "decision_status": "HUMAN_REQUIRED",
        },
        {
            "date": buffer_date,
            "area": "INVENTORY",
            "what_actually_happened": "Structural buffer was not actively governed in frozen pulp",
            "with_the_model": f"Review optimiser-selected +{best_buffer_weeks:.0f} week option; pre-position only with separate COO working-capital approval, otherwise enforce alternate-supplier/air triggers",
            "owner": "Inventory Planner + Procurement",
            "approver": "COO",
            "value_basis": "Optional buffer principal is outside the selected ≤₹2.5 cr package; bottled MT/QC prebuild remains capped at 30d",
            "decision_status": "HUMAN_REQUIRED",
        },
        {
            "date": notice,
            "area": "DEMAND",
            "what_actually_happened": "Distributor shortages made the problem visible",
            "with_the_model": "Model alert is already active; compare actual notice with alert audit log" if actionable is not None else "No model alert fired; review missing QC or threshold parameters",
            "owner": "Demand Planner",
            "approver": "S&OP Lead",
            "value_basis": f"Amber lead={(notice - amber).days}d; Red confirmation={(notice - red).days}d",
            "decision_status": "OBSERVATION",
        },
        {
            "date": route_warning,
            "area": "TRANSPORT + SUPPLY",
            "what_actually_happened": "No documented early route/cover trigger",
            "with_the_model": "Manual landslide/weather input accepted as stale-labelled scenario data; S&OP reviews cover and three allocation options",
            "owner": "Supply Planner + Procurement",
            "approver": "COO",
            "value_basis": "ASSUMPTION: manual route input 7d before closure; not a model weather forecast",
            "decision_status": "HUMAN_REQUIRED",
        },
        {
            "date": allocation_due,
            "area": "SHORTAGE ALLOCATION",
            "what_actually_happened": "Punch was cut to protect DP; both still stocked out",
            "with_the_model": "COO selects Protect DP / Protect Punch / Balanced after seeing contribution/kg, delisting risk and rival threat",
            "owner": "Supply Planner",
            "approver": "COO",
            "value_basis": "No automatic winner; allocation value is inside top-down avoided-loss range",
            "decision_status": "HUMAN_REQUIRED",
        },
        {
            "date": config.closure_start,
            "area": "SUPPLY + TRANSPORT",
            "what_actually_happened": "21-day road closure began with about two weeks of old-mix pulp cover",
            "with_the_model": "Begin approved frozen-buffer drawdown; track daily cover and route status; keep capacity and pulp decisions separate",
            "owner": "Supply Planner",
            "approver": "COO",
            "value_basis": f"Cover {metrics['closure_old_mix_cover_weeks']:.2f}→{metrics['closure_demand_weighted_cover_weeks']:.2f} weeks on current demand",
            "decision_status": "HUMAN_REQUIRED",
        },
        {
            "date": model_air,
            "area": "TRANSPORT",
            "what_actually_happened": f"Actual emergency air was not booked until {air_actual.date()} at ₹{float(config.case['air_freight_cost_cr']):.2f} cr",
            "with_the_model": f"Earlier/smaller air fallback can be approved at scenario cost ₹{model_air_cost:.2f} cr if buffer + route triggers breach",
            "owner": "Procurement Lead",
            "approver": "COO",
            "value_basis": "ASSUMPTION: 20% smaller cost via pre-book trigger; not added again to avoided-loss total",
            "decision_status": "HUMAN_REQUIRED",
        },
        {
            "date": air_actual,
            "area": "TRANSPORT",
            "what_actually_happened": "Air freight booked in closure week 2 at 5× normal cost",
            "with_the_model": "Compare actual booking with earlier trigger; audit any remaining emergency premium",
            "owner": "Procurement Lead",
            "approver": "COO",
            "value_basis": f"Actual ₹{float(config.case['air_freight_cost_cr']):.2f} cr; timing difference={(air_actual - model_air).days}d",
            "decision_status": "OBSERVATION",
        },
        {
            "date": config.closure_end,
            "area": "TRANSPORT",
            "what_actually_happened": "Highway reopened after 21 days; road lead time still applied",
            "with_the_model": "Continue cover alerts until first road receipt and depot recovery; do not declare reopening equal to availability",
            "owner": "Supply Planner",
            "approver": "S&OP Lead",
            "value_basis": "3-day road transit after reopening",
            "decision_status": "RECOMMENDED_NOT_EXECUTED",
        },
    ]
    action_frame = pd.DataFrame(actions).sort_values(["date", "area"]).reset_index(drop=True)

    # Daily visual data: actual cover and a transparent static buffer stress-test.
    inventory = datasets["pulp_inventory_daily"]
    passion = inventory[(inventory["pulp_id"] == "PASSION") &
                        (inventory["date"] >= config.summer_start)].copy()
    daily = passion[[
        "date", "baseline_cover_days", "current_cover_days", "opening_kg", "unmet_requirement_kg"
    ]].rename(columns={
        "baseline_cover_days": "actual_old_mix_cover_days",
        "current_cover_days": "actual_production_cover_days",
    })
    daily["actual_old_mix_cover_weeks"] = daily["actual_old_mix_cover_days"] / 7.0
    daily["actual_production_cover_weeks"] = daily["actual_production_cover_days"] / 7.0
    daily["model_static_buffer_cover_weeks"] = daily["actual_production_cover_weeks"] + best_buffer_weeks
    daily["buffer_visual_basis"] = "STATIC_STRESS_TEST_NOT_A_RE_SIMULATED_PHYSICAL_BALANCE"
    dp_alerts = alerts[alerts["flavor_id"] == "DP"][["date", "signal_bottles", "rolling_baseline", "signal_ratio", "alert_status"]]
    daily = daily.merge(dp_alerts, on="date", how="left")
    actual_events = datasets["event_calendar"].groupby("event_date")["event"].apply(" | ".join)
    daily["actual_event"] = daily["date"].map(actual_events).fillna("")
    model_events = action_frame.groupby("date")["with_the_model"].apply(" | ".join)
    daily["model_event_or_recommendation"] = daily["date"].map(model_events).fillna("")

    impact_total = float(attribution["economic_impact_cr"].sum())
    low_avoided = float(attribution["avoided_loss_low_cr"].sum())
    base_avoided = float(attribution["avoided_loss_base_cr"].sum())
    high_avoided = float(attribution["avoided_loss_high_cr"].sum())
    avoided = {
        "low_cr": low_avoided,
        "base_cr": base_avoided,
        "high_cr": high_avoided,
        "economic_impact_cr": impact_total,
        "low_effective_capture_rate": low_avoided / impact_total if impact_total else 0.0,
        "base_effective_capture_rate": base_avoided / impact_total if impact_total else 0.0,
        "high_effective_capture_rate": high_avoided / impact_total if impact_total else 0.0,
        "estimation_basis": "ASSUMPTION-BASED, NOT SIMULATED",
        "first_amber": str(actual_amber.date()) if actual_amber is not None else "Not triggered",
        "first_red": str(actual_red.date()) if actual_red is not None else "Not triggered",
        "planner_notice": str(notice.date()),
        "alert_lead_days": float((notice - actionable).days) if actionable is not None else 0.0,
        "red_confirmation_lead_days": float((notice - actual_red).days) if actual_red is not None else 0.0,
        "air_days_earlier": float((air_actual - model_air).days),
        "copacker_notice_date": str(red.date()),
        "copacker_eligible_date": str((red + pd.Timedelta(days=int(config.case["copacker_notice_days"]))).date()),
        "copacker_notice_days": float(config.case["copacker_notice_days"]),
        "copacker_notice_given": actionable is not None,
        "actual_air_cost_cr": float(config.case["air_freight_cost_cr"]),
        "model_air_scenario_cost_cr": model_air_cost,
        "confidence": "ASSUMPTION-BASED, NOT SIMULATED: top-down case allocation × assumed capture rates; adoption and approvals are required",
        "double_count_rule": "Action savings are not additive; only top-down root-cause capture is used",
    }
    return daily, action_frame, avoided


def replay_as_of(
    replay_daily: pd.DataFrame,
    actions: pd.DataFrame,
    selected_date: str | pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    """Filter visible events without exposing future model knowledge."""
    selected = pd.Timestamp(selected_date)
    visible_actions = actions[actions["date"] <= selected].copy()
    upcoming = actions[actions["date"] > selected].head(3).copy()
    daily = replay_daily[replay_daily["date"] <= selected].copy()
    return {"actions_to_date": visible_actions, "upcoming_actions": upcoming, "daily_to_date": daily}


def replay_reconciliation(
    actions: pd.DataFrame,
    avoided: dict[str, float | str],
    config: AppConfig,
) -> pd.DataFrame:
    rows = []

    def add(name: str, passed: bool, actual: str, expected: str) -> None:
        rows.append({"check_name": name, "actual": actual, "expected": expected, "status": "PASS" if passed else "FAIL"})

    add("Avoided-loss LOW/BASE/HIGH ordering",
        float(avoided["low_cr"]) <= float(avoided["base_cr"]) <= float(avoided["high_cr"]),
        f"{avoided['low_cr']:.2f}/{avoided['base_cr']:.2f}/{avoided['high_cr']:.2f}", "ordered")
    add("Demand alert precedes planner notice", float(avoided["alert_lead_days"]) > 0,
        f"{avoided['alert_lead_days']:.0f}d", ">0d")
    add("Counterfactual air is earlier", float(avoided["air_days_earlier"]) > 0,
        f"{avoided['air_days_earlier']:.0f}d", ">0d")
    add("Co-packer eligibility respects notice",
        (pd.Timestamp(avoided["copacker_eligible_date"]) - pd.Timestamp(avoided["copacker_notice_date"])).days == int(config.case["copacker_notice_days"]),
        f"{avoided['copacker_notice_date']} → {avoided['copacker_eligible_date']}", f"{config.case['copacker_notice_days']}d")
    add("No automatic execution", actions["decision_status"].isin(
        ["HUMAN_REQUIRED", "RECOMMENDED_NOT_EXECUTED", "OBSERVATION"]
    ).all(), ", ".join(actions["decision_status"].unique()), "human/observation only")
    add("Replay actions stay within/after 1 March", actions["date"].min() >= config.summer_start,
        str(actions["date"].min().date()), f">= {config.summer_start.date()}")
    return pd.DataFrame(rows)
