"""Translation catalogues must stay in lockstep."""

import re
import string

import pytest

from src.i18n import CATALOG, DEFAULT_LANG, t
from src.i18n.en import STRINGS as EN
from src.i18n.fa import STRINGS as FA


def placeholders(template: str) -> set[str]:
    return {
        field
        for _, field, _, _ in string.Formatter().parse(template)
        if field is not None
    }


class TestCatalogueParity:
    def test_same_keys_in_every_language(self):
        assert set(EN) == set(FA), {
            "missing_from_fa": sorted(set(EN) - set(FA)),
            "missing_from_en": sorted(set(FA) - set(EN)),
        }

    @pytest.mark.parametrize("key", sorted(EN))
    def test_same_placeholders_in_every_language(self, key):
        # A placeholder present in one language and absent in the other means
        # that string silently drops information for some groups.
        assert placeholders(EN[key]) == placeholders(FA[key]), key

    @pytest.mark.parametrize("lang", sorted(CATALOG))
    def test_no_empty_strings(self, lang):
        assert all(v.strip() for v in CATALOG[lang].values())

    @pytest.mark.parametrize("lang", sorted(CATALOG))
    def test_html_tags_are_balanced(self, lang):
        # Telegram rejects a message whose HTML does not close, which would
        # fail the send rather than just look wrong.
        for key, value in CATALOG[lang].items():
            opened = re.findall(r"<(\w+)>", value)
            closed = re.findall(r"</(\w+)>", value)
            assert sorted(opened) == sorted(closed), f"{lang}/{key}"


class TestLookup:
    def test_plain_lookup(self):
        assert t("cancelled", "en") == EN["cancelled"]
        assert t("cancelled", "fa") == FA["cancelled"]

    def test_substitution(self):
        assert "Ali" in t("join_done", "en", name="Ali")

    def test_unknown_language_falls_back_to_default(self):
        assert t("cancelled", "de") == CATALOG[DEFAULT_LANG]["cancelled"]

    def test_missing_key_returns_the_key_rather_than_raising(self, caplog):
        assert t("no_such_key_anywhere", "en") == "no_such_key_anywhere"

    def test_missing_placeholder_returns_the_template_rather_than_raising(self):
        # A handler must not crash and lose the user's half-entered expense
        # just because a string was formatted with the wrong argument.
        assert t("join_done", "en") == EN["join_done"]


class TestNoDuplicateKeys:
    """A repeated key in a dict literal is silently dropped by Python.

    The parity test cannot see it, because by the time the module is imported
    only the last value survives. Parsing the source is the only way to catch
    a translation that was quietly overwritten.
    """

    @pytest.mark.parametrize("path", ["src/i18n/en.py", "src/i18n/fa.py"])
    def test_no_key_is_defined_twice(self, path):
        import ast
        import collections
        from pathlib import Path

        source = (Path(__file__).resolve().parent.parent / path).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Dict):
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
                duplicates = [k for k, n in collections.Counter(keys).items() if n > 1]
                assert not duplicates, f"{path} defines {duplicates} more than once"
