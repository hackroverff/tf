#!/usr/bin/env python3
"""Run demand-engine diagnostics against generated data."""
from src.config import load_config
from src.data_loader import load_datasets
from src.demand import (
    build_demand_scenarios,
    censoring_validation,
    detect_demand_anomalies,
    estimate_censored_demand,
    first_alerts,
    forecast_and_latency_diagnostics,
    launch_readiness_gate,
    prepare_qc_signal,
    weekly_rolling_reforecast,
)


def main() -> None:
    cfg = load_config()
    data = load_datasets()
    corrected = estimate_censored_demand(data["daily_sales"])
    signal = prepare_qc_signal(data["qc_sell_through"])
    alerts = detect_demand_anomalies(
        signal,
        baseline_window=int(cfg.case["baseline_window_days"]),
        amber_multiplier=float(cfg.case["amber_multiplier"]),
        amber_days=int(cfg.case["amber_consecutive_days"]),
        red_multiplier=float(cfg.case["red_multiplier"]),
        red_days=int(cfg.case["red_consecutive_days"]),
        min_history=int(cfg.number("A039")),
    )
    metrics, by_flavor = forecast_and_latency_diagnostics(data["monthly_forecast"], data["qc_sell_through"])
    dates = first_alerts(alerts)
    print("DEMAND DIAGNOSTICS")
    print(f"Forecast WAPE: {metrics['forecast_wape']:.1%}")
    print(f"QC planner average latency: {metrics['qc_planner_average_latency_days']:.1f} days")
    print(f"QC planner maximum latency: {metrics['qc_planner_max_latency_days']} days")
    print(f"DP first Amber: {dates['AMBER'].date() if dates['AMBER'] else 'none'}")
    print(f"DP first Red: {dates['RED'].date() if dates['RED'] else 'none'}")
    print(f"Planner notice: {pd_timestamp(cfg.assumption('A007'))}")
    first_actionable = dates["RED"] or dates["AMBER"]
    print(f"Alert lead vs planner notice: {(pd_timestamp(cfg.assumption('A007')) - first_actionable).days} days (first Red/Amber)")
    print("\nCENSORING BACK-TEST (synthetic ground truth used only here)")
    for key, value in censoring_validation(corrected).items():
        print(f"{key}: {value:,.2f}" if isinstance(value, float) else f"{key}: {value}")

    reforecast = weekly_rolling_reforecast(corrected, int(cfg.number("A040")), cfg.number("A034"))
    comparable = reforecast.dropna(subset=["actual_next_week_bottles"])
    wape = ((comparable["reforecast_next_week_bottles"] - comparable["actual_next_week_bottles"]).abs().sum()
            / comparable["actual_next_week_bottles"].sum())
    print(f"\nWeekly rolling next-week WAPE (all channels/depots): {wape:.2%}")
    bottles, pulp = build_demand_scenarios(
        corrected, cfg.tables["bom"], cfg.summer_end, history_days=int(cfg.number("A041")),
        gt_mt_spillover=cfg.number("A034"), uncertainty_pct=cfg.number("A037")
    )
    first_week = bottles["week_start"].min()
    print(f"\nFORWARD WEEK 1 SCENARIOS (week starting {first_week.date()})")
    print(bottles[bottles["week_start"] == first_week].groupby("scenario")["scenario_bottles"].sum().to_string())
    print("\nPASSIONFRUIT PULP REQUIREMENT (KG, WEEK 1)")
    week_pulp = pulp[(pulp["pulp_id"] == "PASSION") & (pulp["week_start"] == first_week)]
    print(week_pulp.groupby("scenario")["pulp_requirement_kg"].sum().to_string())
    status, gate = launch_readiness_gate(
        data["pulp_inventory_daily"], cfg.tables["bom"], cfg.tables["suppliers"],
        "DP", cfg.launch_date, int(cfg.number("A027")), int(cfg.case["launch_notice_days"]),
        production_plan=data["production_daily"],
    )
    print(f"\nLAUNCH GATE: {status}")
    print(gate[["pulp_id", "cover_days", "required_cover_days", "notice_less_lead_days", "status"]].to_string(index=False))
    if status != "BLOCKED":
        raise SystemExit("Expected the synthetic DP launch to fail its imported-dragonfruit readiness gate")


def pd_timestamp(value):
    import pandas as pd
    return pd.Timestamp(value)


if __name__ == "__main__":
    main()
