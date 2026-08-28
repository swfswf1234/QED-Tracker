"""领域先验知识注册表（QED-043 P13 裁决）：领域专属探索引导的唯一集中处（用户审核入口）。

- 精确域名匹配（去除首尾空白）；未命中返回空 dict，不影响其它领域的学科中立探索；
- 内容允许且仅允许存放领域专属知识（教材偏好/主线提示/命名惯例等）；
  通用模板（templates.py）保持学科中立，由守护测试强制；
- 后续课程侧管线（tree/tutorials）直接复用同一份先验。

修改先验 = 改此文件（git 保留历史），无需版本号。
"""

from __future__ import annotations

DOMAIN_PRIORS: dict[str, dict[str, str]] = {
    "高等数学": {
        "textbook_preference": (
            "美版经典教材内容更详细系统；优先选择已有中文翻译版的美版经典教材；"
            "宁缺勿滥，必须是历经教学检验的经典（如 Rudin、Zorich 级别），不选讲义式或应试类图书"
        ),
        "tracks_hint": (
            "经典学习路线为四条主线：分析学、代数学、概率与统计、几何与拓扑；"
            "课程按知识归属归入相应主线"
        ),
        "naming_convention": (
            "以国内数学系命名为准：数学分析（微积分为其工科普称/别名）、"
            "高等代数（线性代数为其别名）、概率论与数理统计；"
            "「数学」「数学（高等数学）」均为本领域的合法称呼，规范化名为「高等数学」，"
            "带括号的学科限定名（如「数学（高等数学）」）是合法的领域名称"
        ),
        "anchor_courses": "数学分析、高等代数、概率论与数理统计为三门基石课，必须入选",
        "level_default": "大学数学系本科至硕士阶段",
        "capstone_hint": "硕士顶峰以研究生资格考试（QE）冲刺为目标组织核心课程",
    },
}

PRIOR_KEYS_BY_STEP: dict[str, tuple[str, ...]] = {
    # 探索管线各步注入的先验键集（分步裁剪，2026-08-26 用户裁决）：
    # domain 步只喂命名/主线/基石/层级四键；courses 步全量；path 步仅顶峰提示；
    # tutorials（课程教材探索，2026-08-26 单 prompt 重设计）仅教材偏好。
    "domain": ("naming_convention", "tracks_hint", "anchor_courses", "level_default"),
    "courses": (
        "naming_convention", "tracks_hint", "anchor_courses", "level_default",
        "textbook_preference", "capstone_hint",
    ),
    "path": ("capstone_hint",),
    "tutorials": ("textbook_preference",),
}


def get_prior(domain_name: str) -> dict[str, str]:
    """按域名精确取先验知识（去首尾空白）；未命中返回空 dict。"""
    return dict(DOMAIN_PRIORS.get((domain_name or "").strip(), {}))


def get_prior_for_step(domain_name: str, step: str) -> dict[str, str]:
    """按步裁剪先验知识：只返回 PRIOR_KEYS_BY_STEP[step] 中声明的键；未命中领域返回空 dict。"""
    allowed = PRIOR_KEYS_BY_STEP.get(step, ())
    prior = DOMAIN_PRIORS.get((domain_name or "").strip(), {})
    return {key: prior[key] for key in allowed if key in prior}
