"""Link queue manager. The agent should use this instead of hand-editing text files.

  python scripts/linkq.py stats
  python scripts/linkq.py next [N]
  python scripts/linkq.py add <url> [<url> ...]      (or: add --file urls.txt, or: add - < stdin)
  python scripts/linkq.py done <url> [note...]
  python scripts/linkq.py fail <url> <reason...>
  python scripts/linkq.py requeue-failed [--contains TEXT]
"""
import sys
from datetime import datetime

from rc_common import ROOT, atomic_write, normalize_url

PENDING = ROOT / "links.txt"
DONE = ROOT / "done.txt"
FAILED = ROOT / "failed.txt"


def _read(p):
    if not p.exists():
        return []
    return [l.rstrip("\n") for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _code(line):
    r = normalize_url(line.split("\t")[0])
    return r[1] if r else None


def _write(p, lines):
    atomic_write(p, "\n".join(lines) + ("\n" if lines else ""))


def pending_urls():
    out = []
    for l in _read(PENDING):
        if l.lstrip().startswith("#"):
            continue
        r = normalize_url(l.split()[0])
        if r:
            out.append(r[0])
    return out


def add_urls(raw_urls):
    known = set()
    for p in (PENDING, DONE, FAILED):
        for l in _read(p):
            c = _code(l)
            if c:
                known.add(c)
    new, dup, bad = [], 0, 0
    for u in raw_urls:
        r = normalize_url(u)
        if not r:
            bad += 1
            continue
        if r[1] in known:
            dup += 1
            continue
        known.add(r[1])
        new.append(r[0])
    if new:
        _write(PENDING, _read(PENDING) + new)
    return len(new), dup, bad


def mark(url, dest, extra):
    r = normalize_url(url)
    if not r:
        print(f"not an instagram post url: {url}")
        return 1
    code = r[1]
    pend = _read(PENDING)
    left = [l for l in pend if _code(l) != code]
    _write(PENDING, left)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = _read(dest)
    lines = [l for l in lines if _code(l) != code]
    lines.append(f"{r[0]}\t{stamp}\t{extra}".rstrip())
    _write(dest, lines)
    print(f"marked {code} -> {dest.name}; pending left: {len(left)}")
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "stats":
        print(f"pending: {len(pending_urls())}\ndone: {len(_read(DONE))}\nfailed: {len(_read(FAILED))}")
        return 0
    if cmd == "next":
        n = int(rest[0]) if rest else 5
        for u in pending_urls()[:n]:
            print(u)
        return 0
    if cmd == "add":
        if rest[:1] == ["--file"]:
            raw = open(rest[1], encoding="utf-8").read().split()
        elif rest[:1] == ["-"]:
            raw = sys.stdin.read().split()
        else:
            raw = rest
        n, d, b = add_urls(raw)
        print(f"added {n}, duplicates skipped {d}, not-a-post {b}")
        return 0
    if cmd == "done":
        return mark(rest[0], DONE, " ".join(rest[1:]))
    if cmd == "fail":
        return mark(rest[0], FAILED, " ".join(rest[1:]))
    if cmd == "requeue-failed":
        needle = rest[1].lower() if rest[:1] == ["--contains"] and len(rest) > 1 else None
        keep, back = [], []
        for l in _read(FAILED):
            (back if (needle is None or needle in l.lower()) else keep).append(l)
        _write(FAILED, keep)
        urls = [l.split("\t")[0] for l in back]
        n, _, _ = add_urls(urls)
        print(f"requeued {n} failed links")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
