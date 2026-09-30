"""prompt 优化模块（QED-043）：领域/课程知识探索工作台。

QED-072 W-8：本包是全部 LLM prompt 的唯一事实源；导入本包即完成注册——
`templates` 为探索族 + 注册表核心，`advisor_templates` 为书级/主链路顾问族。
"""

from qed_tracker.prompt_lab import advisor_templates, templates  # noqa: F401
