"""Right-side region info panel + auto-highlighted top regions panel.

`render_panel` shows full stats for a list of acronyms (from chat or top-N click).
`render_top_regions_panel` shows the leaderboard of regions with the largest
|log2 fold change|, giving Goal 2 a chat-free path on cold start.
`render_region_spatial_panel` shows G001 vs G002 c-Fos signal side-by-side at
the selected region (orthogonal slices, cropped to bbox).
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
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

EMPTY_HINT = "Click a region in 'Top regions' above or ask the chat a question to populate this panel."

TOP_N_DEFAULT = 10
TOP_N_POOL = 50  # ranker pool size before n_eff filter
MIN_N_EFF = 3  # half-cohort minimum for stats meaningfulness


@st.cache_data(show_spinner=False)
def _top_regions_frame(n: int = TOP_N_DEFAULT) -> pd.DataFrame:
    """Pre-rank a pool and filter by minimum sample size, cached on the stats CSV."""
    pool = domain.top_regions(n=TOP_N_POOL, leaf_only=True, by="abs_log2fc")
    df = domain.effects_to_panel_frame(pool)
    df = df[(df["n_A_eff"] >= MIN_N_EFF) & (df["n_B_eff"] >= MIN_N_EFF)]
    return df.head(n).reset_index(drop=True)


def render_top_regions_panel() -> None:
    """Top-N leaderboard ranked by |log2FC|; click a row to inspect.

    Renders one row per region as a clickable button so the selection survives
    Streamlit reruns reliably (glide-data-grid's pointer-event interception
    makes st.dataframe row clicks fragile).
    """
    st.subheader("Top regions by effect size")
    rows = _top_regions_frame(TOP_N_DEFAULT)
    if rows.empty:
        st.warning("No regions meet the minimum sample size.")
        return

    st.caption(
        "Ranked by |log2 fold change| (Semaglutide vs Vehicle). "
        "Click a region to inspect it below."
    )

    # Header row
    hdr = st.columns([1.2, 3.2, 1.0, 1.0])
    hdr[0].markdown("**Acronym**")
    hdr[1].markdown("**Region**")
    hdr[2].markdown("**log2 FC**")
    hdr[3].markdown("**p**")

    for _, row in rows.iterrows():
        cols = st.columns([1.2, 3.2, 1.0, 1.0])
        acr = str(row["acronym"])
        is_selected = (
            st.session_state.selected_acronyms == [acr]
            if st.session_state.get("selected_acronyms")
            else False
        )
        button_type = "primary" if is_selected else "secondary"
        if cols[0].button(acr, key=f"top_{acr}", type=button_type):
            st.session_state.selected_acronyms = [acr]
            st.rerun()
        cols[1].write(str(row["region_name"]))
        log2fc = float(row["log2_fold_change"])
        cols[2].write(f"{log2fc:+.2f}")
        cols[3].write(f"{float(row['p_value']):.3g}")


# ---------------------------------------------------------------------------
# Region-spatial side-by-side panel
# ---------------------------------------------------------------------------


_AXIS_LABELS = ("Axial", "Coronal", "Sagittal")
_GROUP_LABELS = ("Vehicle (G001)", "Semaglutide (G002)")
_SIGNAL_FLOOR_FRACTION = 0.05  # threshold below which signal is hidden


def _orthogonal_slices(volume: np.ndarray, centroid: tuple[int, int, int]):
    """Return (axial, coronal, sagittal) 2D slices through the centroid."""
    z, y, x = centroid
    return (volume[z, :, :], volume[:, y, :], volume[:, :, x])


def render_region_spatial_panel(acronym: str) -> None:
    """G001 vs G002 c-Fos signal at the region, 2 rows × 3 columns."""
    st.subheader(f"Spatial — {acronym}")
    crop = domain.region_spatial_crop(acronym)
    if crop is None:
        st.caption("No spatial mask for this region in the atlas labelmap")
        return

    vmin, vmax = crop.signal_scale
    if vmax <= vmin:
        vmax = vmin + 1.0
    signal_floor = vmin + (vmax - vmin) * _SIGNAL_FLOOR_FRACTION
    anatomy_vmax = float(np.percentile(crop.anatomy, 99)) or 1.0

    fig, axes = plt.subplots(2, 3, figsize=(7.5, 5.2), facecolor="#0a0a0a")
    fig.suptitle(f"Spatial — {acronym}", color="white", fontsize=12)

    signals = (crop.signal_g001, crop.signal_g002)
    for row, (group_label, signal) in enumerate(zip(_GROUP_LABELS, signals)):
        anat_slices = _orthogonal_slices(crop.anatomy, crop.centroid)
        sig_slices = _orthogonal_slices(signal, crop.centroid)
        mask_slices = _orthogonal_slices(crop.mask.astype(np.float32), crop.centroid)
        for col in range(3):
            ax = axes[row, col]
            ax.imshow(
                anat_slices[col], cmap="gray", vmin=0.0, vmax=anatomy_vmax,
                origin="lower", interpolation="nearest",
            )
            masked_signal = np.ma.masked_where(
                sig_slices[col] < signal_floor, sig_slices[col]
            )
            ax.imshow(
                masked_signal, cmap="hot", alpha=0.65,
                vmin=vmin, vmax=vmax, origin="lower", interpolation="nearest",
            )
            try:
                ax.contour(
                    mask_slices[col], levels=[0.5], colors=["cyan"],
                    linewidths=0.6, origin="lower",
                )
            except ValueError:
                pass  # all-zero slice
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_color("#444")
            if row == 0:
                ax.set_title(_AXIS_LABELS[col], color="white", fontsize=9)
            if col == 0:
                ax.set_ylabel(group_label, color="white", fontsize=9)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    st.pyplot(fig, clear_figure=True, use_container_width=True)
    plt.close(fig)
    st.caption(
        f"Anatomy gray + c-Fos warm overlay, region outlined in cyan. "
        f"Slices at the region centroid; shared color scale (vmax={vmax:.2g})."
    )


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
