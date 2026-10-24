"""Independent reconciliation checks against user-supplied case facts."""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .config import AppConfig
from .utils import CRORE


def reconcile(datasets: dict[str, pd.DataFrame], config: AppConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(check_id: str, category: str, name: str, actual: Any, expected: Any,
            tolerance: float = 1e-8, unit: str = "", interpretation: str = "CASE") -> None:
        if isinstance(actual, (int, float, np.number)) and isinstance(expected, (int, float, np.number)):
            passed = bool(np.isfinite(actual) and abs(float(actual) - float(expected)) <= tolerance)
        else:
            passed = actual == expected
        rows.append({
            "check_id": check_id,
            "category": category,
            "check_name": name,
            "actual": actual,
            "expected": expected,
            "tolerance": tolerance,
            "unit": unit,
            "status": "PASS" if passed else "FAIL",
            "interpretation": interpretation,
        })

    daily = datasets["daily_sales"]
    summer = daily[daily["season"] == "SUMMER"]
    pre = daily[daily["season"] == "PRE"]
    demand = int(summer["true_demand_bottles"].sum())
    sales = int(summer["sales_bottles"].sum())
    lost = int(summer["lost_sales_bottles"].sum())
    case = config.case
    expected_demand = int(case["summer_bottles"])
    expected_lost = int(round(expected_demand * float(case["summer_revenue_loss_share"])))

    add("VOL_01", "Volume", "Annual bottles derived from revenue / price",
        float(case["annual_revenue_cr"]) * float(case["crore"]) / float(case["price_per_bottle"]),
        float(case["annual_bottles"]), 0.1, "bottles")
    add("VOL_02", "Volume", "Summer latent demand reconciles to 9.6 cr bottles", demand, expected_demand, 0, "bottles")
    add("VOL_03", "Volume", "Jan-Feb latent demand", int(pre["true_demand_bottles"].sum()),
        int(config.number("A003")), 0, "bottles", "MY ASSUMPTION")
    add("VOL_04", "Volume", "Summer share of annual bottle volume", demand / float(case["annual_bottles"]),
        float(case["summer_revenue_share"]), 1e-12, "fraction", "DERIVED FROM CASE; equal bottle price")
    add("LOSS_01", "Loss", "Summer stock-out-censored bottles", lost, expected_lost, 0, "bottles")
    add("LOSS_02", "Loss", "Lost revenue at Rs60/bottle", lost * float(case["price_per_bottle"]) / CRORE,
        expected_demand * float(case["summer_revenue_loss_share"]) * float(case["price_per_bottle"]) / CRORE,
        1e-8, "Rs cr")
    add("LOSS_03", "Loss", "Lost contribution at 32%", lost * float(case["price_per_bottle"]) * float(case["contribution_margin"]) / CRORE,
        14.7456, 1e-8, "Rs cr")
    add("LOSS_04", "Loss", "Realised summer sales after censoring", sales, expected_demand - expected_lost, 0, "bottles", "DERIVED")
    add("LOSS_05", "Loss", "Lost demand as share of latent summer demand", lost / demand,
        float(case["summer_revenue_loss_share"]), 1e-12, "fraction")

    for _, flavor in config.tables["flavors"].iterrows():
        actual = int(summer.loc[summer["flavor_id"] == flavor["flavor_id"], "true_demand_bottles"].sum())
        expected = int(round(expected_demand * flavor["summer_share"]))
        add(f"MIX_F_{flavor['flavor_id']}", "Flavor mix", f"Latent volume: {flavor['flavor_name']}", actual, expected, len(config.tables["channels"]), "bottles", "CONFIG_WITH_INTEGER_ROUNDING")
    for _, channel in config.tables["channels"].iterrows():
        actual = int(summer.loc[summer["channel_id"] == channel["channel_id"], "true_demand_bottles"].sum())
        expected = int(round(expected_demand * channel["summer_share"]))
        add(f"MIX_C_{channel['channel_id']}", "Channel mix", f"Latent volume: {channel['channel_name']}", actual, expected, len(config.tables["flavors"]), "bottles", "CONFIG_WITH_INTEGER_ROUNDING")

    production = datasets["production_daily"]
    summer_production = production[production["date"] >= config.summer_start]
    actual_output = int(summer_production["actual_bottles"].sum())
    scheduled_output = int(summer_production["scheduled_bottles"].sum())
    months = pd.period_range(config.summer_start, config.summer_end, freq="M").nunique()
    capacity = int(case["combined_monthly_capacity_bottles"]) * months
    add("CAP_01", "Capacity", "Fixed in-house summer capacity", capacity, 100_000_000, 0, "bottles")
    add("CAP_02", "Capacity", "Actual summer production", actual_output,
        int(round(capacity * float(case["summer_utilisation"]))), 0, "bottles")
    add("CAP_03", "Capacity", "Summer utilisation", actual_output / capacity,
        float(case["summer_utilisation"]), 1e-12, "fraction")
    add("CAP_04", "Capacity", "Pulp constraints reallocate rather than lose scheduled plant volume",
        actual_output, scheduled_output, 0, "bottles", "DERIVED")
    capacity_table = datasets["plant_copacker_capacity"]
    in_house_summer = capacity_table[(capacity_table["asset_type"] == "IN_HOUSE") & (capacity_table["month_start"] >= config.summer_start)]
    add("CAP_05", "Capacity", f"{int(case['plant_count'])} plants at case utilisation in monthly capacity table",
        in_house_summer["actual_bottles"].sum() / in_house_summer["capacity_bottles"].sum(),
        float(case["summer_utilisation"]), 1e-12, "fraction")

    dp = daily[daily["flavor_id"] == "DP"]
    nonzero_dp = dp.loc[dp["true_demand_bottles"] > 0, "date"]
    add("EVENT_01", "Events", "Dragon Passion first demand date", nonzero_dp.min(), config.launch_date, unit="date")
    add("EVENT_02", "Events", "Pre-launch Dragon Passion demand", int(dp.loc[dp["date"] < config.launch_date, "true_demand_bottles"].sum()), 0, 0, "bottles")
    viral = datasets["viral_profile"]
    add("EVENT_03", "Events", "Viral ramp starts", viral["date"].min(), config.viral_start, unit="date")
    add("EVENT_04", "Events", "QC multiplier reaches 4x after 14 days", viral["qc_demand_multiplier"].iloc[-1],
        float(case["viral_qc_multiplier"]), 1e-12, "multiplier")
    add("EVENT_05", "Events", "Viral ramp duration", int(viral["days_since_viral_start"].iloc[-1]),
        int(case["viral_ramp_days"]), 0, "days")
    add("EVENT_06", "Events", "Highway closure duration", (config.closure_end - config.closure_start).days + 1,
        int(case["closure_days"]), 0, "days")

    qc = datasets["qc_sell_through"]
    add("FEED_01", "Latency", "QC feed is daily", int(qc["date"].nunique()), len(daily["date"].unique()), 0, "days")
    add("FEED_02", "Latency", "QC sales reconcile to daily sales QC",
        int(qc["sell_through_bottles"].sum()), int(daily.loc[daily["channel_id"] == "QC", "sales_bottles"].sum()), 0, "bottles")
    forecast = datasets["monthly_forecast"]
    valid_forecast = forecast[forecast["actual_sales_bottles"] > 0]
    wape = valid_forecast["absolute_error_bottles"].sum() / valid_forecast["actual_sales_bottles"].sum()
    add("FEED_03", "Forecast", "Flavor x depot WAPE", wape, float(case["forecast_error"]), 1e-12, "fraction")

    add("NET_01", "Network", "Depot count", int(daily["depot_id"].nunique()), len(config.tables["depots"]), 0, "depots", "CONFIG; base case=9")
    add("NET_02", "Network", "Region count", int(daily["region"].nunique()), int(config.tables["depots"]["region"].nunique()), 0, "regions", "CONFIG; base case=4")
    add("NET_03", "Network", "Flavor count", int(daily["flavor_id"].nunique()), len(config.tables["flavors"]), 0, "flavors")
    add("NET_04", "Network", "Channel count", int(daily["channel_id"].nunique()), len(config.tables["channels"]), 0, "channels")

    passion_volume = int(summer.loc[summer["flavor_id"].isin(["PP", "DP"]), "true_demand_bottles"].sum())
    passion_share = float(config.tables["flavors"].set_index("flavor_id").loc[["PP", "DP"], "summer_share"].sum())
    rounding_bottles = len(config.tables["flavors"]) * len(config.tables["channels"])
    add("EXP_01", "Exposure", "Passionfruit-dependent summer volume", passion_volume,
        int(round(expected_demand * passion_share)), rounding_bottles, "bottles", "CONFIG_WITH_INTEGER_ROUNDING")
    add("EXP_02", "Exposure", "Passionfruit-dependent revenue", passion_volume * float(case["price_per_bottle"]) / CRORE,
        expected_demand * passion_share * float(case["price_per_bottle"]) / CRORE,
        rounding_bottles * float(case["price_per_bottle"]) / CRORE, "Rs cr", "CONFIG_WITH_INTEGER_ROUNDING")
    add("EXP_03", "Exposure", "Passionfruit-dependent volume share", passion_volume / demand, passion_share,
        rounding_bottles / demand, "fraction", "CONFIG_WITH_INTEGER_ROUNDING")

    inventory = datasets["pulp_inventory_daily"]
    add("PULP_01", "Pulp", "Minimum closing pulp inventory", float(inventory["closing_kg"].min()), 0.0,
        1e-6, "kg", "NON_NEGATIVITY")
    # Non-negativity needs a directional check rather than abs(actual-expected).
    rows[-1]["status"] = "PASS" if inventory["closing_kg"].min() >= -1e-6 else "FAIL"
    closure_open = inventory[(inventory["pulp_id"] == "PASSION") & (inventory["date"] == config.closure_start)].iloc[0]
    add("PULP_02", "Pulp", "Passionfruit baseline cover at closure start", closure_open["baseline_cover_days"],
        float(case["passion_cover_days_at_closure"]), 1e-8, "days")
    inbound = datasets["pulp_inbound"]
    closure_road = inbound[(inbound["pulp_id"] == "PASSION") & (inbound["mode"] == "Road") &
                           (inbound["arrival_date"] >= config.closure_start) &
                           (inbound["arrival_date"] <= config.closure_end)]
    add("PULP_03", "Pulp", "Road arrivals during 21-day closure", len(closure_road), 0, 0, "shipments")
    air = inbound[inbound["mode"] == "Air"]
    add("AIR_01", "Air freight", "Emergency air actual cost", float(air["actual_cost_cr"].sum()),
        float(case["air_freight_cost_cr"]), 1e-8, "Rs cr")
    add("AIR_02", "Air freight", "Emergency air cost multiple", float(air["cost_multiplier"].iloc[0]),
        float(case["air_cost_multiplier"]), 1e-12, "multiplier")
    add("AIR_03", "Air freight", "Air booking in closure week 2", pd.Timestamp(air["booking_date"].iloc[0]),
        pd.Timestamp(config.assumption("A012")), unit="date", interpretation="ASSUMPTION")

    writeoffs = datasets["depot_writeoffs"]
    writeoff_recon = datasets["writeoff_reconciliation"].iloc[0]
    reported_writeoff = float(writeoffs["writeoff_discount_cr"].sum())
    expected_writeoff = (
        float(case["writeoff_discount_cr"])
        if writeoff_recon["method"] == "AGING_STOCK_CALIBRATE_TO_CASE"
        else float(writeoff_recon["uncalibrated_aging_value_cr"])
    )
    add("WRITE_01", "Depot imbalance", "Reported write-offs follow the disclosed calibration mode", reported_writeoff,
        expected_writeoff, 1e-8, "Rs cr", "CASE CALIBRATION TARGET" if writeoff_recon["method"] == "AGING_STOCK_CALIBRATE_TO_CASE" else "UNCALIBRATED MODEL")
    add("WRITE_02", "Depot imbalance", "Every write-off breaches its channel remaining-shelf cutoff",
        int((writeoffs["minimum_remaining_shelf_days"] >= writeoffs["channel_cutoff_days"]).sum()),
        0, 0, "rows", "DERIVED FROM FIFO STOCK AGING")
    add("WRITE_03", "Depot imbalance", "Write-off calibration gap arithmetic",
        float(writeoff_recon["calibration_gap_cr"]),
        reported_writeoff - float(writeoff_recon["uncalibrated_aging_value_cr"]), 1e-8, "Rs cr", "DISCLOSED CALIBRATION GAP")
    add("WRITE_04", "Depot imbalance", "Uncalibrated aging value ties to write-off rows",
        float(writeoffs["uncalibrated_value_cr"].sum()),
        float(writeoff_recon["uncalibrated_aging_value_cr"]), 1e-8, "Rs cr", "MODEL")
    shelf_rules = config.tables["channel_shelf_life"]
    mtqc_cutoffs = shelf_rules.loc[shelf_rules["channel_id"].isin(["MT", "QC"]), "min_remaining_days"]
    add("WRITE_05", "Depot imbalance", "MT/QC 60-day rule is explicit and config-driven",
        float(mtqc_cutoffs.max()), float(case["mt_qc_min_remaining_shelf_days"]), 0, "days")
    add("WRITE_06", "Depot imbalance", "GT unspecified rule is an editable config toggle",
        bool((shelf_rules["channel_id"] == "GT").any() and "min_remaining_days" in shelf_rules), True,
        unit="boolean", interpretation="MY ASSUMPTION")

    depot_flow = datasets["depot_flow_daily"]
    add("CONSERVE_01", "Conservation", "Maximum absolute daily depot balance error",
        float(depot_flow["conservation_balance_bottles"].abs().max()), 0.0, 1e-6, "bottles", "PHYSICAL IDENTITY")
    add("CONSERVE_02", "Conservation", "Depot receipts equal actual production",
        float(depot_flow["production_receipts_bottles"].sum()), float(production["actual_bottles"].sum()),
        1e-6, "bottles", "PHYSICAL IDENTITY")
    add("CONSERVE_03", "Conservation", "Depot issues equal realised daily sales",
        float(depot_flow["sales_bottles"].sum()), float(daily["sales_bottles"].sum()),
        1e-6, "bottles", "PHYSICAL IDENTITY")
    add("CONSERVE_04", "Conservation", "No negative closing depot stock after write-offs",
        int((depot_flow["closing_bottles"] < -1e-6).sum()), 0, 0, "rows", "NON_NEGATIVITY")
    opening = depot_flow[depot_flow["date"] == depot_flow["date"].min()]
    opening_dp = float(opening.loc[opening["flavor_id"] == "DP", "opening_bottles"].sum())
    add("CONSERVE_05", "Conservation", "Opening DP stock is zero in last-year mix", opening_dp, 0.0, 0, "bottles", "MY ASSUMPTION")
    opening_total = float(opening["opening_bottles"].sum())
    opening_by_flavor = opening.groupby("flavor_id")["opening_bottles"].sum()
    last_year = config.tables["last_year_mix"].set_index("flavor_id")["last_year_share"]
    mix_error = max(
        abs(float(opening_by_flavor.get(flavor_id, 0.0)) - opening_total * float(last_year.loc[flavor_id]))
        for flavor_id in config.tables["flavors"]["flavor_id"]
    )
    add("CONSERVE_06", "Conservation", "Opening stock follows three-week last-year mix",
        mix_error, 0.0, float(len(config.tables["depots"])), "bottles", "CONFIG WITH INTEGER ROUNDING")

    assumptions = datasets["assumptions"]
    add("ASSUME_01", "Governance", "Every exported assumption is flagged MY ASSUMPTION", assumptions["source"].eq("MY ASSUMPTION").all(), True,
        unit="boolean")
    add("ASSUME_02", "Governance", "No duplicate assumption IDs", assumptions["assumption_id"].is_unique, True,
        unit="boolean")
    add("ASSUME_03", "Governance", "Case-text verification field contains only Y/N",
        assumptions["VERIFIED_AGAINST_CASE_TEXT"].isin(["Y", "N"]).all(), True, unit="boolean")
    add("ASSUME_04", "Governance", "All case-marked rows remain unverified without source text",
        bool(assumptions.loc[assumptions["source"].eq("CASE-STATED"), "VERIFIED_AGAINST_CASE_TEXT"].eq("N").all()), True,
        unit="boolean")
    add("DATA_01", "Data quality", "Daily sales key is unique",
        not daily.duplicated(["date", "flavor_id", "channel_id", "depot_id"]).any(), True, unit="boolean")
    add("DATA_02", "Data quality", "Sales plus losses equal latent demand",
        int((daily["sales_bottles"] + daily["lost_sales_bottles"] - daily["true_demand_bottles"]).abs().sum()),
        0, 0, "bottles")
    add("DATA_03", "Data quality", "No negative realised sales", int((daily["sales_bottles"] < 0).sum()), 0, 0, "rows")

    return pd.DataFrame(rows)


def print_reconciliation(checks: pd.DataFrame) -> None:
    display = checks[["check_id", "check_name", "actual", "expected", "unit", "status"]].copy()
    for column in ["actual", "expected"]:
        display[column] = display[column].map(
            lambda value: f"{value:,.4f}" if isinstance(value, (float, np.floating)) else str(value)
        )
    print("\nRECONCILIATION CHECKS")
    print("=" * 110)
    print(display.to_string(index=False))
    print("=" * 110)
    counts = checks["status"].value_counts().to_dict()
    print(f"RESULT: {counts.get('PASS', 0)} PASS / {counts.get('FAIL', 0)} FAIL")


def write_reconciliation(checks: pd.DataFrame, output_dir: str = "data") -> None:
    from pathlib import Path
    path = Path(output_dir)
    checks.to_csv(path / "reconciliation_checks.csv", index=False)
    summary = {
        "status": "PASS" if checks["status"].eq("PASS").all() else "FAIL",
        "checks": len(checks),
        "passed": int(checks["status"].eq("PASS").sum()),
        "failed": int((~checks["status"].eq("PASS")).sum()),
        "volume_convention": "9.6 cr is latent summer demand; realised sales are separately shown after 8% censoring.",
    }
    with (path / "reconciliation_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
