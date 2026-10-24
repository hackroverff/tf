from __future__ import annotations

from dataclasses import replace

import pandas as pd

from src.config import load_config
from src.data_generator import SyntheticDataGenerator
from src.reconciliation import reconcile


def test_generator_scales_by_adding_config_rows_without_code_changes() -> None:
    """Add one flavor, depot and channel; no generator code is special-cased for them."""
    cfg = load_config()
    tables = {name: frame.copy() for name, frame in cfg.tables.items()}

    flavors = tables["flavors"]
    flavors["summer_share"] *= 0.99
    new_flavor = flavors.iloc[[0]].copy()
    new_flavor.loc[:, ["flavor_id", "flavor_name", "summer_share", "available_from_md", "is_new"]] = ["TEST_F", "Config Test Flavor", 0.01, "01-01", 0]
    tables["flavors"] = pd.concat([flavors, new_flavor], ignore_index=True)
    last_year = tables["last_year_mix"]
    last_year["last_year_share"] *= 0.99
    new_mix = last_year.iloc[[0]].copy()
    new_mix.loc[:, ["flavor_id", "last_year_share"]] = ["TEST_F", 0.01]
    tables["last_year_mix"] = pd.concat([last_year, new_mix], ignore_index=True)
    bom = tables["bom"]
    tables["bom"] = pd.concat([bom, pd.DataFrame([{"flavor_id": "TEST_F", "pulp_id": "MANGO", "kg_per_bottle": 0.15, "source": "MY ASSUMPTION", "VERIFIED_AGAINST_CASE_TEXT": "N"}])], ignore_index=True)

    depots = tables["depots"]
    depots["demand_weight"] *= 0.99
    new_depot = depots.iloc[[0]].copy()
    new_depot.loc[:, ["depot_id", "depot_name", "demand_weight", "stock_profile"]] = ["D10", "Config Test Depot", 0.01, "BALANCED"]
    tables["depots"] = pd.concat([depots, new_depot], ignore_index=True)

    channels = tables["channels"]
    channels["summer_share"] *= 0.99
    new_channel = channels.iloc[[0]].copy()
    new_channel.loc[:, ["channel_id", "channel_name", "summer_share"]] = ["TEST_C", "Config Test Channel", 0.01]
    tables["channels"] = pd.concat([channels, new_channel], ignore_index=True)
    shelf = tables["channel_shelf_life"]
    new_shelf = shelf[shelf["channel_id"] == "GT"].iloc[[0]].copy()
    new_shelf.loc[:, ["channel_id", "min_remaining_days"]] = ["TEST_C", 0]
    tables["channel_shelf_life"] = pd.concat([shelf, new_shelf], ignore_index=True)

    scaled_config = replace(cfg, tables=tables)
    scaled = SyntheticDataGenerator(scaled_config).generate()
    daily = scaled["daily_sales"]
    summer = daily[daily["season"] == "SUMMER"]
    assert set(["TEST_F", "DP"]).issubset(set(daily["flavor_id"]))
    assert "D10" in set(daily["depot_id"])
    assert "TEST_C" in set(daily["channel_id"])
    assert summer["true_demand_bottles"].sum() == 96_000_000
    # Joint flavor×channel integer apportionment can move a few remainder
    # bottles between groups; the configured total remains exact.
    assert abs(summer.loc[summer["flavor_id"] == "TEST_F", "true_demand_bottles"].sum() - 960_000) <= 20
    assert not daily[(daily["flavor_id"] == "TEST_F") & (daily["depot_id"] == "D10") & (daily["channel_id"] == "TEST_C")].empty
    checks = reconcile(scaled, scaled_config)
    failures = checks[checks["status"] == "FAIL"]
    assert failures.empty, failures[["check_id", "actual", "expected"]].to_dict("records")
