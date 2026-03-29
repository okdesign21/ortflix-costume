#!/usr/bin/env python3
"""
fix_audio_lang.py — Radarr Custom Script + bulk fixer
Automatically tags missing/und audio language metadata on imported movies.

── As a Radarr Custom Script ──────────────────────────────────────────────────
Radarr → Settings → Connect → Custom Script
  Path: /path/to/fix_audio_lang.py
  On Import: ✓   On Upgrade: ✓

  Language is read from radarr_movie_originallanguage (set by Radarr automatically).
  No hardcoding needed — works correctly for any future movie, any language.

── As a one-off bulk fix ──────────────────────────────────────────────────────
    python3 fix_audio_lang.py           # dry run
    python3 fix_audio_lang.py --apply   # apply to all files in MOVIES_DIR

  In bulk mode, language defaults to 'eng' (since the library was already
  bulk-fixed with per-file language data; this catches any newly added stragglers).

Requirements:
    sudo apt install mkvtoolnix ffmpeg
"""
import subprocess, os, sys, json, re, shutil

# telegram_post is only available when running as a Radarr script (radarr_utils on PATH)
try:
    from radarr_utils import telegram_post
except ImportError:
    def telegram_post(text): pass  # no-op in bulk mode

MOVIES_DIRS       = [
    "/movies",      # host: /home/media/ortflix/Movies
    "/movies-hdr",  # host: /home/media/ortflix/Movies_HDR
]
PLEX_URL          = "http://localhost:32400"
PLEX_TOKEN_FILE   = os.path.expanduser("~/docker_secrets/plex_token")
PLEX_SECTION_ID   = "1"

DRY_RUN = "--apply" not in sys.argv

# ── ISO 639-1 (Radarr) → ISO 639-2/T (mkvpropedit / ffmpeg) ─────────────────
LANG_MAP = {
    "en": "eng", "ja": "jpn", "es": "spa", "de": "deu", "fr": "fra",
    "it": "ita", "ru": "rus", "pl": "pol", "he": "heb", "ar": "ara",
    "hu": "hun", "zh": "zho", "ko": "kor", "pt": "por", "nl": "nld",
    "sv": "swe", "da": "dan", "no": "nor", "fi": "fin", "cs": "ces",
    "tr": "tur", "hi": "hin", "ro": "ron", "el": "ell", "th": "tha",
}


def radarr_language() -> str | None:
    """
    When called by Radarr, radarr_movie_originallanguage is set (e.g. 'ja', 'en').
    Map it to the 3-letter ISO 639-2 code that mkvpropedit/ffmpeg expect.
    Returns None if the env var is absent or unrecognised — caller should warn.
    """
    iso1 = os.environ.get("radarr_movie_originallanguage", "").strip().lower()
    if not iso1:
        return None
    mapped = LANG_MAP.get(iso1, iso1)  # pass through if already 3-letter / unknown code
    if iso1 not in LANG_MAP:
        title = os.environ.get("radarr_movie_title", "unknown title")
        year  = os.environ.get("radarr_movie_year", "")
        msg = (f"⚠️ **fix_audio_lang**: unknown language code `{iso1}` for "
               f"**{title}** ({year}) — tagged as-is. Add `{iso1}` to LANG_MAP if wrong.")
        print(f"  [WARN] {msg}")
        telegram_post(msg)
    return mapped


# ── Core helpers ──────────────────────────────────────────────────────────────

def audio_streams(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-select_streams", "a", path],
        capture_output=True, text=True,
    )
    try:
        return json.loads(r.stdout).get("streams", [])
    except Exception:
        return []


def needs_tag(stream):
    lang = stream.get("tags", {}).get("language", "")
    return not lang or lang in ("und", "NONE")


def run_cmd(cmd):
    if DRY_RUN:
        print("    CMD:", " ".join(f'"{x}"' if " " in x else x for x in cmd))
        return True
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"    ERROR (rc={r.returncode}): {r.stderr.strip()[:300]}")
        return False
    return True


# ── Per-format fixers ─────────────────────────────────────────────────────────

def fix_mkv(path, lang):
    streams = audio_streams(path)
    args = ["mkvpropedit", path]
    for i, s in enumerate(streams):
        if needs_tag(s):
            args += ["--edit", f"track:a{i+1}", "--set", f"language={lang}"]
    if len(args) > 2:
        return run_cmd(args)
    return True


def fix_mp4(path, lang):
    # Write temp to /tmp — avoids permission issues on restricted movie dirs
    tmp = f"/tmp/langtmp_{os.path.basename(path)}"
    streams = audio_streams(path)
    meta_args = []
    for i, s in enumerate(streams):
        if needs_tag(s):
            meta_args += [f"-metadata:s:a:{i}", f"language={lang}"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-i", path, "-c", "copy", "-map", "0"] + meta_args + [tmp]
    ok = run_cmd(cmd)
    if ok and not DRY_RUN:
        if os.path.exists(tmp):
            shutil.copy2(tmp, path)
            os.remove(tmp)
        else:
            print("    ERROR: temp file not created")
            return False
    return ok


def clean_title(filename):
    """Normalize filename to a bare comparable title (for AVI duplicate detection)."""
    name = os.path.splitext(filename)[0]
    name = re.sub(
        r'[\s\._\-]*(DVDRip|DvDrip|BDRip|BRRip|WEBRip|WEBRIP|HDTV|BluRay|'
        r'WEB[\-\.]?DL|x264|x265|XviD|xvid|DTS|H\.?264|H\.?265|AAC|AC3|'
        r'CD\d+|\d{3,4}p|2160p|4[Kk]|10[Bb]it).*',
        '', name, flags=re.IGNORECASE,
    )
    name = re.sub(r'\s*\(\d{4}\)\s*', ' ', name)
    name = re.sub(r'\s+\d{4}\s*$', ' ', name)
    name = re.sub(r'[\._]+', ' ', name)
    name = re.sub(r'\s+-\s+', ' ', name)
    name = re.sub(r'\s*-\s*\w+\s*$', '', name)
    return re.sub(r'\s+', ' ', name).strip().lower()


def fix_avi(path, lang):
    dirname   = os.path.dirname(path)
    avi_base  = os.path.basename(path)
    avi_clean = clean_title(avi_base)
    for fn in os.listdir(dirname):
        if fn == avi_base:
            continue
        fext = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ''
        if fext in ('mp4', 'mkv') and clean_title(fn) == avi_clean:
            print(f"    DUPLICATE of '{fn}' → deleting AVI")
            if not DRY_RUN:
                os.remove(path)
            return "deleted"
    out = path.rsplit(".", 1)[0] + ".mkv"
    if os.path.exists(out):
        print(f"    SKIP — MKV already exists: {os.path.basename(out)}")
        return "skipped"
    ok = run_cmd(["mkvmerge", "--default-language", lang, "-o", out, path])
    if ok and not DRY_RUN and os.path.exists(out):
        os.remove(path)
        print(f"    Remuxed → {os.path.basename(out)} (AVI deleted)")
    return "remuxed"


# ── Plex re-analysis ──────────────────────────────────────────────────────────

def plex_analyze_item(file_path):
    try:
        import urllib.request, urllib.parse
        token = open(PLEX_TOKEN_FILE).read().strip()
        url = f"{PLEX_URL}/library/sections/{PLEX_SECTION_ID}/all?type=1&X-Plex-Token={token}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        for item in data.get("MediaContainer", {}).get("Metadata", []):
            for media in item.get("Media", []):
                for part in media.get("Part", []):
                    if part.get("file") == file_path:
                        key = item["ratingKey"]
                        req2 = urllib.request.Request(
                            f"{PLEX_URL}/library/metadata/{key}/analyze?X-Plex-Token={token}",
                            method="PUT",
                        )
                        urllib.request.urlopen(req2, timeout=10)
                        print(f"  Plex: triggered analyze for ratingKey={key}")
                        return
        print("  Plex: item not found yet (Plex may not have scanned it yet — that's fine)")
    except Exception as e:
        print(f"  Plex: analyze trigger skipped — {e}")


# ── Entry points ──────────────────────────────────────────────────────────────

def run_radarr_mode():
    """Single-file mode: called by Radarr on import/upgrade."""
    event = os.environ.get("radarr_eventtype", "")

    if event == "Test":
        print("[fix_audio_lang] Test event received — script is working.")
        sys.exit(0)

    if event not in ("Download", "Upgrade"):
        print(f"[fix_audio_lang] Skipping event type: {event!r}")
        sys.exit(0)

    file_path = os.environ.get("radarr_moviefile_path", "")
    if not file_path or not os.path.exists(file_path):
        print(f"[fix_audio_lang] File not found: {file_path!r}")
        sys.exit(1)

    filename = os.path.basename(file_path)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    streams  = audio_streams(file_path)
    untagged = [s for s in streams if needs_tag(s)]
    if not untagged:
        print(f"[fix_audio_lang] Already tagged — nothing to do: {filename}")
        sys.exit(0)

    lang = radarr_language()
    if lang:
        print(f"[fix_audio_lang] {filename}  language={lang}  (radarr_movie_originallanguage={os.environ.get('radarr_movie_originallanguage')})")
    else:
        lang = "eng"
        title = os.environ.get("radarr_movie_title", filename)
        year  = os.environ.get("radarr_movie_year", "")
        msg = (f"⚠️ **fix_audio_lang**: `radarr_movie_originallanguage` not set for "
               f"**{title}** ({year}) — defaulted to `eng`. "
               f"Check manually if this is a non-English film.")
        print(f"[fix_audio_lang] {filename}  language=eng  (FALLBACK) — {msg}")
        telegram_post(msg)

    ok = False
    if ext == "mkv":
        ok = fix_mkv(file_path, lang)
    elif ext == "mp4":
        ok = fix_mp4(file_path, lang)
    else:
        print(f"  Format {ext!r} not supported for in-place tagging.")
        sys.exit(0)

    if ok:
        print(f"  Tagged as [{lang}] ✓")
        plex_analyze_item(file_path)
    else:
        sys.exit(1)


def run_bulk_mode():
    """Walk MOVIES_DIR and fix all untagged files."""
    mode = "DRY RUN — pass --apply to commit" if DRY_RUN else "*** LIVE MODE ***"
    print(f"=== Audio Language Bulk Fixer ({mode}) ===\n")

    for tool in ["ffprobe", "ffmpeg", "mkvpropedit", "mkvmerge"]:
        if subprocess.run(["which", tool], capture_output=True).returncode != 0:
            print(f"  MISSING tool: {tool}  →  sudo apt install mkvtoolnix ffmpeg")
            if not DRY_RUN:
                sys.exit(1)

    counts = {"mkv": 0, "mp4": 0, "avi_remuxed": 0, "avi_deleted": 0, "ok": 0}

    dirs_to_scan = [d for d in MOVIES_DIRS if os.path.isdir(d)]
    if not dirs_to_scan:
        print("No movie directories found — check MOVIES_DIRS paths.")
        sys.exit(1)

    for movies_dir in dirs_to_scan:
        print(f"Scanning: {movies_dir}")
    print()

    for movies_dir in dirs_to_scan:
        for root, _, files in os.walk(movies_dir):
            for fn in sorted(files):
                if "." not in fn:
                    continue
                ext = fn.rsplit(".", 1)[-1].lower()
                if ext not in ("mkv", "mp4", "avi"):
                    continue
                path = os.path.join(root, fn)
                streams  = audio_streams(path)
                untagged = [s for s in streams if needs_tag(s)]
                if not untagged:
                    counts["ok"] += 1
                    continue
                # Bulk mode has no Radarr context → default eng.
                # Library is already correctly tagged; this only catches new stragglers.
                lang = "eng"
                print(f"FIX [{ext.upper()}] [{lang}]  {fn}")
                if ext == "mkv":
                    fix_mkv(path, lang)
                    counts["mkv"] += 1
                elif ext == "mp4":
                    fix_mp4(path, lang)
                    counts["mp4"] += 1
                elif ext == "avi":
                    result = fix_avi(path, lang)
                    if result == "deleted":
                        counts["avi_deleted"] += 1
                    elif result == "remuxed":
                        counts["avi_remuxed"] += 1

    print(f"""
=== Summary ===
Already tagged  : {counts['ok']}
MKV fixed       : {counts['mkv']}
MP4 fixed       : {counts['mp4']}
AVI remuxed     : {counts['avi_remuxed']}
AVI deleted     : {counts['avi_deleted']}  (duplicate of existing MP4/MKV)
""")
    if DRY_RUN:
        print("→ Dry run complete. Run with --apply to apply.")
    else:
        print("→ Done. Trigger Plex re-analysis if needed:")
        print(f'  curl -X PUT "{PLEX_URL}/library/sections/{PLEX_SECTION_ID}/analyze?X-Plex-Token=$(cat {PLEX_TOKEN_FILE})"')
        print(f"  (add section IDs for any additional libraries if needed)")


def main():
    if os.environ.get("radarr_eventtype"):
        run_radarr_mode()
    else:
        run_bulk_mode()


if __name__ == "__main__":
    main()
