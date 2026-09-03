# Third-party notices

ANYmaterial's own source code is licensed under MPL-2.0 starting with version
0.2.0. The dependencies below are separate works and retain their upstream
licenses. They are installed separately; their source or object code is not
copied into the ANYmaterial wheel.

| Dependency | Declared requirement | Upstream | License | Distribution |
| --- | --- | --- | --- | --- |
| NumPy | `numpy>=1.26` | https://numpy.org/ | BSD-3-Clause; current wheels also report permissively licensed bundled components | Separate runtime dependency; not bundled |
| setuptools | `setuptools>=68` | https://github.com/pypa/setuptools | MIT | Isolated build dependency; not bundled |
| wheel | `wheel` | https://github.com/pypa/wheel | MIT | Isolated build dependency; not bundled |
| build | `build>=1.2` (`dev` extra) | https://pypa-build.readthedocs.io/ | MIT | Development/release tool; not bundled |
| pytest | `pytest>=8` (`dev` extra) | https://pytest.org/ | MIT | Development/test tool; not bundled |
| Twine | `twine>=5` (`dev` extra) | https://twine.readthedocs.io/ | Apache-2.0 | Release tool; not bundled |

Tkinter is part of supported Python installations and is not bundled by this
project. GitHub Actions used for CI and publication run only in the repository's
automation environment and are not part of the Python distribution.

The material-property sources represented by the bundled JSON files are not
software dependencies. Their provenance and source-specific terms are recorded
in `src/anymaterial/data/LICENSE_DATA.md` and
`src/anymaterial/data/SOURCES.md`.

Release qualification executes `tools/check_dependency_licenses.py` against
the installed runtime dependencies. A new or unknown license fails that check
until it is deliberately reviewed and added to the allowlist and this notice.
