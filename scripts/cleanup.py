"""Storage housekeeping.

  python scripts/cleanup.py            # delete everything in tmp/, show sizes
  python scripts/cleanup.py --models   # also delete cached Whisper models (re-downloads next run)
"""
import shutil
import sys

from rc_common import DATA, MODELS, ROOT, TMP


def size(p):
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def mb(n):
    return f"{n / 1e6:.1f} MB"


def main():
    before = size(TMP)
    if TMP.exists():
        for child in TMP.iterdir():
            if child.name == ".gitkeep":
                continue
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
    left = size(TMP)
    print(f"tmp/: freed {mb(before - left)}; remaining {mb(left)}")
    if "--models" in sys.argv:
        m = size(MODELS)
        for child in MODELS.iterdir():
            if child.name == ".gitkeep":
                continue
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
        print(f"models/: freed {mb(m)}")
    else:
        print(f"models/: {mb(size(MODELS))} (kept; use --models to delete)")
    print(f"data/: {mb(size(DATA))}")
    free = shutil.disk_usage(ROOT).free
    print(f"disk free: {free / 1e9:.1f} GB")
    return 0 if left == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
