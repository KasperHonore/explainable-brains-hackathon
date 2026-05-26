"""Cached data loaders for the Challenge B dashboard.

CSVs are read directly from `/workspace/data/`. NIfTI volumes are downloaded
from the Hetzner bucket on first call and cached on disk + in-process.
All loaders are decorated with `@st.cache_data` / `@st.cache_resource` so
Streamlit reruns don't reread or re-download.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import SimpleITK as sitk
import streamlit as st

from bucket_access.bucket_utils import download_file

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
BUCKET_PREFIX_TAB = "challengeB/tabular_data_quantification"
BUCKET_PREFIX_NIFTI = "challengeB/spatial_brain_maps"

# Streamlit's static mount serves /app/static/<filename>. Streamlit's safe-join
# refuses symlinks, so the niivue iframe needs real files under static/. We
# copy from data/ on first run rather than duplicating downloads.
_STATIC_COPY_MAP = {
    "anatomy.nii.gz": "brain_atlas_anatomy.nii.gz",
    "diff.nii.gz": "cfos_group_median_difference_G002_vs_G001.nii.gz",
    "g001.nii.gz": "cfos_G001_median.nii.gz",
    "g002.nii.gz": "cfos_G002_median.nii.gz",
    "regions.nii.gz": "brain_atlas_regions.nii.gz",
}


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------


def _ensure_csv(name: str, bucket_subpath: str) -> Path:
    local = DATA_DIR / name
    if not local.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        download_file(f"{bucket_subpath}/{name}", str(local))
    return local


@st.cache_data
def get_quantification() -> pd.DataFrame:
    """Per-animal × per-region c-Fos densities. Shape (12, 1359)."""
    path = _ensure_csv("cfos_object_density_quantification.csv", BUCKET_PREFIX_TAB)
    return pd.read_csv(path)


@st.cache_data
def get_statistics() -> pd.DataFrame:
    """Per-region G002 vs G001 stats. Shape (1356, 28)."""
    path = _ensure_csv(
        "cfos_object_density_statistics_G002_vs_G001.csv", BUCKET_PREFIX_TAB
    )
    return pd.read_csv(path)


@st.cache_data
def get_atlas() -> pd.DataFrame:
    """Atlas region table — id, parent_id, name, acronym, RGB. Shape (1356, 9)."""
    path = _ensure_csv("atlas_regions.csv", BUCKET_PREFIX_NIFTI)
    return pd.read_csv(path)


@st.cache_data
def get_atlas_lookup() -> dict[str, dict]:
    """Acronym → {id, name, parent_acronym}. Used by the LLM prompt and click resolver."""
    atlas = get_atlas()
    by_id = {int(row["id"]): row["acronym"] for _, row in atlas.iterrows()}
    lookup: dict[str, dict] = {}
    for _, row in atlas.iterrows():
        parent = by_id.get(int(row["parent_id"]), "")
        lookup[row["acronym"]] = {
            "id": int(row["id"]),
            "name": row["name"],
            "parent_acronym": parent,
        }
    return lookup


# ---------------------------------------------------------------------------
# NIfTI loaders
# ---------------------------------------------------------------------------


def _ensure_nifti(name: str) -> Path:
    local = DATA_DIR / name
    if not local.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        download_file(f"{BUCKET_PREFIX_NIFTI}/{name}", str(local))
    return local


def ensure_static_volumes() -> None:
    """Make sure static/<short>.nii.gz exists for every volume niivue serves.

    Streamlit's static mount can't follow symlinks, so we copy the downloaded
    NIfTIs from data/ into static/ on first call. Idempotent.
    """
    import shutil

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    for short_name, bucket_name in _STATIC_COPY_MAP.items():
        target = STATIC_DIR / short_name
        if target.exists() and target.stat().st_size > 0:
            continue
        source = _ensure_nifti(bucket_name)
        shutil.copy2(source, target)


@st.cache_resource
def get_anatomy_path() -> Path:
    return _ensure_nifti("brain_atlas_anatomy.nii.gz")


@st.cache_resource
def get_regions_path() -> Path:
    return _ensure_nifti("brain_atlas_regions.nii.gz")


@st.cache_resource
def get_diff_map_path() -> Path:
    return _ensure_nifti("cfos_group_median_difference_G002_vs_G001.nii.gz")


@st.cache_resource
def get_g001_median_path() -> Path:
    return _ensure_nifti("cfos_G001_median.nii.gz")


@st.cache_resource
def get_g002_median_path() -> Path:
    return _ensure_nifti("cfos_G002_median.nii.gz")


@st.cache_resource
def get_regions_image() -> sitk.Image:
    """The labelmap volume as a SimpleITK image — used for click-to-region resolution."""
    return sitk.ReadImage(str(get_regions_path()))


@st.cache_resource
def get_anatomy_image() -> sitk.Image:
    """Anatomy NIfTI as a SimpleITK image (for the region-spatial panel)."""
    return sitk.ReadImage(str(get_anatomy_path()))


@st.cache_resource
def get_g001_median_image() -> sitk.Image:
    """G001 c-Fos median signal NIfTI as a SimpleITK image."""
    return sitk.ReadImage(str(get_g001_median_path()))


@st.cache_resource
def get_g002_median_image() -> sitk.Image:
    """G002 c-Fos median signal NIfTI as a SimpleITK image."""
    return sitk.ReadImage(str(get_g002_median_path()))


# ---------------------------------------------------------------------------
# Click-to-region resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedRegion:
    id: int
    acronym: str
    name: str


def resolve_label(label_id: int) -> Optional[ResolvedRegion]:
    """Map a labelmap integer (= atlas id) back to its atlas row, or None if not found / background."""
    if not label_id:
        return None
    atlas = get_atlas()
    hit = atlas[atlas["id"] == int(label_id)]
    if hit.empty:
        return None
    row = hit.iloc[0]
    return ResolvedRegion(
        id=int(row["id"]), acronym=row["acronym"], name=row["name"]
    )
