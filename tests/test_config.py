"""Configuration must fail loudly, not produce a plausible-looking wrong setup."""

import pytest
from pydantic import ValidationError

from src.config import Settings


def _settings(**over):
    base = {"BOT_TOKEN": "123456:abcdef", "SUPER_ADMIN_ID": "42"}
    base.update(over)
    return Settings(_env_file=None, **base)


class TestBotToken:
    def test_valid_token(self):
        assert _settings().bot_token == "123456:abcdef"

    def test_surrounding_quotes_are_stripped(self):
        assert _settings(BOT_TOKEN='"123456:abcdef"').bot_token == "123456:abcdef"

    @pytest.mark.parametrize("bad", ["", "abcdef", "notdigits:secret", "BOT_TOKEN=1:2"])
    def test_malformed_token_rejected(self, bad):
        with pytest.raises(ValidationError):
            _settings(BOT_TOKEN=bad)


class TestSuperAdminId:
    def test_positive_user_id(self):
        assert _settings(SUPER_ADMIN_ID="777").super_admin_id == 777

    @pytest.mark.parametrize("bad", ["0", "-1001234567890"])
    def test_chat_id_or_zero_rejected(self, bad):
        # A negative id is a chat, not a user; accepting it would silently
        # lock every admin command out.
        with pytest.raises(ValidationError):
            _settings(SUPER_ADMIN_ID=bad)


class TestDefaults:
    def test_db_path_and_proxy_defaults(self):
        s = _settings()
        assert s.db_path.as_posix() == "data/ledger.db"
        assert s.telegram_proxy == ""
        assert s.log_level == "INFO"

    def test_log_level_normalized(self):
        assert _settings(LOG_LEVEL="debug").log_level == "DEBUG"

    def test_unknown_log_level_rejected(self):
        with pytest.raises(ValidationError):
            _settings(LOG_LEVEL="chatty")
