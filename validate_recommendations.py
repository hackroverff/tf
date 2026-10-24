#!/usr/bin/env python3
"""Validate risk completeness and the human approval state machine."""
import pandas as pd

from src.config import load_config
from src.data_loader import load_datasets
from src.demand import detect_demand_anomalies, estimate_censored_demand, launch_readiness_gate, prepare_qc_signal
from src.links import build_causal_links, build_loss_attribution
from src.recommendations import apply_decision, approval_summary, build_risk_register, empty_approval_log


def main() -> None:
    cfg = load_config()
    data = load_datasets()
    corrected = estimate_censored_demand(data["daily_sales"])
    alerts = detect_demand_anomalies(prepare_qc_signal(data["qc_sell_through"]), min_history=int(cfg.number("A039")))
    metrics, _ = build_causal_links(data, corrected, alerts, cfg)
    attribution = build_loss_attribution(cfg)
    status, _ = launch_readiness_gate(
        data["pulp_inventory_daily"], cfg.tables["bom"], cfg.tables["suppliers"], "DP", cfg.launch_date,
        int(cfg.number("A027")), int(cfg.case["launch_notice_days"]), data["production_daily"],
    )
    risks = build_risk_register(cfg, metrics, attribution, status, 0.057142)
    required = ["what_fired", "why_fired", "severity", "amount_base_cr", "recommended_action", "owner_role", "approver_role", "deadline"]
    assert not risks[required].isna().any().any()
    assert risks["status"].eq("PROPOSED").all()
    assert risks["execution_status"].eq("NOT_EXECUTED_HUMAN_DECISION_ONLY").all()
    print("RISK REGISTER")
    print(risks[["risk_id", "area", "severity", "amount_base_cr", "owner_role", "approver_role", "deadline", "status"]].to_string(index=False))
    log = empty_approval_log()
    risks, log = apply_decision(risks, log, "R003", "MODIFY", "COO", "Stage investment", "Approve one-week frozen buffer first", "2026-04-01")
    risks, log = apply_decision(risks, log, "R003", "APPROVE", "COO", "Proceed with human-approved buffer", timestamp="2026-04-02")
    risks, log = apply_decision(risks, log, "R005", "REJECT", "S&OP Lead", "Capacity is not the binding route constraint", timestamp="2026-04-02")
    print("\nAPPROVAL LOG")
    print(log.to_string(index=False))
    print("\nSUMMARY", approval_summary(risks))
    assert len(log) == 3
    assert log["execution_status"].eq("NOT_EXECUTED_HUMAN_DECISION_ONLY").all()
    print("RECOMMENDATION + APPROVAL CHECKS: PASS")


if __name__ == "__main__":
    main()
