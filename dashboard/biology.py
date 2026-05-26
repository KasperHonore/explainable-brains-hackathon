"""Neuro-circuit biology mapping for the Classic plots tab.

Three hardcoded circuits (Satiety, Aversion, Reward) translate atlas acronyms
into the biology a non-specialist judge can follow. Each circuit has an
expected direction of change in Semaglutide vs Vehicle; `score_circuit`
counts how many member regions actually move that direction in the data.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from dashboard import data

logger = logging.getLogger(__name__)

Direction = Literal["up", "down"]


@dataclass(frozen=True)
class BiologyCircuit:
    key: str
    headline: str
    explanation: str
    members: tuple[str, ...]
    expected_direction: Direction


@dataclass(frozen=True)
class CircuitScore:
    circuit: BiologyCircuit
    n_total: int  # members present in stats with non-NaN log2FC
    n_aligned: int  # of those, how many move in the expected direction
    member_rows: pd.DataFrame  # acronym, region_name, log2_fold_change, p_value, aligned


_RAW_CIRCUITS: tuple[BiologyCircuit, ...] = (
    BiologyCircuit(
        key="satiety",
        headline="Satiety & gut-brain axis",
        explanation=(
            "'I'm full' signals from gut to brainstem. GLP-1 agonists like "
            "semaglutide are expected to amplify these regions."
        ),
        members=("NTS", "DMX", "PB", "AP", "CEA", "ARH", "PVH", "DMH", "LH", "VMH"),
        expected_direction="up",
    ),
    BiologyCircuit(
        key="aversion",
        headline="Emotional aversion",
        explanation=(
            "Food becomes emotionally less appealing — the amygdala / "
            "bed-nucleus circuit gets recruited when eating loses its pull."
        ),
        members=("CEA", "BST", "BLA", "MEA", "PVT", "LHA", "NTS"),
        expected_direction="up",
    ),
    BiologyCircuit(
        key="reward",
        headline="Reward, motivation & smell",
        explanation=(
            "Food stops feeling worth wanting; the dopaminergic reward and "
            "olfactory circuits should quiet down under semaglutide."
        ),
        members=("ACB", "VTA", "ORB", "MOB", "AON", "PIR", "OT", "AI", "AIv"),
        expected_direction="down",
    ),
)


def _filter_to_atlas(circuits: tuple[BiologyCircuit, ...]) -> tuple[BiologyCircuit, ...]:
    """Drop acronyms from each circuit that don't exist in the loaded atlas."""
    atlas_acronyms = set(data.get_atlas_lookup().keys())
    out: list[BiologyCircuit] = []
    for c in circuits:
        kept = tuple(a for a in c.members if a in atlas_acronyms)
        dropped = tuple(a for a in c.members if a not in atlas_acronyms)
        if dropped:
            logger.info(
                "biology: dropped %d acronym(s) from %s (not in atlas): %s",
                len(dropped), c.key, ", ".join(dropped),
            )
        out.append(
            BiologyCircuit(
                key=c.key,
                headline=c.headline,
                explanation=c.explanation,
                members=kept,
                expected_direction=c.expected_direction,
            )
        )
    return tuple(out)


def get_circuits() -> tuple[BiologyCircuit, ...]:
    """Atlas-filtered circuit definitions. Cheap; called per render."""
    return _filter_to_atlas(_RAW_CIRCUITS)


def score_circuit(circuit: BiologyCircuit, stats: pd.DataFrame) -> CircuitScore:
    """Count how many of the circuit's member regions move as expected."""
    expected_sign = 1 if circuit.expected_direction == "up" else -1
    sub = stats[stats["acronym"].isin(circuit.members)].copy()
    sub = sub.dropna(subset=["log2_fold_change"])
    sub["aligned"] = (
        ((sub["log2_fold_change"] > 0) & (expected_sign > 0))
        | ((sub["log2_fold_change"] < 0) & (expected_sign < 0))
    )
    member_rows = sub[
        ["acronym", "region_name", "log2_fold_change", "p_value", "aligned"]
    ].copy()
    # Sort so aligned regions with biggest effect surface first.
    member_rows["_rank"] = member_rows["log2_fold_change"].abs() * expected_sign * (
        member_rows["log2_fold_change"].apply(lambda v: 1 if v * expected_sign > 0 else -1)
    )
    member_rows = member_rows.sort_values("_rank", ascending=False).drop(columns=["_rank"])
    return CircuitScore(
        circuit=circuit,
        n_total=int(len(sub)),
        n_aligned=int(sub["aligned"].sum()),
        member_rows=member_rows.reset_index(drop=True),
    )
