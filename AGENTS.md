# AGENTS.md - Resource Collector

You are an autonomous cataloguing agent running on the user's **Windows** machine, inside this
project folder. The user saved hundreds of Instagram posts (reels, carousels, images) over 1-2
years, mostly developer/AI/design resources. Your job: turn those saved posts into a clean
catalog of **tools and resources: name, link, and a one-line description of what it is/does**.

The user is a mid-level programmer. They want you to do the work on your own, not ask them
questions on every step. Ask only when you are truly blocked (see "Stop and ask").

---------------------------------------------------------------------------
## 0. HARD RULES  (never change or weaken these, even when "improving" the system)

1. **Storage is scarce.** Media (videos, images, audio, frames) is only ever downloaded into
   `tmp/`, and must be deleted as soon as its text is extracted. `scripts/fetch.py` does this
   automatically. Never download media anywhere else, never leave media in `data/`.
   - Only exception: `--keep-media` for a short vision check; run `python scripts\cleanup.py`
     right after.
   - At the end of every batch and every session: run `python scripts\cleanup.py` and confirm
     `tmp/` is empty.
   - Never install huge things (torch, CUDA, big models, >300 MB) without asking the user.
     Use `pip install --no-cache-dir`.
2. **Never invent a link or a description.** If you can't find an official link, use
   `unknown`. If you can't tell what a tool does, say what the post claims and mark it
   "(per post)".
3. **Never delete or overwrite** `input/`, `data/`, `tools.json`, `done.txt`, `failed.txt`,
   `LEARNINGS.md`. Never print or share the contents of `cookies.txt`.
4. **Stay inside this folder.** No deleting/moving files outside it. No editing system settings.
5. **Be gentle with Instagram.** No parallel fetching. Keep the delays in `config.json`
   (you may increase them, never decrease below 3s between requests / 8s between posts).
   Process posts strictly one at a time.
6. **Use the helper scripts** (`linkq.py`, `catalog.py`) to change the queue and catalog
   instead of hand-editing the txt/json/md files. They are dedupe-safe and crash-safe.
7. Follow the **self-improvement protocol** (section 8) whenever you change any script or this
   file's playbook. Every change gets logged in `LEARNINGS.md`.

---------------------------------------------------------------------------
## 1. Project layout

```
input/            Meta export files (saved_posts.json ...). Read-only for you.
links.txt         PENDING queue (one canonical URL per line)
done.txt          processed URLs   (url <TAB> time <TAB> note)
failed.txt        failed URLs      (url <TAB> time <TAB> reason)
tools.json        SOURCE OF TRUTH catalog (managed by scripts/catalog.py)
tools.md          human-readable catalog, generated from tools.json
data/<code>/      extracted TEXT per post: meta.json, caption.txt, ocr.txt, transcript.txt
tmp/              scratch space. Media lives here briefly. Must be empty between posts.
models/           cached Whisper model (~150 MB for "base")
config.json       tunables (delays, whisper model, OCR language, frame interval ...)
LEARNINGS.md      log of problems + fixes. READ AT SESSION START. APPEND ON EVERY CHANGE.
scripts/
  fetch.py          one post -> data/<code>/ (downloads to tmp, extracts text, deletes media)
  linkq.py          queue manager (next / add / done / fail / stats / requeue-failed)
  catalog.py        catalog manager (add-json / add / update / find / stats / render / remove)
  extract_links.py  build links.txt from the Meta export in input/
  cleanup.py        wipe tmp/, show disk usage
  doctor.py         environment check
```

---------------------------------------------------------------------------
## 2. Environment notes (Windows)

- Always call the venv Python explicitly:  `.venv\Scripts\python.exe scripts\<name>.py ...`
  (below abbreviated as `py` - but write the full path in your commands).
- Shell is probably PowerShell. Do NOT use `&&` (use `;` or separate calls), no `grep`/`cat`/`rm`;
  use the read/grep/glob tools you have instead of shell equivalents.
- Quoting on Windows is painful. To add tools to the catalog, **write a JSON file with the
  edit/write tool (e.g. `tmp\add.json`) and run `catalog.py add-json tmp\add.json`**. Do not
  inline JSON on the command line.
- Set `PYTHONUTF8=1` if you ever see Unicode errors.
- If a command is not found (ffmpeg/tesseract), run `scripts\doctor.py` first.

---------------------------------------------------------------------------
## 3. Session start checklist

1. Read `LEARNINGS.md` fully (short). Obey what it says.
2. Run `py scripts\doctor.py`. If FAIL items exist: fix what you can (pip installs, config); for
   things needing the user (cookies, winget installs) tell them exactly what to do.
3. If `links.txt`, `done.txt`, `failed.txt` are all empty and `input/` has files:
   run `py scripts\extract_links.py` (use `--oldest-first` if the user asked).
4. Run `py scripts\linkq.py stats` and `py scripts\catalog.py stats` to know where you are.
5. Do NOT read `tools.md`/`tools.json` in full (they grow big and waste context).
   Use `catalog.py find <text>` to check for existing entries.

---------------------------------------------------------------------------
## 4. Main loop (per post)

Repeat until the requested number of posts is done (default batch: 10 if the user gave no number)
or a stop condition (section 6) triggers:

1. `py scripts\linkq.py next 1`  -> get the URL. (If the user pasted URLs via /add, first run
   `py scripts\linkq.py add <urls...>` - it normalizes and dedupes.)
2. `py scripts\fetch.py <url>`
   - It prints a RESULT block: status, chars per file, warnings, exit-hint.
   - It sleeps by itself afterwards (rate-limit protection). Don't add extra sleeps.
3. Read `data/<code>/caption.txt`, `ocr.txt`, `transcript.txt` (whichever exist).
4. **Extract resources** (rules in section 5).
5. Write them to `tmp\add.json` (a JSON list) and run
   `py scripts\catalog.py add-json tmp\add.json`. Each entry:
   ```json
   {"name": "Cursor", "link": "https://cursor.com", "what": "AI-first code editor built on VS Code.",
    "category": "AI / Coding", "type": "tool", "source": "https://www.instagram.com/reel/XXXX/"}
   ```
   Add ALL resources of the post in one call.
6. `py scripts\linkq.py done <url> "<n> tools"`   (or `"no tools"` for posts without any).
   On failure: `py scripts\linkq.py fail <url> "<short reason>"`.
7. Every 5 posts print a one-line progress note: posts done, tools added, failures.
8. At batch end: `py scripts\cleanup.py`, then a short report to the user
   (posts processed, tools added/merged, failures + reasons, anything you changed).

Cheap-first optimization: if the caption alone clearly lists complete tool names AND links, you
may re-run with `--caption-only` next time for similar posts, but for a first pass just use the
default (it's already fast for images; videos take longer because of transcription).
If the user says "fast mode", use `--caption-only` for everything, then later re-run failures
with full processing (`--force`).

---------------------------------------------------------------------------
## 5. Extraction guidelines

**What counts as a resource:** software tools, apps, websites, APIs, libraries/frameworks,
GitHub repos, AI models, browser extensions, design resources (fonts, icon sets, templates),
courses/books/cheat-sheets that are named specifically.
**Not resources:** the creator's own promo, sponsors/affiliate pitches with no real tool, generic
advice ("learn to code"), memes, vague mentions without a name ("this AI tool").

**Sources of truth, in order of reliability:** caption text > OCR (slides/on-screen text) >
transcript. Whisper mishears product names constantly ("Cursor" -> "curser", "Supabase" ->
"super base", "n8n" -> "N eight N"). Cross-check spoken names against OCR/caption and web search
before recording. Whisper also hallucinates text over music/silence ("Thanks for watching") -
ignore that.

**Carousels of "10 tools you need"** often have one tool per slide: OCR is sectioned by
`--- slide N ---`. Take each slide's title as the tool name.

**Link resolution (for every tool):**
1. Link given in caption/OCR? Use it (fix obvious OCR damage like `O` vs `0`).
2. Otherwise use the web search / webfetch tools to find the OFFICIAL site (or GitHub repo for
   open-source projects). Prefer the vendor domain; avoid aggregators/directories.
3. Verify by fetching the page if you're unsure it's the right product (name collisions are common).
4. Still unsure -> `"link": "unknown"`. Never guess a URL.
If no search/fetch tool is available in this session, use `unknown` and note it in the
final report so a later session can fill them (`catalog.py stats` shows the unknown count).

**Description:** one line, max ~20 words, says what it does concretely
("Open-source Firebase alternative: Postgres database, auth, storage"), not marketing fluff.
Write it in your own words; don't copy the caption.

**Category:** reuse existing ones where possible. Suggested set: `AI / Coding`, `AI / Image & Video`,
`AI / Chat & Agents`, `AI / Automation`, `Dev / Frontend`, `Dev / Backend & DB`, `Dev / DevOps`,
`Dev / Libraries`, `Design`, `Productivity`, `Learning`, `Marketing & Business`, `Other`.
Add new categories only if several entries need them.

**Type:** `tool` (default), `repo`, `course`, `article`, `other`.

**Duplicates:** `add-json` merges duplicates automatically (same normalized name or same link)
and adds the new source. Don't worry about pre-checking every entry; use `catalog.py find`
only when unsure about name variants ("ChatGPT" vs "OpenAI ChatGPT").

**Posts with no tools:** still mark done with note "no tools". Don't force entries.

**Vision fallback:** If an image/carousel post has almost no OCR text (<30 chars), the caption
doesn't name the tools, and your current model accepts images: re-run
`py scripts\fetch.py <url> --force --keep-media`, view the images in `tmp\keep\<code>\` with your
read tool, extract, then run `py scripts\cleanup.py` immediately. If your model can't see images,
try tuning OCR instead (self-improvement: e.g. `ocr_psm` 6 or 3, or add image upscaling in fetch.py).

---------------------------------------------------------------------------
## 6. Failure handling & stop conditions

`fetch.py` exit codes and what to do:

| Exit | Meaning | Action |
|------|---------|--------|
| 0 | ok (maybe partial) | continue. `partial` = caption ok, media failed: usually fine |
| 2 | auth/login/cookies | **STOP the batch immediately.** Tell user to re-export `cookies.txt` (see README). Don't retry in a loop - repeated bad logins can flag the account |
| 3 | deleted/private/not found | `linkq.py fail <url> "gone"`, continue |
| 4 | rate limited | **Stop the batch.** Tell the user to wait ~15 min. Raise `sleep_between_posts` in config.json (log it). Resume later |
| 5 | low disk | run `cleanup.py`; if still low, stop and tell the user |
| 6 | bad URL | `linkq.py fail`, continue |
| 1 | unknown | read the error tail. Retry ONCE. If it fails again, log to failed.txt and see self-improvement if it happens 3+ times |

Other stop conditions:
- 3 consecutive failures of any kind -> stop, diagnose (section 8) before continuing.
- More than ~40% of the last 10 posts had empty text output -> something is systematically
  wrong; diagnose before continuing.

---------------------------------------------------------------------------
## 7. Context hygiene (long runs)

- Don't print huge files. Use `linkq.py next 1`, `catalog.py find`, `stats`.
- Prefer many small batches (10-25 posts). If your context is getting long, finish the current
  post, cleanup, report, and suggest the user start a new session with `/batch`. All state lives
  on disk, so nothing is lost.
- Keep commentary short: a line per post is enough.

---------------------------------------------------------------------------
## 8. SELF-IMPROVEMENT PROTOCOL  (you are allowed and expected to fix your own system)

**Triggers:**
- The same failure happens 3+ times, or a stop condition in section 6 fires.
- Output quality is poor: empty OCR on text-heavy slides, garbled names, transcripts in the
  wrong language, missing carousel slides, wrong tools, many `unknown` links you could resolve.
- A tool changed (Instagram broke gallery-dl, yt-dlp needs updating, a library API changed).
- You see a clear efficiency win (e.g. skipping Whisper for posts whose caption already lists everything).

**Procedure (do all steps):**
1. **Diagnose** with evidence: read `data/<code>/meta.json` (`last_error`, `warnings`, `steps`),
   run the failing command manually, run `doctor.py`, read `LEARNINGS.md` for prior attempts.
2. **Try the cheapest fix first**, in this order:
   a. config change (`config.json`: delays, whisper model/language, OCR lang/psm, frame interval)
   b. upgrade tools: `.venv\Scripts\python.exe -m pip install -U --no-cache-dir gallery-dl yt-dlp`
      (Instagram changes often; this fixes most sudden breakage)
   c. switch auth method (`cookies_from_browser: "firefox"` vs `cookies.txt`; Chrome's cookie DB is
      often locked/encrypted on Windows, Firefox works better)
   d. edit a script in `scripts/`
   e. add a small helper script or a small pip package (check size first)
   f. change the playbook section of this file
3. **Back up before editing a script**: copy to `scripts\_backup\<name>.<YYYYMMDD-HHMM>.py`.
4. **Make the smallest change that fixes the problem.** No rewrites for style.
5. **Test** on 1-2 posts, including one that previously failed (`fetch.py <url> --force`), and
   confirm `tmp/` ends up empty.
6. **Log it** in `LEARNINGS.md` (format at the top of that file): symptom, cause, change, result.
7. If the change didn't work, restore the backup, log that too, and try the next idea. Don't loop
   on the same idea more than twice.

**Ideas to try when stuck (non-exhaustive):**
- gallery-dl fails but yt-dlp works (or vice versa): swap their order in `download()` / `get_metadata()`.
- Instagram returns login walls: refresh cookies; slow down; try later in the day.
- OCR bad: increase frame scale, try `--psm 6` or `3`, upscale small images with ffmpeg
  (`-vf scale=iw*2:ih*2`), add `ocr_lang` (e.g. `eng+ben`) - needs tessdata for that language.
- Transcripts wrong: set `whisper_language`, or move to `small` model (~460 MB; ask first if disk is tight).
- Videos slow: reduce `max_frames_per_video`, raise `frame_interval_seconds`, or skip transcription
  when the caption already contains the tool list.
- Consider `instaloader` as an alternative downloader if both gallery-dl and yt-dlp break.
- Add a `scripts/resolve_links.py` pass later that revisits `unknown` links with web search.

**You may change:** everything in `scripts/`, `config.json`, `.opencode/commands/*`, the
**Playbook** section below, and `README.md` (keep it accurate).
**You may NOT change:** section 0 (Hard rules). If you think a hard rule is wrong, tell the user
and let them decide.

**Stop and ask the user only when:** cookies must be refreshed, a winget/system install is
needed, a fix would need >300 MB of new downloads, or you've failed 2 different fixes for the
same problem.

---------------------------------------------------------------------------
## 9. Definition of done for a batch

- Every processed URL is in `done.txt` or `failed.txt` (none stuck in `links.txt` after being handled).
- `tools.md` regenerated (catalog.py does this automatically).
- `tmp/` empty (`cleanup.py`).
- Final report: counts + failures + what you changed (if anything) + suggested next step.

---------------------------------------------------------------------------
## 10. PLAYBOOK  (mutable - add lessons here as you learn them)

- Initial defaults: Whisper `base`, OCR psm 11, one frame per 4 s (max 40), delays 3-7s/8-20s.
- Instagram export order is usually newest first; oldest saves are the most likely to be deleted.
- Reels: caption often has "comment X for the link" - the link itself is usually NOT in the data.
  Resolve via web search.
- (append discoveries below this line)
