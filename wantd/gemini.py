"""The three Gemini reads. Each returns the same Extraction schema, and tiers 2 and 3
get the earlier draft so they correct it instead of starting over."""

import logging
import os

from google import genai
from google.genai import errors, types

from wantd import config
from wantd.fetch import Meta
from wantd.schema import Extraction

logger = logging.getLogger(__name__)

INLINE_LIMIT = 15 * 1024 * 1024  # inline requests cap at ~20MB total; bigger files go via the Files API

RULES = """You extract structured notes from one short video (Instagram reel or YouTube Short).

Rules:
- domain: "shopping" for products/stores/outfits/beauty/gadgets, "places" for cafes/restaurants/travel spots, "recipe" for food prep, "knowledge" for explainers/tips, else "other".
- Copy @handles, links, brand names, product names, prices and place names EXACTLY as written or said. Never paraphrase, correct or translate them.
- products: one entry per distinct item shown or named. places: one entry per distinct place.
- summary: state the information itself. Never write "this reel shows", "the speaker says", "in this video".
- action_items: practical takeaways only. Exclude follow/like/comment/share/subscribe/save/"link in bio".
- tags: 1-4 lowercase topic tags.
- Hindi and Hinglish are common. Keep the transcript in the original language; write title, summary and action_items in English.
- confidence: be honest. Low if the key payload (product, place, steps) is unclear or likely shown on screen but not visible to you.
- needs_visual: true if the important information is probably on screen rather than spoken (outfits, text cards, store handles, music-only reels)."""

_client = None


def client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")
        # Busy models answer 5xx at random; the SDK retries those. 429 (quota) goes straight
        # to the fallback model: a daily cap will not clear in 30 seconds.
        retry = types.HttpRetryOptions(attempts=5, initial_delay=2, max_delay=30,
                                       http_status_codes=[500, 503, 504])
        _client = genai.Client(api_key=config.GEMINI_API_KEY,
                               http_options=types.HttpOptions(timeout=180_000, retry_options=retry))
    return _client


def _context(meta: Meta, draft: Extraction | None) -> str:
    lines = [f"Creator: @{meta.channel}" if meta.channel else "",
             f"Title: {meta.title}" if meta.title else "",
             f"Caption: {meta.caption}" if meta.caption else "Caption: (none)"]
    if draft:
        lines.append("Draft from an earlier, cheaper pass. It may be incomplete or wrong; "
                     "correct and complete it, and keep its transcript:\n"
                     + draft.model_dump_json(indent=1))
    return "\n".join(l for l in lines if l)


def _generate(model: str, parts: list, task: str) -> Extraction:
    cfg = types.GenerateContentConfig(
        system_instruction=RULES,
        temperature=0.2,
        response_mime_type="application/json",
        response_schema=Extraction,
    )
    try:
        resp = client().models.generate_content(model=model, contents=[*parts, task], config=cfg)
    except (errors.ServerError, errors.ClientError) as e:
        # Still overloaded after the SDK's retries: a different model has its own capacity.
        fallback = config.GEMINI_FALLBACK_MODEL
        if not fallback or fallback == model or (e.code not in (429, 500, 503, 504)):
            raise
        logger.warning("%s unavailable (%s); falling back to %s", model, e.code, fallback)
        resp = client().models.generate_content(model=fallback, contents=[*parts, task], config=cfg)
    if resp.parsed is None:
        raise RuntimeError(f"Gemini returned no parseable JSON: {(resp.text or '')[:200]}")
    return resp.parsed


def _file_part(path: str, mime: str) -> types.Part:
    if os.path.getsize(path) <= INLINE_LIMIT:
        with open(path, "rb") as f:
            return types.Part.from_bytes(data=f.read(), mime_type=mime)
    uploaded = client().files.upload(file=path)
    return types.Part(file_data=types.FileData(file_uri=uploaded.uri, mime_type=mime))


def from_audio(audio_path: str, meta: Meta) -> Extraction:
    """Tier 1: transcript + caption. Cheapest, and enough for most talking reels."""
    task = (_context(meta, None) + "\n\nThe attached audio is the reel's soundtrack. "
            "Transcribe the speech verbatim into `transcript`, then fill every field.")
    return _generate(config.GEMINI_MODEL, [_file_part(audio_path, "audio/mp3")], task)


def from_frames(frame_paths: list[str], meta: Meta, draft: Extraction | None) -> Extraction:
    """Tier 2: one frame per scene cut, in reel order, read alongside the draft."""
    parts = []
    for p in frame_paths:
        with open(p, "rb") as f:
            parts.append(types.Part.from_bytes(data=f.read(), mime_type="image/jpeg"))
    task = (_context(meta, draft) + f"\n\nThe {len(frame_paths)} images are key frames from "
            "the reel, in order. Read all on-screen text into `on_screen_text`, identify every "
            "product/place shown, and fill every field.")
    return _generate(config.GEMINI_MODEL, parts, task)


def from_video(meta: Meta, draft: Extraction | None, video_path: str | None) -> Extraction:
    """Tier 3: the whole video. Public YouTube links go to Gemini by URL, no download."""
    if video_path:
        part = _file_part(video_path, "video/mp4")
    elif meta.platform == "youtube":
        part = types.Part(file_data=types.FileData(file_uri=meta.url))
    else:
        raise RuntimeError("no video available for tier 3")
    task = (_context(meta, draft) + "\n\nThe attached video is the full reel. Use speech, "
            "on-screen text and visuals together, and fill every field.")
    return _generate(config.GEMINI_VIDEO_MODEL, [part], task)
