"""Classic 2D stats visualizations (volcano, top-bar, biology cards, per-mouse).

All panels share `st.session_state.selected_acronyms` with the 3D viewer tab,
so clicking a region in any plot updates the entire dashboard.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard import biology, data, domain

# Diverging palette: red = up in Semaglutide, blue = up in Vehicle, grey = ns.
COLOR_UP = "#C0392B"
COLOR_DOWN = "#1F4E79"
COLOR_NS = "#9aa0a6"
COLOR_RING = "#0F2A4A"  # navy ring for selected region

PLOTLY_BG = "rgba(0,0,0,0)"


# ---------------------------------------------------------------------------
# Data prep
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def volcano_frame() -> pd.DataFrame:
    """Cached frame for the volcano: one row per region with x/y/direction."""
    stats = data.get_statistics().copy()
    stats = stats.dropna(subset=["log2_fold_change", "p_value"])
    stats["neg_log10_p"] = -np.log10(stats["p_value"].clip(lower=1e-30))
    direction = np.where(
        stats["p_value"] >= 0.05, "ns",
        np.where(stats["log2_fold_change"] > 0, "up", "down"),
    )
    stats["direction"] = direction
    return stats.reset_index(drop=True)[
        ["acronym", "region_name", "log2_fold_change", "p_value",
         "neg_log10_p", "direction"]
    ]


def _selected_acronym() -> str | None:
    selected = st.session_state.get("selected_acronyms") or []
    return selected[0] if selected else None


def _select_acronym(acronym: str) -> None:
    """Write the selection and trigger a rerun so every panel updates."""
    st.session_state.selected_acronyms = [acronym]
    st.rerun()


def _consume_plotly_event(event, frame: pd.DataFrame, key_col: str = "acronym") -> None:
    """If Plotly returned a point selection, map index → acronym and select it."""
    if not event:
        return
    try:
        indices = event.selection.point_indices
    except AttributeError:
        return
    if not indices:
        return
    idx = int(indices[0])
    if 0 <= idx < len(frame):
        acronym = str(frame.iloc[idx][key_col])
        if acronym and (
            not st.session_state.get("selected_acronyms")
            or st.session_state.selected_acronyms[0] != acronym
        ):
            _select_acronym(acronym)


# ---------------------------------------------------------------------------
# Volcano
# ---------------------------------------------------------------------------


def render_volcano() -> None:
    df = volcano_frame()
    if df.empty:
        st.info("No statistics available for the volcano plot.")
        return

    color_map = {"up": COLOR_UP, "down": COLOR_DOWN, "ns": COLOR_NS}
    sel = _selected_acronym()

    fig = go.Figure()
    # One trace per direction so legend reads cleanly.
    for label, color in (
        ("up", COLOR_UP), ("down", COLOR_DOWN), ("ns", COLOR_NS),
    ):
        sub = df[df["direction"] == label]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["log2_fold_change"], y=sub["neg_log10_p"],
            mode="markers",
            name={"up": "↑ Semaglutide", "down": "↑ Vehicle", "ns": "ns"}[label],
            marker=dict(color=color, size=7, opacity=0.85,
                        line=dict(width=0)),
            text=sub["acronym"],
            customdata=sub[["region_name", "p_value"]].to_numpy(),
            hovertemplate=(
                "<b>%{text}</b><br>"
                "%{customdata[0]}<br>"
                "log2FC = %{x:+.2f}<br>"
                "p = %{customdata[1]:.3g}<extra></extra>"
            ),
        ))

    # Label top 8 by |log2FC| × -log10(p).
    df = df.assign(_rank=df["neg_log10_p"] * df["log2_fold_change"].abs())
    top = df.nlargest(8, "_rank")
    fig.add_trace(go.Scatter(
        x=top["log2_fold_change"], y=top["neg_log10_p"],
        mode="text", text=top["acronym"], textposition="top center",
        textfont=dict(size=10, color="#1F1F1F"),
        showlegend=False, hoverinfo="skip",
    ))

    # Selected ring (separate trace) so it stays on top.
    if sel:
        sel_row = df[df["acronym"] == sel]
        if not sel_row.empty:
            fig.add_trace(go.Scatter(
                x=sel_row["log2_fold_change"], y=sel_row["neg_log10_p"],
                mode="markers",
                marker=dict(size=16, color="rgba(0,0,0,0)",
                            line=dict(width=2.5, color=COLOR_RING)),
                name=f"Selected: {sel}", hoverinfo="skip",
            ))

    # Dashed p = 0.05 line.
    fig.add_hline(y=-np.log10(0.05), line_dash="dash",
                  line_color="#aaaaaa", annotation_text="p = 0.05",
                  annotation_position="top right")

    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="log2 fold change",
        yaxis_title="-log10(p)",
        plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        dragmode="zoom",
    )
    fig.update_xaxes(gridcolor="#EEF0F3", zerolinecolor="#cccccc")
    fig.update_yaxes(gridcolor="#EEF0F3")

    event = st.plotly_chart(
        fig, key="classic_volcano",
        on_select="rerun", selection_mode="points",
        use_container_width=True,
    )
    _consume_plotly_event(event, df)


# ---------------------------------------------------------------------------
# Top movers bar
# ---------------------------------------------------------------------------


def _top_bottom_frame(n: int = 10) -> pd.DataFrame:
    """Top n by log2FC (positive) and bottom n by log2FC, joined."""
    stats = data.get_statistics().copy()
    stats = stats[stats["is_lowest_level"] == True]  # noqa: E712
    stats = stats.dropna(subset=["log2_fold_change"])
    top = stats.nlargest(n, "log2_fold_change")
    bot = stats.nsmallest(n, "log2_fold_change")
    joined = pd.concat([top, bot], ignore_index=True)
    return joined[
        ["acronym", "region_name", "log2_fold_change", "p_value"]
    ].reset_index(drop=True)


def render_top_movers_bar() -> None:
    df = _top_bottom_frame(n=10)
    if df.empty:
        st.info("No regions available for the top-movers bar.")
        return

    # Sort so bars descend within each direction; positive at top, negative at bottom.
    df = df.sort_values("log2_fold_change", ascending=True).reset_index(drop=True)

    colors = np.where(df["log2_fold_change"] > 0, COLOR_UP, COLOR_DOWN)
    sel = _selected_acronym()
    line_colors = [COLOR_RING if a == sel else "rgba(0,0,0,0)"
                   for a in df["acronym"]]

    fig = go.Figure(go.Bar(
        y=df["acronym"], x=df["log2_fold_change"],
        orientation="h",
        marker=dict(color=colors,
                    line=dict(color=line_colors, width=2)),
        customdata=df[["region_name", "p_value"]].to_numpy(),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "%{customdata[0]}<br>"
            "log2FC = %{x:+.2f}<br>"
            "p = %{customdata[1]:.3g}<extra></extra>"
        ),
    ))
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="log2 fold change",
        yaxis_title="",
        plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
        showlegend=False,
    )
    fig.update_xaxes(gridcolor="#EEF0F3", zerolinecolor="#cccccc")

    event = st.plotly_chart(
        fig, key="classic_top_bar",
        on_select="rerun", selection_mode="points",
        use_container_width=True,
    )
    _consume_plotly_event(event, df)


# ---------------------------------------------------------------------------
# Biology insight cards
# ---------------------------------------------------------------------------


def _render_circuit_card(score: biology.CircuitScore, index: int) -> None:
    """One circuit's headline + score + member bar chart."""
    c = score.circuit
    arrow = "↑" if c.expected_direction == "up" else "↓"
    st.markdown(f"#### {c.headline}")
    st.caption(c.explanation)
    if score.n_total == 0:
        st.warning("No member regions found in the atlas.")
        return
    fraction = score.n_aligned / score.n_total if score.n_total else 0.0
    st.markdown(
        f"**{score.n_aligned}/{score.n_total}** regions move {arrow} "
        f"as expected"
    )
    st.progress(fraction)

    df = score.member_rows.head(8).copy()
    if df.empty:
        return
    # Expected direction draws the same colour as the volcano's `up` / `down`.
    expected_color = COLOR_UP if c.expected_direction == "up" else COLOR_DOWN
    misaligned_color = "#9aa0a6"
    bar_colors = [
        expected_color if aligned else misaligned_color
        for aligned in df["aligned"]
    ]
    sel = _selected_acronym()
    line_colors = [COLOR_RING if a == sel else "rgba(0,0,0,0)"
                   for a in df["acronym"]]

    fig = go.Figure(go.Bar(
        y=df["acronym"], x=df["log2_fold_change"],
        orientation="h",
        marker=dict(color=bar_colors,
                    line=dict(color=line_colors, width=2)),
        customdata=df[["region_name", "p_value", "aligned"]].to_numpy(),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "%{customdata[0]}<br>"
            "log2FC = %{x:+.2f}<br>"
            "p = %{customdata[1]:.3g}<br>"
            "aligned = %{customdata[2]}<extra></extra>"
        ),
    ))
    fig.update_layout(
        height=220,
        margin=dict(l=10, r=10, t=4, b=10),
        xaxis_title="log2 FC",
        plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
        showlegend=False,
    )
    fig.update_xaxes(gridcolor="#EEF0F3", zerolinecolor="#cccccc")

    event = st.plotly_chart(
        fig, key=f"classic_circuit_{c.key}_{index}",
        on_select="rerun", selection_mode="points",
        use_container_width=True,
    )
    _consume_plotly_event(event, df.reset_index(drop=True))


def render_biology_cards() -> None:
    stats = data.get_statistics()
    circuits = biology.get_circuits()
    cols = st.columns(len(circuits), gap="medium")
    for i, (col, circuit) in enumerate(zip(cols, circuits)):
        with col:
            _render_circuit_card(biology.score_circuit(circuit, stats), index=i)


# ---------------------------------------------------------------------------
# Per-mouse strip plot
# ---------------------------------------------------------------------------


def render_per_mouse_plot(acronym: str) -> None:
    densities = domain.densities_for_region(acronym)
    if not densities:
        st.caption(f"No per-animal density rows for `{acronym}`.")
        return

    df = pd.DataFrame([{
        "group": "Vehicle (G001)" if d.group == "G001" else "Semaglutide (G002)",
        "animal_nr": d.animal_nr,
        "scan_name": d.scan_name,
        "density": d.density if d.density is not None else float("nan"),
    } for d in densities])

    valid = df.dropna(subset=["density"])
    if valid.empty:
        st.caption(
            f"All density values for `{acronym}` are missing in this scan set."
        )
        return

    fig = go.Figure()
    for group_label, color in (
        ("Vehicle (G001)", COLOR_DOWN),
        ("Semaglutide (G002)", COLOR_UP),
    ):
        sub = df[df["group"] == group_label]
        if sub.empty:
            continue
        fig.add_trace(go.Box(
            y=sub["density"], x=[group_label] * len(sub),
            name=group_label,
            marker=dict(color=color, size=8, opacity=0.85),
            line=dict(color=color),
            boxpoints="all", boxmean=True, jitter=0.45, pointpos=0,
            customdata=sub[["animal_nr", "scan_name"]].to_numpy(),
            hovertemplate=(
                "<b>%{x}</b><br>"
                "animal = %{customdata[0]}<br>"
                "scan = %{customdata[1]}<br>"
                "density = %{y:.0f}<extra></extra>"
            ),
        ))

    fig.update_layout(
        height=380,
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis_title="density (cells / mm³)",
        plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
        showlegend=False,
    )
    fig.update_yaxes(gridcolor="#EEF0F3")
    st.plotly_chart(fig, key=f"classic_permouse_{acronym}",
                    use_container_width=True)


# ---------------------------------------------------------------------------
# Tab composition
# ---------------------------------------------------------------------------


def render_classic_tab() -> None:
    st.subheader("Effect vs significance + top movers")
    col_v, col_b = st.columns([3, 2], gap="medium")
    with col_v:
        st.markdown("**Volcano** — every region, click to inspect")
        render_volcano()
    with col_b:
        st.markdown("**Top 10 ↑ / ↓ by log2 fold change**")
        render_top_movers_bar()

    st.divider()
    st.subheader("Biology insight — circuits and their expected direction")
    render_biology_cards()

    st.divider()
    st.subheader("Per-animal density for the selected region")
    selected = _selected_acronym()
    if not selected:
        st.caption(
            "Click a region in the volcano, top-mover bar, or biology card "
            "above to see the per-animal density distribution here."
        )
        return
    render_per_mouse_plot(selected)
