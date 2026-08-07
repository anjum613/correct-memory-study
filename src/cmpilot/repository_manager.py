"""Create and inspect isolated repositories for the engineering smoke test."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


REPOSITORY_COPY_POLICY = "isolated-repository-copy-v1"
REPOSITORY_CONTENT_SCHEMA = "isolated-repository-content-v1"
WORKING_COPY_PERMISSION_FAILURE = "WORKING_COPY_PERMISSION_FAILURE"
DIRECTORY_MODE = 0o700
ORDINARY_FILE_MODE = 0o600
EXECUTABLE_FILE_MODE = 0o700


class RepositoryCopyError(OSError):
    """Raised when a source tree cannot be copied into an isolated repository."""


@dataclass(frozen=True)
class RepositoryContentDigest:
    """Mode-independent digest of repository paths, bytes, and symlink targets."""

    canonical_inventory: bytes
    sha256: str
    entry_count: int
    schema: str = REPOSITORY_CONTENT_SCHEMA

    def as_record(self) -> dict[str, object]:
        return {
            "entry_count": self.entry_count,
            "schema": self.schema,
            "sha256": self.sha256,
        }


def prepare_working_copy(
    template: Path,
    *,
    temporary_root: Path | None = None,
    destination: Path | None = None,
) -> tuple[Path, str]:
    """Copy a template into a fresh repository and create its initial commit."""
    if not template.is_dir():
        raise FileNotFoundError(f"smoke template does not exist: {template}")
    if destination is not None:
        generated_destination = False
        working_copy = destination
        if working_copy.exists():
            raise FileExistsError(f"working-copy destination already exists: {working_copy}")
    else:
        generated_destination = True
        working_copy = Path(
            tempfile.mkdtemp(prefix="cmpilot-smoke-", dir=temporary_root)
        )

    try:
        source_digest = repository_content_digest(template)
        if generated_destination:
            _populate_repository_copy(template, working_copy)
        else:
            copy_repository_tree(template, working_copy)
        destination_digest = repository_content_digest(working_copy)
        if destination_digest != source_digest:
            raise RepositoryCopyError(
                "isolated repository content differs from its source before Git initialization"
            )
        _verify_working_copy_permissions(working_copy)
    except BaseException:
        if generated_destination:
            shutil.rmtree(working_copy)
        raise
    for arguments in (
        ("init",),
        ("config", "user.name", "cmpilot smoke preparer"),
        ("config", "user.email", "cmpilot@example.invalid"),
        ("add", "."),
        ("commit", "-m", "Initial smoke-test repository"),
    ):
        git(working_copy, *arguments, check=True)
    return working_copy, git(working_copy, "rev-parse", "HEAD", check=True).stdout.strip()


def copy_repository_tree(source: Path, destination: Path) -> RepositoryContentDigest:
    """Copy repository content while normalizing only destination permissions."""
    _validate_source_root(source)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"working-copy destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(
            f"working-copy destination parent does not exist: {destination.parent}"
        )
    destination.mkdir(mode=DIRECTORY_MODE)
    destination.chmod(DIRECTORY_MODE)
    try:
        _populate_repository_copy(source, destination)
        source_digest = repository_content_digest(source)
        destination_digest = repository_content_digest(destination)
        if destination_digest != source_digest:
            raise RepositoryCopyError(
                "isolated repository content differs from its source"
            )
        return destination_digest
    except BaseException:
        shutil.rmtree(destination)
        raise


def _validate_source_root(source: Path) -> None:
    try:
        information = source.lstat()
    except FileNotFoundError as error:
        raise FileNotFoundError(f"repository source does not exist: {source}") from error
    if stat.S_ISLNK(information.st_mode) or not stat.S_ISDIR(information.st_mode):
        raise RepositoryCopyError(
            f"repository source must be a real directory, not a symlink: {source}"
        )


def _repository_entries(
    source_root: Path,
    current: Path | None = None,
) -> Iterator[tuple[Path, Path, os.stat_result]]:
    current = source_root if current is None else current
    with os.scandir(current) as entries:
        ordered = sorted(entries, key=lambda entry: entry.name)
    for entry in ordered:
        source = Path(entry.path)
        relative = source.relative_to(source_root)
        if len(relative.parts) == 1 and relative.name == ".git":
            continue
        information = entry.stat(follow_symlinks=False)
        yield source, relative, information
        if stat.S_ISDIR(information.st_mode):
            yield from _repository_entries(source_root, source)


def _populate_repository_copy(source: Path, destination: Path) -> None:
    _validate_source_root(source)
    destination.chmod(DIRECTORY_MODE)
    source_root = source.resolve(strict=True)
    for source_path, relative, information in _repository_entries(source):
        destination_path = destination / relative
        if stat.S_ISDIR(information.st_mode):
            destination_path.mkdir(mode=DIRECTORY_MODE)
            destination_path.chmod(DIRECTORY_MODE)
            continue
        if stat.S_ISREG(information.st_mode):
            shutil.copyfile(source_path, destination_path, follow_symlinks=False)
            mode = (
                EXECUTABLE_FILE_MODE
                if information.st_mode & 0o111
                else ORDINARY_FILE_MODE
            )
            destination_path.chmod(mode)
            continue
        if stat.S_ISLNK(information.st_mode):
            target = os.readlink(source_path)
            _validate_symlink(source_root, source_path, target)
            destination_path.symlink_to(target)
            continue
        raise RepositoryCopyError(
            f"unsupported repository entry type: {source_path}"
        )


def _validate_symlink(source_root: Path, source_path: Path, target: str) -> None:
    if os.path.isabs(target):
        raise RepositoryCopyError(
            f"repository symlink resolves outside the source: {source_path} -> {target}"
        )
    try:
        (source_path.parent / target).resolve(strict=False).relative_to(source_root)
    except ValueError as error:
        raise RepositoryCopyError(
            f"repository symlink resolves outside the source: {source_path} -> {target}"
        ) from error


def _verify_working_copy_permissions(repository: Path) -> None:
    for path in [repository, *repository.rglob("*")]:
        if path.is_symlink() or not path.is_dir():
            continue
        information = path.stat()
        if information.st_uid != os.geteuid():
            raise RepositoryCopyError(
                f"working-copy directory is not owned by the current user: {path}"
            )
        if stat.S_IMODE(information.st_mode) & 0o300 != 0o300:
            raise RepositoryCopyError(
                f"working-copy directory is not owner-writable and searchable: {path}"
            )


def repository_content_digest(repository: Path) -> RepositoryContentDigest:
    """Hash stable repository content while excluding source Git metadata."""
    _validate_source_root(repository)
    rows: list[dict[str, str]] = []
    for path, relative, information in _repository_entries(repository):
        record = {"path": relative.as_posix()}
        if stat.S_ISDIR(information.st_mode):
            record["type"] = "directory"
        elif stat.S_ISREG(information.st_mode):
            record.update(
                {
                    "sha256": _sha256_file(path),
                    "type": "file",
                }
            )
        elif stat.S_ISLNK(information.st_mode):
            record.update(
                {
                    "target": os.readlink(path),
                    "type": "symlink",
                }
            )
        else:
            raise RepositoryCopyError(f"unsupported repository entry type: {path}")
        rows.append(record)
    payload = {
        "entries": rows,
        "schema": REPOSITORY_CONTENT_SCHEMA,
    }
    canonical = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return RepositoryContentDigest(
        canonical_inventory=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
        entry_count=len(rows),
    )


def repository_mode_inventory(repository: Path) -> list[dict[str, object]]:
    """Observe ownership and permissions without making them content-authoritative."""
    _validate_source_root(repository)
    paths = [(repository, Path("."), repository.lstat())]
    paths.extend(_repository_entries(repository))
    rows: list[dict[str, object]] = []
    for path, relative, information in paths:
        if stat.S_ISDIR(information.st_mode):
            kind = "directory"
        elif stat.S_ISREG(information.st_mode):
            kind = "file"
        elif stat.S_ISLNK(information.st_mode):
            kind = "symlink"
        else:
            kind = "special"
        rows.append(
            {
                "gid": information.st_gid,
                "mode": format(stat.S_IMODE(information.st_mode), "04o"),
                "path": relative.as_posix(),
                "type": kind,
                "uid": information.st_uid,
            }
        )
    return rows


def repository_preparation_record(
    source: Path,
    destination: Path,
    initial_commit: str,
) -> dict[str, object]:
    """Describe source integrity and destination usability after preparation."""
    source_digest = repository_content_digest(source)
    destination_digest = repository_content_digest(destination)
    source_information = source.stat()
    destination_information = destination.stat()
    return {
        "content_digest_match": source_digest == destination_digest,
        "destination": {
            "content_digest": destination_digest.as_record(),
            "mode_inventory": repository_mode_inventory(destination),
            "owner_gid": destination_information.st_gid,
            "owner_uid": destination_information.st_uid,
            "path": str(destination),
            "root_mode": format(
                stat.S_IMODE(destination_information.st_mode), "04o"
            ),
        },
        "git": {
            "directory_created": (destination / ".git").is_dir(),
            "initial_commit": initial_commit,
            "status": git(destination, "status", "--short", check=True).stdout,
        },
        "policy": REPOSITORY_COPY_POLICY,
        "schema": "isolated-repository-preparation-v1",
        "source": {
            "content_digest": source_digest.as_record(),
            "mode_inventory": repository_mode_inventory(source),
            "owner_gid": source_information.st_gid,
            "owner_uid": source_information.st_uid,
            "path": str(source),
            "root_mode": format(stat.S_IMODE(source_information.st_mode), "04o"),
        },
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_working_copy_failure(record: Mapping[str, object]) -> str | None:
    """Classify the read-only-copy signature preserved by calculator job 25514."""
    destination_mode = _mode_value(record.get("destination_mode"))
    source_mode = _mode_value(record.get("source_mode"))
    git_exit_code = record.get("git_exit_code")
    git_directory_created = record.get("git_directory_created")
    if (
        destination_mode is not None
        and source_mode is not None
        and destination_mode & stat.S_IWUSR == 0
        and source_mode & stat.S_IWUSR == 0
        and isinstance(git_exit_code, int)
        and git_exit_code != 0
        and git_directory_created is False
    ):
        return WORKING_COPY_PERMISSION_FAILURE
    return None


def _mode_value(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 8)
        except ValueError:
            return None
    return None


def git(repository: Path, *arguments: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        text=True,
        capture_output=True,
        check=check,
    )


def run_tests(repository: Path) -> subprocess.CompletedProcess[str]:
    """Run the template's pytest suite without creating caches in the copy."""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=repository,
        text=True,
        capture_output=True,
        env=environment,
    )


def template_snapshot(template: Path) -> dict[Path, bytes]:
    return {path.relative_to(template): path.read_bytes() for path in template.rglob("*") if path.is_file()}


def final_patch(repository: Path, initial_commit: str) -> str:
    """Return all tracked changes since the initial state, including agent commits."""
    return git(repository, "diff", "--binary", "--no-ext-diff", initial_commit, "--").stdout
