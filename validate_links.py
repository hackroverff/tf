#!/usr/bin/env python3
"""Validate causal-link quantities and loss-attribution reconciliation."""
from src.config import load_config
from src.data_loader import load_datasets
from src.demand import detect_demand_anomalies, estimate_censored_demand, prepare_qc_signal
from src.links import attribution_reconciliation, build_causal_links, build_loss_attribution


def main() -> None:
    cfg = load_config()
    data = load_datasets()
    corrected = estimate_censored_demand(data["daily_sales"])
    signal = prepare_qc_signal(data["qc_sell_through"])
    alerts = detect_demand_anomalies(signal, min_history=int(cfg.number("A039")))
    metrics, edges = build_causal_links(data, corrected, alerts, cfg)
    print("CAUSAL LINK METRICS")
    for key in [
        "first_amber_date", "first_red_date", "sensing_lead_days", "launch_lead_gap_days",
        "previral_physical_cover_weeks", "closure_old_mix_cover_weeks",
        "closure_demand_weighted_cover_weeks", "viral4_pulp_requirement_uplift_pct",
        "pp_forced_production_cut_bottles", "pp_lost_revenue_cr", "stockout_censored_bottles",
        "air_freight_cost_cr", "rival_launch_lag_days",
    ]:
        value = metrics[key]
        print(f"{key}: {value:,.3f}" if isinstance(value, float) else f"{key}: {value}")
    print("\nQUANTIFIED EDGES")
    print(edges[["edge_type", "source", "target", "display", "source_flag"]].to_string(index=False))

    attribution = build_loss_attribution(cfg)
    print("\nLOSS ATTRIBUTION")
    print(attribution[["root_cause_id", "lost_contribution_cr", "air_freight_cr", "writeoff_discount_cr",
                       "economic_impact_cr", "low_economic_impact_cr", "high_economic_impact_cr",
                       "avoided_loss_low_cr", "avoided_loss_base_cr", "avoided_loss_high_cr"]].to_string(index=False))
    print("\nATTRIBUTION RECONCILIATION")
    checks = attribution_reconciliation(attribution, cfg)
    print(checks.to_string(index=False))
    print(f"\nAvoided loss LOW/BASE/HIGH: Rs{attribution['avoided_loss_low_cr'].sum():.2f} / "
          f"Rs{attribution['avoided_loss_base_cr'].sum():.2f} / Rs{attribution['avoided_loss_high_cr'].sum():.2f} cr")
    if not checks["status"].eq("PASS").all():
        raise SystemExit("Attribution reconciliation failed")
    print("LINK + ATTRIBUTION CHECKS: PASS")


if __name__ == "__main__":
    main()
