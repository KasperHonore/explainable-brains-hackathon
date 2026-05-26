"""Streamlit entry: 'Google Earth for Brain Activity' — Challenge B dashboard.

MVP-1 milestone: walking skeleton. Renders the Allen mouse anatomy NIfTI in a
niivue WebGL canvas inside Streamlit. No overlays, chat, or panels yet.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from dashboard.niivue import VolumeLayer, render_brain_view

DATA_DIR = Path(__file__).resolve().parent / "data"
ANATOMY = DATA_DIR / "brain_atlas_anatomy.nii.gz"


def main() -> None:
    st.set_page_config(page_title="Brain Earth", layout="wide")
    st.title("Brain Earth — Challenge B")
    st.caption("MVP-1: walking skeleton. Drag to rotate.")

    if not ANATOMY.exists():
        st.error(
            f"Anatomy volume not found at {ANATOMY}. "
            "Run the bucket download (see bucket_access/bucket_utils.py)."
        )
        return

    render_brain_view([VolumeLayer(path=ANATOMY, colormap="gray", opacity=1.0)])


if __name__ == "__main__":
    main()
