"""Fetch ONE Instagram post, extract text (caption, OCR, transcript), delete the media.

  python scripts/fetch.py <url> [--caption-only] [--no-transcribe] [--no-video-ocr]
                                [--keep-media] [--force] [--no-delay] [--force-long]

Output: data/<shortcode>/{meta.json, caption.txt, ocr.txt, transcript.txt}
All downloaded media lives in tmp/<shortcode>/ and is ALWAYS deleted at the end
(unless --keep-media, in which case it is moved to tmp/keep/<shortcode>/ and you must
run scripts/cleanup.py when done looking at it).

Exit codes: 0 ok | 1 other error | 2 auth/login problem | 3 post gone/private
            4 rate limited | 5 low disk | 6 bad url
"""
import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from rc_common import DATA, MODELS, ROOT, TMP, atomic_write, find_binary, load_config, normalize_url

OK, OTHER, AUTH, GONE, RATE, DISK, BADURL = 0, 1, 2, 3, 4, 5, 6
IMG = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VID = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
GDL = [sys.executable, "-m", "gallery_dl"]
YTDLP = [sys.executable, "-m", "yt_dlp"]

warnings = []
network_used = False


def warn(msg):
    warnings.append(msg)
    print(f"[warn] {msg}", file=sys.stderr)


def run(cmd, timeout=600):
    global network_used
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError as e:
        return 127, "", str(e)


def classify(text):
    t = (text or "").lower()
    if any(k in t for k in ("429", "rate limit", "rate-limit", "too many requests", "wait a few minutes")):
        return RATE
    if any(k in t for k in ("login", "401", "403", "checkpoint", "not logged in", "authenticat",
                            "cookies", "sessionid", "csrf")):
        return AUTH
    if any(k in t for k in ("404", "not found", "unavailable", "does not exist", "removed", "private")):
        return GONE
    return OTHER


def auth_args(cfg):
    cf = cfg.get("cookies_file")
    if cf and (ROOT / cf).exists():
        return ["--cookies", str(ROOT / cf)]
    if cfg.get("cookies_from_browser"):
        return ["--cookies-from-browser", cfg["cookies_from_browser"]]
    return []


def sleep_arg(cfg):
    a, b = cfg["sleep_between_requests"]
    return f"{a}-{b}"


def natural_key(p):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name)]


# ---------------------------------------------------------------- metadata
def get_metadata(url, cfg):
    """Returns (info dict, error text)."""
    global network_used
    network_used = True
    info = {"caption": "", "author": "", "date": "", "media_count": 0, "kinds": []}
    errs = []
    rc, out, err = run(GDL + auth_args(cfg) + ["--sleep-request", sleep_arg(cfg), "-j", url], timeout=180)
    if rc == 0 and out.strip():
        try:
            data = json.loads(out)
        except Exception:
            data = []
        for entry in data if isinstance(data, list) else []:
            if not isinstance(entry, list) or not entry:
                continue
            meta = entry[-1] if isinstance(entry[-1], dict) else {}
            if entry[0] == 3:
                info["media_count"] += 1
                info["kinds"].append(str(meta.get("extension", "")).lower())
            for k in ("description", "caption"):
                if meta.get(k) and not info["caption"]:
                    info["caption"] = str(meta[k])
            if not info["author"]:
                info["author"] = str(meta.get("username") or meta.get("owner") or "")
            if not info["date"]:
                info["date"] = str(meta.get("post_date") or meta.get("date") or "")
    else:
        errs.append(f"gallery-dl -j rc={rc}: {(err or out)[-600:]}")

    if info["media_count"] == 0 and not info["caption"]:
        rc, out, err = run(YTDLP + auth_args(cfg) + ["--skip-download", "--dump-single-json",
                                                       "--no-warnings", "--no-playlist", url], timeout=180)
        if rc == 0 and out.strip():
            try:
                j = json.loads(out)
                info["caption"] = j.get("description") or j.get("title") or ""
                info["author"] = j.get("uploader") or j.get("channel") or ""
                info["date"] = j.get("upload_date") or ""
                info["media_count"] = 1
                info["kinds"] = ["mp4"]
            except Exception as e:  # noqa: BLE001
                errs.append(f"yt-dlp json parse failed: {e}")
        else:
            errs.append(f"yt-dlp rc={rc}: {(err or out)[-600:]}")
    return info, "\n".join(errs)


# ---------------------------------------------------------------- download
def list_media(work):
    return sorted([p for p in work.rglob("*") if p.is_file() and p.suffix.lower() in IMG | VID], key=natural_key)


def download(url, work, cfg):
    global network_used
    network_used = True
    work.mkdir(parents=True, exist_ok=True)
    rc, out, err = run(GDL + auth_args(cfg) + ["--sleep-request", sleep_arg(cfg), "--filesize-max",
                                                cfg["max_filesize"], "-D", str(work),
                                                "-f", "{num}.{extension}", url], timeout=900)
    media = list_media(work)
    errtxt = "" if media else f"gallery-dl rc={rc}: {(err or out)[-500:]}"
    if not media:
        rc, out, err = run(YTDLP + auth_args(cfg) + ["--no-playlist", "--max-filesize", cfg["max_filesize"],
                                                       "-o", str(work / "video.%(ext)s"), url], timeout=900)
        media = list_media(work)
        if not media:
            errtxt += f"\nyt-dlp rc={rc}: {(err or out)[-500:]}"
    return media, errtxt


# ---------------------------------------------------------------- OCR
def clean_ocr(text):
    lines = []
    for l in text.splitlines():
        l = l.strip()
        if len(re.sub(r"[\W_]", "", l)) >= 3:
            lines.append(l)
    return lines


def ocr_image(path, cfg, tess):
    p = path
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}:
        ff = find_binary("ffmpeg")
        conv = path.with_suffix(".png")
        if ff:
            run([ff, "-y", "-loglevel", "error", "-i", str(path), str(conv)], timeout=60)
            if conv.exists():
                p = conv
    rc, out, err = run([tess, str(p), "stdout", "-l", cfg["ocr_lang"], "--psm", str(cfg["ocr_psm"])], timeout=120)
    if rc != 0:
        warn(f"tesseract failed on {path.name}: {err[-200:]}")
        return []
    return clean_ocr(out)


def video_duration(path):
    fp = find_binary("ffprobe")
    if not fp:
        return None
    rc, out, _ = run([fp, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], timeout=30)
    try:
        return float(out.strip())
    except Exception:
        return None


def video_frames_ocr(path, work, cfg, tess, seen):
    ff = find_binary("ffmpeg")
    if not ff:
        warn("ffmpeg not found; skipping video frame OCR")
        return []
    fdir = work / f"frames_{path.stem}"
    fdir.mkdir(exist_ok=True)
    run([ff, "-y", "-loglevel", "error", "-i", str(path), "-vf",
         f"fps=1/{cfg['frame_interval_seconds']},scale=1280:-2", "-frames:v",
         str(cfg["max_frames_per_video"]), "-q:v", "3", str(fdir / "%03d.jpg")], timeout=300)
    new_lines = []
    for f in sorted(fdir.glob("*.jpg"), key=natural_key):
        for l in ocr_image(f, cfg, tess):
            k = re.sub(r"\W", "", l.lower())
            if k and k not in seen:
                seen.add(k)
                new_lines.append(l)
    shutil.rmtree(fdir, ignore_errors=True)
    return new_lines


# ---------------------------------------------------------------- transcription
_model = None


def transcribe(path, cfg):
    global _model
    from faster_whisper import WhisperModel
    if _model is None:
        MODELS.mkdir(exist_ok=True)
        _model = WhisperModel(cfg["whisper_model"], device="cpu", compute_type="int8",
                              download_root=str(MODELS))
    segs, info = _model.transcribe(str(path), vad_filter=True, language=cfg.get("whisper_language"))
    text = " ".join(s.text.strip() for s in segs).strip()
    return text, info.language


# ---------------------------------------------------------------- cleanup
def rmtree_retry(p):
    for _ in range(4):
        shutil.rmtree(p, ignore_errors=True)
        if not Path(p).exists():
            return True
        time.sleep(1)
    return False


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--caption-only", action="store_true")
    ap.add_argument("--no-transcribe", action="store_true")
    ap.add_argument("--no-video-ocr", action="store_true")
    ap.add_argument("--keep-media", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--force-long", action="store_true")
    ap.add_argument("--no-delay", action="store_true")
    a = ap.parse_args()

    cfg = load_config()
    norm = normalize_url(a.url)
    if not norm:
        print("RESULT status=failed reason=bad_url (expected instagram.com/p|reel|tv/<code>)")
        return BADURL
    url, code = norm

    free_gb = shutil.disk_usage(ROOT).free / 1e9
    if free_gb < cfg["min_free_disk_gb"]:
        print(f"RESULT status=failed reason=low_disk free={free_gb:.1f}GB (min {cfg['min_free_disk_gb']}GB). "
              "Run scripts/cleanup.py and tell the user.")
        return DISK

    out_dir = DATA / code
    meta_path = out_dir / "meta.json"
    if meta_path.exists() and not a.force:
        try:
            old = json.loads(meta_path.read_text(encoding="utf-8"))
            if old.get("status") == "complete" or (old.get("status") == "caption_only" and a.caption_only):
                print(f"RESULT status=already_processed post={code} dir=data/{code}")
                return OK
        except Exception:
            pass

    work = TMP / code
    TMP.mkdir(exist_ok=True)
    if work.exists():
        rmtree_retry(work)
    out_dir.mkdir(parents=True, exist_ok=True)

    code_exit = OK
    errtxt = ""
    steps = {}
    caption = ocr_text = transcript = ""
    kept = False
    lang = None
    try:
        info, e1 = get_metadata(url, cfg)
        errtxt += e1
        caption = info["caption"]
        steps["metadata"] = bool(caption or info["media_count"])

        media = []
        if not a.caption_only and (info["media_count"] or not e1):
            media, e2 = download(url, work, cfg)
            errtxt += "\n" + e2
            steps["download"] = bool(media)

        images = [m for m in media if m.suffix.lower() in IMG]
        videos = [m for m in media if m.suffix.lower() in VID]
        tess = find_binary("tesseract")
        if (images or videos) and not tess:
            warn("tesseract not found: OCR skipped (run scripts/doctor.py)")

        ocr_sections = []
        if images and tess:
            for i, img in enumerate(images, 1):
                lines = ocr_image(img, cfg, tess)
                if lines:
                    ocr_sections.append(f"--- slide {i} ---\n" + "\n".join(lines))
            steps["image_ocr"] = True

        seen = set()
        transcripts = []
        for vi, v in enumerate(videos, 1):
            dur = video_duration(v)
            if dur and dur > cfg["max_video_minutes"] * 60 and not a.force_long:
                warn(f"{v.name} is {dur/60:.0f} min > max_video_minutes; skipped heavy processing "
                     "(use --force-long to override)")
                continue
            if tess and not a.no_video_ocr:
                lines = video_frames_ocr(v, work, cfg, tess, seen)
                if lines:
                    ocr_sections.append(f"--- video {vi} on-screen text ---\n" + "\n".join(lines))
                steps["video_ocr"] = True
            if not a.no_transcribe:
                try:
                    t, lang = transcribe(v, cfg)
                    if t:
                        transcripts.append(t if len(videos) == 1 else f"--- video {vi} ---\n{t}")
                    steps["transcribe"] = True
                except Exception as e:  # noqa: BLE001
                    warn(f"transcription failed for {v.name}: {type(e).__name__}: {e}")

        ocr_text = "\n\n".join(ocr_sections)
        transcript = "\n\n".join(transcripts)

        if a.keep_media and work.exists():
            dest = TMP / "keep" / code
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                rmtree_retry(dest)
            shutil.move(str(work), str(dest))
            kept = True

        status = "complete"
        if a.caption_only:
            status = "caption_only"
        elif not media:
            status = "partial"
        if not (caption or ocr_text or transcript):
            status = "failed"
            code_exit = classify(errtxt) if errtxt.strip() else OTHER

        for name, text in (("caption.txt", caption), ("ocr.txt", ocr_text), ("transcript.txt", transcript)):
            f = out_dir / name
            if text:
                atomic_write(f, text)
            elif f.exists():
                f.unlink()

        atomic_write(meta_path, json.dumps({
            "url": url, "shortcode": code, "status": status, "author": info["author"],
            "date": info["date"], "media_count": info["media_count"], "kinds": info["kinds"],
            "whisper_language": lang, "steps": steps, "warnings": warnings,
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "last_error": errtxt.strip()[-800:] if status in ("failed", "partial") else "",
        }, indent=2, ensure_ascii=False))
    finally:
        if work.exists():
            if not rmtree_retry(work):
                print(f"[warn] could not delete {work}; run scripts/cleanup.py", file=sys.stderr)

    # ---- report
    print("=== RESULT ===")
    print(f"status: {status}   post: {code}   author: {info['author'] or '?'}   media: {info['media_count']} {sorted(set(info['kinds']))}")
    for name, text in (("caption.txt", caption), ("ocr.txt", ocr_text), ("transcript.txt", transcript)):
        print(f"{name}: {len(text)} chars" if text else f"{name}: (empty)")
    print(f"dir: data/{code}")
    if warnings:
        print("warnings: " + " | ".join(warnings))
    if kept:
        print(f"MEDIA KEPT in tmp/keep/{code} - delete it with scripts/cleanup.py when done!")
    if status == "failed":
        print("error detail (tail):\n" + errtxt.strip()[-700:])
        hints = {AUTH: "login/cookies problem -> STOP the batch, ask user to refresh cookies.txt",
                 RATE: "rate limited -> stop, wait 10+ min, increase delays in config.json",
                 GONE: "post deleted/private -> log with linkq.py fail and move on",
                 OTHER: "unknown -> see AGENTS.md failure handling / self-improvement"}
        print(f"exit-hint: {hints.get(code_exit, '')}")
    elif status == "partial":
        print("hint: caption ok but media download failed; usually fine if caption lists the tools.")

    if not a.no_delay and network_used and code_exit not in (GONE, BADURL, AUTH):
        lo, hi = cfg["sleep_between_posts"]
        time.sleep(random.uniform(lo, hi))
    return code_exit


if __name__ == "__main__":
    sys.exit(main())
