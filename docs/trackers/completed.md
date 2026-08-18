# 完成台账

状态：Current
最后更新：2026-08-18

本文件只追加已关闭任务的简短结果、提交或本地验证证据。

| ID | 关闭日期 | 结果 | 验证证据 |
| --- | --- | --- | --- |
| QED-001 | 2026-07-30 | 应用层拆分为 books、papers、resources，旧聚合服务退出运行时。 | 全量回归 `49 passed`；Ruff 通过。 |
| QED-002 | 2026-07-30 | 百炼顾问、两套内置目标档案、评分契约与密钥隔离完成。 | 百炼 MockTransport、档案校验和失败报告测试通过。 |
| QED-003 | 2026-07-30 | arXiv 检索规划、候选去重、Inventory 排除、稳定排序、选择报告及显式下载完成。 | 应用层与 CLI 离线端到端测试覆盖退出码 2、3、4、5，共 `49 passed`。 |
| QED-004 | 2026-07-30 | 0.4 CLI、配置、文档治理和分发元数据完成。 | Python 3.12 wheel 构建成功并包含目录及两套论文档案；`git diff --check` 通过。 |
| QED-006 | 2026-07-30 | 0.5 收缩为三个开放教材来源，删除 Range 续传、重复 PDF 检查、两个冗余命令和 BeautifulSoup 依赖。 | 离线全量回归 `48 passed`，Ruff 与 diff 门禁通过；Python 3.12 wheel 包数据和依赖元数据验证通过。 |
| QED-007 | 2026-07-30 | 完成 0.5 发布一致性审计，修正文档代码路由并统一本地与 GitHub Actions 门禁。 | `49 passed`、Ruff、diff、Python 3.12 wheel、包数据和 CLI 冒烟通过。 |
| QED-008 | 2026-08-05 | 服务化：8901 API（/api/v1）+ 后台任务与轮询完成。 | 提交 `cbc841c`；`GET /health`、任务落盘、并发上限与 sha256 幂等；API/客户端单元测试通过。 |
| QED-009 | 2026-08-05 | 配置与数据迁移：直读根 .env `QED_*`，TOML 与 `QED_TRACKER_*` 退役，数据根 dataset/qed-tracker/（raw/meta/tmp）布局完成。 | 提交 `cbc841c`；无根 .env 时最小默认值 + 尾注提醒；新下载落 raw/ 对应类型目录。 |
| QED-012 | 2026-08-05 | MySQL qt_resources 登记索引与状态机完成：双写、状态机 candidate→…→approved/rejected、llm_evaluation/catalog_ref/留痕字段。 | 提交 `47b636d`；先落盘后登记、失败可重放、同 sha256 幂等、无密码降级运行；db 测试通过。 |
| QED-013 | 2026-08-05 | 书单 math-qe-v2 与 LLM 筛选评估完成：13 门课程 54 目标、qwen 辅助、按课程批量评估。 | 提交 `21aad7d`、`4405a87`；catalog 落 catalogs/；evaluate 产出 candidate 含可审阅 llm_evaluation，不写资源事实。 |
| QED-015 | 2026-08-05 | 下载任务与预览端点完成：POST /tasks/books/download（仅 confirmed）+ GET /resources/{id}/file 预览流。 | 提交 `21aad7d`；非法触发 409、sha256 幂等复用、预览 Content-Type/长度正确。 |
| QED-016 | 2026-08-05 | 验收闭环端点完成：confirm（candidate→confirmed）、approve（downloaded→approved）、reject（candidate 或 downloaded→rejected，reason 必填，后者硬删文件 + DB 留痕）；闭环经 8901 API。注：设计中的 CLI 闭环命令（catalog evaluate / resources … / books download）未实现，属 QED-010 转 HTTP 客户端范围（2026-08-12 W3 台账勘误）。 | 提交 `21aad7d`；非法迁移 409、拒绝必填原因、已拒记录保留且同源候选不再推荐。 |
| QED-017 | 2026-08-06 | 人工评估三态与中文优先完成：状态机 backup、backup 端点、前端三态卡片 + 按课程评估视图、evaluate 跳过已评估目标。 | 提交 `5f7c015`（17 文件 316+/23-，含 docs/design/source-discovery.md）；8901 重启后三态冒烟通过；QED-Engine ARCH-004 Phase 0 回执。 |
| QED-020 | 2026-08-10 | 人工评审优化完成：evaluate 同源去重（file_hint 例外）、qt_resources.review_note（Alembic 0002）、存量重复清理流程。 | 提交 `8693ca2`；全量 `145 passed + 3 skipped` + ruff；定向测试覆盖同源去重/file_hint/review_note；设计 review-round-dedup.md 同步。 |
| QED-021 | 2026-08-10 | LibgenProvider（发现专用）与人工登记闭环完成：libgen_li 解析、RETIRED_PROVIDERS 移除 libgen、POST /resources/{id}/register、ResourceKind.SUPPLEMENT。 | 提交 `8693ca2`；libgen 10 测试、register 37 测试、前端 46 测试全绿；libgen 候选永不自动写文件。 |
| QED-018 | 2026-08-12 | 来源探索与评估完成（三轮实测）：archive 中文 CJK 策略、open_library/gutenberg/OTL/libretexts/sciencep/pressbooks 连通性结论、libgen.li 中文全覆盖实测并裁决「发现专用 + 人工下载指引」。 | 评估矩阵与可达链路结论落 docs/design/source-discovery.md；libgen 恢复发现专用（RETIRED_PROVIDERS 移除）；剩余「libgen 人工下载通道」作为持续目标并入路线图。 |
| QED-023 | 2026-08-12 | 数据库设计确认完成：qt_* 表结构事实源文档升级（表清单/表结构/迁移），根仓库只做指引与规划（2026-08-09 用户裁决）。 | database-schema-ownership.md 转 Accepted/Implemented（含 qt_resources DDL/状态机/迁移管理）；根仓库 REQ-026 回执并入 QED-014 联调。 |
| QED-025 | 2026-08-12 | 提示文案修复：books.py 退役来源报错改为指向根 .env 的 QED_SOURCES。 | 提交（本轮）；定向测试断言新文案（`退役.*QED_SOURCES`）；全量门禁全绿。 |
| QED-019 | 2026-08-13 | 01 数学分析闭环完成：套一 Rudin 中/英 + 吉米多维奇 + 费定晖、套二 菲赫金哥尔茨 3 卷 + 谢惠民 上下、套三 陈纪修 上/下/答案 共 **12 条 approved**（≥2 套达标）；register 人工下载登记端点实测（套一本地 4 文件 + 套二 Downloads 5 文件登记通过）；陈纪修 v1/v2=textbook（上下册）、answers=solutions 类别区分并双写修正；全部 12 PDF + 12 meta JSON 经 sha256 校验移交根仓库 `dataset/qed-tracker/`（2026-08-13 用户审阅 01_math_analysis 目录无问题后放行）。 | 8901 API 实测：4+5 register → downloaded → 9 approve 全绿；API roles 核验（v1/v2=[textbook]、answers=[solutions]）；移交脚本 sha256 逐一校验通过（24 文件）；`224 passed + 3 skipped` 基线。 |
| QED-033 | 2026-08-18 | 8901 课程体系只读端点完成：`GET /api/v1/courses`（按领域分组全量，sort_order 有序）与 `GET /api/v1/courses/{domain_id}`（未知 404）；无 DB 409；**纯只读透出、数据加工对 QED-Engine 透明**（支撑根仓库 REQ-035 课程体系数据源切换）。 | 提交（QED-033）；`/courses` 4 用例 + 全量 **213 passed + 3 skipped + ruff clean**；8901 真实冒烟（math 1 领域/4 阶段/14 门课、课程字段恰 7 契约字段、/courses/math 200、/courses/phys 404）；契约节写入 database-schema.md「课程体系只读端点」。 |
| QED-034 | 2026-08-18 | 01 套 qt_books 数据纠偏 + solutions/supplement 词汇全量退休：吉米多维奇/费定晖 title 还原真实书名（原误写「数学分析原理（Rudin）」、part 误作第N册）、Rudin 两版 part 清空（版本归 display_title）、微积分学教程/习题课讲义 title 去作者、陈纪修上/下册 roles=[textbook,exercises]、答案册→exercise/[exercises]、习题课讲义 roles 收敛 [exercises]；models.py 退休 SUPPLEMENT/SOLUTIONS + catalog 54 目标 book×37+exercise×17；database-schema.md 书行响应契约（title/display_title 必含，前端消费 display_title）。 | 提交（QED-034）；事务 UPDATE 12 行（updated_by=data_fix，仅元数据列，磁盘零触碰）；全量 **213 passed + 3 skipped + ruff + git diff --check**；8901 冒烟 3 套全 200（kind/roles/title/part/display_title 全部符合）；证据归档 docs/history/qed-034-book-data-cleanup/（before/after 全行 dump + API 冒烟）。 |
| QED-035 | 2026-08-18 | 生命周期脚本 `_pid_is_alive` 编码修复完成（承接根仓库 REQ-040）：中文 Windows tasklist GBK 表头 utf-8 解码失败 → readerthread 中断 → stdout=None → TypeError → 停止/重启退出码 1 的故障闭环——`errors="replace"` 容忍非 utf-8 输出 + `(result.stdout or "")` 空值兜底（范式由根仓库 web 脚本同构验证）。 | 提交（QED-035）；回归测试 test_pid_is_alive_tolerates_non_utf8_stdout（stdout=None 不抛错/errors 参数存在/正常 ASCII 判定三场景）；全量 **214 passed + 3 skipped + ruff clean + git diff --check** + 文档治理 8 passed；真实 8901 冒烟（既有运行实例 stop exit 0 + PID 清理、start --wait healthy、restart exit 0，此前同操作退出码 1）；**REQ-040 回执内容已整理，待用户授权写入根仓库 REQ-040 行**。 |
