# 设计索引

状态：Current
最后更新：2026-08-04

- [下载与清单](acquisition-and-inventory.md)：来源协议、选择规则、可靠下载、资源 schema 和失败语义。
- [arXiv 论文智能发现](paper-discovery.md)：目标档案、百炼检索规划、评分、选择报告和显式下载。
- [Axiom-Flow 交接](axiom-handoff.md)：HTTP 接口、传输记录、幂等边界和失败处理。
- [服务接口设计](tracker-service.md)（Accepted，需求方 QED-Engine）：8901 API、后台任务与轮询、
  配置与数据布局迁移、qed 库 MySQL 资源登记（qt_resources）、基础书单 math-qe-v2 与批量下载。

用户命令查[日常操作](../guides/operations.md)，系统级边界查[系统总览](../architecture/system-overview.md)。跨项目契约（端口、环境变量、dataset 布局）以 QED-Engine 根仓库 `docs/` 为准。
