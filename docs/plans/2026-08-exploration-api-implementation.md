# 探索 API 联调实现计划（QED-040/041 Phase 3a-3c）

状态：Current
最后更新：2026-08-24

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现探索 API 全部 8 端点 + 2 个任务处理器 + CurriculumExploreAdvisor，使前端能真实调用 LLM 发起领域探索和课程探索。

**Architecture:** 在 `main.py` 的 `create_app` 中合并探索 handler 到 TaskManager；探索端点直接定义在 FastAPI app 上（沿用既有路由模式）；CurriculumExploreAdvisor 补齐 explore_advisor.py 最后一块；adopt 端点通过 KnowledgeRepository.create_knowledge 单事务落库。

**Tech Stack:** FastAPI + SQLAlchemy ORM + httpx.MockTransport（测试） + 百炼 qwen-plus（真实 LLM）

---

## 文件结构

| 文件 | 职责 | 变更类型 |
|------|------|----------|
| `src/qed_tracker/providers/explore_advisor.py` | 新增 `CurriculumExploreAdvisor` 类 | 修改（追加 ~90 行） |
| `src/qed_tracker/api/main.py` | 新增 8 个探索路由 + 2 个 task handler + Application 持有 ExplorationRepository | 修改（追加 ~200 行） |
| `tests/test_explore_advisor.py` | 已有课程层 11 测试；新增领域层 7 测试 | 修改（追加 ~100 行） |
| `tests/test_api.py` | 新增探索 API 契约测试 | 修改（追加 ~150 行） |

---

## Task 1: CurriculumExploreAdvisor（领域层 LLM advisor）

**前置条件：** `CourseExploreAdvisor` 已完成且通过 11 个测试。`CurriculumExploreAdvisor` 已在测试文件中定义 7 个用例但 import 会失败（类不存在）。

**Files:**
- Modify: `src/qed_tracker/providers/explore_advisor.py`（追加 `CurriculumExploreAdvisor` 类）
- Test: `tests/test_explore_advisor.py`（已有 7 个领域层测试用例）

- [ ] **Step 1: 确认测试文件已引用 CurriculumExploreAdvisor**

检查 `tests/test_explore_advisor.py` 中 import 和 7 个 curriculum 测试用例存在。已确认（本次会话早期写入）。

- [ ] **Step 2: 运行测试确认 ImportError（RED）**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_explore_advisor.py -q`
Expected: collection ERROR — `ImportError: cannot import name 'CurriculumExploreAdvisor'`

- [ ] **Step 3: 实现 CurriculumExploreAdvisor 类**

在 `src/qed_tracker/providers/explore_advisor.py` 末尾追加：

```python
class CurriculumExploreAdvisor(ExploreAdvisorBase):
    """领域层：为新领域提议课程体系变更序列（4~9 条 changes，create_domain 居首）。"""

    contract_version = "curriculum-explore-v1"

    def propose(
        self,
        domain_name: str,
        *,
        mode: str,
        ref_text: str = "",
        ref_doc_path: str = "",
    ) -> list[dict[str, Any]]:
        payload = {
            "domain_name": domain_name,
            "reference": _read_reference(mode, ref_text, ref_doc_path),
        }
        self.last_payload = payload
        messages = [
            {
                "role": "system",
                "content": "你是课程体系设计顾问。根据新领域名称与探索过程参考文档，"
                "提议该领域的课程体系变更序列。" + _UNTRUSTED_NOTE + _STRICT_JSON_NOTE,
            },
            {
                "role": "user",
                "content": "为下述新领域设计课程体系。要求：\n"
                "- create_domain 恰好一条且居首；随后 3~8 条 create_course；\n"
                "- target_id 用小写 slug（^[a-z0-9][a-z0-9_]{1,62}$）；\n"
                "- stage 必须取自 create_domain.payload.stages；\n"
                "- sort_order 从 1 递增；\n"
                "- prerequisites 仅引用本批 course target_id；\n"
                "- change_id 不输出（服务端生成）。\n"
                '输出格式：{"changes":[{"action":"create_domain","entity":"domain","target_id":"<slug>",'
                '"payload":{"name":"...","description":"...","stages":["本科基础","本科进阶"]},'
                '"reason":"..."},{"action":"create_course","entity":"course","target_id":"<slug>",'
                '"payload":{"name":"...","stage":"本科基础","sort_order":1,'
                '"prerequisites":[],"aliases":[],"note":"..."},"reason":"..."}]}\n'
                + json.dumps(payload, ensure_ascii=False),
            },
        ]
        changes = self._structured(messages, self._validate)
        enriched: list[dict[str, Any]] = []
        for idx, item in enumerate(changes, start=1):
            entry = dict(item)
            entry["change_id"] = f"ch_{idx:02d}"
            enriched.append(entry)
        return enriched

    @staticmethod
    def _validate(value: object) -> list[dict[str, Any]]:
        if not isinstance(value, dict) or not isinstance(value.get("changes"), list):
            raise ValueError("缺少 changes 数组")
        items = value["changes"]
        if not 4 <= len(items) <= 9:
            raise ValueError("changes 数量必须为 4 到 9")
        first = items[0]
        if not isinstance(first, dict) or first.get("action") != "create_domain" or first.get("entity") != "domain":
            raise ValueError("首位必须是 create_domain")
        domain_payload = first.get("payload", {})
        stages = domain_payload.get("stages", [])
        if not isinstance(stages, list) or not (2 <= len(stages) <= 5) or not all(isinstance(s, str) for s in stages):
            raise ValueError("domain.payload.stages 必须是 2~5 个字符串数组")
        _require_text(domain_payload.get("name"), 100, "domain.payload.name")
        _require_text(domain_payload.get("description"), 500, "domain.payload.description")
        seen_slugs: set[str] = set()
        for item in items[1:]:
            if not isinstance(item, dict) or item.get("action") != "create_course":
                raise ValueError("非首位必须是 create_course")
            slug = str(item.get("target_id", ""))
            if not _SLUG_PATTERN.match(slug):
                raise ValueError(f"target_id 格式非法：{slug}")
            if slug in seen_slugs:
                raise ValueError(f"target_id 批内重复：{slug}")
            seen_slugs.add(slug)
            payload = item.get("payload", {})
            if not isinstance(payload, dict):
                raise ValueError("course payload 必须是对象")
            _require_text(payload.get("name"), 100, "course.payload.name")
            stage = payload.get("stage", "")
            if stage not in stages:
                raise ValueError(f"stage 不在领域 stages 内：{stage}")
            sort_order = payload.get("sort_order")
            if not isinstance(sort_order, int) or sort_order < 1:
                raise ValueError(f"sort_order 必须是正整数：{sort_order}")
            prereqs = payload.get("prerequisites", [])
            if not isinstance(prereqs, list) or not all(p in seen_slugs for p in prereqs):
                raise ValueError(f"prerequisites 越界引用：{prereqs}")
            aliases = payload.get("aliases", [])
            if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
                raise ValueError("aliases 必须是字符串数组")
            _require_text(item.get("reason"), 500, "reason")
        return [dict(item) for item in items]
```

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_explore_advisor.py -q`
Expected: 18 passed（11 课程层 + 7 领域层）

- [ ] **Step 5: 提交**

```bash
git add src/qed_tracker/providers/explore_advisor.py tests/test_explore_advisor.py
git commit -m "feat(explore): add CurriculumExploreAdvisor with validate+repair-retry"
```

---

## Task 2: Application 持有 ExplorationRepository + 探索 handler 闭包

**Files:**
- Modify: `src/qed_tracker/api/main.py`（Application.__init__ + create_app）

- [ ] **Step 1: Application 新增 exploration_repository 属性**

在 `Application.__init__` 中（约 line 74 后），追加 exploration_repository 初始化：

```python
        self._exploration_repository = None
        if settings.db_configured:
            from qed_tracker.db.exploration_repository import ExplorationRepository
            from qed_tracker.database import create_engine_for, session_factory as sf

            engine = self._db_engine or create_engine_for(settings)
            self._exploration_repository = ExplorationRepository(sf(engine))
```

注意：如果 `_db_engine` 已创建则复用，避免重复引擎。需在 `__init__` 开头调整引擎创建顺序——先决定 engine，再建 repository。实际改法：

将 `_db_engine` 和 `_knowledge_repository` 的创建提到 advisor 之前，`_exploration_repository` 紧随其后。

- [ ] **Step 2: 新增 _explore_course_handler 闭包**

在 `create_app` 函数内（`manager = TaskManager(...)` 之后、`lifespan` 之前），定义：

```python
    def _explore_course_handler(params: dict[str, Any], progress) -> dict[str, Any]:
        from qed_tracker.providers.explore_advisor import CourseExploreAdvisor, ExploreAdvisorError

        run_id = params["run_id"]
        er = app._exploration_repository
        if er is None:
            er.finish_failed(run_id, error={"code": "DB_UNAVAILABLE", "message": "数据库未配置"})
            return {"run_id": run_id, "status": "failed"}
        run = er.get_run(run_id)
        if run is None:
            return {"run_id": run_id, "status": "not_found"}
        course_id = run.course_id
        kr = app._knowledge_repository
        if kr is None:
            er.finish_failed(run_id, error={"code": "DB_UNAVAILABLE", "message": "知识库未配置"})
            return {"run_id": run_id, "status": "failed"}
        with kr._session_factory() as session:
            from qed_tracker.db.models import QedCourse
            course_row = session.get(QedCourse, course_id)
        if course_row is None:
            er.finish_failed(run_id, error={"code": "COURSE_NOT_FOUND", "message": f"课程不存在：{course_id}"})
            return {"run_id": run_id, "status": "failed"}
        if app.advisor is None:
            er.finish_failed(run_id, error={"code": "LLM_UNAVAILABLE", "message": "未配置 LLM 密钥"})
            return {"run_id": run_id, "status": "failed"}
        advisor_kwargs = dict(
            api_key=llm_api_key(),
            model=app.settings.llm_model,
            base_url=app.settings.llm_base_url,
            timeout=app.settings.llm_timeout_seconds,
            call_budget=app.settings.llm_call_budget,
            max_tokens=app.settings.llm_max_tokens,
            api_select=app.settings.api_select,
            gateway_url=app.settings.llm_gateway_url,
            engine=app._db_engine,
        )
        advisor = CourseExploreAdvisor(**advisor_kwargs)
        try:
            course_dict = {
                "course_id": course_row.course_id,
                "name": course_row.name,
                "stage": course_row.stage,
                "prerequisites": list(course_row.prerequisites),
                "note": course_row.note,
            }
            proposals = advisor.propose(
                course_dict,
                mode=run.params.get("mode", "direct"),
                ref_text=run.params.get("ref_text", ""),
                ref_doc_path=run.params.get("ref_doc_path", ""),
            )
            er.finish_ready(run_id, proposals=proposals, meta=advisor.metadata())
            return {"run_id": run_id, "status": "ready", "proposal_count": len(proposals)}
        except ExploreAdvisorError as exc:
            er.finish_failed(run_id, error={"code": exc.code, "message": str(exc)})
            return {"run_id": run_id, "status": "failed", "error": exc.code}
        finally:
            advisor.close()
```

- [ ] **Step 3: 新增 _explore_curriculum_handler 闭包**

```python
    def _explore_curriculum_handler(params: dict[str, Any], progress) -> dict[str, Any]:
        from qed_tracker.providers.explore_advisor import CurriculumExploreAdvisor, ExploreAdvisorError

        run_id = params["run_id"]
        er = app._exploration_repository
        if er is None:
            er.finish_failed(run_id, error={"code": "DB_UNAVAILABLE", "message": "数据库未配置"})
            return {"run_id": run_id, "status": "failed"}
        run = er.get_run(run_id)
        if run is None:
            return {"run_id": run_id, "status": "not_found"}
        if app.advisor is None:
            er.finish_failed(run_id, error={"code": "LLM_UNAVAILABLE", "message": "未配置 LLM 密钥"})
            return {"run_id": run_id, "status": "failed"}
        advisor_kwargs = dict(
            api_key=llm_api_key(),
            model=app.settings.llm_model,
            base_url=app.settings.llm_base_url,
            timeout=app.settings.llm_timeout_seconds,
            call_budget=app.settings.llm_call_budget,
            max_tokens=app.settings.llm_max_tokens,
            api_select=app.settings.api_select,
            gateway_url=app.settings.llm_gateway_url,
            engine=app._db_engine,
        )
        advisor = CurriculumExploreAdvisor(**advisor_kwargs)
        try:
            changes = advisor.propose(
                run.domain_name,
                mode=run.params.get("mode", "direct"),
                ref_text=run.params.get("ref_text", ""),
                ref_doc_path=run.params.get("ref_doc_path", ""),
            )
            er.finish_ready(run_id, proposals=changes, meta=advisor.metadata())
            return {"run_id": run_id, "status": "ready", "change_count": len(changes)}
        except ExploreAdvisorError as exc:
            er.finish_failed(run_id, error={"code": exc.code, "message": str(exc)})
            return {"run_id": run_id, "status": "failed", "error": exc.code}
        finally:
            advisor.close()
```

- [ ] **Step 4: 合并 handler 到 TaskManager**

修改 `manager = TaskManager(...)` 那行：

```python
    explore_handlers = {
        "explore_course": _explore_course_handler,
        "explore_curriculum": _explore_curriculum_handler,
    }
    all_handlers = {**explore_handlers, **(extra_handlers or {})}
    manager = TaskManager(TaskStore(settings.state_dir / "tasks"), all_handlers)
```

- [ ] **Step 5: 确认现有测试不回归**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_api.py -q`
Expected: 全部通过（现有端点不受影响）

---

## Task 3: 课程层五端点

**Files:**
- Modify: `src/qed_tracker/api/main.py`（追加路由定义）

- [ ] **Step 1: 新增 api_error 辅助函数**

在 `_candidate_dict` 函数之后（line ~108），追加：

```python
def api_error(status_code: int, code: str, message: str) -> HTTPException:
    """新端点专用错误结构：{detail:{code,message}}。"""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})
```

- [ ] **Step 2: 新增 _explore_run_view 辅助**

```python
def _explore_run_view(run) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "scope": run.scope,
        "course_id": run.course_id,
        "domain_name": run.domain_name,
        "status": run.status,
        "params": run.params,
        "proposals": run.proposals,
        "adopted_proposal_ids": run.adopted_ids,
        "conflicts": run.conflicts,
        "error": run.error,
        "task_id": run.task_id,
        "meta": run.meta,
        "created_at": run.created_at.isoformat() if hasattr(run.created_at, "isoformat") else str(run.created_at),
        "updated_at": run.updated_at.isoformat() if hasattr(run.updated_at, "isoformat") else str(run.updated_at),
    }
```

- [ ] **Step 3: POST /api/v1/courses/{course_id}/explore**

在 `tasks` 路由之前（line ~480），追加：

```python
    # ---------------- 探索端点（QED-040/041） ----------------

    def _er(app: Application):
        if app._exploration_repository is None:
            raise api_error(409, "DB_UNAVAILABLE", "数据库未配置：探索端点需 QtExploreRun 表")
        return app._exploration_repository

    @fastapi_app.post("/api/v1/courses/{course_id}/explore", status_code=202)
    def course_explore(course_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        mode = payload.get("mode", "direct")
        if mode not in ("direct", "text", "doc"):
            raise api_error(400, "INVALID_PARAMS", f"非法 mode：{mode}")
        ref_text = payload.get("ref_text", "")
        ref_doc_path = payload.get("ref_doc_path", "")
        if mode == "text" and not (ref_text or "").strip():
            raise api_error(400, "INVALID_PARAMS", "mode=text 必须提供 ref_text")
        if mode == "doc":
            from pathlib import Path
            if not (ref_doc_path or "").strip() or not Path(ref_doc_path).is_file():
                raise api_error(400, "INVALID_PARAMS", f"ref_doc_path 不可读：{ref_doc_path}")
        kr = app._knowledge_repository
        if kr is None:
            raise api_error(409, "DB_UNAVAILABLE", "数据库未配置")
        with kr._session_factory() as session:
            from qed_tracker.db.models import QedCourse
            if session.get(QedCourse, course_id) is None:
                raise api_error(404, "COURSE_NOT_FOUND", f"课程不存在：{course_id}")
        er = _er(app)
        if er.find_running("course", course_id):
            raise api_error(409, "COURSE_EXPLORATION_IN_PROGRESS", "该课程已有进行中的探索任务")
        run = er.create_run("course", course_id=course_id, params={"mode": mode, "ref_text": ref_text, "ref_doc_path": ref_doc_path})
        record = manager.submit("explore_course", {"run_id": run.run_id})
        er.attach_task(run.run_id, record.task_id)
        return {"run_id": run.run_id, "task_id": record.task_id, "status": "running"}
```

- [ ] **Step 4: GET /api/v1/explore-runs/{run_id}**

```python
    @fastapi_app.get("/api/v1/explore-runs/{run_id}")
    def explore_run_detail(run_id: str) -> dict[str, Any]:
        er = _er(app)
        run = er.get_run(run_id)
        if run is None:
            raise api_error(404, "RUN_NOT_FOUND", f"探索运行不存在：{run_id}")
        # 孤儿 running 兜底
        if run.status == "running" and run.task_id:
            task = manager.get(run.task_id)
            if task is None or task.status == "failed":
                code = "TASK_LOST" if task is None else "TASK_FAILED"
                er.finish_failed(run_id, error={"code": code, "message": f"任务{code}"})
                run = er.get_run(run_id)
        return _explore_run_view(run)
```

- [ ] **Step 5: POST /api/v1/explore-runs/{run_id}/adopt**

```python
    @fastapi_app.post("/api/v1/explore-runs/{run_id}/adopt")
    def explore_run_adopt(run_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        selected = payload.get("selected", [])
        if not isinstance(selected, list) or not selected:
            raise api_error(400, "INVALID_PARAMS", "selected 必须是非空数组")
        er = _er(app)
        run = er.get_run(run_id)
        if run is None:
            raise api_error(404, "RUN_NOT_FOUND", f"探索运行不存在：{run_id}")
        if run.status != "ready":
            raise api_error(409, "RUN_STATE_CONFLICT", f"当前状态 {run.status} 不允许采纳")
        proposals = run.proposals or []
        proposal_ids = {p["proposal_id"] for p in proposals}
        invalid = [sid for sid in selected if sid not in proposal_ids]
        if invalid:
            raise api_error(400, "INVALID_PARAMS", f"未知 proposal_id：{invalid}")
        kr = app._knowledge_repository
        if kr is None:
            raise api_error(409, "DB_UNAVAILABLE", "知识库未配置")
        with kr._session_factory() as session:
            from sqlalchemy import func as sa_func
            from qed_tracker.db.models import QtKnowledge
            count = session.scalar(
                sa_func.count().select_from(QtKnowledge).where(
                    QtKnowledge.course_id == run.course_id,
                    QtKnowledge.kind == "tutorial",
                    QtKnowledge.status.in_(["draft", "confirmed", "completed"]),
                )
            ) or 0
        remaining = 4 - count
        if len(selected) > remaining:
            raise api_error(409, "CAPACITY_REACHED", f"剩余槽位 {remaining}，已选 {len(selected)}")
        adopted = []
        for proposal in proposals:
            if proposal["proposal_id"] in selected:
                knowledge = kr.create_knowledge(
                    domain_id=run.course_id.split("_")[0] if "_" in run.course_id else "math",
                    course_id=run.course_id,
                    kind="tutorial",
                    set_no=proposal.get("set_no", ""),
                    name=tutorial_name(proposal.get("set_no", ""), proposal["textbook"]["title"], proposal["textbook"].get("authors", [])),
                )
                adopted.append({"knowledge_id": knowledge.knowledge_id, "set_name": proposal["set_name"]})
        er.adopt_run(run_id, adopted_ids=[a["knowledge_id"] for a in adopted])
        run = er.get_run(run_id)
        return {"adopted": adopted, "remaining_slots": 4 - count - len(selected), "run": _explore_run_view(run)}
```

- [ ] **Step 6: POST /api/v1/explore-runs/{run_id}/discard**

```python
    @fastapi_app.post("/api/v1/explore-runs/{run_id}/discard")
    def explore_run_discard(run_id: str) -> dict[str, Any]:
        er = _er(app)
        run = er.get_run(run_id)
        if run is None:
            raise api_error(404, "RUN_NOT_FOUND", f"探索运行不存在：{run_id}")
        if run.status not in ("ready", "discarded"):
            raise api_error(409, "RUN_STATE_CONFLICT", f"当前状态 {run.status} 不允许放弃")
        er.discard_run(run_id)
        return _explore_run_view(er.get_run(run_id))
```

- [ ] **Step 7: GET /api/v1/courses/{course_id}/explore-runs**

```python
    @fastapi_app.get("/api/v1/courses/{course_id}/explore-runs")
    def course_explore_runs(course_id: str, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> list[dict[str, Any]]:
        er = _er(app)
        runs = er.list_runs("course", course_id, limit=limit, offset=offset)
        return [
            {
                "run_id": r.run_id, "status": r.status,
                "proposal_count": len(r.proposals) if r.proposals else 0,
                "adopted_count": len(r.adopted_ids) if r.adopted_ids else 0,
                "created_at": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
                "updated_at": r.updated_at.isoformat() if hasattr(r.updated_at, "isoformat") else str(r.updated_at),
            }
            for r in runs
        ]
```

- [ ] **Step 8: 确认现有测试不回归**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_api.py -q`
Expected: 全部通过

---

## Task 4: 领域层三端点

**Files:**
- Modify: `src/qed_tracker/api/main.py`（追加路由定义）

- [ ] **Step 1: POST /api/v1/curriculum-explore**

```python
    @fastapi_app.post("/api/v1/curriculum-explore", status_code=202)
    def curriculum_explore(payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        domain_name = (payload.get("domain_name") or "").strip()
        if not domain_name or len(domain_name) > 100:
            raise api_error(400, "INVALID_PARAMS", "domain_name 必须是 1~100 字符")
        mode = payload.get("mode", "direct")
        if mode not in ("direct", "text", "doc"):
            raise api_error(400, "INVALID_PARAMS", f"非法 mode：{mode}")
        ref_text = payload.get("ref_text", "")
        ref_doc_path = payload.get("ref_doc_path", "")
        if mode == "text" and not (ref_text or "").strip():
            raise api_error(400, "INVALID_PARAMS", "mode=text 必须提供 ref_text")
        if mode == "doc":
            from pathlib import Path
            if not (ref_doc_path or "").strip() or not Path(ref_doc_path).is_file():
                raise api_error(400, "INVALID_PARAMS", f"ref_doc_path 不可读：{ref_doc_path}")
        er = _er(app)
        if er.find_running("curriculum", domain_name):
            raise api_error(409, "CURRICULUM_EXPLORATION_IN_PROGRESS", "该领域已有进行中的探索任务")
        run = er.create_run("curriculum", domain_name=domain_name, params={"mode": mode, "ref_text": ref_text, "ref_doc_path": ref_doc_path})
        record = manager.submit("explore_curriculum", {"run_id": run.run_id})
        er.attach_task(run.run_id, record.task_id)
        return {"run_id": run.run_id, "task_id": record.task_id, "status": "running"}
```

- [ ] **Step 2: GET /api/v1/curriculum-runs/{run_id}**

```python
    @fastapi_app.get("/api/v1/curriculum-runs/{run_id}")
    def curriculum_run_detail(run_id: str) -> dict[str, Any]:
        er = _er(app)
        run = er.get_run(run_id)
        if run is None:
            raise api_error(404, "RUN_NOT_FOUND", f"探索运行不存在：{run_id}")
        if run.status == "running" and run.task_id:
            task = manager.get(run.task_id)
            if task is None or task.status == "failed":
                code = "TASK_LOST" if task is None else "TASK_FAILED"
                er.finish_failed(run_id, error={"code": code, "message": f"任务{code}"})
                run = er.get_run(run_id)
        return _explore_run_view(run)
```

- [ ] **Step 3: POST /api/v1/curriculum-runs/{run_id}/apply**

```python
    @fastapi_app.post("/api/v1/curriculum-runs/{run_id}/apply")
    def curriculum_run_apply(run_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        selected = payload.get("selected", [])
        if not isinstance(selected, list) or not selected:
            raise api_error(400, "INVALID_PARAMS", "selected 必须是非空数组")
        er = _er(app)
        run = er.get_run(run_id)
        if run is None:
            raise api_error(404, "RUN_NOT_FOUND", f"探索运行不存在：{run_id}")
        if run.status != "ready":
            raise api_error(409, "RUN_STATE_CONFLICT", f"当前状态 {run.status} 不允许应用")
        changes = run.proposals or []
        change_ids = {c["change_id"] for c in changes}
        invalid = [sid for sid in selected if sid not in change_ids]
        if invalid:
            raise api_error(400, "INVALID_PARAMS", f"未知 change_id：{invalid}")
        kr = app._knowledge_repository
        if kr is None:
            raise api_error(409, "DB_UNAVAILABLE", "知识库未配置")
        applied = []
        conflicts = []
        for change in changes:
            if change["change_id"] not in selected:
                continue
            action = change["action"]
            target_id = change["target_id"]
            payload_data = change.get("payload", {})
            try:
                with kr._session_factory() as session:
                    from qed_tracker.db.models import QedCourse, QedDomain
                    if action == "create_domain":
                        existing = session.get(QedDomain, target_id)
                        if existing is not None:
                            conflicts.append({"change_id": change["change_id"], "reason": f"领域已存在：{target_id}"})
                            continue
                        row = QedDomain(
                            domain_id=target_id,
                            name=payload_data.get("name", ""),
                            description=payload_data.get("description", ""),
                            stages=payload_data.get("stages", []),
                        )
                        from qed_tracker.db.knowledge_repository import _touch
                        _touch(row, created=True)
                        session.add(row)
                        session.commit()
                    elif action == "create_course":
                        existing = session.get(QedCourse, target_id)
                        if existing is not None:
                            conflicts.append({"change_id": change["change_id"], "reason": f"课程 id 已存在：{target_id}"})
                            continue
                        domain_id = changes[0]["target_id"]
                        row = QedCourse(
                            course_id=target_id,
                            domain_id=domain_id,
                            name=payload_data.get("name", ""),
                            stage=payload_data.get("stage", ""),
                            sort_order=payload_data.get("sort_order", 1),
                            prerequisites=payload_data.get("prerequisites", []),
                            aliases=payload_data.get("aliases", []),
                            note=payload_data.get("note", ""),
                        )
                        from qed_tracker.db.knowledge_repository import _touch
                        _touch(row, created=True)
                        session.add(row)
                        session.commit()
                    applied.append({"change_id": change["change_id"], "entity": change["entity"], "target_id": target_id})
            except Exception as exc:
                conflicts.append({"change_id": change["change_id"], "reason": str(exc)})
        status_target = "applied" if not conflicts else "partially_applied"
        if status_target == "applied":
            er.apply_run(run_id, applied_ids=[a["change_id"] for a in applied], conflicts=None)
        else:
            er.apply_run(run_id, applied_ids=[a["change_id"] for a in applied], conflicts=conflicts)
        run = er.get_run(run_id)
        return {"applied": applied, "conflicts": conflicts, "run": _explore_run_view(run)}
```

- [ ] **Step 4: 确认现有测试不回归**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_api.py -q`
Expected: 全部通过

---

## Task 5: 提交 + 全量测试

- [ ] **Step 1: 运行全量测试**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests -q`
Expected: 全部通过（266+ passed）

- [ ] **Step 2: ruff 检查**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m ruff check src tests`
Expected: clean

- [ ] **Step 3: 提交**

```bash
git add src/qed_tracker/api/main.py src/qed_tracker/providers/explore_advisor.py
git commit -m "feat(explore): add 8 exploration API endpoints + 2 task handlers"
```

---

## Task 6: 端到端冒烟验证（真实 LLM）

- [ ] **Step 1: 确认 .env 配置**

确认根 `.env` 或 QED-Tracker `.env` 含：
- `API_KEY=<百炼 API_KEY>`
- `QED_DB_PASSWORD=<MySQL 密码>`
- `QED_DATA_ROOT=D:\coding\QED-Engine\dataset`

- [ ] **Step 2: 清空+重建数据库**

```bash
& "D:\software\anaconda3\envs\QED_env\python.exe" -m qed_tracker.db.migrate
```

- [ ] **Step 3: 启动服务**

```bash
& "D:\software\anaconda3\envs\QED_env\python.exe" -m qed_tracker.cli serve
```

- [ ] **Step 4: 测试课程探索**

```bash
curl -X POST http://127.0.0.1:8901/api/v1/courses/01_math_analysis/explore -H "Content-Type: application/json" -d '{"mode":"direct"}'
# 返回 202 + run_id + task_id

# 轮询
curl http://127.0.0.1:8901/api/v1/explore-runs/{run_id}
# 等待 status: ready + proposals

# 采纳
curl -X POST http://127.0.0.1:8901/api/v1/explore-runs/{run_id}/adopt -H "Content-Type: application/json" -d '{"selected":["pp_xxx"]}'
```

- [ ] **Step 5: 测试领域探索**

```bash
curl -X POST http://127.0.0.1:8901/api/v1/curriculum-explore -H "Content-Type: application/json" -d '{"domain_name":"高等数学","mode":"direct"}'
# 轮询 + apply
```
