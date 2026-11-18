"""Checks that need no network or API key. Run: pytest"""

from wantd import config
from wantd.fetch import friendly_error, normalize_video_url, platform_of
from wantd.frames import Frame, order_and_cap
from wantd.handles import clean_handle, merge_handles, mine_caption
from wantd.pipeline import should_escalate
from wantd.schema import Extraction


def test_url_canonical_forms():
    ig = "https://www.instagram.com/reel/ABC123"
    assert normalize_video_url("https://instagram.com/p/ABC123/?igsh=x") == ig
    assert normalize_video_url("https://www.instagram.com/someuser/reel/ABC123") == ig
    assert normalize_video_url("https://www.instagram.com/reel/ABC123/?utm_source=ig_web_copy_link") == ig
    yt = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert normalize_video_url("https://www.youtube.com/shorts/dQw4w9WgXcQ") == yt
    assert normalize_video_url("https://youtu.be/dQw4w9WgXcQ?t=10") == yt
    assert normalize_video_url("https://m.youtube.com/watch?app=desktop&v=dQw4w9WgXcQ") == yt
    assert normalize_video_url("https://vimeo.com/12345") == "https://vimeo.com/12345"
    assert platform_of(ig) == "instagram" and platform_of(yt) == "youtube"


def test_friendly_errors_hide_stderr():
    bot = "WARNING: noise\nERROR: [youtube] x: Sign in to confirm you're not a bot."
    assert "YouTube blocked" in friendly_error(bot)
    assert friendly_error("ERROR: [youtube] xyz: Private video") == "That video is private."
    assert friendly_error("WARNING: noise\nERROR: specific") == "ERROR: specific"


def test_handles():
    assert clean_handle("garbage!!") is None
    assert clean_handle("shop at @thelinenlabel now") == "thelinenlabel"
    handles, tags = mine_caption("cam from @insta360 \U0001FAF6 #insta360 #VloggingCamera")
    assert handles == ["@insta360"] and tags == ["insta360", "vloggingcamera"]
    # caption first, dedupe case-insensitively, creator's own watermark dropped
    assert merge_handles(["@Store.co"], ["@store.co", "@me", "@other"], own="me") == ["@store.co", "@other"]
    # emails are not handles
    assert mine_caption("collabs: zera@gmail.com")[0] == []
    assert clean_handle("@gmail.com") is None


def test_frames_keep_reel_order():
    fs = [Frame("c", 3.0), Frame("a", 0.5), Frame("b", None), Frame("d", 1.5)]
    assert [f.path for f in order_and_cap(fs, 3)] == ["a", "d", "c"]


def _ex(**kw) -> Extraction:
    base = dict(domain="shopping", title="t", summary="s", action_items=[], tags=[],
                products=[], places=[], handles=[], on_screen_text=[], transcript="word " * 50,
                language="en", confidence=0.9, needs_visual=False)
    return Extraction(**{**base, **kw})


def test_escalation():
    assert should_escalate(None)
    assert not should_escalate(_ex())
    assert should_escalate(_ex(confidence=config.CONFIDENCE_OK - 0.1))
    assert should_escalate(_ex(needs_visual=True))
    assert should_escalate(_ex(transcript="just music"))                       # sparse speech
    # once frames were read, only low confidence escalates further
    assert not should_escalate(_ex(transcript="", needs_visual=True), saw_visuals=True)
    assert should_escalate(_ex(confidence=0.3), saw_visuals=True)
