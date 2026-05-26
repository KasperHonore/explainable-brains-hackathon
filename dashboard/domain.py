"""Challenge B domain model — types and operations on atlas / stats / quant data.

I/O and Streamlit caching live in `dashboard.data`. This module holds join logic,
effect-size views, and rankings so UI code stays thin.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Optional

import numpy as np
import pandas as pd
import SimpleITK as sitk

from dashboard import data

GroupId = Literal["G001", "G002"]

META_COLS = frozenset({"scan_name", "animal_nr", "group_nr"})


@dataclass(frozen=True)
class AtlasRegion:
    id: int
    acronym: str
    name: str
    parent_id: int
    parent_acronym: str = ""


@dataclass(frozen=True)
class RegionEffect:
    acronym: str
    region_name: str
    log2_fc: float
    log2_fc_ci_low: float
    log2_fc_ci_high: float
    p_uncorrected: float
    n_semaglutide_eff: int  # stats n_A_eff (G002)
    n_vehicle_eff: int  # stats n_B_eff (G001)
    hierarchy_level: int
    is_lowest_level: bool
    in_labelmap: bool


@dataclass(frozen=True)
class AnimalDensity:
    scan_name: str
    animal_nr: str
    group: GroupId
    acronym: str
    density: Optional[float]


# ---------------------------------------------------------------------------
# Atlas
# ---------------------------------------------------------------------------


def get_atlas_region(acronym: str) -> Optional[AtlasRegion]:
    lookup = data.get_atlas_lookup()
    hit = lookup.get(acronym)
    if not hit:
        return None
    atlas = data.get_atlas()
    row = atlas[atlas["acronym"] == acronym].iloc[0]
    return AtlasRegion(
        id=int(hit["id"]),
        acronym=acronym,
        name=str(hit["name"]),
        parent_id=int(row["parent_id"]),
        parent_acronym=str(hit.get("parent_acronym", "")),
    )


@lru_cache(maxsize=1)
def labelmap_region_ids() -> frozenset[int]:
    """Atlas IDs that appear as at least one voxel in the region labelmap."""
    path = data.get_regions_path()
    arr = sitk.GetArrayFromImage(sitk.ReadImage(str(path)))
    return frozenset(int(v) for v in np.unique(arr) if v)


def in_labelmap(region_id: int) -> bool:
    return int(region_id) in labelmap_region_ids()


# ---------------------------------------------------------------------------
# Statistics → RegionEffect
# ---------------------------------------------------------------------------


def _row_to_effect(
    row: pd.Series, labels: frozenset[int], *, acronym: Optional[str] = None
) -> RegionEffect:
    rid = int(row["region_id"])
    acr = acronym if acronym is not None else str(row.get("acronym", row.name))
    return RegionEffect(
        acronym=acr,
        region_name=str(row["region_name"]),
        log2_fc=float(row["log2_fold_change"]),
        log2_fc_ci_low=float(row["log2fc_ci_low"]),
        log2_fc_ci_high=float(row["log2fc_ci_high"]),
        p_uncorrected=float(row["p_value"]),
        n_semaglutide_eff=int(row["n_A_eff"]),
        n_vehicle_eff=int(row["n_B_eff"]),
        hierarchy_level=int(row["hierarchy_level"]),
        is_lowest_level=bool(row["is_lowest_level"]),
        in_labelmap=rid in labels,
    )


def effects_from_stats(
    stats: pd.DataFrame,
    acronyms: list[str],
    *,
    labels: Optional[frozenset[int]] = None,
) -> list[RegionEffect]:
    """Resolve acronyms to effects; preserve input order; skip unknown acronyms."""
    if not acronyms:
        return []
    labels = labels if labels is not None else labelmap_region_ids()
    sub = stats[stats["acronym"].isin(acronyms)].set_index("acronym")
    out: list[RegionEffect] = []
    for acr in acronyms:
        if acr not in sub.index:
            continue
        row = sub.loc[acr]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        out.append(_row_to_effect(row, labels, acronym=acr))
    return out


def resolve_effects(acronyms: list[str]) -> list[RegionEffect]:
    """Load cached stats and resolve acronyms (panel / LLM follow-up)."""
    return effects_from_stats(data.get_statistics(), acronyms)


def top_regions(
    n: int = 20,
    *,
    leaf_only: bool = True,
    by: Literal["abs_log2fc", "log2fc"] = "abs_log2fc",
) -> list[RegionEffect]:
    """Rank regions by effect size for auto-highlight / demo defaults."""
    stats = data.get_statistics().copy()
    if leaf_only:
        stats = stats[stats["is_lowest_level"] == True]  # noqa: E712
    stats = stats.dropna(subset=["log2_fold_change"])
    if by == "abs_log2fc":
        stats["_rank"] = stats["log2_fold_change"].abs()
    else:
        stats["_rank"] = stats["log2_fold_change"]
    stats = stats.nlargest(n, "_rank")
    labels = labelmap_region_ids()
    return [_row_to_effect(row, labels) for _, row in stats.iterrows()]


def effects_to_panel_frame(effects: list[RegionEffect]) -> pd.DataFrame:
    """DataFrame columns matching the side panel."""
    if not effects:
        return pd.DataFrame(
            columns=[
                "acronym",
                "region_name",
                "log2_fold_change",
                "p_value",
                "n_A_eff",
                "n_B_eff",
                "in_labelmap",
            ]
        )
    rows = [
        {
            "acronym": e.acronym,
            "region_name": e.region_name,
            "log2_fold_change": e.log2_fc,
            "p_value": e.p_uncorrected,
            "n_A_eff": e.n_semaglutide_eff,
            "n_B_eff": e.n_vehicle_eff,
            "in_labelmap": e.in_labelmap,
        }
        for e in effects
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Quantification (long)
# ---------------------------------------------------------------------------


def quant_region_columns(quant: pd.DataFrame) -> list[str]:
    return [c for c in quant.columns if c not in META_COLS]


def quant_long(quant: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Melt wide quantification to one row per scan × region."""
    if quant is None:
        quant = data.get_quantification()
    regions = quant_region_columns(quant)
    long = quant.melt(
        id_vars=list(META_COLS),
        value_vars=regions,
        var_name="acronym",
        value_name="density",
    )
    long["group_nr"] = long["group_nr"].astype(str)
    return long


def densities_for_region(acronym: str, quant: Optional[pd.DataFrame] = None) -> list[AnimalDensity]:
    """Per-animal densities for one region (boxplot / strip plot input)."""
    long = quant_long(quant)
    sub = long[long["acronym"] == acronym]
    out: list[AnimalDensity] = []
    for _, row in sub.iterrows():
        val = row["density"]
        density = None if pd.isna(val) else float(val)
        out.append(
            AnimalDensity(
                scan_name=str(row["scan_name"]),
                animal_nr=str(row["animal_nr"]),
                group=row["group_nr"],  # type: ignore[arg-type]
                acronym=acronym,
                density=density,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Spatial helpers (for future mask / highlight)
# ---------------------------------------------------------------------------


def region_id_for_acronym(acronym: str) -> Optional[int]:
    lookup = data.get_atlas_lookup()
    hit = lookup.get(acronym)
    return int(hit["id"]) if hit else None


def mask_for_region(acronym: str) -> Optional[np.ndarray]:
    """Binary ZYX mask for an acronym, or None if not in the labelmap."""
    rid = region_id_for_acronym(acronym)
    if rid is None or not in_labelmap(rid):
        return None
    arr = sitk.GetArrayFromImage(data.get_regions_image()).astype(np.int32)
    return arr == rid


# ---------------------------------------------------------------------------
# Region-spatial crop (anatomy + per-group c-Fos signal, side-by-side ready)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegionSpatialCrop:
    """Bounded slab of anatomy + G001 + G002 signal centered on a region."""
    acronym: str
    bbox: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]  # (z, y, x)
    anatomy: np.ndarray  # (dz, dy, dx)
    signal_g001: np.ndarray
    signal_g002: np.ndarray
    mask: np.ndarray  # bool (dz, dy, dx)
    centroid: tuple[int, int, int]  # (z, y, x) within crop
    signal_scale: tuple[float, float]  # shared (vmin, vmax)


@lru_cache(maxsize=64)
def region_spatial_crop(acronym: str, pad: int = 4) -> Optional[RegionSpatialCrop]:
    """Crop anatomy + G001/G002 signal + mask to the region's bounding box.

    Returns None when the region has no voxel mask in the atlas labelmap.
    """
    mask_full = mask_for_region(acronym)
    if mask_full is None:
        return None
    coords = np.argwhere(mask_full)
    if coords.size == 0:
        return None

    zmin, ymin, xmin = coords.min(axis=0)
    zmax, ymax, xmax = coords.max(axis=0) + 1
    nz, ny, nx = mask_full.shape
    z0, z1 = max(0, int(zmin) - pad), min(nz, int(zmax) + pad)
    y0, y1 = max(0, int(ymin) - pad), min(ny, int(ymax) + pad)
    x0, x1 = max(0, int(xmin) - pad), min(nx, int(xmax) + pad)

    anatomy = sitk.GetArrayFromImage(data.get_anatomy_image())
    sig1 = sitk.GetArrayFromImage(data.get_g001_median_image())
    sig2 = sitk.GetArrayFromImage(data.get_g002_median_image())

    sl = (slice(z0, z1), slice(y0, y1), slice(x0, x1))
    anat_c = anatomy[sl].astype(np.float32)
    sig1_c = sig1[sl].astype(np.float32)
    sig2_c = sig2[sl].astype(np.float32)
    mask_c = mask_full[sl]

    centroid_full = coords.mean(axis=0).astype(int)
    centroid = (
        int(centroid_full[0] - z0),
        int(centroid_full[1] - y0),
        int(centroid_full[2] - x0),
    )

    in_region = np.concatenate(
        [sig1_c[mask_c].ravel(), sig2_c[mask_c].ravel()]
    )
    in_region = in_region[in_region > 0]
    vmax = float(np.percentile(in_region, 99)) if in_region.size else 1.0
    if vmax <= 0:
        vmax = float(max(sig1_c.max(), sig2_c.max(), 1.0))

    return RegionSpatialCrop(
        acronym=acronym,
        bbox=((int(z0), int(z1)), (int(y0), int(y1)), (int(x0), int(x1))),
        anatomy=anat_c,
        signal_g001=sig1_c,
        signal_g002=sig2_c,
        mask=np.asarray(mask_c, dtype=bool),
        centroid=centroid,
        signal_scale=(0.0, vmax),
    )
