"""Hashemwise - translation lookup.

`t(key, lang, **params)` is the only entry point. A missing key or a missing
placeholder returns something visible and logs loudly rather than raising: a
typo in a rarely-used string should not take a handler down mid-flow and lose
what the user was in the middle of entering. The test suite asserts both
catalogues have identical keys, so those cases do not reach production.
"""

from __future__ import annotations

import logging

from src.i18n.en import STRINGS as EN
from src.i18n.fa import STRINGS as FA

log = logging.getLogger(__name__)

CATALOG: dict[str, dict[str, str]] = {"en": EN, "fa": FA}
DEFAULT_LANG = "en"

LANG_NAMES = {"en": "English", "fa": "فارسی"}


def t(key: str, lang: str = DEFAULT_LANG, **params: object) -> str:
    """Look up `key` in `lang`, falling back to English then to the key itself."""
    catalog = CATALOG.get(lang) or CATALOG[DEFAULT_LANG]
    template = catalog.get(key)

    if template is None:
        template = CATALOG[DEFAULT_LANG].get(key)
        if template is None:
            log.error("missing translation key %r", key)
            return key
        log.warning("key %r missing from %r catalogue; used English", key, lang)

    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError) as exc:
        log.error("bad placeholder in %r/%r: %s", lang, key, exc)
        return template
