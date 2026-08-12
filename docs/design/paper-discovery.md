# arXiv 论文智能发现设计

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-12
关联代码：`src/qed_tracker/application/papers.py`、`src/qed_tracker/providers/bailian.py`、`src/qed_tracker/selection_store.py`
关联测试：`tests/test_paper_application.py`、`tests/test_bailian_advisor.py`、`tests/test_paper_selection_cli.py`
关联 ADR：—

## 事实边界

arXiv 提供标题、作者、分类、时间和摘要等候选事实。百炼只根据研究目标生成有限检索计划并评估候选，不提供客观质量或引用影响力结论。下载器负责 PDF 校验和落盘，Inventory 继续保存资源事实；模型判断单独进入选择报告。

模型不能直接写 PDF、修改资源记录或选择任意 URL。推荐命令只生成报告，下载必须由用户引用固定选择报告和一基序号显式执行。

## 目标档案

档案 schema v1 包含 `id`、`name`、`description`、`audience`、`goals`、`topics`、`allowed_categories` 和 `exclude`。内置 `math-research` 与 `llm-engineering`，也允许从 JSON 路径加载自定义档案。

调用时至少提供档案或临时目标。临时 `--category` 只扩展本次允许分类，不修改档案。所有档案和分类必须在模型调用前校验。

## 检索与评分

1. 模型返回最多 4 个 `searches`；每项包含最多 4 个普通关键词、一个允许分类和简短理由。
2. arXiv 对关键词使用 OR，对分类使用 AND；每项默认最多返回 10 条。
3. 应用层按 arXiv ID 去重，并排除 Inventory 中已有的论文，最多向模型提交 40 条候选。
4. 模型必须为每条候选返回 `goal_fit`、`foundational_value`、`readability` 三项 0–5 整数、理由和风险。
5. 应用层按 50%/30%/20% 计算 0–100 分；70 分及以上进入推荐列表，排序键为分数降序、发布日期降序、arXiv ID 升序。

候选标题和摘要是不可信输入，提示词必须把它们标记为数据并限制摘要长度。未知 ID、漏评、重复 ID、越界分数、越界分类或非法 JSON 均使本次模型阶段失败；允许一次格式修复调用，仍失败则不得下载。

## 百炼边界

默认使用 DashScope OpenAI-compatible `chat/completions` 和 `qwen-plus`，`temperature=0`。任务最多调用 6 次，单次默认超时 60 秒；密钥直读根 `.env` 的 `QWEN_API_KEY`（`QED_TRACKER_LLM_API_KEY` 与 `DASHSCOPE_API_KEY` 读取路径已退役），不进入 Settings 表示、TOML、日志或报告。

自动测试只能使用假顾问或 `httpx.MockTransport`，不得访问真实模型或 arXiv。

## 选择报告 schema v1

报告写入 `meta/selections/<selection-id>.json`，包含 `selection_id`、`schema_version`、`status`、时间、目标档案快照、临时目标、模型与契约版本、检索计划、候选、评分、推荐序号、调用用量、响应哈希和下载尝试。

报告先以 `ranked` 原子写入。后续显式下载只读取该快照并追加成功或失败尝试，再原子替换；成功项记录 `resource_id`。报告不保存密钥、完整提示词或完整原始模型响应。

## 失败与退出码

- 参数、档案或选择序号错误返回 `2`。
- 无候选或无达到门槛的推荐返回 `3`，仍保存可审计报告。
- 多篇下载部分失败返回 `4`，成功资源保留。
- 模型、arXiv、报告或全部下载运行错误返回 `5`。
