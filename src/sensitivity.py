"""Shared one-click scenario and detection-sensitivity functions.

All controls produce explicit assumption scenarios. They do not fit parameters,
call external services, or turn avoided-loss arithmetic into a simulation.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import numpy as np
import pandas as pd

from .config import AppConfig
from .data_generator import SyntheticDataGenerator
from .demand import detect_demand_anomalies, first_alerts, prepare_qc_signal


ROOT_CAUSE_PROFILES = ("BASE", "EQUAL", "LATE_SENSING_HEAVY", "ROUTE_HEAVY")


def scenario_config(
    config: AppConfig,
    initial_multiplier: float | None = None,
    planner_notice: str | pd.Timestamp | None = None,
    root_cause_profile: str = "BASE",
    capture_multiplier: float = 1.0,
    closure_probability: float | None = None,
    qc_share: float | None = None,
) -> AppConfig:
    """Return a copied config with every one-click control applied consistently."""
    case = dict(config.case)
    assumptions = config.assumptions.copy()
    tables = {name: frame.copy() for name, frame in config.tables.items()}

    if initial_multiplier is not None:
        if not 1.0 <= float(initial_multiplier) <= float(case["viral_qc_multiplier"]):
            raise ValueError("Initial DP QC multiplier must be between 1x and the case peak")
        assumptions.loc[assumptions["assumption_id"] == "A042", "value"] = str(float(initial_multiplier))
    if planner_notice is not None:
        notice = pd.Timestamp(planner_notice)
        assumptions.loc[assumptions["assumption_id"] == "A007", "value"] = str(notice.date())
    if root_cause_profile not in ROOT_CAUSE_PROFILES:
        raise ValueError(f"Unknown root-cause profile {root_cause_profile}")
    if not 0.0 <= float(capture_multiplier) <= 1.5:
        raise ValueError("Capture multiplier must be between 0 and 1.5")

    attribution = tables["loss_attribution"]
    if root_cause_profile == "EQUAL":
        attribution["lost_contribution_share"] = 1.0 / len(attribution)
    elif root_cause_profile in {"LATE_SENSING_HEAVY", "ROUTE_HEAVY"}:
        selected = "LATE_SENSING" if root_cause_profile == "LATE_SENSING_HEAVY" else "ROUTE_SINGLE_SOURCE"
        shares = attribution["lost_contribution_share"].astype(float).copy()
        # Move 20 percentage points to the selected cause, proportionally from
        # the others. Air/write-off allocations remain separate assumptions.
        selected_index = attribution.index[attribution["root_cause_id"] == selected]
        if len(selected_index) != 1:
            raise ValueError(f"Missing root cause {selected}")
        index = selected_index[0]
        transfer = min(0.20, float(shares.drop(index).sum()))
        other_total = float(shares.drop(index).sum())
        for other in shares.index:
            if other == index:
                continue
            reduction = transfer * float(shares.loc[other]) / other_total if other_total else 0.0
            shares.loc[other] -= reduction
        shares.loc[index] += transfer
        attribution["lost_contribution_share"] = shares
    for column in ["low_capture", "base_capture", "high_capture"]:
        attribution[column] = (attribution[column].astype(float) * float(capture_multiplier)).clip(0.0, 1.0)

    if closure_probability is not None:
        probability = float(closure_probability)
        if not 0.0 <= probability <= 1.0:
            raise ValueError("Closure probability must be between zero and one")
        case["passion_closure_probability"] = probability
        routes = tables["routes"]
        routes.loc[routes["route_id"] == "R_PASSION", "summer_closure_probability"] = probability
    if qc_share is not None:
        share = float(qc_share)
        base_shares = config.tables["channels"].set_index("channel_id")["summer_share"].astype(float)
        if not 0.0 <= share < 1.0:
            raise ValueError("QC share must be in [0, 1)")
        channels = tables["channels"].copy()
        other = base_shares.drop(labels=["QC"])
        other_total = float(other.sum())
        channels["summer_share"] = channels["channel_id"].map(
            lambda channel: share if channel == "QC" else (1.0 - share) * float(other.get(channel, 0.0)) / other_total
        )
        tables["channels"] = channels

    return replace(config, case=case, assumptions=assumptions, tables=tables)


def ramp_lead_sensitivity(
    config: AppConfig,
    detector_params: dict[str, float | int],
    multipliers: Iterable[float] = (1.0, 1.5, 2.0, 2.5, 3.0),
) -> pd.DataFrame:
    """Recompute first Amber/Red and reaction lead for each initial DP QC ramp."""
    rows = []
    notice = pd.Timestamp(config.assumption("A007"))
    for multiplier in multipliers:
        changed = scenario_config(config, initial_multiplier=float(multiplier))
        generator = SyntheticDataGenerator(changed)
        daily = generator._build_demand_and_sales()
        qc = generator._build_qc_feed(daily)
        signal = prepare_qc_signal(qc, int(changed.case["baseline_window_days"]))
        alerts = detect_demand_anomalies(signal, **detector_params)
        dates = first_alerts(alerts, "DP")
        amber = dates["AMBER"]
        red = dates["RED"]
        rows.append({
            "initial_dp_qc_multiplier": float(multiplier),
            "first_amber": amber,
            "first_red": red,
            "planner_notice": notice,
            "amber_reaction_lead_days": (notice - amber).days if amber is not None else np.nan,
            "red_confirmation_lead_days": (notice - red).days if red is not None else np.nan,
            "alert_status": "TRIGGERED" if amber is not None or red is not None else "NO_ALERT",
            "basis": "SYNTHETIC_DETECTION_BACKTEST_NOT_AVOIDED_LOSS_SIMULATION",
        })
    return pd.DataFrame(rows)


def avoided_loss_range(attribution: pd.DataFrame) -> pd.DataFrame:
    """Always-visible LOW/BASE/HIGH arithmetic with effective capture rates."""
    impact = float(attribution["economic_impact_cr"].sum())
    rows = []
    for scenario, key, capture_column in [
        ("LOW", "avoided_loss_low_cr", "low_capture"),
        ("BASE", "avoided_loss_base_cr", "base_capture"),
        ("HIGH", "avoided_loss_high_cr", "high_capture"),
    ]:
        avoided = float(attribution[key].sum())
        rows.append({
            "scenario": scenario,
            "avoided_loss_cr": avoided,
            "effective_capture_rate": avoided / impact if impact else 0.0,
            "capture_rate_inputs": "; ".join(
                f"{row.root_cause_id}={float(getattr(row, capture_column)):.0%}"
                for row in attribution.itertuples()
            ),
            "estimation_basis": "ASSUMPTION-BASED, NOT SIMULATED",
        })
    return pd.DataFrame(rows)
