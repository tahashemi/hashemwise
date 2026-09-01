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
        for command in (
            "/expense", "/settle", "/balances", "/members", "/history", "/cancel", "/setup"
        ):
            assert command in text, command

    def test_admin_commands_hidden_from_ordinary_members(self):
        # Listing commands that only answer "you can't do that" is noise.
        text = help_text("en", include_admin=False)
        assert "/auth" not in text and "/deauth" not in text

    def test_admin_commands_shown_to_the_admin(self):
        text = help_text("en", include_admin=True)
        assert "/auth" in text and "/groups" in text

    @pytest.mark.parametrize("lang", ["en", "fa"])
    def test_history_is_offered_to_everyone(self, lang):
        # Reading history is open to the whole group; only deleting is not.
        assert "/history" in help_text(lang, include_admin=False)

    @pytest.mark.parametrize("lang", ["en", "fa"])
    def test_version_is_offered_to_everyone(self, lang):
        assert "/version" in help_text(lang, include_admin=False)

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


class TestCommandsAreNotSwallowedMidWizard:
    """A handler bound only to a state matches *any* message in that state.

    Every one of ours waits on a ForceReply, so without a reply filter an
    abandoned wizard silently ate later commands - /history among them, because
    its router is registered after the expense and settle routers.
    """

    HANDLER_MODULES = ["expense.py", "settle.py", "setup.py", "groups.py", "history.py"]

    def _state_bound_decorators(self):
        """Every `@router.message(SomeStates.x, ...)` in the handler modules."""
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "src" / "handlers"
        found = []
        for name in self.HANDLER_MODULES:
            tree = ast.parse((root / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.AsyncFunctionDef):
                    continue
                for dec in node.decorator_list:
                    if not isinstance(dec, ast.Call):
                        continue
                    target = ast.unparse(dec.func)
                    if not target.endswith("router.message"):
                        continue
                    args = [ast.unparse(a) for a in dec.args]
                    if args and args[0].endswith("States." + args[0].split(".")[-1]) and "States." in args[0]:
                        found.append((name, node.name, args))
        return found

    def test_there_are_some_to_check(self):
        assert self._state_bound_decorators(), "no state-bound message handlers found"

    def test_every_state_handler_also_requires_a_reply(self):
        offenders = [
            f"{module}:{func}"
            for module, func, args in self._state_bound_decorators()
            if not any("reply_to_message" in a for a in args)
        ]
        assert not offenders, (
            f"{offenders} match any message in their state and will swallow "
            "commands such as /history from a user with an abandoned wizard"
        )
