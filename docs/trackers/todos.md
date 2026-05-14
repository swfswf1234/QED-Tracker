# QED-Tracker 任务清单

## v0.1 已完成

| ID | 类型 | 描述 | 状态 |
|----|------|------|------|
| T-001 | 架构 | 项目重构：精简为采集器 + 索引引擎 | ✅ |
| T-002 | 数据库 | 连接池 + BaseRepository 泛型 CRUD | ✅ |
| T-003 | 数据库 | 4 表 ORM 模型 (textbook/paper/official_doc/resource) | ✅ |
| T-004 | 采集器 | PaperCollector: arXiv 搜索 + 交互确认 + 下载 + 入库 | ✅ |
| T-005 | 采集器 | TextbookHunter: LibGen 搜索 + 交互确认 + 下载 + 入库 | ✅ |
| T-006 | 采集器 | DocScraper: wget --mirror 官方文档爬取 + 入库 | ✅ |
| T-007 | 脚本 | init_db.py 数据库初始化 (建库+建表) | ✅ |
| T-008 | 脚本 | scan_dataset.py 扫描已有文件入库 | ✅ |
| T-009 | 数据 | 已有 5 本教材 PDF 归位 | ✅ |
| T-010 | 清理 | 删除旧代码 (src/test/schemas/旧 services) | ✅ |
| T-011 | 文档 | 全部文档重写 (README/arch/schema/trackers/kb) | ✅ |

## 后续待办

| ID | 类型 | 描述 | 优先级 |
|----|------|------|--------|
| T-101 | 执行 | 检索教材 03-10 (中文教材 + 英文教材 + 习题集) | P1 |
| T-102 | 执行 | 按领域检索 arXiv 论文 | P2 |
| T-103 | 执行 | 爬取 PyTorch/scikit-learn/YOLO 文档 | P2 |
| T-104 | 功能 | resources 表对接 (博客/视频/项目链接) | P3 |
| T-105 | 功能 | GitHub 项目检索 (入 resources 表) | P3 |

## 已解决

| ID | 说明 | 解决方式 |
|----|------|---------|
| T-102 (旧) | LibGen 镜像不可访问 | 镜像列表更新为 libgen.li/vg/la/bz/gl, 添加 Annas Archive 备用源 |
