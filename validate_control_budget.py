#!/usr/bin/env python3
"""Validate lightweight control-tower calculations and selected budget."""
from src.budget import build_budget, budget_impact, budget_reconciliation
from src.config import load_config
from src.control_tower import control_tower_tiles, inventory_cover_snapshot, suggest_depot_transfers
from src.data_loader import load_datasets
from src.demand import detect_demand_anomalies, estimate_censored_demand, prepare_qc_signal
from src.links import build_loss_attribution
from src.supply import build_exposure_map


def main() -> None:
    cfg = load_config()
    data = load_datasets()
    corrected = estimate_censored_demand(data["daily_sales"])
    cover = inventory_cover_snapshot(
        corrected, data["depot_stock_weekly"], cfg.summer_end, int(cfg.number("A041")),
        int(cfg.case["depot_cover_days"]), int(cfg.number("A052")), int(cfg.number("A053")),
        int(cfg.number("A054")),
    )
    transfers = suggest_depot_transfers(
        cover, float(cfg.case["transfer_cost_per_bottle"]), int(cfg.case["transfer_min_days"]),
        int(cfg.case["transfer_max_days"]), float(cfg.case["price_per_bottle"]) * float(cfg.case["contribution_margin"]),
        cfg.number("A035"),
    )
    print("INVENTORY STATUS")
    print(cover.groupby(["inventory_status", "flavor_id"]).size().unstack(fill_value=0).to_string())
    print(f"\nTRANSFERS: {len(transfers)} suggestions; {transfers['transfer_bottles'].sum():,.0f} bottles; "
          f"cost Rs{transfers['transfer_cost_cr'].sum():.3f} cr; net Rs{transfers['net_expected_benefit_cr'].sum():.3f} cr")
    print(transfers.head(12).to_string(index=False))
    if not transfers.empty:
        outgoing = transfers.groupby(["flavor_id", "origin_depot_id"])["transfer_bottles"].sum()
        for (flavor, depot), quantity in outgoing.items():
            available = cover.loc[(cover["flavor_id"] == flavor) & (cover["depot_id"] == depot), "surplus_bottles"].iloc[0]
            assert quantity <= available + 1
        assert (transfers["net_expected_benefit_cr"] > 0).all()
        assert transfers["decision"].eq("HUMAN_APPROVAL_REQUIRED").all()

    alerts = detect_demand_anomalies(prepare_qc_signal(data["qc_sell_through"]), min_history=int(cfg.number("A039")))
    exposure = build_exposure_map(
        cfg.summer_end, data["pulp_inventory_daily"], cfg.tables["flavors"], cfg.tables["bom"],
        cfg.tables["suppliers"], cfg.tables["routes"],
    )
    tiles = control_tower_tiles(cfg, alerts, exposure, cover, transfers, cfg.summer_end)
    print("\nCONTROL TOWER")
    print(tiles[["area", "status", "metric", "value", "owner"]].to_string(index=False))
    assert set(tiles["area"]) == {"DEMAND", "SUPPLY", "INVENTORY", "DISTRIBUTION", "TRANSPORTATION"}

    budget, summary = build_budget(cfg)
    impact = budget_impact(build_loss_attribution(cfg), summary)
    print("\nSELECTED FIRST-YEAR BUDGET")
    print(budget[["item_id", "cost_cr", "cost_type", "selected", "selected_cost_cr"]].to_string(index=False))
    print(f"TOTAL: Rs{summary['total_cost_cr']:.3f} cr; headroom Rs{summary['headroom_cr']:.3f} cr; "
          f"one-time Rs{summary['one_time_build_cr']:.3f} cr; run+contingency Rs{summary['year1_run_cr']:.3f} cr")
    print("\nIMPACT")
    print(impact.to_string(index=False))
    checks = budget_reconciliation(cfg)
    print("\nCONTROL + BUDGET RECONCILIATION")
    print(checks.to_string(index=False))
    if not checks["status"].eq("PASS").all():
        raise SystemExit("Budget checks failed")
    print("CONTROL TOWER + BUDGET CHECKS: PASS")


if __name__ == "__main__":
    main()
