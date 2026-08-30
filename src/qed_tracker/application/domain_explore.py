"""领域探索状态机（QED-051 / REQ-067 B8）。

纯逻辑编排：接收 KnowledgeRepository 与 DomainPipeline（可注入假管线，零公网），
负责「探索中→已生成/已完成/失败」状态迁移、explore_pending 写负、全量自动落库。
不直接持有 FastAPI/网络；调用方（api task handler）负责提交任务的进程语义。

与 prompt_lab dry-run（只读不写）不同：本模块是正式流程，会写共享表
（qed_domain / qed_course），LLM 审计经管线内 engine 落 qed_llm_calls。
"""

from __future__ import annotations

from typing import Any

from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.prompt_lab.pipeline import NameConfirmationRequired

_STAGES = ["基础", "主干", "分支", "前沿"]


def _apply_domain(repo: KnowledgeRepository, domain_id: str, report: dict[str, Any]) -> None:
    """领域字段 upsert（探索产物列由本仓库写；name 由确认路径单独写）。"""
    d = report["domain"]
    path = report.get("path", {})
    repo.update_domain(
        domain_id,
        description=d.get("description", ""),
        level=d.get("level", ""),
        classic_tracks=d.get("classic_tracks", []),
        stages=list(_STAGES),
        path_results={"edges": path.get("edges", []), "graph_td": path.get("graph_td", "")},
    )


def _apply_courses(repo: KnowledgeRepository, domain_id: str, report: dict[str, Any]) -> dict[str, int]:
    """课程幂等 upsert（course_id=slug，契约同 import）；返回 {created, updated}。"""
    created = 0
    updated = 0
    for index, course in enumerate(report.get("courses", [])):
        slug = str(course["slug"])
        fields = dict(
            domain_id=domain_id, name=course["name"], stage=course.get("stage", ""),
            sort_order=index, description=course.get("summary", ""),
            aliases=course.get("aliases", []), track=course.get("track", ""),
            prerequisites=course.get("prerequisites", []),
        )
        if repo.get_course(slug) is None:
            repo.create_course(course_id=slug, **fields)
            created += 1
        else:
            repo.update_course(slug, stage=fields["stage"], sort_order=fields["sort_order"],
                               description=fields["description"], aliases=fields["aliases"],
                               track=fields["track"], prerequisites=fields["prerequisites"])
            updated += 1
    return {"created": created, "updated": updated}


def run_domain_explore(repo: KnowledgeRepository, pipeline: Any, *, domain_id: str,
                       scope_hint: str = "", mode: str = "direct", ref_text: str = "",
                       ref_doc_path: str = "", confirm_name_override: str = "") -> dict[str, Any]:
    """执行一次领域探索，返回 outcome 与落库统计。

    状态语义（调用方须已置「探索中」——explore/confirm-name 端点同步置位）：
    - NameConfirmationRequired（无 override）→ 置「已生成」+ explore_pending(name_confirm)；
    - 成功 → apply 全量落库 → 置「已完成」，explore_pending 清空；若有 override 且改名，写 name；
    - 其他异常 → 置「失败」+ explore_pending(failed)，重抛（交给 TaskManager 记 failed）。
    """
    domain = repo.get_domain(domain_id)
    if domain is None:
        raise KeyError(f"领域不存在：{domain_id}")
    try:
        report = pipeline.explore(
            domain.name,
            scope_hint=scope_hint, mode=mode, ref_text=ref_text, ref_doc_path=ref_doc_path,
            confirm_name_override=confirm_name_override,
        )
    except NameConfirmationRequired as exc:
        repo.update_domain(domain_id, exploration_stage="已生成",
                           explore_pending={"kind": "name_confirm", "name_check": exc.name_check})
        return {"outcome": "confirmation_required", "domain_id": domain_id}
    except Exception as exc:  # noqa: BLE001 - 管线异常统一写失败态后重抛（TaskManager 记 failed）
        repo.update_domain(domain_id, exploration_stage="失败",
                           explore_pending={"kind": "failed", "error": str(exc)[:500]})
        raise

    final_name = (confirm_name_override or "").strip() or str(domain.name)
    if confirm_name_override and final_name != domain.name:
        repo.update_domain(domain_id, name=final_name)

    _apply_domain(repo, domain_id, report)
    counts = _apply_courses(repo, domain_id, report)
    repo.update_domain(domain_id, exploration_stage="已完成", explore_pending=None)
    return {"outcome": "applied", "domain_id": domain_id,
            "courses_created": counts["created"], "courses_updated": counts["updated"]}
