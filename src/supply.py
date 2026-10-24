"""Supply exposure, constrained capacity, buffer economics and allocation."""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from .utils import CRORE


def build_exposure_map(
    as_of: str | pd.Timestamp,
    pulp_inventory: pd.DataFrame,
    flavors: pd.DataFrame,
    bom: pd.DataFrame,
    suppliers: pd.DataFrame,
    routes: pd.DataFrame,
    summer_bottles: int = 96_000_000,
    price_per_bottle: float = 60.0,
    fragility_rule: str = "route_single=1/0.5;source_single=1/0.5;red=0.50;amber=0.20",
) -> pd.DataFrame:
    """One row per pulp with physical cover and revenue dependency."""
    as_of = pd.Timestamp(as_of)
    inventory = pulp_inventory[pulp_inventory["date"] == as_of].copy()
    if inventory.empty:
        raise ValueError(f"No pulp inventory at {as_of.date()}")
    exposure = inventory.merge(suppliers, on="pulp_id", how="left").merge(routes, on="route_id", how="left")
    flavor_shares = flavors.set_index("flavor_id")["summer_share"]
    dependent = bom.groupby("pulp_id")["flavor_id"].apply(list).to_dict()
    exposure["dependent_flavors"] = exposure["pulp_id"].map(lambda p: ", ".join(dependent.get(p, [])))
    exposure["dependent_summer_bottles"] = exposure["pulp_id"].map(
        lambda p: int(round(sum(float(flavor_shares.get(f, 0.0)) for f in dependent.get(p, [])) * summer_bottles))
    )
    exposure["dependent_revenue_cr"] = exposure["dependent_summer_bottles"] * price_per_bottle / CRORE
    exposure["current_cover_weeks"] = exposure["current_cover_days"] / 7.0
    exposure["baseline_cover_weeks"] = exposure["baseline_cover_days"] / 7.0
    exposure["lead_time_weeks"] = exposure["lead_time_days"] / 7.0
    exposure["cover_less_lead_weeks"] = exposure["current_cover_weeks"] - exposure["lead_time_weeks"]
    try:
        parts = dict(part.strip().split("=", 1) for part in fragility_rule.split(";"))
        route_single, route_multi = [float(value) for value in parts["route_single"].split("/")]
        source_single, source_multi = [float(value) for value in parts["source_single"].split("/")]
        red_threshold = float(parts["red"])
        amber_threshold = float(parts["amber"])
    except (KeyError, ValueError) as error:
        raise ValueError("A065 must define route_single, source_single, red and amber") from error
    exposure["fragility_score"] = (
        exposure["summer_closure_probability"]
        * np.where(exposure["single_route_flag"] == 1, route_single, route_multi)
        * np.where(exposure["single_source_flag"] == 1, source_single, source_multi)
    )
    exposure["risk_flag"] = np.where(
        (exposure["cover_less_lead_weeks"] < 0) | (exposure["fragility_score"] >= red_threshold),
        "RED",
        np.where((exposure["current_cover_weeks"] < exposure["lead_time_weeks"] + 1) | (exposure["fragility_score"] >= amber_threshold), "AMBER", "GREEN"),
    )
    columns = [
        "date", "pulp_id", "pulp_name", "supplier_name", "qualified_supplier_count",
        "single_source_flag", "route_name", "single_route_flag", "summer_closure_probability",
        "lead_time_days", "opening_kg", "current_daily_requirement_kg", "current_cover_weeks",
        "baseline_cover_weeks", "lead_time_weeks", "cover_less_lead_weeks", "dependent_flavors",
        "dependent_summer_bottles", "dependent_revenue_cr", "fragility_score", "risk_flag",
    ]
    return exposure[columns].sort_values(["risk_flag", "dependent_revenue_cr"], ascending=[True, False]).reset_index(drop=True)


def passionfruit_requirement_profile(
    corrected_daily: pd.DataFrame,
    bom: pd.DataFrame,
    as_of: str | pd.Timestamp,
    history_days: int = 28,
    contribution_per_bottle: float = 19.2,
) -> dict[str, float]:
    """Blended requirement and contribution per passionfruit kg from recent demand."""
    as_of = pd.Timestamp(as_of)
    start = as_of - pd.Timedelta(days=history_days - 1)
    history = corrected_daily[(corrected_daily["date"] >= start) & (corrected_daily["date"] <= as_of)]
    passion_bom = bom[bom["pulp_id"] == "PASSION"][["flavor_id", "kg_per_bottle"]]
    demand = history.groupby("flavor_id")["estimated_demand_bottles"].sum().rename("bottles").reset_index()
    demand = demand.merge(passion_bom, on="flavor_id", how="inner")
    if demand.empty:
        raise ValueError("No passionfruit-dependent demand in selected history")
    demand["pulp_kg"] = demand["bottles"] * demand["kg_per_bottle"]
    daily_bottles = float(demand["bottles"].sum() / history_days)
    daily_kg = float(demand["pulp_kg"].sum() / history_days)
    contribution_per_kg = daily_bottles * contribution_per_bottle / daily_kg
    return {
        "daily_bottles": daily_bottles,
        "daily_pulp_kg": daily_kg,
        "contribution_per_kg": contribution_per_kg,
        "history_days": float(history_days),
    }


def closure_loss_scenarios(
    daily_pulp_requirement_kg: float,
    existing_pulp_kg: float,
    contribution_per_kg: float,
    normal_pulp_cost_per_kg: float,
    annual_closure_probability: float = 0.60,
    conditional_weights: Mapping[int, float] | None = None,
    air_cost_multiplier: float = 5.0,
    additional_buffer_kg: float = 0.0,
) -> pd.DataFrame:
    """Expected next-summer loss for 1/2/3-week road closures.

    Expected values are probability-weighted contribution loss, not a claim that
    every closure produces the same outcome.  Air cost is shown separately to
    avoid adding it to contribution loss as if it were revenue.
    """
    if daily_pulp_requirement_kg <= 0 or contribution_per_kg < 0:
        raise ValueError("Daily requirement must be positive and contribution non-negative")
    if existing_pulp_kg < 0 or additional_buffer_kg < 0:
        raise ValueError("Inventory and buffer cannot be negative")
    weights = dict(conditional_weights or {1: 0.25, 2: 0.35, 3: 0.40})
    if set(weights) != {1, 2, 3} or abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("Closure weights must cover 1/2/3 weeks and sum to one")
    usable = existing_pulp_kg + additional_buffer_kg
    rows = []
    for weeks, conditional_probability in weights.items():
        requirement = daily_pulp_requirement_kg * weeks * 7.0
        shortage = max(0.0, requirement - usable)
        lost_contribution = shortage * contribution_per_kg / CRORE
        air_total = shortage * normal_pulp_cost_per_kg * air_cost_multiplier / CRORE
        air_premium = shortage * normal_pulp_cost_per_kg * (air_cost_multiplier - 1.0) / CRORE
        annual_probability = annual_closure_probability * conditional_probability
        rows.append({
            "closure_weeks": weeks,
            "closure_days": weeks * 7,
            "conditional_probability": conditional_probability,
            "annual_probability": annual_probability,
            "no_closure_probability": 1.0 - annual_closure_probability,
            "pulp_requirement_kg": requirement,
            "usable_pulp_kg": usable,
            "shortage_kg": shortage,
            "lost_contribution_cr": lost_contribution,
            "air_total_cost_cr": air_total,
            "air_premium_cr": air_premium,
            "expected_contribution_loss_cr": annual_probability * lost_contribution,
            "expected_air_total_cost_cr": annual_probability * air_total,
            "expected_air_premium_cr": annual_probability * air_premium,
        })
    return pd.DataFrame(rows)


def calculate_buffer_option(
    buffer_weeks: float,
    daily_pulp_requirement_kg: float,
    existing_pulp_kg: float,
    contribution_per_kg: float,
    normal_pulp_cost_per_kg: float,
    annual_closure_probability: float = 0.60,
    conditional_weights: Mapping[int, float] | None = None,
    annual_carry_rate: float = 0.18,
    cold_storage_rate: float = 0.08,
    air_cost_multiplier: float = 5.0,
    frozen_shelf_life_days: int = 180,
) -> dict[str, float]:
    """Pure buffer calculation; unit-tested independently of Streamlit."""
    buffer_days = buffer_weeks * 7.0
    if buffer_weeks < 0 or buffer_days > frozen_shelf_life_days:
        raise ValueError("Buffer must be non-negative and within frozen shelf life")
    buffer_kg = daily_pulp_requirement_kg * buffer_days
    scenarios = closure_loss_scenarios(
        daily_pulp_requirement_kg=daily_pulp_requirement_kg,
        existing_pulp_kg=existing_pulp_kg,
        contribution_per_kg=contribution_per_kg,
        normal_pulp_cost_per_kg=normal_pulp_cost_per_kg,
        annual_closure_probability=annual_closure_probability,
        conditional_weights=conditional_weights,
        air_cost_multiplier=air_cost_multiplier,
        additional_buffer_kg=buffer_kg,
    )
    expected_loss = float(scenarios["expected_contribution_loss_cr"].sum())
    expected_air_premium = float(scenarios["expected_air_premium_cr"].sum())
    investment = buffer_kg * normal_pulp_cost_per_kg / CRORE
    annual_carry = investment * (annual_carry_rate + cold_storage_rate)
    return {
        "buffer_weeks": float(buffer_weeks),
        "buffer_kg": float(buffer_kg),
        "buffer_working_capital_cr": float(investment),
        "annual_carry_and_storage_cr": float(annual_carry),
        "expected_stockout_loss_cr": expected_loss,
        "expected_air_premium_cr": expected_air_premium,
        # Total means total: expected air premium is not merely displayed and
        # then omitted from the objective (A020/A025 correction).
        "expected_total_cost_cr": float(annual_carry + expected_loss + expected_air_premium),
    }


def optimise_buffer(
    daily_pulp_requirement_kg: float,
    existing_pulp_kg: float,
    contribution_per_kg: float,
    normal_pulp_cost_per_kg: float,
    max_buffer_weeks: int = 8,
    **kwargs,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Enumerate small integer buffer choices and minimise expected total cost."""
    zero = calculate_buffer_option(
        0, daily_pulp_requirement_kg, existing_pulp_kg, contribution_per_kg,
        normal_pulp_cost_per_kg, **kwargs,
    )
    rows = []
    for weeks in range(max_buffer_weeks + 1):
        option = calculate_buffer_option(
            weeks, daily_pulp_requirement_kg, existing_pulp_kg, contribution_per_kg,
            normal_pulp_cost_per_kg, **kwargs,
        )
        option["avoided_expected_loss_cr"] = zero["expected_stockout_loss_cr"] - option["expected_stockout_loss_cr"]
        option["avoided_expected_air_premium_cr"] = zero["expected_air_premium_cr"] - option["expected_air_premium_cr"]
        option["net_expected_benefit_cr"] = (
            option["avoided_expected_loss_cr"]
            + option["avoided_expected_air_premium_cr"]
            - option["annual_carry_and_storage_cr"]
        )
        rows.append(option)
    table = pd.DataFrame(rows)
    # Probability at which each positive buffer ties the zero-buffer option.
    # Carrying cost is fixed; closure loss and air premium scale with annual p.
    # Annual probabilities are mutually exclusive duration buckets and sum to p.
    # Evaluate at p=1 to recover the conditional expected cost curve.
    conditional_at_p1 = closure_loss_scenarios(
        daily_pulp_requirement_kg, existing_pulp_kg, contribution_per_kg,
        normal_pulp_cost_per_kg, annual_closure_probability=1.0, **{
            key: value for key, value in kwargs.items()
            if key in {"conditional_weights", "air_cost_multiplier"}
        },
    )
    zero_conditional_at_p1 = float(
        (conditional_at_p1["lost_contribution_cr"] * conditional_at_p1["conditional_probability"]).sum()
        + (conditional_at_p1["air_premium_cr"] * conditional_at_p1["conditional_probability"]).sum()
    )
    break_even = []
    for option in rows:
        weeks = option["buffer_weeks"]
        conditional = closure_loss_scenarios(
            daily_pulp_requirement_kg, existing_pulp_kg, contribution_per_kg,
            normal_pulp_cost_per_kg, annual_closure_probability=1.0,
            additional_buffer_kg=option["buffer_kg"], **{
                key: value for key, value in kwargs.items()
                if key in {"conditional_weights", "air_cost_multiplier"}
            },
        )
        conditional_cost = float(
            (conditional["lost_contribution_cr"] * conditional["conditional_probability"]).sum()
            + (conditional["air_premium_cr"] * conditional["conditional_probability"]).sum()
        )
        avoided_at_p1 = zero_conditional_at_p1 - conditional_cost
        probability = option["annual_carry_and_storage_cr"] / avoided_at_p1 if avoided_at_p1 > 0 else np.inf
        break_even.append(float(probability))
    table["break_even_vs_zero_probability"] = break_even
    best = table.loc[table["expected_total_cost_cr"].idxmin()].to_dict()
    best["break_even_closure_probability"] = float(best["break_even_vs_zero_probability"])
    best["is_working_capital_in_program_budget"] = False
    return table, best


def air_only_comparison(closure_scenarios: pd.DataFrame) -> dict[str, float | str]:
    """Cost of covering every modelled shortage by air, with no extra buffer.

    This is a separate response strategy, not an additional cost stacked on the
    same bottles: it assumes air capacity is available and prevents the modelled
    contribution loss. Normal pulp cost is shown alongside the premium so the
    comparison cannot be mistaken for a freight-only quote.
    """
    return {
        "strategy": "AIR_ONLY_NO_ADDITIONAL_BUFFER",
        "expected_air_total_cost_cr": float(closure_scenarios["expected_air_total_cost_cr"].sum()),
        "expected_air_premium_cr": float(closure_scenarios["expected_air_premium_cr"].sum()),
        "expected_stockout_loss_cr": 0.0,
        "annual_carry_and_storage_cr": 0.0,
        "expected_total_cost_cr": float(closure_scenarios["expected_air_premium_cr"].sum()),
        "assumption": "All shortage kg can be air-freighted in time; no residual stock-out loss; normal pulp cost excluded as common to both strategies.",
    }


def _scale_plan_to_pulp(
    planned_by_flavor: pd.Series,
    bom: pd.DataFrame,
    stock_kg: dict[str, float],
) -> tuple[pd.Series, dict[str, float]]:
    """Scale a flavor plan until every BOM pulp balance is non-negative."""
    plan = planned_by_flavor.astype(float).copy()
    flavor_pulps = bom.groupby("flavor_id")["pulp_id"].apply(list).to_dict()
    kg_per_bottle = bom.set_index(["flavor_id", "pulp_id"])["kg_per_bottle"].to_dict()
    for _ in range(max(1, len(bom) * 2)):
        usage: dict[str, float] = {}
        for flavor, bottles in plan.items():
            for pulp in flavor_pulps.get(flavor, []):
                usage[pulp] = usage.get(pulp, 0.0) + bottles * float(kg_per_bottle[(flavor, pulp)])
        ratios = {
            pulp: min(1.0, max(0.0, stock_kg.get(pulp, 0.0)) / required) if required > 1e-9 else 1.0
            for pulp, required in usage.items()
        }
        if all(ratio >= 1.0 - 1e-10 for ratio in ratios.values()):
            break
        for flavor in plan.index:
            factors = [ratios.get(pulp, 0.0) for pulp in flavor_pulps.get(flavor, [])]
            if factors:
                plan.loc[flavor] *= min(factors)
    usage = {}
    for flavor, bottles in plan.items():
        for pulp in flavor_pulps.get(flavor, []):
            usage[pulp] = usage.get(pulp, 0.0) + bottles * float(kg_per_bottle[(flavor, pulp)])
    return plan, usage


def constrained_weekly_planner(
    bottle_scenarios: pd.DataFrame,
    as_of: str | pd.Timestamp,
    combined_monthly_capacity: int = 25_000_000,
    historical_utilisation: float = 0.95,
    copacker_share: float = 0.10,
    copacker_notice_days: int = 14,
    copacker_premium: float = 0.25,
    base_variable_cost_per_bottle: float = 40.8,
    days_per_month: float = 30.4375,
    bottled_shelf_life_days: int = 90,
    mt_qc_min_remaining_days: int = 60,
    copacker_notice_given: bool = False,
    bom: pd.DataFrame | None = None,
    opening_pulp_kg: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Weekly bottle plan with notice and, when supplied, physical pulp limits.

    Opening pulp is carried week to week. No unconfirmed future inbound is
    credited. In-house production draws pulp first; eligible co-packer output
    can use only the remaining balances. This prevents the former infeasible
    4x-plan reserve from being counted against an already-empty pulp pool.
    """
    as_of = pd.Timestamp(as_of)
    demand = bottle_scenarios.groupby(["scenario", "week_start"], as_index=False)["scenario_bottles"].sum()
    in_house = combined_monthly_capacity * 7.0 / days_per_month
    historical = in_house * historical_utilisation
    copacker = combined_monthly_capacity * copacker_share * 7.0 / days_per_month
    notice_date = as_of if copacker_notice_given else pd.NaT
    demand["in_house_capacity_bottles"] = in_house
    demand["historical_run_rate_bottles"] = historical
    demand["in_house_headroom_bottles"] = in_house - historical
    demand["copacker_notice_date"] = notice_date
    demand["copacker_eligible_date"] = notice_date + pd.Timedelta(days=copacker_notice_days) if copacker_notice_given else pd.NaT
    eligible = (demand["week_start"] >= as_of + pd.Timedelta(days=copacker_notice_days)) if copacker_notice_given else pd.Series(False, index=demand.index)
    demand["copacker_capacity_bottles"] = np.where(eligible, copacker, 0.0)
    demand["max_feasible_bottles"] = demand["in_house_capacity_bottles"] + demand["copacker_capacity_bottles"]

    if bom is None or opening_pulp_kg is None:
        demand["in_house_planned_bottles"] = np.minimum(demand["scenario_bottles"], in_house)
        demand["copacker_used_bottles"] = np.minimum(
            demand["copacker_capacity_bottles"], np.maximum(0.0, demand["scenario_bottles"] - in_house)
        )
        demand["unmet_bottles"] = np.maximum(0.0, demand["scenario_bottles"] - demand["max_feasible_bottles"])
        demand["pulp_limited_copacker_bottles"] = 0.0
        demand["pulp_feasibility_rule"] = "NOT_EVALUATED_NO_PULP_INPUT"
    else:
        result_rows = []
        flavor_demand = bottle_scenarios.groupby(["scenario", "week_start", "flavor_id"], as_index=False)["scenario_bottles"].sum()
        for scenario, scenario_demand in flavor_demand.groupby("scenario", sort=False):
            stock = {str(key): max(0.0, float(value)) for key, value in opening_pulp_kg.items()}
            for week, week_demand in scenario_demand.groupby("week_start", sort=True):
                desired = week_demand.set_index("flavor_id")["scenario_bottles"].astype(float)
                total = float(desired.sum())
                bottle_service = min(1.0, in_house / total) if total > 0 else 1.0
                in_house_plan, in_house_usage = _scale_plan_to_pulp(desired * bottle_service, bom, stock)
                for pulp, used in in_house_usage.items():
                    stock[pulp] = stock.get(pulp, 0.0) - used
                residual = (desired - in_house_plan).clip(lower=0.0)
                week_key = pd.Timestamp(week)
                is_eligible = bool(copacker_notice_given and week_key >= as_of + pd.Timedelta(days=copacker_notice_days))
                copacker_cap = copacker if is_eligible else 0.0
                residual_total = float(residual.sum())
                copacker_service = min(1.0, copacker_cap / residual_total) if residual_total > 0 else 0.0
                uncapped_copacker = residual * copacker_service
                copacker_plan, copacker_usage = _scale_plan_to_pulp(uncapped_copacker, bom, stock)
                for pulp, used in copacker_usage.items():
                    stock[pulp] = stock.get(pulp, 0.0) - used
                result_rows.append({
                    "scenario": scenario,
                    "week_start": week_key,
                    "scenario_bottles": total,
                    "in_house_planned_bottles": float(in_house_plan.sum()),
                    "copacker_used_bottles": float(copacker_plan.sum()),
                    "unmet_bottles": float((desired - in_house_plan - copacker_plan).clip(lower=0.0).sum()),
                    "pulp_limited_copacker_bottles": float((uncapped_copacker - copacker_plan).clip(lower=0.0).sum()),
                    "pulp_feasibility_rule": "OPENING_STOCK_ONLY_IN_HOUSE_FIRST_CARRY_FORWARD",
                    **{f"closing_{pulp.lower()}_kg": max(0.0, stock.get(pulp, 0.0)) for pulp in bom["pulp_id"].unique()},
                })
        constrained = pd.DataFrame(result_rows)
        demand = demand.drop(columns=["scenario_bottles"]).merge(
            constrained, on=["scenario", "week_start"], how="left", validate="one_to_one"
        )
    demand["pulp_feasible_bottles"] = demand["in_house_planned_bottles"] + demand["copacker_used_bottles"]
    demand["copacker_premium_cr"] = (
        demand["copacker_used_bottles"] * base_variable_cost_per_bottle * copacker_premium / CRORE
    )
    demand["mt_qc_max_prebuild_days"] = bottled_shelf_life_days - mt_qc_min_remaining_days
    demand["shelf_life_rule"] = (
        f"MT/QC prebuild <= {bottled_shelf_life_days - mt_qc_min_remaining_days} days; "
        "hold structural buffer in frozen pulp, not bottles"
    )
    return demand.sort_values(["scenario", "week_start"]).reset_index(drop=True)


def shortage_allocation_options(
    available_passionfruit_kg: float,
    demand_by_flavor_channel: pd.DataFrame,
    bom: pd.DataFrame,
    options: pd.DataFrame,
    contribution_per_bottle: float = 19.2,
    channel_risk_weights: Mapping[str, float] | None = None,
    service_rule: str = "proportional",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Present feasible allocations; deliberately choose no auto-winner."""
    if available_passionfruit_kg < 0:
        raise ValueError("Available pulp cannot be negative")
    demand = demand_by_flavor_channel.rename(columns={"scenario_bottles": "demand_bottles"}).copy()
    if "demand_bottles" not in demand:
        raise ValueError("Demand needs scenario_bottles or demand_bottles")
    demand = demand[demand["flavor_id"].isin(["PP", "DP"])]
    risk = dict(channel_risk_weights or {"GT": 1.0, "MT": 2.0, "QC": 3.0})
    kg_lookup = bom[bom["pulp_id"] == "PASSION"].set_index("flavor_id")["kg_per_bottle"].to_dict()
    summaries, details = [], []
    for option in options.itertuples():
        allocated_kg = 0.0
        supported_bottles = 0.0
        lost_bottles = 0.0
        weighted_risk = 0.0
        for flavor in ["PP", "DP"]:
            share = float(option.dp_pulp_share) if flavor == "DP" else 1.0 - float(option.dp_pulp_share)
            flavor_pulp = available_passionfruit_kg * share
            flavor_demand = demand[demand["flavor_id"] == flavor]
            total_demand = float(flavor_demand["demand_bottles"].sum())
            max_bottles = flavor_pulp / kg_lookup[flavor]
            service = min(1.0, max_bottles / total_demand) if total_demand > 0 else 1.0
            if service_rule == "proportional":
                supported_by_index = pd.Series(flavor_demand["demand_bottles"] * service, index=flavor_demand.index)
            elif service_rule == "risk_priority":
                remaining = max_bottles
                supported_by_index = pd.Series(0.0, index=flavor_demand.index)
                priority = flavor_demand.assign(
                    _priority=flavor_demand["channel_id"].map(lambda channel: float(risk.get(channel, 1.0)))
                ).sort_values(["_priority", "channel_id"], ascending=[False, True])
                for index, row in priority.iterrows():
                    supported_by_index.loc[index] = min(float(row["demand_bottles"]), remaining)
                    remaining -= supported_by_index.loc[index]
            else:
                raise ValueError("A064 service_rule must be 'proportional' or 'risk_priority'")
            for row in flavor_demand.itertuples():
                supported = float(supported_by_index.loc[row.Index])
                unmet = float(row.demand_bottles) - supported
                used_kg = supported * kg_lookup[flavor]
                allocated_kg += used_kg
                supported_bottles += supported
                lost_bottles += unmet
                weighted_risk += unmet * float(risk.get(row.channel_id, 1.0))
                details.append({
                    "option_id": option.option_id,
                    "flavor_id": flavor,
                    "channel_id": row.channel_id,
                    "demand_bottles": float(row.demand_bottles),
                    "flavor_pulp_budget_kg": flavor_pulp,
                    "used_pulp_kg": used_kg,
                    "supported_bottles": supported,
                    "unmet_bottles": unmet,
                    "service_rate": supported / float(row.demand_bottles) if float(row.demand_bottles) > 0 else 1.0,
                    "weighted_delisting_risk": unmet * float(risk.get(row.channel_id, 1.0)),
                })
        retained = supported_bottles * contribution_per_bottle / CRORE
        summaries.append({
            "option_id": option.option_id,
            "option_name": option.option_name,
            "dp_pulp_share": float(option.dp_pulp_share),
            "pp_pulp_share": 1.0 - float(option.dp_pulp_share),
            "available_pulp_kg": available_passionfruit_kg,
            "used_pulp_kg": allocated_kg,
            "unused_pulp_kg": available_passionfruit_kg - allocated_kg,
            "supported_bottles": supported_bottles,
            "unmet_bottles": lost_bottles,
            "retained_contribution_cr": retained,
            "contribution_per_available_pulp_kg": retained * CRORE / available_passionfruit_kg if available_passionfruit_kg else 0.0,
            "weighted_delisting_risk": weighted_risk,
            "dp_unmet_bottles": float(sum(d["unmet_bottles"] for d in details if d["option_id"] == option.option_id and d["flavor_id"] == "DP")),
            "rival_threat_flag": "HIGH" if option.option_id != "PROTECT_DP" else "MITIGATED_NOT_REMOVED",
            "decision_logic": option.decision_logic,
            "trade_off": option.trade_off,
            "decision": "HUMAN_REQUIRED",
        })
    summary = pd.DataFrame(summaries)
    summary["contribution_rank"] = summary["retained_contribution_cr"].rank(ascending=False, method="min").astype(int)
    summary["risk_rank_low_is_better"] = summary["weighted_delisting_risk"].rank(ascending=True, method="min").astype(int)
    return summary, pd.DataFrame(details)


def supply_option_economics(
    option_config: pd.DataFrame,
    buffer_table: pd.DataFrame,
    best_buffer: Mapping[str, float],
    closure_scenarios: pd.DataFrame,
) -> pd.DataFrame:
    """Cost/benefit comparison with working capital separated from run cost."""
    baseline_loss = float(closure_scenarios["expected_contribution_loss_cr"].sum())
    baseline_air_premium = float(closure_scenarios["expected_air_premium_cr"].sum())
    rows = []
    for option in option_config.itertuples():
        cost = float(option.year1_cost_cr)
        if option.option_id == "PREBUY_BUFFER":
            cost = float(best_buffer["annual_carry_and_storage_cr"])
            benefit = float(best_buffer["avoided_expected_loss_cr"]) + float(best_buffer.get("avoided_expected_air_premium_cr", 0.0))
            working_capital = float(best_buffer["buffer_working_capital_cr"])
        else:
            benefit = baseline_loss * float(option.expected_loss_reduction) + baseline_air_premium * float(option.air_cost_reduction)
            working_capital = 0.0
        rows.append({
            "option_id": option.option_id,
            "option_name": option.option_name,
            "year1_run_or_build_cost_cr": cost,
            "recoverable_working_capital_cr": working_capital,
            "expected_annual_benefit_cr": benefit,
            "net_expected_benefit_cr": benefit - cost,
            "benefit_cost_ratio": benefit / cost if cost > 0 else np.nan,
            "notes": option.notes,
            "source": "MY ASSUMPTION" if option.option_id != "PREBUY_BUFFER" else "MODEL OUTPUT WITH MY ASSUMPTION",
            "VERIFIED_AGAINST_CASE_TEXT": "N",
        })
    return pd.DataFrame(rows)
