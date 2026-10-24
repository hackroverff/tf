"""Quantified two-way causal links and root-cause loss attribution."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import AppConfig
from .demand import build_demand_scenarios, first_alerts
from .supply import passionfruit_requirement_profile
from .utils import CRORE


def build_causal_links(
    datasets: dict[str, pd.DataFrame],
    corrected_daily: pd.DataFrame,
    alerts: pd.DataFrame,
    config: AppConfig,
) -> tuple[dict[str, float | str], pd.DataFrame]:
    """Calculate edge labels from data rather than hard-coding chart text."""
    case = config.case
    dates = first_alerts(alerts, "DP")
    first_actionable = dates["AMBER"] or dates["RED"]
    notice = pd.Timestamp(config.assumption("A007"))
    sensing_lead_days = float((notice - first_actionable).days) if first_actionable is not None else 0.0
    amber_lead_days = float((notice - dates["AMBER"]).days) if dates["AMBER"] is not None else 0.0
    red_confirmation_days = float((notice - dates["RED"]).days) if dates["RED"] is not None else 0.0
    imported_lead = int(config.tables["suppliers"].set_index("pulp_id").loc["DRAGON_IMP", "lead_time_days"])

    inventory = datasets["pulp_inventory_daily"]
    passion = inventory[inventory["pulp_id"] == "PASSION"].set_index("date")
    closure_row = passion.loc[config.closure_start]
    previral_row = passion.loc[config.viral_start - pd.Timedelta(days=1)]
    profile = passionfruit_requirement_profile(
        corrected_daily, config.tables["bom"], config.closure_start,
        int(config.number("A041")),
        float(case["price_per_bottle"]) * float(case["contribution_margin"]),
    )
    old_cover = float(closure_row["opening_kg"] / closure_row["baseline_daily_requirement_kg"] / 7.0)
    demand_cover = float(closure_row["opening_kg"] / profile["daily_pulp_kg"] / 7.0)
    previral_cover = float(previral_row["opening_kg"] / previral_row["baseline_daily_requirement_kg"] / 7.0)

    bottles, pulp = build_demand_scenarios(
        corrected_daily, config.tables["bom"], notice,
        history_days=int(config.number("A041")), gt_mt_spillover=config.number("A034"),
        uncertainty_pct=config.number("A037"), horizon_weeks=int(config.number("A060")),
        week_start_day=config.assumption("A061"),
    )
    first_week = bottles["week_start"].min()
    week_pulp = pulp[(pulp["week_start"] == first_week) & (pulp["pulp_id"] == "PASSION")].set_index("scenario")
    base_pulp = float(week_pulp.loc["BASE", "pulp_requirement_kg"])
    viral_pulp = float(week_pulp.loc["VIRAL_4X", "pulp_requirement_kg"])
    pulp_uplift = viral_pulp / base_pulp - 1.0 if base_pulp else 0.0

    production = datasets["production_daily"]
    closure_production = production[production["date"] >= config.closure_start]
    pp_forced_cut = float((
        closure_production.loc[closure_production["flavor_id"] == "PP", "scheduled_bottles"]
        - closure_production.loc[closure_production["flavor_id"] == "PP", "actual_bottles"]
    ).sum())
    dp_forced_cut = float((
        closure_production.loc[closure_production["flavor_id"] == "DP", "scheduled_bottles"]
        - closure_production.loc[closure_production["flavor_id"] == "DP", "actual_bottles"]
    ).sum())
    daily = datasets["daily_sales"]
    summer = daily[daily["season"] == "SUMMER"]
    pp_lost = float(summer.loc[summer["flavor_id"] == "PP", "lost_sales_bottles"].sum())
    dp_lost = float(summer.loc[summer["flavor_id"] == "DP", "lost_sales_bottles"].sum())
    total_lost = float(summer["lost_sales_bottles"].sum())
    total_demand = float(summer["true_demand_bottles"].sum())
    air = datasets["pulp_inbound"]
    air_cost = float(air.loc[air["mode"] == "Air", "actual_cost_cr"].sum())

    metrics: dict[str, float | str] = {
        "first_amber_date": str(dates["AMBER"].date()) if dates["AMBER"] else "Not triggered",
        "first_red_date": str(dates["RED"].date()) if dates["RED"] else "Not triggered",
        "planner_notice_date": str(notice.date()),
        "sensing_lead_days": sensing_lead_days,
        "amber_lead_days": amber_lead_days,
        "red_confirmation_lead_days": red_confirmation_days,
        "launch_notice_days": float(case["launch_notice_days"]),
        "imported_dragonfruit_lead_days": float(imported_lead),
        "launch_lead_gap_days": float(imported_lead - int(case["launch_notice_days"])),
        "previral_physical_cover_weeks": previral_cover,
        "closure_old_mix_cover_weeks": old_cover,
        "closure_demand_weighted_cover_weeks": demand_cover,
        "cover_erosion_weeks": old_cover - demand_cover,
        "viral4_pulp_requirement_uplift_pct": 100.0 * pulp_uplift,
        "closure_days": float(case["closure_days"]),
        "pp_forced_production_cut_bottles": pp_forced_cut,
        "dp_forced_production_cut_bottles": dp_forced_cut,
        "pp_lost_sales_bottles": pp_lost,
        "dp_lost_sales_bottles": dp_lost,
        "pp_lost_revenue_cr": pp_lost * float(case["price_per_bottle"]) / CRORE,
        "stockout_censored_bottles": total_lost,
        "stockout_censoring_share": total_lost / total_demand,
        "air_freight_cost_cr": air_cost,
        "rival_launch_lag_days": float(config.number("A067")),
    }

    edges = [
        ("Viral reel", "DP QC demand", "DEMAND", "QC multiplier at day 14", 4.0, "4.0× QC demand in 14 days", "CASE"),
        ("DP QC demand", "Daily Amber/Red alert", "DEMAND", "First Amber lead; Red confirmation", metrics["sensing_lead_days"], f"Amber {metrics['first_amber_date']} = {metrics['amber_lead_days']:.0f}d lead; Red {metrics['first_red_date']} = {metrics['red_confirmation_lead_days']:.0f}d", "MODEL"),
        ("DP QC demand", "Passionfruit requirement", "DEMAND_TO_SUPPLY", "Viral 4x scenario pulp uplift", metrics["viral4_pulp_requirement_uplift_pct"], f"+{metrics['viral4_pulp_requirement_uplift_pct']:.1f}% passionfruit kg/week", "SCENARIO_ASSUMPTION"),
        ("Passionfruit requirement", "Usable pulp cover", "DEMAND_TO_SUPPLY", "Old-mix to current-demand cover", demand_cover, f"{old_cover:.2f} → {demand_cover:.2f} weeks at closure", "MODEL"),
        ("Launch handoff", "Imported dragonfruit readiness", "DEMAND_TO_SUPPLY", "Lead time less notice", metrics["launch_lead_gap_days"], f"{metrics['imported_dragonfruit_lead_days']:.0f}d lead vs {metrics['launch_notice_days']:.0f}d notice = {metrics['launch_lead_gap_days']:.0f}d gap", "CASE + MIDPOINT_ASSUMPTION"),
        ("Highway closure", "Passionfruit shortage", "SUPPLY", "Closure length", metrics["closure_days"], "21 days without road inbound", "CASE"),
        ("Passionfruit shortage", "Passionfruit Punch cut", "SUPPLY_TO_DEMAND", "Additional production cut after closure", pp_forced_cut, f"{pp_forced_cut / 1e6:.2f}m PP bottles cut beyond schedule", "SYNTHETIC_RECONCILIATION"),
        ("Passionfruit Punch cut", "Lost sales", "SUPPLY_TO_DEMAND", "PP lost revenue", metrics["pp_lost_revenue_cr"], f"₹{metrics['pp_lost_revenue_cr']:.2f} cr PP lost revenue", "SYNTHETIC_GROUND_TRUTH"),
        ("Stock-outs", "Censored demand signal", "SUPPLY_TO_DEMAND", "Sales/demand gap", total_lost, f"{total_lost / 1e6:.2f}m bottles hidden from sales ({total_lost / total_demand:.1%})", "CASE_TOTAL"),
        ("Stock-outs", "Rival shelf-space threat", "SUPPLY_TO_DEMAND", "Rival launch lag", metrics["rival_launch_lag_days"], "Rival in 6 weeks; shelf-space ₹ not quantified", "CASE; NO_INVENTED_VALUE"),
        ("Route closure", "Emergency air freight", "SUPPLY_TO_DEMAND", "Actual emergency cost", air_cost, f"₹{air_cost:.2f} cr; shown separately from contribution", "CASE"),
    ]
    edge_frame = pd.DataFrame(edges, columns=["source", "target", "edge_type", "metric", "value", "display", "source_flag"])
    return metrics, edge_frame


def build_loss_attribution(config: AppConfig) -> pd.DataFrame:
    """Allocate case losses to causes, then apply transparent capture ranges.

    Lost revenue is shown for context but is NOT added to lost contribution.
    Economic impact = contribution loss + air freight + write-offs/discounts.
    """
    case = config.case
    crore = float(case["crore"])
    summer_bottles = float(case["summer_bottles"])
    lost_bottles = summer_bottles * float(case["summer_revenue_loss_share"])
    lost_revenue = lost_bottles * float(case["price_per_bottle"]) / crore
    lost_contribution = lost_revenue * float(case["contribution_margin"])
    sensitivity = config.number("A047")
    rows = []
    for row in config.tables["loss_attribution"].itertuples():
        revenue_component = lost_revenue * float(row.lost_contribution_share)
        contribution_component = lost_contribution * float(row.lost_contribution_share)
        air_component = float(case["air_freight_cost_cr"]) * float(row.air_freight_share)
        writeoff_component = float(case["writeoff_discount_cr"]) * float(row.writeoff_share)
        impact = contribution_component + air_component + writeoff_component
        rows.append({
            "root_cause_id": row.root_cause_id,
            "root_cause": row.root_cause,
            "allocated_lost_revenue_cr_context_only": revenue_component,
            "lost_contribution_cr": contribution_component,
            "air_freight_cr": air_component,
            "writeoff_discount_cr": writeoff_component,
            "economic_impact_cr": impact,
            "low_economic_impact_cr": impact - sensitivity * contribution_component,
            "high_economic_impact_cr": impact + sensitivity * contribution_component,
            "low_capture": float(row.low_capture),
            "base_capture": float(row.base_capture),
            "high_capture": float(row.high_capture),
            "avoided_loss_low_cr": impact * float(row.low_capture),
            "avoided_loss_base_cr": impact * float(row.base_capture),
            "avoided_loss_high_cr": impact * float(row.high_capture),
            "evidence": row.evidence,
            "recommended_intervention": row.recommended_intervention,
            "source": "MY ASSUMPTION — ALLOCATION OF CASE-STATED TOTALS",
            "VERIFIED_AGAINST_CASE_TEXT": "N",
        })
    result = pd.DataFrame(rows)
    if not np.isclose(config.tables["loss_attribution"]["lost_contribution_share"].sum(), 1.0):
        raise ValueError("Lost-contribution attribution shares must sum to one")
    if not np.isclose(config.tables["loss_attribution"]["air_freight_share"].sum(), 1.0):
        raise ValueError("Air-freight attribution shares must sum to one")
    if not np.isclose(config.tables["loss_attribution"]["writeoff_share"].sum(), 1.0):
        raise ValueError("Write-off attribution shares must sum to one")
    return result


def attribution_reconciliation(attribution: pd.DataFrame, config: AppConfig) -> pd.DataFrame:
    case = config.case
    lost_revenue = float(case["summer_bottles"]) * float(case["summer_revenue_loss_share"]) * float(case["price_per_bottle"]) / CRORE
    expected = {
        "Lost revenue context": (attribution["allocated_lost_revenue_cr_context_only"].sum(), lost_revenue),
        "Lost contribution": (attribution["lost_contribution_cr"].sum(), lost_revenue * float(case["contribution_margin"])),
        "Air freight": (attribution["air_freight_cr"].sum(), float(case["air_freight_cost_cr"])),
        "Write-offs/discounts": (attribution["writeoff_discount_cr"].sum(), float(case["writeoff_discount_cr"])),
        "Total economic impact without revenue double count": (
            attribution["economic_impact_cr"].sum(),
            lost_revenue * float(case["contribution_margin"]) + float(case["air_freight_cost_cr"]) + float(case["writeoff_discount_cr"]),
        ),
    }
    rows = []
    for name, (actual, target) in expected.items():
        rows.append({"check_name": name, "actual_cr": actual, "expected_cr": target, "status": "PASS" if np.isclose(actual, target) else "FAIL"})
    rows.append({
        "check_name": "Avoided-loss ranges ordered LOW <= BASE <= HIGH",
        "actual_cr": attribution["avoided_loss_low_cr"].sum(),
        "expected_cr": attribution["avoided_loss_high_cr"].sum(),
        "status": "PASS" if (attribution["avoided_loss_low_cr"] <= attribution["avoided_loss_base_cr"]).all() and (attribution["avoided_loss_base_cr"] <= attribution["avoided_loss_high_cr"]).all() else "FAIL",
    })
    return pd.DataFrame(rows)
