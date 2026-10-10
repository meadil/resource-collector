# Resource Collector

**Turn your saved Instagram posts into a catalog of tools.**

You save posts showing tools you might use. This downloads each one, pulls the
text out of the image or video, and writes down what the tool is called and
where to find it — into a single `tools.md` file.

Media is deleted immediately after the text is extracted, so nothing piles up.

---

## The problem

Tool recommendations live inside images and videos. You scroll past them, save
them "for later," and never look again. Three months later you have 400 saved
posts and no idea what any of them were.

This turns that backlog into a searchable list.

---

## How it works

```
saved_posts.json  (your Meta data export)
        ↓
  pull out all the post links
        ↓
  download each post            ← image or video, goes to tmp/
        ↓
  read the text out of it       ← OCR for images, Whisper for video audio
        ↓
  find the tool name + link
        ↓
  append to tools.md
        ↓
  delete the media
```

---

## Setup (Windows)

1. Install Python 3.10+ and [OpenCode](https://opencode.ai):
   ```powershell
   winget install Python.Python.3.12
   ```

2. Create the environment and install dependencies:
   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   ```

3. **Instagram cookies** — needed to download most saved posts:
   - Log into instagram.com in a browser (a secondary account is safer)
   - Install a cookie export extension ("Get cookies.txt LOCALLY")
   - Export cookies for instagram.com in Netscape format
   - Save as `cookies.txt` in this folder (already gitignored — keep it private)
   - Alternative: set `"cookies_from_browser": "firefox"` in `config.json`

4. Copy your Meta export files (`saved_posts.json`) into `input/`.

---

## Run

Two ways, depending on whether you want an agent or just the scripts.

### With an agent

Start OpenCode in this folder and ask for what you want in plain language:
process the next batch, add specific links, check the queue, work out why
something failed.

> **Note:** the original slash commands (`/batch`, `/improve`, `/status`) lived
> in an `.opencode/` folder that isn't in this repository. Describe the task in
> words instead, or run the scripts directly below.

### Without an agent

```powershell
$py = ".\.venv\Scripts\python.exe"

& $py scripts\extract_links.py --dry-run   # preview the link list
& $py scripts\extract_links.py             # build links.txt
& $py scripts\fetch.py <url>               # fetch one post
& $py scripts\catalog.py stats             # catalog stats
& $py scripts\cleanup.py                   # remove leftover media
```

Start with three posts, look at what comes out, then scale up.

---

## Scripts

| File | What it does |
|------|--------------|
| `scripts/fetch.py` | Downloads a post, extracts text, cleans up |
| `scripts/extract_links.py` | Reads your export, builds the work queue |
| `scripts/catalog.py` | Writes and manages the tool catalog |
| `scripts/linkq.py` | Queue status and retry logic |
| `scripts/doctor.py` | Checks that everything is installed correctly |
| `scripts/cleanup.py` | Deletes leftover media and cached models |
| `scripts/rc_common.py` | Shared helpers |

---

## Storage

- Media → `tmp/`, deleted after every post
- `data/` → small text files only
- `models/` → Whisper model cache (~150 MB); `cleanup.py --models` removes it

---

## Caveats

- Automated access is against Instagram's terms. Keep it personal, slow, and
  small-batch. This is a personal tool, not a scraper.
- It was built without live Instagram access, so expect to debug the pipeline on
  first run. The scripts are the part that's tested; the wiring may not be.
- Pinterest can be added later as another fetcher — pins usually link straight to
  the tool's site.

---

`AGENTS.md` has the full technical reference; `LEARNINGS.md` has the gotchas.