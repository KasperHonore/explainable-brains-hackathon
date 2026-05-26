"""One-shot copy install when symlinks cannot be created. Run: python tools/sync_copy.py"""
import shutil
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
PKG = Path(r"C:\cursor\agentic-dev-skills")
WS = Path(__file__).resolve().parent.parent
NAMES = ("setup", "spec", "plan", "build", "review", "audit", "reflect", "help-skills")

for name in NAMES:
    src = PKG / "skills" / name
    for dest_root in (WS / ".claude" / "skills", WS / ".cursor" / "skills"):
        d = dest_root / name
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(src, d)
        print("copied", d)

scripts_dst = WS / "scripts"
if scripts_dst.exists():
    shutil.rmtree(scripts_dst)
shutil.copytree(PKG / "scripts", scripts_dst)
print("copied", scripts_dst)
