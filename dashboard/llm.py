"""Anthropic-backed chat agent grounded to the Allen mouse atlas.

The system prompt lists every atlas acronym (~1356 rows) so Claude has no
excuse to invent one. A post-filter intersects every acronym-shaped token in
the response against the atlas set — anything Claude makes up gets dropped
before the highlight call.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import anthropic

from dashboard.data import get_atlas_lookup

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

# Acronym shape in this atlas: 1–10 chars starting with letter, alnum-with-slash/dash.
# Examples in the data: PVT, ACA2/3, ACA6a, NTS, ENTl1.
_ACRONYM_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9/\-]{0,9}")


class ChatUnavailable(RuntimeError):
    """Raised when the chat path can't run (missing key, network failure, 401)."""


@dataclass
class ChatResponse:
    text: str
    acronyms: list[str] = field(default_factory=list)  # atlas-validated
    dropped: list[str] = field(default_factory=list)  # mentioned but not in atlas


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def build_system_prompt() -> str:
    """Render the atlas into a system prompt; instruct Claude to stay grounded."""
    lookup = get_atlas_lookup()
    # Format as `ACRONYM — Full name (parent: PARENT)` lines.
    lines = []
    for acronym, info in lookup.items():
        parent = info["parent_acronym"]
        suffix = f" (parent: {parent})" if parent else ""
        lines.append(f"{acronym} — {info['name']}{suffix}")
    atlas_block = "\n".join(lines)

    return (
        "You are a neuroscience research assistant exploring c-Fos activity in "
        "mouse brains treated with semaglutide (Wegovy/Ozempic) vs vehicle. "
        "Answer in plain English, keep it under 3 sentences, and when you name a "
        "brain region ALWAYS use its acronym as it appears in the table below.\n\n"
        "Rules:\n"
        "1. Only name region acronyms from this table. If a concept doesn't have a clear "
        "atlas region, say so plainly.\n"
        "2. Aim for 3–8 acronyms per answer when the question is biological; fewer is fine.\n"
        "3. Do not include disclaimers or apologies — the caller is a domain expert.\n\n"
        "ATLAS REGIONS (acronym — name):\n"
        f"{atlas_block}\n"
    )


# ---------------------------------------------------------------------------
# Post-filter
# ---------------------------------------------------------------------------


def filter_acronyms(text: str, valid: set[str]) -> tuple[list[str], list[str]]:
    """Pull acronym-shaped tokens out of text; split into (in_atlas, dropped).

    Order-preserving and de-duplicated by first occurrence.
    """
    seen: set[str] = set()
    keep: list[str] = []
    drop: list[str] = []
    for match in _ACRONYM_TOKEN.findall(text):
        if match in seen:
            continue
        seen.add(match)
        # Case-sensitive match: atlas acronyms are case-defined.
        if match in valid:
            keep.append(match)
        elif _looks_like_acronym(match):
            # Only flag dropped if it actually looks like an acronym (uppercase-leaning),
            # not every English word. Avoids flooding `dropped` with prose.
            drop.append(match)
    return keep, drop


def _looks_like_acronym(token: str) -> bool:
    """Heuristic: a token is acronym-shaped if it has an uppercase letter
    AND either contains a digit/slash/dash OR is all uppercase."""
    if not any(c.isupper() for c in token):
        return False
    if any(c.isdigit() or c in "/-" for c in token):
        return True
    return token.isupper()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def answer(query: str, *, model: str = DEFAULT_MODEL) -> ChatResponse:
    """Ask Claude a biological question; return text + filtered acronyms.

    Raises ChatUnavailable if ANTHROPIC_API_KEY is missing or the API call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ChatUnavailable(
            "ANTHROPIC_API_KEY is not set. Export it in the shell before launching Streamlit."
        )

    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=build_system_prompt(),
            messages=[{"role": "user", "content": query}],
        )
    except anthropic.APIError as exc:
        raise ChatUnavailable(f"Anthropic API error: {exc}") from exc

    text = "".join(
        block.text for block in msg.content if getattr(block, "type", "") == "text"
    )

    atlas_acronyms = set(get_atlas_lookup().keys())
    keep, drop = filter_acronyms(text, atlas_acronyms)
    return ChatResponse(text=text, acronyms=keep, dropped=drop)
