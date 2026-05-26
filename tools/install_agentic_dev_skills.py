#!/usr/bin/env python3
"""Install agentic-dev-skills into this workspace.

  python3 tools/install_agentic_dev_skills.py           # symlinks (default)
  python3 tools/install_agentic_dev_skills.py --copy    # copy trees (no symlink privilege)
  python3 tools/install_agentic_dev_skills.py --setup     # install + brownfield Standard setup

Run from repo root (Git Bash, WSL, or devcontainer).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_NAMES = (
    "setup",
    "spec",
    "plan",
    "build",
    "review",
    "audit",
    "reflect",
    "help-skills",
)


def default_pkg_root() -> Path:
    env = os.environ.get("AGENTIC_DEV_SKILLS_ROOT")
    if env:
        return Path(env)
    if Path("/opt/agentic-dev-skills").is_dir():
        return Path("/opt/agentic-dev-skills")
    return Path(r"C:\cursor\agentic-dev-skills")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def read_version(pkg: Path) -> str:
    version_file = pkg / "VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    return "unknown"


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def symlink_dir(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        remove_path(dst)
    try:
        os.symlink(src, dst, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
            check=True,
            capture_output=True,
            text=True,
        )


def symlink_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        remove_path(dst)
    os.symlink(src, dst)


def copy_dir(src: Path, dst: Path) -> None:
    if dst.exists():
        remove_path(dst)
    shutil.copytree(src, dst)


def install_skills(pkg: Path, dest_parent: Path, *, use_copy: bool) -> None:
    dest_parent.mkdir(parents=True, exist_ok=True)
    for name in SKILL_NAMES:
        src = pkg / "skills" / name
        if not src.is_dir():
            raise FileNotFoundError(f"Missing skill directory: {src}")
        dest = dest_parent / name
        if use_copy:
            copy_dir(src, dest)
        else:
            symlink_dir(src, dest)
        print(f"  {'copied' if use_copy else 'linked'}: {dest}")


def install_scripts(pkg: Path, target: Path, *, use_copy: bool) -> None:
    scripts_src = pkg / "scripts"
    scripts_dst = target / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    for entry in scripts_src.iterdir():
        dest = scripts_dst / entry.name
        if entry.is_dir():
            if use_copy:
                copy_dir(entry, dest)
            else:
                symlink_dir(entry, dest)
            print(f"  {'copied' if use_copy else 'linked'} dir: scripts/{entry.name}")
        elif entry.suffix in (".sh", ".py"):
            if use_copy:
                shutil.copy2(entry, dest)
            else:
                symlink_file(entry, dest)
            print(f"  {'copied' if use_copy else 'linked'}: scripts/{entry.name}")

    apply_script_overrides(target)


def apply_script_overrides(target: Path) -> None:
    """Workspace patches for scripts that break on Windows CRLF bind mounts."""
    overrides = {
        "setup-write-workflow.sh": repo_root() / "tools" / "patches" / "setup-write-workflow.sh",
        "setup-install-hooks.sh": repo_root() / "tools" / "patches" / "setup-install-hooks.sh",
    }
    scripts_dst = target / "scripts"
    for name, src in overrides.items():
        if not src.is_file():
            continue
        dest = scripts_dst / name
        if dest.is_symlink() or dest.exists():
            remove_path(dest)
        shutil.copy2(src, dest)
        dest.chmod(dest.stat().st_mode | 0o111)
        print(f"  patched: scripts/{name}")


def write_markers(pkg: Path, target: Path, version: str) -> None:
    claude = target / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "installed-version").write_text(version + "\n", encoding="utf-8")
    (claude / "installed-package-path").write_text(
        str(pkg.resolve()) + "\n", encoding="utf-8"
    )
    print(f"  wrote: .claude/installed-version ({version})")


def run_setup(target: Path, pkg: Path) -> None:
    scripts = target / "scripts"
    bash = "bash"
    env = {**os.environ, "AGENTIC_DEV_SKILLS_ROOT": str(pkg)}
    steps = [
        [
            bash,
            str(scripts / "setup-create-infra.sh"),
            "--mode",
            "brownfield",
            "--package-root",
            str(pkg),
        ],
        [
            bash,
            str(scripts / "setup-install-hooks.sh"),
            "--tier",
            "with-rails",
            "--package-root",
            str(pkg),
        ],
        [
            bash,
            str(scripts / "setup-write-workflow.sh"),
            "--mode",
            "brownfield",
            "--tier",
            "with-rails",
            "--package-root",
            str(pkg),
        ],
    ]
    for cmd in steps:
        print(f"\n> {' '.join(cmd)}")
        subprocess.run(cmd, cwd=target, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy files instead of symlinks (Windows without Developer Mode)",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run brownfield setup scripts after install",
    )
    args = parser.parse_args()

    pkg = default_pkg_root()
    target = repo_root()
    if not pkg.is_dir():
        print(f"ERROR: package not found at {pkg}", file=sys.stderr)
        return 1

    version = read_version(pkg)
    use_copy = args.copy
    print(f"Installing agentic-dev-skills {version} ({'copy' if use_copy else 'symlink'})")
    print(f"  package: {pkg}")
    print(f"  target:  {target}")

    print("Installing .claude/skills/ ...")
    install_skills(pkg, target / ".claude" / "skills", use_copy=use_copy)
    print("Installing .cursor/skills/ ...")
    install_skills(pkg, target / ".cursor" / "skills", use_copy=use_copy)
    print("Installing scripts/ ...")
    install_scripts(pkg, target, use_copy=use_copy)
    write_markers(pkg, target, version)

    if args.setup:
        print("\nRunning /setup (brownfield, Standard guardrails) ...")
        run_setup(target, pkg)

    print(f"\nInstalled agentic-dev-skills {version} into {target}.")
    if not args.setup:
        print("Next: python3 tools/install_agentic_dev_skills.py --setup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
