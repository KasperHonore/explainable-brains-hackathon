"""Streamlit entry: 'Google Earth for Brain Activity' — Challenge B dashboard.

MVP-5 milestone: chat → grounded acronym extraction → region info panel,
alongside the niivue volume + diff overlay from MVP-3.

Hackathon scope cuts (pre-authorized in the spec risk table):
- Chat-driven brain re-coloring (AC-3 partial fallback): the spatial view
  stays on the default diff map; selected regions surface in the side panel.
- Click-to-pick (AC-5): Streamlit's inline HTML components have no clean
  callback channel without a custom component. Deferred.
"""
from __future__ import annotations

import streamlit as st

from dashboard import data, llm
from dashboard.niivue import BrainViewMode, VolumeLayer, render_brain_view
from dashboard.panel import render_panel

NO_MATCH_HINT = (
    "I couldn't link your question to specific atlas regions — try mentioning "
    "a brain system like hypothalamus, cortex, or brainstem."
)


def _init_state() -> None:
    st.session_state.setdefault("selected_acronyms", [])
    st.session_state.setdefault("chat_text", "")
    st.session_state.setdefault("chat_status", "")


def _handle_query(query: str) -> None:
    """Call the LLM, update session state, never raise to the UI."""
    try:
        response = llm.answer(query)
    except llm.ChatUnavailable as exc:
        st.session_state.chat_status = f"chat unavailable — {exc}"
        st.session_state.chat_text = ""
        st.session_state.selected_acronyms = []
        return

    st.session_state.chat_text = response.text
    st.session_state.selected_acronyms = response.acronyms
    if response.acronyms:
        st.session_state.chat_status = (
            f"{len(response.acronyms)} region(s) named"
            + (f" · dropped {len(response.dropped)} non-atlas tokens" if response.dropped else "")
        )
    else:
        st.session_state.chat_status = NO_MATCH_HINT


def main() -> None:
    st.set_page_config(page_title="Brain Earth", layout="wide")
    _init_state()

    st.title("Brain Earth — c-Fos response to Semaglutide")
    col_view, col_panel = st.columns([2, 1], gap="medium")

    with col_view:
        view_mode = st.radio(
            "Brain view",
            options=[
                BrainViewMode.DIFFERENCE,
                BrainViewMode.COMPARE_GROUPS,
            ],
            format_func=lambda m: {
                BrainViewMode.DIFFERENCE: "Difference overlay (G002 − G001)",
                BrainViewMode.COMPARE_GROUPS: "Compare groups (side by side)",
            }[m],
            horizontal=True,
            label_visibility="collapsed",
        )
        if view_mode == BrainViewMode.DIFFERENCE:
            st.caption(
                "3D anatomy + c-Fos difference. Red = up in Semaglutide, blue = down. "
                "Use the Z slider on the right to cut through the volume."
            )
        else:
            st.caption(
                "Vehicle vs Semaglutide group median c-Fos maps in the same atlas space. "
                "Shared Z slider on the right."
            )

        try:
            data.ensure_static_volumes()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not prepare volumes: {exc}")
            return

        if view_mode == BrainViewMode.COMPARE_GROUPS:
            render_brain_view([], height=560, mode=BrainViewMode.COMPARE_GROUPS)
        else:
            # Threshold near-zero diff voxels to fully transparent — the diff
            # signal is dense (every brain voxel has some value), so without
            # a dead-zone the overlay drowns the anatomy. cal_min=1.0 hides
            # |log2FC| < 1; cal_max=3.0 saturates at p90 abs.
            layers = [
                VolumeLayer(static_name="anatomy.nii.gz", colormap="gray", opacity=1.0),
                VolumeLayer(
                    static_name="diff.nii.gz",
                    colormap="warm",
                    colormap_negative="winter",
                    opacity=0.7,
                    cal_min=1.0,
                    cal_max=3.0,
                ),
            ]
            render_brain_view(layers, height=560, mode=BrainViewMode.DIFFERENCE)

        query = st.chat_input("Ask about brain regions — e.g. 'regions involved in hunger and satiety'")
        if query:
            _handle_query(query)

        if st.session_state.chat_text:
            st.markdown(f"**Claude:** {st.session_state.chat_text}")
        if st.session_state.chat_status:
            st.caption(st.session_state.chat_status)

    with col_panel:
        st.subheader("Region detail")
        render_panel(st.session_state.selected_acronyms)


if __name__ == "__main__":
    main()
