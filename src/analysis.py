"""Orchestration of pure analytics into one application context."""
from __future__ import annotations

import pandas as pd

from .budget import build_budget, budget_impact, budget_reconciliation
from .config import AppConfig
from .control_tower import control_tower_tiles, inventory_cover_snapshot, suggest_depot_transfers
from .demand import (
    build_demand_scenarios,
    censoring_validation,
    detect_demand_anomalies,
    estimate_censored_demand,
    forecast_and_latency_diagnostics,
    launch_readiness_gate,
    prepare_qc_signal,
    weekly_rolling_reforecast,
)
from .links import attribution_reconciliation, build_causal_links, build_loss_attribution
from .quality import run_data_quality_checks
from .recommendations import build_risk_register
from .replay import build_scenario_replay, replay_reconciliation
from .sensitivity import avoided_loss_range
from .supply import (
    air_only_comparison,
    build_exposure_map,
    closure_loss_scenarios,
    constrained_weekly_planner,
    optimise_buffer,
    passionfruit_requirement_profile,
    shortage_allocation_options,
    supply_option_economics,
)


def build_analysis(config: AppConfig, datasets: dict[str, pd.DataFrame], detector_params: dict[str, float | int]) -> dict:
    """Compute all page tables once per detector-parameter selection."""
    qc_available = "qc_sell_through" in datasets and not datasets["qc_sell_through"].empty
    depot_available = "depot_stock_weekly" in datasets and not datasets["depot_stock_weekly"].empty
    feed_degraded = not (qc_available and depot_available)
    uncertainty_pct = config.number("A038") if feed_degraded else config.number("A037")
    corrected = estimate_censored_demand(datasets["daily_sales"], int(config.case["baseline_window_days"]))
    signal = prepare_qc_signal(datasets["qc_sell_through"], int(config.case["baseline_window_days"]))
    alerts = detect_demand_anomalies(signal, **detector_params)
    forecast_metrics, forecast_by_flavor = forecast_and_latency_diagnostics(
        datasets["monthly_forecast"], datasets["qc_sell_through"]
    )
    censoring_metrics = censoring_validation(corrected)
    reforecast = weekly_rolling_reforecast(
        corrected, int(config.number("A040")), config.number("A034"), config.assumption("A061")
    )
    comparable = reforecast.dropna(subset=["actual_next_week_bottles"])
    reforecast_wape = float(
        (comparable["reforecast_next_week_bottles"] - comparable["actual_next_week_bottles"]).abs().sum()
        / comparable["actual_next_week_bottles"].sum()
    )
    launch_status, launch_gate = launch_readiness_gate(
        datasets["pulp_inventory_daily"], config.tables["bom"], config.tables["suppliers"],
        "DP", config.launch_date, int(config.number("A027")), int(config.case["launch_notice_days"]),
        datasets["production_daily"],
    )

    exposure = build_exposure_map(
        config.closure_start, datasets["pulp_inventory_daily"], config.tables["flavors"],
        config.tables["bom"], config.tables["suppliers"], config.tables["routes"],
        int(config.case["summer_bottles"]), float(config.case["price_per_bottle"]), config.assumption("A065"),
    )
    passion = exposure[exposure["pulp_id"] == "PASSION"].iloc[0]
    profile = passionfruit_requirement_profile(
        corrected, config.tables["bom"], config.closure_start, int(config.number("A041")),
        float(config.case["price_per_bottle"]) * float(config.case["contribution_margin"]),
    )
    normal_cost = float(config.tables["suppliers"].set_index("pulp_id").loc["PASSION", "normal_cost_per_kg"])
    closure_weights = {1: config.number("A031"), 2: config.number("A032"), 3: config.number("A033")}
    closure_scenarios = closure_loss_scenarios(
        profile["daily_pulp_kg"], float(passion["opening_kg"]), profile["contribution_per_kg"],
        normal_cost, float(config.case["passion_closure_probability"]), closure_weights,
        float(config.case["air_cost_multiplier"]),
    )
    buffer_table, best_buffer = optimise_buffer(
        profile["daily_pulp_kg"], float(passion["opening_kg"]), profile["contribution_per_kg"], normal_cost,
        max_buffer_weeks=int(config.number("A046")),
        annual_closure_probability=float(config.case["passion_closure_probability"]),
        conditional_weights=closure_weights, annual_carry_rate=config.number("A029"),
        cold_storage_rate=config.number("A030"), air_cost_multiplier=float(config.case["air_cost_multiplier"]),
        frozen_shelf_life_days=int(config.case["frozen_pulp_shelf_life_days"]),
    )
    air_only = air_only_comparison(closure_scenarios)
    best_buffer["air_only_expected_total_cost_cr"] = float(air_only["expected_total_cost_cr"])
    best_buffer["recommended_strategy"] = (
        "AIR_ONLY" if float(air_only["expected_total_cost_cr"]) < float(best_buffer["expected_total_cost_cr"])
        else f"BUFFER_{int(best_buffer['buffer_weeks'])}_WEEKS"
    )
    best_buffer["recommendation_margin_cr"] = abs(
        float(air_only["expected_total_cost_cr"]) - float(best_buffer["expected_total_cost_cr"])
    )
    if best_buffer["recommended_strategy"].startswith("BUFFER_") and float(best_buffer["buffer_weeks"]) == 0:
        best_buffer["recommended_strategy"] = "NO_ADDITIONAL_BUFFER"
    best_buffer["low_probability_caveat"] = bool(
        float(config.case["passion_closure_probability"]) < float(best_buffer["break_even_closure_probability"])
    )
    best_buffer["small_margin_caveat"] = bool(
        float(best_buffer["recommendation_margin_cr"]) < 0.10 or float(best_buffer["net_expected_benefit_cr"]) < 0.10
    )
    supply_options = supply_option_economics(
        config.tables["supply_options"], buffer_table, best_buffer, closure_scenarios
    )

    bottle_scenarios, pulp_scenarios = build_demand_scenarios(
        corrected, config.tables["bom"], config.summer_end,
        history_days=int(config.number("A041")), gt_mt_spillover=config.number("A034"),
        uncertainty_pct=uncertainty_pct, horizon_weeks=int(config.number("A060")),
        week_start_day=config.assumption("A061"),
    )
    opening_pulp = datasets["pulp_inventory_daily"].loc[
        datasets["pulp_inventory_daily"]["date"] == config.summer_end
    ].set_index("pulp_id")["opening_kg"].to_dict()
    capacity_plan = constrained_weekly_planner(
        bottle_scenarios, config.summer_end,
        combined_monthly_capacity=int(config.case["combined_monthly_capacity_bottles"]),
        historical_utilisation=float(config.case["summer_utilisation"]),
        copacker_share=float(config.case["copacker_max_volume_share"]),
        copacker_notice_days=int(config.case["copacker_notice_days"]),
        copacker_premium=float(config.case["copacker_cost_premium"]),
        base_variable_cost_per_bottle=float(config.case["price_per_bottle"]) * (1.0 - float(config.case["contribution_margin"])),
        days_per_month=config.number("A028"),
        bottled_shelf_life_days=int(config.case["bottled_shelf_life_days"]),
        mt_qc_min_remaining_days=int(config.case["mt_qc_min_remaining_shelf_days"]),
        copacker_notice_given=True, bom=config.tables["bom"], opening_pulp_kg=opening_pulp,
    )

    allocation_date = config.closure_start + pd.Timedelta(days=14)
    allocation_bottles, _ = build_demand_scenarios(
        corrected, config.tables["bom"], allocation_date,
        history_days=int(config.number("A041")), gt_mt_spillover=config.number("A034"),
        uncertainty_pct=uncertainty_pct, horizon_weeks=int(config.number("A060")),
        week_start_day=config.assumption("A061"),
    )
    allocation_week = allocation_bottles["week_start"].min()
    allocation_demand = allocation_bottles[
        (allocation_bottles["scenario"] == "VIRAL_4X") & (allocation_bottles["week_start"] == allocation_week)
    ]
    available_passion = float(datasets["pulp_inventory_daily"].loc[
        (datasets["pulp_inventory_daily"]["date"] == allocation_date) &
        (datasets["pulp_inventory_daily"]["pulp_id"] == "PASSION"), "opening_kg"
    ].iloc[0])
    allocation, allocation_detail = shortage_allocation_options(
        available_passion, allocation_demand, config.tables["bom"], config.tables["allocation_options"],
        float(config.case["price_per_bottle"]) * float(config.case["contribution_margin"]),
        {"GT": config.number("A043"), "MT": config.number("A044"), "QC": config.number("A045")},
        config.assumption("A064"),
    )

    attribution = build_loss_attribution(config)
    causal_metrics, causal_edges = build_causal_links(datasets, corrected, alerts, config)
    copacker_benefit = float(supply_options.loc[supply_options["option_id"] == "CO_PACKER", "expected_annual_benefit_cr"].iloc[0])
    risks = build_risk_register(config, causal_metrics, attribution, launch_status, copacker_benefit)
    replay_daily, replay_actions, avoided = build_scenario_replay(
        config, datasets, corrected, alerts, attribution, float(best_buffer["buffer_weeks"])
    )

    cover = inventory_cover_snapshot(
        corrected, datasets["depot_stock_weekly"], config.summer_end,
        int(config.number("A041")), int(config.case["depot_cover_days"]),
        int(config.number("A052")), int(config.number("A053")), int(config.number("A054")),
    )
    try:
        transfer_rule = dict(part.split("=", 1) for part in config.assumption("A059").split(";"))
        same_region_days = int(transfer_rule["same_region"])
        cross_region_days = int(transfer_rule["cross_region"])
        if not int(config.case["transfer_min_days"]) <= same_region_days <= cross_region_days <= int(config.case["transfer_max_days"]):
            raise ValueError("A059 transfer days must be ordered and within the case 2–4 day range")
    except (KeyError, ValueError) as error:
        raise ValueError("A059 must be same_region=N;cross_region=N within the case range") from error
    transfers = suggest_depot_transfers(
        cover, float(config.case["transfer_cost_per_bottle"]), same_region_days,
        cross_region_days,
        float(config.case["price_per_bottle"]) * float(config.case["contribution_margin"]), config.number("A035"),
    )
    end_exposure = build_exposure_map(
        config.summer_end, datasets["pulp_inventory_daily"], config.tables["flavors"], config.tables["bom"],
        config.tables["suppliers"], config.tables["routes"],
        int(config.case["summer_bottles"]), float(config.case["price_per_bottle"]), config.assumption("A065"),
    )
    end_profile = passionfruit_requirement_profile(
        corrected, config.tables["bom"], config.summer_end, int(config.number("A041")),
        float(config.case["price_per_bottle"]) * float(config.case["contribution_margin"]),
    )
    end_passion = datasets["pulp_inventory_daily"].loc[
        (datasets["pulp_inventory_daily"]["date"] == config.summer_end) &
        (datasets["pulp_inventory_daily"]["pulp_id"] == "PASSION")
    ].iloc[0]
    end_demand_cover = float(end_passion["opening_kg"] / end_profile["daily_pulp_kg"] / 7.0)
    tiles = control_tower_tiles(
        config, alerts, end_exposure, cover, transfers, config.summer_end, end_demand_cover
    )
    budget, budget_summary = build_budget(config)
    impact = budget_impact(attribution, budget_summary)

    return {
        "feed_degraded": feed_degraded,
        "qc_available": qc_available,
        "depot_available": depot_available,
        "scenario_uncertainty_pct": uncertainty_pct,
        "corrected": corrected,
        "signal": signal,
        "alerts": alerts,
        "forecast_metrics": forecast_metrics,
        "forecast_by_flavor": forecast_by_flavor,
        "censoring_metrics": censoring_metrics,
        "reforecast": reforecast,
        "reforecast_wape": reforecast_wape,
        "launch_status": launch_status,
        "launch_gate": launch_gate,
        "exposure": exposure,
        "passion_profile": profile,
        "closure_scenarios": closure_scenarios,
        "buffer_table": buffer_table,
        "best_buffer": best_buffer,
        "air_only": air_only,
        "writeoff_reconciliation": datasets.get("writeoff_reconciliation", pd.DataFrame()),
        "depot_mismatch": datasets.get("depot_stock_weekly", pd.DataFrame()),
        "supply_options": supply_options,
        "bottle_scenarios": bottle_scenarios,
        "pulp_scenarios": pulp_scenarios,
        "capacity_plan": capacity_plan,
        "allocation_date": allocation_date,
        "available_passion_kg": available_passion,
        "allocation": allocation,
        "allocation_detail": allocation_detail,
        "attribution": attribution,
        "causal_metrics": causal_metrics,
        "causal_edges": causal_edges,
        "risks": risks,
        "replay_daily": replay_daily,
        "replay_actions": replay_actions,
        "avoided": avoided,
        "avoided_range": avoided_loss_range(attribution),
        "cover": cover,
        "transfers": transfers,
        "tiles": tiles,
        "budget": budget,
        "budget_summary": budget_summary,
        "budget_impact": impact,
        "quality_checks": run_data_quality_checks(datasets, config),
        "attribution_checks": attribution_reconciliation(attribution, config),
        "replay_checks": replay_reconciliation(replay_actions, avoided, config),
        "budget_checks": budget_reconciliation(config),
    }
