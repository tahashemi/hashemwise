"""The version string, and its agreement with the changelog."""

import re
from pathlib import Path

from src.version import __version__

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__


def test_changelog_exists():
    assert CHANGELOG.is_file()


def test_changelog_top_entry_matches_the_code():
    """A release whose changelog disagrees with the binary is worse than none."""
    headings = re.findall(r"^## (\d+\.\d+\.\d+)$", CHANGELOG.read_text(encoding="utf-8"), re.M)
    assert headings, "no version headings in CHANGELOG.md"
    assert headings[0] == __version__, f"changelog says {headings[0]}, code says {__version__}"


def test_changelog_versions_descend():
    text = CHANGELOG.read_text(encoding="utf-8")
    versions = [
        tuple(int(p) for p in v.split(".")) for v in re.findall(r"^## (\d+\.\d+\.\d+)$", text, re.M)
    ]
    assert versions == sorted(versions, reverse=True)


class TestInstallerContract:
    """install.sh and main.py share two strings. Nothing else enforces that."""

    def _installer(self) -> str:
        return (CHANGELOG.parent / "install.sh").read_text(encoding="utf-8")

    def test_readiness_marker_matches(self):
        # The installer waits for this line to decide the bot authenticated.
        # If they drift, a healthy install reports failure and tears itself down.
        from src.main import READY_MARKER

        assert f'READY_MARKER="{READY_MARKER}"' in self._installer()

    def test_the_bot_actually_logs_the_marker(self):
        from pathlib import Path

        main_src = Path(__file__).resolve().parent.parent / "src" / "main.py"
        assert "READY_MARKER," in main_src.read_text(encoding="utf-8")

    def test_installer_supports_version_pinning(self):
        installer = self._installer()
        assert 'VERSION="${VERSION:-}"' in installer
        assert "refs/tags/$VERSION" in installer

    def test_installer_does_not_shallow_clone(self):
        # A shallow clone cannot check out an older tag, which would make the
        # documented rollback impossible. Comments are allowed to mention it;
        # actual commands are not.
        code = [
            line for line in self._installer().splitlines() if not line.lstrip().startswith("#")
        ]
        assert not [line for line in code if "--depth" in line]
