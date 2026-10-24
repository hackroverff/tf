"""Lightweight inventory, distribution and transportation control-tower logic."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import AppConfig
from .utils import CRORE


def inventory_cover_snapshot(
    corrected_daily: pd.DataFrame,
    depot_stock: pd.DataFrame,
    as_of: str | pd.Timestamp,
    history_days: int = 28,
    target_cover_days: int = 21,
    short_days: int = 14,
    overstock_days: int = 35,
    stale_after_days: int = 7,
) -> pd.DataFrame:
    """Compare latest depot stock with current demand-weighted 21-day need."""
    as_of = pd.Timestamp(as_of)
    snapshots = depot_stock[depot_stock["snapshot_date"] <= as_of]
    # Use the latest available snapshot per flavor × depot. If one depot misses
    # the newest weekly upload, its previous row survives and becomes STALE;
    # stale origins are excluded from transfer suggestions below.
    stock = snapshots.sort_values(["flavor_id", "depot_id", "snapshot_date"]).groupby(
        ["flavor_id", "depot_id"], group_keys=False
    ).tail(1).copy()
    start = as_of - pd.Timedelta(days=history_days - 1)
    history = corrected_daily[(corrected_daily["date"] >= start) & (corrected_daily["date"] <= as_of)]
    demand = history.groupby(["flavor_id", "depot_id"], as_index=False)["estimated_demand_bottles"].sum()
    demand["current_daily_demand_bottles"] = demand["estimated_demand_bottles"] / history_days
    # New flow-conserved stock already includes a trailing-sales field; current
    # corrected demand is a separate operational estimate and must not collide.
    stock = stock.drop(columns=["current_daily_demand_bottles"], errors="ignore")
    stock = stock.merge(demand[["flavor_id", "depot_id", "current_daily_demand_bottles"]], on=["flavor_id", "depot_id"], how="left")
    stock["current_daily_demand_bottles"] = stock["current_daily_demand_bottles"].fillna(0.0)
    stock["demand_weighted_need_bottles"] = stock["current_daily_demand_bottles"] * target_cover_days
    stock["cover_days_current_demand"] = np.where(
        stock["current_daily_demand_bottles"] > 0,
        stock["stock_bottles"] / stock["current_daily_demand_bottles"],
        np.inf,
    )
    stock["gap_to_target_bottles"] = stock["stock_bottles"] - stock["demand_weighted_need_bottles"]
    stock["surplus_bottles"] = stock["gap_to_target_bottles"].clip(lower=0)
    stock["deficit_bottles"] = (-stock["gap_to_target_bottles"]).clip(lower=0)
    stock["inventory_status"] = np.select(
        [stock["cover_days_current_demand"] < short_days, stock["cover_days_current_demand"] > overstock_days],
        ["SHORT", "OVERSTOCK"],
        default="WATCH",
    )
    stock.loc[stock["current_daily_demand_bottles"] <= 0, "inventory_status"] = "NO_CURRENT_DEMAND"
    stock["snapshot_age_days"] = (as_of - stock["snapshot_available_date"]).dt.days
    stock["stale_flag"] = stock["snapshot_age_days"] > stale_after_days
    stock["cover_basis"] = f"TRAILING_{history_days}D_CORRECTED_DEMAND_TARGET_{target_cover_days}D"
    return stock.sort_values(["flavor_id", "depot_id"]).reset_index(drop=True)


def suggest_depot_transfers(
    cover: pd.DataFrame,
    transfer_cost_per_bottle: float = 1.50,
    same_region_days: int = 2,
    cross_region_days: int = 4,
    contribution_per_bottle: float = 19.2,
    recovery_fraction: float = 0.70,
) -> pd.DataFrame:
    """Greedy surplus-to-deficit suggestions; origins retain 21-day cover."""
    rows = []
    work = cover[~cover["stale_flag"]].copy()
    for flavor in sorted(work["flavor_id"].unique()):
        subset = work[work["flavor_id"] == flavor]
        origins = subset[subset["surplus_bottles"] >= 1].sort_values("surplus_bottles", ascending=False)
        destinations = subset[subset["deficit_bottles"] >= 1].sort_values("cover_days_current_demand")
        remaining_origin = origins.set_index("depot_id")["surplus_bottles"].to_dict()
        origin_meta = origins.set_index("depot_id")
        for dest in destinations.itertuples():
            remaining_deficit = float(dest.deficit_bottles)
            if remaining_deficit < 1:
                continue
            for origin_id in sorted(remaining_origin, key=lambda d: remaining_origin[d], reverse=True):
                if remaining_deficit < 1:
                    break
                available = remaining_origin[origin_id]
                if available < 1 or origin_id == dest.depot_id:
                    continue
                quantity = int(np.floor(min(available, remaining_deficit)))
                if quantity < 1:
                    continue
                origin_region = str(origin_meta.loc[origin_id, "region"])
                days = same_region_days if origin_region == dest.region else cross_region_days
                transfer_cost = quantity * transfer_cost_per_bottle / CRORE
                recovered = quantity * recovery_fraction * contribution_per_bottle / CRORE
                net = recovered - transfer_cost
                if net <= 0:
                    continue
                rows.append({
                    "flavor_id": flavor,
                    "origin_depot_id": origin_id,
                    "origin_region": origin_region,
                    "destination_depot_id": dest.depot_id,
                    "destination_region": dest.region,
                    "transfer_bottles": quantity,
                    "transit_days": days,
                    "transfer_cost_cr": transfer_cost,
                    "expected_recovered_contribution_cr": recovered,
                    "net_expected_benefit_cr": net,
                    "recovery_fraction_assumption": recovery_fraction,
                    "origin_cover_preserved_days": 21,
                    "decision": "HUMAN_APPROVAL_REQUIRED",
                })
                remaining_origin[origin_id] -= quantity
                remaining_deficit -= quantity
    if not rows:
        return pd.DataFrame(columns=[
            "flavor_id", "origin_depot_id", "destination_depot_id", "transfer_bottles", "transit_days",
            "transfer_cost_cr", "expected_recovered_contribution_cr", "net_expected_benefit_cr", "decision",
        ])
    return pd.DataFrame(rows).sort_values("net_expected_benefit_cr", ascending=False).reset_index(drop=True)


def control_tower_tiles(
    config: AppConfig,
    alerts: pd.DataFrame,
    exposure: pd.DataFrame,
    cover: pd.DataFrame,
    transfers: pd.DataFrame,
    as_of: str | pd.Timestamp,
    passion_demand_cover_weeks: float | None = None,
) -> pd.DataFrame:
    """Five lightweight tiles on one shared operational data model."""
    as_of = pd.Timestamp(as_of)
    dp = alerts[(alerts["flavor_id"] == "DP") & (alerts["date"] <= as_of)]
    latest_alert = dp.sort_values("date").iloc[-1] if not dp.empty else None
    demand_status = str(latest_alert["alert_status"]) if latest_alert is not None else ("AMBER" if alerts.empty else "GREEN")
    demand_value = "Unavailable" if alerts.empty else (f"{float(latest_alert['signal_ratio']):.2f}× baseline" if latest_alert is not None and pd.notna(latest_alert["signal_ratio"]) else "No baseline")
    passion = exposure[exposure["pulp_id"] == "PASSION"].iloc[0]
    supply_cover = passion_demand_cover_weeks if passion_demand_cover_weeks is not None else float(passion["current_cover_weeks"])
    short = cover[cover["inventory_status"] == "SHORT"]
    overstock = cover[cover["inventory_status"] == "OVERSTOCK"]
    closure_active = config.closure_start <= as_of <= config.closure_end
    inventory_status = "AMBER" if cover.empty else ("RED" if not short.empty and not overstock.empty else ("AMBER" if not short.empty or not overstock.empty else "GREEN"))
    inventory_value = "Unavailable" if cover.empty else f"{len(short)} / {len(overstock)}"
    inventory_detail = "Depot workbook missing; stock unknown and transfers suppressed" if cover.empty else f"Short flavors={short['flavor_id'].nunique()}; overstocked flavors={overstock['flavor_id'].nunique()}; 21d current-demand target"
    rows = [
        {
            "area": "DEMAND",
            "status": demand_status,
            "metric": "DP QC signal",
            "value": demand_value,
            "detail": "QC feed missing; detector disabled and proxy uncertainty widened" if alerts.empty else f"Latest status {demand_status}; daily QC, weekly reforecast; GT remains proxy-only",
            "recommended_action": "Named planner validates alert and refreshes bottles + pulp",
            "owner": "Demand Planner",
        },
        {
            "area": "SUPPLY",
            "status": str(passion["risk_flag"]),
            "metric": "Passionfruit cover / exposure",
            "value": f"{supply_cover:.2f} weeks / ₹{float(passion['dependent_revenue_cr']):.1f} cr",
            "detail": "Single source + single route; fixed plant capacity and co-packer notice apply",
            "recommended_action": "Review frozen buffer, alternate supplier and allocation options",
            "owner": "Supply Planner + Procurement",
        },
        {
            "area": "INVENTORY",
            "status": inventory_status,
            "metric": "Short / overstocked flavor-depots",
            "value": inventory_value,
            "detail": inventory_detail,
            "recommended_action": "Rebalance weekly cover; hold structural buffer in frozen pulp",
            "owner": "Inventory Planner",
        },
        {
            "area": "DISTRIBUTION",
            "status": "AMBER" if cover.empty or not transfers.empty else "GREEN",
            "metric": "Suggested transfers / net benefit",
            "value": "Unavailable" if cover.empty else (f"{len(transfers)} / ₹{transfers['net_expected_benefit_cr'].sum():.2f} cr" if not transfers.empty else "0 / ₹0"),
            "detail": "Depot stock unknown; transfers suppressed" if cover.empty else "2–4 days; ₹1.50/bottle; origins retain target cover; 70% recovery assumption",
            "recommended_action": "Depot planner modifies/approves lane-feasible transfers",
            "owner": "Depot Planner",
        },
        {
            "area": "TRANSPORTATION",
            "status": "RED" if closure_active else "AMBER",
            "metric": "Passion route closure likelihood",
            "value": f"{float(config.case['passion_closure_probability']):.0%}" + ("; CLOSED" if closure_active else ""),
            "detail": f"Air fallback 5×; actual emergency ₹{float(config.case['air_freight_cost_cr']):.2f} cr; manual weather input is stale-labelled",
            "recommended_action": "Trigger COO review when route warning or cover < lead + buffer fires",
            "owner": "Procurement + COO",
        },
    ]
    return pd.DataFrame(rows)
