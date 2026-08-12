# 设计索引

状态：Current
最后更新：2026-08-12

- [下载与清单](acquisition-and-inventory.md)：来源协议、选择规则、可靠下载、资源 schema 和失败语义。
- [arXiv 论文智能发现](paper-discovery.md)：目标档案、百炼检索规划、评分、选择报告和显式下载。
- [Axiom-Flow 交接](axiom-handoff.md)：HTTP 接口、传输记录、幂等边界和失败处理。
- [服务接口设计](tracker-service.md)（Accepted，需求方 QED-Engine）：8901 API、后台任务与轮询、
  配置与数据布局迁移、qed 库 MySQL 资源登记（qt_resources）、基础书单 math-qe-v2 与批量下载。
- [来源探索与评估](source-discovery.md)：发现合适下载路径、淘汰不合适路径的目标、评估矩阵、
  合规边界（libgen 类不纳入）与探索流程。
- [人工评审优化](review-round-dedup.md)（Accepted，需求方 QED-Engine）：evaluate 同源去重、
  file_hint 例外与 review_note 人工评审留痕。
- [治理契约范本对齐](governance-contract-alignment.md)（Accepted，QED-022）：守护契约测试的
  契约头六字段、守护面清单与编写约定对齐根仓库范本。
- [qt_* 表结构事实源](database-schema-ownership.md)（Accepted，QED-023）：qed 库 `qt_*` 表
  清单与结构由本仓库确认并维护。
- [套标记字段 set_no](catalog-set-field.md)（Draft 待评审，QED-024）：catalog target 增加
  可选 `set_no` 字段支持按「套」展示课程完成判定。

用户命令查[日常操作](../guides/operations.md)，系统级边界查[系统总览](../architecture/system-overview.md)。跨项目契约（端口、环境变量、dataset 布局）以 QED-Engine 根仓库 `docs/` 为准。
