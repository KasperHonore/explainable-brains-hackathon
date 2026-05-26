# agentic-dev-skills (local install)

Internal tooling — paths are gitignored. Package lives at `C:\cursor\agentic-dev-skills` (or `/opt/agentic-dev-skills` in devcontainer).

## One-time / after package update

From repo root in **Git Bash** or **devcontainer**:

```bash
# Preferred: symlinks (updates when you git pull the package)
python tools/install_agentic_dev_skills.py --setup

# Windows without symlink privilege
python tools/install_agentic_dev_skills.py --copy --setup
```

Or double-click `tools/run_install.cmd` on Windows.

Full file sync only (no setup scripts):

```bash
python tools/batch_copy_from_package.py
```

## Devcontainer

`postCreateCommand` runs `install.sh` and links `.cursor/skills/` automatically on rebuild.
