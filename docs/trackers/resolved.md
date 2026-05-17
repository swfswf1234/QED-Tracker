# 已完成任务

## v0.1 完成项

| ID | 描述 | 完成日期 |
|----|------|----------|
| T-001 | 项目重构：精简为采集器 + 索引引擎 | 2026-05-12 |
| T-002 | 连接池 + BaseRepository 泛型 CRUD | 2026-05-12 |
| T-003 | 4 表 ORM 模型 (textbook/paper/official_doc/resource) | 2026-05-12 |
| T-004 | PaperCollector: arXiv 搜索 + 交互确认 + 下载 + 入库 | 2026-05-12 |
| T-005 | TextbookHunter: LibGen 搜索 + 交互确认 + 下载 + 入库 | 2026-05-12 |
| T-006 | DocScraper: wget --mirror 官方文档爬取 + 入库 | 2026-05-12 |
| T-007 | init_db.py 数据库初始化 (建库+建表) | 2026-05-12 |
| T-008 | scan_dataset.py 扫描已有文件入库 | 2026-05-12 |
| T-009 | 已有 5 本教材 PDF 归位 | 2026-05-12 |
| T-010 | 删除旧代码 (src/test/schemas/旧 services) | 2026-05-12 |
| T-011 | 文档体系搭建 (README/arch/schema/trackers/kb) | 2026-05-12 |
| T-012 | LibGen Range 分块续传下载 | 2026-05-16 |
| T-013 | 406MB 数据集入库 git | 2026-05-16 |
| T-014 | 教材下载 Phase 1 (03-10, 成功 17 个文件) | 2026-05-16 |

## 历史遗留解决

| ID | 说明 | 解决方式 |
|----|------|---------|
| T-102 (旧) | LibGen 镜像不可访问 | 镜像列表更新为 libgen.li/vg/la/bz/gl, 添加 Annas Archive 备用源 |

## v0.2 新增完成

| ID | 描述 | 完成日期 |
|----|------|----------|
| T-101~116 | 第一阶段架构重构全部完成（数据库抽象层/课程体系/工具层/采集层/仓储层） | 2026-05-16 |
| T-203.1 | 官方文档镜像工具: `app/tools/wget_mirror.py` — wget --mirror via WSL | 2026-05-17 |
| T-203.2 | DocScraper 改为 wget 镜像方案, DOC_SOURCES 新增 xgboost | 2026-05-17 |
| T-203.3 | xgboost 文档镜像验证 (125 HTML + 47 PNG + 9 CSS + 5 JS, 11.21 MB) | 2026-05-17 |
