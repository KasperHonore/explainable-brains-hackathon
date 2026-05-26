#!/bin/bash
# setup-install-hooks.sh — install hooks for the chosen tier.
#
# Tiers:
#   with-rails (default): workflow-integrity (pre-commit) + session-start
#   no-rails:             zero hooks
#
# Optional flags:
#   --harden              also install pre-commit-validate (production hardening)
#   --backlog-validate    also install validate-backlog (opt-in extra layer)
#
# Hook script bodies are extracted from skills/setup/refs/hooks-guide.md (the
# canonical source). scripts/health-check.sh is copied from the package.
#
# Usage: bash scripts/setup-install-hooks.sh --tier {with-rails|no-rails} \
#                                            [--harden] [--backlog-validate] \
#                                            --package-root <path>
# Exit 0 on success.

set -euo pipefail

TIER=""
HARDEN=0
BACKLOG_VALIDATE=0
PKG_ROOT=""
while [ $# -gt 0 ]; do
    case "$1" in
        --tier) TIER="$2"; shift 2 ;;
        --harden) HARDEN=1; shift ;;
        --backlog-validate) BACKLOG_VALIDATE=1; shift ;;
        --package-root) PKG_ROOT="$2"; shift 2 ;;
        *) echo "usage: $0 --tier {with-rails|no-rails} [--harden] [--backlog-validate] --package-root <path>" >&2; exit 1 ;;
    esac
done

case "$TIER" in
    with-rails|no-rails) ;;
    *) echo "ERROR: --tier must be 'with-rails' or 'no-rails'" >&2; exit 1 ;;
esac

if [ -z "$PKG_ROOT" ] || [ ! -d "$PKG_ROOT" ]; then
    echo "ERROR: --package-root must point at an agentic-dev-skills checkout" >&2
    exit 1
fi

HOOKS_GUIDE="$PKG_ROOT/skills/setup/refs/hooks-guide.md"
if [ ! -f "$HOOKS_GUIDE" ]; then
    echo "ERROR: hooks-guide.md not found at $HOOKS_GUIDE" >&2
    exit 1
fi

if [ "$TIER" = "no-rails" ]; then
    echo "no-rails tier: no hooks to install."
    exit 0
fi

mkdir -p .claude/hooks
echo "Installing hooks (tier: $TIER)..."

# Strip CR so awk line anchors work when the package is bind-mounted from Windows (CRLF).
HOOKS_GUIDE_UNIX=$(mktemp)
trap 'rm -f "$HOOKS_GUIDE_UNIX"' EXIT
sed 's/\r$//' "$HOOKS_GUIDE" > "$HOOKS_GUIDE_UNIX"

# Extract a hook script body from hooks-guide.md by header comment line.
# The hooks-guide embeds each hook in a code block whose first line is the
# Bash hashbang followed by `# .claude/hooks/<name>.sh — ...`.
extract_hook() {
    local hook_name="$1" out="$2"
    if [ -e "$out" ]; then
        echo "  skip (exists): $out"
        return 0
    fi
    awk -v name="$hook_name" '
        $0 ~ "^# \\.claude/hooks/" name "\\.sh" { in_block=1 }
        in_block && /^```$/ { exit }
        in_block { print }
    ' "$HOOKS_GUIDE_UNIX" > "$out"
    if [ ! -s "$out" ]; then
        echo "ERROR: could not extract hook '$hook_name' from $HOOKS_GUIDE" >&2
        rm -f "$out"
        return 1
    fi
    # Prepend bash shebang (the awk output starts at the comment line)
    { echo "#!/bin/bash"; cat "$out"; } > "$out.tmp" && mv "$out.tmp" "$out"
    chmod +x "$out"
    echo "  installed: $out"
}

extract_hook "workflow-integrity" .claude/hooks/workflow-integrity.sh
extract_hook "secrets-scan" .claude/hooks/secrets-scan.sh
extract_hook "session-start" .claude/hooks/session-start.sh
extract_hook "reflect-nudge" .claude/hooks/reflect-nudge.sh

# Optional: pre-commit-validate
if [ "$HARDEN" = "1" ]; then
    extract_hook "pre-commit-validate" .claude/hooks/pre-commit-validate.sh
fi

# Optional: validate-backlog
if [ "$BACKLOG_VALIDATE" = "1" ]; then
    extract_hook "validate-backlog" .claude/hooks/validate-backlog.sh
fi

# scripts/health-check.sh — skip if exists (brownfield-safe)
mkdir -p scripts
if [ -f "$PKG_ROOT/scripts/health-check.sh" ]; then
    if [ -e "scripts/health-check.sh" ]; then
        echo "  skip (exists): scripts/health-check.sh"
    else
        cp "$PKG_ROOT/scripts/health-check.sh" scripts/health-check.sh
        chmod +x scripts/health-check.sh
        echo "  copied: scripts/health-check.sh"
    fi
fi

# .claude/settings.json — skip if exists (brownfield-safe; never clobber user permissions)
SETTINGS=".claude/settings.json"
if [ -e "$SETTINGS" ]; then
    echo "  skip (exists): $SETTINGS — review manually if hook registration is missing"
else
    PRECOMMIT_HOOKS='        {"type": "command", "command": ".claude/hooks/workflow-integrity.sh"},
        {"type": "command", "command": ".claude/hooks/secrets-scan.sh"}'
    [ "$HARDEN" = "1" ] && PRECOMMIT_HOOKS="$PRECOMMIT_HOOKS,
        {\"type\": \"command\", \"command\": \".claude/hooks/pre-commit-validate.sh\"}"
    [ "$BACKLOG_VALIDATE" = "1" ] && PRECOMMIT_HOOKS="$PRECOMMIT_HOOKS,
        {\"type\": \"command\", \"command\": \".claude/hooks/validate-backlog.sh\"}"

    cat > "$SETTINGS" <<EOF
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
$PRECOMMIT_HOOKS
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [{"type": "command", "command": ".claude/hooks/session-start.sh"}]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [{"type": "command", "command": ".claude/hooks/reflect-nudge.sh"}]
      }
    ]
  }
}
EOF
    echo "  wrote: $SETTINGS"
fi

echo "Done."
exit 0
