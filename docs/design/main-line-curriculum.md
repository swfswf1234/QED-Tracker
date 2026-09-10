# 主链路设计：课程体系、教材条目、渠道记录与 CLI 流程

设计状态：Accepted
实现状态：Implemented
确认状态：已确认
最后更新：2026-09-09
关联代码：`src/qed_tracker/courses.py`、`src/qed_tracker/main_line/`（advisor.py）、`src/qed_tracker/cli.py`（courses/mainline/books 命令组）、`src/qed_tracker/application/book_fetch.py`（取书承接）、`src/qed_tracker/providers/books.py`（UTF-8 解码修复）、`docs/knowledge/`（标准答案 JSON，ADR 0006 起经确认流程导入 qed_course；历史种子 `migrations/data/math.json` 已随迁移链删除）
关联测试：`tests/test_courses.py`、`tests/test_main_line_advisor.py`、`tests/test_main_line_cli.py`、`tests/test_encoding_regression.py`
关联 ADR：—
需求方：QED-Engine（8903 前端知识链路；根仓库 [course-acquisition-flow.md](../../../docs/design/course-acquisition-flow.md) 五阶段对齐）
执行方：QED-Tracker
上承架构：[主链路架构](../architecture/main-line.md)（Accepted，QED-026 已实现，见[已完成任务台账](../trackers/completed.md)）

## 1. 课程体系（历史模型留档，已由知识链承接）

> 课程体系数据模型事实源 = `qed_course`/`qed_domain` 共享表（[数据库共享表设计](../architecture/database-shared-tables.md)）
> 与 `docs/knowledge/` 标准答案目录（[知识录入设计](knowledge-import.md)）。本节原 JSON 样本、
> 字段表与 14 门课程清单为 QED-026 时代历史模型留档（原 `migrations/data/math.json` 种子，
> 已随 ADR 0006 迁移链删除），不再现行；`stages`/`stage` 值域已统一为四档
> **【基础、主干、分支、前沿】**。第一阶段验证范围（00 概率论与数理统计、01 数学分析、
> 02 高等代数三门无前置基础课）由 §4 验证闭环承接。

## 2. 教材条目模型（历史设计留档，由 qt_knowledge/qt_books 承接）

> **历史模型注（QED-031 起被取代，QED-050-D 书库化后失效）**：本节原 JSON 条目模型
> （五要素 + 八态状态机 + approve 移交）已被 `qt_knowledge`（两态教程）+ `qt_books`
> （书库化四选用态 + holding）承接；取书/登记/验收语义见
> [下载管线设计](download-pipeline.md)（五阶段链 + mark_owned 唯一登记，
> raw/ 即共用成品区，无「复制移交」语义）。防总评高校准语义由 §5 存续决策承接
> （实现落点 `src/qed_tracker/main_line/advisor.py`）。

## 3. 渠道记录

- 运行时渠道事实由 `qt_sources` 承载（[数据库专用表设计](../architecture/database-private-tables.md)），
  汇总视图由 `mainline channels` 聚合（见 §4：全量遍历 qt_books 聚合 qt_sources，refs 多归属
  不重复计数）。
- 与[来源探索与评估](../plans/2026-09-source-discovery.md)互补：文档矩阵 = 人工评估结论（连通性/覆盖/质量）；
  `qt_sources` = 实际下载尝试（运行时事实）。两者共同支撑「剔除无效渠道」决策。
- 原「每条目 `channels[]` 自动记录」为旧模型表述，已随 §2 历史条目模型退役。

## 4. CLI 流程

> QED-050-D（2026-09-06）命令面重接后口径：取书走 8901 五阶段编排（CLI 只做提交+轮询），
> `approve`/`reject` 已删除（设计裁决 6：raw/ 即下载与人工导入共用成品区，「复制移交」语义
> 消失；reject 无独立态），`verify` 改只读复核。风格沿用 argparse + `--json` + 稳定退出码
> （0 成功 / 2 请求错误 / 3 任务失败或部分失败或文件缺失 / 4 verify 指纹变化 / 6 服务不可达）。

| 命令 | 说明 |
| --- | --- |
| `qed-tracker courses list` | 列出学科课程体系（当前 math） |
| `qed-tracker courses show <course_id>` | 查看单门课（含前置/关联 target；也接受学科名） |
| `qed-tracker mainline list --course <course_id>` | 列出课程教程与书行（`[{status}/{holding}]` 视图） |
| `qed-tracker mainline new --course <id> --title ... [--set-no N]` | 新建 draft 教程：**先参照顶尖大学课程设置（MIT/清华等指定教材）→ 再按此探索**；LLM 预填评价，需唯一密钥 API_KEY（见[服务管理中心设计](service-management.md)）；重复标题预检拦截 |
| `qed-tracker mainline review <knowledge_id>` | 人工定稿（draft → confirmed，无编辑选项：refs/简介在采纳时落行） |
| `qed-tracker mainline download <knowledge_id> [--include-parallel] [--timeout S]` | 教程级取书（裁决 9 双入口教程级）：经 8901 `POST /knowledge/{id}/fetch` 提交后台任务并轮询；refs 聚合书集、排除已 owned、默认 decided（`--include-parallel` 纳入 parallel_ref）、顺序逐书、部分失败汇总 |
| `qed-tracker books fetch <book_id> [--timeout S]` | 书级取书（裁决 9 双入口书级）：经 8901 `POST /books/{id}/fetch`；已 owned no-op |
| `qed-tracker books import <book_id> <path>` | 人工导入：经 8901 `POST /books/{id}/import`（完整性校验 + D9 命名 + mark_owned 登记） |
| `qed-tracker mainline verify <knowledge_id> [--book <book_id>]` | **只读复核**（设计裁决 6）：inspect_pdf 重算比对（ok/missing/invalid/changed 四态；文件名带 `_sha8` 指纹时 sha256 前缀失配 → changed，exit 4），不做任何状态迁移 |
| `qed-tracker mainline channels` | 渠道有效性汇总：全量遍历 qt_books 聚合 qt_sources（refs 多归属不重复计数） |

`approve`（复制移交根仓库）与 `reject` **已删除**——验收已并入五阶段链的机器验收 + `mark_owned`
登记（QED-050-D 设计裁决 6）；存量迁移命令 `migrate` 同步退役（0018 重建 + knowledge import 为
新链路）。

**第一阶段验证闭环**（00/01/02 三门，QED-050-D 口径）：
1. `knowledge import`（或探索采纳）落教程与 decided 书行
2. `mainline download <knowledge_id>` 经 8901 五阶段取书（检索→确认→下载→staging 验收→登记
   owned；无自动候选时任务 result 附人工指引，`books import` 人工补书）
3. `mainline verify <knowledge_id>` 只读复核（文件仍可解析、指纹未变）
4. `mainline channels` 查看渠道有效性，剔除无效渠道

**mainline new 的探索依据（2026-08-12 用户确认）**：
- 第一步：收集顶尖大学（MIT、清华等）该课程的官方指定教材/课程大纲（LLM 检索辅助）；
- 第二步：以该参照为锚点探索可下载候选（渠道搜索 + 候选比对）；
- 第三步：LLM 预填版本/评价/建议，人工评审定稿。

## 5. 已确认决策（存续部分）

- LLM 权威性等级：**高/中/低**，并强制「防总评高」校准（对比评级 + 证据依据，实现落点
  `src/qed_tracker/main_line/advisor.py`）。
- `mainline new` 生成方式：**先参照顶尖大学（MIT/清华等）课程设置 → 再按此探索**
  （2026-08-12 用户确认；顶尖大学参照由 LLM 检索即时生成，候选来源复用现有 providers）。

### LLM 预填契约（mainline-prefill-v1，2026-09-09 自实现计划迁入存档）

实现事实源 = `src/qed_tracker/main_line/advisor.py`；契约值域如下：

- 模板编号 `mainline-prefill/prefill@v1`，`contract_version = "mainline-prefill-v1"`（随结果透出，
  供审计与重放对齐）。
- 预填输出：`{"evaluation": {"source": "llm", "text", "authority", "set_candidate"},
  "advice": {"download", "reason"}}`（不写条目文件，由调用方落盘）。
- 值域校验：
  - `authority` ∈ `高|中|低`（越界即校验失败）；
  - `advice.download` ∈ `recommended|optional|not_recommended`（三值，越界即校验失败）；
  - `set_candidate` 为 `套X` 或空串（空 = 不建议成套）；`reason` 非空散文。
- 坏 JSON 一次修复：响应 JSON 解析/校验失败时以 repair prompt 重问**一次**，仍失败按失败处理。
- 预算控制：`call_budget`（默认 6）计主调用 + 修复调用，耗尽即预算耗尽退出（预填失败可人工评审兜底）。

## 关联文档

- [主链路架构](../architecture/main-line.md)（Accepted，QED-026 已实现）
- [下载管线设计](download-pipeline.md)（取书/登记语义承接）
- [知识录入设计](knowledge-import.md)（教材条目模型承接）
- [下载管线设计](download-pipeline.md)（下载/登记链路复用）
- [来源探索与评估](../plans/2026-09-source-discovery.md)（渠道矩阵）
- 根仓库 [course-acquisition-flow.md](../../../docs/design/course-acquisition-flow.md)（五阶段对齐）
