"""Build links.txt from the Meta 'Download your information' export.

Scans every .json/.html/.txt in input/ (or paths you pass), finds Instagram post/reel URLs
with a regex (so it works no matter how Meta structures the JSON), dedupes, and appends new
ones to links.txt.

  python scripts/extract_links.py                 # scan input/
  python scripts/extract_links.py path\\to\\saved_posts.json --oldest-first
  python scripts/extract_links.py --dry-run
"""
import argparse
import sys
from pathlib import Path

from rc_common import INPUT, POST_RE, normalize_url
from linkq import add_urls, PENDING


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--oldest-first", action="store_true",
                    help="Meta usually lists newest first; this reverses the order")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    files = []
    if a.paths:
        files = [Path(p) for p in a.paths]
    else:
        files = [p for p in sorted(INPUT.rglob("*")) if p.suffix.lower() in (".json", ".html", ".htm", ".txt")]
    if not files:
        print("No input files found. Put the Meta export files in input/ first.")
        return 1

    urls, seen = [], set()
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace").replace("\\/", "/")
        found = 0
        for m in POST_RE.finditer(text):
            r = normalize_url(m.group(0))
            if r and r[1] not in seen:
                seen.add(r[1])
                urls.append(r[0])
                found += 1
        print(f"{f.name}: {found} new unique post links")

    if a.oldest_first:
        urls.reverse()
    reels = sum("/reel/" in u for u in urls)
    print(f"total unique: {len(urls)}  (reels: {reels}, posts/carousels: {len(urls) - reels})")
    if a.dry_run:
        return 0
    n, d, b = add_urls(urls)
    print(f"appended {n} to {PENDING.name} (already known: {d})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
