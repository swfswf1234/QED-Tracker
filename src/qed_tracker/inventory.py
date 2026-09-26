"""以 PDF 哈希为身份的本地资源清单。

ARCH-019 统一数据根：data_root 即 <QED_DATA_ROOT> 共享树——raw/ 为原始成品区
（唯一被外部读取），tmp/qed-tracker/downloads/ 为下载临时区（终态不保留）。

QED-071（A/B 轮拆岛）注意：<data_root>/qed-tracker/meta/resources/ 的单资源 JSON 岛
是 B 轮退役对象，**当前仍是内容身份（sha256/size/page_count）唯一载体**——书侧去重、
论文去重与 inventory verify 均依赖它；DB 内容身份列就位前不得停写（先迁列、后拆岛）。
Axiom 传输留痕（transfers 区）已判废删除（2026-09-24，D3，无读取方）。
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qed_tracker.downloader import DownloadedFile, inspect_pdf
from qed_tracker.models import Candidate, CatalogTarget, ResourceKind, ResourceRecord

logger = logging.getLogger("qed_tracker.inventory")

# 领域缺省：catalog 流程当前只服务 math-qe 目录；体系扩展后由调用方传 domain_id。
DEFAULT_DOMAIN_ID = "math"

# QED-071 R2/D7：staging 清扫阈值 = timeout × retries × 4，绝对下限 6 小时。
_STAGING_AGE_MULTIPLIER = 4
_STAGING_AGE_FLOOR_SECONDS = 6 * 3600


def staging_max_age_seconds(timeout_seconds: float, retries: int) -> int:
    """孤儿 staging 清扫阈值：严格大于单次下载最长寿命（timeout × retries）。

    4 倍安全系数 + 6 小时下限（裁决 D7）；卡死长连接由 httpx timeout 兜底，
    因此无需进程内 in-flight 注册表即可安全清扫。
    """
    return max(int(timeout_seconds * retries * _STAGING_AGE_MULTIPLIER), _STAGING_AGE_FLOOR_SECONDS)


def sweep_downloads(directory: Path, *, max_age_seconds: int) -> list[Path]:
    """按 mtime 年龄清扫本仓孤儿 staging 文件（QED-071 R2）。

    只匹配 `*.download` 与 `*.download.part` 两种本仓命名模式；非递归、不删目录、
    不碰其他项目前缀。失败（权限/占用）只告警不抛出，不得阻断取书任务。
    """
    removed: list[Path] = []
    if not directory.is_dir():
        return removed
    deadline = time.time() - max_age_seconds
    try:
        entries = sorted(directory.iterdir())
    except OSError as exc:
        logger.warning("staging 清扫目录不可读（跳过）：%s：%s", directory, exc)
        return removed
    for path in entries:
        if not path.is_file() or not path.name.endswith((".download", ".download.part")):
            continue
        try:
            if path.stat().st_mtime <= deadline:
                path.unlink()
                removed.append(path)
        except OSError as exc:
            logger.warning("staging 清扫失败（跳过）：%s：%s", path, exc)
    if removed:
        logger.info("staging 年龄清扫：移除 %d 个超龄中间态（>%ss）", len(removed), max_age_seconds)
    return removed


def raw_course_dir(data_root: Path, course_id: str, *, domain_id: str = DEFAULT_DOMAIN_ID) -> Path:
    """课程桶：raw/<domain_id>/<course_id>/（教材/习题成品落盘位）。"""
    return data_root / "raw" / domain_id / course_id


def raw_general_dir(data_root: Path, *, domain_id: str = DEFAULT_DOMAIN_ID) -> Path:
    """领域通用桶：raw/<domain_id>/_general/（inbox/论文等无法归属课程的文件）。"""
    return data_root / "raw" / domain_id / "_general"


def downloads_tmp_dir(data_root: Path) -> Path:
    """下载临时区：tmp/qed-tracker/downloads/（.part/.download 中间态，终态原子替换进 raw）。"""
    return data_root / "tmp" / "qed-tracker" / "downloads"


class Inventory:
    def __init__(self, data_root: Path):
        self.data_root = data_root.resolve()
        self.resources_dir = self.data_root / "qed-tracker" / "meta" / "resources"

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
