# 计划索引

状态：Current
最后更新：2026-08-20

本目录只保存尚未关闭的跨模块实施计划。任务状态以[待办列表](../trackers/todo.md)为准；计划完成后将关闭证据写入 completed，并删除计划正文，详细差异由 Git 保留。过时计划归档至 [历史基线](../history/index.md)（如 2026-08-service-and-book-download 已归档）。

## 活跃计划

- [教程命名规范](2026-08-tutorial-naming.md)（2026-08-20，QED-036，**待人工审核**）：`qt_knowledge` 教程行 name 统一「教程{set_no}：书名（作者）」；textbook_ref 扩展 authors（方案 A）；存量 3 行改名 + mainline new/review 默认命名同步。设计见[教程命名规范设计](../design/tutorial-naming.md)。
- [模型模式与密钥分置](2026-08-model-mode-config.md)（2026-08-20，QED-037，执行中）：自身 `.env` + config 改读 + `llm_client.py` 双模式兼容层 + service `--mode` + qed_llm_calls 调用记录。设计见[模型模式与密钥分置设计](../design/model-mode-config.md)。
- [主链路第一版](2026-08-main-line-curriculum.md)（2026-08-12，QED-026）：课程梳理 → 教材条目（五要素）→ LLM 预填评价 → 人工评审 → 下载 → 验收 → 移交根仓库；CLI 跑通 00/01/02 三门基础课验证。设计见[主链路设计](../design/main-line-curriculum.md)。
- 真实百炼与 arXiv 冒烟（QED-005）属于外部验收阻塞，直接保留在待办列表中。
