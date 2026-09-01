"""Hashemwise - inline keyboards and callback data.

Telegram caps callback data at **64 bytes**, which shapes everything here:
field names are single letters and the flow token is 8 characters rather than a
full uuid. `assert_fits` guards the limit at build time, because exceeding it
fails at send time with an unhelpful error.

Every button in a wizard carries the flow token and the id of the user the menu
belongs to. In a group chat anyone can tap anyone's buttons, so both are
checked before the press is acted on.
"""

from __future__ import annotations

import uuid

from aiogram.filters.callback_data import CallbackData
from aiogram.types import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.currencies import CURRENCIES
from src.i18n import LANG_NAMES, t

CALLBACK_DATA_LIMIT = 64


class FlowCB(CallbackData, prefix="f"):
    """A button belonging to one user's wizard.

    `t` flow token, `o` owner Telegram id, `a` action, `v` action payload.

    `v` is optional because actions like cancel/done/confirm carry no payload.
    It must be declared nullable: aiogram packs a missing value as an empty
    string and unpacks that back to None, so a plain `str` would raise a
    validation error on every one of those presses.
    """

    t: str
    o: int
    a: str
    v: str | None = None


class AdminCB(CallbackData, prefix="ad"):
    """Admin buttons are not part of a wizard and have no flow token."""

    a: str
    v: str | None = None


def new_flow_token() -> str:
    """Short token for button matching. Not a security boundary - the owner id
    check is - just enough to tell one menu from another."""
    return uuid.uuid4().hex[:8]


def new_idem_key() -> str:
    """Full-length key for the database's unique constraint."""
    return uuid.uuid4().hex


def assert_fits(markup: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data and len(button.callback_data.encode()) > CALLBACK_DATA_LIMIT:
                raise ValueError(
                    f"callback data too long ({len(button.callback_data.encode())}B): "
                    f"{button.callback_data!r}"
                )
    return markup


def force_reply() -> ForceReply:
    """Prompt for free text.

    Load-bearing: Telegram's group privacy mode is on by default, so a bot
    never sees ordinary messages in a group - but it *does* see replies to its
    own messages. Every free-text step therefore asks via ForceReply rather
    than plain text, which also means the flow works whether or not privacy
    mode has been turned off in BotFather.
    """
    return ForceReply(selective=True)


def _cancel_row(builder: InlineKeyboardBuilder, flow: str, owner: int, lang: str) -> None:
    builder.button(
        text=t("btn_cancel", lang), callback_data=FlowCB(t=flow, o=owner, a="cancel").pack()
    )


def currency_keyboard(flow: str, owner: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, cur in CURRENCIES.items():
        label = cur.name_fa if lang == "fa" else cur.name_en
        builder.button(
            text=f"{label} ({code})", callback_data=FlowCB(t=flow, o=owner, a="cur", v=code).pack()
        )
    builder.adjust(2)
    _cancel_row(builder, flow, owner, lang)
    return assert_fits(builder.as_markup())


def language_keyboard(flow: str, owner: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, name in LANG_NAMES.items():
        builder.button(
            text=name, callback_data=FlowCB(t=flow, o=owner, a="lang", v=code).pack()
        )
    builder.adjust(2)
    _cancel_row(builder, flow, owner, lang)
    return assert_fits(builder.as_markup())


def member_keyboard(
    members, flow: str, owner: int, lang: str, action: str, exclude: int | None = None
) -> InlineKeyboardMarkup:
    """One button per member - "who paid", "who received", "which one are you"."""
    builder = InlineKeyboardBuilder()
    for m in members:
        if m.user_id == exclude:
            continue
        builder.button(
            text=m.display_name,
            callback_data=FlowCB(t=flow, o=owner, a=action, v=str(m.user_id)).pack(),
        )
    builder.adjust(2)
    _cancel_row(builder, flow, owner, lang)
    return assert_fits(builder.as_markup())


def participants_keyboard(
    members, selected: set[int], flow: str, owner: int, lang: str
) -> InlineKeyboardMarkup:
    """Multi-select toggle list, with Done.

    Not every expense involves everyone; forcing the whole group into every
    split is the most common way a shared-expense tracker produces figures
    people refuse to trust.
    """
    builder = InlineKeyboardBuilder()
    for m in members:
        mark = "✅" if m.user_id in selected else "⬜"
        builder.button(
            text=f"{mark} {m.display_name}",
            callback_data=FlowCB(t=flow, o=owner, a="tog", v=str(m.user_id)).pack(),
        )
    builder.adjust(2)

    builder.row(
        InlineKeyboardButton(
            text=t("btn_done", lang), callback_data=FlowCB(t=flow, o=owner, a="pdone").pack()
        ),
        InlineKeyboardButton(
            text=t("btn_cancel", lang), callback_data=FlowCB(t=flow, o=owner, a="cancel").pack()
        ),
    )
    return assert_fits(builder.as_markup())


def split_type_keyboard(flow: str, owner: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("btn_split_equal", lang),
        callback_data=FlowCB(t=flow, o=owner, a="split", v="eq").pack(),
    )
    builder.button(
        text=t("btn_split_custom", lang),
        callback_data=FlowCB(t=flow, o=owner, a="split", v="cu").pack(),
    )
    builder.adjust(1)
    _cancel_row(builder, flow, owner, lang)
    return assert_fits(builder.as_markup())


def confirm_keyboard(flow: str, owner: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("btn_confirm", lang), callback_data=FlowCB(t=flow, o=owner, a="ok").pack()
    )
    builder.button(
        text=t("btn_cancel", lang), callback_data=FlowCB(t=flow, o=owner, a="cancel").pack()
    )
    builder.adjust(2)
    return assert_fits(builder.as_markup())


def authorize_keyboard(group_id: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("btn_authorize", lang), callback_data=AdminCB(a="auth", v=str(group_id)).pack()
    )
    return assert_fits(builder.as_markup())


def history_keyboard(
    entries, page: int, pages: int, flow: str, owner: int, lang: str, can_delete: bool = False
) -> InlineKeyboardMarkup:
    """Paging for everyone; a Delete button per live entry only for the admin.

    Reading history is open to the whole group, but deleting is not. Hiding the
    buttons is presentation only - the handlers in `handlers/history.py` re-check
    `is_super_admin`, and that is what actually enforces it.
    """
    builder = InlineKeyboardBuilder()
    for e in entries:
        if not can_delete or e["voided_at"] is not None:
            continue
        ref = f"{'e' if e['kind'] == 'expense' else 's'}{e['id']}"
        builder.row(
            InlineKeyboardButton(
                # Same E7/S3 label the entry itself carries, so the button
                # is unambiguous when both kinds share an id number.
                text=t("btn_delete", lang, id=ref.upper()),
                callback_data=FlowCB(t=flow, o=owner, a="hdel", v=ref).pack(),
            )
        )

    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(
                text=t("btn_prev", lang),
                callback_data=FlowCB(t=flow, o=owner, a="hpage", v=str(page - 1)).pack(),
            )
        )
    if page < pages:
        nav.append(
            InlineKeyboardButton(
                text=t("btn_next", lang),
                callback_data=FlowCB(t=flow, o=owner, a="hpage", v=str(page + 1)).pack(),
            )
        )
    if nav:
        builder.row(*nav)

    markup = assert_fits(builder.as_markup())
    # A member reading a single page of history has neither delete buttons nor
    # paging, which would send Telegram a reply_markup whose inline_keyboard is
    # an empty array. Send no markup at all rather than an empty one.
    return markup if markup.inline_keyboard else None


def delete_confirm_keyboard(ref: str, flow: str, owner: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("btn_yes", lang), callback_data=FlowCB(t=flow, o=owner, a="hdelok", v=ref).pack()
    )
    builder.button(
        text=t("btn_no", lang), callback_data=FlowCB(t=flow, o=owner, a="hpage", v="1").pack()
    )
    builder.adjust(2)
    return assert_fits(builder.as_markup())


# ---------------------------------------------------------------------------
# Admin group panel (private chat only)
#
# These use AdminCB, which carries no flow token and no owner: the panel only
# ever exists in the administrator's own private chat, and every handler
# re-checks `is_super_admin`. That is the security boundary, and it also means
# the menu survives a restart instead of expiring like the group wizards do.
# ---------------------------------------------------------------------------

GROUPS_PAGE_SIZE = 8

# Group titles are user-supplied and can be long; a button that wraps is worse
# than one that is trimmed.
MAX_BUTTON_TITLE = 24


def _trim(text: str, limit: int = MAX_BUTTON_TITLE) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def groups_panel_keyboard(
    groups, page: int, pages: int, lang: str, other_lang: str, other_lang_name: str
) -> InlineKeyboardMarkup:
    """The group list: one button per group, plus Add and the language toggle."""
    builder = InlineKeyboardBuilder()
    for g in groups:
        mark = "✅" if g.is_active else "⛔"
        builder.row(
            InlineKeyboardButton(
                text=f"{mark} {_trim(g.title)}",
                callback_data=AdminCB(a="gopen", v=str(g.group_id)).pack(),
            )
        )

    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(
                text=t("btn_prev", lang), callback_data=AdminCB(a="glist", v=str(page - 1)).pack()
            )
        )
    if page < pages:
        nav.append(
            InlineKeyboardButton(
                text=t("btn_next", lang), callback_data=AdminCB(a="glist", v=str(page + 1)).pack()
            )
        )
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(
            text=t("btn_add_group", lang), callback_data=AdminCB(a="gadd").pack()
        ),
        InlineKeyboardButton(
            text=t("btn_language", lang, name=other_lang_name),
            callback_data=AdminCB(a="glang", v=other_lang).pack(),
        ),
    )
    return assert_fits(builder.as_markup())


def group_detail_keyboard(group, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if group.is_active:
        builder.row(
            InlineKeyboardButton(
                text=t("btn_revoke_group", lang),
                callback_data=AdminCB(a="grevoke", v=str(group.group_id)).pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=t("btn_authorize_group", lang),
                callback_data=AdminCB(a="gauth", v=str(group.group_id)).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=t("btn_delete_group", lang),
            callback_data=AdminCB(a="gdel", v=str(group.group_id)).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(text=t("btn_back", lang), callback_data=AdminCB(a="glist", v="1").pack())
    )
    return assert_fits(builder.as_markup())


def group_delete_keyboard(group_id: int, entries: int, lang: str) -> InlineKeyboardMarkup:
    """Confirm permanent deletion.

    The entry count travels in the callback data so the handler can refuse if
    the group has changed since this menu was drawn - a destructive confirm
    must apply to the thing that was actually shown, not to whatever the group
    happens to hold when the button is finally pressed.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("btn_delete_group_confirm", lang),
            callback_data=AdminCB(a="gdelok", v=f"{group_id}|{entries}").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("btn_back", lang), callback_data=AdminCB(a="gopen", v=str(group_id)).pack()
        )
    )
    return assert_fits(builder.as_markup())
