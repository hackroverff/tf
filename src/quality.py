"""Data-quality checks and explicit degradation paths for missing feeds."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import AppConfig


QC_SCHEMA = [
    "date", "flavor_id", "depot_id", "sell_through_bottles", "stockout_flag",
    "marketing_available_date", "planner_consolidated_available_date", "feed_grain",
]
DEPOT_SCHEMA = [
    "snapshot_date", "snapshot_available_date", "flavor_id", "depot_id", "region",
    "stock_bottles", "allocation_basis", "last_year_mix_cover_days", "stock_profile",
]


def apply_missing_feed_fallbacks(datasets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Inject empty optional-feed schemas so analytics can degrade, not crash."""
    result = dict(datasets)
    statuses = []
    for name, schema, impact in [
        ("qc_sell_through", QC_SCHEMA, "Detector disabled; proxy-only demand; uncertainty widened"),
        ("depot_stock_weekly", DEPOT_SCHEMA, "Cover unknown; transfers suppressed; uncertainty widened"),
    ]:
        available = name in result and not result[name].empty
        if not available:
            empty = pd.DataFrame(columns=schema)
            for column in set(schema) & {"date", "snapshot_date", "snapshot_available_date", "marketing_available_date", "planner_consolidated_available_date"}:
                empty[column] = pd.to_datetime(empty[column])
            result[name] = empty
        statuses.append({
            "feed": name,
            "status": "FRESH" if available else "MISSING_FALLBACK_ACTIVE",
            "impact": "Normal analytics" if available else impact,
            "uncertainty_half_width_pct": 20.0 if available else 40.0,
        })
    result["feed_fallbacks"] = pd.DataFrame(statuses)
    return result


def run_data_quality_checks(datasets: dict[str, pd.DataFrame], config: AppConfig) -> pd.DataFrame:
    rows = []

    def add(area: str, check: str, passed: bool, detail: str, fallback: str, severity: str = "ERROR") -> None:
        rows.append({
            "area": area,
            "check": check,
            "status": "PASS" if passed else ("WARN" if severity == "WARN" else "FAIL"),
            "detail": detail,
            "fallback_if_failed": fallback,
            "severity_if_failed": severity,
        })

    for name in ["daily_sales", "qc_sell_through", "depot_stock_weekly", "pulp_inventory_daily", "production_daily"]:
        optional = name in {"qc_sell_through", "depot_stock_weekly"}
        add("COMPLETENESS", f"{name}.csv present", name in datasets and not datasets[name].empty,
            f"{len(datasets.get(name, [])):,} rows",
            "Degrade with stale/proxy labels and wider uncertainty" if optional else "Stop and request a corrected core extract",
            "WARN" if optional else "ERROR")
    daily = datasets["daily_sales"]
    add("KEYS", "Daily sales key unique", not daily.duplicated(["date", "flavor_id", "channel_id", "depot_id"]).any(),
        "date × flavor × channel × depot", "Reject duplicate rows and request corrected vendor extract")
    add("VALUES", "No negative sales or demand", bool((daily[["sales_bottles", "true_demand_bottles", "lost_sales_bottles"]] >= 0).all().all()),
        "All numeric bottle values non-negative", "Set invalid rows to unknown; widen uncertainty and flag owner")
    add("CONSISTENCY", "Sales + lost = latent demand", bool(((daily["sales_bottles"] + daily["lost_sales_bottles"]) == daily["true_demand_bottles"]).all()),
        "Row-level identity holds", "Block reconciliation and do not publish scenarios")
    add("COVERAGE", "181 daily dates", daily["date"].nunique() == 181,
        f"{daily['date'].nunique()} dates from {daily['date'].min().date()} to {daily['date'].max().date()}",
        "Use available dates only; label incomplete horizon")
    qc = datasets["qc_sell_through"]
    latest_qc = qc["date"].max() if not qc.empty else pd.NaT
    add("FRESHNESS", "QC feed reaches 30 June", latest_qc == config.summer_end,
        f"Latest QC={latest_qc.date() if pd.notna(latest_qc) else 'unavailable'}", "Disable detector; use weekly secondary sales/orders; widen uncertainty", "WARN")
    stock = datasets["depot_stock_weekly"]
    latest = stock["snapshot_date"].max() if not stock.empty else pd.NaT
    depot_counts = stock[stock["snapshot_date"] == latest]["depot_id"].nunique() if not stock.empty else 0
    add("COMPLETENESS", "Latest weekly sheet has nine depots", depot_counts == int(config.case["depot_count"]),
        f"Latest={latest.date() if pd.notna(latest) else 'unavailable'}; depots={depot_counts}", "Carry last snapshot forward as STALE; suppress affected transfers", "WARN")
    inventory = datasets["pulp_inventory_daily"]
    add("VALUES", "Pulp closing stock non-negative", bool((inventory["closing_kg"] >= -1e-6).all()),
        f"Minimum={inventory['closing_kg'].min():.4f} kg", "Block buffer recommendation and investigate balance", "ERROR")
    add("CONFIG", "Flavor and channel shares sum to one",
        np.isclose(config.tables["flavors"]["summer_share"].sum(), 1) and np.isclose(config.tables["channels"]["summer_share"].sum(), 1),
        "Config-driven mix is valid", "Stop generation and show config error")
    add("CONFIG", "Every pulp has a supplier and route",
        set(config.tables["pulps"]["pulp_id"]) == set(config.tables["suppliers"]["pulp_id"]),
        f"{len(config.tables['pulps'])} pulps linked", "Flag unmapped pulp; do not calculate cover")
    return pd.DataFrame(rows)


def feed_fallback_assessment(qc_available: bool, depot_sheet_available: bool, config: AppConfig) -> tuple[pd.DataFrame, float]:
    """Demonstrate graceful fallback without deleting the real synthetic files."""
    rows = [
        {
            "feed": "Daily QC sell-through",
            "available": qc_available,
            "status": "FRESH" if qc_available else "MISSING_SIMULATED",
            "analytics_impact": "Amber/Red detector active" if qc_available else "Detector disabled; use depot secondary sales + distributor orders as proxy",
            "owner_action": "Demand planner checks daily freshness" if qc_available else "Vendor IT alerted; demand planner labels low-confidence proxy",
        },
        {
            "feed": "Weekly depot workbook",
            "available": depot_sheet_available,
            "status": "FRESH" if depot_sheet_available else "MISSING_SIMULATED",
            "analytics_impact": "Current-mix cover and transfers active" if depot_sheet_available else "Carry last snapshot as STALE; suppress transfers from unknown stock",
            "owner_action": "Depot planner uploads weekly" if depot_sheet_available else "Depot owner alerted; S&OP sees stale banner",
        },
    ]
    uncertainty = config.number("A037") if qc_available and depot_sheet_available else config.number("A038")
    return pd.DataFrame(rows), float(uncertainty)


def data_model_links() -> pd.DataFrame:
    """One set of keys linking all five control-tower areas."""
    rows = [
        ("Calendar", "date / week_start / month_start", "All", "Shared event and planning clock"),
        ("Flavor", "flavor_id", "Demand, Supply, Inventory, Distribution", "Shares, BOM, sales, stock and allocation"),
        ("Channel", "channel_id", "Demand, Inventory, Distribution", "GT/MT/QC mix, signal visibility and delisting risk"),
        ("Depot / Region", "depot_id / region", "Demand, Inventory, Distribution", "Secondary sales, weekly stock and transfers"),
        ("Pulp", "pulp_id", "Demand, Supply, Transportation", "BOM translation, cover, buffers and shortages"),
        ("Supplier / Route", "supplier_id / route_id", "Supply, Transportation", "Lead time, single-source and closure exposure"),
        ("Capacity asset", "asset_id / month_start", "Supply, Demand scenarios", "Fixed plants and conditional co-packer"),
        ("Decision", "risk_id / log_id", "All", "Human approval and non-execution audit trail"),
    ]
    return pd.DataFrame(rows, columns=["entity", "keys", "areas_used", "purpose"])
