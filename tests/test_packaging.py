"""Packaging metadata has to agree with the code it describes.

A version that drifts from pyproject.toml is invisible until a release is cut
with the wrong number on it, and an allowlist that drifts from the declared
dependencies turns the layering check into decoration.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import anymaterial
from test_layering import ALLOWED_THIRD_PARTY, OPTIONAL_IMPORT_EXCEPTIONS

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

_REQUIREMENT_NAME = re.compile(r"^[A-Za-z0-9._-]+")


def _pyproject() -> dict:
    return tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _declared_dependencies() -> set[str]:
    project = _pyproject()["project"]
    requirements = list(project.get("dependencies", ()))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    names = set()
    for requirement in requirements:
        match = _REQUIREMENT_NAME.match(requirement.strip())
        if match:
            names.add(match.group(0).lower().replace("_", "-"))
    return names


def test_version_matches_pyproject() -> None:
    assert anymaterial.__version__ == _pyproject()["project"]["version"]


def test_release_metadata_is_0_2_0_and_mpl_2_0() -> None:
    project = _pyproject()["project"]
    assert project["version"] == "0.2.0"
    assert project["license"] == "MPL-2.0"
    assert not any(value.startswith("License ::") for value in project["classifiers"])


def test_release_license_bundle_is_complete_and_consistent() -> None:
    project = _pyproject()["project"]
    assert project["license-files"] == [
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_NOTICES.md",
        "docs/LICENSE.md",
        "src/anymaterial/data/LICENSE_DATA.md",
        "src/anymaterial/data/SOURCES.md",
    ]
    assert (REPOSITORY_ROOT / "LICENSE").read_text(encoding="utf-8").startswith(
        "Mozilla Public License Version 2.0\n"
    )
    notice = (REPOSITORY_ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Copyright (c) Audun Nyhus" in notice
    assert "Starting with version 0.2.0" in notice
    assert "Earlier published versions" in notice
    assert "MPL-2.0" in (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    assert "CC BY 4.0" in (REPOSITORY_ROOT / "docs" / "LICENSE.md").read_text(
        encoding="utf-8"
    )
    data_license = (
        REPOSITORY_ROOT / "src" / "anymaterial" / "data" / "LICENSE_DATA.md"
    ).read_text(encoding="utf-8")
    assert "engineering data assets" in data_license
    assert "Mozilla Public License 2.0" in data_license
    assert "CC BY 4.0" in data_license
    sources = (
        REPOSITORY_ROOT / "src" / "anymaterial" / "data" / "SOURCES.md"
    ).read_text(encoding="utf-8")
    assert "DNV-RP-C208" in sources
    assert "doi.org/10.5281/zenodo.6965147" in sources
    assert "NumPy" in (REPOSITORY_ROOT / "THIRD_PARTY_NOTICES.md").read_text(
        encoding="utf-8"
    )


def test_runtime_dependency_licenses_are_reviewed() -> None:
    completed = subprocess.run(
        [sys.executable, "tools/check_dependency_licenses.py"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert '"name": "numpy"' in completed.stdout.casefold()


def test_distribution_and_import_names_are_as_intended() -> None:
    # `anymaterial` is free on PyPI, so distribution and import name agree
    # here.  They do not in the sibling packages, where `anyio` and `anymesh`
    # were taken, which is why this is asserted rather than assumed.
    assert _pyproject()["project"]["name"] == "ANYmaterial"


def test_allowed_third_party_imports_are_declared_dependencies() -> None:
    declared = _declared_dependencies()
    permitted = set(ALLOWED_THIRD_PARTY)
    for extra in OPTIONAL_IMPORT_EXCEPTIONS.values():
        permitted |= set(extra)
    undeclared = sorted(
        name for name in permitted if name.lower().replace("_", "-") not in declared
    )
    assert not undeclared, (
        "the layering allowlist permits imports that pyproject.toml does not "
        f"install in any extra: {undeclared}"
    )


def test_run_gui_bootstraps_without_an_install() -> None:
    """The IDE Run-button entry point must work in a bare checkout.

    Executed with a run_name other than ``__main__`` so the path bootstrap and
    the import run but the window does not open.
    """

    import runpy

    script = REPOSITORY_ROOT / "run_gui.py"
    assert script.is_file()

    namespace = runpy.run_path(str(script), run_name="not_main")
    assert callable(namespace["main"])
    assert namespace["main"].__module__ == "anymaterial.gui"
    assert 'if __name__ == "__main__":\n    raise SystemExit(main())' in script.read_text(
        encoding="utf-8"
    )
