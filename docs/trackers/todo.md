# 待办列表

状态：Current
最后更新：2026-08-12

| ID | 类型 | 状态 | 事项 | 成功标准 |
| --- | --- | --- | --- | --- |
| QED-005 | Validation | 阻塞 | 真实百炼与 arXiv 冒烟 | 配置模型密钥并获准联网后，预览推荐并从同一报告下载一篇临时 PDF。当前阻塞证据：环境中未设置 LLM 密钥。恢复条件是设置 `QWEN_API_KEY`（根 `.env`）并允许受限网络调用；责任位置为本地人工验收。 |
| QED-010 | Plan | 待开始 | [跨项目] CLI 转 HTTP 客户端 + 基于真实 8901 服务的冒烟测试（需求方：QED-Engine，设计：docs/design/tracker-service.md） | `qed-tracker` 命令经 8901 完成任务；启动 → 建任务 → 轮询 → 校验文件落位全链路冒烟通过；`--no-wait` 输出 task_id。 |
| QED-011 | Validation | 待开始 | 重复下载链路验证（用户约定在 QED-008~010 冒烟后执行） | 同一资源二次下载返回既有资源记录，不产生重复文件，任务幂等。 |
| QED-014 | Validation | 待开始 | [跨项目] 联调冒烟与回执：真实 8901 全链路（评估→确认→下载→验收/删除→登记→qed CLI/8903 前端展示）（计划：../plans/2026-08-service-and-book-download.md；承接 QED-017 全链路覆盖、QED-020 存量清理 8901 重启实测、QED-021 真实 evaluate 01 冒烟） | 8901 服务 + qed CLI + QED-Engine 下载工作台数据贯通；根仓库 todo REQ-004/REQ-011/REQ-013/REQ-014 收到回执。 |
| QED-018 | Plan | 进行中 | 来源探索与评估：候选源实测（连通性/中文覆盖/候选质量/下载成功率）→ 评估矩阵更新（docs/design/source-discovery.md）；合适的新源实现 provider 并注册；不合适的记录结论不落地；libgen/annas_archive/zlib 类版权敏感源不纳入（0.5 退役约束补记） | 「来源评估矩阵」含当前三源与已淘汰记录；至少 3 个候选源完成实测并有结论；保留类来源有 provider 实现与定向测试；新来源只搜解析下载地址，写入校验全走通用下载器。**进度**：首轮实测完成（archive 中文 CJK 策略落地、open_library 中文 0、gutenberg/OTL/libretexts 连通性、sciencep 证书、pressbooks 403）；第二轮「可达链路总结与评估」章节落盘（archive 中文为唯一可用中文下载链路）；**第三轮（2026-08-07）libgen.li 实测：中文翻译版书目全覆盖（菲赫金哥尔茨/卓里奇/陶哲轩/谢惠民/裴礼文/Apostol/Rudin 中译全命中），无 HTTP 直链（torrent/IPFS/ed2k，IPFS 网关不可达）；用户裁决 libgen 恢复为「发现专用 + 人工下载指引」来源（RETIRED_PROVIDERS 移除 libgen，文档边界约束已更新）** |
| QED-019 | Validation | 进行中 | [本轮门禁] 01 数学分析闭环（2026-08-07 按「数学课程选书要求」定稿）：**套一** Rudin《数学分析原理》中译 + 吉米多维奇《习题集》中译 + 费定晖解析（本地文件在 `D:\coding\dataset\textbooks\01_math_analysis\`，待复制入数据根 + 登记/验收）；**套二** 菲赫金哥尔茨《微积分学教程》3 卷（01-fikhtengolts-v1/v2/v3）+ 谢惠民《习题课讲义》上下（01-xiehuimin-v1/v2）——libgen.li 发现 → 人工下载 → 登记端点 → 验收；**套三** 陈纪修《数学分析》上下（01-chenjixiu-v1/v2，archive 自动下载）+ 习题答案（supplement）；**英文对照** Rudin EN（已有）+ Pólya（archive 可选）。（计划：根仓库 docs/plans/2026-08-textbook-download-round.md） | 01 至少 2 套教材+习题集人工验收通过（approved），多余候选 PASS 留痕；人工下载登记链路（register 端点）实测通过；下载链路结论回填 source-discovery 矩阵。**进度（2026-08-09）**：catalog 已定稿（01 共 14 目标，54 总；陈纪修拆 v1/v2/answers，title 保持条目级无卷号 + file_hint 双字）；测试全绿（145 passed + 3 skipped）+ ruff 全过；待 8901 重启（迁移 review_note）→ 存量清理 → evaluate 01 → 三态 → 下载/登记。 |
| QED-022 | Plan | 待开始 | [跨项目] 治理契约范本对齐：按根仓库 governance-contract.md 范本对齐守护契约测试（契约头六字段/守护面清单/编写约定）（需求方：QED-Engine REQ-023，设计：docs/design/governance-contract-alignment.md） | 守护类测试契约头六字段齐全（DesignRef 指向本仓库标准）；pytest 全绿 + ruff 全过；回执根仓库 REQ-023（提交号 + 测试输出）。 |
| QED-023 | Plan | 待开始 | [跨项目] 数据库设计确认：qt_* 表结构事实源确认与维护（需求方：QED-Engine REQ-026，2026-08-09 用户裁决根仓库只做指引和规划，设计：docs/design/database-schema-ownership.md） | tracker-service.md + db 迁移声明 qt_* 表清单事实源；确认后回执根仓库 REQ-026，根仓库 database-design.md 收尾为指引与规划。 |
| QED-024 | Plan | 待开始 | [跨项目] catalog target 套标记字段：`set_no` 可选字段（"1"~"4" 中文套 / "en" 英文对照套 / 留空无配套），math-qe.json 54 目标补齐，API 透出（需求方：QED-Engine REQ-028；2026-08-12 用户裁决：属 Plan 类别，方案确定后再进设计文档，既有 Draft 已归档至 docs/history/baselines/catalog-set-field.md） | math-qe.json 全 target 含 set_no（无配套留空）且 01 套归属与既有 note 一致；catalog API 响应含 set_no + schema 契约测试更新；回执根仓库 REQ-028（提交号 + 测试输出），根仓库前端两套判定联调验收。 |
| QED-025 | Defect | 待开始 | 提示文案过时：`src/qed_tracker/providers/books.py`（create_book_providers 退役来源报错分支）仍提示「从 [core].sources 或 QED_TRACKER_SOURCES 中删除」，二者均已退役（TOML 与 QED_TRACKER_* 时代产物，见 docs/design/tracker-service.md） | 提示改为指向根 `.env` 来源配置或移除来源名；定向测试覆盖退役来源报错文案；pytest 全绿 + ruff 全过。 |

规则：任务按类型分类（Plan / Defect / Validation / Candidate），状态只允许 `待开始 / 进行中 / 已完成 / 阻塞`；阻塞必须声明证据、恢复条件和责任位置。任务关闭时从本表移除并追加到[完成台账](completed.md)。
