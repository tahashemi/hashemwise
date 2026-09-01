"""English strings."""

STRINGS: dict[str, str] = {
    # -- general ----------------------------------------------------------
    "app_name": "Hashemwise",
    "start_group": (
        "<b>Hashemwise</b> keeps track of who paid for what.\n\n"
        "/expense - record an expense\n"
        "/settle - record a payment between two people\n"
        "/balances - who owes whom\n"
        "/members - list members\n"
        "/help - what everything does\n"
        "/cancel - abandon whatever you are in the middle of"
    ),
    "start_private": (
        "<b>Hashemwise</b> tracks shared expenses inside a Telegram group.\n\n"
        "Add me to a group, then run /setup there. I do not keep any ledger in "
        "private chats.\n\n"
        "/help - what everything does"
    ),
    "help_title": "<b>Hashemwise</b> - what everything does",
    "help_intro": (
        "I keep track of who paid for what, and work out the shortest set of "
        "payments that squares everyone up."
    ),
    "help_start": (
        "<b>Getting started</b>\n"
        "1. /setup - choose the currency and language, then send the member "
        "names, one per line.\n"
        "2. Everyone runs /join once and taps their own name, linking their "
        "Telegram account.\n"
        "3. /expense every time someone pays for something."
    ),
    "help_daily": (
        "<b>Day to day</b>\n"
        "/expense - record an expense. Asks the amount, what it was for, who "
        "paid, who shares it, and whether to divide it equally or by exact "
        "amounts. Nothing is saved until you confirm.\n"
        "/settle - record that one person handed money to another.\n"
        "/balances - who owes what, and the shortest list of payments that "
        "clears the group.\n"
        "/members - everyone in the group, and who has linked an account.\n"
        "/history - everything recorded here, with exactly what each person was "
        "charged. Anyone can read it; only the bot administrator can delete.\n"
        "/version - which version of me is running.\n"
        "/cancel - abandon whatever you are in the middle of."
    ),
    "help_admin": (
        "<b>Bot administrator only</b>\n"
        "/groups - in our private chat, manage every group: authorize, revoke, "
        "add one by its chat id, or delete one and its whole ledger.\n"
        "/auth, /deauth - authorize or revoke the group you are standing in.\n"
        "Delete buttons in /history are yours alone."
    ),
    "help_notes": (
        "<b>Worth knowing</b>\n"
        "- When a total will not divide evenly, whoever paid covers the odd "
        "one. The exact split is always shown before anything is saved.\n"
        "- Deleting never erases anything: the entry is struck through and "
        "stops counting toward the balances.\n"
        "- The currency is fixed once the group has entries, because old "
        "amounts cannot be reinterpreted in a new one."
    ),
    "cancelled": "Cancelled.",
    "nothing_to_cancel": "You are not in the middle of anything.",
    "btn_cancel": "Cancel",
    "btn_back": "← Back",
    "btn_done": "Done",
    "btn_confirm": "Confirm",
    "btn_yes": "Yes",
    "btn_no": "No",
    # -- access -----------------------------------------------------------
    "unauthorized_group": (
        "This group is not authorized to use Hashemwise. "
        "Ask the bot administrator to approve it."
    ),
    "admin_only": "Only the bot administrator can do that.",
    "group_only": "That only works inside a group.",
    "private_only": "Send that to me in a private chat.",
    "not_setup": "This group is not set up yet. Run /setup first.",
    "not_a_member": "You are not one of this group's members. Run /join first.",
    "not_your_menu": "That menu belongs to someone else.",
    "menu_expired": "This menu has expired. Start again.",
    # -- admin ------------------------------------------------------------
    "new_group_pending": (
        "Added to a new group.\n\n<b>{title}</b>\nChat id: <code>{group_id}</code>\n\n"
        "It cannot be used until you authorize it."
    ),
    "btn_authorize": "Authorize",
    "auth_done": "Authorized. Run /setup in the group to configure it.",
    "auth_already": "That group is already authorized.",
    "deauth_done": "Authorization revoked. The ledger is kept.",
    "groups_header": "<b>Groups</b>",
    "groups_empty": "I have not been added to any group yet.",
    "group_row": "{mark} <b>{title}</b>\n    <code>{group_id}</code> - {currency}, {lang}",
    # -- admin group panel (private chat) ---------------------------------
    "panel_header": "<b>Groups</b> ({count})\nTap one to manage it.",
    "panel_empty": (
        "<b>Groups</b>\n\nI am not in any group yet. Add me to one, or press "
        "the button below if you know its chat id."
    ),
    "panel_page": "<b>Groups</b> ({count}) - page {page} of {pages}\nTap one to manage it.",
    "btn_add_group": "➕ Add a group",
    "btn_language": "🌐 {name}",
    "group_detail": (
        "{mark} <b>{title}</b>\n"
        "<code>{group_id}</code>\n"
        "{currency} · {lang} · {members} member(s) · {entries} entr(y/ies)"
    ),
    "group_detail_active": "This group can use me.",
    "group_detail_revoked": "This group is revoked and cannot use me.",
    "btn_authorize_group": "✅ Authorize",
    "btn_revoke_group": "⛔ Revoke access",
    "btn_delete_group": "🗑 Delete permanently",
    "group_revoked": "Access revoked. The ledger is kept and re-authorizing restores it.",
    "group_authorized": "Authorized.",
    "group_gone": "That group is no longer here. The list has been refreshed.",
    "group_delete_confirm": (
        "<b>Delete {title}?</b>\n\n"
        "This removes the group, its {members} member(s) and all {entries} "
        "recorded entr(y/ies), permanently.\n\n"
        "<b>There is no undo.</b> To keep the ledger and only stop the bot "
        "working there, revoke access instead."
    ),
    "btn_delete_group_confirm": "Yes, delete everything",
    "group_deleted": "<b>{title}</b> and all of its data have been deleted.",
    "group_changed_since": (
        "That group has changed since this menu was drawn, so I have not "
        "deleted anything. Open it again and check."
    ),
    "group_add_prompt": (
        "Send me the group's chat id - a negative number like "
        "<code>-1001234567890</code>.\n\n"
        "I must already be a member of it. If I am not, add me to the group "
        "first; you can get the id from @userinfobot by forwarding a message "
        "from that group to it."
    ),
    "group_add_bad_id": "That is not a chat id. It should be a negative number.",
    "group_add_unreachable": (
        "I cannot see a chat with that id. Add me to the group first, then try "
        "again."
    ),
    "group_add_not_a_group": "That id is not a group.",
    "group_add_done": "<b>{title}</b> added and authorized.",
    "group_add_already": "<b>{title}</b> was already here. It is authorized now.",
    "admin_lang_set": "Admin language set to {name}.",
    # -- version ----------------------------------------------------------
    "version_line": "Hashemwise <b>v{version}</b>",
    # -- setup ------------------------------------------------------------
    "setup_currency": "Which currency does this group use?",
    "setup_currency_locked": (
        "This group already has entries recorded in {currency}. The currency "
        "cannot be changed, because there is no exchange rate to reinterpret "
        "the existing amounts with."
    ),
    "setup_lang": "Which language should I speak here?",
    "setup_members_prompt": (
        "Now send me the members, <b>one name per line</b>.\n\n"
        "For example:\n<code>Ali\nBita\nCyrus</code>\n\n"
        "Use whatever names the group actually calls each other. Each person "
        "can link their own Telegram account afterwards with /join."
    ),
    "setup_members_added": "Added: {names}",
    "setup_members_skipped": "Already a member, skipped: {names}",
    "setup_complete": (
        "<b>Setup complete.</b>\nCurrency: {currency}\nMembers: {count}\n\n"
        "Everyone should run /join to link their Telegram account. "
        "Then /expense to record the first one."
    ),
    "setup_need_two_members": "A group needs at least two members. Send some more names.",
    # -- members ----------------------------------------------------------
    "members_header": "<b>Members</b>",
    "members_empty": "No members yet. Run /setup.",
    "member_row_linked": "{name}",
    "member_row_ghost": "{name} <i>(no Telegram account linked)</i>",
    "member_row_inactive": "<s>{name}</s> <i>(inactive)</i>",
    "join_prompt": "Which of these are you?",
    "join_done": "Linked. You are <b>{name}</b>.",
    "join_already": "You are already linked as <b>{name}</b>.",
    "join_taken": "<b>{name}</b> is already linked to another account.",
    "join_none_free": "Every member is already linked to an account.",
    # -- expense ----------------------------------------------------------
    "expense_amount": "How much was it? ({currency})",
    "expense_description": "What was it for?",
    "expense_payer": "Who paid?",
    "expense_participants": "Who shares this? Tap to toggle, then press Done.",
    "expense_need_participant": "Pick at least one person.",
    "expense_split_type": "How should {amount} be divided?",
    "btn_split_equal": "Split equally",
    "btn_split_custom": "Enter each amount",
    "expense_custom_prompt": (
        "How much of {total} is <b>{name}</b>'s share?\n"
        "Remaining to assign: <b>{remaining}</b>"
    ),
    "expense_custom_over": (
        "That is more than the amount left to assign ({remaining}). Try again."
    ),
    "expense_confirm": (
        "<b>{description}</b>\n{amount} paid by {payer}\n\n{shares}\n\nRecord it?"
    ),
    "expense_share_row": "  {name}: {amount}",
    "expense_share_row_payer": "  {name}: {amount}  <i>(payer)</i>",
    "expense_remainder_note": (
        "<i>{amount} did not divide evenly; the payer covers the odd {unit}.</i>"
    ),
    "expense_saved": "Recorded: <b>{description}</b>, {amount}, paid by {payer}.",
    # -- settle -----------------------------------------------------------
    "settle_payer": "Who handed over the money?",
    "settle_payee": "Who received it?",
    "settle_same_person": "Pick a different person.",
    "settle_amount": "How much did {payer} give {payee}? ({currency})",
    "settle_confirm": "<b>{payer}</b> paid <b>{payee}</b> {amount}.\n\nRecord it?",
    "settle_saved": "Recorded: {payer} paid {payee} {amount}.",
    # -- balances ---------------------------------------------------------
    "balances_header": "<b>Balances</b>",
    "balances_all_settled": "Everyone is square. Nothing is owed.",
    "balances_is_owed": "  {name} is owed {amount}",
    "balances_owes": "  {name} owes {amount}",
    "balances_settled": "  {name} is settled",
    "plan_header": "<b>Suggested payments</b>",
    "plan_row": "  {payer} pays {payee} {amount}",
    "plan_note": "<i>{count} payment(s) clears the whole group.</i>",
    "no_entries_yet": "Nothing has been recorded in this group yet.",
    # -- history ----------------------------------------------------------
    "history_header": "<b>History</b> (page {page} of {pages})",
    "history_empty": "Nothing recorded yet.",
    "history_expense": "<b>#{id}</b>  {description}\n{amount} - paid by {payer} - {date}",
    "history_settlement": "<b>#{id}</b>  {payer} paid {payee}\n{amount} - {date}",
    "history_shares_label": "Split between:",
    "history_voided": "  <s>deleted</s>",
    "history_superseded": " <i>(replaces #{id})</i>",
    "btn_prev": "Previous",
    "btn_next": "Next",
    "btn_delete": "Delete #{id}",
    "btn_edit": "Edit #{id}",
    "history_delete_confirm": "Delete this entry?\n\n{summary}",
    "history_deleted": "Deleted. Balances updated.",
    "history_already_deleted": "That entry was already deleted.",
    "history_edit_start": (
        "Editing #{id}. The old entry will be deleted once you confirm the new one."
    ),
    # -- errors -----------------------------------------------------------
    "err_money": "That amount is not valid.",
    "err_amount_invalid": "I could not read that as a number. Try something like <code>{example}</code>.",
    "err_amount_non_positive": "The amount has to be greater than zero.",
    "err_amount_too_precise": "{currency} allows at most {allowed} decimal place(s).",
    "err_amount_too_large": "That amount is implausibly large.",
    "err_no_participants": "Pick at least one person.",
    "err_negative_share": "A share cannot be negative.",
    "err_split_mismatch": "The shares add up to {sum}, but the total is {total}.",
    "err_ledger_imbalance": (
        "Something is wrong with this group's ledger and the numbers cannot be "
        "trusted, so I will not show them. The administrator has been notified."
    ),
    "err_member_duplicate": "There is already a member with that name.",
    "err_member_in_use": (
        "{name} already appears in the ledger and cannot be removed. "
        "You can mark them inactive instead."
    ),
    "err_description_empty": "Give it a short description.",
    "err_too_long": "That is too long. Keep it under {limit} characters.",
    "err_unexpected": "Something went wrong. Nothing was saved.",
}

# Descriptions for Telegram's own "/" command menu.
COMMANDS: list[tuple[str, str]] = [
    ("expense", "Record an expense"),
    ("settle", "Record a payment between two people"),
    ("balances", "Who owes whom"),
    ("history", "Everything recorded, and each person's share"),
    ("members", "List the group's members"),
    ("join", "Link your Telegram account to a name"),
    ("setup", "Configure this group"),
    ("help", "What everything does"),
    ("cancel", "Abandon the current step"),
]
