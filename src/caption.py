"""Caption handling: keep the original title/caption and description.

Rules:
- The original caption is always preserved (template ``{caption}``).
- Optional hashtags from config are appended on their own lines.
- Facebook Page posts are limited to 1024 characters — longer text is
  truncated cleanly with ``...`` so the post never fails on length.
"""
from __future__ import annotations


def build_caption(caption: str, template: str = "{caption}",
                  max_chars: int = 1024,
                  hashtags: list[str] | None = None) -> str:
    """Build the final caption from the original one.

    Only ``{caption}`` is a placeholder — any other braces in the
    template stay literal instead of raising KeyError (the old
    ``template.format(...)`` crashed the whole run on one bad template).
    """
    caption = (caption or "").strip()
    text = (template or "{caption}").replace("{caption}", caption).strip()
    for tag in hashtags or []:
        tag = tag.strip()
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = "#" + tag
        if tag not in text:
            text = f"{text}\n{tag}" if text else tag
    return truncate(text, max_chars)


def truncate(text: str, max_chars: int) -> str:
    """Truncate to max_chars, ending with '...' instead of mid-word."""
    max_chars = max(int(max_chars or 1024), 4)
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 3].rstrip()
    # avoid cutting in the middle of a word when possible
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "..."
