#!/usr/bin/env python3
"""Run supply-engine reconciliation and sanity checks."""
import numpy as np
import pandas as pd

from src.config import load_config
from src.data_loader import load_datasets
from src.demand import build_demand_scenarios, estimate_censored_demand
from src.supply import (
    build_exposure_map,
    closure_loss_scenarios,
    constrained_weekly_planner,
    optimise_buffer,
    passionfruit_requirement_profile,
    shortage_allocation_options,
    supply_option_economics,
)


def main() -> None:
    cfg = load_config()
    data = load_datasets()
    corrected = estimate_censored_demand(data["daily_sales"])
    exposure = build_exposure_map(
        cfg.closure_start, data["pulp_inventory_daily"], cfg.tables["flavors"], cfg.tables["bom"],
        cfg.tables["suppliers"], cfg.tables["routes"], int(cfg.case["summer_bottles"]),
        float(cfg.case["price_per_bottle"]),
    )
    passion = exposure[exposure["pulp_id"] == "PASSION"].iloc[0]
    print("SUPPLY EXPOSURE")
    print(f"Passionfruit-dependent volume: {passion['dependent_summer_bottles'] / 1e7:.3f} cr bottles")
    print(f"Passionfruit-dependent revenue: Rs{passion['dependent_revenue_cr']:.2f} cr")
    print(f"Cover at closure: {passion['baseline_cover_weeks']:.2f} weeks on old baseline / "
          f"{passion['current_cover_weeks']:.2f} weeks at current run-rate")
    print(f"Single source={passion['single_source_flag']}; single route={passion['single_route_flag']}; "
          f"annual closure probability={passion['summer_closure_probability']:.0%}")

    profile = passionfruit_requirement_profile(
        corrected, cfg.tables["bom"], cfg.closure_start, int(cfg.number("A041")),
        float(cfg.case["price_per_bottle"]) * float(cfg.case["contribution_margin"]),
    )
    normal_cost = float(cfg.tables["suppliers"].set_index("pulp_id").loc["PASSION", "normal_cost_per_kg"])
    weights = {1: cfg.number("A031"), 2: cfg.number("A032"), 3: cfg.number("A033")}
    scenarios = closure_loss_scenarios(
        profile["daily_pulp_kg"], float(passion["opening_kg"]), profile["contribution_per_kg"],
        normal_cost, float(cfg.case["passion_closure_probability"]), weights,
        float(cfg.case["air_cost_multiplier"]),
    )
    print("\nCLOSURE LOSS SCENARIOS (NO ADDITIONAL BUFFER)")
    print(scenarios[["closure_weeks", "annual_probability", "shortage_kg", "lost_contribution_cr",
                     "expected_contribution_loss_cr", "air_total_cost_cr"]].to_string(index=False))
    print(f"Probability-weighted expected contribution loss: Rs{scenarios['expected_contribution_loss_cr'].sum():.3f} cr")

    table, best = optimise_buffer(
        profile["daily_pulp_kg"], float(passion["opening_kg"]), profile["contribution_per_kg"], normal_cost,
        max_buffer_weeks=int(cfg.number("A046")), annual_closure_probability=float(cfg.case["passion_closure_probability"]),
        conditional_weights=weights, annual_carry_rate=cfg.number("A029"), cold_storage_rate=cfg.number("A030"),
        air_cost_multiplier=float(cfg.case["air_cost_multiplier"]),
    )
    print("\nBUFFER OPTIONS")
    print(table[["buffer_weeks", "buffer_working_capital_cr", "annual_carry_and_storage_cr",
                 "expected_stockout_loss_cr", "avoided_expected_loss_cr", "net_expected_benefit_cr"]].to_string(index=False))
    print(f"Optimiser choice: +{best['buffer_weeks']:.0f} weeks; expected total cost Rs{best['expected_total_cost_cr']:.3f} cr; "
          f"working capital disclosed separately Rs{best['buffer_working_capital_cr']:.3f} cr")
    assert np.all(np.diff(table["expected_stockout_loss_cr"]) <= 1e-9)

    options = supply_option_economics(cfg.tables["supply_options"], table, best, scenarios)
    print("\nSUPPLY OPTION ECONOMICS")
    print(options[["option_id", "year1_run_or_build_cost_cr", "recoverable_working_capital_cr",
                   "expected_annual_benefit_cr", "net_expected_benefit_cr"]].to_string(index=False))

    bottles, _ = build_demand_scenarios(
        corrected, cfg.tables["bom"], cfg.closure_start, history_days=int(cfg.number("A041")),
        gt_mt_spillover=cfg.number("A034"), uncertainty_pct=cfg.number("A037"),
    )
    capacity = constrained_weekly_planner(
        bottles, cfg.closure_start, copacker_notice_given=True,
        days_per_month=cfg.number("A028"),
    )
    print("\nCONSTRAINED WEEKLY CAPACITY (BASE)")
    print(capacity[capacity["scenario"] == "BASE"][["week_start", "scenario_bottles", "in_house_capacity_bottles",
                                                       "copacker_capacity_bottles", "max_feasible_bottles", "unmet_bottles"]].to_string(index=False))

    allocation_date = cfg.closure_start + pd.Timedelta(days=14)
    allocation_bottles, _ = build_demand_scenarios(
        corrected, cfg.tables["bom"], allocation_date, history_days=int(cfg.number("A041")),
        gt_mt_spillover=cfg.number("A034"), uncertainty_pct=cfg.number("A037"),
    )
    first_week = allocation_bottles["week_start"].min()
    demand = allocation_bottles[(allocation_bottles["scenario"] == "VIRAL_4X") &
                                (allocation_bottles["week_start"] == first_week)]
    available = data["pulp_inventory_daily"].loc[
        (data["pulp_inventory_daily"]["date"] == allocation_date) &
        (data["pulp_inventory_daily"]["pulp_id"] == "PASSION"), "opening_kg"
    ].iloc[0]
    allocation, _ = shortage_allocation_options(
        float(available), demand, cfg.tables["bom"], cfg.tables["allocation_options"],
        float(cfg.case["price_per_bottle"]) * float(cfg.case["contribution_margin"]),
        {"GT": cfg.number("A043"), "MT": cfg.number("A044"), "QC": cfg.number("A045")},
    )
    print(f"\nSHORTAGE ALLOCATION ({allocation_date.date()}, available={available:,.0f} kg)")
    print(allocation[["option_id", "used_pulp_kg", "retained_contribution_cr", "weighted_delisting_risk",
                      "dp_unmet_bottles", "rival_threat_flag", "contribution_rank", "decision"]].to_string(index=False))
    assert (allocation["used_pulp_kg"] <= available + 1e-6).all()
    assert allocation["decision"].eq("HUMAN_REQUIRED").all()
    print("\nSUPPLY CHECKS: PASS")


if __name__ == "__main__":
    main()
