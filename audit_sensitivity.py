#!/usr/bin/env python3
"""Reproduce the three headline sensitivities in the implementation audit.

The sensing test isolates demand generation and the real QC detector. The other
 tests use the actual closure optimiser and loss-attribution/budget functions.
No source configuration or generated case data is modified.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pandas as pd

from src.analysis import build_analysis
from src.budget import build_budget, budget_impact
from src.config import AppConfig, load_config
from src.data_generator import SyntheticDataGenerator
from src.data_loader import load_datasets
from src.demand import detect_demand_anomalies, first_alerts, prepare_qc_signal
from src.links import build_loss_attribution
from src.supply import optimise_buffer


OUTPUT = Path("sensitivity_results.csv")


def detector_params(config: AppConfig) -> dict[str, float | int]:
    return {
        "baseline_window": int(config.case["baseline_window_days"]),
        "amber_multiplier": float(config.case["amber_multiplier"]),
        "amber_days": int(config.case["amber_consecutive_days"]),
        "red_multiplier": float(config.case["red_multiplier"]),
        "red_days": int(config.case["red_consecutive_days"]),
        "min_history": int(config.number("A039")),
    }


def sensing_sensitivity(config: AppConfig) -> tuple[list[dict], pd.DataFrame]:
    """Vary only A042, the invented immediate multiplier on the reel date."""
    records: list[dict] = []
    display: list[dict] = []
    notice = pd.Timestamp(config.assumption("A007"))
    for initial in [1.0, 1.5, 2.0, 2.5, 3.0]:
        varied = deepcopy(config)
        varied.assumptions.loc[varied.assumptions["assumption_id"].eq("A042"), "value"] = str(initial)
        generator = SyntheticDataGenerator(varied)
        # Only demand and QC are needed for this detector sensitivity. These are
        # the same generator methods used by generate(), not a surrogate curve.
        daily = generator._build_demand_and_sales()
        qc = generator._build_qc_feed(daily)
        signal = prepare_qc_signal(qc, int(varied.case["baseline_window_days"]))
        alerts = detect_demand_anomalies(signal, **detector_params(varied))
        dates = first_alerts(alerts, "DP")
        actionable = dates["RED"] or dates["AMBER"]
        headline_lead = (notice - actionable).days if actionable is not None else None
        amber_lead = (notice - dates["AMBER"]).days if dates["AMBER"] is not None else None
        red_lead = (notice - dates["RED"]).days if dates["RED"] is not None else None
        scenario = f"A042={initial:.1f}" + (" (BASE)" if initial == 2.5 else "")
        values = {
            "first_amber": str(dates["AMBER"].date()) if dates["AMBER"] is not None else "Not triggered",
            "first_red": str(dates["RED"].date()) if dates["RED"] is not None else "Not triggered",
            "headline_alert_lead_days": headline_lead,
            "amber_lead_days": amber_lead,
            "red_lead_days": red_lead,
        }
        display.append({"scenario": scenario, **values})
        for metric, value in values.items():
            records.append({"test": "Viral ramp shape", "scenario": scenario, "metric": metric, "value": value})
    return records, pd.DataFrame(display)


def baseline_analysis(config: AppConfig) -> dict:
    datasets = load_datasets()
    return build_analysis(config, datasets, detector_params(config))


def closure_sensitivity(config: AppConfig, analysis: dict) -> tuple[list[dict], pd.DataFrame]:
    """Vary the case-encoded annual closure probability from 15% to 90%."""
    records: list[dict] = []
    display: list[dict] = []
    profile = analysis["passion_profile"]
    existing = float(analysis["exposure"].loc[analysis["exposure"]["pulp_id"].eq("PASSION"), "opening_kg"].iloc[0])
    normal_cost = float(config.tables["suppliers"].set_index("pulp_id").loc["PASSION", "normal_cost_per_kg"])
    weights = {1: config.number("A031"), 2: config.number("A032"), 3: config.number("A033")}
    base_one_week_avoided = None
    base_carry = None
    for probability in [0.15, 0.30, 0.45, 0.60, 0.90]:
        table, best = optimise_buffer(
            profile["daily_pulp_kg"], existing, profile["contribution_per_kg"], normal_cost,
            max_buffer_weeks=int(config.number("A046")), annual_closure_probability=probability,
            conditional_weights=weights, annual_carry_rate=config.number("A029"),
            cold_storage_rate=config.number("A030"), air_cost_multiplier=float(config.case["air_cost_multiplier"]),
        )
        if probability == 0.60:
            base_one_week_avoided = float(table.loc[table["buffer_weeks"].eq(1), "avoided_expected_loss_cr"].iloc[0])
            base_carry = float(table.loc[table["buffer_weeks"].eq(1), "annual_carry_and_storage_cr"].iloc[0])
        scenario = f"Closure probability={probability:.0%}" + (" (CASE/BASE)" if probability == 0.60 else "")
        values = {
            "zero_buffer_expected_loss_cr": float(table.loc[table["buffer_weeks"].eq(0), "expected_stockout_loss_cr"].iloc[0]),
            "best_buffer_weeks": float(best["buffer_weeks"]),
            "best_net_expected_benefit_cr": float(best["net_expected_benefit_cr"]),
            "best_annual_carry_storage_cr": float(best["annual_carry_and_storage_cr"]),
            "best_recoverable_working_capital_cr": float(best["buffer_working_capital_cr"]),
        }
        display.append({"scenario": scenario, **values})
        for metric, value in values.items():
            records.append({"test": "Closure probability", "scenario": scenario, "metric": metric, "value": value})

    # At the base assumptions, expected loss and avoided loss scale linearly in
    # annual closure probability. This is the one-week carry break-even point.
    assert base_one_week_avoided is not None and base_carry is not None
    break_even = base_carry / (base_one_week_avoided / 0.60)
    records.append({"test": "Closure probability", "scenario": "Derived from base table", "metric": "one_week_carry_break_even_probability", "value": break_even})

    # Specification audit: the displayed expected air premium is excluded from
    # optimise_buffer's objective. Add it back to expose that modeling choice.
    table = analysis["buffer_table"].copy()
    table["cost_including_air_premium_cr"] = (
        table["annual_carry_and_storage_cr"] + table["expected_stockout_loss_cr"] + table["expected_air_premium_cr"]
    )
    best_with_air = table.loc[table["cost_including_air_premium_cr"].idxmin()]
    for metric, value in {
        "best_buffer_weeks": float(best_with_air["buffer_weeks"]),
        "best_total_cost_cr": float(best_with_air["cost_including_air_premium_cr"]),
    }.items():
        records.append({"test": "Buffer objective specification", "scenario": "Add displayed expected air premium to objective", "metric": metric, "value": value})
    return records, pd.DataFrame(display)


def attribution_sensitivity(config: AppConfig) -> tuple[list[dict], pd.DataFrame]:
    """Change only the four judgmental lost-contribution shares."""
    records: list[dict] = []
    display: list[dict] = []
    variants = {
        "BASE 35/35/15/15": [0.35, 0.35, 0.15, 0.15],
        "Equal 25/25/25/25": [0.25, 0.25, 0.25, 0.25],
        "Route-heavy 15/55/15/15": [0.15, 0.55, 0.15, 0.15],
        "Sensing-heavy 55/15/15/15": [0.55, 0.15, 0.15, 0.15],
        "All stale-mix extreme 0/0/0/100": [0.0, 0.0, 0.0, 1.0],
    }
    _, budget_summary = build_budget(config)
    for scenario, shares in variants.items():
        varied = deepcopy(config)
        varied.tables["loss_attribution"]["lost_contribution_share"] = shares
        attribution = build_loss_attribution(varied)
        impact = budget_impact(attribution, budget_summary)
        values = {
            "avoided_loss_low_cr": float(attribution["avoided_loss_low_cr"].sum()),
            "avoided_loss_base_cr": float(attribution["avoided_loss_base_cr"].sum()),
            "avoided_loss_high_cr": float(attribution["avoided_loss_high_cr"].sum()),
            "base_payback_months": float(impact.loc[impact["scenario"].eq("BASE"), "simple_payback_months"].iloc[0]),
        }
        display.append({"scenario": scenario, **values})
        for metric, value in values.items():
            records.append({"test": "Lost-contribution attribution split", "scenario": scenario, "metric": metric, "value": value})
    return records, pd.DataFrame(display)


def main() -> int:
    config = load_config()
    sensing_records, sensing_display = sensing_sensitivity(config)
    analysis = baseline_analysis(config)
    closure_records, closure_display = closure_sensitivity(config, analysis)
    attribution_records, attribution_display = attribution_sensitivity(config)
    records = sensing_records + closure_records + attribution_records
    pd.DataFrame(records).to_csv(OUTPUT, index=False)
    for title, frame in [
        ("VIRAL RAMP SHAPE", sensing_display),
        ("CLOSURE PROBABILITY", closure_display),
        ("LOST-CONTRIBUTION ATTRIBUTION SPLIT", attribution_display),
    ]:
        print(f"\n{title}\n{frame.to_string(index=False)}")
    objective = pd.DataFrame(records)
    print("\nBUFFER OBJECTIVE SPECIFICATION")
    print(objective[objective["test"].eq("Buffer objective specification")].to_string(index=False))
    print(f"\nWrote {len(records)} metric rows to {OUTPUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
