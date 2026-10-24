"""Demand diagnostics, sensing, censoring correction and scenario translation.

Operational functions deliberately do not read ``true_demand_bottles``.  That
column is synthetic ground truth and is used only in separate validation code.
"""
from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from .utils import next_week_start_on, week_period_alias


def estimate_censored_demand(daily_sales: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Estimate demand when sales are constrained by availability.

    - Observed in-stock sales are left unchanged.
    - GT stock-outs use distributor orders as a noisy, non-outlet proxy.
    - Other stock-outs use the rolling mean of recent corrected observations.

    The recursive history keeps long stock-outs from collapsing the baseline to
    zero.  Confidence is explicit because a proxy is not latent-demand truth.
    """
    required = {"date", "flavor_id", "channel_id", "depot_id", "sales_bottles", "stockout_flag"}
    missing = required - set(daily_sales.columns)
    if missing:
        raise ValueError(f"Missing censoring-correction columns: {sorted(missing)}")
    work = daily_sales.copy()
    if "distributor_orders_bottles" not in work:
        work["distributor_orders_bottles"] = 0
    work = work.sort_values(["flavor_id", "channel_id", "depot_id", "date"]).reset_index(drop=True)
    work["rolling_uncensored_baseline"] = 0.0
    work["estimated_demand_bottles"] = 0.0
    work["censoring_method"] = "OBSERVED_SALES"
    work["censoring_confidence"] = "HIGH"

    for _, indices in work.groupby(["flavor_id", "channel_id", "depot_id"], sort=False).groups.items():
        history: list[float] = []
        for idx in indices:
            row = work.loc[idx]
            baseline = float(np.mean(history[-window:])) if history else 0.0
            sales = float(row["sales_bottles"])
            if int(row["stockout_flag"]) == 0:
                estimate = sales
                method = "OBSERVED_SALES"
                confidence = "HIGH"
            else:
                order_proxy = float(row["distributor_orders_bottles"]) if row["channel_id"] == "GT" else 0.0
                if order_proxy > max(sales, baseline):
                    estimate = order_proxy
                    method = "GT_DISTRIBUTOR_ORDER_PROXY"
                    confidence = "MEDIUM"
                elif baseline > sales:
                    estimate = baseline
                    method = "ROLLING_UNCENSORED_BASELINE"
                    confidence = "LOW"
                else:
                    estimate = sales
                    method = "SALES_LOWER_BOUND_LOW_CONFIDENCE"
                    confidence = "LOW"
            work.at[idx, "rolling_uncensored_baseline"] = baseline
            work.at[idx, "estimated_demand_bottles"] = estimate
            work.at[idx, "censoring_method"] = method
            work.at[idx, "censoring_confidence"] = confidence
            history.append(estimate)

    work["estimated_lost_demand_bottles"] = np.maximum(
        0.0, work["estimated_demand_bottles"] - work["sales_bottles"]
    )
    return work.sort_values(["date", "flavor_id", "channel_id", "depot_id"]).reset_index(drop=True)


def prepare_qc_signal(qc_feed: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Aggregate depot-level daily QC to flavor × channel after censoring fix."""
    if qc_feed.empty:
        return pd.DataFrame(columns=[
            "date", "flavor_id", "channel_id", "signal_bottles", "raw_sell_through_bottles",
            "stockout_depot_count", "signal_basis",
        ])
    work = qc_feed.copy()
    work["channel_id"] = "QC"
    work["sales_bottles"] = work["sell_through_bottles"]
    work["distributor_orders_bottles"] = 0
    corrected = estimate_censored_demand(work, window=window)
    signal = corrected.groupby(["date", "flavor_id", "channel_id"], as_index=False).agg(
        signal_bottles=("estimated_demand_bottles", "sum"),
        raw_sell_through_bottles=("sales_bottles", "sum"),
        stockout_depot_count=("stockout_flag", "sum"),
    )
    signal["signal_basis"] = "DAILY_QC_WITH_STOCKOUT_CENSORING_CORRECTION"
    return signal.sort_values(["flavor_id", "date"]).reset_index(drop=True)


def _consecutive_count(condition: np.ndarray) -> np.ndarray:
    counts = np.zeros(len(condition), dtype=int)
    for i, value in enumerate(condition):
        counts[i] = counts[i - 1] + 1 if value and i > 0 else int(bool(value))
    return counts


def detect_demand_anomalies(
    signal: pd.DataFrame,
    value_col: str = "signal_bottles",
    baseline_window: int = 14,
    amber_multiplier: float = 1.5,
    amber_days: int = 2,
    red_multiplier: float = 2.0,
    red_days: int = 3,
    min_history: int = 5,
    group_cols: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Rolling-baseline ratio detector with EWMA and z-score diagnostics.

    Amber requires >1.5× baseline for two consecutive days by default; Red
    requires >2× for three.  Baselines are shifted one day to avoid contaminating
    the threshold with the observation being tested.
    """
    if signal.empty:
        return signal.assign(
            rolling_baseline=[], ewma_baseline=[], signal_ratio=[], z_score=[],
            amber_streak=[], red_streak=[], alert_status=[], alert_reason=[],
        )
    if baseline_window < 2 or min_history < 1:
        raise ValueError("baseline_window must be >=2 and min_history >=1")
    if not (1.0 < amber_multiplier < red_multiplier):
        raise ValueError("Require 1 < amber_multiplier < red_multiplier")
    if amber_days < 1 or red_days < 1:
        raise ValueError("Consecutive-day thresholds must be positive")

    groups = list(group_cols) if group_cols is not None else ["flavor_id"]
    if "channel_id" in signal.columns and "channel_id" not in groups:
        groups.append("channel_id")
    work = signal.copy().sort_values(groups + ["date"]).reset_index(drop=True)
    pieces = []
    for _, group in work.groupby(groups, sort=False, dropna=False):
        group = group.copy().sort_values("date")
        values = group[value_col].astype(float)
        # NaN before the first active sales day; retain genuine zeros after launch.
        active = (values > 0).cummax()
        shifted = values.where(active).shift(1)
        rolling = shifted.rolling(baseline_window, min_periods=min_history).mean()
        ewma = shifted.ewm(span=baseline_window, min_periods=min_history, adjust=False).mean()
        std = shifted.rolling(baseline_window, min_periods=min_history).std(ddof=0)
        # Calendar history is not enough for a new launch: pre-launch zeros must
        # not create an artificial spike. Require real nonzero signal history.
        nonzero_history = (values > 0).astype(int).shift(1).fillna(0).cumsum()
        valid_history = nonzero_history >= min_history
        rolling = rolling.where(valid_history)
        ewma = ewma.where(valid_history)
        std = std.where(valid_history)
        ratio = values / rolling.replace(0, np.nan)
        z_score = (values - rolling) / std.replace(0, np.nan)
        amber_hit = (ratio > amber_multiplier).fillna(False).to_numpy()
        red_hit = (ratio > red_multiplier).fillna(False).to_numpy()
        amber_streak = _consecutive_count(amber_hit)
        red_streak = _consecutive_count(red_hit)
        status = np.where(red_streak >= red_days, "RED", np.where(amber_streak >= amber_days, "AMBER", "NORMAL"))
        reason = np.where(
            status == "RED",
            f"QC signal >{red_multiplier:g}x {baseline_window}d baseline for {red_days} consecutive days",
            np.where(
                status == "AMBER",
                f"QC signal >{amber_multiplier:g}x {baseline_window}d baseline for {amber_days} consecutive days",
                "No threshold breach",
            ),
        )
        group["rolling_baseline"] = rolling
        group["ewma_baseline"] = ewma
        group["signal_ratio"] = ratio.replace([np.inf, -np.inf], np.nan)
        group["z_score"] = z_score.replace([np.inf, -np.inf], np.nan)
        group["amber_streak"] = amber_streak
        group["red_streak"] = red_streak
        group["alert_status"] = status
        group["alert_reason"] = reason
        pieces.append(group)
    return pd.concat(pieces, ignore_index=True).sort_values(["date"] + groups).reset_index(drop=True)


def first_alerts(alerts: pd.DataFrame, flavor_id: str = "DP") -> dict[str, pd.Timestamp | None]:
    flavor = alerts[alerts["flavor_id"] == flavor_id]
    result: dict[str, pd.Timestamp | None] = {}
    for status in ["AMBER", "RED"]:
        dates = flavor.loc[flavor["alert_status"] == status, "date"]
        result[status] = pd.Timestamp(dates.min()) if not dates.empty else None
    return result


def forecast_and_latency_diagnostics(monthly_forecast: pd.DataFrame, qc_feed: pd.DataFrame) -> tuple[dict[str, float], pd.DataFrame]:
    valid = monthly_forecast[monthly_forecast["actual_sales_bottles"] > 0].copy()
    wape = valid["absolute_error_bottles"].sum() / valid["actual_sales_bottles"].sum()
    signed = (valid["forecast_bottles"] - valid["actual_sales_bottles"]).sum()
    bias = signed / valid["actual_sales_bottles"].sum()
    by_flavor = valid.groupby("flavor_id", as_index=False).agg(
        actual_sales_bottles=("actual_sales_bottles", "sum"),
        absolute_error_bottles=("absolute_error_bottles", "sum"),
        signed_error_bottles=("forecast_bottles", "sum"),
    )
    by_flavor["signed_error_bottles"] -= by_flavor["actual_sales_bottles"]
    by_flavor["wape"] = by_flavor["absolute_error_bottles"] / by_flavor["actual_sales_bottles"]
    by_flavor["bias"] = by_flavor["signed_error_bottles"] / by_flavor["actual_sales_bottles"]
    if qc_feed.empty:
        latency = pd.Series(dtype=float)
    else:
        latency = (qc_feed["planner_consolidated_available_date"] - qc_feed["marketing_available_date"]).dt.days
    metrics = {
        "forecast_wape": float(wape),
        "forecast_bias": float(bias),
        "qc_marketing_latency_days": 0.0,
        "qc_planner_average_latency_days": float(latency.mean()) if not latency.empty else float("nan"),
        "qc_planner_max_latency_days": int(latency.max()) if not latency.empty else 0,
    }
    return metrics, by_flavor


def weekly_rolling_reforecast(
    corrected_daily: pd.DataFrame,
    lookback_weeks: int = 4,
    gt_mt_spillover: float = 0.5,
    week_start_day: str = "Monday",
) -> pd.DataFrame:
    """Next-week reforecast using only information available at each week end.

    QC's current-week uplift is used as a leading indicator for GT/MT.  This is a
    flagged proxy, not outlet-level GT visibility.
    """
    work = corrected_daily.copy()
    work["week_start"] = work["date"].dt.to_period(week_period_alias(week_start_day)).dt.start_time
    weekly = work.groupby(["week_start", "flavor_id", "channel_id", "depot_id"], as_index=False).agg(
        corrected_demand_bottles=("estimated_demand_bottles", "sum"),
        sales_bottles=("sales_bottles", "sum"),
        distributor_orders_bottles=("distributor_orders_bottles", "sum"),
    )
    weekly = weekly.sort_values(["flavor_id", "channel_id", "depot_id", "week_start"]).reset_index(drop=True)
    group_cols = ["flavor_id", "channel_id", "depot_id"]
    weekly["baseline_next_week_bottles"] = weekly.groupby(group_cols)["corrected_demand_bottles"].transform(
        lambda values: values.rolling(lookback_weeks, min_periods=1).mean()
    )

    qc = weekly[weekly["channel_id"] == "QC"].groupby(["week_start", "flavor_id"], as_index=False)[
        "corrected_demand_bottles"
    ].sum().sort_values(["flavor_id", "week_start"])
    qc["prior_qc_baseline"] = qc.groupby("flavor_id")["corrected_demand_bottles"].transform(
        lambda values: values.shift(1).rolling(lookback_weeks, min_periods=1).mean()
    )
    qc["qc_leading_uplift"] = np.where(
        qc["prior_qc_baseline"] > 0,
        qc["corrected_demand_bottles"] / qc["prior_qc_baseline"],
        1.0,
    )
    qc["qc_leading_uplift"] = qc["qc_leading_uplift"].clip(lower=1.0).fillna(1.0)
    weekly = weekly.merge(qc[["week_start", "flavor_id", "qc_leading_uplift"]], on=["week_start", "flavor_id"], how="left")
    weekly["qc_leading_uplift"] = weekly["qc_leading_uplift"].fillna(1.0)
    weekly["proxy_multiplier"] = np.where(
        weekly["channel_id"] == "QC",
        weekly["qc_leading_uplift"],
        1.0 + (weekly["qc_leading_uplift"] - 1.0) * gt_mt_spillover,
    )
    weekly["reforecast_next_week_bottles"] = weekly["baseline_next_week_bottles"] * weekly["proxy_multiplier"]
    weekly["target_week_start"] = weekly["week_start"] + pd.Timedelta(days=7)
    weekly["forecast_basis"] = "WEEKLY_ROLLING_QC_LEADING_PROXY"
    weekly["proxy_warning"] = np.where(
        weekly["channel_id"] == "GT",
        "GT distributor orders + QC leading indicator; no GT outlet data",
        "QC-to-channel spillover is an assumption" ,
    )
    actual_next = weekly[group_cols + ["week_start", "corrected_demand_bottles"]].rename(
        columns={"week_start": "target_week_start", "corrected_demand_bottles": "actual_next_week_bottles"}
    )
    weekly = weekly.merge(actual_next, on=group_cols + ["target_week_start"], how="left")
    return weekly.sort_values(["week_start", "flavor_id", "channel_id", "depot_id"]).reset_index(drop=True)


def build_demand_scenarios(
    corrected_daily: pd.DataFrame,
    bom: pd.DataFrame,
    as_of: str | pd.Timestamp,
    horizon_weeks: int = 8,
    history_days: int = 28,
    gt_mt_spillover: float = 0.5,
    uncertainty_pct: float = 20.0,
    multipliers: dict[str, float] | None = None,
    week_start_day: str = "Monday",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convert base / viral 2x / viral 4x scenarios to bottles and BOM pulp kg."""
    if horizon_weeks < 1 or history_days < 1:
        raise ValueError("Scenario horizon and history must be positive")
    as_of = pd.Timestamp(as_of)
    scenarios = multipliers or {"BASE": 1.0, "VIRAL_2X": 2.0, "VIRAL_4X": 4.0}
    history_start = as_of - pd.Timedelta(days=history_days - 1)
    history = corrected_daily[(corrected_daily["date"] >= history_start) & (corrected_daily["date"] <= as_of)]
    if history.empty:
        raise ValueError("No demand history available for scenario baseline")
    daily_base = history.groupby(["flavor_id", "channel_id"], as_index=False)["estimated_demand_bottles"].sum()
    daily_base["baseline_daily_bottles"] = daily_base["estimated_demand_bottles"] / history_days
    next_monday = next_week_start_on(as_of, week_start_day)
    rows = []
    for scenario, multiplier in scenarios.items():
        for week in range(horizon_weeks):
            for row in daily_base.itertuples():
                uplift = 1.0
                if row.flavor_id == "DP":
                    uplift = multiplier if row.channel_id == "QC" else 1.0 + (multiplier - 1.0) * gt_mt_spillover
                bottles = row.baseline_daily_bottles * 7.0 * uplift
                rows.append({
                    "scenario": scenario,
                    "week_start": next_monday + pd.Timedelta(days=7 * week),
                    "flavor_id": row.flavor_id,
                    "channel_id": row.channel_id,
                    "dp_viral_multiplier": multiplier,
                    "applied_uplift": uplift,
                    "scenario_bottles": bottles,
                    "low_bottles": bottles * (1.0 - uncertainty_pct / 100.0),
                    "high_bottles": bottles * (1.0 + uncertainty_pct / 100.0),
                    "basis": f"Trailing {history_days}d corrected demand; GT/MT viral spillover={gt_mt_spillover:.0%}",
                })
    bottle_scenarios = pd.DataFrame(rows)
    pulp = bottle_scenarios.merge(bom, on="flavor_id", how="left")
    pulp["pulp_requirement_kg"] = pulp["scenario_bottles"] * pulp["kg_per_bottle"]
    pulp_scenarios = pulp.groupby(["scenario", "week_start", "pulp_id"], as_index=False)["pulp_requirement_kg"].sum()
    return bottle_scenarios, pulp_scenarios


def launch_readiness_gate(
    pulp_inventory: pd.DataFrame,
    bom: pd.DataFrame,
    suppliers: pd.DataFrame,
    flavor_id: str,
    launch_date: str | pd.Timestamp,
    buffer_days: int = 7,
    launch_notice_days: int = 14,
    production_plan: pd.DataFrame | None = None,
) -> tuple[str, pd.DataFrame]:
    """Block a launch unless every BOM pulp covers lead time + buffer.

    When the scheduled production plan is available, cover uses forward average
    daily requirements over the longest lead-time gate.  This avoids approving a
    summer launch on artificially low trailing preseason consumption.
    """
    launch_date = pd.Timestamp(launch_date)
    required_pulps = bom.loc[bom["flavor_id"] == flavor_id, "pulp_id"].tolist()
    if not required_pulps:
        raise ValueError(f"No BOM configured for {flavor_id}")
    inventory = pulp_inventory[(pulp_inventory["date"] == launch_date) & (pulp_inventory["pulp_id"].isin(required_pulps))]
    if inventory.empty:
        raise ValueError("No launch-date pulp inventory available")
    gate = inventory[["pulp_id", "opening_kg", "current_daily_requirement_kg", "baseline_daily_requirement_kg"]].merge(
        suppliers[["pulp_id", "lead_time_days", "single_source_flag"]], on="pulp_id", how="left"
    )
    gate["buffer_days"] = buffer_days
    gate["required_cover_days"] = gate["lead_time_days"] + buffer_days
    gate["planning_daily_requirement_kg"] = gate["baseline_daily_requirement_kg"]
    gate["cover_basis"] = "EARLY_SUMMER_PLAN_BASELINE"
    if production_plan is not None:
        horizon = int(gate["required_cover_days"].max())
        forward = production_plan[(production_plan["date"] >= launch_date) &
                                  (production_plan["date"] < launch_date + pd.Timedelta(days=horizon))]
        plan = forward.merge(bom, on="flavor_id", how="inner")
        plan["required_kg"] = plan["scheduled_bottles"] * plan["kg_per_bottle"]
        daily_requirement = plan.groupby("pulp_id")["required_kg"].sum() / horizon
        gate["planning_daily_requirement_kg"] = gate["pulp_id"].map(daily_requirement).fillna(0.0)
        gate["cover_basis"] = f"FORWARD_{horizon}D_SCHEDULED_PRODUCTION"
    gate["cover_days"] = np.where(
        gate["planning_daily_requirement_kg"] > 0,
        gate["opening_kg"] / gate["planning_daily_requirement_kg"],
        np.inf,
    )
    gate["cover_gap_days"] = gate["cover_days"] - gate["required_cover_days"]
    gate["notice_days"] = launch_notice_days
    gate["notice_less_lead_days"] = launch_notice_days - gate["lead_time_days"]
    gate["status"] = np.where(gate["cover_gap_days"] >= 0, "PASS", "BLOCK")
    gate["explanation"] = np.where(
        gate["status"] == "PASS",
        "Cover meets supplier lead time + buffer",
        "Insufficient launch cover; qualify/expedite/build frozen pulp before release",
    )
    status = "READY" if gate["status"].eq("PASS").all() else "BLOCKED"
    return status, gate.sort_values("status", ascending=True).reset_index(drop=True)


def censoring_validation(corrected_daily: pd.DataFrame) -> dict[str, float]:
    """Back-test against synthetic truth; never used as an operational input."""
    if "true_demand_bottles" not in corrected_daily:
        return {}
    stocked = corrected_daily[corrected_daily["stockout_flag"] == 1]
    if stocked.empty:
        return {"stockout_rows": 0}
    sales_error = float((stocked["true_demand_bottles"] - stocked["sales_bottles"]).abs().sum())
    corrected_error = float((stocked["true_demand_bottles"] - stocked["estimated_demand_bottles"]).abs().sum())
    return {
        "stockout_rows": int(len(stocked)),
        "sales_absolute_error_bottles": sales_error,
        "corrected_absolute_error_bottles": corrected_error,
        "absolute_error_reduction_pct": 100.0 * (1.0 - corrected_error / sales_error) if sales_error else 0.0,
        "ground_truth_lost_bottles": float(stocked["lost_sales_bottles"].sum()),
        "estimated_lost_bottles": float(stocked["estimated_lost_demand_bottles"].sum()),
    }
