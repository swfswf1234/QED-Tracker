
from qed_tracker.catalog import list_catalogs, load_catalog
from qed_tracker.config import llm_api_key, load_settings
from qed_tracker.matching import match_candidate
from qed_tracker.models import Candidate


def test_load_settings_uses_toml_and_environment(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text('[core]\ndata_root = "library"\nretries = 5\nsources = ["internet_archive"]\n\n[axiom]\nurl = "http://example.test/"\n\n[llm]\nmodel = "qwen-test"\ncall_budget = 4\n', encoding="utf-8")
    monkeypatch.setenv("QED_TRACKER_TIMEOUT_SECONDS", "45")
    monkeypatch.chdir(tmp_path)

    settings = load_settings(config)

    assert settings.data_root == (tmp_path / "library").resolve()
    assert settings.retries == 5
    assert settings.timeout_seconds == 45
    assert settings.sources == ("internet_archive",)
    assert settings.axiom_url == "http://example.test"
    assert settings.llm_model == "qwen-test"
    assert settings.llm_call_budget == 4


def test_llm_key_uses_dedicated_environment_without_entering_settings(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fallback")
    assert llm_api_key() == "fallback"
    monkeypatch.setenv("QED_TRACKER_LLM_API_KEY", "preferred")
    assert llm_api_key() == "preferred"
    assert "preferred" not in repr(load_settings())


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
