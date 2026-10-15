"""模型回复 JSON 容错解析（围栏抽取 + 最外层切片）。

真机取证驱动（2026-10-07）：`paper-plan/plan@v2` 返回**内容完全合规但被 ```json 围栏包裹**的
正文时，裸 `json.loads` 在 char 0 即失败 → 盲发一次 repair 长调用（实测 71.6s 后仍空正文）→
落回确定性检索计划（中文单 term，arXiv 必零候选）。本模块只做形态容错，不改任何契约校验：
解析不出可用 JSON 仍抛 `ValueError`，交调用方按原口径 repair/报错。

三档顺序与根仓库 `services/llm/local_adapt.parse_json_reply` 同形（直解→围栏→最外层切片）。
"""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"^\s*```[ \t]*(?:[A-Za-z0-9_+-]+)?[ \t]*\r?\n(?P<body>.*?)(?:\r?\n?[ \t]*```)?\s*$", re.DOTALL)


def loads_model_json(content: str) -> object:
    """模型正文 → Python 对象：① 直接解析 →② 剥 ``` 围栏 →③ 取最外层 `{}`/`[]` 切片。

    三档全失败抛 `ValueError`（形态与 `json.loads` 一致，供调用方 except 分支直接承接）。
    """
    try:
        return json.loads(content)
    except ValueError:
        pass
    fenced = _extract_fence_body(content)
    for candidate in (fenced, content):
        for snippet in _candidate_slices(candidate):
            try:
                return json.loads(snippet)
            except ValueError:
                continue
    raise ValueError(f"模型响应不是可用 JSON（{content[:120]!r}）")


def _extract_fence_body(text: str) -> str:
    match = _FENCE.match(text)
    return match.group("body") if match else text


def _candidate_slices(text: str) -> list[str]:
    """按**起手位置**从前到后给出外层切片候选（`{` 与 `[` 都探，最外层容器先试）。"""
    found: list[tuple[int, str]] = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start < 0:
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    found.append((start, text[start : index + 1]))
                    break
        else:
            # 未闭合（模型截断/围栏残缺）：剥到文末交给 json.loads 报出真实结构错
            found.append((start, text[start:]))
    return [snippet for _, snippet in sorted(found)]
