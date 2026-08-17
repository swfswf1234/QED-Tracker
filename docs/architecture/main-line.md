# 主链路架构：课程梳理 → 教材寻找 → 下载 → 验收

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-17
关联代码：src/qed_tracker/courses.py、src/qed_tracker/main_line/（advisor.py）、src/qed_tracker/cli.py（courses/mainline 命令组）
关联测试：tests/test_courses.py、tests/test_main_line_advisor.py、tests/test_main_line_cli.py、tests/test_encoding_regression.py
关联 ADR：—
需求方：QED-Engine（8903 前端知识链路消费；根仓库 [course-acquisition-flow.md](../../../docs/design/course-acquisition-flow.md) 五阶段流程对齐）
执行方：QED-Tracker

> 本文件是主链路的架构文档。设计细节（数据模型、端点契约、评审表单）见
> [主链路设计](../design/main-line-curriculum.md)；实现按 [实现计划](../plans/2026-08-main-line-curriculum.md)
> 完成（QED-026，提交链 948fa88~ea905b9，全量 221 passed + 3 skipped）。

## 背景与目标

现有 `catalog/evaluate` 任务是**渠道与功能评估工具**（验证来源可达性、LLM 评分链路），不是
用户的主学习链路。用户主链路是：

1. **领域课程梳理**：确定学科的基础课程体系（先修关系、学习顺序），供 8903 前端知识链路展示；
2. **课程教材寻找**：按课程逐门寻找最佳经典教材（教材 + 习题集），标注版本/评价/下载建议，
   供人工评审；
3. **下载**：从各渠道下载（统一临时区），记录渠道有效性，剔除无效渠道；
4. **人工验收**：给出文件绝对路径，人工验收；不通过则按建议重下或换渠道。

本架构把主链路作为**与 evaluate 平行的独立体系**落地，职责分离、互不干扰。

## 第一版范围（验证阶段）

- **课程**：只梳理并跑通 3 门基础课——**数学分析（01）、高等代数（02）、概率论与数理统计（00）**
  （数学专业本科核心三课，均无前置；后续课程按用户正式确认再扩展，不自动推广）。
- **教材**：每门课程找到并标注最佳经典教材 + 配套习题集（沿用「2–4 套，贵精不贵多」原则）。
- **落位**：下载文件先进本仓库临时数据根（可删可重建）；**人工验收通过后正式移交根仓库
  `dataset/qed-tracker/`**（正式落地，唯一持久位置）。
- **渠道**：主链路内记录每次渠道尝试（来源/成功/失败/耗时），人工可据记录剔除无效渠道；
  与 [来源评估矩阵](../design/source-discovery.md)（人工评估结论）互补，不重复。

## 课程体系（用户 2026-08-12 审理）

- 数据文件：src/qed_tracker/courses/math.json（包内静态数据，范本，未实现）。
- **三大无前置基础课**：00 概率论与数理统计（新增课程）、01 数学分析、02 高等代数
  （= catalog 线性代数，同一课程不同名称）。
- 14 门课程完整清单、先修关系（DAG）、阶段划分见
  [主链路设计](../design/main-line-curriculum.md) 第 1 节；`related_targets` 只关联已通过二次
  确认评估（人工验收 approved）的课程目标，当前全部为空，随验收逐步回填。

## 架构

```mermaid
flowchart LR
    subgraph QEDTracker[QED-Tracker（临时中转）]
        COURSES[课程体系 courses/*.json] --> API[8901 /api/v1 主链路端点]
        API --> ENTRIES[教材条目服务 meta/main-line/]
        ENTRIES --> SEARCH[渠道搜索 providers]
        SEARCH --> DOWNLOAD[通用下载器]
        DOWNLOAD --> TMP[(临时数据根 raw/)]
    end
    API --> UI[8903 前端：课程知识链路 + 评审台]
    UI -->|人工评审 版本/评价/建议| API
    TMP -->|验收通过 移交| ROOT[(根仓库 dataset/qed-tracker/)]
    ROOT --> AXIOM[Axiom-Flow]
```

**职责边界：**

| 层 | 内容 |
| --- | --- |
| 课程体系（`courses/`） | 包内静态 JSON：学科课程清单 + 前置关系（先修→后修 DAG）+ 学习阶段 + 本科/研究生名称映射。数学范本 `courses/math.json`。 |
| 主链路条目（`main_line/` 规划） | 独立存储（`meta/main-line/`）：每门课程下教材条目，五要素 = 课程 + 版本/评价/建议 + 渠道记录 + 验收状态。与候选/资源体系（`meta/resources/`）完全解耦。 |
| 渠道记录 | 每条教材条目的下载尝试历史（来源、成功/失败、文件、耗时），运行时数据，支撑「渠道有效性表」。 |
| 落位 | 本仓库数据根 = 临时中转（可删可重建）；验收通过后移交根仓库 `dataset/qed-tracker/`（正式落地）。 |
| 8901 API | 新增主链路端点（`/courses`、教材条目查询/评审、渠道记录），8903 前端消费。 |

## 与现有体系的关系

| 现有体系 | 与主链路关系 |
| --- | --- |
| `catalog/evaluate` 任务 | 已退役（QED-030）；渠道评估职责由教材搜索/下载路径承接。 |
| `meta/resources/` + 三表（qt_selections/qt_downloads/qt_sources） | 资源登记链路保留（下载文件校验/哈希/登记）；主链路教材条目在验收后独立管理，不重复登记。 |
| `catalogs/math-qe.json` | 现有 13 门课程目录（研究生 QE 方向）保留；主链路课程体系与之并行，`course_id` 命名对齐（同一课程不同名称由用户审理映射，如「线性代数/高等代数」）。 |
| 来源适配器 / 通用下载器 | 复用：主链路下载仍走 providers → 通用下载器 → 校验/哈希，不新建下载实现。 |
| 8903 前端 | 课程知识链路（COURSE_ORDER 现状硬编码 → 改为消费 `/courses` API）；评审台按主链路条目展示。 |

## 关键设计决策（已确认）

1. **课程体系 = 独立包内 JSON + API 透出**：src/qed_tracker/courses/math.json（规划文件，未实现）→
   `GET /courses`（8901）→ 8903 知识链路。catalog 不动。
2. **主链路教材条目 = 独立数据**：五要素（课程 + 版本/评价/建议 + 渠道记录 + 验收状态），
   存储于 `meta/main-line/`，与现有候选/资源解耦。
3. **本仓库数据根 = 临时**：下载/登记先落本仓库 `dataset/qed-tracker/`（可删可重建）；
   **人工验收通过后复制 + 登记同步移交根仓库 `dataset/qed-tracker/`**（临时区副本保留留痕）。
4. **渠道有效性 = 运行时记录 + 文档矩阵互补**：主链路条目记录实际尝试（自动），
   来源评估矩阵记录人工评估结论（文档）；两者共同支撑渠道决策。
5. **乱码修复与存量清理**：解析/登记链路强制 UTF-8；存量乱码（任务/资源 JSON、
   《突破朗道位垒》txt）作为临时记录清理或重编码。
6. **LLM 评价校准**：权威性等级高/中/低 + 防「总评高」对比评级约束（见
   [主链路设计](../design/main-line-curriculum.md)）。
7. **mainline new 参照顶尖大学**：先参照 MIT/清华等课程设置，再按此探索候选（用户确认）。

## 待确认（用户评审）

- 主链路是否立即建 8901 端点，还是先 CLI/文档跑通 3 门课验证流程。
- LLM 预填的模型与提示词实现细节（`QWEN_API_KEY` 复用百炼）。
