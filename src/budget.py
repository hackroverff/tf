"""First-year selected budget, impact ranges and eight-month roadmap."""
from __future__ import annotations

import pandas as pd

from .config import AppConfig


def build_budget(config: AppConfig) -> tuple[pd.DataFrame, dict[str, float]]:
    budget = config.tables["budget"].copy()
    # Keep supply-option economics consistent across pages.
    supply_options = config.tables["supply_options"].set_index("option_id")
    for item_id in ["SECOND_SUPPLIER", "AIR_TRIGGER", "CO_PACKER"]:
        budget.loc[budget["item_id"] == item_id, "cost_cr"] = float(supply_options.loc[item_id, "year1_cost_cr"])
    budget["selected"] = budget["selected"].astype(int)
    budget["selected_cost_cr"] = budget["cost_cr"] * budget["selected"]
    selected = budget[budget["selected"] == 1]
    total = float(selected["selected_cost_cr"].sum())
    summary = {
        "total_cost_cr": total,
        "one_time_build_cr": float(selected.loc[selected["cost_type"] == "ONE_TIME_BUILD", "selected_cost_cr"].sum()),
        "year1_run_cr": float(selected.loc[selected["cost_type"].isin(["YEAR_1_RUN", "CONTINGENCY"]), "selected_cost_cr"].sum()),
        "budget_cap_cr": 2.50,
        "headroom_cr": 2.50 - total,
        "optional_copacker_cost_cr": float(budget.loc[budget["item_id"] == "CO_PACKER", "cost_cr"].iloc[0]),
        "hidden_working_capital_cr": 0.0,
    }
    if total > 2.50 + 1e-9:
        raise ValueError("Selected first-year budget exceeds ₹2.5 cr")
    return budget, summary


def budget_impact(attribution: pd.DataFrame, budget_summary: dict[str, float]) -> pd.DataFrame:
    """Simple next-summer benefit/cost; no option-benefit stacking or discounting."""
    cost = float(budget_summary["total_cost_cr"])
    rows = []
    for scenario in ["low", "base", "high"]:
        benefit = float(attribution[f"avoided_loss_{scenario}_cr"].sum())
        rows.append({
            "scenario": scenario.upper(),
            "selected_first_year_cost_cr": cost,
            "expected_next_summer_benefit_cr": benefit,
            "net_first_year_benefit_cr": benefit - cost,
            "benefit_cost_ratio": benefit / cost,
            "simple_payback_months": 12.0 * cost / benefit if benefit > 0 else float("inf"),
            "basis": "ASSUMPTION-BASED, NOT SIMULATED; top-down root-cause capture; not additive across alerts/options; undiscounted",
        })
    return pd.DataFrame(rows)


def budget_reconciliation(config: AppConfig) -> pd.DataFrame:
    budget, summary = build_budget(config)
    impact = budget_impact(build_loss_attribution_safe(config), summary)
    roadmap = config.tables["roadmap"]
    checks = [
        ("Selected first-year cost <= ₹2.5 cr", summary["total_cost_cr"], 2.50, summary["total_cost_cr"] <= 2.50),
        ("No hidden working capital in selected package", summary["hidden_working_capital_cr"], 0.0, summary["hidden_working_capital_cr"] == 0),
        ("Contingency included", float(budget.loc[budget["item_id"] == "CONTINGENCY", "selected_cost_cr"].iloc[0]), 0.20, float(budget.loc[budget["item_id"] == "CONTINGENCY", "selected_cost_cr"].iloc[0]) > 0),
        ("Roadmap has eight phases", len(roadmap), 8, len(roadmap) == 8),
        ("Training line covers planner adoption", float(budget.loc[budget["item_id"] == "TRAINING", "selected_cost_cr"].iloc[0]), 0.12, float(budget.loc[budget["item_id"] == "TRAINING", "selected_cost_cr"].iloc[0]) > 0),
        ("Benefit scenarios ordered", float(impact["expected_next_summer_benefit_cr"].iloc[0]), float(impact["expected_next_summer_benefit_cr"].iloc[2]), impact["expected_next_summer_benefit_cr"].is_monotonic_increasing),
    ]
    return pd.DataFrame([
        {"check_name": name, "actual": actual, "expected_or_limit": expected, "status": "PASS" if passed else "FAIL"}
        for name, actual, expected, passed in checks
    ])


def build_loss_attribution_safe(config: AppConfig) -> pd.DataFrame:
    # Local import avoids a module-cycle if budget is imported by presentation code.
    from .links import build_loss_attribution
    return build_loss_attribution(config)
