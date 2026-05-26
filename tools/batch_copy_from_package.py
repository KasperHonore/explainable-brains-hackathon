"""Copy skills + scripts from agentic-dev-skills into workspace. Run: python tools/batch_copy_from_package.py"""
import shutil
from pathlib import Path

PKG = Path(r"C:\cursor\agentic-dev-skills")
WS = Path(__file__).resolve().parent.parent

def main():
    for name in ("setup", "spec", "plan", "build", "review", "audit", "reflect", "help-skills"):
        src = PKG / "skills" / name
        for root in (WS / ".claude" / "skills", WS / ".cursor" / "skills"):
            dst = root / name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(dst)
    scripts_dst = WS / "scripts"
    if scripts_dst.exists():
        shutil.rmtree(scripts_dst)
    shutil.copytree(PKG / "scripts", scripts_dst)
    print(scripts_dst)
    print("done")

if __name__ == "__main__":
    main()
