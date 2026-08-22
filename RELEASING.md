# Releasing ANYmaterial

Releases are built and published by
[`.github/workflows/publish.yml`](.github/workflows/publish.yml). The workflow
uses PyPI Trusted Publishing; do not add API tokens to the repository.

PyPI filenames and versions are immutable. Complete the TestPyPI check before
creating the production GitHub release.

## Trusted Publishing setup

1. In the GitHub repository, open **Settings > Environments** and create two
   environments named exactly `testpypi` and `pypi`. Add a required reviewer to
   `pypi` so production publication always has a manual approval gate. A reviewer
   on `testpypi` is optional.
2. Confirm the existing [PyPI project](https://pypi.org/project/ANYmaterial/)
   lists `audunarn` as an owner. On its **Publishing** settings page, add the
   Trusted Publisher below if it is not already configured.
3. On TestPyPI, either add the publisher to the existing project or create a
   pending Trusted Publisher from the account publishing page if the project
   has not been uploaded there yet. Use these exact values:

   | Setting | TestPyPI | PyPI |
   | --- | --- | --- |
   | Project name | `ANYmaterial` | `ANYmaterial` |
   | GitHub owner | `audunarn` | `audunarn` |
   | GitHub repository | `ANYmaterial` | `ANYmaterial` |
   | Workflow filename | `publish.yml` | `publish.yml` |
   | Environment | `testpypi` | `pypi` |

   Configure a pending TestPyPI project at its
   [account publishing page](https://test.pypi.org/manage/account/publishing/).
   Configure the existing PyPI project from its project publishing settings.
   The GitHub owner and repository values are case-sensitive.

## TestPyPI rehearsal

1. Verify that `main` is clean, version `0.1.1` appears in both
   `pyproject.toml` and `anymaterial.__version__`, the changelog has a dated
   `0.1.1` section with no release changes left under `Unreleased`, and the
   **Tests** workflow is green.
2. Run the **Publish** workflow manually from the `main` branch. From a GitHub
   CLI authenticated for the repository:

   ```console
   gh workflow run publish.yml --repo audunarn/ANYmaterial --ref main
   gh run watch --repo audunarn/ANYmaterial
   ```

3. Create a fresh virtual environment and install the exact TestPyPI release.
   PyPI remains the fallback index for dependencies such as NumPy:

   ```console
   python -m venv .venv-testpypi
   .venv-testpypi\Scripts\python -m pip install --upgrade pip
   .venv-testpypi\Scripts\python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ ANYmaterial==0.1.1
   .venv-testpypi\Scripts\anymaterial --help
   .venv-testpypi\Scripts\anymaterial --json library
   .venv-testpypi\Scripts\python -c "import anymaterial as am; assert am.__version__ == '0.1.1'; assert len(am.library().names) == 33"
   ```

   On POSIX systems, replace `.venv-testpypi\Scripts\` with
   `.venv-testpypi/bin/`.

4. Check the TestPyPI description, license, Python requirement, project links,
   wheel, and source distribution. Do not proceed if the install selected a
   package from any source other than TestPyPI.

## Production release

1. Confirm that `0.1.1` is not already present on PyPI and that the TestPyPI
   rehearsal passed for the same commit.
2. Create the annotated tag from the verified `main` commit and push it:

   ```console
   git tag -a v0.1.1 -m "ANYmaterial 0.1.1"
   git push origin v0.1.1
   ```

3. Create a GitHub release for the existing `v0.1.1` tag, using the `0.1.1`
   changelog entry as the release notes. Publish it as a normal release, not a
   draft or prerelease. Publishing the GitHub release triggers the production
   job; approve the `pypi` environment deployment after checking the commit and
   tag.
4. Watch the **Publish** workflow through artifact verification and upload. The
   workflow rejects a release tag that does not equal `v` plus the package
   version.
5. Verify the public release in another fresh environment:

   ```console
   python -m pip install ANYmaterial==0.1.1
   anymaterial --help
   anymaterial --json library
   python -c "import anymaterial as am; assert am.__version__ == '0.1.1'; assert len(am.library().names) == 33"
   ```

6. Confirm the final [PyPI project page](https://pypi.org/project/ANYmaterial/)
   shows the correct README, GPL-3.0-or-later license, Python requirement,
   homepage, repository, and issue links.
