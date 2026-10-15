"""论文探索配方层（QED-068 B 步）。

配方只承载**策略**（年窗 / 推荐数量 / 每组抓取量）；`allowed_categories` 由「领域关键词 →
arXiv 分类」映射推导，映射不到即报错，要求请求显式给出 `categories`（端点映射 422）。
分类取值须匹配 `profiles.CATEGORY_PATTERN`，种子口径对齐打包档案
`paper_profiles/{math-research,llm-engineering}.json`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qed_tracker.models import PaperProfile
from qed_tracker.profiles import CATEGORY_PATTERN

RECIPES: frozenset[str] = frozenset({"frontier", "core"})
"""前沿（近年新鲜度优先）与核心（不限年、少而稳）两配方；值域封闭，非法即 422。"""


@dataclass(frozen=True, slots=True)
class RecipePolicy:
    name: str
    years_limit: int | None
    top: int
    limit: int


_POLICIES: dict[str, RecipePolicy] = {
    "frontier": RecipePolicy("frontier", 3, 10, 15),
    "core": RecipePolicy("core", None, 8, 20),
}

_KEYWORD_CATEGORIES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("数学", "微积分", "分析", "代数", "几何", "拓扑", "方程", "级数", "概率", "随机",
         "优化", "数值", "组合", "数论", "math", "algebra", "geometry", "analysis",
         "topology", "probability", "differential", "series", "optimization"),
        ("math.FA", "math.AP", "math.PR", "math.CA", "math.MG", "math.OC", "math.NA",
         "math.CO", "stat.TH"),
    ),
    (
        ("人工智能", "机器学习", "深度学习", "大模型", "语言模型", "神经", "计算机", "算法",
         "系统", "视觉", "自然语言", "推理", "neural", "machine learning", "deep learning",
         "artificial intelligence", "computer", "algorithm", "vision", "language"),
        ("cs.CL", "cs.LG", "cs.AI", "cs.IR", "cs.CV", "cs.DC", "cs.NE", "cs.SY"),
    ),
    (
        ("物理", "力学", "量子", "相对论", "统计物理", "场论", "physics", "quantum",
         "mechanics", "relativity", "field theory"),
        ("physics.class-ph", "physics.gen-ph", "math.QA"),
    ),
    (
        ("经济", "金融", "博弈", "计量", "市场", "economics", "finance", "game theory"),
        ("econ.GN", "q-fin.PM", "math.DS"),
    ),
)


def recipe_policy(recipe: str) -> RecipePolicy:
    key = (recipe or "").strip()
    if key not in _POLICIES:
        raise ValueError(f"未知论文探索 recipe：{recipe}（可用 {sorted(RECIPES)}）")
    return _POLICIES[key]


def recipe_defaults(recipe: str) -> dict[str, Any]:
    """推荐调用面消费的参数字典（年窗/top/limit）。"""
    policy = recipe_policy(recipe)
    return {"years_limit": policy.years_limit, "top": policy.top, "limit": policy.limit}


def categories_for_domain(*, name: str = "", description: str = "") -> tuple[str, ...]:
    """领域名 + 描述命中关键词 → arXiv 分类；无命中返回空表（由调用方要求显式 categories）。"""
    haystack = f"{name} {description}".lower()
    matched: list[str] = []
    for keywords, categories in _KEYWORD_CATEGORIES:
        if any(keyword.lower() in haystack for keyword in keywords):
            for category in categories:
                if category not in matched:
                    matched.append(category)
    return tuple(matched)


def build_profile(
    *,
    domain_id: str,
    name: str,
    description: str = "",
    recipe: str,
    categories: tuple[str, ...] | list[str] = (),
) -> PaperProfile:
    """领域行 + 配方 → 一次性 PaperProfile（不落 paper_profiles/ 打包档案）。

    显式 `categories` 与映射结果并集（映射在前），保证发起方可以扩大而不能缩小口径；
    两者皆空即报错——论文探索必须有真实分类白名单，不允许无白名单全库扫描。
    """
    policy = recipe_policy(recipe)
    bucket = (domain_id or "").strip()
    if not bucket:
        raise ValueError("论文探索需要显式领域（domain_id 必填）")
    title = (name or "").strip() or bucket
    explicit = tuple(dict.fromkeys(str(item).strip() for item in categories if str(item).strip()))
    invalid = [item for item in explicit if not CATEGORY_PATTERN.fullmatch(item)]
    if invalid:
        raise ValueError(f"非法 arXiv 分类：{', '.join(invalid)}")
    allowed = tuple(dict.fromkeys((*categories_for_domain(name=title, description=description), *explicit)))
    if not allowed:
        raise ValueError(f"无法为领域「{title}」推导 arXiv 分类，请显式指定 categories")
    haystack = f"{title} {description}".lower()
    keywords = tuple(dict.fromkeys(
        keyword
        for group, _categories in _KEYWORD_CATEGORIES
        for keyword in group
        if keyword.lower() in haystack
    )) or (title,)
    return PaperProfile(
        id=f"domain-{bucket}",
        name=title,
        description=(description or "").strip() or title,
        audience="领域学习者与研究者优先",
        goals=(f"梳理「{title}」的{('前沿' if policy.years_limit else '核心')}文献脉络",),
        topics=keywords,
        allowed_categories=allowed,
        years_limit=policy.years_limit,
    )
