import io
import tarfile
from pathlib import Path

import pytest

from tools.verify_published_release import (
    expected_assets,
    extract_archive,
    inspect_archive,
    sha256_file,
    validate_release_metadata,
)


def _write_tar(path: Path, members: dict[str, bytes], *, symlink: tuple[str, str] | None = None):
    with tarfile.open(path, "w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        if symlink:
            info = tarfile.TarInfo(symlink[0])
            info.type = tarfile.SYMTYPE
            info.linkname = symlink[1]
            archive.addfile(info)


def test_release_consumer_validates_metadata_checksums_and_safe_archive(tmp_path: Path):
    assets = tmp_path / "assets"
    assets.mkdir()
    binary = assets / "localflow"
    binary.write_bytes(b"binary")
    bundle = assets / "localflow-0.1.0-linux-x86_64.tar.gz"
    _write_tar(bundle, {"localflow-0.1.0-linux-x86_64/localflow": b"binary"})
    (assets / "SHA256SUMS").write_text(
        f"{sha256_file(binary)}  {binary.name}\n{sha256_file(bundle)}  {bundle.name}\n",
        encoding="ascii",
    )
    expected = expected_assets(assets)
    release = {
        "assets": [
            {"name": name, "size": item["size"], "digest": f"sha256:{item['sha256']}", "state": "uploaded"}
            for name, item in expected.items()
        ]
    }
    commit = "a" * 40
    validate_release_metadata(release, commit, commit, expected)
    assert inspect_archive(bundle) == "localflow-0.1.0-linux-x86_64"
    assert (extract_archive(bundle, tmp_path / "extract") / "localflow").read_bytes() == b"binary"


@pytest.mark.parametrize(
    ("members", "symlink"),
    [
        ({"../escape": b"bad"}, None),
        ({"one/file": b"a", "two/file": b"b"}, None),
        ({"one/file": b"a"}, ("one/link", "../../escape")),
        ({"one\\escape": b"bad"}, None),
    ],
)
def test_release_consumer_rejects_unsafe_archive_members(tmp_path, members, symlink):
    archive = tmp_path / "unsafe.tar.gz"
    _write_tar(archive, members, symlink=symlink)
    with pytest.raises(ValueError, match="unsafe|one root"):
        inspect_archive(archive)


def test_release_consumer_rejects_stale_tag_and_remote_digest(tmp_path: Path):
    asset = tmp_path / "localflow"
    asset.write_bytes(b"binary")
    expected = {asset.name: {"size": asset.stat().st_size, "sha256": sha256_file(asset)}}
    release = {
        "assets": [
            {
                "name": asset.name,
                "size": asset.stat().st_size,
                "digest": f"sha256:{'0' * 64}",
                "state": "uploaded",
            }
        ]
    }
    with pytest.raises(ValueError, match="tag resolves"):
        validate_release_metadata(release, "a" * 40, "b" * 40, expected)
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_release_metadata(release, "a" * 40, "a" * 40, expected)
