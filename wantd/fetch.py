"""Tier 0: get the reel. One yt-dlp call gives metadata (caption included) and a
low-res video, which later tiers reuse for audio and frames. One hit on Instagram,
not two: back-to-back requests trigger "empty media response".
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from wantd import config
from wantd.frames import probe_duration

logger = logging.getLogger(__name__)

# Instagram: /p/ /reel/ /reels/ /tv/, with optional username prefix.
_IG_RE = re.compile(r"instagr(?:am\.com|\.am)/(?:[^/?#]+/)?(?:p|tv|reels?)/([\w-]+)")
# YouTube: watch?v=, /shorts/, /live/, /embed/, youtu.be/ (ids are 11 chars).
_YT_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|live/|embed/)|youtu\.be/)([\w-]{11})"
)


@dataclass
class Meta:
    url: str = ""
    platform: str = "file"          # instagram | youtube | other | file
    title: str = ""
    channel: str = ""
    caption: str = ""
    duration: float = 0.0
    thumbnail: str = ""
    extra: dict = field(default_factory=dict)


def normalize_video_url(url: str) -> str:
    """One canonical form per post, so the same reel is cached and analysed once."""
    m = _IG_RE.search(url or "")
    if m:
        return f"https://www.instagram.com/reel/{m.group(1)}"
    m = _YT_RE.search(url or "")
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url


def platform_of(url: str) -> str:
    u = url or ""
    if "instagram." in u or "instagr.am" in u:
        return "instagram"
    if "youtube." in u or "youtu.be" in u:
        return "youtube"
    return "other"


def _ytdlp_args(url: str) -> list[str]:
    args = []
    if platform_of(url) == "youtube":
        if config.YOUTUBE_PLAYER_CLIENTS:
            args += ["--extractor-args", f"youtube:player_client={config.YOUTUBE_PLAYER_CLIENTS}"]
        if shutil.which("node"):  # yt-dlp needs a JS runtime for YouTube; deno is its default
            args += ["--js-runtimes", "node"]
        if config.YOUTUBE_COOKIES_FILE:
            return args + ["--cookies", config.YOUTUBE_COOKIES_FILE]
    if config.COOKIES_BROWSER:
        args += ["--cookies-from-browser", config.COOKIES_BROWSER]
    elif config.COOKIES_FILE:
        args += ["--cookies", config.COOKIES_FILE]
    return args


def friendly_error(stderr: str) -> str:
    """Turn yt-dlp's wall of stderr into one line a user can act on."""
    low = (stderr or "").lower()
    if "not a bot" in low or "sign in to confirm" in low:
        return "YouTube blocked this download (bot check on server IPs)."
    if "private video" in low or "this video is private" in low:
        return "That video is private."
    if "video unavailable" in low or "removed by the uploader" in low:
        return "That video is unavailable or has been removed."
    if "age" in low and "restrict" in low:
        return "That video is age-restricted."
    if "login required" in low or "empty media response" in low or "rate-limit" in low:
        return "Instagram needs a login or is rate-limiting. Try again later."
    errors = [l.strip() for l in (stderr or "").splitlines() if l.strip().startswith("ERROR:")]
    return errors[-1][:300] if errors else ((stderr or "").strip()[:300] or "Download failed")


def fetch(url: str, out_dir: str) -> tuple[str, Meta]:
    """Download a low-res video plus metadata. Returns (video_path, meta)."""
    url = normalize_video_url(url)
    cmd = [
        sys.executable, "-m", "yt_dlp",  # the yt-dlp installed with us, not whatever is on PATH
        "-f", "best[height<=480][ext=mp4]/best[height<=480]/worst[ext=mp4]/worst",
        "--no-playlist", "--no-warnings", "--print-json",
        *_ytdlp_args(url),
        "-o", os.path.join(out_dir, "reel.%(ext)s"),
        url,
    ]
    logger.info("tier 0: fetching %s", url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(friendly_error(r.stderr))

    data = json.loads(r.stdout.strip().splitlines()[-1])
    meta = Meta(
        url=url,
        platform=platform_of(url),
        title=data.get("title") or "",
        channel=data.get("channel") or data.get("uploader_id") or data.get("uploader") or "",
        caption=(data.get("description") or "").strip(),
        duration=float(data.get("duration") or 0),
        thumbnail=data.get("thumbnail") or "",
    )
    video = next((os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.startswith("reel.")), None)
    if not video:
        raise FileNotFoundError("yt-dlp reported success but wrote no video")
    # Instagram's metadata often omits duration, so read it off the file.
    meta.duration = meta.duration or probe_duration(video) or 0.0
    if meta.duration > config.MAX_VIDEO_DURATION:
        raise ValueError(f"Video too long: {meta.duration:.0f}s (max {config.MAX_VIDEO_DURATION:.0f}s)")
    return video, meta


def extract_audio(video_path: str, out_dir: str) -> str | None:
    """Mono low-bitrate mp3: small enough to send inline. None if there's no audio track."""
    out = os.path.join(out_dir, "audio.mp3")
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path, "-vn", "-ac", "1",
         "-ar", "16000", "-b:a", "32k", out],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1024:
        logger.info("no usable audio track (%s)", (r.stderr or "").strip()[:120])
        return None
    return out
