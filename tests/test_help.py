"""The /help text, and the command menu published to Telegram."""

import pytest

from src.handlers.help import help_text
from src.i18n.en import COMMANDS as EN_COMMANDS
from src.i18n.fa import COMMANDS as FA_COMMANDS
from src.main import command_menu


class TestHelpText:
    @pytest.mark.parametrize("lang", ["en", "fa"])
    def test_mentions_every_everyday_command(self, lang):
        text = help_text(lang, include_admin=False)
        for command in ("/expense", "/settle", "/balances", "/members", "/cancel", "/setup"):
            assert command in text, command

    def test_admin_commands_hidden_from_ordinary_members(self):
        # Listing commands that only answer "you can't do that" is noise.
        text = help_text("en", include_admin=False)
        assert "/history" not in text and "/auth" not in text

    def test_admin_commands_shown_to_the_admin(self):
        text = help_text("en", include_admin=True)
        assert "/history" in text and "/auth" in text

    @pytest.mark.parametrize("lang", ["en", "fa"])
    def test_explains_the_surprising_behaviours(self, lang):
        text = help_text(lang, include_admin=True)
        assert len(text) > 400  # the notes section is present, not just a command list

    @pytest.mark.parametrize("lang", ["en", "fa"])
    def test_html_is_balanced(self, lang):
        import re

        text = help_text(lang, include_admin=True)
        assert sorted(re.findall(r"<(\w+)>", text)) == sorted(re.findall(r"</(\w+)>", text))

    @pytest.mark.parametrize("lang", ["en", "fa"])
    def test_fits_in_one_telegram_message(self, lang):
        assert len(help_text(lang, include_admin=True)) < 4096


class TestCommandMenu:
    def test_both_languages_list_the_same_commands(self):
        assert [c for c, _ in EN_COMMANDS] == [c for c, _ in FA_COMMANDS]

    @pytest.mark.parametrize("lang", ["en", "fa"])
    def test_menu_entries_satisfy_telegram_limits(self, lang):
        for entry in command_menu(lang):
            assert entry.command == entry.command.lower()
            assert 1 <= len(entry.command) <= 32
            assert 1 <= len(entry.description) <= 256

    def test_help_is_in_the_menu(self):
        assert "help" in [c.command for c in command_menu("en")]
