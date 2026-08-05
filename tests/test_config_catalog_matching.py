
from qed_tracker.catalog import list_catalogs, load_catalog
from qed_tracker.config import llm_api_key, load_settings
from qed_tracker.matching import match_candidate
from qed_tracker.models import Candidate


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
    assert len(catalog.targets) == 44
    assert len({target.id for target in catalog.targets}) == 44
    assert {target.course_id for target in catalog.targets} == {
        "01_math_analysis", "02_linear_algebra", "03_topology", "04_real_analysis",
        "05_complex_analysis", "06_functional_analysis", "07_ode", "08_pde",
        "09_abstract_algebra", "10_qe_prep", "11_probability",
        "12_stochastic_processes", "13_high_dim_prob",
    }


def test_strict_match_requires_title_author_language_and_edition():
    target = next(target for target in load_catalog("math-qe").targets if target.id == "03-munkres")
    exact = Candidate("source", "1", "Topology, Second Edition", ("James Munkres",), "English", edition="2nd")
    missing_language = Candidate("source", "2", "Topology, Second Edition", ("James Munkres",), "", edition="2nd")
    wrong_author = Candidate("source", "3", "Topology, Second Edition", ("Other",), "English", edition="2nd")

    assert match_candidate(exact, target).strict
    assert not match_candidate(missing_language, target).strict
    assert not match_candidate(wrong_author, target).strict
