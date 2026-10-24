"""Deterministic synthetic data for the Pulp Riot consulting case.

The generator distinguishes latent demand from realised sales.  Case totals are
imposed by largest-remainder apportionment, so integer bottle counts reconcile
exactly without relying on rounded percentages.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import AppConfig, compiled_assumptions
from .utils import CRORE, apportion, weekday_number


class SyntheticDataGenerator:
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.rng = np.random.default_rng(config.seed)
        self.start = pd.Timestamp(config.year, 1, 1)
        self.end = pd.Timestamp(config.year, 6, 30)
        self.dates = pd.date_range(self.start, self.end, freq="D")
        self.pre_dates = self.dates[self.dates < config.summer_start]
        self.summer_dates = self.dates[self.dates >= config.summer_start]
        self.flavors = config.tables["flavors"]
        self.channels = config.tables["channels"]
        self.depots = config.tables["depots"]
        self.pulps = config.tables["pulps"]
        self.bom = config.tables["bom"]
        self.suppliers = config.tables["suppliers"]
        self.routes = config.tables["routes"]
        self.seasonality = config.tables["monthly_seasonality"].set_index("month")["multiplier"]
        self.notice_date = pd.Timestamp(config.assumption("A007"))
        self.air_booking_date = pd.Timestamp(config.assumption("A012"))
        self.air_arrival_date = self.air_booking_date + pd.Timedelta(days=int(config.number("A013")))

    def generate(self) -> dict[str, pd.DataFrame]:
        daily = self._build_demand_and_sales()
        production = self._build_scheduled_production(daily)
        production, pulp_inventory, pulp_inbound = self._constrain_and_build_pulp(production)
        capacity = self._build_capacity(production)
        depot_stock, depot_flow, depot_batches = self._build_depot_stock(daily, production)
        writeoffs, writeoff_reconciliation = self._build_writeoffs(depot_batches)
        depot_flow = self._apply_writeoffs(depot_flow, writeoffs)
        datasets = {
            "daily_sales": daily,
            "qc_sell_through": self._build_qc_feed(daily),
            "monthly_forecast": self._build_monthly_forecast(daily),
            "depot_stock_weekly": depot_stock,
            "depot_flow_daily": depot_flow,
            "depot_writeoffs": writeoffs,
            "writeoff_reconciliation": writeoff_reconciliation,
            "production_daily": production,
            "plant_copacker_capacity": capacity,
            "pulp_inventory_daily": pulp_inventory,
            "pulp_inbound": pulp_inbound,
            "supplier_routes": self.suppliers.rename(columns={
                "source": "supplier_source", "VERIFIED_AGAINST_CASE_TEXT": "SUPPLIER_VERIFIED_AGAINST_CASE_TEXT",
            }).merge(self.routes.rename(columns={
                "source": "route_source", "VERIFIED_AGAINST_CASE_TEXT": "ROUTE_VERIFIED_AGAINST_CASE_TEXT",
            }), on="route_id", how="left"),
            "viral_profile": self._build_viral_profile(),
            "event_calendar": self._build_events(),
            "assumptions": compiled_assumptions(self.cfg),
        }
        return datasets

    def _daily_weights(self, dates: pd.DatetimeIndex, flavor_id: str, channel_id: str) -> tuple[np.ndarray, np.ndarray]:
        """Create smooth seasonality + seeded noise and return viral multipliers."""
        if len(dates) == 0:
            return np.asarray([]), np.asarray([])
        month_factor = np.asarray([self.seasonality.loc[d.month] for d in dates], dtype=float)
        weekend = np.where(dates.weekday >= 5, 1.0 + self.cfg.number("A005"), 1.0)
        noise = self.rng.lognormal(mean=0.0, sigma=self.cfg.number("A004"), size=len(dates))
        viral = np.ones(len(dates))
        if flavor_id == "DP":
            elapsed = (dates - self.cfg.viral_start).days
            ramp_days = int(self.cfg.case["viral_ramp_days"])
            peak = float(self.cfg.case["viral_qc_multiplier"])
            initial = self.cfg.number("A042")
            rising = (elapsed >= 0) & (elapsed <= ramp_days)
            viral[rising] = initial + (peak - initial) * elapsed[rising] / ramp_days
            viral[elapsed > ramp_days] = peak
            if channel_id != "QC":
                viral = 1.0 + (viral - 1.0) * self.cfg.number("A006")
        return month_factor * weekend * noise * viral, viral

    def _build_demand_and_sales(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        active_pre = self.flavors.loc[self.flavors["available_from_md"] == "01-01"]
        pre_share_sum = active_pre["summer_share"].sum()
        pairs = [(f["flavor_id"], c["channel_id"]) for _, f in self.flavors.iterrows() for _, c in self.channels.iterrows()]
        pre_weights = [
            (self.flavors.set_index("flavor_id").loc[f, "summer_share"] / pre_share_sum
             * self.channels.set_index("channel_id").loc[c, "summer_share"])
            if self.flavors.set_index("flavor_id").loc[f, "available_from_md"] == "01-01" else 0.0
            for f, c in pairs
        ]
        summer_weights = [
            self.flavors.set_index("flavor_id").loc[f, "summer_share"]
            * self.channels.set_index("channel_id").loc[c, "summer_share"]
            for f, c in pairs
        ]
        pre_targets = dict(zip(pairs, apportion(pre_weights, int(self.cfg.number("A003")))))
        summer_targets = dict(zip(pairs, apportion(summer_weights, int(self.cfg.case["summer_bottles"]))))
        for _, flavor in self.flavors.iterrows():
            for _, channel in self.channels.iterrows():
                pair = (flavor["flavor_id"], channel["channel_id"])
                for season, dates in (("PRE", self.pre_dates), ("SUMMER", self.summer_dates)):
                    total = int(pre_targets[pair] if season == "PRE" else summer_targets[pair])
                    weights, viral = self._daily_weights(dates, flavor["flavor_id"], channel["channel_id"])
                    available_from = self.cfg.date(flavor["available_from_md"])
                    weights = np.where(dates >= available_from, weights, 0.0)
                    viral = np.where(dates >= available_from, viral, 0.0)
                    # Apportion jointly over date × depot inside each flavor ×
                    # channel group so rounded group totals remain exact.
                    block_weights = np.concatenate([
                        weights * depot_weight for depot_weight in self.depots["demand_weight"]
                    ])
                    allocations = apportion(block_weights, int(total))
                    rows = []
                    cursor = 0
                    for _, depot in self.depots.iterrows():
                        count = len(dates)
                        rows.append(pd.DataFrame({
                            "date": dates,
                            "flavor_id": flavor["flavor_id"],
                            "channel_id": channel["channel_id"],
                            "depot_id": depot["depot_id"],
                            "region": depot["region"],
                            "season": season,
                            "true_demand_bottles": allocations[cursor:cursor + count],
                            "viral_multiplier_ground_truth": viral,
                        }))
                        cursor += count
                    frames.append(pd.concat(rows, ignore_index=True))

        daily = pd.concat(frames, ignore_index=True)
        daily = daily.sort_values(["date", "flavor_id", "channel_id", "depot_id"]).reset_index(drop=True)
        daily["lost_sales_bottles"] = self._allocate_case_losses(daily)
        daily["sales_bottles"] = daily["true_demand_bottles"] - daily["lost_sales_bottles"]
        daily["stockout_flag"] = (daily["lost_sales_bottles"] > 0).astype(int)
        daily["distributor_orders_bottles"] = 0
        gt = daily["channel_id"] == "GT"
        order_noise = self.rng.normal(0.0, self.cfg.number("A025"), size=int(gt.sum()))
        orders = np.rint(daily.loc[gt, "true_demand_bottles"].to_numpy() * (1.0 + order_noise))
        daily.loc[gt, "distributor_orders_bottles"] = np.maximum(
            daily.loc[gt, "sales_bottles"].to_numpy(), np.maximum(0, orders)
        ).astype(int)
        daily["gt_distributor_count"] = np.where(gt, int(self.cfg.case["gt_distributor_count"]), 0)
        daily["data_classification"] = "SYNTHETIC_GROUND_TRUTH"
        return daily

    def _allocate_case_losses(self, daily: pd.DataFrame) -> np.ndarray:
        """Allocate exactly 8% of summer latent demand to event-driven risk weights."""
        dates = daily["date"]
        flavors = daily["flavor_id"]
        profiles = daily["depot_id"].map(self.depots.set_index("depot_id")["stock_profile"])
        risk = np.zeros(len(daily))
        summer = daily["season"] == "SUMMER"
        viral_shortage = (dates >= self.notice_date) & (dates < self.cfg.closure_start)
        closure_and_recovery = dates >= self.cfg.closure_start
        risk[(flavors == "DP") & viral_shortage] = self.cfg.number("A008")
        risk[(flavors.isin(["DP", "PP"])) & closure_and_recovery] = self.cfg.number("A009")
        risk[(flavors == "DB") & closure_and_recovery] = self.cfg.number("A010")
        risk[(flavors.isin(["MPB", "GC"])) & (profiles == "SHORT") & (dates.dt.month >= 5)] = self.cfg.number("A011")
        raw = daily["true_demand_bottles"].to_numpy(dtype=float) * risk * summer.to_numpy()
        target = int(round(int(self.cfg.case["summer_bottles"]) * float(self.cfg.case["summer_revenue_loss_share"])))
        if raw.sum() < target:
            raise RuntimeError("Loss risk weights are too small to reconcile the case loss")
        # Scale below one, hence no allocation can exceed its row's demand cap.
        scaled = raw * (target / raw.sum())
        return apportion(scaled, target, caps=daily["true_demand_bottles"].to_numpy())

    def _build_qc_feed(self, daily: pd.DataFrame) -> pd.DataFrame:
        qc = daily.loc[daily["channel_id"] == "QC", [
            "date", "flavor_id", "depot_id", "sales_bottles", "stockout_flag"
        ]].copy()
        qc = qc.rename(columns={"sales_bottles": "sell_through_bottles"})
        qc["marketing_available_date"] = qc["date"]
        qc["planner_consolidated_available_date"] = qc["date"] + pd.offsets.MonthEnd(0)
        qc["feed_grain"] = "DAILY_QC_SELL_THROUGH"
        return qc.sort_values(["date", "flavor_id", "depot_id"]).reset_index(drop=True)

    def _build_monthly_forecast(self, daily: pd.DataFrame) -> pd.DataFrame:
        actual = daily.assign(month_start=daily["date"].values.astype("datetime64[M]")).groupby(
            ["month_start", "flavor_id", "depot_id"], as_index=False
        )["sales_bottles"].sum().rename(columns={"sales_bottles": "actual_sales_bottles"})
        flavor_index = {value: i for i, value in enumerate(self.flavors["flavor_id"])}
        depot_index = {value: i for i, value in enumerate(self.depots["depot_id"])}
        forecast_rule = self.cfg.assumption("A062")
        if forecast_rule == "alternating +/-30%":
            directions = [
                1 if (flavor_index[f] + depot_index[d] + m.month) % 2 == 0 else -1
                for f, d, m in zip(actual["flavor_id"], actual["depot_id"], actual["month_start"])
            ]
        elif forecast_rule == "all +30%":
            directions = np.ones(len(actual), dtype=int)
        elif forecast_rule == "all -30%":
            directions = -np.ones(len(actual), dtype=int)
        else:
            raise ValueError("A062 must be 'alternating +/-30%', 'all +30%' or 'all -30%'")
        error = float(self.cfg.case["forecast_error"])
        actual["forecast_bottles"] = actual["actual_sales_bottles"] * (
            1.0 + error * np.asarray(directions)
        )
        actual["absolute_error_bottles"] = (actual["forecast_bottles"] - actual["actual_sales_bottles"]).abs()
        actual["absolute_percentage_error"] = np.where(
            actual["actual_sales_bottles"] > 0,
            actual["absolute_error_bottles"] / actual["actual_sales_bottles"],
            np.nan,
        )
        issue_rule = self.cfg.assumption("A063")
        if issue_rule == "first_day_of_month":
            actual["forecast_issue_date"] = actual["month_start"]
        elif issue_rule == "month_end":
            actual["forecast_issue_date"] = actual["month_start"] + pd.offsets.MonthEnd(0)
        else:
            raise ValueError("A063 must be 'first_day_of_month' or 'month_end'")
        actual["planner_available_date"] = actual["month_start"] + pd.offsets.MonthEnd(0)
        actual["forecast_basis"] = f"MONTHLY_LAST_YEAR_MIX|{forecast_rule}|{issue_rule}"
        return actual.sort_values(["month_start", "flavor_id", "depot_id"]).reset_index(drop=True)

    def _build_scheduled_production(self, daily: pd.DataFrame) -> pd.DataFrame:
        frames = []
        summer_monthly_output = (
            float(self.cfg.case["combined_monthly_capacity_bottles"])
            * float(self.cfg.case["summer_utilisation"])
        )
        for month in range(1, 7):
            month_dates = self.dates[self.dates.month == month]
            month_daily = daily[daily["date"].dt.month == month]
            preseason_rule = int(self.cfg.number("A057"))
            if preseason_rule not in {0, 1}:
                raise ValueError("A057 must be 1 (latent-demand preseason) or 0 (capacity-run-rate preseason)")
            if month < 3 and preseason_rule == 1:
                flavor_targets = month_daily.groupby("flavor_id")["true_demand_bottles"].sum().to_dict()
            elif month < 3:
                preseason_weights = self.flavors.set_index("flavor_id")["summer_share"].astype(float).copy()
                preseason_weights[self.flavors.set_index("flavor_id")["available_from_md"] != "01-01"] = 0.0
                preseason_weights /= preseason_weights.sum()
                flavor_targets = {f: summer_monthly_output * w for f, w in preseason_weights.items()}
            else:
                weights = self.flavors.set_index("flavor_id")["summer_share"].astype(float).copy()
                if month == 4:
                    weights["DP"] *= self.cfg.number("A015")
                if month >= 5:
                    weights["PP"] *= self.cfg.number("A016")
                    weights["DP"] *= self.cfg.number("A017")
                weights /= weights.sum()
                flavor_targets = {f: summer_monthly_output * w for f, w in weights.items()}
            allocated_targets = apportion(
                [flavor_targets.get(f, 0.0) for f in self.flavors["flavor_id"]],
                int(round(sum(flavor_targets.values()))),
            )
            for flavor_id, target in zip(self.flavors["flavor_id"], allocated_targets):
                daily_shape = month_daily.groupby("date")["true_demand_bottles"].sum().reindex(month_dates, fill_value=0)
                flavor_shape = month_daily.loc[month_daily["flavor_id"] == flavor_id].groupby("date")[
                    "true_demand_bottles"
                ].sum().reindex(month_dates, fill_value=0)
                production_shape_rule = self.cfg.assumption("A069")
                if production_shape_rule == "latent_daily_demand_shape":
                    weights = flavor_shape.to_numpy(dtype=float)
                elif production_shape_rule == "flat_daily":
                    weights = np.ones(len(month_dates), dtype=float)
                else:
                    raise ValueError("A069 must be 'latent_daily_demand_shape' or 'flat_daily'")
                if weights.sum() == 0 and target > 0:
                    weights = daily_shape.to_numpy(dtype=float) + 1.0
                available_from = self.cfg.date(self.flavors.set_index("flavor_id").loc[flavor_id, "available_from_md"])
                weights = np.where(month_dates >= available_from, weights, 0.0)
                allocation = apportion(weights, int(target))
                frames.append(pd.DataFrame({
                    "date": month_dates,
                    "flavor_id": flavor_id,
                    "scheduled_bottles": allocation,
                }))
        production = pd.concat(frames, ignore_index=True)
        production["actual_bottles"] = production["scheduled_bottles"]
        return production.sort_values(["date", "flavor_id"]).reset_index(drop=True)

    def _constrain_and_build_pulp(self, production: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Protect DP with scarce passionfruit and move freed capacity to MPB/GC."""
        production = production.copy()
        bom_lookup = self.bom.set_index(["flavor_id", "pulp_id"])["kg_per_bottle"].to_dict()
        scheduled_pulp_rows = production[["date", "flavor_id", "scheduled_bottles"]].merge(
            self.bom, on="flavor_id", how="left"
        )
        scheduled_pulp_rows["scheduled_kg"] = (
            scheduled_pulp_rows["scheduled_bottles"] * scheduled_pulp_rows["kg_per_bottle"]
        )
        scheduled_daily = scheduled_pulp_rows.groupby(["date", "pulp_id"])["scheduled_kg"].sum().unstack(fill_value=0)
        baseline_mask = (scheduled_daily.index >= self.cfg.summer_start) & (
            scheduled_daily.index < self.cfg.viral_start
        )
        passion_baseline = float(scheduled_daily.loc[baseline_mask, "PASSION"].mean())
        previral_cover = self.cfg.number("A014")
        closure_cover = float(self.cfg.case["passion_cover_days_at_closure"])
        normal_cost = float(self.suppliers.set_index("pulp_id").loc["PASSION", "normal_cost_per_kg"])
        air_cost_basis = self.cfg.assumption("A036")
        if air_cost_basis in {"1", "TOTAL_DELIVERED_COST"}:
            air_unit_cost = normal_cost * float(self.cfg.case["air_cost_multiplier"])
        elif air_cost_basis == "FREIGHT_PREMIUM_ONLY":
            air_unit_cost = normal_cost * (float(self.cfg.case["air_cost_multiplier"]) - 1.0)
        else:
            raise ValueError("A036 must be TOTAL_DELIVERED_COST or FREIGHT_PREMIUM_ONLY")
        air_qty = float(self.cfg.case["air_freight_cost_cr"]) * CRORE / air_unit_cost
        road_resume = self.cfg.closure_end + pd.Timedelta(days=int(self.cfg.case["passion_road_transit_days"]) + 1)
        recovery_end = road_resume + pd.Timedelta(days=int(self.cfg.number("A026")) - 1)
        prod_index = production.set_index(["date", "flavor_id"])
        opening = previral_cover * passion_baseline
        passion_records = []
        smoothing_flag = int(self.cfg.number("A056"))
        if smoothing_flag not in {0, 1}:
            raise ValueError("A056 must be 1 (daily smoothing) or 0 (lead-time batch receipts)")
        pending_road = 0.0
        passion_lead = int(self.suppliers.set_index("pulp_id").loc["PASSION", "lead_time_days"])

        for date in self.dates:
            scheduled_req = float(scheduled_daily.loc[date, "PASSION"])
            road_inbound, air_inbound = 0.0, 0.0
            constrained = False
            if date < self.cfg.closure_start:
                if date < self.cfg.viral_start:
                    desired = previral_cover * passion_baseline
                else:
                    horizon = max(1, (self.cfg.closure_start - self.cfg.viral_start).days - 1)
                    progress = min(1.0, (date - self.cfg.viral_start).days / horizon)
                    desired = (previral_cover + (closure_cover - previral_cover) * progress) * passion_baseline
                road_inbound = max(0.0, scheduled_req + desired - opening)
            elif date <= self.cfg.closure_end or date < road_resume:
                constrained = True
                if date == self.air_arrival_date:
                    air_inbound = air_qty
            else:
                days_left = max(1, (recovery_end - date).days + 1)
                rebuild = max(0.0, closure_cover * passion_baseline - opening) / days_left
                road_inbound = scheduled_req + rebuild

            if road_inbound > 0:
                pending_road += road_inbound
                batch_day = ((date - self.start).days % max(1, passion_lead)) == 0
                if smoothing_flag == 1 or batch_day:
                    road_inbound = pending_road
                    pending_road = 0.0
                else:
                    road_inbound = 0.0
            available = opening + road_inbound + air_inbound
            actual_req = min(scheduled_req, available)
            if constrained and actual_req < scheduled_req - 1e-8:
                dp_kg = bom_lookup[("DP", "PASSION")]
                pp_kg = bom_lookup[("PP", "PASSION")]
                dp_scheduled = int(prod_index.loc[(date, "DP"), "actual_bottles"])
                pp_scheduled = int(prod_index.loc[(date, "PP"), "actual_bottles"])
                dp_actual = min(dp_scheduled, int(np.floor(available / dp_kg)))
                remaining = max(0.0, available - dp_actual * dp_kg)
                pp_actual = min(pp_scheduled, int(np.floor(remaining / pp_kg)))
                prod_index.loc[(date, "DP"), "actual_bottles"] = dp_actual
                prod_index.loc[(date, "PP"), "actual_bottles"] = pp_actual
                freed = (dp_scheduled - dp_actual) + (pp_scheduled - pp_actual)
                to_mpb = int(round(freed * self.cfg.number("A018")))
                prod_index.loc[(date, "MPB"), "actual_bottles"] += to_mpb
                prod_index.loc[(date, "GC"), "actual_bottles"] += freed - to_mpb
                actual_req = dp_actual * dp_kg + pp_actual * pp_kg

            closing = max(0.0, available - actual_req)
            passion_records.append({
                "date": date,
                "pulp_id": "PASSION",
                "opening_kg": opening,
                "road_inbound_kg": road_inbound,
                "air_inbound_kg": air_inbound,
                "consumption_kg": actual_req,
                "closing_kg": closing,
                "unmet_requirement_kg": max(0.0, scheduled_req - actual_req),
                "baseline_daily_requirement_kg": passion_baseline,
            })
            opening = closing

        production = prod_index.reset_index()
        production["actual_bottles"] = production["actual_bottles"].astype(int)
        production["passionfruit_constraint_flag"] = (
            production["actual_bottles"] != production["scheduled_bottles"]
        ).astype(int)

        actual_rows = production[["date", "flavor_id", "actual_bottles"]].merge(self.bom, on="flavor_id", how="left")
        actual_rows["consumption_kg"] = actual_rows["actual_bottles"] * actual_rows["kg_per_bottle"]
        actual_daily = actual_rows.groupby(["date", "pulp_id"])["consumption_kg"].sum().unstack(fill_value=0)

        inventory_frames = [pd.DataFrame(passion_records)]
        inbound_source_records = []
        for pulp_id in self.pulps["pulp_id"]:
            if pulp_id == "PASSION":
                continue
            opening_cover = float(self.pulps.set_index("pulp_id").loc[pulp_id, "opening_cover_days"])
            baseline = float(actual_daily.loc[baseline_mask, pulp_id].mean())
            target = opening_cover * baseline
            opening = target
            records = []
            pending_road = 0.0
            pulp_lead = int(self.suppliers.set_index("pulp_id").loc[pulp_id, "lead_time_days"])
            for date in self.dates:
                consumption = float(actual_daily.loc[date, pulp_id])
                road_inbound = max(0.0, consumption + target - opening)
                if road_inbound > 0:
                    pending_road += road_inbound
                    batch_day = ((date - self.start).days % max(1, pulp_lead)) == 0
                    if smoothing_flag == 1 or batch_day:
                        road_inbound = pending_road
                        pending_road = 0.0
                    else:
                        road_inbound = 0.0
                closing = max(0.0, opening + road_inbound - consumption)
                records.append({
                    "date": date,
                    "pulp_id": pulp_id,
                    "opening_kg": opening,
                    "road_inbound_kg": road_inbound,
                    "air_inbound_kg": 0.0,
                    "consumption_kg": consumption,
                    "closing_kg": closing,
                    "unmet_requirement_kg": max(0.0, consumption - opening - road_inbound),
                    "baseline_daily_requirement_kg": baseline,
                })
                opening = closing
            inventory_frames.append(pd.DataFrame(records))

        inventory = pd.concat(inventory_frames, ignore_index=True).merge(
            self.pulps[["pulp_id", "pulp_name"]], on="pulp_id", how="left"
        ).sort_values(["pulp_id", "date"])
        inventory["current_daily_requirement_kg"] = inventory.groupby("pulp_id")["consumption_kg"].transform(
            lambda values: values.rolling(14, min_periods=1).mean()
        )
        inventory["baseline_cover_days"] = np.where(
            inventory["baseline_daily_requirement_kg"] > 0,
            inventory["opening_kg"] / inventory["baseline_daily_requirement_kg"],
            0.0,
        )
        inventory["current_cover_days"] = np.where(
            inventory["current_daily_requirement_kg"] > 0,
            inventory["opening_kg"] / inventory["current_daily_requirement_kg"],
            0.0,
        )
        inventory["storage"] = "FROZEN"
        inventory["inventory_status"] = "SYNTHETIC_DAILY_BALANCE"

        supplier_by_pulp = self.suppliers.set_index("pulp_id")
        for row in inventory.itertuples():
            if row.road_inbound_kg > 1e-8:
                inbound_source_records.append({
                    "arrival_date": row.date,
                    "pulp_id": row.pulp_id,
                    "supplier_id": supplier_by_pulp.loc[row.pulp_id, "supplier_id"],
                    "route_id": supplier_by_pulp.loc[row.pulp_id, "route_id"],
                    "mode": "Road",
                    "quantity_kg": row.road_inbound_kg,
                    "booking_date": row.date - pd.Timedelta(days=int(supplier_by_pulp.loc[row.pulp_id, "lead_time_days"])),
                    "cost_multiplier": 1.0,
                })
            if row.air_inbound_kg > 1e-8:
                inbound_source_records.append({
                    "arrival_date": row.date,
                    "pulp_id": row.pulp_id,
                    "supplier_id": supplier_by_pulp.loc[row.pulp_id, "supplier_id"],
                    "route_id": "AIR_EMERGENCY",
                    "mode": "Air",
                    "quantity_kg": row.air_inbound_kg,
                    "booking_date": self.air_booking_date,
                    "cost_multiplier": float(self.cfg.case["air_cost_multiplier"]),
                })
        inbound = pd.DataFrame(inbound_source_records)
        inbound["normal_unit_cost_per_kg"] = inbound["pulp_id"].map(supplier_by_pulp["normal_cost_per_kg"])
        inbound["actual_unit_cost_per_kg"] = inbound["normal_unit_cost_per_kg"] * inbound["cost_multiplier"]
        inbound["normal_cost_cr"] = inbound["quantity_kg"] * inbound["normal_unit_cost_per_kg"] / CRORE
        inbound["actual_cost_cr"] = inbound["quantity_kg"] * inbound["actual_unit_cost_per_kg"] / CRORE
        inbound["premium_cr"] = inbound["actual_cost_cr"] - inbound["normal_cost_cr"]
        inbound["shipment_status"] = "RECEIVED"
        inbound = inbound.sort_values(["arrival_date", "pulp_id", "mode"]).reset_index(drop=True)
        return production, inventory.reset_index(drop=True), inbound

    def _build_capacity(self, production: pd.DataFrame) -> pd.DataFrame:
        monthly = production.assign(month_start=production["date"].values.astype("datetime64[M]")).groupby(
            "month_start"
        )["actual_bottles"].sum()
        combined_capacity = int(self.cfg.case["combined_monthly_capacity_bottles"])
        rows = []
        plant_count = int(self.cfg.case["plant_count"])
        if plant_count < 1:
            raise ValueError("plant_count must be positive")
        plant_capacity = combined_capacity / plant_count
        for month, output in monthly.items():
            plant_1 = int(output * self.cfg.number("A058"))
            remaining_output = int(output) - plant_1
            remaining_capacity = plant_count - 1
            plant_outputs = [plant_1]
            for plant_index in range(remaining_capacity):
                plants_left = remaining_capacity - plant_index
                value = remaining_output // plants_left
                plant_outputs.append(value)
                remaining_output -= value
            for plant_index, value in enumerate(plant_outputs, start=1):
                rows.append({
                    "month_start": month,
                    "asset_id": f"PLANT_{plant_index:02d}",
                    "asset_type": "IN_HOUSE",
                    "capacity_bottles": plant_capacity,
                    "actual_bottles": value,
                    "utilisation": value / plant_capacity,
                    "notice_days": 0,
                    "cost_premium": 0.0,
                })
            rows.append({
                "month_start": month,
                "asset_id": "CO_PACKER",
                "asset_type": "CO_PACKER",
                "capacity_bottles": int(round(combined_capacity * float(self.cfg.case["copacker_max_volume_share"]))),
                "actual_bottles": 0,
                "utilisation": 0.0,
                "notice_days": int(self.cfg.case["copacker_notice_days"]),
                "cost_premium": float(self.cfg.case["copacker_cost_premium"]),
            })
        return pd.DataFrame(rows).sort_values(["month_start", "asset_id"]).reset_index(drop=True)

    def _build_depot_stock(self, daily: pd.DataFrame, production: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Conserve depot bottles and age FIFO batches; never read forward demand.

        Opening stock is three weeks of the preseason run rate split by the
        configured last-year mix (DP=0). Thereafter each day's physical balance
        is opening + actual production receipts - realised sales. Production is
        allocated across depots using that day's realised sales mix, or depot
        weights when no sales exist. This is an allocation assumption, not a
        claim about unobserved GT outlet demand.
        """
        last_year = self.cfg.tables["last_year_mix"].set_index("flavor_id")["last_year_share"]
        opening_age = int(self.cfg.number("A071"))
        opening_batch_date = self.start - pd.Timedelta(days=opening_age)
        cover_days = int(self.cfg.case["depot_cover_days"])
        preseason_daily = float(self.cfg.number("A003")) / max(1, len(self.pre_dates))
        batches: dict[tuple[str, str], list[list[object]]] = {}
        for depot in self.depots.itertuples():
            depot_total = int(round(preseason_daily * cover_days * float(depot.demand_weight)))
            shares = last_year.reindex(self.flavors["flavor_id"]).fillna(0.0).to_numpy(dtype=float)
            opening_allocation = apportion(shares, depot_total)
            for flavor_id, quantity in zip(self.flavors["flavor_id"], opening_allocation):
                batches[(depot.depot_id, flavor_id)] = [[opening_batch_date, int(quantity)]] if quantity > 0 else []

        sales = daily.groupby(["date", "flavor_id", "depot_id"], as_index=False)["sales_bottles"].sum()
        sales_lookup = sales.set_index(["date", "flavor_id", "depot_id"])["sales_bottles"].to_dict()
        production_daily = production.groupby(["date", "flavor_id"], as_index=False)["actual_bottles"].sum()
        production_lookup = production_daily.set_index(["date", "flavor_id"])["actual_bottles"].to_dict()
        depot_ids = self.depots["depot_id"].tolist()
        depot_weights = self.depots["demand_weight"].to_numpy(dtype=float)
        shelf_life = int(self.cfg.case["bottled_shelf_life_days"])
        flow_rows: list[dict[str, object]] = []

        for date in self.dates:
            for flavor_id in self.flavors["flavor_id"]:
                daily_sales = np.asarray([
                    int(sales_lookup.get((date, flavor_id, depot_id), 0)) for depot_id in depot_ids
                ], dtype=int)
                receipt_weights = daily_sales.astype(float) if daily_sales.sum() > 0 else depot_weights
                opening_by_depot = np.asarray([
                    sum(int(batch[1]) for batch in batches[(depot_id, flavor_id)]) for depot_id in depot_ids
                ], dtype=int)
                required_receipts = np.maximum(0, daily_sales - opening_by_depot)
                production_total = int(production_lookup.get((date, flavor_id), 0))
                if production_total < int(required_receipts.sum()):
                    raise RuntimeError(
                        f"Physical depot deficit at {date.date()} / {flavor_id}: production plus opening "
                        "stock cannot cover realised sales. Adjust production or opening stock; do not clip sales."
                    )
                receipts = apportion(
                    receipt_weights,
                    production_total,
                    minimum=required_receipts,
                )
                for depot, receipt, sold in zip(self.depots.itertuples(), receipts, daily_sales):
                    key = (depot.depot_id, flavor_id)
                    batch_list = batches[key]
                    opening = int(sum(int(batch[1]) for batch in batch_list))
                    if receipt > 0:
                        batch_list.append([date, int(receipt)])
                    remaining_sale = int(sold)
                    for batch in batch_list:
                        if remaining_sale == 0:
                            break
                        taken = min(int(batch[1]), remaining_sale)
                        batch[1] = int(batch[1]) - taken
                        remaining_sale -= taken
                    if remaining_sale > 0:
                        raise RuntimeError(
                            f"Depot conservation would create negative stock at {date.date()} / "
                            f"{depot.depot_id} / {flavor_id}: unmet realised sales={remaining_sale}. "
                            "Adjust production or opening stock; do not hide the deficit."
                        )
                    batches[key] = [batch for batch in batch_list if int(batch[1]) > 0]
                    active = batches[key]
                    closing = int(sum(int(batch[1]) for batch in active))
                    if closing != opening + int(receipt) - int(sold):
                        raise AssertionError("FIFO batch balance does not conserve bottles")
                    if active:
                        oldest = min(pd.Timestamp(batch[0]) for batch in active)
                        weighted_age = sum(
                            (date - pd.Timestamp(batch[0])).days * int(batch[1]) for batch in active
                        ) / closing
                        oldest_age = (date - oldest).days
                    else:
                        oldest = pd.NaT
                        weighted_age = 0.0
                        oldest_age = 0
                    flow_rows.append({
                        "date": date,
                        "flavor_id": flavor_id,
                        "depot_id": depot.depot_id,
                        "region": depot.region,
                        "opening_bottles": opening,
                        "production_receipts_bottles": int(receipt),
                        "sales_bottles": int(sold),
                        "writeoff_bottles": 0.0,
                        "closing_bottles": closing,
                        "oldest_batch_production_date": oldest,
                        "oldest_batch_age_days": int(oldest_age),
                        "weighted_average_age_days": float(weighted_age),
                        "bottled_shelf_life_days": shelf_life,
                        "oldest_remaining_shelf_days": shelf_life - int(oldest_age),
                        "stock_profile": depot.stock_profile,
                    })

        flow = pd.DataFrame(flow_rows).sort_values(["date", "flavor_id", "depot_id"]).reset_index(drop=True)
        flow["current_demand_21d_bottles"] = flow.groupby(["flavor_id", "depot_id"])["sales_bottles"].transform(
            lambda values: values.rolling(cover_days, min_periods=1).sum()
        )
        flow["current_daily_demand_bottles"] = flow["current_demand_21d_bottles"] / cover_days
        flow["current_cover_weeks"] = np.where(
            flow["current_demand_21d_bottles"] > 0,
            flow["closing_bottles"] / (flow["current_demand_21d_bottles"] / 3.0),
            np.nan,
        )
        flow["mismatch_bottles"] = flow["closing_bottles"] - flow["current_demand_21d_bottles"]
        flow["mismatch_status"] = np.select(
            [
                (flow["current_demand_21d_bottles"] > 0) & (flow["closing_bottles"] < flow["current_demand_21d_bottles"]),
                flow["closing_bottles"] > 1.5 * flow["current_demand_21d_bottles"],
            ],
            ["SHORT_VS_TRAILING_21D", "OVERSTOCK_VS_TRAILING_21D"],
            default="WITHIN_1_TO_1_5X_TRAILING_21D",
        )
        flow["conservation_balance_bottles"] = (
            flow["opening_bottles"] + flow["production_receipts_bottles"]
            - flow["sales_bottles"] - flow["writeoff_bottles"] - flow["closing_bottles"]
        )

        weekday_abbr = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][weekday_number(self.cfg.assumption("A055"))]
        snapshots = pd.DatetimeIndex([self.start]).append(
            pd.date_range(self.start, self.end, freq=f"W-{weekday_abbr}")
        ).drop_duplicates().sort_values()
        stock = flow[flow["date"].isin(snapshots)].copy().rename(columns={"date": "snapshot_date"})
        stock["snapshot_available_date"] = stock["snapshot_date"] + pd.Timedelta(days=int(self.cfg.number("A019")))
        stock["stock_bottles"] = stock["closing_bottles"]
        stock["allocation_basis"] = "LAST_YEAR_OPENING_THEN_PRODUCTION_MINUS_SALES_FIFO"
        stock["last_year_mix_cover_days"] = cover_days
        stock["opening_last_year_share"] = stock["flavor_id"].map(last_year).fillna(0.0)
        stock["mix_basis"] = "OPENING_LAST_YEAR_MIX; SUBSEQUENT_PHYSICAL_FLOW"

        ending_batches = []
        for (depot_id, flavor_id), batch_list in batches.items():
            for batch_date, quantity in batch_list:
                if int(quantity) <= 0:
                    continue
                age = (self.end - pd.Timestamp(batch_date)).days
                ending_batches.append({
                    "date": self.end,
                    "depot_id": depot_id,
                    "flavor_id": flavor_id,
                    "production_date": pd.Timestamp(batch_date),
                    "batch_bottles": int(quantity),
                    "age_days": int(age),
                    "remaining_shelf_days": shelf_life - int(age),
                })
        batch_frame = pd.DataFrame(ending_batches)
        return stock.reset_index(drop=True), flow, batch_frame

    def _build_writeoffs(self, depot_batches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Value stock breaching channel cutoffs, then disclose case calibration."""
        channels = self.channels[["channel_id", "summer_share"]]
        rules = self.cfg.tables["channel_shelf_life"].merge(channels, on="channel_id", how="left")
        rows: list[dict[str, object]] = []
        valuation_fraction = float(self.cfg.number("A072"))
        price = float(self.cfg.case["price_per_bottle"])
        for rule in rules.itertuples():
            cutoff = int(rule.min_remaining_days)
            if cutoff <= 0:
                continue  # GT remains an explicit no-cutoff assumption by default.
            eligible = depot_batches[depot_batches["remaining_shelf_days"] < cutoff].copy()
            for (depot_id, flavor_id), group in eligible.groupby(["depot_id", "flavor_id"]):
                bottles = float(group["batch_bottles"].sum()) * float(rule.summer_share)
                if bottles <= 0:
                    continue
                weighted_age = float((group["age_days"] * group["batch_bottles"]).sum() / group["batch_bottles"].sum())
                rows.append({
                    "date": self.end,
                    "depot_id": depot_id,
                    "region": self.depots.set_index("depot_id").loc[depot_id, "region"],
                    "flavor_id": flavor_id,
                    "channel_id": rule.channel_id,
                    "bottles_written_off": bottles,
                    "weighted_batch_age_days": weighted_age,
                    "minimum_remaining_shelf_days": int(group["remaining_shelf_days"].min()),
                    "channel_cutoff_days": cutoff,
                    "cutoff_rule": rule.rule_basis,
                    "reason": "STOCK_AGING_BELOW_CHANNEL_REMAINING_SHELF_CUTOFF",
                    "uncalibrated_value_cr": bottles * price * valuation_fraction / CRORE,
                })
        columns = [
            "date", "depot_id", "region", "flavor_id", "channel_id", "bottles_written_off",
            "weighted_batch_age_days", "minimum_remaining_shelf_days", "channel_cutoff_days",
            "cutoff_rule", "reason", "uncalibrated_value_cr",
        ]
        result = pd.DataFrame(rows, columns=columns)
        target = float(self.cfg.case["writeoff_discount_cr"])
        raw_total = float(result["uncalibrated_value_cr"].sum()) if not result.empty else 0.0
        method = self.cfg.assumption("A068")
        if method == "AGING_STOCK_CALIBRATE_TO_CASE":
            factor = target / raw_total if raw_total > 0 else 0.0
        elif method == "AGING_STOCK_UNCALIBRATED":
            factor = 1.0
        else:
            raise ValueError("A068 must be AGING_STOCK_CALIBRATE_TO_CASE or AGING_STOCK_UNCALIBRATED")
        result["calibration_factor"] = factor
        result["writeoff_discount_cr"] = result["uncalibrated_value_cr"] * factor
        if method == "AGING_STOCK_CALIBRATE_TO_CASE" and not result.empty:
            result["writeoff_discount_cr"] = result["writeoff_discount_cr"].round(6)
            result.iloc[-1, result.columns.get_loc("writeoff_discount_cr")] += round(
                target - float(result["writeoff_discount_cr"].sum()), 6
            )
        result["bottles_revenue_equivalent"] = result["writeoff_discount_cr"] * CRORE / price
        result["value_classification"] = "FIFO_STOCK_AGING_DERIVED_WITH_DISCLOSED_CASE_CALIBRATION"
        reported = float(result["writeoff_discount_cr"].sum()) if not result.empty else 0.0
        reconciliation = pd.DataFrame([{
            "method": method,
            "uncalibrated_aging_value_cr": raw_total,
            "case_calibration_target_cr": target,
            "reported_writeoff_discount_cr": reported,
            "calibration_factor": factor,
            "uncalibrated_minus_target_cr": raw_total - target,
            "calibration_gap_cr": reported - raw_total,
            "aged_bottles_written_off": float(result["bottles_written_off"].sum()) if not result.empty else 0.0,
            "mt_qc_rule": f"Reject below {int(self.cfg.case['mt_qc_min_remaining_shelf_days'])} days remaining",
            "gt_rule": str(rules.loc[rules["channel_id"] == "GT", "rule_basis"].iloc[0]) if (rules["channel_id"] == "GT").any() else "No GT row configured",
            "status": "CALIBRATED_ALLOCATION_NOT_INDEPENDENT_CASE_VERIFICATION" if method == "AGING_STOCK_CALIBRATE_TO_CASE" else "UNCALIBRATED_MODEL_OUTPUT",
        }])
        return result, reconciliation

    def _apply_writeoffs(self, depot_flow: pd.DataFrame, writeoffs: pd.DataFrame) -> pd.DataFrame:
        flow = depot_flow.copy()
        flow["closing_before_writeoff_bottles"] = flow["closing_bottles"]
        if not writeoffs.empty:
            removals = writeoffs.groupby(["date", "depot_id", "flavor_id"])["bottles_written_off"].sum()
            keys = pd.MultiIndex.from_frame(flow[["date", "depot_id", "flavor_id"]])
            flow["writeoff_bottles"] = keys.map(removals).fillna(0.0).astype(float)
        flow["closing_bottles"] = flow["closing_bottles"] - flow["writeoff_bottles"]
        if (flow["closing_bottles"] < -1e-6).any():
            raise RuntimeError("Write-off exceeds available FIFO stock")
        flow["conservation_balance_bottles"] = (
            flow["opening_bottles"] + flow["production_receipts_bottles"]
            - flow["sales_bottles"] - flow["writeoff_bottles"] - flow["closing_bottles"]
        )
        return flow

    def _build_viral_profile(self) -> pd.DataFrame:
        ramp_days = int(self.cfg.case["viral_ramp_days"])
        dates = pd.date_range(self.cfg.viral_start, periods=ramp_days + 1, freq="D")
        peak = float(self.cfg.case["viral_qc_multiplier"])
        initial = self.cfg.number("A042")
        return pd.DataFrame({
            "date": dates,
            "flavor_id": "DP",
            "channel_id": "QC",
            "days_since_viral_start": np.arange(ramp_days + 1),
            "qc_demand_multiplier": initial + (peak - initial) * np.arange(ramp_days + 1) / ramp_days,
            "source": "CASE-STATED EVENT + MY ASSUMPTION FRONT-LOADED LINEAR RAMP",
            "VERIFIED_AGAINST_CASE_TEXT": "N",
        })

    def _build_events(self) -> pd.DataFrame:
        rival_lag_days = int(self.cfg.number("A067"))
        max_rival_lag_days = int(self.cfg.case["rival_launch_lag_weeks"]) * 7
        if not 0 <= rival_lag_days <= max_rival_lag_days:
            raise ValueError(f"A067 must be within the case's {max_rival_lag_days}-day rival-launch window")
        rows = [
            (self.cfg.launch_date, "LAUNCH", "Dragon Passion launch", "CASE-STATED", "Two-week procurement notice"),
            (self.cfg.viral_start, "VIRAL", "Influencer reel; QC ramp starts", "CASE-STATED", "4x ramp over 14 days"),
            (self.notice_date, "NOTICE", "Planners notice distributor shortages", "MY ASSUMPTION", "Exact notice date is synthetic"),
            (self.cfg.closure_start, "CLOSURE", "Passionfruit highway closes", "CASE-STATED", "Single road route"),
            (self.air_booking_date, "AIR_BOOK", "Emergency air freight booked", "MY ASSUMPTION", "Closure week 2"),
            (self.air_arrival_date, "AIR_ARRIVAL", "Emergency air pulp arrives", "MY ASSUMPTION", "Three-day booking-to-arrival lag"),
            (self.cfg.closure_end, "REOPEN", "Highway reopens after 21 days", "CASE-STATED", "Regular road lead time then applies"),
            (self.cfg.viral_start + pd.Timedelta(days=rival_lag_days), "RIVAL", "Rival dragonfruit-passionfruit launch", "MY ASSUMPTION", f"{rival_lag_days} days after viral start; within the case's {max_rival_lag_days}-day window"),
        ]
        events = pd.DataFrame(rows, columns=["event_date", "event_type", "event", "source", "details"]).sort_values("event_date")
        events["VERIFIED_AGAINST_CASE_TEXT"] = "N"
        return events


def write_datasets(datasets: dict[str, pd.DataFrame], output_dir: str | Path = "data") -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for name, frame in datasets.items():
        frame.to_csv(output / f"{name}.csv", index=False)
    # A standalone workbook makes the assumption register easy to review.
    with pd.ExcelWriter(output / "assumptions.xlsx", engine="openpyxl") as writer:
        datasets["assumptions"].to_excel(writer, sheet_name="Assumptions", index=False)
