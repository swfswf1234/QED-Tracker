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
            "经典学习路线为 分析、代数、概率统计 三条主线；"
            "另有跨主线分支课程（点集拓扑、数值分析/科学计算、凸优化、图论、组合数学等）可归入相应主线或单列"
        ),
        "naming_convention": (
            "以国内数学系命名为准：数学分析（微积分为其工科普称/别名）、"
            "高等代数（线性代数为其别名）、概率论与数理统计"
        ),
        "anchor_courses": "数学分析、高等代数、概率论与数理统计为三门基石课，必须入选",
        "level_default": "大学数学系本科至硕士阶段",
        "capstone_hint": "硕士顶峰以研究生资格考试（QE）冲刺为目标组织核心课程",
    },
}


def get_prior(domain_name: str) -> dict[str, str]:
    """按域名精确取先验知识（去首尾空白）；未命中返回空 dict。"""
    return dict(DOMAIN_PRIORS.get((domain_name or "").strip(), {}))
