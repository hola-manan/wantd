"""What every tier returns. One schema for all three, so a later tier can correct an
earlier one field by field instead of producing a different shape."""

from typing import Literal

from pydantic import BaseModel, Field

Domain = Literal["shopping", "places", "recipe", "knowledge", "other"]


class Product(BaseModel):
    name: str
    brand: str = ""
    category: str = ""
    color: str = ""
    price: str = ""                 # as shown/said, e.g. "Rs 1,299"; empty if not stated
    handle: str = ""                # store/brand @handle, copied exactly


class Place(BaseModel):
    name: str
    area: str = ""
    city: str = ""
    handle: str = ""


class Extraction(BaseModel):
    domain: Domain
    title: str = Field(description="5-8 words, no clickbait")
    summary: str = Field(description="2-3 sentences stating the content itself")
    action_items: list[str]
    tags: list[str] = Field(description="1-4 lowercase topic tags")
    products: list[Product]
    places: list[Place]
    handles: list[str] = Field(description="@handles of stores/brands/places, exactly as written")
    on_screen_text: list[str]
    transcript: str = Field(description="verbatim speech, original language; empty if none")
    language: str = Field(description="spoken language, e.g. en, hi, hinglish; empty if none")
    confidence: float = Field(description="0-1: how sure you are this captures the reel's real payload")
    needs_visual: bool = Field(description="true if the key info is probably shown on screen, not said")


class Result(BaseModel):
    url: str
    platform: str
    title: str
    channel: str
    caption: str
    duration: float
    thumbnail: str
    hashtags: list[str]
    tiers_run: list[str]
    extraction: Extraction | None
    elapsed_s: float
