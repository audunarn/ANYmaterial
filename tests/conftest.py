"""Shared pytest configuration.

PyCharm may launch pytest with ``tests`` as the process working directory,
while tests that read repository files do so by relative path.  Normalize the
working directory once for the full session so the suite behaves identically
from PyCharm, PowerShell and CI.

``tests`` is also put on ``sys.path`` so test modules can share helpers by
importing each other, which is how the packaging check reuses the layering
allowlist instead of restating it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_TESTS_ROOT = Path(__file__).resolve().parent

os.chdir(_REPOSITORY_ROOT)
if str(_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TESTS_ROOT))


@pytest.fixture(autouse=True)
def user_library(tmp_path, monkeypatch):
    """Point the user library somewhere disposable, for every test.

    ``add_to_user_library`` writes to a file in the user's home directory by
    default.  A test suite that appended to a real engineer's material library
    would be a genuinely bad thing to run, so the redirection is autouse rather
    than opt-in: a test cannot forget it.
    """

    path = tmp_path / "user_materials.json"
    monkeypatch.setenv("ANYMATERIAL_LIBRARY", str(path))
    return path
