
from qed_tracker.catalog import list_catalogs, load_catalog
from qed_tracker.config import llm_api_key, load_settings
from qed_tracker.matching import match_candidate
from qed_tracker.models import Candidate, DownloadLink, ResourceKind


def test_load_settings_reads_qed_variables_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("QED_MODEL", "qwen-test")
    monkeypatch.setenv("QED_AXIOM_URL", "http://example.test/")
    monkeypatch.setenv("QED_TRACKER_PORT", "8901")
    monkeypatch.setenv("QED_DB_HOST", "db.local")
    monkeypatch.setenv("QED_DB_PORT", "3307")
    monkeypatch.setenv("QED_DB_NAME", "qed")
    monkeypatch.setenv("QED_DB_USER", "reader")
    monkeypatch.setenv("QED_DB_PASSWORD", "secret")
    monkeypatch.chdir(tmp_path)

    settings = load_settings()

    assert settings.llm_model == "qwen-test"
    assert settings.axiom_url == "http://example.test"
    assert settings.port == 8901
    assert settings.db_host == "db.local"
    assert settings.db_port == 3307
    assert settings.db_name == "qed"
    assert settings.db_user == "reader"
    assert settings.db_password == "secret"
    assert settings.db_configured


def test_load_settings_defaults_without_environment(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    settings = load_settings()

    assert settings.data_root == (tmp_path / "dataset" / "qed-tracker").resolve()
    assert settings.axiom_url == "http://127.0.0.1:8902"
    assert settings.port == 8901
    assert settings.db_name == "qed"
    assert settings.db_password == ""
    assert not settings.db_configured
    assert settings.state_dir == (tmp_path / "dataset" / "qed-tracker" / "meta").resolve()


def test_llm_key_reads_qwen_api_key_without_entering_settings(monkeypatch):
    monkeypatch.setenv("QWEN_API_KEY", "qwen-secret")
    assert llm_api_key() == "qwen-secret"
    assert "qwen-secret" not in repr(load_settings())


def test_math_catalog_is_frozen_and_has_unique_targets():
    assert list_catalogs() == ("math-qe",)
    catalog = load_catalog("math-qe")
    assert catalog.status == "frozen"
    assert len(catalog.targets) == 54
    assert len({target.id for target in catalog.targets}) == 54
    assert {target.course_id for target in catalog.targets} == {
        "01_math_analysis", "02_linear_algebra", "03_topology", "04_real_analysis",
        "05_complex_analysis", "06_functional_analysis", "07_ode", "08_pde",
        "09_abstract_algebra", "10_qe_prep", "11_probability",
        "12_stochastic_processes", "13_high_dim_prob",
    }


def test_math_catalog_includes_chenjixiu_volumes():
    """2026-08-07 定稿拆分：01 套三陈纪修《数学分析》按上/下册 + 习题答案三个目标，
    同一 archive 条目（math_analysis_chenjixiu）内以 file_hint 分别选文件（同源去重例外）。
    title 保持条目级「数学分析」不带卷号，否则与 archive 条目标题 strict 匹配失败。"""
    catalog = load_catalog("math-qe")
    targets = {target.id: target for target in catalog.targets}
    v1 = targets["01-chenjixiu-v1"]
    v2 = targets["01-chenjixiu-v2"]
    answers = targets["01-chenjixiu-answers"]
    assert v1.course_id == "01_math_analysis" and v1.kind == "book" and v1.file_hint == "第三版 上"
    assert v2.course_id == "01_math_analysis" and v2.kind == "book" and v2.file_hint == "第三版 下"
    assert answers.kind == ResourceKind.SUPPLEMENT and answers.file_hint == "习题答案"
    assert all(target.title == "数学分析" and target.language == "zh" and "陈纪修" in target.authors for target in (v1, v2, answers))


def test_supplement_kind_is_supported():
    """QED-021：配套资料分类（如与教材同条的习题答案），catalog kind 解析与过滤可用。"""
    assert ResourceKind.SUPPLEMENT.value == "supplement"
    assert ResourceKind("supplement") is ResourceKind.SUPPLEMENT


def test_target_roles_follow_kind_and_allow_multi_role():
    """方案 A（2026-08-12）：catalog target 增加 roles 多值字段——一套书可同时是教材与习题集。
    未显式指定时按 kind 推导（book→[textbook]、exercise→[exercises]、supplement→[solutions]）。"""
    from qed_tracker.models import BookRole

    catalog = load_catalog("math-qe")
    targets = {target.id: target for target in catalog.targets}
    # 谢惠民《习题课讲义》明确双重角色（textbook + exercises）
    assert targets["01-xiehuimin-v1"].roles == (BookRole.TEXTBOOK, BookRole.EXERCISES)
    assert targets["01-xiehuimin-v2"].roles == (BookRole.TEXTBOOK, BookRole.EXERCISES)
    # 普通 book 按 kind 推导
    assert targets["01-rudin-zh"].roles == (BookRole.TEXTBOOK,)
    assert targets["01-demidovich"].roles == (BookRole.EXERCISES,)
    assert targets["01-chenjixiu-answers"].roles == (BookRole.SOLUTIONS,)
    assert BookRole.TEXTBOOK.value == "textbook"


def test_resource_record_roles_roundtrip():
    """方案 A：ResourceRecord.roles 从 catalog target 继承（可选字段，schema v1 向后兼容）。"""
    from qed_tracker.models import ResourceRecord

    record = ResourceRecord(
        resource_id="sha256:abc",
        kind="book",
        title="数学分析",
        authors=["陈纪修"],
        language="zh",
        year="",
        identifiers={},
        source={},
        file={"relative_path": "raw/x.pdf", "sha256": "abc", "size_bytes": 1, "mime_type": "application/pdf", "page_count": 1},
        catalog_ref={"catalog_id": "math-qe", "course_id": "01_math_analysis", "target_id": "01-chenjixiu-v1"},
        roles=["textbook"],
    )
    payload = record.to_dict()
    assert payload["roles"] == ["textbook"]
    restored = ResourceRecord.from_dict(payload)
    assert restored.roles == ["textbook"]
    # 无 roles 时向后兼容（旧 JSON 无该字段）
    del payload["roles"]
    legacy = ResourceRecord.from_dict(payload)
    assert legacy.roles is None


def test_candidate_links_serialize_for_json_api():
    """QED-021：Candidate.links 携带人工下载方案（libgen 等 metadata_only 来源），
    asdict 后必须 JSON 可序列化（FastAPI 响应与 source 落库）。"""
    import json
    from dataclasses import asdict

    from qed_tracker.models import Availability

    candidate = Candidate(
        "libgen_li", "138660986", "微积分学教程 第一卷", ("菲赫金哥尔茨",), "zh",
        availability=Availability.METADATA_ONLY,
        links=(
            DownloadLink("Torrent", "magnet:?xt=urn:btih:abc", "torrent"),
            DownloadLink("IPFS", "https://cloudflare-ipfs.com/ipfs/QmX", "ipfs"),
        ),
    )
    value = asdict(candidate)
    assert value["links"][0] == {"label": "Torrent", "url": "magnet:?xt=urn:btih:abc", "kind": "torrent"}
    json.dumps(value)  # JSON 可序列化


def test_strict_match_requires_title_author_language_and_edition():
    target = next(target for target in load_catalog("math-qe").targets if target.id == "03-munkres")
    exact = Candidate("source", "1", "Topology, Second Edition", ("James Munkres",), "English", edition="2nd")
    missing_language = Candidate("source", "2", "Topology, Second Edition", ("James Munkres",), "", edition="2nd")
    wrong_author = Candidate("source", "3", "Topology, Second Edition", ("Other",), "English", edition="2nd")

    assert match_candidate(exact, target).strict
    assert not match_candidate(missing_language, target).strict
    assert not match_candidate(wrong_author, target).strict


def test_strict_match_accepts_metadata_only_source():
    """QED-021：libgen 等 metadata_only 来源（无直链，人工下载方案）元数据严格匹配
    时同样判定 strict——evaluate 收录候选（带 links），人工 confirm 后按方案下载再登记；
    若 metadata_only 永远不 strict，候选与 links 永远无法展示（只落 pending_manual）。"""
    from qed_tracker.models import Availability

    target = next(target for target in load_catalog("math-qe").targets if target.id == "03-munkres")
    exact = Candidate("libgen_li", "1", "Topology, Second Edition", ("James Munkres",), "English", edition="2nd", availability=Availability.METADATA_ONLY)
    assert match_candidate(exact, target).strict
