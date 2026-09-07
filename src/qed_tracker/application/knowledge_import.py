"""手动知识录入校验器（QED-050 knowledge-dual-flow）。

`docs/knowledge/` 标准答案 JSON 的契约守护：领域（manual@v1）与课程
（course-knowledge/manual@v1）两种校验入口。

与 prompt_lab 模板 validate（LLM 输出契约）独立：
- 手动文件契约 = 知识标准答案（稳定、可审阅、可复现）；
- LLM 输出契约 = 探索生成物（模板 validate，走修复重试）；
两者同源演进的字段语义（stage 四档 / classic_tracks kind / entry_requirements
一句话）保持一致，但校验规则各自维护，不互相复用。

错误以 ValueError 抛出（端点层包装为 400 INVALID_PARAMS；CLI 层打印诊断）。
"""

from __future__ import annotations

import re
from typing import Any

_STAGES = ("基础", "主干", "分支", "前沿")
"""课程四档阶段（D7，2026-08-29 用户裁定），顺序即学习阶段顺序。"""

_TRACK_KINDS = ("main", "branch")
"""classic_tracks 方向类别：main=主干方向 / branch=分支方向（D5）。"""

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
"""slug 规则（与 API 层 _SLUG_RE 一致：小写字母/数字/连字符/下划线）。"""


class KnowledgeImportError(ValueError):
    """手动知识录入校验失败（含字段级诊断信息）。"""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise KnowledgeImportError(message)


def _text(value: Any, limit: int, label: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str):
        raise KnowledgeImportError(f"{label} 必须是字符串")
    text_value = value.strip()
    if nonempty and not text_value:
        raise KnowledgeImportError(f"{label} 不能为空")
    if len(text_value) > limit:
        raise KnowledgeImportError(f"{label} 超长（>{limit}）")
    return text_value


def _slug(value: Any, label: str) -> str:
    text_value = _text(value, 63, label)
    _require(_SLUG_RE.match(text_value), f"{label} 必须匹配 {_SLUG_RE.pattern}：{text_value}")
    return text_value


def _str_list(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise KnowledgeImportError(f"{label} 必须是字符串数组")
    if nonempty and not value:
        raise KnowledgeImportError(f"{label} 必须为非空字符串数组")
    return list(value)


def validate_domain(data: Any) -> dict[str, Any]:
    """校验领域标准答案 JSON（docs/knowledge/<domain>.json 同构）。

    返回原数据（校验通过）；不符合任一规则即抛 KnowledgeImportError。
    """
    _require(isinstance(data, dict), "领域 JSON 必须是对象")
    _slug(data.get("domain"), "domain")
    _text(data.get("name"), 100, "name")
    _text(data.get("description"), 1000, "description")
    _text(data.get("level"), 50, "level", nonempty=False)
    _text(data.get("scope"), 500, "scope", nonempty=False)
    _text(data.get("entry_requirements", ""), 200, "entry_requirements", nonempty=False)

    tracks = data.get("classic_tracks", [])
    _require(isinstance(tracks, list) and len(tracks) <= 4,
             "classic_tracks 必须为 0~4 个方向")
    track_names: list[str] = []
    for i, track in enumerate(tracks):
        _require(isinstance(track, dict), "classic_tracks[i] 必须是对象")
        name = _text(track.get("name"), 50, f"classic_tracks[{i}].name")
        _text(track.get("summary"), 200, f"classic_tracks[{i}].summary")
        kind = str(track.get("kind", "")).strip()
        _require(kind in _TRACK_KINDS,
                 f"classic_tracks[{i}].kind 必须是 main（主干方向）或 branch（分支方向）：{kind}")
        _require(name not in track_names, f"classic_tracks 方向名重复：{name}")
        track_names.append(name)

    stages = _str_list(data.get("stages", []), "stages", nonempty=True)
    _require(len(stages) == len(set(stages)), "stages 存在重复值")
    _require(all(s in _STAGES for s in stages),
             f"stages 值域必须为 {_STAGES} 之一：{stages}")

    if "anchor_courses" in data:
        _str_list(data.get("anchor_courses", []), "anchor_courses")

    courses = data.get("courses", [])
    _require(isinstance(courses, list) and courses, "courses 必须为非空数组")
    id_set: set[str] = set()
    graph: dict[str, list[str]] = {}
    for i, course in enumerate(courses):
        _require(isinstance(course, dict), "courses[i] 必须是对象")
        course_id = _slug(course.get("course_id"), f"courses[{i}].course_id")
        _require(course_id not in id_set, f"courses course_id 重复：{course_id}")
        id_set.add(course_id)
        _text(course.get("name"), 100, f"{course_id}.name")
        track = _text(course.get("track", ""), 50, f"{course_id}.track", nonempty=False)
        _require(track == "" or track in track_names,
                 f"{course_id}.track 必须逐字取自 classic_tracks 中已列出的方向（main 或 branch，{track_names}）：{track}")
        stage = _text(course.get("stage"), 32, f"{course_id}.stage")
        _require(stage in stages, f"{course_id}.stage 必须是 stages（{stages}）之一：{stage}")
        if "aliases" in course:
            _str_list(course.get("aliases", []), f"{course_id}.aliases")
        _text(course.get("summary"), 400, f"{course_id}.summary")
        pres_raw = course.get("prerequisites", [])
        _require(isinstance(pres_raw, list) and all(isinstance(p, str) for p in pres_raw),
                 f"{course_id}.prerequisites 必须是字符串数组")
        pres: list[str] = []
        for pre in pres_raw:
            _require(pre != course_id, f"{course_id} 不允许自环前置")
            if pre not in pres:
                pres.append(pre)
        graph[course_id] = pres

    # 前置关系引用合法（仅允许本批课程 course_id）
    for cid, pres in graph.items():
        for pre in pres:
            _require(pre in id_set, f"{cid}.prerequisites 引用不在本批课程：{pre}")
    # 无环检测（DFS 三色标记，与 prompt_lab path validate 同构）
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {s: WHITE for s in id_set}

    def visit(node: str) -> None:
        color[node] = GRAY
        for nxt in graph.get(node, []):
            if color[nxt] == GRAY:
                raise KnowledgeImportError(f"prerequisites 存在循环：{node} → {nxt}")
            if color[nxt] == WHITE:
                visit(nxt)
        color[node] = BLACK

    for s in id_set:
        if color[s] == WHITE:
            visit(s)

    if "extensions_planned" in data:
        extensions = data.get("extensions_planned", [])
        _require(isinstance(extensions, list), "extensions_planned 必须是数组")
        for i, ext in enumerate(extensions):
            _require(isinstance(ext, dict), "extensions_planned[i] 必须是对象")
            _text(ext.get("name"), 100, f"extensions_planned[{i}].name")
            if ext.get("track"):
                _text(ext.get("track"), 50, f"extensions_planned[{i}].track", nonempty=False)
            for key in ("direction", "reason"):
                if ext.get(key):
                    _text(ext.get(key), 500, f"extensions_planned[{i}].{key}", nonempty=False)
            if "prerequisites_hint" in ext:
                _str_list(ext.get("prerequisites_hint"), f"extensions_planned[{i}].prerequisites_hint")

    return data  # 校验通过原样返回（端点/CLI 直接落库）


_POSITIONS_5 = ("beginner", "intermediate", "advanced", "comprehensive", "elective")
_ALLOWED_AUTHOR_ROLES = ("author", "translator")
_ALLOWED_PARTS = ("", "上册", "下册", "Vol.1", "Vol.2", "Vol.3")
_ALLOWED_LANGUAGES = ("zh", "en")
_ROLES_VALUES = ("textbook", "exercises", "solutions")


_KNOWLEDGE_ID_RE = re.compile(r"^kt-[0-9a-z]+-[0-9a-z]{1,4}$")
"""数据文件版显式 knowledge_id 格式：kt-{abbr}-{set_no}（与仓储层规则一致）。"""

_BOOK_ID_RE = re.compile(r"^[0-9a-z]+-b\d{2,}$")
"""数据文件版显式 book_id 格式：{abbr}-b{NN}（NN 两位起）。"""


def _validate_ref_entry(ref: Any, label: str) -> None:
    """校验单个 ref 条目（textbook_ref/exercise_ref/parallel_ref 元素）。"""
    _require(isinstance(ref, dict), f"{label} 必须是对象")
    _text(ref.get("title"), 256, f"{label}.title")
    part = _text(ref.get("part", ""), 8, f"{label}.part", nonempty=False)
    _require(part in _ALLOWED_PARTS, f"{label}.part 值域错误：{part}")
    authors = ref.get("authors", [])
    _require(isinstance(authors, list) and authors, f"{label}.authors 必须是非空数组")
    for k, a in enumerate(authors):
        _require(isinstance(a, dict), f"{label}.authors[{k}] 必须是对象")
        _text(a.get("name"), 100, f"{label}.authors[{k}].name")
        role = str(a.get("role", "")).strip()
        _require(role in _ALLOWED_AUTHOR_ROLES, f"{label}.authors[{k}].role 值域错误：{role}")
    _text(ref.get("publisher", ""), 128, f"{label}.publisher", nonempty=False)
    _text(ref.get("edition", ""), 64, f"{label}.edition", nonempty=False)
    year = ref.get("year")
    if year is not None:
        _require(isinstance(year, int), f"{label}.year 必须是整数或 null")
    language = str(ref.get("language", "")).strip()
    _require(language in _ALLOWED_LANGUAGES, f"{label}.language 值域错误：{language}")
    roles = ref.get("roles", [])
    _require(isinstance(roles, list) and roles, f"{label}.roles 必须是非空数组")
    for r in roles:
        _require(r in _ROLES_VALUES, f"{label}.roles 值域错误：{r}")
    original_title = ref.get("original_title")
    if original_title is not None:
        _text(original_title, 256, f"{label}.original_title", nonempty=False)
    book_id = ref.get("book_id")
    if book_id is not None:
        _require(isinstance(book_id, str) and _BOOK_ID_RE.match(book_id),
                 f"{label}.book_id 格式错误（应为 {{abbr}}-b{{NN}}）：{book_id}")


def validate_course(data: Any) -> dict[str, Any]:
    """校验课程标准答案 JSON（docs/knowledge/<domain>/<course_id>.json 同构）。

    数据文件版契约（2026-09-03 用户裁决）：顶层为 domain_id/course_id/course_name，
    每套教程显式携带生成好的 knowledge_id（kt-{abbr}-{set_no}）与
    textbook_ref[].book_id（{abbr}-b{NN}）；每套含 set_no/name/position/intro/
    textbook_ref[]/exercise_ref[]/parallel_ref[]。
    """
    _require(isinstance(data, dict), "课程 JSON 必须是对象")
    _slug(data.get("domain_id"), "domain_id")
    _slug(data.get("course_id"), "course_id")
    _text(data.get("course_name"), 100, "course_name")

    tutorials = data.get("tutorials", [])
    _require(isinstance(tutorials, list) and 1 <= len(tutorials) <= 6,
             "tutorials 必须为 1~6 套")
    set_nos: list[str] = []
    knowledge_ids: list[str] = []
    for i, item in enumerate(tutorials):
        _require(isinstance(item, dict), f"tutorials[{i}] 必须是对象")
        set_no = _text(item.get("set_no"), 4, f"tutorials[{i}].set_no")
        _require(set_no not in set_nos, f"tutorials 套号重复：{set_no}")
        set_nos.append(set_no)
        knowledge_id = item.get("knowledge_id")
        if knowledge_id is not None:
            _require(isinstance(knowledge_id, str) and _KNOWLEDGE_ID_RE.match(knowledge_id)
                     and knowledge_id.endswith(f"-{set_no}"),
                     f"tutorials[{i}].knowledge_id 格式错误（应为 kt-{{abbr}}-{set_no}）：{knowledge_id}")
            _require(knowledge_id not in knowledge_ids,
                     f"tutorials knowledge_id 重复：{knowledge_id}")
            knowledge_ids.append(knowledge_id)
        kind = str(item.get("kind", "tutorial")).strip() or "tutorial"
        _require(kind in ("tutorial", "other_material"),
                 f"tutorials[{i}].kind 值域错误：{kind}")
        _text(item.get("name"), 128, f"tutorials[{i}].name")
        position = _text(item.get("position", ""), 24, f"tutorials[{i}].position")
        _require(position in _POSITIONS_5,
                 f"tutorials[{i}].position 值域错误：{position}")
        intro = _text(item.get("intro"), 2000, f"tutorials[{i}].intro")
        _require(len(intro) >= 120, f"tutorials[{i}].intro 至少 120 字")

        # textbook_ref: 非空数组
        textbook_ref = item.get("textbook_ref", [])
        _require(isinstance(textbook_ref, list) and textbook_ref,
                 f"tutorials[{i}].textbook_ref 必须是非空数组")
        for j, ref in enumerate(textbook_ref):
            _validate_ref_entry(ref, f"tutorials[{i}].textbook_ref[{j}]")

        # exercise_ref: null 或数组
        exercise_ref = item.get("exercise_ref")
        if exercise_ref is not None:
            _require(isinstance(exercise_ref, list), f"tutorials[{i}].exercise_ref 必须是 null 或数组")
            for j, ref in enumerate(exercise_ref):
                _validate_ref_entry(ref, f"tutorials[{i}].exercise_ref[{j}]")

        # parallel_ref: null 或数组
        parallel_ref = item.get("parallel_ref")
        if parallel_ref is not None:
            _require(isinstance(parallel_ref, list), f"tutorials[{i}].parallel_ref 必须是 null 或数组")
            for j, ref in enumerate(parallel_ref):
                _validate_ref_entry(ref, f"tutorials[{i}].parallel_ref[{j}]")
    return data
