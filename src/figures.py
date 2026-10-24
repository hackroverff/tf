"""Screenshot-ready Plotly figures used by multiple pages."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .ui import ACCENT, FLAVOR_COLORS, NAVY, STATUS_COLORS, style_figure


def demand_alert_figure(
    alerts: pd.DataFrame,
    planner_notice: pd.Timestamp,
    events: pd.DataFrame | None = None,
) -> go.Figure:
    alert_dates = pd.to_datetime(alerts["date"])
    dp = alerts[(alerts["flavor_id"] == "DP") & (alert_dates.dt.month >= 3)].copy()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dp["date"], y=dp["signal_bottles"], name="Daily QC corrected signal", mode="lines", line={"color": ACCENT, "width": 2.5}))
    fig.add_trace(go.Scatter(x=dp["date"], y=dp["rolling_baseline"], name="14-day trailing baseline", mode="lines", line={"color": "#68788A", "dash": "dash"}))
    for status, color in [("AMBER", STATUS_COLORS["AMBER"]), ("RED", STATUS_COLORS["RED"])]:
        points = dp[dp["alert_status"] == status]
        fig.add_trace(go.Scatter(x=points["date"], y=points["signal_bottles"], name=status, mode="markers", marker={"color": color, "size": 7}))
        if not points.empty:
            first = points.iloc[0]
            fig.add_annotation(
                x=first["date"], y=first["signal_bottles"], text=f"First {status.title()}",
                showarrow=True, arrowhead=2, ay=-36 if status == "AMBER" else 36,
                font={"color": color, "size": 11}, bgcolor="rgba(255,255,255,.9)",
            )
    if events is not None and not events.empty:
        wanted = ["LAUNCH", "VIRAL", "NOTICE", "CLOSURE"]
        labels = {"LAUNCH": "DP launch", "VIRAL": "Viral reel", "NOTICE": "Planner notice", "CLOSURE": "Highway closure"}
        colors = {"LAUNCH": NAVY, "VIRAL": ACCENT, "NOTICE": STATUS_COLORS["AMBER"], "CLOSURE": STATUS_COLORS["RED"]}
        for event in events[events["event_type"].isin(wanted)].itertuples():
            fig.add_vline(
                x=pd.Timestamp(event.event_date), line_dash="dot", line_color=colors[event.event_type],
                annotation_text=labels[event.event_type], annotation_position="top left",
                annotation_font={"size": 10, "color": colors[event.event_type]},
            )
    else:
        fig.add_vline(x=planner_notice, line_dash="dot", line_color=STATUS_COLORS["AMBER"], annotation_text="Planner notice", annotation_position="top left")
    fig.update_yaxes(title="DP QC bottles/day")
    fig.update_xaxes(title="")
    return style_figure(fig, 460, "Reaction timeline | signal, alerts and operating events")


def scenario_figure(bottles: pd.DataFrame) -> go.Figure:
    first_week = bottles["week_start"].min()
    data = bottles[bottles["week_start"] == first_week].groupby(["scenario", "flavor_id"], as_index=False)["scenario_bottles"].sum()
    fig = px.bar(data, x="scenario", y="scenario_bottles", color="flavor_id", barmode="group",
                 color_discrete_map=FLAVOR_COLORS, labels={"scenario_bottles": "Bottles/week", "scenario": "", "flavor_id": "Flavor"})
    return style_figure(fig, 410, f"Bottle scenarios — week of {first_week.date()}")


def reforecast_figure(reforecast: pd.DataFrame) -> go.Figure:
    dp = reforecast[reforecast["flavor_id"] == "DP"].groupby("week_start", as_index=False).agg(
        forecast=("reforecast_next_week_bottles", "sum"), actual=("actual_next_week_bottles", "sum")
    )
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dp["week_start"], y=dp["forecast"], name="Next-week reforecast", mode="lines+markers", line={"color": ACCENT}))
    fig.add_trace(go.Scatter(x=dp["week_start"], y=dp["actual"], name="Corrected demand (back-test)", mode="lines+markers", line={"color": "#2E7D5B"}))
    fig.update_yaxes(title="DP bottles/week")
    return style_figure(fig, 400, "Weekly reaction | rolling reforecast (synthetic back-test)")


def closure_figure(scenarios: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=scenarios["closure_weeks"].astype(str) + " weeks", y=scenarios["lost_contribution_cr"], name="Conditional loss", marker_color="#D99422"))
    fig.add_trace(go.Bar(x=scenarios["closure_weeks"].astype(str) + " weeks", y=scenarios["expected_contribution_loss_cr"], name="Expected contribution loss", marker_color=ACCENT))
    fig.add_trace(go.Bar(x=scenarios["closure_weeks"].astype(str) + " weeks", y=scenarios["expected_air_premium_cr"], name="Expected air premium", marker_color=STATUS_COLORS["AMBER"]))
    fig.update_yaxes(title="₹ cr/year")
    return style_figure(fig, 400, "1/2/3-week closures | conditional loss and expected cost")


def buffer_figure(table: pd.DataFrame, best: dict) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=table["buffer_weeks"], y=table["expected_total_cost_cr"], name="Carry + expected loss + air premium", mode="lines+markers", line={"color": ACCENT, "width": 3}))
    fig.add_trace(go.Scatter(x=table["buffer_weeks"], y=table["expected_stockout_loss_cr"], name="Expected stock-out loss", mode="lines+markers", line={"color": STATUS_COLORS["RED"]}))
    fig.add_trace(go.Scatter(x=table["buffer_weeks"], y=table["expected_air_premium_cr"], name="Expected air premium", mode="lines+markers", line={"color": STATUS_COLORS["AMBER"]}))
    fig.add_trace(go.Scatter(x=table["buffer_weeks"], y=table["annual_carry_and_storage_cr"], name="Annual carry + storage", mode="lines+markers", line={"color": NAVY}))
    fig.add_vline(
        x=float(best["buffer_weeks"]), line_dash="dot", line_color=NAVY,
        annotation_text=f"Recommended +{best['buffer_weeks']:.0f}w | break-even p={best.get('break_even_closure_probability', float('nan')):.1%}",
    )
    fig.update_xaxes(title="Additional frozen buffer (weeks)", dtick=1)
    fig.update_yaxes(title="₹ cr/year")
    return style_figure(fig, 430, "0–4 week buffer optimisation | air premium included")


def capacity_figure(plan: pd.DataFrame) -> go.Figure:
    data = plan[plan["scenario"].isin(["BASE", "VIRAL_4X"])].copy()
    fig = go.Figure()
    for scenario, color in [("BASE", ACCENT), ("VIRAL_4X", STATUS_COLORS["RED"])]:
        subset = data[data["scenario"] == scenario]
        fig.add_trace(go.Scatter(x=subset["week_start"], y=subset["scenario_bottles"], name=f"{scenario} demand", mode="lines", line={"color": color}))
    viral = data[data["scenario"] == "VIRAL_4X"]
    feasible_column = "pulp_feasible_bottles" if "pulp_feasible_bottles" in viral else "max_feasible_bottles"
    fig.add_trace(go.Scatter(x=viral["week_start"], y=viral[feasible_column], name="4× joint bottle + pulp feasible", mode="lines+markers", line={"color": NAVY, "dash": "dash"}))
    if "copacker_used_bottles" in viral:
        fig.add_trace(go.Bar(x=viral["week_start"], y=viral["copacker_used_bottles"], name="Pulp-feasible co-packer output", marker_color="#7D9C9D", opacity=0.65))
    fig.update_yaxes(title="Bottles/week")
    return style_figure(fig, 430, "Constrained weekly plan | co-packer limited by notice and pulp")


def causal_map_figure(edges: pd.DataFrame) -> go.Figure:
    positions = {
        "Viral reel": (0, 3), "DP QC demand": (1.4, 3), "Daily Amber/Red alert": (3, 3.6),
        "Passionfruit requirement": (3, 2.5), "Usable pulp cover": (4.7, 2.5),
        "Launch handoff": (0, 1), "Imported dragonfruit readiness": (3, 1),
        "Highway closure": (3.7, 0), "Passionfruit shortage": (5, 1.1),
        "Passionfruit Punch cut": (6.4, 1.6), "Lost sales": (8, 1.6),
        "Stock-outs": (6.3, 2.8), "Censored demand signal": (8, 2.8),
        "Rival shelf-space threat": (8, 3.8), "Emergency air freight": (5.8, -0.2),
    }
    fig = go.Figure()
    for edge in edges.itertuples():
        if edge.source not in positions or edge.target not in positions:
            continue
        x0, y0 = positions[edge.source]
        x1, y1 = positions[edge.target]
        color = ACCENT if edge.edge_type.startswith("DEMAND") else STATUS_COLORS["RED"]
        fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=3, arrowsize=1.4, arrowwidth=1.5, arrowcolor=color, text="")
        fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2 + 0.10, text=edge.display,
                           showarrow=False, font={"size": 9, "color": color}, bgcolor="rgba(255,255,255,.88)", borderpad=2)
    for node, (x, y) in positions.items():
        fill = "#EAF1FB" if x < 3.2 else ("#FFF1E8" if x < 6 else "#F2F4F7")
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=[node], textposition="bottom center",
                                 marker={"size": 20, "color": fill, "line": {"color": "#516173", "width": 1.2}},
                                 textfont={"size": 10, "color": "#223042"}, hoverinfo="text", showlegend=False))
    fig.update_xaxes(visible=False, range=[-0.7, 8.8])
    fig.update_yaxes(visible=False, range=[-0.8, 4.4])
    fig.update_layout(hovermode="closest")
    return style_figure(fig, 650, "Two-way causal link map — edge labels carry their own units")


def attribution_waterfall(attribution: pd.DataFrame) -> go.Figure:
    labels = attribution["root_cause"].tolist() + ["Total economic impact"]
    values = attribution["economic_impact_cr"].tolist()
    fig = go.Figure(go.Waterfall(
        x=labels, y=values + [sum(values)], measure=["relative"] * len(values) + ["total"],
        text=[f"₹{v:.2f}" for v in values] + [f"₹{sum(values):.2f}"], textposition="outside",
        connector={"line": {"color": "#98A2B3"}}, increasing={"marker": {"color": "#C43D3D"}},
        totals={"marker": {"color": "#17324D"}},
    ))
    fig.update_yaxes(title="₹ cr (contribution + air + write-offs)")
    fig.update_xaxes(tickangle=-15)
    return style_figure(fig, 440, "Loss attribution — no revenue/contribution double count")


def impact_figure(impact: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=impact["scenario"], y=impact["expected_next_summer_benefit_cr"], name="Expected benefit", marker_color="#2E7D5B",
                         text=impact["expected_next_summer_benefit_cr"].map(lambda v: f"₹{v:.2f}"), textposition="outside"))
    fig.add_trace(go.Bar(x=impact["scenario"], y=impact["selected_first_year_cost_cr"], name="First-year cost", marker_color=NAVY,
                         text=impact["selected_first_year_cost_cr"].map(lambda v: f"₹{v:.2f}"), textposition="outside"))
    fig.update_yaxes(title="₹ cr")
    return style_figure(fig, 390, "Next-summer benefit vs selected first-year cost")


def replay_cover_figure(daily: pd.DataFrame, selected: pd.Timestamp, closure_start: pd.Timestamp) -> go.Figure:
    data = daily[daily["date"] <= selected]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=data["date"], y=data["actual_production_cover_weeks"], name="Actual production-run-rate cover", mode="lines", line={"color": "#C43D3D"}))
    fig.add_trace(go.Scatter(x=data["date"], y=data["actual_old_mix_cover_weeks"], name="Actual old-mix cover", mode="lines", line={"color": "#68788A", "dash": "dash"}))
    fig.add_trace(go.Scatter(x=data["date"], y=data["model_static_buffer_cover_weeks"], name="Model static buffer stress-test", mode="lines", line={"color": ACCENT}))
    fig.add_vline(x=closure_start, line_dash="dot", line_color="#223042", annotation_text="Closure")
    fig.update_yaxes(title="Passionfruit cover (weeks)")
    return style_figure(fig, 410, "Replay cover view — buffer line is a static stress-test, not resimulation")


def depot_cover_heatmap(cover: pd.DataFrame, max_days: float = 42.0) -> go.Figure:
    """Latest depot × flavor cover with low/high values shown in days."""
    if cover.empty:
        fig = go.Figure()
        fig.add_annotation(text="Depot stock unavailable", showarrow=False)
        return style_figure(fig, 390, "Depot × flavor cover | unavailable")
    data = cover.copy()
    data["cover_display"] = data["cover_days_current_demand"].replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(0, max_days)
    pivot = data.pivot(index="flavor_id", columns="depot_id", values="cover_display")
    text = pivot.map(lambda value: f"{value:.0f}d")
    fig = go.Figure(go.Heatmap(
        z=pivot.to_numpy(), x=pivot.columns.tolist(), y=pivot.index.tolist(),
        text=text.to_numpy(), texttemplate="%{text}", hovertemplate="%{y} / %{x}: %{z:.1f} days<extra></extra>",
        zmin=0, zmax=max_days,
        colorscale=[[0.0, STATUS_COLORS["RED"]], [0.33, "#E8C77D"], [0.67, "#82B4B2"], [1.0, ACCENT]],
        colorbar={"title": "Days cover"},
    ))
    fig.update_xaxes(title="Depot")
    fig.update_yaxes(title="Flavor")
    return style_figure(fig, 410, "Depot × flavor mismatch | current-demand days of cover")


def ramp_lead_figure(ramp: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ramp["initial_dp_qc_multiplier"], y=ramp["amber_reaction_lead_days"],
        name="First Amber reaction lead", mode="lines+markers+text",
        text=ramp["amber_reaction_lead_days"].map(lambda value: "" if pd.isna(value) else f"{value:.0f}d"),
        textposition="top center", line={"color": ACCENT, "width": 3}, marker={"size": 9},
        customdata=pd.to_datetime(ramp["first_amber"]).dt.strftime("%Y-%m-%d"),
        hovertemplate="Initial %{x:.1f}×<br>Amber %{customdata}<br>Lead %{y:.0f}d<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=ramp["initial_dp_qc_multiplier"], y=ramp["red_confirmation_lead_days"],
        name="Red confirmation lead", mode="lines+markers", line={"color": STATUS_COLORS["RED"], "width": 2, "dash": "dash"},
        customdata=pd.to_datetime(ramp["first_red"]).dt.strftime("%Y-%m-%d"),
        hovertemplate="Initial %{x:.1f}×<br>Red %{customdata}<br>Lead %{y:.0f}d<extra></extra>", connectgaps=False,
    ))
    fig.update_xaxes(title="Initial DP QC viral multiplier (×)", dtick=0.5)
    fig.update_yaxes(title="Days before 31 March planner notice", rangemode="tozero")
    return style_figure(fig, 420, "Reaction lead vs initial ramp | no Red shown when not triggered")


def avoided_range_figure(range_table: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=range_table["scenario"], y=range_table["avoided_loss_cr"],
        marker_color=["#8B98A5", ACCENT, NAVY],
        text=[f"₹{value:.2f} cr<br>{rate:.1%} capture" for value, rate in zip(range_table["avoided_loss_cr"], range_table["effective_capture_rate"])],
        textposition="outside",
        customdata=range_table["capture_rate_inputs"],
        hovertemplate="%{x}<br>%{customdata}<extra></extra>",
    ))
    fig.update_yaxes(title="Avoided economic loss (₹ cr)")
    fig.update_xaxes(title="")
    fig.update_layout(showlegend=False)
    return style_figure(fig, 400, "LOW / BASE / HIGH | assumption-based, not simulated")
