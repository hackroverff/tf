from __future__ import annotations

import pandas as pd

from src.analysis import build_analysis
from src.config import load_config
from src.control_tower import inventory_cover_snapshot, suggest_depot_transfers
from src.data_loader import load_datasets
from src.demand import estimate_censored_demand
from src.quality import apply_missing_feed_fallbacks


PARAMS = {
    "baseline_window": 14,
    "amber_multiplier": 1.5,
    "amber_days": 2,
    "red_multiplier": 2.0,
    "red_days": 3,
    "min_history": 5,
}


def test_missing_qc_and_depot_files_degrade_entire_analysis() -> None:
    cfg = load_config()
    data = load_datasets()
    data.pop("qc_sell_through")
    data.pop("depot_stock_weekly")
    data = apply_missing_feed_fallbacks(data)
    analysis = build_analysis(cfg, data, PARAMS)
    assert analysis["feed_degraded"]
    assert analysis["scenario_uncertainty_pct"] == 40
    assert analysis["alerts"].empty
    assert analysis["cover"].empty
    assert analysis["transfers"].empty
    assert analysis["avoided"]["first_red"] == "Not triggered"
    assert analysis["tiles"].set_index("area").loc["INVENTORY", "status"] == "AMBER"
    assert analysis["tiles"].set_index("area").loc["DISTRIBUTION", "status"] == "AMBER"
    statuses = set(analysis["quality_checks"]["status"])
    assert "WARN" in statuses and "FAIL" not in statuses
    scenario = analysis["bottle_scenarios"].iloc[0]
    assert scenario["low_bottles"] < scenario["scenario_bottles"] < scenario["high_bottles"]


def test_missing_recent_depot_upload_carries_last_snapshot_as_stale() -> None:
    cfg = load_config()
    data = load_datasets()
    stock = data["depot_stock_weekly"]
    latest_two = sorted(stock["snapshot_date"].unique())[-2:]
    degraded = stock[~((stock["depot_id"] == "D01") & (stock["snapshot_date"].isin(latest_two)))].copy()
    corrected = estimate_censored_demand(data["daily_sales"])
    cover = inventory_cover_snapshot(corrected, degraded, cfg.summer_end, stale_after_days=7)
    d01 = cover[cover["depot_id"] == "D01"]
    assert len(d01) == 5
    assert d01["stale_flag"].all()
    assert d01["snapshot_date"].max() < max(latest_two)
    transfers = suggest_depot_transfers(cover)
    assert transfers.empty or not transfers[["origin_depot_id", "destination_depot_id"]].isin(["D01"]).any().any()
