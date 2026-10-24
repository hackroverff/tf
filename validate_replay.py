#!/usr/bin/env python3
"""Validate the counterfactual timeline and impact ranges."""
from src.config import load_config
from src.data_loader import load_datasets
from src.demand import detect_demand_anomalies, estimate_censored_demand, prepare_qc_signal
from src.links import build_loss_attribution
from src.replay import build_scenario_replay, replay_as_of, replay_reconciliation
from src.supply import optimise_buffer, passionfruit_requirement_profile


def main() -> None:
    cfg = load_config()
    data = load_datasets()
    corrected = estimate_censored_demand(data["daily_sales"])
    alerts = detect_demand_anomalies(prepare_qc_signal(data["qc_sell_through"]), min_history=int(cfg.number("A039")))
    attribution = build_loss_attribution(cfg)
    profile = passionfruit_requirement_profile(corrected, cfg.tables["bom"], cfg.closure_start, 28, 19.2)
    passion = data["pulp_inventory_daily"].loc[
        (data["pulp_inventory_daily"]["date"] == cfg.closure_start) &
        (data["pulp_inventory_daily"]["pulp_id"] == "PASSION")
    ].iloc[0]
    _, best = optimise_buffer(
        profile["daily_pulp_kg"], float(passion["opening_kg"]), profile["contribution_per_kg"], 180.0,
        max_buffer_weeks=int(cfg.number("A046")), annual_closure_probability=0.60,
        conditional_weights={1: cfg.number("A031"), 2: cfg.number("A032"), 3: cfg.number("A033")},
        annual_carry_rate=cfg.number("A029"), cold_storage_rate=cfg.number("A030"),
    )
    daily, actions, avoided = build_scenario_replay(
        cfg, data, corrected, alerts, attribution, float(best["buffer_weeks"])
    )
    print("REPLAY ACTIONS")
    print(actions[["date", "area", "what_actually_happened", "with_the_model", "approver", "decision_status"]].to_string(index=False))
    print("\nAVOIDED LOSS SUMMARY")
    for key, value in avoided.items():
        print(f"{key}: {value:,.2f}" if isinstance(value, float) else f"{key}: {value}")
    selected = replay_as_of(daily, actions, cfg.closure_start)
    print(f"\nAs of {cfg.closure_start.date()}: {len(selected['actions_to_date'])} actions visible; "
          f"{len(selected['upcoming_actions'])} upcoming shown; no future rows in daily={selected['daily_to_date']['date'].max().date()}")
    assert selected["daily_to_date"]["date"].max() == cfg.closure_start
    checks = replay_reconciliation(actions, avoided, cfg)
    print("\nREPLAY RECONCILIATION")
    print(checks.to_string(index=False))
    if not checks["status"].eq("PASS").all():
        raise SystemExit("Replay checks failed")
    print("SCENARIO REPLAY CHECKS: PASS")


if __name__ == "__main__":
    main()
