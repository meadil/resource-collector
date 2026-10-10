"""Tool catalog manager. tools.json is the source of truth; tools.md is generated.

  python scripts/catalog.py add-json tmp/add.json     # preferred: file with a JSON list of entries
  python scripts/catalog.py add --name X --link URL --what "..." --category AI --source POST_URL
  python scripts/catalog.py update --name X [--link ..] [--what ..] [--category ..] [--type ..]
  python scripts/catalog.py find <text>
  python scripts/catalog.py stats
  python scripts/catalog.py render
  python scripts/catalog.py remove --name X

Entry fields: name (required), link ("unknown" if not found), what, category, type
(tool|repo|course|article|other), source (instagram post url; can be a list).
Duplicates (same normalized name OR same link) are merged: sources are combined and empty
fields are filled in.
"""
import argparse
import json
import re
import sys
from datetime import date
from urllib.parse import urlparse

from rc_common import ROOT, atomic_write

DB = ROOT / "tools.json"
MD = ROOT / "tools.md"


def load():
    if DB.exists():
        return json.loads(DB.read_text(encoding="utf-8"))
    return []


def save(items):
    atomic_write(DB, json.dumps(items, indent=2, ensure_ascii=False))
    render(items)


def nkey(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def lkey(link):
    if not link or link.strip().lower() in ("unknown", "n/a", ""):
        return None
    u = urlparse(link if "://" in link else "https://" + link)
    host = u.netloc.lower().removeprefix("www.")
    return host + u.path.rstrip("/").lower()


def upsert(items, e):
    name = (e.get("name") or "").strip()
    if not name:
        return "skipped(no name)"
    link = (e.get("link") or "unknown").strip()
    src = e.get("source") or []
    if isinstance(src, str):
        src = [src]
    entry = {
        "name": name,
        "link": link,
        "what": (e.get("what") or "").strip(),
        "category": (e.get("category") or "Other").strip(),
        "type": (e.get("type") or "tool").strip(),
        "sources": [s for s in src if s],
        "added": str(date.today()),
    }
    nk, lk = nkey(name), lkey(link)
    for it in items:
        if nkey(it["name"]) == nk or (lk and lkey(it["link"]) == lk):
            for s in entry["sources"]:
                if s not in it["sources"]:
                    it["sources"].append(s)
            if lkey(it["link"]) is None and lk:
                it["link"] = link
            if not it.get("what") and entry["what"]:
                it["what"] = entry["what"]
            if it.get("category", "Other") == "Other" and entry["category"] != "Other":
                it["category"] = entry["category"]
            return "merged"
    items.append(entry)
    return "added"


def render(items=None):
    items = load() if items is None else items
    by = {}
    for it in items:
        by.setdefault(it.get("category", "Other"), []).append(it)
    out = ["# Tools & Resources Catalog", "",
           f"_{len(items)} entries. Generated from tools.json by scripts/catalog.py. Do not edit by hand._", ""]
    for cat in sorted(by, key=str.lower):
        out.append(f"## {cat}")
        out.append("")
        for it in sorted(by[cat], key=lambda x: x["name"].lower()):
            link = it["link"]
            l = f"[{link}]({link})" if link.startswith("http") else link
            n = len(it.get("sources", []))
            src = it["sources"][0] if n else ""
            extra = f" · saved from {n} post{'s' if n != 1 else ''}" + (f" ([first]({src}))" if src else "")
            out.append(f"- **{it['name']}** ({it.get('type', 'tool')}) - {it.get('what', '')}  \n  {l}{extra}")
        out.append("")
    atomic_write(MD, "\n".join(out))


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("cmd", nargs="?")
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--name")
    ap.add_argument("--link")
    ap.add_argument("--what")
    ap.add_argument("--category")
    ap.add_argument("--type")
    ap.add_argument("--source")
    a = ap.parse_args(argv)
    items = load()

    if a.cmd == "add-json":
        path = a.rest[0]
        raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8-sig").read()
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        res = [upsert(items, e) for e in data]
        save(items)
        print(f"added {res.count('added')}, merged {res.count('merged')}, skipped {len(res) - res.count('added') - res.count('merged')}; total {len(items)}")
        for e, r in zip(data, res):
            print(f"  {r}: {e.get('name')}")
        return 0
    if a.cmd == "add":
        r = upsert(items, {"name": a.name, "link": a.link, "what": a.what,
                           "category": a.category, "type": a.type, "source": a.source})
        save(items)
        print(f"{r}: {a.name}; total {len(items)}")
        return 0
    if a.cmd == "update":
        for it in items:
            if nkey(it["name"]) == nkey(a.name):
                for k in ("link", "what", "category", "type"):
                    v = getattr(a, k)
                    if v:
                        it[k] = v
                save(items)
                print("updated", it["name"])
                return 0
        print("not found")
        return 1
    if a.cmd == "remove":
        n0 = len(items)
        items = [i for i in items if nkey(i["name"]) != nkey(a.name)]
        save(items)
        print(f"removed {n0 - len(items)}")
        return 0
    if a.cmd == "find":
        q = " ".join(a.rest).lower()
        hits = [i for i in items if q in i["name"].lower() or q in i.get("what", "").lower() or q in i["link"].lower()]
        for i in hits[:20]:
            print(f"- {i['name']} | {i['link']} | {i.get('what', '')[:80]}")
        print(f"({len(hits)} matches)")
        return 0
    if a.cmd == "stats":
        cats = {}
        unk = 0
        for i in items:
            cats[i.get("category", "Other")] = cats.get(i.get("category", "Other"), 0) + 1
            unk += lkey(i["link"]) is None
        print(f"total: {len(items)}  unknown-link: {unk}")
        for c, n in sorted(cats.items(), key=lambda x: -x[1]):
            print(f"  {c}: {n}")
        return 0
    if a.cmd == "render":
        render()
        print("rendered tools.md")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
