"""Shared helpers for resource-collector scripts."""
import json
import os
import re
import shutil
import sys
from pathlib import Path


def setup_utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


setup_utf8()

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp"
DATA = ROOT / "data"
MODELS = ROOT / "models"
INPUT = ROOT / "input"

DEFAULT_CONFIG = {
    "cookies_file": "cookies.txt",
    "cookies_from_browser": None,
    "whisper_model": "base",
    "whisper_language": None,
    "ocr_lang": "eng",
    "ocr_psm": 11,
    "frame_interval_seconds": 4,
    "max_frames_per_video": 40,
    "max_video_minutes": 15,
    "max_filesize": "200M",
    "sleep_between_requests": [3, 7],
    "sleep_between_posts": [8, 20],
    "min_free_disk_gb": 2,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    p = ROOT / "config.json"
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] config.json unreadable ({e}); using defaults", file=sys.stderr)
    return cfg


# instagram.com/p/CODE, /reel/CODE, /reels/CODE, /tv/CODE, optionally /username/ before
POST_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:[A-Za-z0-9_.]+/)?(p|reel|reels|tv)/([A-Za-z0-9_-]+)"
)


def normalize_url(text):
    """Return (canonical_url, shortcode) or None."""
    if not text:
        return None
    m = POST_RE.search(text.replace("\\/", "/"))
    if not m:
        return None
    kind, code = m.group(1), m.group(2)
    kind = "reel" if kind in ("reel", "reels") else kind
    return f"https://www.instagram.com/{kind}/{code}/", code


def atomic_write(path, text):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def find_binary(name):
    p = shutil.which(name)
    if p:
        return p
    if os.name == "nt":
        candidates = []
        if name == "tesseract":
            candidates = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
            ]
        for c in candidates:
            if os.path.exists(c):
                return c
    return None
