"""Hashemwise - the single source of truth for the running version.

Lives inside `src/` so it ships with the Docker image, which copies only that
directory. Kept in step with the top entry of CHANGELOG.md by a test.
"""

__version__ = "1.1.1"
