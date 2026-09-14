"""测试 downloader 模块的 verify_content 内容校验（REQ-019, QED-066）。"""

from __future__ import annotations

from pypdf import PdfWriter

from qed_tracker.downloader import ContentVerificationResult, verify_content

# ===== verify_content 单元测试 =====


def test_verify_content_matching_title(tmp_path, text_pdf_bytes):
    """首页文本与登记标题一致 → passed=True 且 score ≥ 阈值。"""
    pdf = tmp_path / "match.pdf"
    pdf.write_bytes(text_pdf_bytes("Mathematical Analysis"))
    result = verify_content(pdf, ["Mathematical Analysis"])
    assert result.passed is True
    assert result.score >= 0.5


def test_verify_content_mismatching_title(tmp_path, text_pdf_bytes):
    """首页文本与登记标题不符 → passed=False 且 score < 阈值（软信号）。"""
    pdf = tmp_path / "mismatch.pdf"
    pdf.write_bytes(text_pdf_bytes("Advanced Linear Algebra"))
    result = verify_content(pdf, ["Mathematical Analysis"])
    assert result.passed is False
    assert result.score < 0.5
    assert "不匹配" in result.message


def test_verify_content_no_expected_titles(tmp_path, text_pdf_bytes):
    """无基准标题时跳过检查。"""
    pdf = tmp_path / "no_titles.pdf"
    pdf.write_bytes(text_pdf_bytes("Anything"))
    result = verify_content(pdf, [])
    assert result.passed is True
    assert "无基准标题" in result.message


def test_verify_content_empty_pdf_list(tmp_path):
    """PDF 无页面时跳过检查。"""
    writer = PdfWriter()
    pdf = tmp_path / "empty.pdf"
    with pdf.open("wb") as f:
        writer.write(f)
    result = verify_content(pdf, ["某标题"])
    assert result.passed is True


def test_verify_content_scanned_pdf(tmp_path, pdf_bytes):
    """扫描版 PDF（无文本层，extract_text 返回空）跳过检查。"""
    pdf = tmp_path / "scanned.pdf"
    pdf.write_bytes(pdf_bytes)
    result = verify_content(pdf, ["数学分析"])
    assert result.passed is True
    assert "无文本层" in result.message


def test_verify_content_corrupt_pdf(tmp_path):
    """损坏 PDF 跳过检查（不崩溃）。"""
    pdf = tmp_path / "corrupt.pdf"
    pdf.write_bytes(b"not a pdf at all")
    result = verify_content(pdf, ["数学分析"])
    assert result.passed is True
    assert "提取失败" in result.message


def test_verify_content_threshold(tmp_path, text_pdf_bytes):
    """自定义阈值生效：提高阈值后原本通过的相似度被判为不匹配。"""
    pdf = tmp_path / "thresh.pdf"
    pdf.write_bytes(text_pdf_bytes("Mathematical Analysis"))
    assert verify_content(pdf, ["Mathematical Analysis"], threshold=0.99).passed is True
    assert verify_content(pdf, ["Advanced Linear Algebra"], threshold=0.99).passed is False


def test_verify_content_result_fields():
    """ContentVerificationResult 字段可访问。"""
    r = ContentVerificationResult(passed=True, score=0.95, message="ok")
    assert r.passed is True
    assert r.score == 0.95
    assert r.message == "ok"
