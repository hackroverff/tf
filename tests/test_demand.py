from __future__ import annotations

import numpy as np
import pandas as pd

from src.demand import (
    build_demand_scenarios,
    detect_demand_anomalies,
    estimate_censored_demand,
    first_alerts,
)


def flat_then_viral_signal() -> pd.DataFrame:
    values = [100.0] * 20 + [160.0, 160.0] + [400.0] * 3
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=len(values), freq="D"),
        "flavor_id": "DP",
        "channel_id": "QC",
        "signal_bottles": values,
    })


def test_detector_requires_consecutive_days_and_emits_red() -> None:
    alerts = detect_demand_anomalies(flat_then_viral_signal())
    assert alerts.loc[20, "alert_status"] == "NORMAL"  # first amber-ratio day
    assert alerts.loc[21, "alert_status"] == "AMBER"  # second consecutive day
    assert alerts.loc[22, "alert_status"] == "AMBER"  # first red-ratio day
    assert alerts.loc[24, "alert_status"] == "RED"    # third consecutive red-ratio day
    dates = first_alerts(alerts)
    assert dates["AMBER"] == pd.Timestamp("2026-01-22")
    assert dates["RED"] == pd.Timestamp("2026-01-25")


def test_detector_is_stable_on_flat_series_and_shifts_baseline() -> None:
    values = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=30),
        "flavor_id": "MPB",
        "signal_bottles": 100.0,
    })
    alerts = detect_demand_anomalies(values)
    assert alerts["alert_status"].eq("NORMAL").all()
    assert alerts.loc[:4, "rolling_baseline"].isna().all()
    assert alerts.loc[5, "rolling_baseline"] == 100.0
    # If the current point leaked into its own baseline, this ratio would be lower.
    assert np.isclose(alerts.loc[5, "signal_ratio"], 1.0)


def test_detector_threshold_validation() -> None:
    signal = flat_then_viral_signal()
    try:
        detect_demand_anomalies(signal, amber_multiplier=2.0, red_multiplier=1.5)
    except ValueError as error:
        assert "amber_multiplier" in str(error)
    else:
        raise AssertionError("Invalid thresholds should fail clearly")


def test_censoring_correction_uses_history_not_ground_truth() -> None:
    rows = []
    for i, date in enumerate(pd.date_range("2026-01-01", periods=20)):
        stocked_out = i >= 17
        rows.append({
            "date": date,
            "flavor_id": "DP",
            "channel_id": "QC",
            "depot_id": "D01",
            "sales_bottles": 0 if stocked_out else 100,
            "stockout_flag": int(stocked_out),
            "distributor_orders_bottles": 0,
            # Deliberately absurd: an operational correction must not read this.
            "true_demand_bottles": 999999,
        })
    corrected = estimate_censored_demand(pd.DataFrame(rows))
    assert corrected.loc[:16, "estimated_demand_bottles"].eq(100).all()
    assert corrected.loc[17:, "estimated_demand_bottles"].eq(100).all()
    assert corrected.loc[17:, "censoring_confidence"].eq("LOW").all()


def test_gt_stockout_uses_orders_as_labelled_proxy() -> None:
    daily = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=6),
        "flavor_id": "DP",
        "channel_id": "GT",
        "depot_id": "D01",
        "sales_bottles": [100, 100, 100, 100, 20, 20],
        "stockout_flag": [0, 0, 0, 0, 1, 1],
        "distributor_orders_bottles": [0, 0, 0, 0, 140, 140],
    })
    corrected = estimate_censored_demand(daily, window=3)
    assert corrected.loc[4, "estimated_demand_bottles"] == 140
    assert corrected.loc[4, "censoring_method"] == "GT_DISTRIBUTOR_ORDER_PROXY"
    assert corrected.loc[4, "censoring_confidence"] == "MEDIUM"


def test_scenarios_convert_bottles_to_pulp() -> None:
    dates = pd.date_range("2026-01-01", periods=28)
    daily = pd.DataFrame({
        "date": dates,
        "flavor_id": "DP",
        "channel_id": "QC",
        "depot_id": "D01",
        "sales_bottles": 100,
        "estimated_demand_bottles": 100,
    })
    bom = pd.DataFrame({"flavor_id": ["DP"], "pulp_id": ["PASSION"], "kg_per_bottle": [0.06]})
    bottles, pulp = build_demand_scenarios(daily, bom, dates.max(), horizon_weeks=1, history_days=28)
    base = bottles[bottles["scenario"] == "BASE"].iloc[0]
    viral = bottles[bottles["scenario"] == "VIRAL_4X"].iloc[0]
    assert base["scenario_bottles"] == 700
    assert viral["scenario_bottles"] == 2800
    assert np.isclose(pulp[pulp["scenario"] == "VIRAL_4X"]["pulp_requirement_kg"].iloc[0], 168.0)
