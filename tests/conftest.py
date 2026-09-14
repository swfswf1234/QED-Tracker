from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


@pytest.fixture
def pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


@pytest.fixture
def text_pdf_bytes():
    """构造含真实文本层的最小 PDF（首页可被 pypdf extract_text 抽取）。

    仅用 pypdf 原生原语（不引入 reportlab 等新依赖）：空白页 + Helvetica 字体资源 +
    BT/Tj 内容流。文本须为 Latin-1 可编码字符（Helvetica 单字节字体）。
    """

    def _make(text: str, *, pages: int = 1) -> bytes:
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        font_ref = writer._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
        })
        escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 24 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(content)
        for _ in range(pages - 1):
            writer.add_blank_page(width=612, height=792)
        stream = BytesIO()
        writer.write(stream)
        return stream.getvalue()

    return _make
