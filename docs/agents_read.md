# 📜 QED-Engine: Agentic Operations Protocol (AOP)

> **版本**：1.0 (Geek/PhD Hybrid Edition)
> **状态**：Active
> **目标**：实现从“信息获取”到“逻辑内化”的闭环，跨越数学研究最低标准。

## 1. 认知与优先级协议 (Cognitive Priority)

Agent 在执行任务前必须遵守以下优先级：

1. **SSoT (Single Source of Truth)**：`docs/` 目录下的文档是唯一真实来源，禁止猜测。
2. **Context-First**：先检查 `docs/trackers/todos.md`，再阅读相关 `docs/design/` 文档。
3. **Safety & Idempotency**：所有操作应可重复运行，不可逆操作必须在 `docs/worklogs/` 请求人类二次确认。

## 2. 核心工作流：P-E-V-L 循环

每个原子任务必须经历以下四个阶段：

### 2.1 计划阶段 (Plan)

* **Actions**：在执行前，于对话中或 `docs/worklogs/` 生成任务预览。
* **Content**：包括当前状态分析、预期执行步骤及潜在风险评估。

### 2.2 执行阶段 (Execute)

* **代码规范**：Python 遵循 PEP 8，FastAPI 架构需保持模块化与依赖注入。
* **数学符号**：所有文档及代码注释中的公式必须使用标准 LaTeX (`$formula$` 或 `$$formula$$`)。

### 2.3 验证阶段 (Verify)

* **强制自检**：禁止"盲写"，必须运行相关脚本或测试用例验证逻辑。
* **结果记录**：验证证据（日志片段或输出）必须追加至当天 `docs/worklogs/`。

### 2.4 日志阶段 (Log)

* **Tracker 同步**：严禁在未更新 `docs/trackers/todos.md` 的情况下提交代码。
* **文档沉淀**：重构或架构变动必须同步更新 `docs/design/` 下的对应文件。

## 3. 数字化与 RAG 专项规则 (Knowledge Core)

针对数学教材数字化的特殊要求：

* **Layout Awareness**：处理 MinerU 产出的数据时，必须保留标题、定理、习题的逻辑层级。
* **Reference Integrity**：在 LlamaIndex 索引过程中，必须保留原书中的交叉引用标签（如“见定理 2.1”）。
* **Latex Sanitization**：遇到无法确定的公式识别错误，必须标记 `[CHECK_REQUIRED]`，严禁擅自修改数学逻辑。

## 4. 目录职责与自动化协议

所有 AOP 目录均位于 `docs/` 下。

| 目录 | 强制规则 |
| --- | --- |
| **`docs/design/`** | 统一存放架构、模块设计和技术方案。不准使用散文，优先使用 Mermaid 图表和代码 Schema。 |
| **`docs/discuss/`** | 存放尚未定案的技术路径。讨论完成后需标注 `Resolved` 并转移至 `docs/design/` 或 `docs/trackers/`。 |
| **`docs/trackers/`** | 只维护 `todos.md` (未完成) 和 `resolved.md` (已完成)。严禁在此存放详档。 |
| **`docs/worklogs/`** | 文件名必须为 `YYYY-MM-DD.md`。记录每一轮操作的内容、关键文件和验证结果。 |
| **`docs/knowledge_base/`** | 记录数字化进度。包含 `inventory.md` (书目状态) 和 `dependency_graph.md` (知识依赖)。 |

## 5. 运行环境

* **Conda 环境**：`QED_env`
* **Python 版本**：3.12
* **依赖安装**：`pip install -r requirements.txt`
* **代理配置**：`setting.ini` 的 `[Proxy]` 段落配置 HTTP 代理 (Clash 默认 7890)
* **Agent 行为**：所有 Python 操作必须在此 Conda 环境下执行，不可使用 Base 或其他环境。

## 6. GIT 管理与提交规范

* **分支管理**：`main` 保持稳定，`dev` 用于日常开发，大型重构使用 `feat/` 前缀。
* **Commit Message**：必须包含前缀：`feat:`, `fix:`, `docs:`, `refactor:`。
* **提交前检查**：每一轮 Commit 前，Agent 必须检查并更新相关 `docs/design/`, `docs/trackers/` 和当天 `docs/worklogs/`。

---