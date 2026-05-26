"""Streamlit entry: 'Google Earth for Brain Activity' — Challenge B dashboard.

MVP-3 milestone: anatomy + G002-G001 diff overlay (divergent red/blue),
rendered in niivue. No chat or side panel yet — those land in MVP-4/5.
"""
from __future__ import annotations

import streamlit as st

from dashboard import data
from dashboard.niivue import VolumeLayer, render_brain_view


def main() -> None:
    st.set_page_config(page_title="Brain Earth", layout="wide")
    st.title("Brain Earth — Challenge B")
    st.caption(
        "Anatomy + Semaglutide (G002) − Vehicle (G001) c-Fos difference. "
        "Red = up in Semaglutide, blue = down. Drag to rotate."
    )

    try:
        anatomy_path = data.get_anatomy_path()
        diff_path = data.get_diff_map_path()
    except Exception as exc:  # noqa: BLE001 — show any data-fetch failure
        st.error(f"Could not load volumes: {exc}")
        return

    layers = [
        VolumeLayer(path=anatomy_path, colormap="gray", opacity=1.0),
        VolumeLayer(
            path=diff_path,
            colormap="warm",          # positive: red/orange
            colormap_negative="winter",  # negative: blue/cyan
            opacity=0.7,
        ),
    ]
    render_brain_view(layers, height=600)


if __name__ == "__main__":
    main()
