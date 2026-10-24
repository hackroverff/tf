"""Configuration loading and validation.

All case facts and assumptions live outside the analytics code.  In particular,
adding a flavor, depot or channel only requires new configuration rows.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd


CONFIG_TABLES = (
    "flavors",
    "pulps",
    "bom",
    "depots",
    "channels",
    "suppliers",
    "routes",
    "monthly_seasonality",
    "allocation_options",
    "supply_options",
    "loss_attribution",
    "budget",
    "roadmap",
    "last_year_mix",
    "channel_shelf_life",
)


@dataclass(frozen=True)
class AppConfig:
    root: Path
    case: dict[str, Any]
    tables: dict[str, pd.DataFrame]
    assumptions: pd.DataFrame

    @property
    def year(self) -> int:
        return int(self.assumption("A001"))

    @property
    def seed(self) -> int:
        return int(self.assumption("A002"))

    def assumption(self, assumption_id: str) -> str:
        row = self.assumptions.loc[self.assumptions["assumption_id"] == assumption_id]
        if row.empty:
            raise KeyError(f"Missing assumption {assumption_id}")
        return str(row.iloc[0]["value"])

    def number(self, assumption_id: str) -> float:
        return float(self.assumption(assumption_id))

    def date(self, month_day: str) -> pd.Timestamp:
        return pd.Timestamp(f"{self.year}-{month_day}")

    @property
    def summer_start(self) -> pd.Timestamp:
        return self.date(self.case["summer_start_md"])

    @property
    def summer_end(self) -> pd.Timestamp:
        return self.date(self.case["summer_end_md"])

    @property
    def launch_date(self) -> pd.Timestamp:
        return self.date(self.case["launch_md"])

    @property
    def viral_start(self) -> pd.Timestamp:
        return self.date(self.case["viral_start_md"])

    @property
    def closure_start(self) -> pd.Timestamp:
        return self.date(self.case["closure_start_md"])

    @property
    def closure_end(self) -> pd.Timestamp:
        return self.closure_start + pd.Timedelta(days=int(self.case["closure_days"]) - 1)


def load_config(config_dir: str | Path = "config") -> AppConfig:
    """Load config relative to the repository, independent of notebook cwd."""
    config_path = Path(config_dir)
    if not config_path.is_absolute() and not config_path.exists():
        config_path = Path(__file__).resolve().parents[1] / config_path
    with (config_path / "case.json").open(encoding="utf-8") as handle:
        case = json.load(handle)
    tables = {
        name: pd.read_csv(config_path / f"{name}.csv") for name in CONFIG_TABLES
    }
    assumptions = pd.read_csv(config_path / "assumptions.csv", dtype=str)
    config = AppConfig(config_path.parent, case, tables, assumptions)
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    """Fail early with useful messages instead of producing inconsistent data."""
    flavors = config.tables["flavors"]
    channels = config.tables["channels"]
    depots = config.tables["depots"]
    pulps = config.tables["pulps"]
    bom = config.tables["bom"]
    suppliers = config.tables["suppliers"]
    routes = config.tables["routes"]

    if abs(flavors["summer_share"].sum() - 1.0) > 1e-9:
        raise ValueError("Flavor summer_share must sum to 1")
    if abs(channels["summer_share"].sum() - 1.0) > 1e-9:
        raise ValueError("Channel summer_share must sum to 1")
    if abs(depots["demand_weight"].sum() - 1.0) > 1e-9:
        raise ValueError("Depot demand_weight must sum to 1")
    # Base-case anchors are validated without blocking config-only scaling.
    if len(depots) == int(config.case["depot_count"]) and depots["region"].nunique() != int(config.case["region_count"]):
        raise ValueError("Base-case region count does not match case.json")
    if not set(bom["flavor_id"]).issubset(set(flavors["flavor_id"])):
        raise ValueError("BOM references an unknown flavor")
    if not set(bom["pulp_id"]).issubset(set(pulps["pulp_id"])):
        raise ValueError("BOM references an unknown pulp")
    if not set(suppliers["pulp_id"]) == set(pulps["pulp_id"]):
        raise ValueError("Every configured pulp needs one primary supplier row")
    if not set(suppliers["route_id"]).issubset(set(routes["route_id"])):
        raise ValueError("Supplier references an unknown route")
    if (bom["kg_per_bottle"] < 0).any():
        raise ValueError("BOM quantities cannot be negative")
    last_year = config.tables["last_year_mix"]
    if set(last_year["flavor_id"]) != set(flavors["flavor_id"]):
        raise ValueError("last_year_mix must contain every configured flavor exactly once")
    if abs(last_year["last_year_share"].sum() - 1.0) > 1e-9:
        raise ValueError("last_year_share must sum to 1")
    if (last_year["last_year_share"] < 0).any():
        raise ValueError("last_year_share cannot be negative")
    shelf_rules = config.tables["channel_shelf_life"]
    if set(shelf_rules["channel_id"]) != set(channels["channel_id"]):
        raise ValueError("channel_shelf_life must contain every configured channel")
    if (shelf_rules["min_remaining_days"] < 0).any():
        raise ValueError("Channel shelf-life cutoffs cannot be negative")
    if (shelf_rules["min_remaining_days"] > float(config.case["bottled_shelf_life_days"])).any():
        raise ValueError("Channel shelf-life cutoffs cannot exceed total bottled shelf life")
    mtqc = shelf_rules[shelf_rules["channel_id"].isin(["MT", "QC"])]
    if not mtqc.empty and not mtqc["min_remaining_days"].eq(float(config.case["mt_qc_min_remaining_shelf_days"])).all():
        raise ValueError("MT/QC cutoff must equal the case's 60-day remaining-shelf rule")
    domestic = config.case["dragonfruit_domestic_share"]
    if not 0 <= float(domestic) <= 1:
        raise ValueError("dragonfruit_domestic_share must be between zero and one")
    for flavor_id in ["DP", "DB"]:
        flavor_bom = bom[bom["flavor_id"] == flavor_id].set_index("pulp_id")["kg_per_bottle"]
        if {"DRAGON_DOM", "DRAGON_IMP"}.issubset(flavor_bom.index):
            total = float(flavor_bom["DRAGON_DOM"] + flavor_bom["DRAGON_IMP"])
            if total > 0 and abs(float(flavor_bom["DRAGON_DOM"]) / total - float(domestic)) > 1e-9:
                raise ValueError(f"{flavor_id} dragonfruit BOM does not match the case domestic share")
    imported_lead = suppliers.loc[suppliers["supplier_id"] == "SUP_DRAGON_IMP", "lead_time_days"]
    if not imported_lead.empty:
        lead = float(imported_lead.iloc[0])
        if not float(config.case["dragonfruit_imported_lead_min_days"]) <= lead <= float(config.case["dragonfruit_imported_lead_max_days"]):
            raise ValueError("Imported dragonfruit lead time is outside the case range")


def compiled_assumptions(config: AppConfig) -> pd.DataFrame:
    """Append row-level config assumptions to the scalar assumption register."""
    frames = [config.assumptions.copy()]

    def add(rows: list[dict[str, str]]) -> None:
        if not rows:
            return
        frame = pd.DataFrame(rows)
        frame["source"] = "MY ASSUMPTION"
        frame["VERIFIED_AGAINST_CASE_TEXT"] = "N"
        frames.append(frame)

    bom_rows = []
    for i, row in config.tables["bom"].iterrows():
        bom_rows.append({
            "assumption_id": f"BOM_{i + 1:03d}",
            "category": "BOM",
            "value": str(row["kg_per_bottle"]),
            "unit": "kg/bottle",
            "description": f"{row['flavor_id']} requires {row['pulp_id']}",
            "rationale": "BOM coefficients are not specified in the case",
        })
    add(bom_rows)

    availability_rows = []
    for _, row in config.tables["flavors"].iterrows():
        if row["availability_source"] == "MY ASSUMPTION":
            availability_rows.append({
                "assumption_id": f"AVAILABILITY_{row['flavor_id']}",
                "category": "Flavor availability",
                "value": str(row["available_from_md"]),
                "unit": "month-day",
                "description": f"{row['flavor_name']} is available from this synthetic date",
                "rationale": "Existing-flavor preseason availability is not specified",
            })
    add(availability_rows)

    channel_rows = []
    for _, row in config.tables["channels"].iterrows():
        if row["channel_id"] != "QC":
            channel_rows.append({
                "assumption_id": f"FEED_{row['channel_id']}",
                "category": "Channel data visibility",
                "value": f"marketing={row['marketing_feed_frequency']}; planner={row['planner_feed_frequency']}; outlet={row['outlet_data_available']}",
                "unit": "config",
                "description": f"Feed assumptions for {row['channel_name']}",
                "rationale": "Only QC daily marketing data and the GT outlet blind spot are case facts",
            })
    add(channel_rows)

    depot_rows = []
    for _, row in config.tables["depots"].iterrows():
        depot_rows.append({
            "assumption_id": f"DEPOT_{row['depot_id']}",
            "category": "Depot network",
            "value": str(row["demand_weight"]),
            "unit": "demand weight",
            "description": f"{row['depot_name']} in {row['region']}; stock profile={row['stock_profile']}",
            "rationale": "Synthetic depot identities, weights and imbalance profiles",
        })
    add(depot_rows)

    pulp_rows = []
    for _, row in config.tables["pulps"].iterrows():
        pulp_rows.append({
            "assumption_id": f"PULP_{row['pulp_id']}",
            "category": "Pulp cover",
            "value": str(row["opening_cover_days"]),
            "unit": "days",
            "description": f"Opening cover for {row['pulp_name']}",
            "rationale": "Only passionfruit cover at closure is a case fact",
        })
    add(pulp_rows)

    supplier_rows = []
    for _, row in config.tables["suppliers"].iterrows():
        supplier_rows.append({
            "assumption_id": f"SUPPLIER_{row['supplier_id']}",
            "category": "Supplier economics",
            "value": f"lead={row['lead_time_days']}d; cost={row['normal_cost_per_kg']}/kg; qualified={row['qualified_supplier_count']}",
            "unit": "config",
            "description": f"Primary supplier parameters for {row['pulp_id']}",
            "rationale": "Costs and non-case supplier/lead-time details are synthetic",
        })
    add(supplier_rows)

    route_rows = []
    for _, row in config.tables["routes"].iterrows():
        if row["route_id"] == "R_PASSION":
            continue
        route_rows.append({
            "assumption_id": f"ROUTE_{row['route_id']}",
            "category": "Route risk",
            "value": f"transit={row['transit_days']}d; closure={row['summer_closure_probability']}",
            "unit": "config",
            "description": f"Route parameters for {row['route_name']}",
            "rationale": "Non-passionfruit route details are synthetic",
        })
    add(route_rows)

    season_rows = []
    for _, row in config.tables["monthly_seasonality"].iterrows():
        season_rows.append({
            "assumption_id": f"SEASON_{int(row['month']):02d}",
            "category": "Demand shape",
            "value": str(row["multiplier"]),
            "unit": "multiplier",
            "description": f"Month {int(row['month'])} daily demand weight",
            "rationale": "Within-season seasonality is not supplied",
        })
    add(season_rows)

    option_rows = []
    for _, row in config.tables["allocation_options"].iterrows():
        option_rows.append({
            "assumption_id": f"ALLOC_{row['option_id']}",
            "category": "Shortage allocation",
            "value": str(row["dp_pulp_share"]),
            "unit": "DP share of available passionfruit pulp",
            "description": row["option_name"],
            "rationale": row["trade_off"],
        })
    for _, row in config.tables["supply_options"].iterrows():
        option_rows.append({
            "assumption_id": f"SUPPLY_OPTION_{row['option_id']}",
            "category": "Supply option economics",
            "value": f"cost={row['year1_cost_cr']}cr; loss_reduction={row['expected_loss_reduction']}; air_reduction={row['air_cost_reduction']}",
            "unit": "config",
            "description": row["option_name"],
            "rationale": row["notes"],
        })
    for _, row in config.tables["loss_attribution"].iterrows():
        option_rows.append({
            "assumption_id": f"ATTRIBUTION_{row['root_cause_id']}",
            "category": "Loss attribution and capture",
            "value": f"contribution_share={row['lost_contribution_share']}; air_share={row['air_freight_share']}; writeoff_share={row['writeoff_share']}; capture={row['low_capture']}/{row['base_capture']}/{row['high_capture']}",
            "unit": "shares",
            "description": row["root_cause"],
            "rationale": row["evidence"],
        })
    for _, row in config.tables["budget"].iterrows():
        option_rows.append({
            "assumption_id": f"BUDGET_{row['item_id']}",
            "category": "First-year budget",
            "value": str(row["cost_cr"]),
            "unit": "Rs cr",
            "description": f"{row['line_item']} (selected={row['selected']})",
            "rationale": row["notes"],
        })
    for _, row in config.tables["roadmap"].iterrows():
        option_rows.append({
            "assumption_id": f"ROADMAP_{row['month']}",
            "category": "Eight-month roadmap",
            "value": str(row["month"]),
            "unit": "programme month",
            "description": row["live_capability"],
            "rationale": row["adoption_gate"],
        })
    for _, row in config.tables["last_year_mix"].iterrows():
        option_rows.append({
            "assumption_id": f"LAST_YEAR_MIX_{row['flavor_id']}",
            "category": "Opening depot mix",
            "value": str(row["last_year_share"]),
            "unit": "share",
            "description": f"Pre-viral/pre-launch opening-stock share for {row['flavor_id']}",
            "rationale": "Last-year depot mix is not supplied; DP and DB are zero before launch",
        })
    for _, row in config.tables["channel_shelf_life"].iterrows():
        option_rows.append({
            "assumption_id": f"SHELF_RULE_{row['channel_id']}",
            "category": "Channel shelf-life governance",
            "value": str(row["min_remaining_days"]),
            "unit": "days remaining",
            "description": f"{row['channel_id']}: {row['rule_basis']}",
            "rationale": row["rule_status"],
        })
    add(option_rows)

    result = pd.concat(frames, ignore_index=True)
    if "VERIFIED_AGAINST_CASE_TEXT" not in result:
        result["VERIFIED_AGAINST_CASE_TEXT"] = "N"
    result["VERIFIED_AGAINST_CASE_TEXT"] = result["VERIFIED_AGAINST_CASE_TEXT"].fillna("N")
    columns = ["assumption_id", "category", "value", "unit", "description", "rationale", "source", "VERIFIED_AGAINST_CASE_TEXT"]
    return result[columns].drop_duplicates(subset=["assumption_id"], keep="first")
