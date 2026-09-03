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

1. Verify that `main` is clean, version `0.2.0` appears in both
   `pyproject.toml` and `anymaterial.__version__`, the changelog has a dated
   `0.2.0` section with no release changes left under `Unreleased`, and the
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
   .venv-testpypi\Scripts\python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ ANYmaterial==0.2.0
   .venv-testpypi\Scripts\anymaterial --help
   .venv-testpypi\Scripts\anymaterial --json library
   .venv-testpypi\Scripts\python -c "import anymaterial as am; assert am.__version__ == '0.2.0'; assert len(am.library().names) == 33"
   ```

   On POSIX systems, replace `.venv-testpypi\Scripts\` with
   `.venv-testpypi/bin/`.

4. Check the TestPyPI description, license, Python requirement, project links,
   wheel, and source distribution. Do not proceed if the install selected a
   package from any source other than TestPyPI.

## Production release

1. Confirm that `0.2.0` is not already present on PyPI and that the TestPyPI
   rehearsal passed for the current `main` commit. This commit is the immutable
   artifact source; do not amend it after the workflow builds the assets.
2. Download the complete `python-package-distributions` artifact from that
   workflow run. Keep the wheel, source distribution, and `SHA256SUMS` together
   without renaming or adding files:

   ```console
   gh run download RUN_ID --repo audunarn/ANYmaterial --name python-package-distributions --dir release-assets
   ```

3. Record the artifact-source commit and tree, byte counts, and uppercase SHA-256
   digests of both distributions. Record distinct SHA-256 digests for the
   accepted qualification evidence and its independent review. Create canonical,
   key-sorted JSON at `docs/release/anymaterial-0.2.0-ledger.json` using the
   `anyecosystem.release-ledger-v1` schema and terminal
   `ACCEPTED_ANYMATERIAL_0_2_0_RELEASE`.
4. Commit only that new ledger. It must be the direct child of the artifact
   source, with no other file changed. Tag this ledger commit and push both:

   ```console
   git add docs/release/anymaterial-0.2.0-ledger.json
   git commit -m "docs: authorize ANYmaterial 0.2.0 release"
   git tag -a v0.2.0 -m "ANYmaterial 0.2.0"
   git push origin main v0.2.0
   ```

5. Create the GitHub release for the existing `v0.2.0` tag, use the `0.2.0`
   changelog entry as its notes, and attach exactly the wheel, source
   distribution, and `SHA256SUMS` downloaded above. Publish it as a normal
   release, not a draft or prerelease. Approve the `pypi` environment only after
   confirming the tag, source commit, ledger, assets, qualification evidence,
   and independent review.
6. Watch the **Publish** workflow. Its verifier rejects any moved tag, non-ledger
   commit, changed source tree, extra or missing asset, hash mismatch, package
   identity mismatch, or unreviewed runtime dependency license before upload.
7. Verify the public release in another fresh environment:

   ```console
   python -m pip install ANYmaterial==0.2.0
   anymaterial --help
   anymaterial --json library
   python -c "import anymaterial as am; assert am.__version__ == '0.2.0'; assert len(am.library().names) == 33"
   ```

8. Confirm the final [PyPI project page](https://pypi.org/project/ANYmaterial/)
   shows the correct README, MPL-2.0 license expression, Python requirement,
   homepage, repository, issue links, and complete license/notice bundle.
