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
        assert 'RELEASE_TAG="${VERSION:-}"' in installer
        assert "refs/tags/$RELEASE_TAG" in installer

    def test_installer_does_not_shallow_clone(self):
        # A shallow clone cannot check out an older tag, which would make the
        # documented rollback impossible. Comments are allowed to mention it;
        # actual commands are not.
        code = [
            line for line in self._installer().splitlines() if not line.lstrip().startswith("#")
        ]
        assert not [line for line in code if "--depth" in line]


class TestOsReleaseCollisions:
    """install.sh sources /etc/os-release, which defines a fixed set of names.

    Assigning any of them beforehand means the distribution silently replaces
    the value. That is exactly how `VERSION=v1.0.0` became `12 (bookworm)` on
    Debian and made the installer look for a release tag by that name.
    """

    # Everything os-release is specified to define.
    OS_RELEASE_FIELDS = {
        "NAME", "VERSION", "ID", "ID_LIKE", "VERSION_ID", "VERSION_CODENAME",
        "PRETTY_NAME", "ANSI_COLOR", "CPE_NAME", "HOME_URL", "SUPPORT_URL",
        "DOCUMENTATION_URL", "BUG_REPORT_URL", "PRIVACY_POLICY_URL", "LOGO",
        "BUILD_ID", "VARIANT", "VARIANT_ID", "IMAGE_ID", "IMAGE_VERSION",
    }

    def test_no_variable_collides_with_os_release(self):
        import re
        from pathlib import Path

        installer = (Path(__file__).resolve().parent.parent / "install.sh").read_text(
            encoding="utf-8"
        )
        assigned = set()
        for line in installer.splitlines():
            line = line.strip()
            if line.startswith("#"):
                continue
            match = re.match(r"^(?:export\s+)?([A-Z_][A-Z0-9_]*)=", line)
            if match:
                assigned.add(match.group(1))

        collisions = assigned & self.OS_RELEASE_FIELDS
        assert not collisions, (
            f"install.sh assigns {sorted(collisions)}, which /etc/os-release also "
            "defines; sourcing it would overwrite them"
        )

    def test_release_pinning_uses_a_safe_name(self):
        from pathlib import Path

        installer = (Path(__file__).resolve().parent.parent / "install.sh").read_text(
            encoding="utf-8"
        )
        # The caller still passes VERSION=...; it is captured under another
        # name before /etc/os-release is sourced.
        assert 'RELEASE_TAG="${VERSION:-}"' in installer
        assert installer.index('RELEASE_TAG="${VERSION:-}"') < installer.index(
            ". /etc/os-release"
        )

    def test_shallow_installs_are_deepened(self):
        from pathlib import Path

        installer = (Path(__file__).resolve().parent.parent / "install.sh").read_text(
            encoding="utf-8"
        )
        # Older versions of this script cloned shallow, which cannot reach a tag.
        assert "--is-shallow-repository" in installer
        assert "--unshallow" in installer
