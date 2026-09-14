# 开发指南

状态：Current
最后更新：2026-09-11

本指南保存 QED-Tracker **怎么开发**：流程、步骤与边界。事实分工如下——

| 内容 | 唯一维护位置 |
| --- | --- |
| 本机环境事实（机器标识、conda 环境名/路径、端口速查） | [本地开发环境](../standards/local-dev.md) |
| 可复制命令（安装/测试/门禁/CLI 冒烟） | 本指南「环境速查与命令矩阵」 |
| 服务启停与操作流程 | [操作指南](operations.md) |
| 工程治理规则（文档/ADR/测试/跨项目） | [规范索引](../standards/index.md) |
| Agent 入口与变更分级判据 | 根 [AGENTS.md](../../AGENTS.md) |

## 定位与边界

- **本指南负责**：开发流程与步骤、门禁命令、事实来源与实现约束。
- **本指南不负责**：治理规则正文（`standards/`）、架构与设计契约（`architecture/`、`design/`）、
  服务操作（[operations.md](operations.md)）。
- **维护契约**：[文档治理规范](../standards/doc-governance.md) 规定 `guides/` 为人类文档、
  agent 不主动整理；本指南「开发流程」节由根 [AGENTS.md](../../AGENTS.md) 的 AI 开发守则授权
  承载 agent 开发流程正文，其余节默认由人类维护，agent 只提建议。

## 当前事实来源

按以下顺序定位信息：

1. [README](../../README.md)：产品边界和首次使用。
2. [文档索引](../index.md)：当前架构、设计、指南和路线图入口。
3. [待办列表](../trackers/todo.md)：当前计划、缺陷和外部验收阻塞。
4. 代码、测试和包内目录数据：最终运行事实。

历史资料只用于追溯，不得作为当前实现依据。公共 CLI、配置、目录 schema、资源 schema 或 Axiom 契约发生变化时，必须同步更新当前文档和测试。

## 环境速查与命令矩阵

环境事实（conda 环境名/路径、机器标识、端口速查）以[本地开发环境](../standards/local-dev.md)为准，
本节不复制。可复制命令统一在本节维护：

| 操作 | 命令 |
| --- | --- |
| 安装/更新依赖 | `conda run -n qed_env python -m pip install -e ".[dev]"` |
| 全量测试 | `conda run -n qed_env python -m pytest tests -q` |
| 代码质量 | `conda run -n qed_env python -m ruff check src tests scripts` |
| 文档门禁 | `conda run -n qed_env python -m pytest tests/test_documentation.py -q` |
| CLI 冒烟 | `conda run -n qed_env qed-tracker --version` |
| 目录冒烟 | `conda run -n qed_env qed-tracker --json catalog list` |
| 差异检查 | `git diff --check` |

> 环境名以[本地开发环境](../standards/local-dev.md)为准（本机为 `qed_env`；Windows 文件系统大小写
> 不敏感，历史文档中的 `QED_env` 指向同一环境）。配置直读根仓库 `.env` 的 `QED_*` 变量，无根
> `.env` 时使用内置最小默认值，详见[操作指南](operations.md)。

## 开发流程（六步）

每项目独立走六步；变更边界判据见根 [AGENTS.md](../../AGENTS.md)「变更分级与边界」。技能只做薄
触发与指路，正文以本仓库 docs 为准。

| 步 | agent 动作 | 人类决策点 | 事实源 | 技能 |
| --- | --- | --- | --- | --- |
| 1 进场读必读 | 读状态快照、台账与相关标准 | 交付任务、定优先级 | [project-status](../trackers/project-status.md)、[todo](../trackers/todo.md)、[standards](../standards/index.md) | `qed-intake` |
| 2 定级 | 判变更对象与风险分类，给出方案 | **拍板定级**（未定级不实施） | 根 [AGENTS.md](../../AGENTS.md)、[todo 规则](../trackers/todo.md) | `qed-intake` |
| 3 立项 | 写 `plans/` 计划 + todo 登记 | **评审计划** | [doc-governance](../standards/doc-governance.md) | `qed-plan` |
| 4 实现 | 用 code-map 定位模块，先测试后实现（TDD） | 抽查/评审 | [code-map](../architecture/code-map.md)、`design/`、[testing](../standards/testing.md) | `qed-implement` |
| 5 验证 | 跑完整门禁，整理证据 | **验收** | [testing](../standards/testing.md)、[local-dev](../standards/local-dev.md) | `verification-before-completion` |
| 6 收尾 | 计划两态判定、todo 移 `completed.md`、同步设计/架构/索引 | **确认关闭** | [doc-governance](../standards/doc-governance.md) | `qed-closeout` |

**标准映射机制**：全局工具层（`~/.config/opencode/` 的默认开发 agent 提示与 `qed-*` 技能）只引用
「概念」（任务生命周期、文档治理、测试门禁、本地环境、模块映射），实际文件由
根 [AGENTS.md](../../AGENTS.md)「标准映射」表定位，技能不硬编码本仓库路径。本仓库暂无独立
`task-lifecycle.md`，任务生命周期口径内联于 `AGENTS.md`「变更分级与边界」。

## 分支与提交

- `develop` 用于日常开发，较大改动从它派生 `feat/*`。
- 发布候选从 `develop` 合入 `main`。
- `main` 上的修复发布后必须同步回 `develop`。
- 提交保持单一目的，不回滚无关用户改动；过程由 Git 记录，不新增逐日 worklog。

## 实现约束

- 来源适配器只搜索和解析下载地址，文件写入、重试、校验、哈希及去重必须经过通用服务。
- 默认测试不得访问公网。来源协议变化使用固定 fixture 覆盖，真实连通性由人工检查。
- 测试只能使用临时目录，禁止读取或修改实际数据根。
- 不得隐式扫描、移动或删除数据根内的 PDF。
- TLS 校验默认开启，只能由用户显式配置关闭。
- 批量目录下载必须保持严格匹配；不确定候选不得自动落盘。
- Axiom 上传默认不解析，只有显式 `--parse` 才能创建可能产生费用的任务。
- 论文推荐测试必须使用假顾问或 `httpx.MockTransport`，CI 不读取模型密钥、不访问 arXiv，也不把模型评分写入资源事实。
- 主链路（`courses`/`mainline`/`books`）：教程与书行落 `qt_knowledge`/`qt_books`（QED-050-D
  书库化，0018 重建契约）；LLM 预填/确认只生成可审阅评估，判断不写资源事实（落 `qt_sources`
  留痕 + `qed_llm_calls` 审计）；取书经 8901 五阶段链（CLI 只提交+轮询），下载/校验/哈希走通用
  服务；登记唯一入口 `mark_owned`（raw/ 即下载与人工导入共用成品区，无「复制移交」语义，
  approve/reject 已删除）；主链路测试必须使用假顾问/FakeProvider 或 `httpx.MockTransport`，
  不访问公网、不读取真实数据根。
- 探索管线（`prompt_lab/`）：领域/课程 dry-run 不写任何表（engine 置 None），唯一痕迹是
  `qed_llm_calls` 审计；LLM 输出只经模板 `validate` + 跨步一致性校验，模型不写资源事实；
  长输出（courses@v8 / tutorials@v2）需 `max_tokens ≥ 16384`（`DomainPipeline`/`CoursePipeline`
  已强制下限，`settings.llm_max_tokens`=4096 会 `finish_reason=length` 截断）。

## 验证门禁

安装开发依赖后，按「环境速查与命令矩阵」运行完整门禁：**全量 pytest、ruff 检查、
`qed-tracker --version` 与 catalog 冒烟全部通过**方可声称完成（门禁组成与隔离铁律见
[测试架构与门禁](../standards/testing.md)）。文档治理类变更必须运行 `tests/test_documentation.py`
并全绿。

测试覆盖配置优先级、目录唯一性和匹配边界、来源归一化、可靠下载、资源登记与校验、论文推荐与报告重放、CLI 命令树和退出码，以及 Axiom 的上传与可选解析。真实来源和模型在线可用性不作为门禁；人工检查应记录运行时间、来源、模型、结果和错误摘要（探索管线真实冒烟记录见[操作指南](operations.md)「实测记录（2026-09-03）」与共享表 `qed_llm_calls` 审计）。

本地门禁为唯一门禁（不依赖远端 CI）；wheel 构建不作为门禁（项目不分发 wheel，editable 安装已覆盖入口与数据文件验证）。
