from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, Protocol

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from markguardiola import __version__
from markguardiola.core.config import Settings
from markguardiola.db.base import Base
from markguardiola.features.pipeline import FEATURE_SCHEMA_VERSION
from markguardiola.ml.registry.artifacts import source_code_revision
from markguardiola.ml.targets import TARGETS
from markguardiola.release.manifest import (
    BLOCK_SIZE,
    FOOTBALL_TABLES,
    RAW_INPUT_TABLES,
    REQUIRED_TABLES,
    BinaryReader,
    BundleManifest,
    FileRecord,
    dependency_hash,
    file_record,
    path_record,
    safe_path,
    table_columns,
)


def connect(settings: Settings) -> psycopg.Connection[Any]:
    url = make_url(settings.migration_database_url).set(drivername="postgresql")
    return psycopg.connect(url.render_as_string(hide_password=False))


def _scalar(connection: psycopg.Connection[Any], query: str | sql.Composed) -> Any:
    row = connection.execute(query).fetchone()
    if row is None:
        raise ValueError()
    return row[0]


def require_empty_database(connection: psycopg.Connection[Any]) -> None:
    for table in Base.metadata.sorted_tables:
        found = connection.execute(
            sql.SQL("SELECT EXISTS (SELECT 1 FROM {})").format(sql.Identifier(table.name))
        ).fetchone()
        if found and found[0]:
            raise ValueError()


LATEST_PREDICTION = (
    "SELECT id FROM prediction_runs WHERE status = 'succeeded' "
    "ORDER BY prediction_cutoff DESC, created_at DESC, id DESC LIMIT 1"
)


def _selection(table: str) -> sql.SQL:

    conditions = {
        "model_versions": "status = 'champion'",
        "prediction_runs": f"id = ({LATEST_PREDICTION})",
        "player_match_predictions": f"prediction_run_id = ({LATEST_PREDICTION})",
    }
    return sql.SQL(conditions.get(table, "TRUE"))


def _root_relative(path: str | Path, root: Path) -> str:
    resolved = Path(path).resolve(strict=True)
    relative = resolved.relative_to(root.resolve()).as_posix()
    safe_path(relative)
    return relative


def _metadata_is_safe(value: object) -> None:

    if isinstance(value, dict):
        for key, item in value.items():
            if (
                re.search(
                    r"(?i)(password|secret|authorization|cookie|api.?key|access.?token)", str(key)
                )
                and item
            ):
                raise ValueError()
            _metadata_is_safe(item)
    elif isinstance(value, list):
        for item in value:
            _metadata_is_safe(item)


def _collect_files(
    connection: psycopg.Connection[Any], settings: Settings
) -> tuple[dict[str, Path], dict[str, dict[str, str]], dict[str, str]]:
    files: dict[str, Path] = {}
    paths: dict[str, dict[str, str]] = {
        "feature_snapshot_metadata": {},
        "model_versions": {},
        "ingestion_runs": {},
    }
    data = settings.data_root.resolve()
    artifacts = settings.artifact_root.resolve()

    def add(root: Path, relative: str, prefix: str) -> None:
        safe_path(relative)
        path = root / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError()
        files[f"{prefix}/{relative}"] = path

    def add_raw(relative: str) -> None:
        add(data, f"raw/{relative}", "data")
        metadata = f"raw/{relative}.metadata.json"
        envelope = json.loads((data / metadata).read_text())
        _metadata_is_safe(envelope.get("request_params", {}))
        _metadata_is_safe(envelope.get("response_headers", {}))
        add(data, metadata, "data")

    for (config,) in connection.execute("SELECT config FROM data_sources"):
        _metadata_is_safe(config)
    for path, params, headers, digest in connection.execute(
        "SELECT storage_path, request_params, http_metadata, content_sha256 FROM raw_objects"
    ):
        _metadata_is_safe(params)
        _metadata_is_safe(headers)
        add_raw(path)
        if path_record(data / "raw" / path).sha256 != digest:
            raise ValueError()
    for run_id, manifest in connection.execute("SELECT id, manifest FROM ingestion_runs"):
        if not manifest.get("path"):
            continue
        relative = _root_relative(manifest["path"], data)
        paths["ingestion_runs"][str(run_id)] = relative
        add(data, relative, "data")
        for entry in json.loads((data / relative).read_text()).get("objects", []):
            add_raw(entry["relative_path"])
    for identifier, path, digest in connection.execute(
        "SELECT id, storage_path, manifest_hash FROM feature_snapshot_metadata"
    ):
        relative = _root_relative(path, data)
        paths["feature_snapshot_metadata"][str(identifier)] = relative
        add(data, relative, "data")
        add(data, str(Path(relative).with_suffix(".manifest.json")), "data")
        if path_record(data / relative).sha256 != digest:
            raise ValueError()
    champions: dict[str, str] = {}
    for identifier, target, version, path, revision, status in connection.execute(
        "SELECT id, target, version, artifact_path, code_revision, status FROM model_versions "
        "WHERE status = 'champion'"
    ):
        relative = _root_relative(path, artifacts)
        paths["model_versions"][str(identifier)] = relative
        add(artifacts, relative, "artifacts")
        add(artifacts, f"models/{target}/{version}/manifest.json", "artifacts")
        evaluation = f"evaluations/{target}/{version}.json"
        add(artifacts, evaluation, "artifacts")
        if revision:
            add(artifacts, f"source/{revision}.zip", "artifacts")
        if Path(relative).stem != f"model-{path_record(artifacts / relative).sha256}":
            raise ValueError()
        if status == "champion":
            if target in champions:
                raise ValueError()
            champions[target] = version
            pointer_name = f"models/{target}/champion.json"
            add(artifacts, pointer_name, "artifacts")
            pointer = json.loads((artifacts / pointer_name).read_text())
            if pointer["version"] != version or f"models/{pointer['artifact']}" != relative:
                raise ValueError()
    for revision, model_versions in connection.execute(
        "SELECT code_revision, model_versions FROM prediction_runs "
        f"WHERE id = ({LATEST_PREDICTION})"
    ):
        if model_versions != champions:
            raise ValueError()
        if revision:
            add(artifacts, f"source/{revision}.zip", "artifacts")
    missing = (set(TARGETS) - {"base_rating"}) - set(champions)
    if missing:
        raise ValueError()
    return files, paths, champions


def build_bundle(
    settings: Settings,
    destination: Path,
    *,
    version: str,
    reconstruction_cutoff: datetime | None = None,
) -> BundleManifest:
    if reconstruction_cutoff is not None and (
        reconstruction_cutoff.tzinfo is None or reconstruction_cutoff > datetime.now(UTC)
    ):
        raise ValueError()
    checksum_path = destination.with_suffix(destination.suffix + ".sha256")
    if destination.exists() or checksum_path.exists():
        raise FileExistsError()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version):
        raise ValueError()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    published = False
    checksum_created = False
    try:
        with connect(settings) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SET LOCAL search_path TO public")
            major = connection.info.server_version // 10000
            if major != 17:
                raise ValueError()
            migration = _scalar(connection, "SELECT version_num FROM alembic_version")
            inputs, paths, champions = _collect_files(connection, settings)
            records: dict[str, FileRecord] = {}
            counts: dict[str, int] = {}
            with zipfile.ZipFile(
                temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=1
            ) as archive:
                for table, columns in table_columns().items():
                    counts[table] = _scalar(
                        connection,
                        sql.SQL("SELECT count(*) FROM {} WHERE {}").format(
                            sql.Identifier(table), _selection(table)
                        ),
                    )
                    if table in REQUIRED_TABLES and counts[table] == 0:
                        raise ValueError()
                    digest, size = hashlib.sha256(), 0
                    member = f"tables/{table}.copy"
                    query = sql.SQL(
                        "COPY (SELECT {} FROM {} WHERE {}) TO STDOUT (FORMAT BINARY)"
                    ).format(
                        sql.SQL(",").join(map(sql.Identifier, columns)),
                        sql.Identifier(table),
                        _selection(table),
                    )
                    with (
                        connection.cursor().copy(query) as source,
                        archive.open(member, "w", force_zip64=True) as target,
                    ):
                        buffer = bytearray()
                        for block in source:
                            buffer.extend(block)
                            if len(buffer) >= BLOCK_SIZE:
                                target.write(buffer)
                                digest.update(buffer)
                                size += len(buffer)
                                buffer.clear()
                        if buffer:
                            target.write(buffer)
                            digest.update(buffer)
                            size += len(buffer)
                    records[member] = FileRecord(size=size, sha256=digest.hexdigest())
                    print(f"Exported {table}: {counts[table]} rows", flush=True)
                for name, path in sorted(inputs.items()):
                    digest, size = hashlib.sha256(), 0
                    with (
                        path.open("rb") as source,
                        archive.open(name, "w", force_zip64=True) as target,
                    ):
                        while block := source.read(BLOCK_SIZE):
                            target.write(block)
                            digest.update(block)
                            size += len(block)
                    records[name] = FileRecord(size=size, sha256=digest.hexdigest())
                manifest = BundleManifest(
                    version=version,
                    application_version=__version__,
                    created_at=datetime.now(UTC).isoformat(),
                    reconstruction_cutoff=(
                        reconstruction_cutoff.isoformat() if reconstruction_cutoff else None
                    ),
                    postgres_major=major,
                    migration_head=migration,
                    feature_schema=FEATURE_SCHEMA_VERSION,
                    lock_sha256=dependency_hash(),
                    source_revision=source_code_revision(),
                    columns=table_columns(),
                    row_counts=counts,
                    champions=champions,
                    files=records,
                    paths=paths,
                )
                archive.writestr("manifest.json", manifest.model_dump_json(indent=2))

        checksum = path_record(temporary).sha256
        os.link(temporary, destination)
        published = True
        with checksum_path.open("x") as checksum_file:
            checksum_created = True
            checksum_file.write(f"{checksum}  {destination.name}\n")
        return manifest
    except BaseException:
        if checksum_created:
            checksum_path.unlink(missing_ok=True)
        if published:
            destination.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _verified_file(path: Path, expected_sha256: str) -> Iterator[BinaryIO]:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError()
    with path.open("rb") as source:
        if file_record(source).sha256 != expected_sha256:
            raise ValueError()
        source.seek(0)
        yield source


_LEGACY_RAW_HEAD = "b6a1739e4c20"
_TEMPORAL_HEAD = "d83a2f7046bc"


def verify_bundle(
    path: Path, expected_sha256: str, *, raw_inputs_only: bool = False
) -> BundleManifest:
    with (
        _verified_file(path, expected_sha256) as source_file,
        zipfile.ZipFile(source_file) as archive,
    ):
        members = archive.infolist()
        names = [member.filename for member in members]
        if len(names) != len({name.casefold() for name in names}) or len(names) > 100_000:
            raise ValueError()
        for member in members:
            safe_path(member.filename)
            kind = stat.S_IFMT(member.external_attr >> 16)
            if member.is_dir() or kind not in (0, stat.S_IFREG) or member.flag_bits & 1:
                raise ValueError()
        if archive.getinfo("manifest.json").file_size > 16 * BLOCK_SIZE:
            raise ValueError()
        manifest = BundleManifest.model_validate_json(archive.read("manifest.json"))
        if set(names) != set(manifest.files) | {"manifest.json"}:
            raise ValueError()

        legacy_raw = raw_inputs_only and manifest.migration_head == _LEGACY_RAW_HEAD
        expected_columns = table_columns()
        if legacy_raw:
            expected_columns["matches"] = [
                column
                for column in expected_columns["matches"]
                if column not in {"kickoff_precision", "kickoff_provenance"}
            ]
        if manifest.columns != expected_columns or set(manifest.row_counts) != FOOTBALL_TABLES:
            raise ValueError()
        if {name for name in names if name.startswith("tables/")} != {
            f"tables/{table}.copy" for table in FOOTBALL_TABLES
        }:
            raise ValueError()
        if (set(TARGETS) - {"base_rating"}) - set(manifest.champions) or set(
            manifest.champions
        ) - set(TARGETS):
            raise ValueError()
        if (
            manifest.feature_schema != ("2.0.0" if legacy_raw else FEATURE_SCHEMA_VERSION)
            or manifest.lock_sha256 != dependency_hash()
        ):
            raise ValueError()
        if manifest.application_version != __version__:
            raise ValueError()
        if any(manifest.row_counts[table] == 0 for table in REQUIRED_TABLES):
            raise ValueError()
        if sum(record.size for record in manifest.files.values()) > 100 * 1024**3:
            raise ValueError()
        for name, record in manifest.files.items():
            if not name.startswith(
                (
                    "tables/",
                    "data/raw/",
                    "data/gold/",
                    "data/manifests/",
                    "artifacts/models/",
                    "artifacts/evaluations/",
                    "artifacts/source/",
                )
            ):
                raise ValueError()
            if archive.getinfo(name).file_size != record.size:
                raise ValueError()
            with archive.open(name) as source:
                if file_record(source) != record:
                    raise ValueError()
        for table, mapping in manifest.paths.items():
            if table not in {"feature_snapshot_metadata", "model_versions", "ingestion_runs"}:
                raise ValueError()
            for identifier, relative in mapping.items():
                uuid.UUID(identifier)
                safe_path(relative)
                prefix = "artifacts" if table == "model_versions" else "data"
                if f"{prefix}/{relative}" not in manifest.files:
                    raise ValueError()
        for table in ("feature_snapshot_metadata", "model_versions"):
            if len(manifest.paths.get(table, {})) != manifest.row_counts[table]:
                raise ValueError()
        _verify_champions(archive, manifest)
    return manifest


def _verify_champions(archive: zipfile.ZipFile, manifest: BundleManifest) -> None:
    def read_json(name: str) -> dict[str, Any]:
        if name not in manifest.files or manifest.files[name].size > 16 * BLOCK_SIZE:
            raise ValueError()
        value = json.loads(archive.read(name))
        if not isinstance(value, dict):
            raise ValueError()
        return value

    for target, version in manifest.champions.items():
        pointer = read_json(f"artifacts/models/{target}/champion.json")
        expected_manifest = f"{target}/{version}/manifest.json"
        if pointer.get("version") != version or pointer.get("manifest") != expected_manifest:
            raise ValueError()
        artifact = pointer.get("artifact", "")
        safe_path(artifact)
        if not artifact.startswith(f"{target}/{version}/model-") or not artifact.endswith(
            ".joblib"
        ):
            raise ValueError()
        record = manifest.files.get(f"artifacts/models/{artifact}")
        if record is None or Path(artifact).stem != f"model-{record.sha256}":
            raise ValueError()
        model = read_json(f"artifacts/models/{expected_manifest}")
        if (
            model.get("target") != target
            or model.get("version") != version
            or model.get("feature_schema_version") != manifest.feature_schema
        ):
            raise ValueError()
        revision = model.get("code_revision")
        if not revision or f"artifacts/source/{revision}.zip" not in manifest.files:
            raise ValueError()
        read_json(f"artifacts/evaluations/{target}/{version}.json")


class BinaryWriter(Protocol):
    def write(self, data: bytes, /) -> object: ...


def _copy_checked(source: BinaryReader, target: BinaryWriter, expected: FileRecord) -> None:
    digest, size = hashlib.sha256(), 0
    while block := source.read(BLOCK_SIZE):
        size += len(block)
        if size > expected.size:
            raise ValueError()
        digest.update(block)
        target.write(block)
    if FileRecord(size=size, sha256=digest.hexdigest()) != expected:
        raise ValueError()


def restore_bundle(settings: Settings, path: Path, *, expected_sha256: str) -> BundleManifest:
    return _restore_bundle(settings, path, expected_sha256=expected_sha256, raw_inputs_only=False)


def restore_raw_inputs(settings: Settings, path: Path, *, expected_sha256: str) -> BundleManifest:

    return _restore_bundle(settings, path, expected_sha256=expected_sha256, raw_inputs_only=True)


def _restore_bundle(
    settings: Settings,
    path: Path,
    *,
    expected_sha256: str,
    raw_inputs_only: bool,
) -> BundleManifest:
    manifest = verify_bundle(path, expected_sha256, raw_inputs_only=raw_inputs_only)
    included_tables = RAW_INPUT_TABLES if raw_inputs_only else FOOTBALL_TABLES
    run_manifests = {
        f"data/{relative}" for relative in manifest.paths.get("ingestion_runs", {}).values()
    }
    roots = {"data": settings.data_root.resolve(), "artifacts": settings.artifact_root.resolve()}
    if roots["data"].is_relative_to(roots["artifacts"]) or roots["artifacts"].is_relative_to(
        roots["data"]
    ):
        raise ValueError()
    created: list[Path] = []
    committed = False
    try:
        with (
            _verified_file(path, expected_sha256) as source_file,
            zipfile.ZipFile(source_file) as archive,
            connect(settings) as connection,
        ):
            connection.execute("SET LOCAL search_path TO public")

            connection.execute("SELECT pg_advisory_xact_lock(681753289)")
            for metadata_table in Base.metadata.sorted_tables:
                connection.execute(
                    sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(
                        sql.Identifier(metadata_table.name)
                    )
                )
            require_empty_database(connection)
            head = _scalar(connection, "SELECT version_num FROM alembic_version")
            compatible_migration = head == manifest.migration_head or (
                raw_inputs_only
                and (manifest.migration_head, head) == (_LEGACY_RAW_HEAD, _TEMPORAL_HEAD)
            )
            if not compatible_migration or (
                connection.info.server_version // 10000 != manifest.postgres_major
            ):
                raise ValueError()
            for root in roots.values():
                root.mkdir(parents=True, exist_ok=True)
                if any(root.iterdir()):
                    raise ValueError()
            for name in manifest.files:
                if raw_inputs_only and not (name.startswith("data/raw/") or name in run_manifests):
                    continue
                parts = safe_path(name).parts
                if parts[0] not in roots:
                    continue
                destination = roots[parts[0]].joinpath(*parts[1:])
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as target:
                    created.append(destination)
                    with archive.open(name) as source:
                        _copy_checked(source, target, manifest.files[name])
            for table, columns in table_columns().items():
                if table not in included_tables:
                    continue
                query = sql.SQL("COPY {} ({}) FROM STDIN (FORMAT BINARY)").format(
                    sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, columns))
                )
                with (
                    archive.open(f"tables/{table}.copy") as source,
                    connection.cursor().copy(query) as target,
                ):
                    _copy_checked(source, target, manifest.files[f"tables/{table}.copy"])
                count = _scalar(
                    connection, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                )
                if count != manifest.row_counts[table]:
                    raise ValueError()
                print(f"Restored {table}: {count} rows", flush=True)
            _rebase_paths(connection, manifest, roots, included_tables=included_tables)
        committed = True
    finally:
        if not committed:
            for created_path in reversed(created):
                created_path.unlink(missing_ok=True)
                parent = created_path.parent
                while parent not in roots.values():
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
    return manifest


def _rebase_paths(
    connection: psycopg.Connection[Any],
    manifest: BundleManifest,
    roots: dict[str, Path],
    *,
    included_tables: frozenset[str] = FOOTBALL_TABLES,
) -> None:
    for table, field, root_name in (
        ("feature_snapshot_metadata", "storage_path", "data"),
        ("model_versions", "artifact_path", "artifacts"),
    ):
        if table not in included_tables:
            continue
        mapping = manifest.paths.get(table, {})
        identifiers = {
            str(row[0])
            for row in connection.execute(
                sql.SQL("SELECT id FROM {}").format(sql.Identifier(table))
            )
        }
        if set(mapping) != identifiers:
            raise ValueError()
        for identifier, relative in mapping.items():
            connection.execute(
                sql.SQL("UPDATE {} SET {} = %s WHERE id = %s").format(
                    sql.Identifier(table), sql.Identifier(field)
                ),
                (str(roots[root_name] / relative), identifier),
            )
    for identifier, relative in manifest.paths.get("ingestion_runs", {}).items():
        connection.execute(
            "UPDATE ingestion_runs SET manifest = "
            "jsonb_set(manifest, '{path}', to_jsonb(%s::text)) WHERE id = %s",
            (str(roots["data"] / relative), identifier),
        )
