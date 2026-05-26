#!/bin/bash
# setup-write-workflow.sh — render .claude/WORKFLOW.md from the workflow-guide.md template.
#
# Substitutes {MODE_DISPLAY}, {TIER_DISPLAY}, {HOOK_LIST_FOR_TIER} placeholders
# (plain-English forms — see the template's "Generation rules" section for the
# mapping). The template block is the fenced markdown inside
# skills/setup/refs/workflow-guide.md.
#
# Usage: bash scripts/setup-write-workflow.sh --mode {greenfield|brownfield} \
#                                             --tier {with-rails|no-rails} \
#                                             --package-root <path>
# Exit 0 on success.

set -euo pipefail

MODE=""
TIER=""
PKG_ROOT=""
while [ $# -gt 0 ]; do
    case "$1" in
        --mode) MODE="$2"; shift 2 ;;
        --tier) TIER="$2"; shift 2 ;;
        --package-root) PKG_ROOT="$2"; shift 2 ;;
        *) echo "usage: $0 --mode {greenfield|brownfield} --tier {with-rails|no-rails} --package-root <path>" >&2; exit 1 ;;
    esac
done

case "$MODE" in
    greenfield|brownfield) ;;
    *) echo "ERROR: --mode must be 'greenfield' or 'brownfield'" >&2; exit 1 ;;
esac
case "$TIER" in
    with-rails|no-rails) ;;
    *) echo "ERROR: --tier must be 'with-rails' or 'no-rails'" >&2; exit 1 ;;
esac

if [ -z "$PKG_ROOT" ] || [ ! -d "$PKG_ROOT" ]; then
    echo "ERROR: --package-root must point at an agentic-dev-skills checkout" >&2
    exit 1
fi

GUIDE="$PKG_ROOT/skills/setup/refs/workflow-guide.md"
if [ ! -f "$GUIDE" ]; then
    echo "ERROR: workflow-guide.md not found at $GUIDE" >&2
    exit 1
fi

# Read the package version once (used by both the skip-exists notice and the
# cold-start orientation block below).
PKG_VERSION=""
if [ -f "$PKG_ROOT/VERSION" ]; then
    PKG_VERSION=$(head -n 1 "$PKG_ROOT/VERSION" | tr -d '[:space:]')
fi
[ -z "$PKG_VERSION" ] && PKG_VERSION="(version unknown)"

# Pick the right HOOK_LIST_FOR_TIER content; write to a temp file for multi-line sed substitution
HOOK_LIST_FILE=$(mktemp)
trap 'rm -f "$HOOK_LIST_FILE"' EXIT
if [ "$TIER" = "with-rails" ]; then
    cat > "$HOOK_LIST_FILE" <<'EOF'
- `workflow-integrity` (pre-commit) — flags commits on `feature/{TASK-ID}-...` branches where the task isn't in `.claude/backlog/_queue.json`
- `secrets-scan` (pre-commit) — blocks commits whose staged content contains a known API-key prefix (`sk-`, `AIza`, `AKIA`, `ghp_`, `xoxb-`, `hf_`) or a `.env` file
- `session-start` (session-start) — prints a 5-line workflow reminder at session open + drift warnings if anything's stale
- `reflect-nudge` (session-end) — if the session had commits but no new rules/knowledge captured, prints a one-line nudge to consider `/reflect` before closing
EOF
else
    cat > "$HOOK_LIST_FILE" <<'EOF'
- (none — no-rails projects skip hooks; install with-rails later if reliability matters)
EOF
fi

# Extract the template (fenced markdown block under "## Generation template").
# Outer fence is four backticks (````markdown ... ````) so nested three-backtick
# blocks inside the template — the diagram, the git-revert example — extract
# cleanly. Pre-v0.24.0 the outer fence was three backticks and the awk exited
# on the first nested fence, silently truncating WORKFLOW.md at the diagram.
# Strip CR so awk line anchors work when the package is bind-mounted from Windows (CRLF).
TEMPLATE_FILE=$(mktemp)
GUIDE_UNIX=$(mktemp)
trap 'rm -f "$HOOK_LIST_FILE" "$TEMPLATE_FILE" "$GUIDE_UNIX"' EXIT
sed 's/\r$//' "$GUIDE" > "$GUIDE_UNIX"
awk '
    /^## Generation template$/ { in_section=1; next }
    in_section && /^````markdown$/ { in_block=1; next }
    in_block && /^````$/ { exit }
    in_block { print }
' "$GUIDE_UNIX" > "$TEMPLATE_FILE"

if [ ! -s "$TEMPLATE_FILE" ]; then
    echo "ERROR: could not extract Generation template from $GUIDE" >&2
    exit 1
fi

# Skip if .claude/WORKFLOW.md already exists (brownfield-safe; never clobber user customizations)
mkdir -p .claude
if [ -e .claude/WORKFLOW.md ]; then
    echo "skip (exists): .claude/WORKFLOW.md — review manually if you want the $PKG_VERSION template"
    exit 0
fi

# Map CLI flag values to plain-English display strings (see workflow-guide.md "Generation rules")
case "$MODE" in
    greenfield) MODE_DISPLAY="a new project" ;;
    brownfield) MODE_DISPLAY="an existing codebase" ;;
esac
case "$TIER" in
    with-rails) TIER_DISPLAY="Standard guardrails" ;;
    no-rails)   TIER_DISPLAY="no guardrails (every check is opt-in)" ;;
esac

# Substitute single-line placeholders, then expand the multi-line HOOK_LIST_FOR_TIER
sed -e "s|{MODE_DISPLAY}|$MODE_DISPLAY|g" -e "s|{TIER_DISPLAY}|$TIER_DISPLAY|g" "$TEMPLATE_FILE" \
    | sed -e "/{HOOK_LIST_FOR_TIER}/r $HOOK_LIST_FILE" -e "/{HOOK_LIST_FOR_TIER}/d" \
    > .claude/WORKFLOW.md

echo "Wrote .claude/WORKFLOW.md ($MODE mode, $TIER tier)"

# Cold-start orientation block. Prints after a fresh install only (the
# skip-exists branch above returns before this point on re-runs). This is
# the user's first impression of the package — keep it deterministic and
# don't let the calling Claude session layer a deployment-log summary on top.
cat <<EOF

─── agentic-dev-skills $PKG_VERSION — installed ──────────────────
You now have a structured spec → plan → build → review → reflect
workflow as six slash commands. Files-on-disk, not chat memory.

What just changed in this project:
EOF

# CLAUDE.md bullet only when CLAUDE.md actually exists. In the real /setup
# flow Claude writes CLAUDE.md during Q2 (before this script runs), so the
# bullet shows. If the four scripts are run standalone (without Claude
# authoring CLAUDE.md first), no bullet — matching what's actually on disk.
if [ -f CLAUDE.md ]; then
    echo "  • CLAUDE.md          your project's instructions, loaded every session"
fi

cat <<EOF
  • .claude/WORKFLOW.md  the six commands and when to use each
  • .claude/specs/       what to build, written before any code
  • .claude/backlog/     one task per file, sized for one Claude session
  • .claude/reviews/     the reviewer's notes on each change, kept after merge
EOF

# .claude/knowledge/ bullet only when the directory exists. v0.22.0 onward,
# /setup creates it; older /setup'd projects re-running setup may not have
# it yet, so the bullet stays conditional.
if [ -d .claude/knowledge ]; then
    echo "  • .claude/knowledge/   what each part of the project does and why"
fi

# .claude/hooks/ bullet only when hooks actually got installed (--tier with-rails).
# On --tier no-rails, setup-install-hooks.sh skips everything, so the bullet
# would be misleading.
if [ "$TIER" = "with-rails" ]; then
    echo "  • .claude/hooks/       small automatic checks at commit and session start"
fi

cat <<EOF

What to run next:
  1. Open .claude/WORKFLOW.md (~60 lines) — the full skill list and cadence
  2. Run /spec — it'll interview you about what to build, write the
     answers to disk as a spec, then /plan turns that into small
     tasks for /build to implement
──────────────────────────────────────────────────────────────────
EOF

exit 0
