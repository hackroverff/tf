from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.supply import (
    calculate_buffer_option,
    closure_loss_scenarios,
    constrained_weekly_planner,
    optimise_buffer,
    shortage_allocation_options,
)


def test_buffer_calculation_exact_one_week_closure() -> None:
    kwargs = dict(
        daily_pulp_requirement_kg=100.0,
        existing_pulp_kg=0.0,
        contribution_per_kg=10.0,
        normal_pulp_cost_per_kg=2.0,
        annual_closure_probability=1.0,
        conditional_weights={1: 1.0, 2: 0.0, 3: 0.0},
        annual_carry_rate=0.10,
        cold_storage_rate=0.0,
    )
    zero = calculate_buffer_option(0, **kwargs)
    one = calculate_buffer_option(1, **kwargs)
    assert zero["expected_stockout_loss_cr"] == pytest.approx(7_000.0 / 10_000_000)
    assert one["buffer_kg"] == 700.0
    assert one["expected_stockout_loss_cr"] == 0.0
    assert one["buffer_working_capital_cr"] == pytest.approx(1_400.0 / 10_000_000)
    assert one["annual_carry_and_storage_cr"] == pytest.approx(140.0 / 10_000_000)
    assert one["expected_total_cost_cr"] == pytest.approx(one["annual_carry_and_storage_cr"])


def test_existing_cover_reduces_shortage_before_new_buffer() -> None:
    scenarios = closure_loss_scenarios(
        daily_pulp_requirement_kg=100,
        existing_pulp_kg=350,
        contribution_per_kg=20,
        normal_pulp_cost_per_kg=2,
        annual_closure_probability=0.6,
        conditional_weights={1: 1.0, 2: 0.0, 3: 0.0},
    )
    row = scenarios.iloc[0]
    assert row["shortage_kg"] == 350
    assert row["annual_probability"] == 0.6
    assert row["expected_contribution_loss_cr"] == pytest.approx(0.6 * 350 * 20 / 10_000_000)


def test_buffer_search_has_monotonic_loss_and_respects_shelf_life() -> None:
    table, best = optimise_buffer(
        daily_pulp_requirement_kg=100,
        existing_pulp_kg=0,
        contribution_per_kg=100,
        normal_pulp_cost_per_kg=2,
        max_buffer_weeks=4,
        annual_closure_probability=1,
        conditional_weights={1: 0.2, 2: 0.3, 3: 0.5},
    )
    assert np.all(np.diff(table["expected_stockout_loss_cr"]) <= 1e-12)
    assert 0 <= best["buffer_weeks"] <= 4
    with pytest.raises(ValueError, match="frozen shelf life"):
        calculate_buffer_option(
            26, 100, 0, 100, 2, frozen_shelf_life_days=180
        )


def test_copacker_notice_and_capacity_math() -> None:
    as_of = pd.Timestamp("2026-03-01")
    scenarios = pd.DataFrame({
        "scenario": ["BASE", "BASE"],
        "week_start": [pd.Timestamp("2026-03-02"), pd.Timestamp("2026-03-16")],
        "scenario_bottles": [7_000_000, 7_000_000],
    })
    plan = constrained_weekly_planner(scenarios, as_of, copacker_notice_given=True)
    assert plan.loc[0, "copacker_capacity_bottles"] == 0
    assert plan.loc[1, "copacker_capacity_bottles"] > 0
    assert plan.loc[1, "max_feasible_bottles"] == pytest.approx(
        plan.loc[1, "in_house_capacity_bottles"] + plan.loc[1, "copacker_capacity_bottles"]
    )
    assert plan.loc[0, "mt_qc_max_prebuild_days"] == 30


def test_shortage_allocation_is_feasible_and_human_controlled() -> None:
    demand = pd.DataFrame({
        "flavor_id": ["PP", "DP"],
        "channel_id": ["QC", "QC"],
        "scenario_bottles": [10_000, 10_000],
    })
    bom = pd.DataFrame({
        "flavor_id": ["PP", "DP"],
        "pulp_id": ["PASSION", "PASSION"],
        "kg_per_bottle": [0.15, 0.06],
    })
    options = pd.DataFrame({
        "option_id": ["PROTECT_DP", "PROTECT_PP"],
        "option_name": ["DP", "PP"],
        "dp_pulp_share": [0.70, 0.30],
        "decision_logic": ["test", "test"],
        "trade_off": ["test", "test"],
    })
    summary, _ = shortage_allocation_options(1_000, demand, bom, options)
    assert (summary["used_pulp_kg"] <= 1_000 + 1e-8).all()
    assert summary["decision"].eq("HUMAN_REQUIRED").all()
    protect_dp = summary[summary["option_id"] == "PROTECT_DP"].iloc[0]
    protect_pp = summary[summary["option_id"] == "PROTECT_PP"].iloc[0]
    assert protect_dp["retained_contribution_cr"] > protect_pp["retained_contribution_cr"]
    assert protect_dp["dp_unmet_bottles"] == 0
