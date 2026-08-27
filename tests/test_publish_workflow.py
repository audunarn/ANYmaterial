import hashlib
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_manual_testpypi_and_verified_release_asset_paths_are_separate() -> None:
    workflow = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    assert "repository-url: https://test.pypi.org/legacy/" in workflow
    assert "sha256sum *.whl *.tar.gz > SHA256SUMS" in workflow
    assert "gh release download" in workflow
    assert "Verify exact release artifact set and hashes" in workflow
    assert "hashlib.sha256(path.read_bytes()).hexdigest()" in workflow
    assert "timeout-minutes: 20" not in workflow
    assert "anymaterial-{version}-py3-none-any.whl" in workflow
    assert "path.is_symlink()" in workflow
    verifier = workflow.split("Verify exact release artifact set and hashes", 1)[1]
    assert "assert " not in verifier


def _verifier() -> str:
    workflow = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    section = workflow.split("Verify exact release artifact set and hashes", 1)[1]
    script = section.split("        run: |\n", 1)[1].split("\n      - uses:", 1)[0]
    return script.replace("          ", "", 1).replace("\n          ", "\n")


def _run(tmp_path: Path, *, tag: str = "v0.1.1", wheel: str = "anymaterial-0.1.1-py3-none-any.whl", digest_ok: bool = True) -> subprocess.CompletedProcess[str]:
    release = tmp_path / "release"
    release.mkdir(parents=True)
    files = {wheel: b"wheel", "anymaterial-0.1.1.tar.gz": b"sdist"}
    for name, data in files.items():
        (release / name).write_bytes(data)
    rows = [f"{hashlib.sha256(data).hexdigest()}  {name}" for name, data in files.items()]
    if not digest_ok:
        rows[0] = "0" * 64 + "  " + wheel
    (release / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="ascii")
    environment = os.environ.copy()
    environment["RELEASE_TAG"] = tag
    return subprocess.run([sys.executable, "-c", _verifier()], cwd=tmp_path, env=environment, capture_output=True, text=True, check=False)


def test_release_verifier_rejects_wrong_tag_name_and_hash(tmp_path: Path) -> None:
    assert _run(tmp_path / "valid").returncode == 0
    assert _run(tmp_path / "tag", tag="v0.1.0").returncode != 0
    assert _run(tmp_path / "name", wheel="other-0.1.1-py3-none-any.whl").returncode != 0
    assert _run(tmp_path / "hash", digest_ok=False).returncode != 0
