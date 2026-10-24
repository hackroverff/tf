#!/usr/bin/env python3
"""Build the audit-grade assumptions register from the actual project files.

This adds case-encoded inputs, derived values and material implicit modeling
choices to the original ASSUMPTION-only export. It also identifies scalar
"parameters" whose values are documentary because Python never reads them.
"""
from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
import re

import pandas as pd

from src.config import compiled_assumptions, load_config


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "assumptions_register.csv"
PY_FILES = sorted((ROOT / "src").rglob("*.py")) + [ROOT / "app.py", ROOT / "generate_data.py"]


@lru_cache(maxsize=1)
def function_segments() -> tuple[tuple[str, str, str], ...]:
    """Parse Python files once and return (path, qualified function, source)."""
    segments: list[tuple[str, str, str]] = []
    for path in PY_FILES:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            segment = ast.get_source_segment(source, node) or ""
            names = [node.name]
            parent = parents.get(node)
            while parent is not None and not isinstance(parent, ast.Module):
                if isinstance(parent, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.append(parent.name)
                parent = parents.get(parent)
            segments.append((str(path.relative_to(ROOT)), ".".join(reversed(names)), segment))
    return tuple(segments)


def code_references(token: str) -> list[str]:
    """Return functions/methods containing a literal configuration token."""
    pattern = re.compile(rf"\b{re.escape(token)}\b")
    return [
        f"{path}::{function}"
        for path, function, segment in function_segments()
        if pattern.search(segment)
    ]


# Formerly documentary scalar IDs are now live. Removed legacy stock
# factors A020-A024 are documented in CHANGELOG.md, not presented as knobs.
DOCUMENTARY_LOCATIONS: dict[str, str] = {}


ROW_LOCATIONS = {
    "BOM_": "config/bom.csv; src/data_generator.py::SyntheticDataGenerator._constrain_and_build_pulp; src/demand.py::build_demand_scenarios; src/supply.py::shortage_allocation_options",
    "AVAILABILITY_": "config/flavors.csv; src/data_generator.py::SyntheticDataGenerator._build_demand_and_sales and _build_scheduled_production",
    "FEED_": "config/channels.csv (frequency fields are documentary); src/demand.py::weekly_rolling_reforecast and estimate_censored_demand",
    "DEPOT_": "config/depots.csv; src/data_generator.py::SyntheticDataGenerator._build_demand_and_sales, _build_depot_stock and _build_writeoffs; src/control_tower.py",
    "PULP_": "config/pulps.csv; src/data_generator.py::SyntheticDataGenerator._constrain_and_build_pulp; src/demand.py::launch_readiness_gate",
    "SUPPLIER_": "config/suppliers.csv; src/data_generator.py::SyntheticDataGenerator._constrain_and_build_pulp; src/supply.py::build_exposure_map; src/demand.py::launch_readiness_gate",
    "ROUTE_": "config/routes.csv; src/supply.py::build_exposure_map; src/data_generator.py::SyntheticDataGenerator._constrain_and_build_pulp",
    "SEASON_": "config/monthly_seasonality.csv; src/data_generator.py::SyntheticDataGenerator._daily_weights",
    "ALLOC_": "config/allocation_options.csv; src/supply.py::shortage_allocation_options",
    "SUPPLY_OPTION_": "config/supply_options.csv; src/supply.py::supply_option_economics; src/replay.py::build_scenario_replay; src/budget.py::build_budget",
    "ATTRIBUTION_": "config/loss_attribution.csv; src/links.py::build_loss_attribution; src/budget.py::budget_impact",
    "BUDGET_": "config/budget.csv; src/budget.py::build_budget and budget_impact",
    "ROADMAP_": "config/roadmap.csv; src/pages/budget_architecture.py::render_budget; src/budget.py::budget_reconciliation",
    "LAST_YEAR_MIX_": "config/last_year_mix.csv; src/data_generator.py::SyntheticDataGenerator._build_depot_stock; src/reconciliation.py::reconcile (CONSERVE_05/06)",
    "SHELF_RULE_": "config/channel_shelf_life.csv; src/config.py::validate_config; src/data_generator.py::SyntheticDataGenerator._build_writeoffs",
}

HIGH_A = {
    "A003", "A006", "A007", "A008", "A009", "A010", "A011", "A014", "A015", "A016", "A017", "A018",
    "A021", "A022", "A023", "A024", "A025", "A027", "A029", "A030", "A031", "A032", "A033", "A034",
    "A035", "A036", "A041", "A042", "A047", "A048", "A049", "A050", "A051", "A062", "A064", "A068",
    "A071", "A072",
}
LOW_A = {"A001", "A002", "A004", "A005", "A012", "A013", "A019", "A028", "A037", "A038", "A039", "A040", "A046", "A052", "A053", "A054", "A055", "A057", "A058", "A059", "A060", "A061", "A063", "A065", "A066", "A067", "A069"}


def existing_impact(assumption_id: str, category: str) -> str:
    if assumption_id in HIGH_A:
        return "High"
    if assumption_id in LOW_A:
        return "Low"
    if assumption_id.startswith(("ATTRIBUTION_", "SUPPLY_OPTION_", "ALLOC_", "BOM_")):
        return "High"
    if assumption_id.startswith("BUDGET_"):
        return "Med"
    if assumption_id.startswith("ROADMAP_"):
        return "Low"
    if assumption_id.startswith(("DEPOT_", "PULP_", "SUPPLIER_", "SEASON_")):
        return "Med"
    if category in {"Censoring", "Buffer economics", "Closure scenarios", "Loss attribution and capture"}:
        return "High"
    return "Med"


CASE_META = {
    "annual_revenue_cr": ("Annual company revenue", "Rs cr", "High"),
    "contribution_margin": ("Company-average contribution margin", "fraction", "High"),
    "price_per_bottle": ("Average price per bottle", "Rs/bottle", "High"),
    "annual_bottles": ("Annual bottle volume", "bottles", "High"),
    "summer_revenue_share": ("Summer share of annual revenue/volume under uniform price", "fraction", "High"),
    "summer_bottles": ("Latent summer demand", "bottles", "High"),
    "summer_start_md": ("Synthetic summer start month-day", "month-day", "High"),
    "summer_end_md": ("Synthetic summer end month-day", "month-day", "High"),
    "plant_count": ("Number of in-house plants", "plants", "Med"),
    "combined_monthly_capacity_bottles": ("Combined in-house monthly capacity", "bottles/month", "High"),
    "summer_utilisation": ("Summer capacity utilisation", "fraction", "High"),
    "copacker_max_volume_share": ("Maximum co-packer volume share", "fraction of combined in-house capacity", "High"),
    "copacker_cost_premium": ("Co-packer variable-cost premium", "fraction", "High"),
    "copacker_notice_days": ("Co-packer notice requirement", "days", "High"),
    "depot_count": ("Number of depots", "depots", "Med"),
    "region_count": ("Number of regions", "regions", "Med"),
    "gt_distributor_count": ("GT distributor count", "distributors", "Low"),
    "frozen_pulp_shelf_life_days": ("Frozen-pulp shelf life", "days", "High"),
    "bottled_shelf_life_days": ("Bottled-juice shelf life", "days", "High"),
    "mt_qc_min_remaining_shelf_days": ("MT/QC minimum remaining shelf life at receipt", "days", "High"),
    "passion_road_transit_days": ("Passionfruit road transit", "days", "High"),
    "passion_closure_probability": ("Annual passionfruit-road closure probability", "probability", "High"),
    "passion_cover_days_at_closure": ("Passionfruit old-baseline cover at closure", "days", "High"),
    "depot_cover_days": ("Depot target cover", "days", "High"),
    "transfer_min_days": ("Same-region transfer duration used by the prototype", "days", "Med"),
    "transfer_max_days": ("Cross-region transfer duration used by the prototype", "days", "Med"),
    "transfer_cost_per_bottle": ("Inter-depot transfer cost", "Rs/bottle", "High"),
    "forecast_error": ("Monthly forecast WAPE anchor", "fraction", "Med"),
    "launch_md": ("Dragon Passion launch month-day", "month-day", "High"),
    "launch_notice_days": ("Launch procurement notice", "days", "High"),
    "viral_start_md": ("Viral reel/ramp start month-day", "month-day", "High"),
    "viral_ramp_days": ("Time to reach peak QC multiplier", "days", "High"),
    "viral_qc_multiplier": ("Peak DP QC multiplier", "multiplier", "High"),
    "closure_start_md": ("Passionfruit highway closure start month-day", "month-day", "High"),
    "closure_days": ("Passionfruit highway closure duration", "days", "High"),
    "air_freight_cost_cr": ("Actual emergency air-freight cost", "Rs cr", "High"),
    "air_cost_multiplier": ("Emergency air cost multiple", "multiplier", "High"),
    "summer_revenue_loss_share": ("Summer bottle/revenue loss share under uniform price", "fraction", "High"),
    "writeoff_discount_cr": ("Depot write-offs and discounts", "Rs cr", "High"),
    "rival_launch_lag_weeks": ("Rival launch lag", "weeks", "Med"),
    "dragonfruit_domestic_share": ("Domestic share of dragonfruit pulp", "fraction", "High"),
    "dragonfruit_imported_lead_min_days": ("Imported dragonfruit minimum lead time", "days", "High"),
    "dragonfruit_imported_lead_max_days": ("Imported dragonfruit maximum lead time", "days", "High"),
    "baseline_window_days": ("Demand-detector rolling baseline", "days", "High"),
    "amber_multiplier": ("Amber signal/baseline threshold", "multiplier", "High"),
    "amber_consecutive_days": ("Amber consecutive-day requirement", "days", "High"),
    "red_multiplier": ("Red signal/baseline threshold", "multiplier", "High"),
    "red_consecutive_days": ("Red consecutive-day requirement", "days", "High"),
}

# Every operational case key is read. Unit/metadata conventions are documented
# separately; no stale "unused" locations are retained in this register.
UNUSED_CASE_LOCATIONS: dict[str, str] = {}



def row(row_id: str, assumption: str, value: object, source: str, why: str, where: str, impact: str) -> dict:
    return {
        "ID": row_id,
        "Assumption": assumption,
        "Value used": value,
        "Source": source,
        "VERIFIED_AGAINST_CASE_TEXT": "N",
        "Why it was needed": why,
        "Where in code": where,
        "Impact if wrong": impact,
    }


def main() -> int:
    config = load_config()
    rows: list[dict] = []

    # CASE-STATED means "encoded as a case input in this repository". The
    # original case document is not included, so this audit cannot independently
    # verify every source label against that document.
    for key, value in config.case.items():
        if key in {"case_name", "currency", "crore"}:
            continue
        description, unit, impact = CASE_META[key]
        references = code_references(key)
        where = "config/case.json"
        if key in UNUSED_CASE_LOCATIONS:
            where = UNUSED_CASE_LOCATIONS[key]
        elif references:
            where += "; " + "; ".join(references)
        else:
            where += "; no direct Python reference found"
        source = "DERIVED FROM CASE" if key == "annual_bottles" else "CASE-STATED"
        why = "Case anchor for the prototype; source classification is as encoded in this repository, not independently re-verified"
        if key == "annual_bottles":
            why = "Derived as Rs1,200 cr × 10,000,000 / Rs60 = 200,000,000 bottles"
        rows.append(row(f"CASE_{key.upper()}", description, f"{value} {unit}", source, why, where, impact))

    # Case-marked rows in operational CSVs are not included by
    # compiled_assumptions(), so add them explicitly as well.
    case_table_rows: list[dict] = []
    for flavor in config.tables["flavors"].itertuples():
        case_table_rows.append(row(
            f"CASE_FLAVOR_{flavor.flavor_id}_SHARE", f"Summer flavor share: {flavor.flavor_name}",
            f"{flavor.summer_share} fraction", "CASE-STATED",
            "Case-marked flavor mix needed to apportion the 96 m summer total",
            "config/flavors.csv; src/data_generator.py::SyntheticDataGenerator._build_demand_and_sales; src/supply.py::build_exposure_map", "High",
        ))
    for channel in config.tables["channels"].itertuples():
        case_table_rows.append(row(
            f"CASE_CHANNEL_{channel.channel_id}_SHARE", f"Summer channel share: {channel.channel_name}",
            f"{channel.summer_share} fraction", "CASE-STATED",
            "Case-marked channel mix needed to apportion every flavor's summer volume",
            "config/channels.csv; src/data_generator.py::SyntheticDataGenerator._build_demand_and_sales", "High",
        ))
    case_table_rows.extend([
        row("CASE_DP_AVAILABILITY", "Dragon Passion is unavailable before launch", "03-03 month-day", "CASE-STATED", "Pre-launch DP demand must be zero", "config/flavors.csv; src/data_generator.py::SyntheticDataGenerator._build_demand_and_sales", "High"),
        row("CASE_QC_DAILY_FEED", "QC daily marketing sell-through with month-end planner consolidation", "Daily marketing; month-end planner; outlet data=1", "CASE-STATED", "Defines the demand-sensing and latency story", "config/channels.csv; src/data_generator.py::SyntheticDataGenerator._build_qc_feed", "High"),
        row("CASE_GT_NO_OUTLET_DATA", "GT outlet-level data is unavailable", "outlet_data_available=0", "CASE-STATED", "Requires a labelled distributor-order/secondary-sales proxy rather than invented outlet truth", "config/channels.csv; src/demand.py::estimate_censored_demand and weekly_rolling_reforecast", "High"),
        row("CASE_PASSION_SINGLE_SOURCE", "Passionfruit has one qualified supplier", "qualified_supplier_count=1; single_source_flag=1", "CASE-STATED", "Drives supply-fragility exposure and launch risk", "config/suppliers.csv; src/supply.py::build_exposure_map", "High"),
        row("CASE_PASSION_LEAD_TIME", "Passionfruit supplier/road lead time", "3 days", "CASE-STATED", "Used for inbound booking dates, reopening lag and launch cover", "config/suppliers.csv and config/routes.csv; src/data_generator.py::SyntheticDataGenerator._constrain_and_build_pulp; src/demand.py::launch_readiness_gate", "High"),
        row("CASE_PASSION_SINGLE_ROUTE", "Passionfruit has one road route", "single_route_flag=1", "CASE-STATED", "Drives closure exposure; there is no alternate physical route in the generator", "config/routes.csv; src/supply.py::build_exposure_map", "High"),
        row("CASE_BUDGET_CAP", "Selected first-year build-plus-run budget cap", "Rs2.50 cr", "CASE-STATED", "Explicit project constraint; the selected package is checked against it", "src/budget.py::build_budget and budget_reconciliation (hardcoded 2.50; not stored in config/case.json)", "High"),
    ])
    rows.extend(case_table_rows)

    derived = [
        row("DERIVED_SUMMER_CAPACITY", "Mar-Jun in-house capacity", "25,000,000 × 4 = 100,000,000 bottles", "DERIVED FROM CASE", "Capacity reconciliation and utilisation denominator", "src/reconciliation.py::reconcile (CAP_01)", "High"),
        row("DERIVED_SUMMER_PRODUCTION", "Mar-Jun actual production", "100,000,000 × 95% = 95,000,000 bottles", "DERIVED FROM CASE", "Match the case utilisation anchor", "src/data_generator.py::SyntheticDataGenerator._build_scheduled_production; src/reconciliation.py::reconcile (CAP_02)", "High"),
        row("DERIVED_LOST_BOTTLES", "Stock-out-censored summer bottles", "96,000,000 × 8% = 7,680,000 bottles", "DERIVED FROM CASE", "Separate latent demand from realised sales", "src/data_generator.py::SyntheticDataGenerator._allocate_case_losses; src/reconciliation.py::reconcile (LOSS_01)", "High"),
        row("DERIVED_LOST_REVENUE", "Lost summer revenue", "7,680,000 × Rs60 / 10,000,000 = Rs46.08 cr", "DERIVED FROM CASE", "Revenue context; not added to contribution", "src/links.py::build_loss_attribution; src/reconciliation.py::reconcile (LOSS_02)", "High"),
        row("DERIVED_LOST_CONTRIBUTION", "Lost summer contribution", "Rs46.08 cr × 32% = Rs14.7456 cr", "DERIVED FROM CASE", "Economic-impact and attribution base", "src/links.py::build_loss_attribution; src/reconciliation.py::reconcile (LOSS_03)", "High"),
        row("DERIVED_COPACKER_CAPACITY", "Co-packer monthly capacity base", "25,000,000 × 10% = 2,500,000 bottles/month", "DERIVED FROM CASE", "Define maximum co-packer headroom", "src/data_generator.py::SyntheticDataGenerator._build_capacity; src/supply.py::constrained_weekly_planner", "High"),
        row("DERIVED_VARIABLE_COST", "Base variable cost used for co-packer premium", "Rs60 × (1 − 32%) = Rs40.80/bottle", "DERIVED FROM CASE", "Convert 25% co-packer premium to rupees", "src/supply.py::constrained_weekly_planner (default base_variable_cost_per_bottle)", "High"),
        row("DERIVED_MT_QC_PREBUILD", "Maximum MT/QC finished-goods prebuild", "90 − 60 = 30 days", "DERIVED FROM CASE", "Preserve 60 days remaining shelf life at receipt", "src/supply.py::constrained_weekly_planner; displayed as a rule, not a dynamic inventory constraint", "High"),
        row("DERIVED_CLOSURE_END", "Highway reopening date", "2026-05-10 + 20 days = 2026-05-30", "DERIVED FROM CASE", "Create an inclusive 21-day closure", "src/config.py::AppConfig.closure_end; src/data_generator.py::SyntheticDataGenerator._build_events", "High"),
    ]
    rows.extend(derived)

    # Enrich every compiled config assumption with a live code reference.
    original = compiled_assumptions(config)
    for item in original.to_dict("records"):
        assumption_id = item["assumption_id"]
        references = code_references(assumption_id)
        if assumption_id in DOCUMENTARY_LOCATIONS:
            where = "config/assumptions.csv; " + DOCUMENTARY_LOCATIONS[assumption_id]
        else:
            prefix = next((prefix for prefix in ROW_LOCATIONS if assumption_id.startswith(prefix)), None)
            if prefix:
                where = ROW_LOCATIONS[prefix]
            elif references:
                where = "config/assumptions.csv; " + "; ".join(references)
            else:
                where = "config/assumptions.csv; no direct Python reference found"
        value = str(item["value"])
        if str(item["unit"]):
            value += f" {item['unit']}"
        rows.append(row(
            assumption_id, item["description"], value, "MY ASSUMPTION", item["rationale"], where,
            existing_impact(assumption_id, item["category"]),
        ))

    implicit = [
        row("MODEL_INDEPENDENT_FLAVOR_CHANNEL_MIX", "The case channel mix is applied independently to every flavor", "GT/MT/QC = 55%/25%/20% within every flavor in the baseline", "MY ASSUMPTION", "No flavor-specific channel split is supplied; needed to allocate each flavor across channels", "src/data_generator.py::SyntheticDataGenerator._build_demand_and_sales (outer product of flavor and channel shares)", "High"),
        row("MODEL_DP_QC_SHARE", "Dragon Passion QC share", "20% of DP = 2,304,000 bottles; 2.4% of total summer demand in the baseline", "MY ASSUMPTION", "The case gives total QC mix, not DP's channel mix; the detector needs a DP QC series", "src/data_generator.py::SyntheticDataGenerator._build_demand_and_sales; follows MODEL_INDEPENDENT_FLAVOR_CHANNEL_MIX", "High"),
        row("MODEL_VIRAL_APPLICATION", "How the 4× event is applied", "DP QC daily weight: editable A042 2.5× linearly to 4× at day 14; GT/MT receive 35% of uplift above 1 in historical generation", "MY ASSUMPTION", "The case gives an endpoint and duration, not the response path, cross-channel propagation or normalization", "src/data_generator.py::SyntheticDataGenerator._daily_weights and _build_demand_and_sales; src/sensitivity.py::scenario_config", "High"),
        row("MODEL_UNIFORM_PRICE_MARGIN", "Uniform price and contribution margin across flavors and channels", "Rs60 and 32% applied to every flavor/channel", "MY ASSUMPTION", "Case supplies company averages, not a flavor/channel margin matrix; needed for all rupee impacts", "src/links.py::build_loss_attribution; src/supply.py::passionfruit_requirement_profile and shortage_allocation_options; src/control_tower.py::suggest_depot_transfers", "High"),
        row("MODEL_GT_ORDER_GENERATION", "GT distributor orders are generated from latent GT ground truth", "round(latent × (1 + Normal(0, 0.15))), floored at realised sales and zero", "MY ASSUMPTION", "No GT outlet data exists; a noisy proxy was needed for censoring correction", "src/data_generator.py::SyntheticDataGenerator._build_demand_and_sales; src/demand.py::estimate_censored_demand", "High"),
        row("MODEL_LOSS_ALLOCATION", "Stock-out losses remain case-calibrated rather than physically derived", "Event-risk-weighted latent rows scaled to exactly 7,680,000 bottles", "MY ASSUMPTION", "The case total is known but its row-level distribution is not; production→depot→sales conservation is applied to the resulting realised sales", "src/data_generator.py::SyntheticDataGenerator._allocate_case_losses; src/reconciliation.py::reconcile (LOSS_01 and CONSERVE_01)", "High"),
        row("MODEL_DEPOT_STOCK_BASIS", "Opening depot mix and subsequent stock balance", "Three weeks of preseason run rate × last_year_mix (DP=0), then opening + production receipts − sales − write-offs = closing", "MY ASSUMPTION", "No last-year depot data or transactional shipment history exists; a non-forward-looking, conserved synthetic balance was needed", "config/last_year_mix.csv; src/data_generator.py::SyntheticDataGenerator._build_depot_stock and _apply_writeoffs; src/reconciliation.py::reconcile (CONSERVE_01–06)", "High"),
        row("MODEL_COPACKER_FLAVOR_FLEXIBILITY", "Co-packer flexibility remaining after BOM feasibility", "Flavor-level BOM constraints; no changeover, line-eligibility or yield-loss matrix", "MY ASSUMPTION", "No co-packer flexibility details are supplied", "src/supply.py::constrained_weekly_planner and _scale_plan_to_pulp", "High"),
        row("MODEL_CAPACITY_PULP_COUPLING", "Joint weekly bottle and pulp feasibility", "Opening pulp only; in-house draws first; eligible co-packer uses remaining balances; closing stock carries forward with no unconfirmed inbound", "MY ASSUMPTION", "Capacity must not create unavailable pulp; future confirmed inbound was not supplied", "src/analysis.py::build_analysis; src/supply.py::constrained_weekly_planner", "High"),
        row("MODEL_COPACKER_ACTUAL_ZERO", "Generated actual co-packer production", "0 bottles in every Jan-Jun month", "MY ASSUMPTION", "The case capacity table needs an actual/available distinction; no co-packer production history is supplied", "src/data_generator.py::SyntheticDataGenerator._build_capacity", "Med"),
        row("MODEL_PHYSICAL_FLOW_COUPLING", "Production-to-depot allocation needed to conserve realised sales", "Same-day sales mix guides receipts, subject to each depot's minimum shortfall after opening stock; FIFO batches carry the balance", "MY ASSUMPTION", "No actual lane-level shipment manifest is supplied; this allocation prevents negative stock and preserves exact totals", "src/data_generator.py::SyntheticDataGenerator._build_depot_stock; src/reconciliation.py::reconcile (CONSERVE_01–04)", "High"),
        row("MODEL_BUFFER_OBJECTIVE", "Buffer and emergency-air economic convention", "Minimise carry/storage + expected contribution loss + expected air premium over 0–4 weeks; air-only separately assumes all shortage is covered in time", "MY ASSUMPTION", "A comparable buffer-versus-air view and explicit break-even probability were required; emergency response effectiveness is not supplied", "src/supply.py::calculate_buffer_option, optimise_buffer and air_only_comparison", "High"),
        row("MODEL_AIR_LOT_QUANTITY", "Emergency air lot size inferred from the case cost", "Rs3.2 cr / (Rs180/kg × 5) = 35,555.56 kg under TOTAL_DELIVERED_COST", "MY ASSUMPTION", "Physical air arrival required kg; neither normal pulp cost nor the 5× cost interpretation is fully specified", "src/data_generator.py::SyntheticDataGenerator._constrain_and_build_pulp; live A036 cost-basis rule", "High"),
        row("MODEL_ECONOMIC_IMPACT_CONVENTION", "Headline economic-impact convention", "Rs14.7456 cr contribution + full Rs3.20 cr air + Rs6.00 cr write-offs = Rs23.9456 cr", "MY ASSUMPTION", "A non-revenue-double-counting summary was needed; the case does not supply this combined total or prove category independence", "src/links.py::build_loss_attribution and attribution_reconciliation", "High"),
        row("MODEL_CENSORING_CORRECTION", "Operational stock-out censoring correction", "In-stock sales unchanged; GT uses distributor orders when above sales/baseline; other stock-outs use recursive trailing-14-day corrected mean or sales lower bound", "MY ASSUMPTION", "Sales are availability-censored, but latent demand is unobserved; a confidence-labelled proxy was needed", "src/demand.py::estimate_censored_demand and prepare_qc_signal", "High"),
        row("MODEL_REFORECAST_EVALUATION_TARGET", "Weekly reforecast evaluation target", "Next-week corrected synthetic demand, not GT outlet truth; WAPE is a footnote while Amber reaction lead is the operating claim", "MY ASSUMPTION", "Operational functions must not read latent ground truth; only synthetic corrected history is available", "src/demand.py::weekly_rolling_reforecast; src/analysis.py::build_analysis; src/pages/demand_supply.py::render_demand", "High"),
        row("MODEL_APPROVAL_CHAIN", "Proposed approval and escalation chain", "Planner / S&OP Lead / COO roles; required approver is enforced and COO is mandatory for peak-season approvals; no authenticated identity or sequential signatures", "MY ASSUMPTION", "Human decision ownership was required, but no org-level identity/permission system is available", "src/recommendations.py::build_risk_register and apply_decision; src/pages/decisions_replay.py::_decide", "Med"),
        row("MODEL_REPLAY_BUFFER_VISUAL", "Replay buffer line is a static stress-test", "Actual production cover + optimiser-selected buffer weeks; no physical re-simulation", "MY ASSUMPTION", "A counterfactual visual was needed without rebuilding all inventory and production flows", "src/replay.py::build_scenario_replay (model_static_buffer_cover_weeks)", "Med"),
        row("MODEL_WRITEOFF_CALIBRATION", "FIFO stock-aging write-off valuation and case calibration", "Raw Rs5.3572887 cr × 1.11996951 = reported Rs6.0000000 cr; disclosed gap Rs0.6427113 cr", "MY ASSUMPTION", "MT/QC cutoff failures determine eligible bottles and relative allocation; the case total is retained only as a calibration target", "src/data_generator.py::SyntheticDataGenerator._build_writeoffs; data/writeoff_reconciliation.csv; src/reconciliation.py::reconcile (WRITE_01–06)", "High"),
        row("MODEL_AVOIDED_LOSS_BASIS", "Avoided-loss estimation basis", "ASSUMPTION-BASED, NOT SIMULATED: Rs6.325632 / Rs11.643392 / Rs16.432512 cr LOW/BASE/HIGH at baseline", "MY ASSUMPTION", "Only root-cause allocations and capture rates are available; no historical intervention trial or causal simulation exists", "src/links.py::build_loss_attribution; src/replay.py::build_scenario_replay; src/sensitivity.py::avoided_loss_range", "High"),
    ]
    rows.extend(implicit)

    result = pd.DataFrame(rows)
    assert result["ID"].is_unique, result[result["ID"].duplicated(keep=False)]
    assert set(result["Source"]) <= {"CASE-STATED", "DERIVED FROM CASE", "MY ASSUMPTION"}
    assert set(result["Impact if wrong"]) <= {"Low", "Med", "High"}
    required = {"A003", "A025", "A029", "A030", "A042", "BOM_011", "MODEL_DP_QC_SHARE", "MODEL_COPACKER_FLAVOR_FLEXIBILITY", "MODEL_APPROVAL_CHAIN", "MODEL_DEPOT_STOCK_BASIS", "MODEL_BUFFER_OBJECTIVE", "A071", "A072"}
    assert required <= set(result["ID"])
    assert result["VERIFIED_AGAINST_CASE_TEXT"].isin(["Y", "N"]).all()
    assert result.loc[result["Source"].isin(["CASE-STATED", "DERIVED FROM CASE"]), "VERIFIED_AGAINST_CASE_TEXT"].eq("N").all()
    result.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(result)} unique rows to {OUTPUT}")
    print(result.groupby(["Source", "Impact if wrong"]).size().unstack(fill_value=0).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
