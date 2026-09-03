"""Fail closed when an installed runtime dependency has an unreviewed license."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPROVED_SPDX = frozenset(
    {
        "0BSD",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "CC0-1.0",
        "ISC",
        "MIT",
        "MPL-2.0",
        "Zlib",
    }
)
CLASSIFIER_EXPRESSIONS = {
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
}
REQUIREMENT_NAME = re.compile(r"^[A-Za-z0-9._-]+")
SPDX_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*")


def _runtime_dependency_names() -> list[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    names = []
    for requirement in project.get("dependencies", ()):
        match = REQUIREMENT_NAME.match(requirement.strip())
        if match:
            names.append(match.group(0))
    return sorted(names, key=str.casefold)


def _license_expression(name: str) -> tuple[str, str]:
    try:
        package = distribution(name)
    except PackageNotFoundError as error:
        raise RuntimeError(f"runtime dependency is not installed: {name}") from error

    expression = package.metadata.get("License-Expression")
    source = "License-Expression"
    if not expression:
        classifiers = package.metadata.get_all("Classifier", ())
        matches = {
            CLASSIFIER_EXPRESSIONS[value]
            for value in classifiers
            if value in CLASSIFIER_EXPRESSIONS
        }
        if len(matches) != 1:
            raise RuntimeError(f"{name} has no unambiguous SPDX license metadata")
        expression = matches.pop()
        source = "Classifier"

    tokens = {
        token
        for token in SPDX_TOKEN.findall(expression)
        if token not in {"AND", "OR", "WITH"}
    }
    unknown = sorted(tokens - APPROVED_SPDX)
    if unknown:
        raise RuntimeError(
            f"{name} has unreviewed license identifiers {unknown}: {expression}"
        )
    return expression, source


def inventory() -> list[dict[str, str]]:
    rows = []
    for name in _runtime_dependency_names():
        package = distribution(name)
        expression, source = _license_expression(name)
        rows.append(
            {
                "license_expression": expression,
                "license_source": source,
                "name": package.metadata["Name"],
                "version": package.version,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    text = json.dumps(inventory(), indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
