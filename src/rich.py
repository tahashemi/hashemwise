"""Hashemwise - building Telegram rich messages (Bot API 10.1+).

Pure functions that return plain dicts in the shape `sendRichMessage` expects.
No aiogram and no database, for the same reason as `render.py`: the payloads
can be checked against the documented schema without a bot token.

Field names follow https://core.telegram.org/bots/api#inputrichblocktable.
Text inside blocks is a RichText, which may be a plain string - and a plain
string is never parsed, so user-supplied names need no escaping here.
"""

from __future__ import annotations

from typing import Any, Sequence

# Telegram rejects a table wider than this. Callers check `fits()` and fall
# back to the plain-text layout rather than sending something that will fail.
MAX_COLUMNS = 20
# Counted across the whole message, table rows included.
MAX_BLOCKS = 500

RichText = Any  # str, or a {"type": ..., "text": ...} formatting object


def struck(text: RichText) -> RichText:
    return {"type": "strikethrough", "text": text}


def bold(text: RichText) -> RichText:
    return {"type": "bold", "text": text}


def cell(text: RichText, *, header: bool = False, align: str = "center") -> dict:
    # align and valign are not optional in RichBlockTableCell, unlike the
    # other fields; leaving either out is a request Telegram can reject.
    c: dict = {"text": text, "align": align, "valign": "middle"}
    if header:
        c["is_header"] = True
    return c


def table(
    headers: Sequence[RichText],
    rows: Sequence[Sequence[RichText]],
    caption: RichText | None = None,
) -> dict:
    block: dict = {
        "type": "table",
        "cells": [[cell(h, header=True) for h in headers]]
        + [[c if isinstance(c, dict) and "valign" in c else cell(c) for c in row] for row in rows],
        "is_bordered": True,
        "is_striped": True,
        "is_compact": True,
    }
    if caption:
        block["caption"] = caption
    return block


def paragraph(text: RichText) -> dict:
    return {"type": "paragraph", "text": text}


def message(blocks: Sequence[dict], lang: str) -> dict:
    # Without is_rtl a Persian table lays its columns out left to right, so the
    # first column - the one a Persian reader starts from - ends up last.
    return {"blocks": list(blocks), "is_rtl": lang == "fa"}


def html_message(text: str, lang: str) -> dict:
    """An existing HTML-formatted string, as a rich message.

    Used when a rich message has to be edited into a plain notice (a delete
    confirmation): editing it with ordinary `text` would change its kind.
    """
    return {"html": text, "is_rtl": lang == "fa"}


def fits(rich: dict) -> bool:
    """Whether every table respects the column limit and the block count."""
    blocks = rich.get("blocks", [])
    count = 0
    for block in blocks:
        count += 1
        if block.get("type") == "table":
            if any(len(row) > MAX_COLUMNS for row in block["cells"]):
                return False
            count += len(block["cells"])
    return count <= MAX_BLOCKS
