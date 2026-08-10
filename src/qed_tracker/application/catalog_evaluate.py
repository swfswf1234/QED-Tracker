"""书单按课程批量评估用例（QED-013）。

流程：搜索源 → 严格匹配 → LLM 评估（宁缺勿滥，低分不收录）→ 候选落库 candidate；
来源不可得时中文书登记 pending_manual、英文书登记 not_found；
同 catalog_ref + title 已拒候选跳过不重复推荐。
模型只生成可审阅评估（llm_evaluation），不写资源事实、不自动下载。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol

from qed_tracker.application.books import BookService
from qed_tracker.catalog import Catalog
from qed_tracker.db.models import ResourceStatus
from qed_tracker.db.repository import ResourceRepository
from qed_tracker.models import BookAssessment, Candidate

MIN_RECOMMEND_SCORE = 60


def _source_failure_reason(failures: list[tuple[str, str]]) -> str:
    """来源失败原因：列出每个 provider 的具体错误（便于定位卡点，如 DNS 污染/限流）。"""
    if not failures:
        return "来源不可得"
    details = "; ".join(f"{name}: {error[:160]}" for name, error in failures)
    return f"来源不可得（{details}）"


class BookAdvisor(Protocol):
    model_name: str

    def assess(self, candidates: list[Candidate], *, target) -> list[BookAssessment]: ...

    def close(self) -> None: ...


def _catalog_ref(catalog: Catalog, target) -> dict[str, str]:
    return {"catalog_id": catalog.id, "target_id": target.id, "course_id": target.course_id}


def _source_dict(candidate: Candidate) -> dict[str, str]:
    source = {
        "provider": candidate.provider,
        "provider_id": candidate.provider_id,
        "page_url": candidate.page_url,
        "download_url": candidate.download_url,
    }
    if candidate.file_keywords:
        source["file_keywords"] = list(candidate.file_keywords)
    if candidate.links:
        # QED-021：metadata_only 来源的人工下载方案（torrent/IPFS/ed2k）随 source 落库
        from dataclasses import asdict

        source["links"] = [asdict(link) for link in candidate.links]
    return source


class CatalogEvaluator:
    def __init__(self, books: BookService, repository: ResourceRepository, *, advisor: BookAdvisor | None = None):
        self.books = books
        self.repository = repository
        self.advisor = advisor

    def evaluate(self, catalog: Catalog, *, course: str = "", limit: int = 8, progress: Callable[[int, str], None] | None = None) -> dict[str, Any]:
        report: dict[str, Any] = {
            "catalog_id": catalog.id,
            "course_id": course or None,
            "targets": 0,
            "candidates": [],
            "pending_manual": [],
            "not_found": [],
            "skipped": [],
            "errors": [],
        }
        targets = [target for target in catalog.targets if not course or target.course_id.startswith(course.zfill(2))]
        total = len(targets)
        seen_provider_ids: dict[str, str] = {}  # QED-020：单次评估内同来源只收录首个目标（provider_id → 首次目标 id）
        for index, target in enumerate(targets, start=1):
            report["targets"] += 1
            ref = _catalog_ref(catalog, target)
            if progress is not None:
                progress(int(30 + (index - 1) / total * 60), f"评估 {index}/{total}：{target.id}（{target.title}）搜索中")
            try:
                self._evaluate_target(target, ref, limit, report, seen_provider_ids)
            except Exception as exc:  # noqa: BLE001 - 单目标失败不中断整个任务
                report["errors"].append({"target_id": target.id, "error": str(exc)[:300]})
                if progress is not None:
                    progress(int(30 + index / total * 60), f"评估 {index}/{total}：{target.id} 失败：{str(exc)[:120]}")
        return report

    def _evaluate_target(self, target, ref: dict[str, str], limit: int, report: dict[str, Any], seen_provider_ids: dict[str, str]) -> None:
        if self.repository.find_rejected_same_source(catalog_ref=ref, title=target.title):
            report["skipped"].append({"target_id": target.id, "reason": "同源候选此前已被拒绝"})
            return
        existing = self.repository.find_by_ref(ref)
        if existing is not None and existing.status not in (ResourceStatus.PENDING_MANUAL.value, ResourceStatus.NOT_FOUND.value):
            # 已有人工决策/进行中（backup/approved/rejected/confirmed/downloading/downloaded/failed）：
            # 跳过不重复推荐，也不得重置回 candidate（QED-017）
            report["skipped"].append({"target_id": target.id, "reason": f"已有登记（{existing.status}）"})
            return
        ranked = self.books.search(target.query or target.title, limit=limit, target=target)
        strict = next((item for item in ranked if item.match and item.match.strict), None)
        if strict is None:
            reason = _source_failure_reason(self.books.failures)
            self.repository.upsert_candidate(
                title=target.title,
                authors=target.authors,
                language=target.language,
                edition=target.edition,
                kind=target.kind.value,
                source={"provider": "", "provider_id": ""},
                catalog_ref=ref,
            )
            row = self.repository.find_candidate_by_ref(ref)
            if target.language == "zh":
                self.repository.mark_pending_manual(row.resource_id)
                report["pending_manual"].append({"target_id": target.id, "reason": reason})
            else:
                self.repository.mark_not_found(row.resource_id)
                report["not_found"].append({"target_id": target.id, "reason": reason})
            return
        candidate = strict.candidate
        if candidate.provider_id and candidate.provider_id in seen_provider_ids and not target.file_hint:
            # QED-020：单次评估内同一来源（provider_id）只收录首个目标，避免重复推荐；
            # file_hint 目标例外（QED-021 裁决）：同一条目多个 PDF（上/下/答案）按
            # 文件名关键词分别收录，各自 resolve 选对应文件，不受同源去重限制。
            report["skipped"].append({"target_id": target.id, "reason": f"同来源已由首次目标覆盖（{seen_provider_ids[candidate.provider_id]}）"})
            return
        if target.file_hint:
            # QED-019：同条目多 PDF（教材 + 配套习题答案）时按文件名关键词精确下载
            candidate = replace(candidate, file_keywords=(target.file_hint,))
        if candidate.availability == "metadata_only":
            # QED-021：libgen 等发现专用来源 resolve 填充人工下载方案（links），
            # 随候选落库供前端展示；resolve 失败不阻断收录（仍可后续按 page_url 人工处理）
            try:
                candidate = self.books.resolve(candidate)
            except Exception as exc:  # noqa: BLE001 - 方案解析失败降级为无 links 候选
                report["errors"].append({"target_id": target.id, "error": f"解析下载方案失败：{str(exc)[:200]}"})
        evaluation = None
        if self.advisor is not None:
            try:
                assessment = self.advisor.assess([candidate], target=target)[0]
            except Exception as exc:  # noqa: BLE001 - 模型失败降级为无评估候选
                report["errors"].append({"target_id": target.id, "error": f"模型评估失败：{str(exc)[:200]}"})
            else:
                if assessment.score < MIN_RECOMMEND_SCORE:
                    report["skipped"].append({"target_id": target.id, "reason": f"模型评分过低（{assessment.score}）"})
                    return
                evaluation = {
                    "score": assessment.score,
                    "verdict": assessment.verdict,
                    "summary": assessment.summary,
                    "model": self.advisor.model_name,
                    "evaluated_at": datetime.now(UTC).isoformat(),
                }
        row = self.repository.upsert_candidate(
            title=candidate.title,
            authors=candidate.authors,
            language=candidate.language,
            year=candidate.year,
            edition=candidate.edition,
            kind=target.kind.value,
            source=_source_dict(candidate),
            llm_evaluation=evaluation,
            catalog_ref=ref,
        )
        if candidate.provider_id:
            seen_provider_ids[candidate.provider_id] = target.id
        report["candidates"].append({"target_id": target.id, "resource_id": row.resource_id, "title": row.title})
