"""Settings, read once from the environment (and .env if present)."""

import os

from dotenv import load_dotenv

load_dotenv()


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Tiers 1-2. The "-latest" aliases aren't served on every key, so pin a version.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
# Tier 3 (full video) is the rare, expensive step; allow a stronger model there.
GEMINI_VIDEO_MODEL = os.getenv("GEMINI_VIDEO_MODEL", GEMINI_MODEL)
# Used when the model above is still overloaded (429/5xx) after retries. Empty disables.
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")

# A tier's result is accepted when its self-reported confidence reaches this.
CONFIDENCE_OK = _f("CONFIDENCE_OK", 0.7)
# Fewer spoken words than this means the payload is probably on screen.
MIN_TRANSCRIPT_WORDS = int(os.getenv("MIN_TRANSCRIPT_WORDS", 20))
MAX_VIDEO_DURATION = _f("MAX_VIDEO_DURATION", 300)

# yt-dlp auth. Prototype only: logged-in scraping breaks Meta's terms (see README).
COOKIES_BROWSER = os.getenv("COOKIES_BROWSER", "")   # e.g. "chrome" for local dev
COOKIES_FILE = os.getenv("COOKIES_FILE", "")
YOUTUBE_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE", "")
# YouTube flags datacenter IPs; alternate player clients sometimes get past the check.
YOUTUBE_PLAYER_CLIENTS = os.getenv("YOUTUBE_PLAYER_CLIENTS", "android,ios,tv")
