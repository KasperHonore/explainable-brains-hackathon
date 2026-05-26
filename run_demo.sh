#!/usr/bin/env bash
# run_demo.sh — Launch the Brain Earth Streamlit dashboard with a guardrail
# against accidentally going live without an ANTHROPIC_API_KEY (which makes
# the chat-driven region highlight silently dead — see KEY-1 spec).
#
# Usage:
#   bash scripts/run_demo.sh              # require the key, refuse if missing
#   bash scripts/run_demo.sh --allow-no-key   # launch anyway (viewer-only mode)
#
# If /workspace/.env exists, it is sourced so the key can live there
# (gitignored via the existing *.env pattern). Exit 2 on missing-key without
# the override flag; that distinguishes it from generic failure (exit 1).

set -euo pipefail

ALLOW_NO_KEY=0
for arg in "$@"; do
    case "$arg" in
        --allow-no-key) ALLOW_NO_KEY=1 ;;
        *) echo "usage: $0 [--allow-no-key]" >&2; exit 1 ;;
    esac
done

ENV_FILE="${WORKSPACE_DIR:-/workspace}/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    if [ "$ALLOW_NO_KEY" -eq 1 ]; then
        echo "chat: DISABLED — proceeding because --allow-no-key"
    else
        echo "ERROR: ANTHROPIC_API_KEY not found." >&2
        echo "  Either export it in this shell, drop it into $ENV_FILE," >&2
        echo "  or pass --allow-no-key to launch the dashboard without chat." >&2
        exit 2
    fi
else
    echo "chat: enabled"
fi

exec python -m streamlit run streamlit_app.py \
    --server.headless true \
    --server.port 8501
