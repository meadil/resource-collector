"""Environment check. Run this first, and whenever something behaves strangely."""
import importlib
import shutil
import subprocess
import sys

from rc_common import INPUT, ROOT, find_binary, load_config

ok_all = True


def check(label, ok, detail=""):
    global ok_all
    ok_all &= bool(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {label} {detail}")


def main():
    cfg = load_config()
    check("python >= 3.9", sys.version_info >= (3, 9), sys.version.split()[0])
    check("running inside .venv", ".venv" in sys.executable.lower() or "venv" in sys.prefix.lower(), sys.executable)
    for mod in ("gallery_dl", "yt_dlp", "faster_whisper"):
        try:
            importlib.import_module(mod)
            check(f"python module {mod}", True)
        except Exception as e:  # noqa: BLE001
            check(f"python module {mod}", False, f"-> pip install ({e})")
    for b in ("ffmpeg", "ffprobe", "tesseract"):
        p = find_binary(b)
        check(f"binary {b}", p, p or "-> not found (winget install; reopen terminal)")
    cf = ROOT / (cfg.get("cookies_file") or "cookies.txt")
    if cf.exists():
        txt = cf.read_text(encoding="utf-8", errors="replace")
        check("cookies.txt has instagram sessionid", "sessionid" in txt and "instagram.com" in txt)
    elif cfg.get("cookies_from_browser"):
        check("cookies via browser", True, f"({cfg['cookies_from_browser']})")
    else:
        check("cookies", False, "-> export instagram cookies to cookies.txt (see README)")
    files = [p for p in INPUT.rglob("*") if p.suffix.lower() in (".json", ".html", ".txt") and "PUT_YOUR" not in p.name]
    check("input/ has export files", files, f"({len(files)} files)")
    free = shutil.disk_usage(ROOT).free / 1e9
    check("disk free", free >= cfg["min_free_disk_gb"], f"{free:.1f} GB")
    print("\nALL GOOD" if ok_all else "\nFix the FAIL items above.")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
