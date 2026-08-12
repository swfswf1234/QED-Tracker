# 主链路设计：课程体系、教材条目、渠道记录与 CLI 流程

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-12
关联代码：`src/qed_tracker/courses.py`、`src/qed_tracker/courses/math.json`、`src/qed_tracker/main_line/`（store.py/advisor.py）、`src/qed_tracker/cli.py`（courses/mainline 命令组）、`src/qed_tracker/providers/books.py`（UTF-8 解码修复）
关联测试：`tests/test_courses.py`、`tests/test_main_line_store.py`、`tests/test_main_line_advisor.py`、`tests/test_main_line_cli.py`、`tests/test_encoding_regression.py`
关联 ADR：—
需求方：QED-Engine（8903 前端知识链路；根仓库 [course-acquisition-flow.md](../../../docs/design/course-acquisition-flow.md) 五阶段对齐）
执行方：QED-Tracker
上承架构：[主链路架构](../architecture/main-line.md)（Accepted，QED-026 已实现，见[实现计划](../plans/2026-08-main-line-curriculum.md)）

## 1. 课程体系数据模型（courses/math.json）

**绝对路径**：`D:\coding\QED-Engine\QED-Tracker\src\qed_tracker\courses\math.json`
（与 catalogs/math-qe.json 同级；`pyproject.toml` `package-data` 增加 `courses/*.json`）

### schema

```json
{
  "schema_version": 1,
  "subject": "math",
  "name": "数学",
  "description": "本科-研究生基础课程体系（依据《突破朗道位垒》梳理，用户 2026-08-12 审理）",
  "stages": ["本科基础", "本科进阶", "研究生基础", "QE冲刺"],
  "courses": [
    {
      "course_id": "01_math_analysis",
      "name": "数学分析",
      "aliases": ["高等数学（工科称呼）"],
      "stage": "本科基础",
      "prerequisites": [],
      "related_targets": ["01-rudin-zh", "01-rudin-en", "01-demidovich", "01-feidinghui",
                          "01-fikhtengolts-v1", "01-fikhtengolts-v2", "01-fikhtengolts-v3",
                          "01-xiehuimin-v1", "01-xiehuimin-v2", "01-chenjixiu-v1",
                          "01-chenjixiu-v2", "01-chenjixiu-answers", "01-polya"],
      "note": "三大基础课之一"
    }
  ]
}
```

### 字段

| 字段 | 内容 |
| --- | --- |
| `schema_version` / `subject` / `name` / `description` | 体系元信息；`subject=math` 预留其他学科扩展（计算机等） |
| `stages` | 学习阶段顺序（本科基础/本科进阶/研究生基础/QE冲刺） |
| `courses[]` | 课程清单，**数组顺序即学习顺序**（主知识链路 DAG 拓扑序） |
| `course_id` | 与 `catalogs/math-qe.json` 对齐；新增课程（如概率论与数理统计）用独立 id |
| `name` / `aliases` | 规范名 + 别名（同一课程不同名称：高等代数/线性代数） |
| `stage` | 所属阶段（`stages` 之一） |
| `prerequisites` | 先修课程 id 数组（空 = 基础课；构成主知识链路 DAG） |
| `related_targets` | 关联 catalog 目标 id（`math-qe.json` 内）。**只关联已通过二次确认评估（人工验收 approved）的课程目标**；当前全部为空，随主链路验收逐步回填 |
| `note` | 备注（选书依据等） |

### 课程清单（14 门，用户 2026-08-12 审理）

| course_id | 名称 | stage | prerequisites | 说明 |
| --- | --- | --- | --- | --- |
| 00_probability_stats | 概率论与数理统计 | 本科基础 | — | **新增课程**（无前置基础课）；catalog 无独立课程，related_targets 暂空 |
| 01_math_analysis | 数学分析 | 本科基础 | — | 三大基础课之一 |
| 02_linear_algebra | 高等代数 | 本科基础 | — | aliases: 线性代数（catalog 02 显示名） |
| 03_topology | 点集拓扑 | 本科基础 | 01, 02 | 泛函与流形先修 |
| 04_real_analysis | 实分析 | 研究生基础 | 03 | 测度论 |
| 05_complex_analysis | 复分析 | 研究生基础 | 03 | — |
| 06_functional_analysis | 泛函分析 | 研究生基础 | 04, 05 | — |
| 07_ode | 常微分方程 | 本科进阶 | 01 | — |
| 08_pde | 偏微分方程 | 研究生基础 | 01, 07 | — |
| 09_abstract_algebra | 抽象代数 | 研究生基础 | 02 | — |
| 10_qe_prep | QE 冲刺 | QE冲刺 | 01,03,04,05,06,07,08,09,11,13 | 汇总冲刺 |
| 11_probability | 测度论概率 | 研究生基础 | 04 | catalog 11（研究生课，与 00 不同） |
| 12_stochastic_processes | 随机过程 | 研究生基础 | 11 | — |
| 13_high_dim_prob | 高维概率论 | 研究生基础 | 11 | — |

### 第一阶段验证范围

只对 **00 概率论与数理统计、01 数学分析、02 高等代数** 三门（无前置基础课）跑通主链路闭环；
其余课程待用户正式确认后逐门扩展。

## 2. 主链路教材条目（meta/main-line/）

**存储**：数据根 `meta/main-line/<course_id>/<entry_id>.json`（独立于资源清单 `meta/resources/`）。
`entry_id` = 稳定 slug（如 `01-rudin-zh`），人工或工具生成，可重名不同版本。
`mainline new` 自动生成 `<course_prefix>-<slug>`：slug 取标题 ASCII 部分；纯中文标题
用标题 UTF-8 哈希前 8 位兜底（确定性、同课程内唯一），重复标题在调用 LLM 前即拒绝。

### 五要素 schema

```json
{
  "schema_version": 1,
  "entry_id": "01-rudin-zh",
  "course_id": "01_math_analysis",
  "title": "数学分析原理",
  "authors": ["Rudin"],
  "version": {
    "edition": "第3版",
    "publisher": "机械工业出版社",
    "year": "2003",
    "language": "zh",
    "detail": "中译本；译自 Principles of Mathematical Analysis 3rd"
  },
  "evaluation": {
    "source": "llm",
    "text": "经典中的经典，数学分析中文首选教材之一",
    "authority": "高",
    "set_candidate": "套一"
  },
  "advice": {
    "download": "recommended",
    "reason": "经典教材中文翻译版，与吉米多维奇习题集配对；archive 可自动下载"
  },
  "channels": [
    {
      "channel": "internet_archive",
      "attempted_at": "2026-08-12T10:00:00+00:00",
      "ok": true,
      "file_sha256": "730d8220...",
      "note": ""
    }
  ],
  "status": "draft",
  "reject_reason": "",
  "updated_at": "2026-08-12T10:00:00+00:00"
}
```

### 字段说明

| 要素 | 字段 | 内容 |
| --- | --- | --- |
| 课程 | `course_id` | 课程体系 id |
| 版本 | `version` | 版次/出版社/年份/语言/详细描述（回答「什么版本的什么教材」） |
| 评价 | `evaluation` | LLM 预填（`source=llm`）+ 人工可修改（`source=manual`）；文本 + 权威性等级（高/中/低）+ 套候选 |
| 建议 | `advice` | 下载建议（recommended / optional / not_recommended）+ 理由 |
| 渠道 | `channels[]` | 渠道尝试记录（自动生成，见下） |
| 状态 | `status` | 状态机（见下） |

### 状态机

```
draft（LLM 预填/人工新建）
  → reviewed（人工评审通过：版本/评价/建议定稿）
  → downloading（触发渠道下载）
  → downloaded（文件已落临时区）
  → approved（人工验收通过 → 移交根仓库）
  → rejected（人工否定：候选或文件硬删，记录保留留痕）
```

- `draft → reviewed`：人工评审（CLI 交互或编辑 JSON）；评价/建议允许人工覆盖 LLM 预填。
- `reviewed → downloading`：CLI 显式触发下载；尝试各渠道（archive 自动 / libgen 发现专用 →
  人工下载指引 → register 登记）。
- `downloading → downloaded`：文件经通用下载器/登记端点落临时区。
- `downloaded → approved`：人工验收（预览 PDF + 给出绝对路径）；通过后**复制**文件与登记同步
  **移交根仓库 `dataset/qed-tracker/`**（正式落地，临时区副本保留留痕），条目记录 `final_path`；
  同时课程 `related_targets` 回填该目标（二次确认评估完成）。
- `downloaded → rejected`：人工验收不通过，按建议重下或换渠道（可回 `draft` 改建议后重试）。

### LLM 评价校准（防「总评高」）

- 权威性等级取值 **高 / 中 / 低**；LLM 预填时强制要求**给出区分度依据**：引用具体证据
  （如「XX 大学 QE 指定教材」「数学社区公认经典」「知名度低/版本小众」），不能仅凭书名判断。
- 提示词要求对同一课程多本候选**相互对比评级**（至少一高必有一中/低，避免全部评高）；
  人工评审时如发现 LLM 输出失真可覆盖（`source=manual`）。
- 评价文本与权威性等级**仅供人工参考**，不作为自动下载依据（下载仍需显式 `download` 触发）。

### 与现有资源体系的关系

- 下载文件仍走现有通用下载器（PDF 校验/哈希/原子落盘）+ 资源登记（`meta/resources/` +
  `qt_resources`），**不新建下载实现**；主链路条目在验收后记录 `resource_id` 引用。
- `evaluate` 任务不动（渠道评估工具）；主链路条目独立生成。

## 3. 渠道记录（渠道有效性表）

- **运行时数据**：每条目 `channels[]` 自动记录每次渠道尝试（来源、时间、成功/失败、文件哈希、
  备注）。汇总视图 = 按渠道聚合的成功/失败次数与成功率。
- **与 source-discovery.md 互补**：文档矩阵 = 人工评估结论（连通性/覆盖/质量）；主链路渠道记录
  = 实际下载尝试（运行时事实）。两者共同支撑「剔除无效渠道」决策。
- **人工可标注**：渠道尝试可附人工备注（如「libgen torrent 需人工下载」），供评审。

## 4. CLI 流程（已实现，QED-026）

> 以下命令已实现（提交链 948fa88~ea905b9，全量 221 passed + 3 skipped）。风格沿用
> argparse + `--json` + 稳定退出码（0 成功 / 2 错误 / 3 无结果）。

| 命令 | 说明 |
| --- | --- |
| `qed-tracker courses list` | 列出学科课程体系（当前 math） |
| `qed-tracker courses show <course_id>` | 查看单门课（含前置/关联 target；也接受学科名） |
| `qed-tracker mainline list --course <course_id>` | 列出课程教材条目（五要素视图） |
| `qed-tracker mainline new --course <id> --title ...` | 新建条目：**先参照顶尖大学课程设置（MIT/清华等指定教材）→ 再按此探索**；LLM 预填评价，需 QWEN_API_KEY |
| `qed-tracker mainline review <course_id> <entry_id>` | 人工评审定稿（状态迁移 draft→reviewed） |
| `qed-tracker mainline download <course_id> <entry_id>` | 触发渠道下载（自动源或人工下载指引） |
| `qed-tracker mainline verify <course_id> <entry_id>` | 校验已下载文件（PDF 结构/SHA-256/页数） |
| `qed-tracker mainline approve <course_id> <entry_id>` | 验收通过 → 复制移交根仓库 dataset/qed-tracker/ |
| `qed-tracker mainline reject <course_id> <entry_id> --reason <原因>` | 验收不通过（原因必填，持久化 reject_reason） |
| `qed-tracker mainline channels` | 渠道有效性汇总表（成功率视图） |

### 已知限制（2026-08-12 最终评审登记，后续任务）

1. **版本要素 CLI 闭环未实现**：`mainline new` 不落 `version`，`review` 仅状态迁移；
   `version` 字段当前需手工编辑 JSON。后续：new/review 增加 `--edition/--language/--publisher`
   参数写入 version。
2. **人工下载 register 闭环未实现**：无自动候选时提示"register 登记"，但没有 CLI 命令把
   `downloading → downloaded` 并写入人工登记的 `resource_id/final_path`（libgen 场景）。
   后续：新增 `mainline register <course_id> <entry_id> --path <相对路径>` 复用登记端点。
3. **防总评高「对比评级」单本不可执行**：`prefill` 每次只呈现一本书，提示词要求的
   "同课程多本对比评级、至少一本非高"无法真正实现。后续：批量预填或注入同课程已在册条目
   供对比。
4. **`rejected → draft` 重试无 CLI 出口**：状态机支持（有测试），但 CLI 无命令，且重试同标题
   会被 `new` 重复预检拦截。后续：`review` 支持 rejected 条目回 draft。

**第一阶段验证闭环**（00/01/02 三门）：
1. `courses list` 确认课程体系加载（14 门，含新增 00）
2. 每门课 `mainline new` 生成教材条目——**先参照顶尖大学（MIT/清华等）该课程指定教材设置，
   再按此探索候选**；LLM 预填评价/建议（防「总评高」校准）
3. `mainline review` 人工定稿（版本/评价/建议）
4. `mainline download` 下载（archive 自动或 libgen 人工指引 → register）
5. `mainline verify` 校验 → `mainline approve` 验收通过，**复制 + 登记同步**移交根仓库
6. `mainline channels` 查看渠道有效性，剔除无效渠道

**mainline new 的探索依据（2026-08-12 用户确认）**：
- 第一步：收集顶尖大学（MIT、清华等）该课程的官方指定教材/课程大纲（LLM 检索辅助）；
- 第二步：以该参照为锚点探索可下载候选（渠道搜索 + 候选比对）；
- 第三步：LLM 预填版本/评价/建议，人工评审定稿。

## 5. 乱码修复与存量清理（本轮一并执行）

- **修复**：来源解析与任务/资源 JSON 写入链路强制 UTF-8（定位 `_text()` 解码 / `json.dumps`
  编码处）；新增回归测试守护（写入内容含中文断言可读）。
- **存量清理**：本仓库数据根为临时中转（用户已确认可删可重建）——乱码任务/资源 JSON 清理或
  重建；《突破朗道位垒》txt 重编码为 UTF-8（保留原 GBK 到历史基线或直接修复）。

## 6. 已确认决策（2026-08-12 用户审理）

- `00_probability_stats` 的 `related_targets`：**暂空**（catalog 无独立课程）。
- `related_targets` 通用规则：**只关联已通过二次确认评估（人工验收 approved）的课程目标**，
  当前全部为空，随主链路验收逐步回填。
- LLM 权威性等级：**高/中/低**，并强制「防总评高」校准（对比评级 + 证据依据，见上）。
- `mainline new` 生成方式：**先参照顶尖大学（MIT/清华等）课程设置 → 再按此探索**。
- 移交根仓库动作：**复制 + 登记同步**（临时区副本保留留痕）。

## 7. 待确认（评审后实现）

- LLM 预填的模型与提示词实现细节（`QWEN_API_KEY` 复用百炼）。
- 顶尖大学参照的来源与存储方式（LLM 检索即时生成 vs 预置课程大纲数据）。
- `mainline new` 的候选来源范围（复用现有 providers / 新增主链路专属渠道）。

## 关联文档

- [主链路架构](../architecture/main-line.md)（Accepted，QED-026 已实现）
- [下载与清单设计](acquisition-and-inventory.md)（下载/登记链路复用）
- [来源探索与评估](source-discovery.md)（渠道矩阵）
- 根仓库 [course-acquisition-flow.md](../../../docs/design/course-acquisition-flow.md)（五阶段对齐）
