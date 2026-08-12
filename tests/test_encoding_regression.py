"""QED-026 Task 8 回归：来源响应强制 UTF-8 解码，任务/资源 JSON 不得出现乱码。

乱码机制（2026-08-09 实测数据）：httpx Response.text/json() 按 Content-Type
声明的 charset 解码（errors="replace"）；若远端误声明 GBK 而内容为 UTF-8 字节，
中文标题即变成 U+FFFD 乱码字符串，随后随候选标题/任务 JSON 落盘。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from qed_tracker.main_line.store import EntryStore
from qed_tracker.providers.books import InternetArchiveProvider, LibgenLiProvider, _decode_text

# 2026-08-09 真实 libgen.li 页面结构（与 tests/test_book_providers.py 同步）
SEARCH_PAGE = """
<html><body>
<table id="tablelibgen">
<tr><th>ID</th><th>Time add.</th><th>Title</th><th>Series</th><th>Author(s)</th>
<th>Publisher</th><th>Year</th><th>Language</th><th>Pages</th><th>Size</th><th>Ext.</th><th>Mirrors</th></tr>
<tr>
<td><b>俄罗斯数学教材选编系列</b><br><a data-toggle="tooltip" title="Add/Edit : 2019-08-26; ID: 93391564<br>微积分学教程 第一卷（高等教育出版社，2006年）" href="edition.php?id=138177644">微积分学教程 第一卷 <i>第8版</i></a></td>
<td>菲赫金哥尔茨, Г. М.</td><td>高等教育出版社</td><td>2006</td><td>Chinese</td>
<td>1780 / 1780</td><td>27 MB</td><td>pdf</td><td>1 2 3 4</td>
</tr>
</table>
</body></html>
"""


def _with_charset(content: bytes, charset: str) -> httpx.Response:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=content,
            headers={"Content-Type": f"text/html; charset={charset}"},
            request=request,
        )

    return handler


def test_entry_store_writes_utf8(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create({
        "entry_id": "cn-test", "course_id": "01_math_analysis", "title": "数学分析原理",
        "authors": ["Rudin"], "version": {"detail": "中译本"},
    })
    raw = (tmp_path / "meta" / "main-line" / "01_math_analysis" / "cn-test.json").read_bytes()
    raw.decode("utf-8")  # 必须能被 UTF-8 解码
    value = json.loads(raw.decode("utf-8"))
    assert value["title"] == "数学分析原理"
    assert value["authors"] == ["Rudin"]
    assert "中译本" in value["version"]["detail"]


def test_decode_text_roundtrip() -> None:
    """来源响应中文必须显式 UTF-8 解码（回归：GBK 误解码产生乱码）。"""
    assert _decode_text("数学分析".encode("utf-8")) == "数学分析"  # noqa: UP012 - 回归测试显式声明编码
    assert "微积分学教程" in _decode_text("微积分学教程 第一卷 第8版".encode("utf-8"))  # noqa: UP012


def test_libgen_li_search_ignores_misdeclared_charset() -> None:
    """远端声明 charset=gbk 但内容为 UTF-8 时，候选标题不得乱码（回归 Task 8）。"""
    provider = LibgenLiProvider()
    provider.client = httpx.Client(
        transport=httpx.MockTransport(_with_charset(SEARCH_PAGE.encode("utf-8"), "gbk")),
        follow_redirects=True,
    )
    try:
        results = provider.search("微积分学教程 菲赫金哥尔茨 第一卷", 5)
    finally:
        provider.close()
    assert "微积分学教程 第一卷" in results[0].title
    assert "菲赫金哥尔茨" in results[0].authors[0]
    assert "\ufffd" not in results[0].title


def test_archive_search_ignores_misdeclared_charset() -> None:
    """archive.org 声明 charset=gbk 但内容为 UTF-8 JSON 时，标题不得乱码（回归 Task 8）。"""
    payload = '{"response": {"docs": [{"identifier": "math_analysis_chenjixiu", "title": "数学分析陈纪修", "creator": ["陈纪修"]}]}}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload.encode("utf-8"),
            headers={"Content-Type": "application/json; charset=gbk"},
            request=request,
        )

    provider = InternetArchiveProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    try:
        result = provider.search("数学分析 陈纪修", 5)[0]
    finally:
        provider.close()
    assert result.title == "数学分析陈纪修"
    assert result.authors == ("陈纪修",)
    assert "\ufffd" not in result.title
