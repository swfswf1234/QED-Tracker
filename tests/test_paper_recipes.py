"""QED-068 B 步：论文探索配方层（recipe→年窗/数量策略 + 领域→arXiv 分类映射）。

待裁项 #4 裁决口径：配方只给**策略**（年窗/top/limit），分类由「领域关键词→arXiv 分类」
映射推导，映射不到即报错要求请求显式给 `categories`（端点映射 422）。
"""

from __future__ import annotations

import pytest

from qed_tracker.paper_recipes import (
    RECIPES,
    build_profile,
    categories_for_domain,
    recipe_defaults,
)


def test_recipes_are_frontier_and_core_only() -> None:
    assert RECIPES == frozenset({"frontier", "core"})


def test_recipe_defaults_carry_strategy_within_recommend_limits() -> None:
    """frontier=近年新鲜度优先；core=不限年、少而稳；数值须落在 recommend 的 1..25/1..20 区间。"""
    frontier = recipe_defaults("frontier")
    core = recipe_defaults("core")
    assert frontier["years_limit"] == 3
    assert core["years_limit"] is None
    for item in (frontier, core):
        assert 1 <= item["limit"] <= 25
        assert 1 <= item["top"] <= 20
    assert frontier["top"] >= core["top"]


def test_unknown_recipe_raises() -> None:
    with pytest.raises(ValueError, match="recipe"):
        recipe_defaults("weekly")


def test_math_domain_maps_to_math_categories() -> None:
    categories = categories_for_domain(name="高等数学与偏微分方程", description="极限、级数、多元微积分与 PDE")
    assert categories
    assert any(item.startswith("math.") for item in categories)


def test_ai_domain_maps_to_cs_categories() -> None:
    categories = categories_for_domain(name="大模型与机器学习", description="Transformer 预训练与推理系统")
    assert any(item.startswith("cs.") for item in categories)


def test_unmappable_domain_returns_empty_for_explicit_categories() -> None:
    assert categories_for_domain(name="符号逻辑史", description="") == ()


def test_build_profile_is_complete_and_recipe_scoped() -> None:
    profile = build_profile(
        domain_id="math-advanced",
        name="高等数学",
        description="微积分与级数",
        recipe="frontier",
    )
    assert profile.id == "domain-math-advanced"
    assert profile.name == "高等数学"
    assert profile.allowed_categories
    assert all(part.startswith(("math.", "cs.", "stat.", "physics.")) for part in profile.allowed_categories)
    assert profile.audience and profile.goals and profile.topics


def test_explicit_categories_extend_the_mapping() -> None:
    profile = build_profile(
        domain_id="math-advanced",
        name="高等数学",
        description="微积分与级数",
        recipe="core",
        categories=("stat.TH",),
    )
    assert "stat.TH" in profile.allowed_categories


def test_unmapped_domain_without_categories_is_rejected() -> None:
    with pytest.raises(ValueError, match="categories"):
        build_profile(
            domain_id="weird",
            name="符号逻辑史",
            description="",
            recipe="core",
        )
