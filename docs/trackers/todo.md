# 待办列表

状态：Current
最后更新：2026-08-20

| ID | 类型 | 状态 | 事项 | 成功标准 |
| --- | --- | --- | --- | --- |
| QED-010 | Plan | 待开始 | [跨项目] CLI 转 HTTP 客户端 + 基于真实 8901 服务的冒烟测试（需求方：QED-Engine，设计：docs/design/tracker-service.md；**承接 QED-005**（真实百炼与 arXiv 论文链路冒烟：papers recommend → selections download 下载临时 PDF，2026-08-20 用户裁决并入）） | `qed-tracker` 命令经 8901 完成任务；启动 → 建任务 → 轮询 → 校验文件落位全链路冒烟通过；`--no-wait` 输出 task_id；论文链路真实冒烟（推荐 → 同一报告下载临时 PDF）。 |
| QED-011 | Validation | 待开始 | 重复下载链路验证（用户约定在 QED-008~010 冒烟后执行） | 同一资源二次下载返回既有资源记录，不产生重复文件，任务幂等。 |
| QED-014 | Validation | 待开始 | [跨项目] 联调冒烟与回执：真实 8901 全链路（评估→确认→下载→验收/删除→登记→qed CLI/8903 前端展示）（设计：docs/design/tracker-service.md；承接 QED-017 全链路覆盖、QED-020 存量清理 8901 重启实测、QED-021 真实 evaluate 01 冒烟、**QED-023 回执根仓库 REQ-026**；原计划 2026-08-service-and-book-download 已归档至 docs/history/baselines/） | 8901 服务 + qed CLI + QED-Engine 下载工作台数据贯通；根仓库 todo REQ-004/REQ-011/REQ-013/REQ-014/**REQ-026** 收到回执。 |
| QED-022 | Plan | 待开始 | [跨项目] 治理契约范本对齐：按根仓库 governance-contract.md 范本对齐守护契约测试（契约头六字段/守护面清单/编写约定）（需求方：QED-Engine REQ-023，设计：docs/design/governance-contract-alignment.md） | 守护类测试契约头六字段齐全（DesignRef 指向本仓库标准）；pytest 全绿 + ruff 全过；回执根仓库 REQ-023（提交号 + 测试输出）。 |
| QED-024 | Plan | 待开始 | [跨项目] catalog target 套标记字段：`set_no` 可选字段（"1"~"4" 中文套 / "en" 英文对照套 / 留空无配套），math-qe.json 54 目标补齐，API 透出（需求方：QED-Engine REQ-028；2026-08-12 用户裁决：属 Plan 类别，方案确定后再进设计文档，既有 Draft 已归档至 docs/history/baselines/catalog-set-field.md） | math-qe.json 全 target 含 set_no（无配套留空）且 01 套归属与既有 note 一致；catalog API 响应含 set_no + schema 契约测试更新；回执根仓库 REQ-028（提交号 + 测试输出），根仓库前端两套判定联调验收。 |
| QED-026 | Plan | 进行中 | 主链路第一版（CLI 跑通 3 门基础课验证）：课程体系加载（courses/math.json + courses list/show）、教材条目五要素存储（meta/main-line/ + 状态机）、LLM 预填评价（参照顶尖大学 + 防总评高校准）、mainline new/review/download/verify/approve/reject/channels、验收后复制+登记同步移交根仓库 dataset/qed-tracker/、乱码修复与存量清理（设计：docs/design/main-line-curriculum.md，计划：../plans/2026-08-main-line-curriculum.md） | 00/01/02 三门课程闭环：courses list 显示 14 门；每门生成教材条目（LLM 预填可评审）；review 定稿；download/verify/approve 移交根仓库；channels 汇总渠道有效性；全量门禁全绿。**进度（2026-08-12）**：实现完成——courses/mainline 全命令 + 五要素存储/状态机 + LLM 预填 + 渠道记录 + approve 移交 + UTF-8 解码修复（提交链 948fa88~ea905b9，全量 221 passed + 3 skipped + ruff）；待人工闭环验证（配置 API_KEY → mainline new → review → download → approve 移交根仓库，密钥已配置可执行）。**已知限制**（2026-08-12 评审登记，见设计文档「已知限制」）：版本要素 CLI 闭环、人工下载 register 闭环、防总评高单本对比不可执行、rejected 重试无 CLI 出口。**2026-08-13 更新**：01 资源链路人工闭环已验证（evaluate → 三态 → register → approve → 移交根仓库，见 QED-019 台账）；mainline CLI 人工闭环验证并入三表重构轮（QED-028/029 迁移后在新模型重演 00/01/02，旧双轨由用户裁决统一为三表）。 |

规则：任务按类型分类（Plan / Defect / Validation / Candidate），状态只允许 `待开始 / 进行中 / 已完成 / 阻塞`；阻塞必须声明证据、恢复条件和责任位置。任务关闭时从本表移除并追加到[完成台账](completed.md)。
