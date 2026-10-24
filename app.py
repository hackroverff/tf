"""Pulp Riot Juice Co. — Dragon Passion control-tower prototype.

Run locally:
    streamlit run app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.analysis import build_analysis
from src.config import load_config
from src.data_generator import SyntheticDataGenerator
from src.data_loader import load_datasets
from src.export import excel_export_bytes
from src.pages.assumptions_sensitivity import render_assumptions_sensitivity
from src.pages.budget_architecture import render_architecture, render_budget
from src.pages.decisions_replay import render_recommendations, render_replay
from src.pages.demand_supply import render_demand, render_supply
from src.pages.overview_links import render_control_tower, render_links, render_what_went_wrong
from src.quality import apply_missing_feed_fallbacks
from src.recommendations import empty_approval_log
from src.reconciliation import reconcile
from src.sensitivity import ramp_lead_sensitivity, scenario_config


DEFAULT_SCENARIO = (2.5, "2026-03-31", "BASE", 1.0, 0.60, 0.20)
NAV_GROUPS = {
    "Overview": ["Control Tower", "What Went Wrong"],
    "Deep dives": ["Demand", "Supply", "Causal Link Map"],
    "Decisions": ["Recommendations", "Scenario Replay", "Budget & Impact"],
    "Evidence & system": ["Assumptions & Sensitivity", "Architecture & Data Quality"],
}

st.set_page_config(
    page_title="Pulp Riot | Dragon Passion Control Tower",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """<style>
    :root {--accent:#0F6B6D;--navy:#17324D;--text:#223042;--muted:#617182;--line:#DCE5E9;}
    .stApp {background:#F5F7F9;color:var(--text);font-family:Arial,sans-serif;}
    .block-container {padding-top:1rem;padding-bottom:2rem;max-width:1540px;}
    [data-testid="stSidebar"] {background:#FFFFFF;border-right:1px solid var(--line);}
    [data-testid="stSidebar"] .stMarkdown h2 {color:var(--navy);letter-spacing:.04em;}
    h1 {font-size:2rem;color:var(--navy);margin-bottom:.45rem;font-weight:700;}
    h2 {font-size:1.3rem;color:var(--navy);margin-top:1.15rem;}
    h3 {font-size:1.08rem;color:var(--navy);}
    p, label, .stMarkdown {color:var(--text);}
    .takeaway {background:#EAF3F2;border-left:4px solid var(--accent);padding:11px 14px;
      border-radius:4px;margin:0 0 14px 0;font-size:14px;line-height:1.45;color:var(--navy);}
    .section-label {font-size:11px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:700;margin-top:12px;}
    [data-testid="stMetric"] {border:1px solid var(--line);border-top:3px solid var(--accent);
      border-radius:7px;padding:12px 13px;background:#FFFFFF;min-height:108px;box-shadow:0 1px 2px rgba(23,50,77,.03);}
    [data-testid="stMetricLabel"],[data-testid="stMetricLabel"] * {color:var(--muted)!important;font-size:12px;}
    [data-testid="stMetricValue"],[data-testid="stMetricValue"] * {color:var(--navy)!important;}
    [data-testid="stMetricValue"] {font-size:1.4rem;}
    [data-testid="stMetricDelta"] {font-size:11px;}
    .status-tile {border:1px solid var(--line);border-top:5px solid;border-radius:7px;
      padding:13px;min-height:242px;background:#FFFFFF;color:var(--text);}
    .tile-area {font-size:11px;font-weight:700;letter-spacing:.06em;color:var(--muted);}
    .status-pill {display:inline-block;margin:8px 0;padding:3px 8px;border-radius:11px;color:white;font-size:10px;font-weight:700;}
    .tile-metric {font-size:12px;color:var(--muted);}.tile-value {font-size:20px;font-weight:700;margin:4px 0 8px 0;color:var(--navy);}
    .tile-detail {font-size:11px;min-height:52px;line-height:1.4;}.tile-next {font-size:11px;margin-top:8px;line-height:1.4;}
    .tile-owner {font-size:10px;color:var(--muted);margin-top:6px;}
    .stAlert {border-radius:6px;}.stButton button,.stDownloadButton button {border-radius:5px;}
    .stButton button[kind="primary"],.stDownloadButton button[kind="primary"] {background:var(--accent);border-color:var(--accent);}
    [data-testid="stDataFrame"] {border:1px solid var(--line);border-radius:5px;}
    [data-testid="stExpander"] {background:#FFFFFF;border:1px solid var(--line);border-radius:6px;margin-bottom:8px;}
    .js-plotly-plot {border:1px solid var(--line);border-radius:6px;background:#FFFFFF;}
    #MainMenu {visibility:hidden;} footer {visibility:hidden;}
    </style>""",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_base():
    config = load_config()
    required = [
        "daily_sales", "monthly_forecast", "production_daily", "pulp_inventory_daily",
        "pulp_inbound", "assumptions", "depot_flow_daily", "writeoff_reconciliation",
    ]
    datasets = apply_missing_feed_fallbacks(load_datasets(required=required))
    return config, datasets


def _detector_params(parameter_key: tuple) -> dict[str, float | int]:
    baseline, amber_multiplier, amber_days, red_multiplier, red_days, min_history = parameter_key
    return {
        "baseline_window": int(baseline), "amber_multiplier": float(amber_multiplier),
        "amber_days": int(amber_days), "red_multiplier": float(red_multiplier),
        "red_days": int(red_days), "min_history": int(min_history),
    }


@st.cache_data(show_spinner=False)
def get_scenario_base(scenario_key: tuple = DEFAULT_SCENARIO):
    config, datasets = load_base()
    initial, notice, root_profile, capture, closure_probability, qc_share = scenario_key
    config = scenario_config(config, float(initial), str(notice), str(root_profile), float(capture), float(closure_probability), float(qc_share))
    data_changed = (
        scenario_key[0] != DEFAULT_SCENARIO[0]
        or scenario_key[1] != DEFAULT_SCENARIO[1]
        or scenario_key[5] != DEFAULT_SCENARIO[5]
    )
    if data_changed:
        datasets = apply_missing_feed_fallbacks(SyntheticDataGenerator(config).generate())
        datasets["reconciliation_checks"] = reconcile(datasets, config)
    return config, datasets


@st.cache_data(show_spinner=False)
def get_analysis(parameter_key: tuple, scenario_key: tuple = DEFAULT_SCENARIO):
    config, datasets = get_scenario_base(scenario_key)
    return build_analysis(config, datasets, _detector_params(parameter_key))


@st.cache_data(show_spinner=False)
def get_ramp_sensitivity(parameter_key: tuple, scenario_key: tuple = DEFAULT_SCENARIO) -> pd.DataFrame:
    config, _ = get_scenario_base(scenario_key)
    return ramp_lead_sensitivity(config, _detector_params(parameter_key))


@st.cache_data(show_spinner=False)
def get_excel_export(
    parameter_key: tuple,
    risks: pd.DataFrame,
    approval_log: pd.DataFrame,
    scenario_key: tuple = DEFAULT_SCENARIO,
    mode: str = "Last summer replay",
) -> bytes:
    config, datasets = get_scenario_base(scenario_key)
    analysis = get_analysis(parameter_key, scenario_key)
    tables: dict[str, pd.DataFrame] = {}
    case_facts = pd.DataFrame({"case_fact": list(config.case), "value": list(config.case.values())})
    case_facts["source"] = case_facts["case_fact"].map(lambda key: "DERIVED FROM CASE" if key == "annual_bottles" else "CASE-STATED")
    case_facts["VERIFIED_AGAINST_CASE_TEXT"] = "N"
    tables["CASE_FACTS"] = case_facts
    for name, frame in config.tables.items():
        tables[f"CONFIG_{name}"] = frame
    for name, frame in datasets.items():
        tables[f"DATA_{name}"] = frame
    for name in [
        "corrected", "signal", "alerts", "forecast_by_flavor", "reforecast", "launch_gate",
        "exposure", "closure_scenarios", "buffer_table", "supply_options", "bottle_scenarios",
        "pulp_scenarios", "capacity_plan", "allocation", "allocation_detail", "attribution",
        "causal_edges", "replay_daily", "replay_actions", "cover", "transfers", "tiles",
        "budget", "budget_impact", "quality_checks", "attribution_checks", "replay_checks", "budget_checks",
        "avoided_range", "depot_mismatch", "writeoff_reconciliation",
    ]:
        tables[f"MODEL_{name}"] = analysis[name]
    for name in ["forecast_metrics", "censoring_metrics", "passion_profile", "best_buffer", "air_only", "avoided", "budget_summary"]:
        tables[f"MODEL_{name}"] = pd.DataFrame([analysis[name]])
    tables["MODEL_ramp_sensitivity"] = get_ramp_sensitivity(parameter_key, scenario_key)
    tables["WORKFLOW_risk_register"] = risks
    tables["WORKFLOW_approval_log"] = approval_log
    tables["WORKFLOW_scenario"] = pd.DataFrame([{
        "mode": mode, "initial_dp_qc_multiplier": scenario_key[0], "planner_notice": scenario_key[1],
        "root_cause_profile": scenario_key[2], "capture_multiplier": scenario_key[3],
        "closure_probability": scenario_key[4], "qc_share": scenario_key[5],
        "execution_status": "NOT_EXECUTED_HUMAN_DECISION_ONLY",
    }])
    return excel_export_bytes(tables)


def main() -> None:
    try:
        config, _ = load_base()
    except FileNotFoundError as error:
        st.error(f"{error}\n\nRun `python generate_data.py` first, then restart the app.")
        st.stop()

    st.sidebar.markdown("## PULP RIOT")
    st.sidebar.caption("Dragon Passion | TransfiNITTe 2026")
    section = st.sidebar.selectbox("Section", list(NAV_GROUPS))
    page = st.sidebar.radio("Page", NAV_GROUPS[section])
    brand, toggle = st.columns([1.4, 1.0])
    brand.markdown("### 🐉 Dragon Passion Control Tower")
    brand.caption("Light planning prototype · human decisions only")
    mode = toggle.radio("View", ["Last summer replay", "Next summer plan"], horizontal=True, label_visibility="collapsed", key="view_mode")

    with st.sidebar.expander("Demand detector parameters", expanded=page == "Demand"):
        baseline = st.number_input("Rolling baseline (days)", 7, 28, int(config.case["baseline_window_days"]), 1)
        amber_multiplier = st.number_input("Amber multiplier", 1.1, 4.0, float(config.case["amber_multiplier"]), 0.1)
        amber_days = st.number_input("Amber consecutive days", 1, 5, int(config.case["amber_consecutive_days"]), 1)
        red_multiplier = st.number_input("Red multiplier", 1.2, 5.0, float(config.case["red_multiplier"]), 0.1)
        red_days = st.number_input("Red consecutive days", 1, 5, int(config.case["red_consecutive_days"]), 1)
        min_history = st.number_input("Minimum active history (days)", 3, 14, int(config.number("A039")), 1)
    if red_multiplier <= amber_multiplier:
        st.sidebar.error("Red multiplier must be greater than Amber multiplier.")
        st.stop()
    parameter_key = (baseline, amber_multiplier, amber_days, red_multiplier, red_days, min_history)

    default_scenario = (
        float(config.number("A042")), str(config.assumption("A007")), "BASE", 1.0,
        float(config.case["passion_closure_probability"]),
        float(config.tables["channels"].set_index("channel_id").loc["QC", "summer_share"]),
    )

    def reset_scenario() -> None:
        for key, value in zip(
            ["scenario_initial", "scenario_notice", "scenario_root", "scenario_capture", "scenario_closure", "scenario_qc"],
            default_scenario,
        ):
            st.session_state[key] = pd.Timestamp(value).date() if key == "scenario_notice" else value

    with st.sidebar.expander("Scenario & one-click sensitivity", expanded=page in {"Demand", "Supply", "Assumptions & Sensitivity"}):
        initial = st.number_input("Initial DP QC ramp (×)", 1.0, float(config.case["viral_qc_multiplier"]), default_scenario[0], 0.5, key="scenario_initial")
        notice = st.date_input("Planner notice date", value=pd.Timestamp(default_scenario[1]).date(), key="scenario_notice")
        root_profile = st.selectbox("Root-cause split", ["BASE", "EQUAL", "LATE_SENSING_HEAVY", "ROUTE_HEAVY"], key="scenario_root")
        capture = st.slider("Capture-rate multiplier", 0.0, 1.5, default_scenario[3], 0.05, key="scenario_capture")
        closure_probability = st.slider("Annual closure probability", 0.0, 1.0, default_scenario[4], 0.05, key="scenario_closure")
        qc_share = st.slider("QC summer volume share", 0.05, 0.40, default_scenario[5], 0.05, key="scenario_qc")
        st.button("Reset scenario inputs", on_click=reset_scenario, width="stretch")
        st.caption("Assumption scenarios only. Capture rates cap at 100%. Nothing executes.")
    scenario_key = (float(initial), str(notice), str(root_profile), float(capture), float(closure_probability), float(qc_share))

    with st.spinner("Running reconciled demand and supply analytics…"):
        analysis = get_analysis(parameter_key, scenario_key)
    config, _ = get_scenario_base(scenario_key)
    if analysis["feed_degraded"]:
        st.warning(f"Degraded data mode: scenario uncertainty is ±{analysis['scenario_uncertainty_pct']:.0f}%. Missing QC disables detection; unknown depot stock cannot originate transfers.")
    if st.session_state.get("risk_scenario_key") != scenario_key:
        st.session_state.risk_register = analysis["risks"].copy()
        st.session_state.risk_scenario_key = scenario_key
    risks = st.session_state.get("risk_register", analysis["risks"])
    approval_log = st.session_state.get("approval_log", empty_approval_log())

    with st.sidebar.expander("Excel export", expanded=False):
        st.caption("Raw data, config, model tables, sensitivity, checks, risks and approval log for the active scenario.")
        with st.spinner("Preparing workbook…"):
            workbook = get_excel_export(parameter_key, risks, approval_log, scenario_key, mode)
        st.download_button("Download all tables (.xlsx)", data=workbook, file_name="pulp_riot_dragon_passion_control_tower.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
        with open("data/assumptions.xlsx", "rb") as handle:
            st.download_button("Download baseline assumptions", data=handle.read(), file_name="pulp_riot_assumptions.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    st.sidebar.caption("Fixed seed 42 · Local CSVs · No external APIs · COO for peak trade-offs")

    if page == "Control Tower":
        render_control_tower(config, _, analysis, mode)
    elif page == "What Went Wrong":
        render_what_went_wrong(config, _, analysis)
    elif page == "Demand":
        render_demand(config, _, analysis)
    elif page == "Supply":
        render_supply(config, _, analysis)
    elif page == "Causal Link Map":
        render_links(config, _, analysis)
    elif page == "Recommendations":
        render_recommendations(config, _, analysis)
    elif page == "Scenario Replay":
        render_replay(config, _, analysis, mode)
    elif page == "Budget & Impact":
        render_budget(config, _, analysis)
    elif page == "Assumptions & Sensitivity":
        with st.spinner("Recomputing initial-ramp detection sensitivity…"):
            ramp = get_ramp_sensitivity(parameter_key, scenario_key)
        render_assumptions_sensitivity(config, _, analysis, ramp, scenario_key)
    else:
        render_architecture(config, _, analysis)

    st.caption("Synthetic case prototype | CASE-STATED / DERIVED FROM CASE / MY ASSUMPTION lineage | Approval records decisions only; nothing is executed.")


if __name__ == "__main__":
    main()
