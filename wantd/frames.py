"""Tier 2 input: pick the few frames that matter.

- one frame per SCENE CHANGE: a text card or outfit change *is* a cut, so this
  gives one clean frame per segment instead of 100 near-duplicates
- plus forced early frames, because the opening title card carries the intent
- near-duplicates dropped by ffmpeg's mpdecimate
"""

import logging
import os
import re
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SCENE_THRESHOLD = 0.30    # ffmpeg scene score above which we call it a new scene
MAX_FRAMES = 20           # plenty for a sub-90s reel
FRAME_SIZE = 768          # fits within 768x768, the vision-model sweet spot
EARLY_FRAMES = (0.5, 1.5)  # title-card insurance
JPEG_Q = 3


@dataclass
class Frame:
    path: str
    t: float | None  # seconds into the reel, when ffmpeg reported it


def _scale() -> str:
    return f"scale=w={FRAME_SIZE}:h={FRAME_SIZE}:force_original_aspect_ratio=decrease"


def probe_duration(video_path: str) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=30,
        )
        return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        return None


def _grab_at(video_path: str, t: float, out_path: str) -> bool:
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", video_path,
         "-frames:v", "1", "-vf", _scale(), "-q:v", str(JPEG_Q), out_path],
        capture_output=True, text=True, timeout=60,
    )
    return r.returncode == 0 and os.path.exists(out_path)


def _scene_frames(video_path: str, out_dir: str, threshold: float) -> list[Frame]:
    pattern = os.path.join(out_dir, "scene_%03d.jpg")
    vf = f"select='gt(scene\\,{threshold})',mpdecimate,{_scale()},showinfo"
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "info", "-i", video_path,
         "-vf", vf, "-fps_mode", "vfr", "-q:v", str(JPEG_Q), pattern],
        capture_output=True, text=True, timeout=180,
    )
    # showinfo logs one "pts_time:<n>" per emitted frame, in output order.
    times = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr or "")]
    files = sorted(f for f in os.listdir(out_dir) if f.startswith("scene_"))
    return [Frame(os.path.join(out_dir, name), times[i] if i < len(times) else None)
            for i, name in enumerate(files)]


def order_and_cap(frames: list[Frame], max_frames: int) -> list[Frame]:
    """Reel order carries meaning (it's the creator's own ranking); unknown times go last."""
    frames = sorted(frames, key=lambda f: (f.t is None, f.t or 0.0))
    return frames[:max_frames]


def extract_frames(video_path: str, out_dir: str,
                   scene_threshold: float = SCENE_THRESHOLD,
                   max_frames: int = MAX_FRAMES) -> list[Frame]:
    os.makedirs(out_dir, exist_ok=True)
    duration = probe_duration(video_path)
    frames = []
    for i, t in enumerate(EARLY_FRAMES):
        if duration is not None and t >= duration:
            continue
        p = os.path.join(out_dir, f"early_{i}.jpg")
        if _grab_at(video_path, t, p):
            frames.append(Frame(p, t))
    frames += _scene_frames(video_path, out_dir, scene_threshold)
    frames = order_and_cap(frames, max_frames)
    logger.info("tier 2: %d frames picked (duration=%s)", len(frames), duration)
    return frames
