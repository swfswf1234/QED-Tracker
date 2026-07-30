"""以 PDF 哈希为身份的本地资源清单。"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qed_tracker.downloader import DownloadedFile, inspect_pdf
from qed_tracker.models import Candidate, CatalogTarget, ResourceKind, ResourceRecord


class Inventory:
    def __init__(self, data_root: Path):
        self.data_root = data_root.resolve()
        self.resources_dir = self.data_root / ".qed-tracker" / "resources"
        self.transfers_dir = self.data_root / ".qed-tracker" / "transfers" / "axiom"

    def _record_path(self, digest: str) -> Path:
        return self.resources_dir / f"{digest}.json"

    def register(
        self,
        path: Path,
        *,
        kind: ResourceKind,
        title: str,
        authors: Iterable[str] = (),
        language: str = "",
        year: str = "",
        identifiers: dict[str, str] | None = None,
        source: dict[str, Any] | None = None,
        catalog_target: CatalogTarget | None = None,
    ) -> ResourceRecord:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.data_root)
        except ValueError as exc:
            raise ValueError(f"资源必须位于数据根目录内：{self.data_root}") from exc
        digest, size, page_count = inspect_pdf(resolved)
        downloaded = DownloadedFile(resolved, digest, size, page_count)
        return self._register_verified(
            downloaded,
            kind=kind,
            title=title,
            authors=authors,
            language=language,
            year=year,
            identifiers=identifiers,
            source=source,
            catalog_target=catalog_target,
        )

    def _register_verified(
        self,
        downloaded: DownloadedFile,
        *,
        kind: ResourceKind,
        title: str,
        authors: Iterable[str] = (),
        language: str = "",
        year: str = "",
        identifiers: dict[str, str] | None = None,
        source: dict[str, Any] | None = None,
        catalog_target: CatalogTarget | None = None,
    ) -> ResourceRecord:
        resolved = downloaded.path.resolve()
        try:
            relative = resolved.relative_to(self.data_root).as_posix()
        except ValueError as exc:
            raise ValueError(f"资源必须位于数据根目录内：{self.data_root}") from exc
        existing = self.get(downloaded.sha256)
        if existing and existing.absolute_path(self.data_root).exists():
            return existing
        record = ResourceRecord(
            resource_id=f"sha256:{downloaded.sha256}",
            kind=kind.value,
            title=title or resolved.stem,
            authors=list(authors),
            language=language,
            year=year,
            identifiers=identifiers or {},
            source=source or {"provider": "local", "retrieved_at": datetime.now(UTC).isoformat()},
            file={
                "relative_path": relative,
                "sha256": downloaded.sha256,
                "size_bytes": downloaded.size_bytes,
                "mime_type": "application/pdf",
                "page_count": downloaded.page_count,
            },
            catalog_ref=(
                {"catalog_id": "math-qe", "target_id": catalog_target.id, "course_id": catalog_target.course_id}
                if catalog_target
                else None
            ),
        )
        target = self._record_path(downloaded.sha256)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)
        return record

    def register_candidate(
        self, downloaded: DownloadedFile, candidate: Candidate, kind: ResourceKind, catalog_target: CatalogTarget | None = None
    ) -> ResourceRecord:
        return self._register_verified(
            downloaded,
            kind=kind,
            title=candidate.title,
            authors=candidate.authors,
            language=candidate.language,
            year=candidate.year,
            identifiers=candidate.identifiers,
            source={
                "provider": candidate.provider,
                "provider_id": candidate.provider_id,
                "page_url": candidate.page_url,
                "download_url": candidate.download_url,
                "retrieved_at": datetime.now(UTC).isoformat(),
            },
            catalog_target=catalog_target,
        )

    def get(self, resource_id: str) -> ResourceRecord | None:
        digest = resource_id.removeprefix("sha256:")
        path = self._record_path(digest)
        if not path.exists():
            return None
        return ResourceRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def find_by_catalog_target(self, catalog_id: str, target_id: str) -> ResourceRecord | None:
        for record in self.list():
            reference = record.catalog_ref or {}
            if reference.get("catalog_id") == catalog_id and reference.get("target_id") == target_id:
                return record
        return None

    def list(self, kind: str | None = None) -> list[ResourceRecord]:
        if not self.resources_dir.exists():
            return []
        records = [ResourceRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in self.resources_dir.glob("*.json")]
        if kind:
            records = [record for record in records if record.kind == kind]
        return sorted(records, key=lambda record: (record.kind, record.title.casefold(), record.resource_id))

    def verify(self) -> list[tuple[ResourceRecord, str]]:
        results = []
        for record in self.list():
            path = record.absolute_path(self.data_root)
            if not path.exists():
                results.append((record, "missing"))
                continue
            try:
                digest, size, pages = inspect_pdf(path)
            except Exception as exc:
                results.append((record, f"invalid: {exc}"))
                continue
            status = "ok" if (digest == record.sha256 and size == record.file["size_bytes"] and pages == record.file["page_count"]) else "changed"
            results.append((record, status))
        return results

    def scan(self, roots: Iterable[Path]) -> tuple[list[ResourceRecord], list[tuple[Path, str]]]:
        registered: list[ResourceRecord] = []
        errors: list[tuple[Path, str]] = []
        for root in roots:
            for path in sorted(root.resolve().rglob("*.pdf")):
                try:
                    registered.append(self.register(path, kind=ResourceKind.BOOK, title=path.stem))
                except Exception as exc:
                    errors.append((path, str(exc)))
        return registered, errors

    def record_axiom_transfer(self, resource: ResourceRecord, payload: dict[str, Any]) -> Path:
        digest = resource.resource_id.removeprefix("sha256:")
        target = self.transfers_dir / f"{digest}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return target
