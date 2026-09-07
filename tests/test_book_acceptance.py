"""书籍机器验收门（QED-050 阶段 4，无 LLM）定向测试：硬门槛矩阵 + 软信号只记录不拒绝。

fixture 用 pypdf 现场生成 PDF（多页/加密/空白页/文本页），不访问公网。
设计语义（download-pipeline.md 阶段 4）：五项硬门槛任一不满足即拒绝且
拒绝项逐条记录；文本层字符数为软信号，空白页（0 字符）不拒绝。
"""

from __future__ import annotations

import inspect
from pathlib import Path

from pypdf import PdfWriter

from qed_tracker.downloader import accept_pdf


def _write_pdf(path: Path, *, pages: int = 1, encrypt: str | None = None, pad: int = 0) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if pad:
        writer.add_metadata({"/Producer": "Q" * pad})
    if encrypt:
        writer.encrypt(encrypt)
    with path.open("wb") as stream:
        writer.write(stream)
    return path


def _text_pdf(path: Path) -> Path:
    """手写最小带文本 PDF（Helvetica Tj，xref 表精确构造，pypdf strict=False 可解析）。"""
    content = b"BT /F1 24 Tf 72 700 Td (Hello QED tracker) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    path.write_bytes(bytes(out))
    return path


def test_accept_valid_pdf_with_defaults(tmp_path):
    """默认门槛（≥10 页 / ≥200KB）下合格 PDF 通过；空白页软信号 0 不拒绝。"""
    path = _write_pdf(tmp_path / "ok.pdf", pages=12, pad=260_000)
    result = accept_pdf(path)
    assert result.accepted
    assert result.reasons == ()
    assert result.page_count == 12
    assert result.size_bytes >= 204_800
    assert result.text_chars == 0  # 空白页：软信号 0，只记录不拒绝


def test_reject_non_pdf_magic(tmp_path):
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"MZ\x90\x00 not a pdf at all ----------")
    result = accept_pdf(path, min_pages=1, min_size=0)
    assert not result.accepted
    assert len(result.reasons) == 1 and "魔数" in result.reasons[0]
    assert result.page_count == 0 and result.text_chars == -1  # 软信号无法评估


def test_reject_corrupt_structure(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\n<this is not a pdf body>")
    result = accept_pdf(path, min_pages=1, min_size=0)
    assert not result.accepted
    assert any("结构无效" in r for r in result.reasons)


def test_reject_encrypted(tmp_path):
    """加密 PDF 拒绝（is_encrypted 硬门槛；属主加密空密码可解同样不放行）。"""
    path = _write_pdf(tmp_path / "enc.pdf", pages=12, pad=260_000, encrypt="secret")
    result = accept_pdf(path, min_pages=1, min_size=0)
    assert not result.accepted
    assert any("加密" in r for r in result.reasons)


def test_reject_page_count(tmp_path):
    path = _write_pdf(tmp_path / "thin.pdf", pages=3)
    result = accept_pdf(path, min_pages=10, min_size=0)
    assert not result.accepted
    assert any("页数 3" in r for r in result.reasons)


def test_reject_size_and_pages_collected_together(tmp_path):
    """多项硬门槛同时不满足：拒绝项逐条全部记录（供留痕诊断）。"""
    path = _write_pdf(tmp_path / "tiny.pdf", pages=2)
    result = accept_pdf(path, min_pages=10, min_size=10_000_000)
    assert not result.accepted
    assert any("页数 2" in r for r in result.reasons)
    assert any("大小" in r for r in result.reasons)
    assert len(result.reasons) == 2


def test_text_layer_soft_signal_recorded(tmp_path):
    """带文本层 PDF：软信号 >0 记录进结果，判定不受影响。"""
    path = _text_pdf(tmp_path / "text.pdf")
    result = accept_pdf(path, min_pages=1, min_size=0)
    assert result.accepted
    assert result.text_chars > 0
    assert result.page_count == 1


def test_acceptance_defaults_match_design():
    """设计默认值守护：min_pages=10 / min_size=204800（download-pipeline.md 配置表）。"""
    signature = inspect.signature(accept_pdf)
    assert signature.parameters["min_pages"].default == 10
    assert signature.parameters["min_size"].default == 204800
