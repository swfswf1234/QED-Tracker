import urllib.parse
from dataclasses import replace

import httpx
import pytest

from qed_tracker.models import Availability
from qed_tracker.providers.books import (
    RETIRED_PROVIDERS,
    GoogleBooksProvider,
    InternetArchiveProvider,
    LibgenLiProvider,
    OpenLibraryProvider,
    create_book_providers,
)


def _replace_client(provider, handler):
    provider.client.close()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_open_library_marks_records_without_archive_id_as_metadata_only():
    payload = {"docs": [{"title": "Book", "author_name": ["Author"], "ia": []}]}
    provider = OpenLibraryProvider()
    _replace_client(provider, lambda request: httpx.Response(200, json=payload, request=request))
    try:
        result = provider.search("Book", 5)[0]
    finally:
        provider.close()
    assert result.availability == Availability.METADATA_ONLY


def test_google_books_exposes_only_real_pdf_download_links():
    payload = {"items": [
        {"id": "a", "volumeInfo": {"title": "Downloadable", "authors": ["A"]}, "accessInfo": {"pdf": {"downloadLink": "https://example.test/a.pdf"}}},
        {"id": "b", "volumeInfo": {"title": "Preview"}, "accessInfo": {"pdf": {}}},
    ]}
    provider = GoogleBooksProvider()
    _replace_client(provider, lambda request: httpx.Response(200, json=payload, request=request))
    try:
        results = provider.search("Book", 5)
    finally:
        provider.close()
    assert results[0].availability == Availability.DOWNLOADABLE
    assert results[1].availability == Availability.METADATA_ONLY


def test_internet_archive_resolves_largest_public_pdf():
    def handler(request):
        if request.url.path.startswith("/advancedsearch"):
            return httpx.Response(200, json={"response": {"docs": [{"identifier": "book-1", "title": "Book"}]}}, request=request)
        return httpx.Response(200, json={"files": [
            {"name": "small.pdf", "size": "10"},
            {"name": "large file.pdf", "size": "20"},
            {"name": "private.pdf", "size": "30", "private": True},
        ]}, request=request)

    provider = InternetArchiveProvider()
    _replace_client(provider, handler)
    try:
        resolved = provider.resolve(provider.search("Book", 5)[0])
    finally:
        provider.close()
    assert resolved.download_url.endswith("large%20file.pdf")
    assert resolved.size_bytes == 20


def test_internet_archive_resolve_prefers_file_keyword():
    """同一条目含教材与配套习题答案多个 PDF 时，file_keywords 优先选文件名含关键词的文件
    （01-chenjixiu-exercises：陈纪修条目内选「习题答案.pdf」而非最大教材 PDF）。"""

    def handler(request):
        if request.url.path.startswith("/advancedsearch"):
            return httpx.Response(200, json={"response": {"docs": [{"identifier": "math_analysis_chenjixiu", "title": "数学分析"}]}}, request=request)
        return httpx.Response(200, json={"files": [
            {"name": "数学分析 陈纪修 第三版 上.pdf", "size": "50000000"},
            {"name": "数学分析(陈纪修.第二版上下册)习题答案.pdf", "size": "8000000"},
            {"name": "数学分析 陈纪修 第三版 下.pdf", "size": "40000000"},
        ]}, request=request)

    provider = InternetArchiveProvider()
    _replace_client(provider, handler)
    try:
        candidate = provider.search("数学分析 陈纪修", 5)[0]
        # evaluate 按 target.file_hint 传递 file_keywords（见 catalog_evaluate.py）
        candidate = replace(candidate, file_keywords=("习题答案",))
        resolved = provider.resolve(candidate)
    finally:
        provider.close()
    # download_url 为 URL 编码形式；解码后应含「习题答案」且 size 为习题答案文件
    assert "习题答案" in urllib.parse.unquote(resolved.download_url)
    assert resolved.download_url.endswith("%E4%B9%A0%E9%A2%98%E7%AD%94%E6%A1%88.pdf")
    assert resolved.size_bytes == 8000000


def test_internet_archive_resolve_volume_hint_picks_volume_file():
    """2026-08-09 回归：archive 条目文件名是「第三版 上/下」单字（无「册」），
    file_hint 已对齐为「第三版 上/下」；「下册」不能子串误命中「第二版上下册」习题答案。"""

    def handler(request):
        if request.url.path.startswith("/advancedsearch"):
            return httpx.Response(200, json={"response": {"docs": [{"identifier": "math_analysis_chenjixiu", "title": "数学分析"}]}}, request=request)
        return httpx.Response(200, json={"files": [
            {"name": "数学分析 陈纪修 第三版 上 (陈纪修，於崇华，金路) (Z-Library).pdf", "size": "50000000", "md5": "a" * 32},
            {"name": "数学分析 陈纪修 第三版 下 (陈纪修，於崇华，金路) (Z-Library).pdf", "size": "40000000", "md5": "b" * 32},
            {"name": "数学分析(陈纪修.第二版上下册)习题答案.pdf", "size": "8000000", "md5": "c" * 32},
        ]}, request=request)

    provider = InternetArchiveProvider()
    _replace_client(provider, handler)
    try:
        candidate = provider.search("数学分析 陈纪修", 5)[0]
        upper = provider.resolve(replace(candidate, file_keywords=("第三版 上",)))
        lower = provider.resolve(replace(candidate, file_keywords=("第三版 下",)))
    finally:
        provider.close()
    assert upper.size_bytes == 50000000
    assert lower.size_bytes == 40000000
    assert "上" in urllib.parse.unquote(upper.download_url)
    assert "下" in urllib.parse.unquote(lower.download_url)
    assert "习题答案" not in urllib.parse.unquote(lower.download_url)


def test_internet_archive_resolve_records_declared_md5():
    """2026-08-09：resolve 记录 archive 声明的 md5，供下载后内容完整性校验。"""

    def handler(request):
        if request.url.path.startswith("/advancedsearch"):
            return httpx.Response(200, json={"response": {"docs": [{"identifier": "book-1", "title": "Book"}]}}, request=request)
        return httpx.Response(200, json={"files": [
            {"name": "book.pdf", "size": "10", "md5": "0123456789abcdef0123456789abcdef"},
        ]}, request=request)

    provider = InternetArchiveProvider()
    _replace_client(provider, handler)
    try:
        resolved = provider.resolve(provider.search("Book", 5)[0])
    finally:
        provider.close()
    assert resolved.identifiers.get("md5") == "0123456789abcdef0123456789abcdef"


def test_internet_archive_multiword_query_searches_all_fields():
    """archive.org Solr 的 `title:(a b c)` 对多词查询返回 0；必须全字段 AND 连接。"""

    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"response": {"docs": []}}, request=request)

    provider = InternetArchiveProvider()
    _replace_client(provider, handler)
    try:
        provider.search("Munkres Topology 2nd", 8)
    finally:
        provider.close()
    q = httpx.URL(captured["url"]).params["q"]
    assert "mediatype:texts" in q
    assert not q.startswith("title:("), f"多词查询不得用 title:(...) 限定：{q}"
    assert "Munkres" in q and "Topology" in q


def test_internet_archive_chinese_query_uses_phrase_query():
    """中文（CJK）query 必须用 title 精确短语 + AND 组合查询（QED-018 实测：
    全字段 OR 拆词对中文只返回 ChinaXiv 预印本噪音，`title:"数学分析" AND 陈纪修`
    才能命中真实中文教材如 math_analysis_chenjixiu）。"""

    captured = []

    def handler(request):
        captured.append(httpx.URL(str(request.url)).params["q"])
        return httpx.Response(200, json={"response": {"docs": []}}, request=request)

    provider = InternetArchiveProvider()
    _replace_client(provider, handler)
    try:
        provider.search("数学分析 陈纪修", 8)
        provider.search("Munkres Topology 2nd", 8)
    finally:
        provider.close()
    zh_q, en_q = captured
    assert zh_q.startswith('title:"数学分析"'), f"中文查询应取首词 title 短语：{zh_q}"
    assert "陈纪修" in zh_q and "mediatype:texts" in zh_q
    assert not en_q.startswith("title:("), f"英文多词查询保持全字段：{en_q}"
    assert "Munkres" in en_q


def test_retired_provider_has_actionable_migration_error():
    with pytest.raises(ValueError, match=r"0\.5.*core.*sources"):
        create_book_providers(("annas_archive",))
    assert "libgen" not in RETIRED_PROVIDERS, "libgen 已恢复为发现专用来源（QED-021）"


# ---- QED-021：libgen_li 发现专用来源（搜索 + 人工下载方案，无直链） ----

# 2026-08-09 真实页面结构：数据行 9 列（表头 12 列，ID/Time add./Mirrors 不在数据行）：
# [0] Series + Title（edition 链接，带含 HTML 的 tooltip 属性）[1] Author(s) [2] Publisher
# [3] Year [4] Language [5] Pages [6] Size [7] Ext(格式) [8] 分页/镜像
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
<tr>
<td><a data-toggle="tooltip" title="Add/Edit : 2019-08-26; ID: 93391565<br>微积分学教程 第二卷" href="edition.php?id=138177646">微积分学教程 第二卷 <i>第8版</i></a></td>
<td>菲赫金哥尔茨, Г. М.</td><td>高等教育出版社</td><td>2006</td><td>Chinese</td>
<td>1220</td><td>30 MB</td><td>pdf</td><td>1 2 3 4</td>
</tr>
</table>
</body></html>
"""

EDITION_PAGE = """
<html><body>
<h1>Edition 138660986</h1>
<table>
<tr><td>MD5</td><td><a href="md5:10037efa2fa109a3b111a37d29191a3d">10037efa2fa109a3b111a37d29191a3d</a></td></tr>
<tr><td>IPFS</td><td><a href="https://cloudflare-ipfs.com/ipfs/QmXk8c9z1z2z3z4z5">QmXk8c9z1z2z3z4z5</a></td></tr>
<tr><td>Torrent</td><td><a href="magnet:?xt=urn:btih:abc123def456">torrent</a></td></tr>
<tr><td>ed2k</td><td><a href="ed2k://|file|fikhtengolts_v1.pdf|32400000|10037efa2fa109a3b111a37d29191a3d|/">ed2k</a></td></tr>
</table>
</body></html>
"""


def _libgen_handler(html_pages: dict[str, str]):
    def handler(request):
        page = html_pages.get(request.url.path, "")
        return httpx.Response(200, text=page, request=request)

    return handler


def test_libgen_li_search_parses_rows_metadata_only():
    provider = LibgenLiProvider()
    _replace_client(provider, _libgen_handler({"/index.php": SEARCH_PAGE}))
    try:
        results = provider.search("微积分学教程 菲赫金哥尔茨 第一卷", 5)
    finally:
        provider.close()
    assert len(results) == 2
    first = results[0]
    assert first.provider == "libgen_li"
    assert first.provider_id == "138177644"
    assert "微积分学教程 第一卷" in first.title
    assert first.language == "Chinese"
    assert first.year == "2006"
    assert first.size_bytes == 27 * 1024 * 1024  # 9 列模板 [6] 大小
    assert first.authors and "菲赫金哥尔茨" in first.authors[0]
    assert first.availability == Availability.METADATA_ONLY
    assert first.download_url == ""  # libgen.li 无 HTTP 直链
    assert "edition.php?id=138177644" in first.page_url


def test_libgen_li_resolve_extracts_download_links():
    """resolve 从 edition 页提取人工下载方案（torrent/IPFS/ed2k），不产生直链。"""
    provider = LibgenLiProvider()
    _replace_client(
        provider,
        _libgen_handler({"/index.php": SEARCH_PAGE, "/edition.php": EDITION_PAGE}),
    )
    try:
        candidate = provider.search("Фикхтенгольц", 5)[0]
        resolved = provider.resolve(candidate)
    finally:
        provider.close()
    assert resolved.download_url == ""
    labels = {link.label: link.url for link in resolved.links}
    assert labels["Torrent"].startswith("magnet:?xt=urn:btih:")
    assert "cloudflare-ipfs.com/ipfs/" in labels["IPFS"]
    assert labels["ed2k"].startswith("ed2k://|file|")
    assert resolved.identifiers.get("md5") == "10037efa2fa109a3b111a37d29191a3d"


def test_libgen_li_is_registered_source():
    providers = create_book_providers(("libgen_li",))
    assert providers[0].name == "libgen_li"
