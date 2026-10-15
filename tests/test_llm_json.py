"""`loads_model_json` 三档容错单测（纯函数，不触网）。"""

import pytest

from qed_tracker.llm_json import loads_model_json


def test_plain_json_parses_without_change():
    assert loads_model_json('{"a": 1}') == {"a": 1}


def test_fenced_json_block_is_extracted():
    content = '```json\n{"searches": [{"terms": ["limits"], "category": "math.CA"}]}\n```'
    assert loads_model_json(content) == {"searches": [{"terms": ["limits"], "category": "math.CA"}]}


def test_unclosed_fence_still_parses():
    content = '```json\n{"a": 1, "b": [1, 2]}'
    assert loads_model_json(content) == {"a": 1, "b": [1, 2]}


def test_prose_before_and_after_object_is_sliced():
    content = '好的，检索计划如下：\n{"searches": []}\n以上。'
    assert loads_model_json(content) == {"searches": []}


def test_string_content_with_braces_does_not_break_the_slice():
    content = '```json\n{"reason": "含 } 与 { 的说明", "terms": ["a"]} 尾注\n```'
    assert loads_model_json(content) == {"reason": "含 } 与 { 的说明", "terms": ["a"]}


def test_top_level_array_is_sliced():
    assert loads_model_json('前文 [{"a": 1}] 后文') == [{"a": 1}]


def test_broken_json_raises_value_error():
    with pytest.raises(ValueError):
        loads_model_json("not-json at all")


def test_truncated_object_reports_structural_error_not_success():
    with pytest.raises(ValueError):
        loads_model_json('{"searches": [{"terms": "x"')
