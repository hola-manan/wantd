"""The tiered reel-understanding pipeline.

    tier 0  metadata + caption          (yt-dlp, no model)
    tier 1  audio + caption             (Gemini, cheapest)
    tier 2  key frames + draft          (only if tier 1 is unsure or the payload is visual)
    tier 3  full video + draft          (only if still unsure)

Each tier runs only when the one before isn't confident, so most reels never reach
the expensive step. Full video samples ~1 frame/sec and can skip fast text cards, so
tier 3 adds to the earlier tiers rather than replacing them.
"""

import logging
import os
import shutil
import tempfile
import time
from typing import Callable

from wantd import config, frames, gemini
from wantd.fetch import Meta, extract_audio, fetch, normalize_video_url, platform_of
from wantd.handles import merge_handles, mine_caption
from wantd.schema import Extraction, Result

logger = logging.getLogger(__name__)


def should_escalate(ex: Extraction | None, saw_visuals: bool = False) -> bool:
    if ex is None or ex.confidence < config.CONFIDENCE_OK:
        return True
    if saw_visuals:
        return False  # frames already read: "needs visuals" and sparse speech are covered
    return ex.needs_visual or len((ex.transcript or "").split()) < config.MIN_TRANSCRIPT_WORDS


def run(target: str, max_tier: int = 3, keep_dir: str | None = None,
        on_stage: Callable[[str], None] = lambda s: None) -> Result:
    """Process a reel URL or a local video file."""
    started = time.monotonic()
    work = keep_dir or tempfile.mkdtemp(prefix="wantd_")
    os.makedirs(work, exist_ok=True)
    tiers: list[str] = []
    ex: Extraction | None = None
    video: str | None = None

    try:
        # --- tier 0: get the reel ---
        on_stage("fetching")
        if os.path.exists(target):
            video, meta = target, Meta(url=os.path.abspath(target))
        else:
            meta = Meta(url=normalize_video_url(target), platform=platform_of(target))
            try:
                video, meta = fetch(target, work)
                tiers.append("metadata")
            except Exception as e:
                # YouTube can still be read by URL; anything else has nothing to work with.
                if meta.platform != "youtube":
                    raise
                logger.warning("download failed (%s); reading YouTube by URL", e)
        caption_handles, hashtags = mine_caption(meta.caption)

        # --- tier 1: audio ---
        audio = extract_audio(video, work) if video and max_tier >= 1 else None
        if audio:
            on_stage("tier1_audio")
            ex = gemini.from_audio(audio, meta)
            tiers.append("audio")

        # --- tier 2: key frames ---
        if video and max_tier >= 2 and should_escalate(ex):
            on_stage("tier2_frames")
            picked = frames.extract_frames(video, os.path.join(work, "frames"))
            if picked:
                transcript = ex.transcript if ex else ""
                ex = gemini.from_frames([f.path for f in picked], meta, ex)
                ex.transcript = ex.transcript or transcript
                tiers.append("frames")

        # --- tier 3: full video ---
        if (max_tier >= 3 and should_escalate(ex, saw_visuals="frames" in tiers)
                and (video or meta.platform == "youtube")):
            on_stage("tier3_video")
            transcript = ex.transcript if ex else ""
            ex = gemini.from_video(meta, ex, video)
            ex.transcript = ex.transcript or transcript
            tiers.append("video")

        if ex:
            # Caption handles lead: they're exact, unlike anything read off pixels.
            ex.handles = merge_handles(caption_handles, ex.handles, own=meta.channel)

        on_stage("done")
        return Result(
            url=meta.url, platform=meta.platform, title=meta.title, channel=meta.channel,
            caption=meta.caption, duration=meta.duration, thumbnail=meta.thumbnail,
            hashtags=hashtags, tiers_run=tiers, extraction=ex,
            elapsed_s=round(time.monotonic() - started, 1),
        )
    finally:
        if not keep_dir:
            shutil.rmtree(work, ignore_errors=True)
