# Wantd: reel understanding

Turns an Instagram reel or YouTube Short into structured data (domain, products with brand and price, places, @handles, on-screen text, transcript, summary) using a tiered Gemini pipeline. The extraction core is ported from iSave.

## Pipeline

| Tier | Input | Runs when |
|---|---|---|
| 0 · metadata | caption, channel, duration, thumbnail (yt-dlp), plus handles and hashtags mined from the caption | always |
| 1 · audio | soundtrack plus caption → Gemini transcribes and extracts | the reel has audio |
| 2 · key frames | one frame per scene cut (ffmpeg) plus the tier 1 draft → Gemini | tier 1 is unsure, the payload is visual, or there is little speech |
| 3 · full video | the whole video plus the draft → Gemini | still unsure after tier 2 |

All tiers return the same schema ([wantd/schema.py](wantd/schema.py)). Later tiers correct the draft instead of starting over. If the YouTube download fails, tier 3 reads the public URL directly. Caption handles take priority over anything read off pixels, and the creator's own watermark handle is dropped.

## Setup

Needs Python 3.11+, `ffmpeg` and `node` (yt-dlp uses node for YouTube).

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env        # then set GEMINI_API_KEY
```

## Use

```bash
# CLI: prints the result as JSON
.venv/bin/python -m wantd "https://www.instagram.com/reel/XXXX/"
.venv/bin/python -m wantd "https://youtube.com/shorts/XXXX" --max-tier 1   # cap cost while testing
.venv/bin/python -m wantd reel.mp4 --keep out/run1                          # keep video, audio and frames

# API
.venv/bin/uvicorn wantd.api:app --reload
curl -X POST localhost:8000/extract -H 'content-type: application/json' -d '{"url":"https://..."}'
curl localhost:8000/extract/<id>       # status: queued | running | done | failed, plus the current stage

# Tests (no network or API key needed)
.venv/bin/pytest
```

The API analyses each reel once: a second request for the same reel, in any URL form, returns the same job.

## Configuration (.env)

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | | required |
| `GEMINI_MODEL` | `gemini-3.5-flash` | tiers 1 and 2 |
| `GEMINI_VIDEO_MODEL` | same as `GEMINI_MODEL` | tier 3 |
| `GEMINI_FALLBACK_MODEL` | `gemini-3.5-flash-lite` | used when the main model is overloaded or out of quota |
| `CONFIDENCE_OK` | `0.7` | a tier's result is accepted at or above this |
| `MIN_TRANSCRIPT_WORDS` | `20` | less speech than this sends the reel to tier 2 |
| `MAX_VIDEO_DURATION` | `300` | seconds |
| `COOKIES_BROWSER` / `COOKIES_FILE` | empty | local prototype only, see below |

**Free-tier quota:** about 20 requests a day per model on the free Gemini tier. A reel uses 1 to 3 requests. Turn on billing, or use the buildathon Google Cloud credits, before any real use.

## Platform access

Public Instagram reels download **logged out** with no cookies. Keep it that way. Logged-in scraping breaks Meta's terms and risks the account. YouTube is read through Gemini's official URL input when the download fails. Planned official paths: DM-to-save (Meta's messaging webhook, `ig_reel` attachments), comment-to-save (mentions webhook), and user-shared screen recordings.

## Layout

```
wantd/
  fetch.py      tier 0: URL canonicalisation, yt-dlp download + metadata, audio extraction
  frames.py     scene-cut frame picking (ffmpeg)
  gemini.py     the three Gemini reads, retries and model fallback
  pipeline.py   tier orchestration and escalation rules
  handles.py    @handle and #hashtag parsing and cleanup
  schema.py     output schema
  api.py        FastAPI service (in-memory jobs and cache)
  __main__.py   CLI
```

**Not ported from iSave yet:** the database, auth, reminders, bulk import, and the Instagram webhooks. Add them as the app needs them.
