#!/usr/bin/env python3
"""Verify a rolling GitHub Release as a fresh external consumer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tarfile
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_sha256sums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        parts = raw_line.split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"invalid SHA256SUMS line {line_number}")
        digest, name = parts
        name = name.removeprefix("*")
        if not SHA256_RE.fullmatch(digest) or Path(name).name != name or name in checksums:
            raise ValueError(f"unsafe SHA256SUMS line {line_number}")
        checksums[name] = digest
    if not checksums:
        raise ValueError("SHA256SUMS is empty")
    return checksums


def expected_assets(directory: Path) -> dict[str, dict[str, int | str]]:
    files = sorted(path for path in directory.iterdir() if path.is_file())
    if not files or not (directory / "SHA256SUMS").is_file():
        raise ValueError("expected release assets and SHA256SUMS are required")
    result = {
        path.name: {"sha256": sha256_file(path), "size": path.stat().st_size}
        for path in files
    }
    manifest = parse_sha256sums(directory / "SHA256SUMS")
    if set(manifest) != set(result) - {"SHA256SUMS"}:
        raise ValueError("SHA256SUMS does not cover exactly the non-manifest assets")
    for name, digest in manifest.items():
        if result[name]["sha256"] != digest:
            raise ValueError(f"local checksum mismatch for {name}")
    return result


def validate_release_metadata(
    release: dict,
    tag_commit: str,
    expected_commit: str,
    expected: dict[str, dict[str, int | str]],
) -> dict[str, dict]:
    if tag_commit != expected_commit:
        raise ValueError(f"tag resolves to {tag_commit}, expected {expected_commit}")
    assets = {asset["name"]: asset for asset in release.get("assets", [])}
    if set(assets) != set(expected):
        raise ValueError(
            f"release asset names are {sorted(assets)}, expected {sorted(expected)}"
        )
    for name, local in expected.items():
        remote = assets[name]
        if remote.get("state") != "uploaded":
            raise ValueError(f"release asset is not uploaded: {name}")
        if remote.get("size") != local["size"]:
            raise ValueError(f"release asset size mismatch: {name}")
        if remote.get("digest") != f"sha256:{local['sha256']}":
            raise ValueError(f"release asset digest mismatch: {name}")
    return assets


def inspect_archive(path: Path) -> str:
    roots: set[str] = set()
    names: set[str] = set()
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        if not members:
            raise ValueError("release archive is empty")
        for member in members:
            name = member.name
            pure = PurePosixPath(name)
            if (
                not name
                or "\\" in name
                or pure.is_absolute()
                or ".." in pure.parts
                or name in names
                or member.issym()
                or member.islnk()
                or member.isdev()
                or member.isfifo()
            ):
                raise ValueError(f"unsafe release archive member: {name!r}")
            names.add(name)
            roots.add(pure.parts[0])
    if len(roots) != 1:
        raise ValueError(f"release archive must have one root, found {sorted(roots)}")
    return next(iter(roots))


def safe_member_filter(member: tarfile.TarInfo, destination: str) -> tarfile.TarInfo:
    """Apply Python's data filter while retaining sanitized directory modes."""
    filtered = tarfile.data_filter(member, destination)
    if filtered.isdir() and member.mode is not None:
        # data_filter deliberately ignores directory modes. Release roots need
        # 0750 and secrets needs 0700, so restore only ordinary rwx bits after
        # removing group/other writes and all special bits.
        filtered = filtered.replace(mode=member.mode & 0o755)
    return filtered


def extract_archive(path: Path, destination: Path) -> Path:
    root = inspect_archive(path)
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("extract destination must be empty")
    with tarfile.open(path, "r:gz") as archive:
        if hasattr(tarfile, "data_filter"):
            archive.extractall(destination, filter=safe_member_filter)
        else:
            archive.extractall(destination)
    extracted_root = destination / root
    if not extracted_root.is_dir():
        raise ValueError("archive root was not extracted as a directory")
    return extracted_root


class GitHubClient:
    def __init__(self, repository: str, token: str | None = None):
        self.repository = repository
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "LocalFlow-release-consumer-gate",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def json(self, path: str) -> dict:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{self.repository}/{path}",
            headers=self.headers,
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def release(self, tag: str) -> dict:
        return self.json(f"releases/tags/{urllib.parse.quote(tag, safe='')}")

    def tag_commit(self, tag: str) -> str:
        value = self.json(f"git/ref/tags/{urllib.parse.quote(tag, safe='')}")["object"]
        for _ in range(5):
            if value["type"] == "commit":
                return value["sha"]
            if value["type"] != "tag":
                raise ValueError(f"unsupported tag object type: {value['type']}")
            value = self.json(f"git/tags/{value['sha']}")["object"]
        raise ValueError("annotated tag chain is too deep")

    def download(self, url: str, destination: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": self.headers["User-Agent"]})
        temporary = destination.with_suffix(destination.suffix + ".part")
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        temporary.replace(destination)


def verify_published_release(
    repository: str,
    tag: str,
    expected_commit: str,
    expected_directory: Path,
    download_directory: Path,
    attempts: int,
) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ValueError("expected commit must be a full lowercase Git SHA")
    expected = expected_assets(expected_directory)
    download_directory.mkdir(parents=True, exist_ok=True)
    client = GitHubClient(repository, os.environ.get("GITHUB_TOKEN"))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            release = client.release(tag)
            tag_commit = client.tag_commit(tag)
            assets = validate_release_metadata(release, tag_commit, expected_commit, expected)
            for name in sorted(expected):
                destination = download_directory / name
                client.download(assets[name]["browser_download_url"], destination)
                if destination.stat().st_size != expected[name]["size"]:
                    raise ValueError(f"downloaded asset size mismatch: {name}")
                if sha256_file(destination) != expected[name]["sha256"]:
                    raise ValueError(f"downloaded asset digest mismatch: {name}")
            downloaded_manifest = parse_sha256sums(download_directory / "SHA256SUMS")
            for name, digest in downloaded_manifest.items():
                if sha256_file(download_directory / name) != digest:
                    raise ValueError(f"downloaded SHA256SUMS mismatch: {name}")
            archives = list(download_directory.glob("*.tar.gz"))
            if len(archives) != 1:
                raise ValueError("release must contain exactly one tar.gz bundle")
            archive_root = inspect_archive(archives[0])
            return {
                "repository": repository,
                "tag": tag,
                "expected_commit": expected_commit,
                "tag_commit": tag_commit,
                "release_id": release["id"],
                "release_published_at": release["published_at"],
                "release_updated_at": release["updated_at"],
                "archive_root": archive_root,
                "assets": expected,
                "verified_at": datetime.now(UTC).isoformat(),
                "workflow_run": os.environ.get("GITHUB_SERVER_URL", "")
                + "/"
                + os.environ.get("GITHUB_REPOSITORY", repository)
                + "/actions/runs/"
                + os.environ.get("GITHUB_RUN_ID", ""),
            }
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError(f"published release did not converge after {attempts} attempts: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-assets", type=Path, required=True)
    parser.add_argument("--download-directory", type=Path, required=True)
    parser.add_argument("--extract-directory", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=8)
    args = parser.parse_args()
    if args.attempts < 1 or args.attempts > 20:
        raise SystemExit("--attempts must be between 1 and 20")
    receipt = verify_published_release(
        args.repository,
        args.tag,
        args.expected_commit,
        args.expected_assets,
        args.download_directory,
        args.attempts,
    )
    archive = next(args.download_directory.glob("*.tar.gz"))
    extracted_root = extract_archive(archive, args.extract_directory)
    receipt["extracted_root"] = str(extracted_root)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(extracted_root)


if __name__ == "__main__":
    main()
