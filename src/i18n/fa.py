"""Persian strings.

Layout note: balances are rendered one person per line rather than in a table.
Mixing Western digits into RTL prose makes Telegram reorder things
unpredictably. The per-person split tables in /history are the exception - they
go inside a <pre> block whose lines are prefixed with a left-to-right mark, so
the columns stay aligned regardless of the surrounding text direction.
"""

STRINGS: dict[str, str] = {
    # -- general ----------------------------------------------------------
    "app_name": "هاشم‌وایز",
    "start_group": (
        "<b>هاشم‌وایز</b> حساب اینکه چه کسی چه چیزی را پرداخت کرده نگه می‌دارد.\n\n"
        "/expense - ثبت یک هزینه\n"
        "/settle - ثبت پرداخت بین دو نفر\n"
        "/balances - چه کسی به چه کسی بدهکار است\n"
        "/members - فهرست اعضا\n"
        "/help - هر بخش چه کاری می‌کند\n"
        "/cancel - لغو کاری که در حال انجامش هستید"
    ),
    "start_private": (
        "<b>هاشم‌وایز</b> هزینه‌های مشترک را داخل یک گروه تلگرام حساب می‌کند.\n\n"
        "مرا به یک گروه اضافه کنید و آنجا /setup را اجرا کنید. "
        "در گفتگوی خصوصی هیچ حسابی نگه نمی‌دارم.\n\n"
        "/help - هر بخش چه کاری می‌کند"
    ),
    "help_title": "<b>هاشم‌وایز</b> - هر بخش چه کاری می‌کند",
    "help_intro": (
        "من حساب اینکه چه کسی چه چیزی را پرداخت کرده نگه می‌دارم و کوتاه‌ترین "
        "مجموعه پرداخت‌ها را که حساب همه را صاف می‌کند حساب می‌کنم."
    ),
    "help_start": (
        "<b>شروع کار</b>\n"
        "۱. /setup - واحد پول و زبان را انتخاب کنید، بعد نام اعضا را هر کدام "
        "در یک خط بفرستید.\n"
        "۲. هر نفر یک بار /join را اجرا می‌کند و روی نام خودش می‌زند تا حساب "
        "تلگرامش وصل شود.\n"
        "۳. هر بار کسی چیزی پرداخت کرد، /expense."
    ),
    "help_daily": (
        "<b>کارهای روزمره</b>\n"
        "/expense - ثبت یک هزینه. مبلغ، بابت چه چیزی، چه کسی پرداخت کرده، بین "
        "چه کسانی تقسیم می‌شود، و اینکه مساوی تقسیم شود یا با مبالغ دقیق را "
        "می‌پرسد. تا تأیید نکنید چیزی ذخیره نمی‌شود.\n"
        "/settle - ثبت اینکه یک نفر به دیگری پول داده است.\n"
        "/balances - چه کسی چقدر بدهکار است، و کوتاه‌ترین فهرست پرداخت‌هایی که "
        "حساب گروه را صاف می‌کند.\n"
        "/members - همه اعضای گروه، و اینکه چه کسی حسابش را وصل کرده.\n"
        "/cancel - لغو کاری که در حال انجامش هستید."
    ),
    "help_admin": (
        "<b>فقط مدیر ربات</b>\n"
        "/history - همه موارد ثبت‌شده با ریز سهم هر نفر، و دکمه‌ای برای حذف "
        "اشتباهات.\n"
        "/auth، /deauth، /groups - تعیین اینکه چه گروه‌هایی می‌توانند از من "
        "استفاده کنند."
    ),
    "help_notes": (
        "<b>خوب است بدانید</b>\n"
        "- وقتی مبلغ دقیق تقسیم نشود، باقی‌مانده به عهده پرداخت‌کننده است. "
        "سهم دقیق هر نفر همیشه پیش از ذخیره نشان داده می‌شود.\n"
        "- حذف هیچ‌وقت چیزی را پاک نمی‌کند: مورد خط‌خورده می‌شود و دیگر در "
        "مانده حساب‌ها به حساب نمی‌آید.\n"
        "- واحد پول پس از ثبت اولین مورد قفل می‌شود، چون مبالغ قبلی را نمی‌توان "
        "با واحد جدید بازتفسیر کرد."
    ),
    "cancelled": "لغو شد.",
    "nothing_to_cancel": "کاری در جریان نیست.",
    "btn_cancel": "لغو",
    "btn_back": "بازگشت",
    "btn_done": "تمام",
    "btn_confirm": "تأیید",
    "btn_yes": "بله",
    "btn_no": "خیر",
    # -- access -----------------------------------------------------------
    "unauthorized_group": (
        "این گروه مجاز به استفاده از هاشم‌وایز نیست. "
        "از مدیر ربات بخواهید آن را تأیید کند."
    ),
    "admin_only": "فقط مدیر ربات می‌تواند این کار را انجام دهد.",
    "group_only": "این فقط داخل گروه کار می‌کند.",
    "private_only": "این را در گفتگوی خصوصی برای من بفرستید.",
    "not_setup": "این گروه هنوز تنظیم نشده است. ابتدا /setup را اجرا کنید.",
    "not_a_member": "شما جزو اعضای این گروه نیستید. ابتدا /join را اجرا کنید.",
    "not_your_menu": "این منو متعلق به شخص دیگری است.",
    "menu_expired": "این منو منقضی شده است. دوباره شروع کنید.",
    # -- admin ------------------------------------------------------------
    "new_group_pending": (
        "به یک گروه جدید اضافه شدم.\n\n<b>{title}</b>\nشناسه گروه: <code>{group_id}</code>\n\n"
        "تا زمانی که آن را تأیید نکنید قابل استفاده نیست."
    ),
    "btn_authorize": "تأیید",
    "auth_done": "تأیید شد. برای تنظیم، در گروه /setup را اجرا کنید.",
    "auth_already": "این گروه از قبل تأیید شده است.",
    "deauth_done": "تأیید لغو شد. اطلاعات حساب حفظ شد.",
    "groups_header": "<b>گروه‌ها</b>",
    "groups_empty": "هنوز به هیچ گروهی اضافه نشده‌ام.",
    "group_row": "{mark} <b>{title}</b>\n    <code>{group_id}</code> - {currency}، {lang}",
    # -- setup ------------------------------------------------------------
    "setup_currency": "این گروه از چه واحد پولی استفاده می‌کند؟",
    "setup_currency_locked": (
        "در این گروه از قبل مواردی به {currency} ثبت شده است. واحد پول قابل "
        "تغییر نیست، چون نرخ تبدیلی وجود ندارد که مبالغ قبلی را با آن بازتفسیر کنیم."
    ),
    "setup_lang": "اینجا به چه زبانی صحبت کنم؟",
    "setup_members_prompt": (
        "حالا اعضا را برایم بفرستید، <b>هر نام در یک خط</b>.\n\n"
        "برای مثال:\n<code>علی\nبیتا\nکوروش</code>\n\n"
        "همان نام‌هایی را بنویسید که واقعاً همدیگر را صدا می‌زنید. هر نفر بعداً "
        "می‌تواند با /join حساب تلگرام خودش را وصل کند."
    ),
    "setup_members_added": "اضافه شد: {names}",
    "setup_members_skipped": "از قبل عضو بود، رد شد: {names}",
    "setup_complete": (
        "<b>تنظیم کامل شد.</b>\nواحد پول: {currency}\nتعداد اعضا: {count}\n\n"
        "همه باید /join را اجرا کنند تا حساب تلگرامشان وصل شود. "
        "بعد با /expense اولین هزینه را ثبت کنید."
    ),
    "setup_need_two_members": "یک گروه حداقل به دو عضو نیاز دارد. نام‌های بیشتری بفرستید.",
    # -- members ----------------------------------------------------------
    "members_header": "<b>اعضا</b>",
    "members_empty": "هنوز عضوی نیست. /setup را اجرا کنید.",
    "member_row_linked": "{name}",
    "member_row_ghost": "{name} <i>(حساب تلگرام وصل نشده)</i>",
    "member_row_inactive": "<s>{name}</s> <i>(غیرفعال)</i>",
    "join_prompt": "کدام‌یک از این‌ها شما هستید؟",
    "join_done": "وصل شد. شما <b>{name}</b> هستید.",
    "join_already": "شما از قبل به عنوان <b>{name}</b> وصل شده‌اید.",
    "join_taken": "<b>{name}</b> از قبل به حساب دیگری وصل شده است.",
    "join_none_free": "همه اعضا از قبل به یک حساب وصل شده‌اند.",
    # -- expense ----------------------------------------------------------
    "expense_amount": "مبلغ چقدر بود؟ ({currency})",
    "expense_description": "بابت چه چیزی بود؟",
    "expense_payer": "چه کسی پرداخت کرد؟",
    "expense_participants": "این هزینه بین چه کسانی تقسیم می‌شود؟ برای انتخاب بزنید، بعد تمام را بزنید.",
    "expense_need_participant": "حداقل یک نفر را انتخاب کنید.",
    "expense_split_type": "{amount} چطور تقسیم شود؟",
    "btn_split_equal": "تقسیم مساوی",
    "btn_split_custom": "وارد کردن سهم هر نفر",
    "expense_custom_prompt": (
        "سهم <b>{name}</b> از {total} چقدر است؟\n"
        "باقی‌مانده برای تقسیم: <b>{remaining}</b>"
    ),
    "expense_custom_over": "این بیشتر از باقی‌مانده ({remaining}) است. دوباره وارد کنید.",
    "expense_confirm": (
        "<b>{description}</b>\n{amount} پرداخت‌شده توسط {payer}\n\n{shares}\n\nثبت شود؟"
    ),
    "expense_share_row": "  {name}: {amount}",
    "expense_share_row_payer": "  {name}: {amount}  <i>(پرداخت‌کننده)</i>",
    "expense_remainder_note": (
        "<i>{amount} دقیق تقسیم نشد؛ باقی‌مانده {unit} به عهده پرداخت‌کننده است.</i>"
    ),
    "expense_saved": "ثبت شد: <b>{description}</b>، {amount}، پرداخت‌شده توسط {payer}.",
    # -- settle -----------------------------------------------------------
    "settle_payer": "چه کسی پول را داد؟",
    "settle_payee": "چه کسی آن را گرفت؟",
    "settle_same_person": "یک نفر دیگر را انتخاب کنید.",
    "settle_amount": "{payer} چقدر به {payee} داد؟ ({currency})",
    "settle_confirm": "<b>{payer}</b> مبلغ {amount} به <b>{payee}</b> پرداخت کرد.\n\nثبت شود؟",
    "settle_saved": "ثبت شد: {payer} مبلغ {amount} به {payee} پرداخت کرد.",
    # -- balances ---------------------------------------------------------
    "balances_header": "<b>مانده حساب‌ها</b>",
    "balances_all_settled": "حساب همه صاف است. کسی به کسی بدهکار نیست.",
    "balances_is_owed": "  {name} طلبکار است: {amount}",
    "balances_owes": "  {name} بدهکار است: {amount}",
    "balances_settled": "  حساب {name} صاف است",
    "plan_header": "<b>پرداخت‌های پیشنهادی</b>",
    "plan_row": "  {payer} به {payee} می‌پردازد: {amount}",
    "plan_note": "<i>با {count} پرداخت حساب کل گروه صاف می‌شود.</i>",
    "no_entries_yet": "هنوز چیزی در این گروه ثبت نشده است.",
    # -- history ----------------------------------------------------------
    "history_header": "<b>تاریخچه</b> (صفحه {page} از {pages})",
    "history_empty": "هنوز چیزی ثبت نشده است.",
    "history_expense": "<b>#{id}</b>  {description}\n{amount} - پرداخت‌شده توسط {payer} - {date}",
    "history_settlement": "<b>#{id}</b>  {payer} به {payee} پرداخت کرد\n{amount} - {date}",
    "history_shares_label": "تقسیم بین:",
    "history_voided": "  <s>حذف‌شده</s>",
    "history_superseded": " <i>(جایگزین #{id})</i>",
    "btn_prev": "قبلی",
    "btn_next": "بعدی",
    "btn_delete": "حذف #{id}",
    "btn_edit": "ویرایش #{id}",
    "history_delete_confirm": "این مورد حذف شود؟\n\n{summary}",
    "history_deleted": "حذف شد. مانده حساب‌ها به‌روز شد.",
    "history_already_deleted": "این مورد از قبل حذف شده بود.",
    "history_edit_start": "ویرایش #{id}. مورد قبلی پس از تأیید مورد جدید حذف می‌شود.",
    # -- errors -----------------------------------------------------------
    "err_money": "این مبلغ معتبر نیست.",
    "err_amount_invalid": "نتوانستم این را به عنوان عدد بخوانم. چیزی مثل <code>{example}</code> بنویسید.",
    "err_amount_non_positive": "مبلغ باید بزرگ‌تر از صفر باشد.",
    "err_amount_too_precise": "{currency} حداکثر {allowed} رقم اعشار می‌پذیرد.",
    "err_amount_too_large": "این مبلغ به طور غیرمنطقی بزرگ است.",
    "err_no_participants": "حداقل یک نفر را انتخاب کنید.",
    "err_negative_share": "سهم نمی‌تواند منفی باشد.",
    "err_split_mismatch": "مجموع سهم‌ها {sum} شد، ولی مبلغ کل {total} است.",
    "err_ledger_imbalance": (
        "مشکلی در حساب این گروه وجود دارد و اعداد قابل اعتماد نیستند، پس آن‌ها "
        "را نشان نمی‌دهم. به مدیر اطلاع داده شد."
    ),
    "err_member_duplicate": "عضوی با این نام از قبل وجود دارد.",
    "err_member_in_use": (
        "{name} از قبل در حساب‌ها ثبت شده و قابل حذف نیست. "
        "می‌توانید او را غیرفعال کنید."
    ),
    "err_description_empty": "یک توضیح کوتاه بنویسید.",
    "err_too_long": "این خیلی طولانی است. کمتر از {limit} کاراکتر بنویسید.",
    "err_unexpected": "مشکلی پیش آمد. چیزی ذخیره نشد.",
}

# Descriptions for Telegram's own "/" command menu.
COMMANDS: list[tuple[str, str]] = [
    ("expense", "ثبت یک هزینه"),
    ("settle", "ثبت پرداخت بین دو نفر"),
    ("balances", "چه کسی به چه کسی بدهکار است"),
    ("members", "فهرست اعضای گروه"),
    ("join", "وصل کردن حساب تلگرام شما به یک نام"),
    ("setup", "تنظیم این گروه"),
    ("help", "هر بخش چه کاری می‌کند"),
    ("cancel", "لغو مرحله فعلی"),
]
