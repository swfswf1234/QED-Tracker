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
    main_names: list[str] = []
    for i, track in enumerate(tracks):
        _require(isinstance(track, dict), "classic_tracks[i] 必须是对象")
        name = _text(track.get("name"), 50, f"classic_tracks[{i}].name")
        _text(track.get("summary"), 200, f"classic_tracks[{i}].summary")
        kind = str(track.get("kind", "")).strip()
        _require(kind in _TRACK_KINDS,
                 f"classic_tracks[{i}].kind 必须是 main（主干方向）或 branch（分支方向）：{kind}")
        _require(name not in track_names, f"classic_tracks 方向名重复：{name}")
        track_names.append(name)
        if kind == "main":
            main_names.append(name)

    stages = _str_list(data.get("stages", []), "stages", nonempty=True)
    _require(len(stages) == len(set(stages)), "stages 存在重复值")
    _require(all(s in _STAGES for s in stages),
             f"stages 值域必须为 {_STAGES} 之一：{stages}")

    if "anchor_courses" in data:
        _str_list(data.get("anchor_courses", []), "anchor_courses")

    courses = data.get("courses", [])
    _require(isinstance(courses, list) and courses, "courses 必须为非空数组")
    slug_set: set[str] = set()
    graph: dict[str, list[str]] = {}
    for i, course in enumerate(courses):
        _require(isinstance(course, dict), "courses[i] 必须是对象")
        slug = _slug(course.get("slug"), f"courses[{i}].slug")
        _require(slug not in slug_set, f"courses slug 重复：{slug}")
        slug_set.add(slug)
        _text(course.get("name"), 100, f"{slug}.name")
        track = _text(course.get("track", ""), 50, f"{slug}.track", nonempty=False)
        _require(track == "" or track in main_names,
                 f"{slug}.track 必须逐字取自 classic_tracks 的 main 方向（{main_names}）：{track}")
        stage = _text(course.get("stage"), 32, f"{slug}.stage")
        _require(stage in stages, f"{slug}.stage 必须是 stages（{stages}）之一：{stage}")
        if "aliases" in course:
            _str_list(course.get("aliases", []), f"{slug}.aliases")
        _text(course.get("summary"), 400, f"{slug}.summary")
        pres_raw = course.get("prerequisites", [])
        _require(isinstance(pres_raw, list) and all(isinstance(p, str) for p in pres_raw),
                 f"{slug}.prerequisites 必须是字符串数组")
        pres: list[str] = []
        for pre in pres_raw:
            _require(pre != slug, f"{slug} 不允许自环前置")
            if pre not in pres:
                pres.append(pre)
        graph[slug] = pres

    # 前置关系引用合法（仅允许本批课程 slug）
    for slug, pres in graph.items():
        for pre in pres:
            _require(pre in slug_set, f"{slug}.prerequisites 引用不在本批课程：{pre}")
    # 无环检测（DFS 三色标记，与 prompt_lab path validate 同构）
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {s: WHITE for s in slug_set}

    def visit(node: str) -> None:
        color[node] = GRAY
        for nxt in graph.get(node, []):
            if color[nxt] == GRAY:
                raise KnowledgeImportError(f"prerequisites 存在循环：{node} → {nxt}")
            if color[nxt] == WHITE:
                visit(nxt)
        color[node] = BLACK

    for s in slug_set:
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


def validate_course(data: Any) -> dict[str, Any]:
    """校验课程标准答案 JSON（docs/knowledge/<domain>/<course_id>.json 同构）。

    tutorials 套直接可转换为 A2（POST /courses/{course_id}/knowledge）的 tutorials 数组；
    meta 等信息校验宽松（知识文件元数据），核心校验针对 tutorials 契约。
    """
    _require(isinstance(data, dict), "课程 JSON 必须是对象")
    _slug(data.get("domain"), "domain")
    course = data.get("course", {})
    _require(isinstance(course, dict), "course 必须是对象")
    _slug(course.get("course_id"), "course.course_id")
    _text(course.get("name"), 100, "course.name")

    tutorials = data.get("tutorials", [])
    _require(isinstance(tutorials, list) and 1 <= len(tutorials) <= 4,
             "tutorials 必须为 1~4 套（宁缺勿滥）")
    set_nos: list[str] = []
    titles: set[str] = set()
    for i, item in enumerate(tutorials):
        _require(isinstance(item, dict), "tutorials[i] 必须是对象")
        set_no = _text(item.get("set_no"), 4, f"tutorials[{i}].set_no")
        _require(set_no not in set_nos, f"tutorials 套号重复：{set_no}")
        set_nos.append(set_no)
        _text(item.get("set_name"), 60, f"tutorials[{i}].set_name")
        textbook = item.get("textbook", {})
        _require(isinstance(textbook, dict), "tutorials[i].textbook 必须是对象")
        title = _text(textbook.get("title"), 200, "textbook.title")
        _require(title not in titles, f"教科书名重复：{title}")
        titles.add(title)
        _str_list(textbook.get("authors", []), "textbook.authors", nonempty=True)
        roles = textbook.get("roles", [])
        _require(isinstance(roles, list) and "textbook" in roles,
                 "textbook.roles 必须为数组且含 textbook")
        _validate_target_path(textbook.get("target_path"), "textbook.target_path")
        exercise = item.get("exercise")
        if exercise is not None:
            _require(isinstance(exercise, dict), "exercise 必须是对象或 null")
            _text(exercise.get("title"), 200, "exercise.title")
            _str_list(exercise.get("authors", []), "exercise.authors", nonempty=True)
            _validate_target_path(exercise.get("target_path"), "exercise.target_path")
        _text(item.get("reason"), 100, "tutorials[i].reason", nonempty=False)
        _text(textbook.get("intro"), 2000, "textbook.intro")
    return data


def _validate_target_path(value: Any, label: str) -> None:
    if value is None or value == "":
        return  # 目标路径可选（未定出版本的书籍可缺省）
    _text(value, 500, label)
    _require(not value.startswith("/") and "\\" not in value and ".." not in value,
             f"{label} 必须是数据根相对路径（不含绝对路径/上级跳转）：{value}")
