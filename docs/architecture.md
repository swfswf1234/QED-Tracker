# 系统架构 v0.2

> QED-Tracker 重构版架构：采集层 → 工具层 → 仓储层 → 数据库抽象层

## 全景

```mermaid
graph TB
    subgraph "配置"
        CFG[setting.ini] --> CORE[app/core/config.py]
    end

    subgraph "课程体系"
        MATH[app/curricula/math_qe.py]
        LLM[app/curricula/llm_research.py]
    end

    subgraph "工具层 app/tools/"
        LOG[tools/logger.py]
        LD[tools/libgen_downloader.py]
        AD[tools/annas_downloader.py]
        AF[tools/arxiv_fetcher.py]
        GD[tools/github_downloader.py]
        WM[tools/wget_mirror.py<br/>wget --mirror via WSL]
    end

    subgraph "采集层 app/collectors/"
        TH[textbook_hunter.py] --> LD & AD
        TH --> MATH
        PC[paper_collector.py] --> AF
        DS[doc_scraper.py] --> WM
    end

    subgraph "仓储层 app/repository/"
        REPO[BaseRepository[T]]
        TR[textbook_repo.py]
        PR[paper_repo.py]
        DR[doc_repo.py]
        RR[resource_repo.py]
    end

    subgraph "数据库抽象层 app/db/"
        BASE[db/base.py: 抽象接口]
        MYSQL[db/mysql.py: MySQL 适配器]
        PG[db/postgresql.py: PostgreSQL 适配器]
        SESS[db/session.py: 连接池管理]
        INIT[db/init_db.py: 建库建表]
    end

    subgraph "CLI 入口 scripts/"
        HT[scripts/hunt_textbooks.py]
        HP[scripts/hunt_papers.py]
        HD[scripts/hunt_docs.py]
        SCAN[scripts/scan_dataset.py]
        IDB[scripts/init_db.py]
    end

    HT --> TH
    HP --> PC
    HD --> DS
    SCAN --> REPO
    IDB --> INIT

    TH & PC & DS --> REPO
    REPO --> BASE
    BASE --> MYSQL
    BASE --> PG
```

## 模块职责

| 层 | 模块 | 文件 | 职责 |
|----|------|------|------|
| **配置** | Config | `app/core/config.py` | 从 setting.ini 读取配置，多库引擎选择 |
| **课程体系** | Curriculum Base | `app/curricula/base.py` | 课程基类 + 置信度枚举 (A/B/C) |
| | Math QE | `app/curricula/math_qe.py` | 突破朗道位垒 (10 门课 + 目标教材) |
| | LLM Research | `app/curricula/llm_research.py` | ⚠️ 大模型方向 (后续部分) |
| **工具层** | Logger | `app/tools/logger.py` | 集中日志配置 |
| | LibGen Downloader | `app/tools/libgen_downloader.py` | 多镜像搜索 + Range 分块续传 |
| | Anna's Downloader | `app/tools/annas_downloader.py` | Anna's Archive 备选源 |
| | arXiv Fetcher | `app/tools/arxiv_fetcher.py` | arXiv API 封装 (从 services 迁入) |
| | GitHub Downloader | `app/tools/github_downloader.py` | GitHub release/docs 跟踪 |
| | Wget Mirror | `app/tools/wget_mirror.py` | wget --mirror 全站镜像 (通过 WSL 调用) |
| | Video Tracker | `app/tools/video_tracker.py` | 📌 占位: 视频/博客跟踪 |
| **采集层** | TextbookHunter | `app/collectors/textbook_hunter.py` | 教材采集编排: 搜索→匹配置信度→下载→入库 |
| | PaperCollector | `app/collectors/paper_collector.py` | arXiv 论文检索: 搜索→交互→下载→入库 |
| | DocScraper | `app/collectors/doc_scraper.py` | 官方文档镜像: wget --mirror via WSL, 含 CSS/JS/字体 |
| **仓储层** | BaseRepository[T] | `app/repository/__init__.py` | 泛型 CRUD 基类 |
| | TextbookRepo | `app/repository/textbook_repo.py` | 教材仓储 (by_course, by_path) |
| | PaperRepo | `app/repository/paper_repo.py` | 论文仓储 (by_arxiv_id) |
| | OfficialDocRepo | `app/repository/doc_repo.py` | 文档仓储 (by_name) |
| | ResourceRepo | `app/repository/resource_repo.py` | 资源仓储 (by_type) |
| **DB 抽象层** | Base Interface | `app/db/base.py` | 抽象数据库接口 (connect/execute/close) |
| | MySQL | `app/db/mysql.py` | MySQL 适配器 |
| | PostgreSQL | `app/db/postgresql.py` | PostgreSQL 适配器 (从 core/database.py 迁入) |
| | Session | `app/db/session.py` | 连接池管理 |
| | Init DB | `app/db/init_db.py` | 建库建表逻辑 (从 scripts/ 迁入) |
| **CLI** | hunt_textbooks | `scripts/hunt_textbooks.py` | 教材检索入口 |
| | hunt_papers | `scripts/hunt_papers.py` | 论文检索入口 |
| | hunt_docs | `scripts/hunt_docs.py` | 文档爬取入口 |
| | scan_dataset | `scripts/scan_dataset.py` | 扫描已有文件入库 |
| | init_db | `scripts/init_db.py` | 快速建库 (转发 app/db/init_db.py) |

## 数据流

```
用户 → CLI/API → Collector → Tool(下载/搜索) → 本地 dataset/
                    ↓
              课程体系(置信度匹配)
                    ↓
              Repository(CRUD)
                    ↓
          DB 抽象层 → MySQL / PostgreSQL
```

## 关键设计原则

1. **工具层与采集层分离**: 具体下载/搜索逻辑下沉到 tools/，collector 只做编排
2. **DB 抽象层可选**: 应用可运行无数据库模式（`--no-db`），仅操作本地文件
3. **课程体系驱动**: 采集什么、怎么匹配置信度由 curricula/ 定义，collector 不硬编码
4. **多引擎透明**: repository 层不感知底层是 MySQL 还是 PostgreSQL
