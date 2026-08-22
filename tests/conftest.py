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
import inspect
import sys
from pathlib import Path
from uuid import uuid4

import pytest


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_TESTS_ROOT = Path(__file__).resolve().parent

os.chdir(_REPOSITORY_ROOT)
if str(_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TESTS_ROOT))


_RUN_GUI_TESTS = os.environ.get("ANYMATERIAL_RUN_GUI_TESTS", "").casefold() in {
    "1",
    "true",
    "yes",
}


def pytest_configure(config):
    if getattr(config.option, "basetemp", None) is None:
        config.option.basetemp = str(
            _REPOSITORY_ROOT / f".pytest_tmp_{uuid4().hex}"
        )
    config.addinivalue_line(
        "markers", "gui: opt-in test that creates a real Tk desktop window"
    )


def pytest_collection_modifyitems(items):
    """Never open the material editor during an ordinary test run."""

    if _RUN_GUI_TESTS:
        return
    marker = pytest.mark.skip(
        reason="real Tk GUI test is opt-in; set ANYMATERIAL_RUN_GUI_TESTS=1"
    )
    for item in items:
        try:
            source = inspect.getsource(item.obj)
        except (OSError, TypeError):
            source = ""
        if any(name.endswith("root") for name in item.fixturenames) or any(
            token in source for token in ("tk.Tk(", "tkinter.Tk(")
        ):
            item.add_marker("gui")
            item.add_marker(marker)


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
