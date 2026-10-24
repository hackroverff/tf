"""Shared light-consulting Streamlit and Plotly presentation helpers."""
from __future__ import annotations

import html
import warnings

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st


ACCENT = "#0F6B6D"
NAVY = "#17324D"
TEXT = "#223042"
MUTED = "#617182"
GRID = "#E4EBEE"
STATUS_COLORS = {
    "RED": "#C43D3D", "AMBER": "#D99422", "GREEN": "#2E7D5B", "NORMAL": "#2E7D5B",
    "PASS": "#2E7D5B", "BLOCKED": "#C43D3D", "READY": "#2E7D5B",
}
FLAVOR_COLORS = {
    "MPB": "#0F6B6D", "GC": "#4D8586", "PP": "#7D9C9D",
    "DP": "#17324D", "DB": "#8B98A5",
}
CHANNEL_COLORS = {"GT": "#17324D", "MT": "#0F6B6D", "QC": "#6F8F94"}


def style_figure(fig: go.Figure, height: int = 420, title: str | None = None) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        title={"text": title, "x": 0.01, "xanchor": "left", "font": {"size": 16, "color": NAVY}} if title else None,
        font={"family": "Arial, sans-serif", "size": 12, "color": TEXT},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        margin={"l": 58, "r": 28, "t": 72 if title else 40, "b": 58},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, linecolor="#B8C4CA")
    fig.update_yaxes(gridcolor=GRID, zerolinecolor="#AAB4C0")
    return fig


@st.cache_data(show_spinner=False, max_entries=100)
def _cached_png(figure_json: str, height: int) -> bytes:
    figure = pio.from_json(figure_json)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return figure.to_image(format="png", width=1400, height=height, scale=1)


def chart_with_download(fig: go.Figure, key: str, file_name: str | None = None) -> None:
    """Render a key chart and offer a real PNG, with explicit failure fallback."""
    st.plotly_chart(fig, width="stretch", key=f"plotly_{key}")
    try:
        png = _cached_png(fig.to_json(), max(500, int(fig.layout.height or 700)))
        st.download_button(
            "Download chart (PNG)",
            data=png,
            file_name=file_name or f"{key}.png",
            mime="image/png",
            key=f"download_{key}",
            width="stretch",
        )
    except Exception as error:  # pragma: no cover - depends on local Kaleido runtime
        st.caption(f"PNG export is unavailable in this runtime: {error}. The interactive chart and Excel export remain available.")


def raw_table(frame: pd.DataFrame, height: int = 320) -> None:
    """Consistent bounded table with Arrow-safe display-only mixed columns."""
    display = frame.copy()
    for column in display.columns:
        if display[column].dtype != object:
            continue
        non_null = display[column].dropna()
        types = {type(value) for value in non_null.head(100)}
        if len(types) > 1:
            display[column] = display[column].map(
                lambda value: value.isoformat() if isinstance(value, (pd.Timestamp,)) else ("" if pd.isna(value) else str(value))
            )
    st.dataframe(display, width="stretch", hide_index=True, height=height)


def render_tile(tile) -> None:
    color = STATUS_COLORS.get(str(tile["status"]).upper(), MUTED)
    st.markdown(
        f"""<div class="status-tile" style="border-top-color:{color}">
        <div class="tile-area">{html.escape(str(tile['area']))}</div>
        <div class="status-pill" style="background:{color}">{html.escape(str(tile['status']))}</div>
        <div class="tile-metric">{html.escape(str(tile['metric']))}</div>
        <div class="tile-value">{html.escape(str(tile['value']))}</div>
        <div class="tile-detail">{html.escape(str(tile['detail']))}</div>
        <div class="tile-next"><b>Next:</b> {html.escape(str(tile['recommended_action']))}</div>
        <div class="tile-owner"><b>Owner:</b> {html.escape(str(tile['owner']))}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str, takeaway: str | None = None) -> None:
    st.title(title)
    st.markdown(
        f"<div class='takeaway'><b>Takeaway</b> — {html.escape(takeaway or subtitle)}</div>",
        unsafe_allow_html=True,
    )
    if takeaway:
        st.caption(subtitle)


def section_label(text: str) -> None:
    st.markdown(f"<div class='section-label'>{html.escape(text)}</div>", unsafe_allow_html=True)


def cr(value: float, decimals: int = 2) -> str:
    return f"₹{value:,.{decimals}f} cr"


def millions(value: float, decimals: int = 2) -> str:
    return f"{value / 1_000_000:,.{decimals}f} m"
