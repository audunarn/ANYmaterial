from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_manual_testpypi_and_verified_release_asset_paths_are_separate() -> None:
    workflow = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    assert "repository-url: https://test.pypi.org/legacy/" in workflow
    assert "sha256sum *.whl *.tar.gz > SHA256SUMS" in workflow
    assert "gh release download" in workflow
    assert "Verify exact release artifact set and hashes" in workflow
    assert "hashlib.sha256(path.read_bytes()).hexdigest()" in workflow
    assert "timeout-minutes: 20" not in workflow
