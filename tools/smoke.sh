#!/usr/bin/env bash
# Pre-demo smoke test. Runs every check we can without Playwright/a real browser.
# Exits 0 on full pass, non-zero on any failure.
#
# Usage:
#   bash scripts/smoke.sh              # full run, ANTHROPIC_API_KEY optional
#   ANTHROPIC_API_KEY=... bash scripts/smoke.sh   # also runs the live chat AC

set -u

cd "$(dirname "$0")/.."

ARTIFACT_DIR="/tmp/smoke-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$ARTIFACT_DIR"
LOG="$ARTIFACT_DIR/smoke.log"
exec > >(tee "$LOG") 2>&1

fail() { echo "AC-$1: FAIL — $2"; exit 1; }
ok()   { echo "AC-$1: PASS"; }

PORT=${PORT:-8501}

echo "=== Brain Earth smoke test ==="
echo "Artifacts: $ARTIFACT_DIR"
echo

# -----------------------------------------------------------------------------
# AC-2: data module returns expected shapes and lookups
# -----------------------------------------------------------------------------
python - <<'PY' || fail 2 "data module import or shape mismatch"
from dashboard import data
assert data.get_quantification().shape == (12, 1359), f"quant shape {data.get_quantification().shape}"
assert data.get_statistics().shape    == (1356, 28), f"stats shape {data.get_statistics().shape}"
assert data.get_atlas().shape         == (1356, 9),  f"atlas shape {data.get_atlas().shape}"
lk = data.get_atlas_lookup()
assert len(lk) == 1356
assert lk["root"]["id"] == 5000
assert data.resolve_label(5000).acronym == "root"
assert data.resolve_label(0) is None
assert data.resolve_label(99999999) is None
PY
ok 2

# -----------------------------------------------------------------------------
# AC-4: LLM post-filter drops non-atlas acronyms
# -----------------------------------------------------------------------------
python - <<'PY' || fail 4 "post-filter regression"
from dashboard.llm import filter_acronyms
from dashboard.data import get_atlas_lookup
valid = set(get_atlas_lookup().keys())
keep, drop = filter_acronyms("Hunger involves ARH, NTS, PVH neurons. HUNG matters too.", valid)
assert "ARH" in keep and "NTS" in keep and "PVH" in keep, f"keep={keep}"
assert "HUNG" in drop, f"drop={drop}"
PY
ok 4

# -----------------------------------------------------------------------------
# AC-6: no-key path raises ChatUnavailable cleanly
# -----------------------------------------------------------------------------
python - <<'PY' || fail 6 "no-key path did not raise ChatUnavailable"
import os
os.environ.pop("ANTHROPIC_API_KEY", None)
from dashboard.llm import answer, ChatUnavailable
try:
    answer("test")
    raise AssertionError("expected ChatUnavailable")
except ChatUnavailable:
    pass
PY
ok 6

# -----------------------------------------------------------------------------
# AC-1: Streamlit boots and serves the home page
# -----------------------------------------------------------------------------
if curl -sf -o /dev/null --max-time 2 "http://localhost:$PORT/_stcore/health"; then
    SPAWNED_BY_US=0
    echo "(Streamlit already running on :$PORT — reusing)"
else
    SPAWNED_BY_US=1
    nohup streamlit run streamlit_app.py \
        --server.headless true --server.port "$PORT" \
        --browser.gatherUsageStats false \
        > "$ARTIFACT_DIR/streamlit.log" 2>&1 &
    ST_PID=$!
    trap '[ "$SPAWNED_BY_US" = "1" ] && kill $ST_PID 2>/dev/null || true' EXIT
fi

# Wait up to 30s for ready
for i in $(seq 1 30); do
    if curl -sf -o /dev/null --max-time 1 "http://localhost:$PORT/_stcore/health"; then
        break
    fi
    sleep 1
done
curl -sf -o /dev/null --max-time 2 "http://localhost:$PORT/_stcore/health" \
    || fail 1 "Streamlit did not respond on :$PORT within 30s"
curl -sf "http://localhost:$PORT/" -o "$ARTIFACT_DIR/home.html"
grep -q "<title>Streamlit</title>" "$ARTIFACT_DIR/home.html" \
    || fail 1 "home page missing Streamlit title"
ok 1

# -----------------------------------------------------------------------------
# AC-7: NIfTI cache works (files exist after first call)
# -----------------------------------------------------------------------------
for f in brain_atlas_anatomy.nii.gz brain_atlas_regions.nii.gz cfos_group_median_difference_G002_vs_G001.nii.gz; do
    [ -s "data/$f" ] || fail 7 "data/$f missing or empty after data layer init"
done
ok 7

# -----------------------------------------------------------------------------
# AC-3 (LIVE): the canon "hunger" query returns ≥3 atlas acronyms
# Only runs when ANTHROPIC_API_KEY is set; otherwise reported as SKIP.
# -----------------------------------------------------------------------------
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    python - <<'PY' || fail 3 "live chat AC failed"
from dashboard.llm import answer
r = answer("show me regions involved in hunger and satiety")
assert len(r.acronyms) >= 3, f"got only {len(r.acronyms)} acronyms: {r.acronyms}"
print(f"  acronyms: {r.acronyms}")
PY
    ok 3
else
    echo "AC-3: SKIP (set ANTHROPIC_API_KEY to run live chat assertion)"
fi

echo
echo "=== smoke complete — artifacts: $ARTIFACT_DIR ==="
