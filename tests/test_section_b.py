from __future__ import annotations

import pandas as pd
import pytest

from src.config import load_config
from src.recommendations import apply_decision, empty_approval_log
from src.sensitivity import avoided_loss_range, scenario_config
from src.supply import calculate_buffer_option, constrained_weekly_planner, optimise_buffer
from src.links import build_loss_attribution


def test_air_premium_is_in_objective_and_break_even_identity() -> None:
    kwargs = dict(
        daily_pulp_requirement_kg=100.0,
        existing_pulp_kg=0.0,
        contribution_per_kg=100.0,
        normal_pulp_cost_per_kg=2.0,
        conditional_weights={1: 0.2, 2: 0.3, 3: 0.5},
        annual_carry_rate=0.18,
        cold_storage_rate=0.08,
        air_cost_multiplier=5.0,
    )
    table, best = optimise_buffer(max_buffer_weeks=4, annual_closure_probability=0.6, **kwargs)
    for row in table.itertuples():
        assert row.expected_total_cost_cr == pytest.approx(
            row.annual_carry_and_storage_cr + row.expected_stockout_loss_cr + row.expected_air_premium_cr
        )
    probability = float(best["break_even_closure_probability"])
    assert 0 < probability < 1
    zero = calculate_buffer_option(0, annual_closure_probability=probability, **kwargs)
    selected = calculate_buffer_option(float(best["buffer_weeks"]), annual_closure_probability=probability, **kwargs)
    assert selected["expected_total_cost_cr"] == pytest.approx(zero["expected_total_cost_cr"])


def test_copacker_output_cannot_consume_unavailable_pulp() -> None:
    scenarios = pd.DataFrame({
        "scenario": ["VIRAL_4X", "VIRAL_4X"],
        "week_start": [pd.Timestamp("2026-07-06"), pd.Timestamp("2026-07-13")],
        "flavor_id": ["DP", "DP"],
        "scenario_bottles": [1_000_000.0, 1_000_000.0],
    })
    bom = pd.DataFrame({"flavor_id": ["DP"], "pulp_id": ["PASSION"], "kg_per_bottle": [0.06]})
    plan = constrained_weekly_planner(
        scenarios, pd.Timestamp("2026-06-30"), copacker_notice_given=True,
        bom=bom, opening_pulp_kg={"PASSION": 100.0},
    )
    assert (plan["closing_passion_kg"] >= -1e-8).all()
    consumed = ((plan["in_house_planned_bottles"] + plan["copacker_used_bottles"]) * 0.06).sum()
    assert consumed <= 100.0 + 1e-8
    assert plan["unmet_bottles"].sum() > 0
    assert plan["pulp_feasibility_rule"].eq("OPENING_STOCK_ONLY_IN_HOUSE_FIRST_CARRY_FORWARD").all()


def test_peak_tradeoff_requires_coo_and_logs_action() -> None:
    risks = pd.DataFrame({
        "risk_id": ["R_PEAK"],
        "status": ["PROPOSED"],
        "recommended_action": ["Approve two-week frozen buffer"],
        "owner_role": ["Planner"],
        "approver_role": ["COO"],
        "peak_season_tradeoff": [True],
        "execution_status": ["NOT_EXECUTED_HUMAN_DECISION_ONLY"],
    })
    with pytest.raises(ValueError, match="COO"):
        apply_decision(risks, empty_approval_log(), "R_PEAK", "APPROVE", "S&OP Lead")
    updated, log = apply_decision(
        risks, empty_approval_log(), "R_PEAK", "APPROVE", "COO", timestamp="2026-04-01 09:30"
    )
    assert updated.loc[0, "status"] == "APPROVED"
    assert log.loc[0, "approver_role"] == "COO"
    assert log.loc[0, "action"] == "Approve two-week frozen buffer"
    assert log.loc[0, "execution_status"] == "NOT_EXECUTED_HUMAN_DECISION_ONLY"


def test_one_click_controls_propagate_and_range_is_not_simulation() -> None:
    config = load_config()
    changed = scenario_config(
        config, root_cause_profile="EQUAL", capture_multiplier=1.5,
        closure_probability=0.45, qc_share=0.30,
    )
    assert changed.tables["loss_attribution"]["lost_contribution_share"].sum() == pytest.approx(1.0)
    assert changed.tables["loss_attribution"]["base_capture"].max() <= 1.0
    assert changed.case["passion_closure_probability"] == 0.45
    assert changed.tables["routes"].set_index("route_id").loc["R_PASSION", "summer_closure_probability"] == 0.45
    assert changed.tables["channels"]["summer_share"].sum() == pytest.approx(1.0)
    assert changed.tables["channels"].set_index("channel_id").loc["QC", "summer_share"] == 0.30
    range_table = avoided_loss_range(build_loss_attribution(changed))
    assert range_table["scenario"].tolist() == ["LOW", "BASE", "HIGH"]
    assert range_table["estimation_basis"].eq("ASSUMPTION-BASED, NOT SIMULATED").all()
    assert (range_table["effective_capture_rate"] >= 0).all()
