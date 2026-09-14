# 操作指南

状态：Current
最后更新：2026-09-11

本指南描述 QED-Tracker 的主流程操作：环境与本地配置 → 启动服务 → 健康检查 → 知识探索 → 下载（规划中）。命令均通过脚本或 `qed-tracker` CLI 执行；系统边界与契约见[系统总览](../architecture/system-overview.md)。

## 1. 环境配置与本地配置

### 1.1 Python 环境

本机环境事实（conda 环境名/路径、Python 版本、机器标识、服务端口速查）以
[本地开发环境](../standards/local-dev.md)为准，该文档仅在指定机器上生效、其他环境需复制并修改；
安装与门禁命令见[开发指南](development.md)「环境速查与命令矩阵」。本仓库所有命令统一经该
conda 环境执行，避免 shell 落到 anaconda base 缺少项目依赖。

### 1.2 配置来源与优先级

配置读取优先级：**真实环境变量 → 本仓库 `.env` → 根仓库 `.env`（自当前目录向上查找）→
内置最小默认值**；只认 `QED_*` 变量 + 密钥变量 `API_KEY`（`TOML` 与 `QED_TRACKER_*` 前缀已退役）。
本仓库 `.env` 最小模板（`API_KEY` 与 `QED_DB_PASSWORD` 为独立运行底线键，不得删除）：

```dotenv
QED_API_SELECT=local      # local=直连厂商；qed-engine=经 8900 网关（不接触密钥）
API_KEY=                  # 模型调用密钥（LLM 探索必需）
QED_MODEL=qwen3.7-plus    # 探索管线模型（P15 纪律：非思考型）
QED_DB_HOST=127.0.0.1
QED_DB_PASSWORD=          # MySQL 密码（未配置时 8901 相关端点 409 降级，服务照常）
QED_TRACKER_PORT=8901
QED_DATA_ROOT=D:\coding\QED-Engine\dataset
```

其他常用键：`QED_LLM_TIMEOUT`（默认 300s，探索管线长生成依赖此值）、`QED_TRACKER_URL`（CLI 访问的 8901 地址）、`QED_PROXY`、`QED_TLS_VERIFY`（默认开启，仅可由用户显式关闭）、`QED_SOURCES`（渠道遍历顺序）。

取书链键组（`QED_BOOK_*`，语义见[下载管线设计](../design/download-pipeline.md)）：
`QED_BOOK_CANDIDATE_BUDGET`（候选级预算秒数，默认 300）、`QED_BOOK_MIN_PAGES`（机器验收页数下限，默认 10）、
`QED_BOOK_MIN_SIZE_BYTES`（大小下限，默认 204800）、`QED_BOOK_SEARCH_LIMIT`（每 query 每渠道候选上限，默认 8）、
`QED_BOOK_QUERY_VARIANTS`（LLM 检索词变体上限，默认 3）、`QED_BOOK_LLM_QUERY`/`QED_BOOK_LLM_CONFIRM`
（LLM 检索词变体/候选确认开关，默认开）、`QED_BOOK_LLM_BUDGET`（单次取书 LLM 确认调用预算，默认 8）。
旧键 `QED_FETCH_ATTEMPT_TIMEOUT` 已由 `QED_BOOK_CANDIDATE_BUDGET` 取代（一版别名，新键设置时被其覆盖）。

安装后确认生效配置：

```powershell
qed-tracker config show
```

**排障提示**：未配置 MySQL 不是故障（相关端点按契约 409 降级）；`API_KEY` 未配置时 LLM
dry-run 端点返回 409 而非崩溃。数据根内的 PDF 不会被隐式扫描、移动或删除。

## 2. 启动服务（后台运行）

以下命令统一经 `conda run -n qed_env` 执行（本地开发环境约定，见[本地开发环境](../standards/local-dev.md)）。

### 2.1 脚本方式（推荐，后台启动，支持启停管理）

仓库级启停入口统一为 `scripts/qed_tracker_service.py`（契约见[服务管理中心设计](../design/service-management.md)）：
它以**后台子进程**方式启动 8901 服务，命令立即返回，PID 与日志落 `logs/`：

```powershell
conda run -n qed_env python scripts/qed_tracker_service.py start            # 默认立即返回，后台运行
conda run -n qed_env python scripts/qed_tracker_service.py start --wait 30  # 轮询 /api/v1/health 直到就绪
conda run -n qed_env python scripts/qed_tracker_service.py start --mode qed-engine  # 指定模型模式
conda run -n qed_env python scripts/qed_tracker_service.py status           # 运行状态（pid/端口探测）
conda run -n qed_env python scripts/qed_tracker_service.py stop             # 优雅停止 + 强杀兜底
conda run -n qed_env python scripts/qed_tracker_service.py restart --wait --mode local
```

运行事实：PID 文件 `logs/qed-tracker.pid`，模式状态文件 `logs/qed-tracker-mode`，
子进程输出落 `logs/qed-tracker-serve.log`，应用日志写 `logs/qed-tracker.log`。退出码
`0` 成功/幂等、`1` 运行失败、`2` 参数错误。

**停止可靠性语义**（2026-09-04，与根仓库 8900/8903 脚本同构）：判活用内核句柄探测
（探测失败不再误判为「已死」）；优雅信号（CTRL_BREAK）未生效由强杀兜底成功时回显
`stopped (forced)`——正常现象，conda run 等跨 console 语境常见，无需处理；优雅+强杀后
仍存活则退出码 1 显式报 `stop failed`（绝不假 stopped），按提示手动
`taskkill /PID <pid> /T /F` 后重试 `stop` 清理 PID 文件。停止后可再用 `status` 复核，
避免残留进程占用端口。

### 2.2 CLI 方式（前台运行，排查/临时用）

```powershell
conda run -n qed_env qed-tracker serve --port 8901
```

前台阻塞运行，适合调试日志；日常后台运行用 2.1 脚本方式。独立启动时自动从当前目录向上查找根
`.env` 并注入 `QED_*` 与密钥（不覆盖已显式设置的环境变量）；MySQL 迁移失败只警告、服务照常启动。
服务日志双通道输出：stderr 与 `logs/qed-tracker.log`。

## 3. 主流程

### 3.1 健康检查

服务就绪后探测健康端点（返回 `{"status": "ok"}`）：

```powershell
Invoke-RestMethod http://127.0.0.1:8901/api/v1/health
```

脚本方式可直接用 `start --wait 30` 完成启动+健康等待；`status` 子命令同样经端口探测确认服务存活。

### 3.2 知识探索

知识获取分两条轨道，二者择一或混用：

#### 轨道一：手动导入标准答案 JSON（无 LLM，导入即定稿）

知识正本位于 `docs/knowledge/`（领域 JSON + 课程 JSON，作为对照基准数据）：

```powershell
qed-tracker domains import docs/knowledge/math-advanced.json
qed-tracker knowledge import docs/knowledge/math-advanced/math_analysis.json
qed-tracker books import <book_id> <本地PDF绝对路径> --target raw/<domain>/<course>/<书名>.pdf
```

- `domains import`：领域标准答案 JSON → 写 qed_domain/qed_course，领域直接标记已完成（CLI 跳过人工审核，重放幂等）。
- `knowledge import`：课程标准答案 JSON → 采纳后导入即确认 + 按 refs 幂等建候选册，直达「已确认+候选册就绪」。
- `books import`：本地 PDF → 校验（magic/页数）→ 哈希去重 → 拷入数据根 → 登记为资源。

#### 轨道二：LLM 领域探索（需 `API_KEY`，经 8901 dry-run 同步执行，不写库）

```powershell
qed-tracker domains explore 高等数学
qed-tracker domains explore 高等数学 --scope "本科基础与核心主干" --timeout 600
qed-tracker domains explore 高等数学 --mode text --ref-text "用户探索笔记内容..."
qed-tracker domains explore 高等数学 --confirm-name 高等数学
```

- 管线为两步（`domain@v4` 领域校验与探索 → `courses@v8` 核心课程+层级+先修），输出与
  `docs/knowledge/` 领域标准答案同构（每门课 stage/prerequisites 内联）；真实耗时约 1~3 分钟。
- `--mode text`（配 `--ref-text`）或 `--mode doc`（配 `--ref-doc <路径>`）可注入用户参考材料。
- **名称确认流**：当输出 `领域名称需要人工确认` 时，核对建议名后带
  `--confirm-name <规范名>` 重跑即可贯穿后续步骤。
- 输出含课程清单（stage 分层 + 前置关系）、graph TD 学习路径图与逐步调用明细；
  `--json`（全局选项，置于命令前）输出完整 JSON 便于脚本消费。
- 每次调用的模板编号、完整问句与原始回答落共享表 `qed_llm_calls`，可经根仓库前端审核。

课程教材探索（为已知课程推荐「教材+习题集」成套方案）当前经 API dry-run 端点使用：
`POST /api/v1/courses/{course_id}/prompt-explores/dry-run`，契约见[API 文档](../architecture/api.md)。

#### 完整探索走查（推荐顺序）

1. **确认服务就绪**：`status` 或健康检查（见 §3.1）。
2. **手动轨导入标准答案**（可选，无需 LLM）：`domains import docs/knowledge/math-advanced.json`。
3. **LLM 领域探索（真实冒烟）**：`domains explore 高等数学`（见轨道二；记录耗时与课程数）。
4. **前置：确保课程存在**——课程探索作用于已知课程行：若走手动轨已 `domains import` 或领域探索
   已 `apply-results` 落库，`qed_course` 才有对应课程；否则课程 dry-run 返回
   `404 COURSE_NOT_FOUND`（表重建后默认无课程，走查前先执行本步）。
5. **课程教材探索（只需选一门，如 `math_analysis`）**：当前 CLI 无课程探索命令，经 8901
   API dry-run（PowerShell）：

   ```powershell
   Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8901/api/v1/courses/math_analysis/prompt-explores/dry-run -ContentType 'application/json' -Body '{}'
   ```

   - 返回 `{dry_run, report: {course, tutorials}, calls}`：`tutorials` 为 2~4 套方案
     （set_no/name/position/intro/textbook_ref[]/exercise_ref[]/parallel_ref[]），`calls` 为逐步调用明细。
   - 只探索一门即可验证课程管线；契约见[API 文档](../architecture/api.md)。
6. **审阅与落库**：领域/课程探索结果经 apply-results 确认或 re-explore 重探
   （当前 CLI 未暴露 apply，可经 API），见[探索管线设计](../design/exploration-pipeline.md)；手动轨
   六步流程与状态机见[知识录入设计](../design/knowledge-import.md)。

> **真实 LLM 冒烟依赖 API 配额**（内部依赖）：模型调用需 `API_KEY` 有可用额度；免费额度耗尽时
> 模型返回 `HTTP 403 Free quota exhausted`，dry-run 端点按契约映射为 `409/502 LLM_UNAVAILABLE`，
> 领域 `domains explore` 以退出码 2 + 错误 JSON 收尾、课程 dry-run 返回 `502`。此属外部配额限制，
> 非代码缺陷（2026-09-03 已切付费模型后验证通过）。

#### 实测记录（2026-09-03）

以下为切换到付费模型 `deepseek-v4-flash-0731` 后的**真实冒烟结果**（模型 `qwen3.7-plus` 时
`free quota exhausted`，改用付费模型 + 放宽 `max_tokens`）：

| 冒烟项 | 方式 | 结果 | 明细 |
| --- | --- | --- | --- |
| 领域探索 `高等数学` | CLI `qed-tracker --json domains explore 高等数学` | ✅ 退出码 0，132s | 完整报告：领域 + 12 门课程（mathematical_analysis / advanced_algebra / probability_and_statistics /…），`calls` domain@v4 + courses@v8 |
| 领域探索 `高等数学` | API `POST /api/v1/prompt-explores/dry-run` | ✅ HTTP 200，104.7s | 同报告，`confirmation_required=false` |
| 课程探索 `math_analysis` | API `POST /api/v1/courses/math_analysis/prompt-explores/dry-run` | ✅ HTTP 200，135.9s | 4 套方案（教程1~4，position 五档，textbook_ref/exercise_ref/parallel_ref 齐全），`calls` tutorials@v2 |

- **遗留缺陷修复**：领域/课程管线输出曾因 `llm_max_tokens=4096` 触发 `finish_reason=length`
  （`LLM_UNAVAILABLE`）；`DomainPipeline`/`CoursePipeline` 已改为 `max_tokens ≥ 16384` 下限。
- 前置：课程探索需 `qed_course` 已有对应课程（经 `domains import` 或领域探索 `apply-results` 落库），
  否则返回 `404 COURSE_NOT_FOUND`。

探索结果的确认/重新探索（apply-results / re-explore）与落库流程见[探索管线设计](../design/exploration-pipeline.md)。

### 3.3 书籍取书与登记（QED-050-D 书库化，已实现）

自动取书走五阶段链（检索→LLM 确认→下载→staging 机器验收→登记 owned），全部经 8901 后台
任务执行（CLI 只提交+轮询），设计与验收标准见
[下载管线设计](../design/download-pipeline.md)、端点契约见
[API 文档](../architecture/api.md)：

```powershell
qed-tracker mainline download <knowledge_id>
qed-tracker mainline download <knowledge_id> --include-parallel --timeout 3600
qed-tracker books fetch <book_id>
qed-tracker mainline verify <knowledge_id>
qed-tracker mainline channels
```

- 教程级取书（裁决 9 双入口教程级）：refs 聚合书集、排除已 owned、默认 decided（`--include-parallel`
  纳入 parallel_ref）；书级取书为单册五阶段，已 owned no-op；`mainline verify` 只读复核
  （inspect_pdf 重算比对，ok/missing/invalid/changed，不做状态迁移）；`mainline channels` 汇总
  qt_books 聚合 qt_sources 的渠道有效性。

- **机器验收硬门槛**（可经 `QED_BOOK_MIN_PAGES`/`QED_BOOK_MIN_SIZE_BYTES` 配置）：魔数 +
  pypdf 可解析 + 非加密 + 页数/大小下限；未过门槛的文件留在 staging，永不进入数据根 raw/。
- **人工导入**与自动取书汇合同一登记服务（`books import`，见 §3.2）：跳过初筛门槛，保留
  完整性校验（魔数/pypdf/sha256），D9 内容指纹命名，登记 `channel=local_import`。
- **并发防护**：同书同类型取书任务查重，重复提交返回 `409 TASK_ALREADY_RUNNING`。
- 无自动候选时任务结果附人工指引（file_keywords + metadata 候选链接），用 `books import` 补书。

## 4. 退出码约定

CLI 退出码：`0` 成功，`2` 参数或请求错误（资源不存在、服务 4xx、复核文件不可解析），`3` 任务
失败或部分失败（取书任务失败、没有可用候选、文件缺失），`4` 批处理部分失败或 verify 检测文件
指纹变化（changed），`5` 下载、文件或运行错误（顶层异常兜底），`6` 8901 服务不可达。机器调用应
同时检查退出码和 JSON 输出，不应只匹配人类可读文本。全局选项放在一级命令之前：

```powershell
qed-tracker --json domains explore 高等数学
```
