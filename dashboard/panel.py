"""Right-side region info panel.

Given a list of acronyms (from chat or click), render one row per region
with: acronym, region_name, log2_fold_change, p_value, n_A_eff, n_B_eff.
NaN cells render as '—'.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import domain

PANEL_COLUMNS = [
    "acronym",
    "region_name",
    "log2_fold_change",
    "p_value",
    "n_A_eff",
    "n_B_eff",
]

EMPTY_HINT = "Ask the chat a question about brain regions to populate this panel."


def render_panel(selected_acronyms: list[str]) -> None:
    """Write the region table to the current Streamlit container."""
    if not selected_acronyms:
        st.info(EMPTY_HINT)
        return

    effects = domain.resolve_effects(selected_acronyms)
    rows = domain.effects_to_panel_frame(effects)
    if rows.empty:
        st.warning("No matching atlas regions for the acronyms returned.")
        return

    # NaN → em-dash for display only; types become object/str.
    rows = rows.where(pd.notna(rows), "—")

    st.subheader(f"{len(rows)} region(s) selected")
    st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
        column_config={
            "acronym": st.column_config.TextColumn("Acronym", width="small"),
            "region_name": st.column_config.TextColumn("Region"),
            "log2_fold_change": st.column_config.NumberColumn(
                "log2 FC", format="%.2f", help="G002 − G001, base-2"
            ),
            "p_value": st.column_config.NumberColumn(
                "p (uncorrected)", format="%.3g"
            ),
            "n_A_eff": st.column_config.NumberColumn("n G002", format="%d"),
            "n_B_eff": st.column_config.NumberColumn("n G001", format="%d"),
            "in_labelmap": st.column_config.CheckboxColumn(
                "In 3D mask",
                help="False = stats exist but this region has no voxel label in the atlas volume",
            ),
        },
    )
