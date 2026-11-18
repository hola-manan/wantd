"""@handles and #hashtags. A handle is a far better extraction target than "which
white linen dress is this": rigid format, high-contrast on screen, and it either
resolves on Instagram or it doesn't."""

import re

# Not preceded by a word char or dot, so "hi@gmail.com" isn't read as @gmail.com.
HANDLE_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9._]{2,30})")
# Models sometimes return an email's domain as a handle; these are never shops.
_MAIL_DOMAINS = {"gmail.com", "yahoo.com", "yahoo.in", "outlook.com", "hotmail.com",
                 "icloud.com", "rediffmail.com", "proton.me"}
HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]{2,50})")


def clean_handle(raw) -> str | None:
    """Strict on purpose: OCR-ish noise must never be promoted to a handle."""
    s = str(raw or "").strip()
    if "@" in s:
        m = HANDLE_RE.search(s)
        s = m.group(1) if m else ""
    s = s.lower().strip(".")
    return s if re.fullmatch(r"[a-z0-9._]{2,30}", s) and s not in _MAIL_DOMAINS else None


def mine_caption(caption: str | None) -> tuple[list[str], list[str]]:
    """Handles and hashtags straight from the caption: free, exact, no model call."""
    text = caption or ""
    handles = merge_handles(HANDLE_RE.findall(text))
    tags = list(dict.fromkeys(t.lower() for t in HASHTAG_RE.findall(text)))
    return handles, tags


def merge_handles(*groups, own: str | None = None) -> list[str]:
    """Dedupe across sources in order, drop the creator's own watermark handle."""
    own = (own or "").lower().lstrip("@")
    out, seen = [], set()
    for group in groups:
        for h in group or []:
            c = clean_handle(h)
            if c and c != own and c not in seen:
                seen.add(c)
                out.append(f"@{c}")
    return out
