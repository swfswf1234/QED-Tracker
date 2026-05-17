# QED-Tracker v0.2

> **QED-Engine Part 1** — 面向数学博士资格考试 (QE) 与 AI 大模型研究的资源检索与分类引擎。
> 按《突破朗道位垒》课程目录，检索教材 PDF、arXiv 论文、官方文档，分门别类存入本地 dataset，建立 MySQL/PostgreSQL 索引。

## 架构总览

```
app/
├── core/          配置加载 (setting.ini)
├── db/            数据库抽象层 (MySQL + PostgreSQL)
├── models/        ORM 模型 (4 表)
├── repository/    仓储层 (泛型 CRUD)
├── curricula/     课程体系定义 (含置信度 A/B/C)
├── collectors/    采集编排层
├── tools/         工具集合 (LibGen/GitHub/arXiv/Logger)
└── main.py        FastAPI 入口
```

## 核心功能

| 功能 | 说明 | 状态 |
|------|------|------|
| **教材检索** | LibGen 多镜像搜索 + Anna's Archive 备用 → 交互/自动下载 | ✅ v0.1 |
| **论文检索** | arXiv API 按数学/LLM 分类搜索 → 下载 | ✅ v0.1 |
| **文档爬取** | wget --mirror 爬取官方文档 | ✅ v0.1 |
| **数据库索引** | MySQL (本机) / PostgreSQL (可选) 双引擎 | ✅ v0.2 |
| **GitHub 跟踪** | 项目 release/docs 采集 | ✅ v0.2 |
| **课程体系** | 置信度 A/B/C 标记 + 可扩展多体系 | ✅ v0.2 |

## 快速开始

```bash
# 1. 复制配置并修改
cp setting.example.ini setting.ini

# 2. 安装依赖
pip install -r requirements.txt

# 3. 修改 setting.ini (数据库/代理配置)
# 4. 初始化数据库
python scripts/init_db.py --create-db

# 5. 扫描已有文件入库
python scripts/scan_dataset.py

# 6. 检索教材
python scripts/hunt_textbooks.py              # 交互式遍历全部
python scripts/hunt_textbooks.py --auto       # 自动模式

# 7. 检索论文
python scripts/hunt_papers.py --domain math.CA --max 10

# 8. 爬取官方文档
python scripts/hunt_docs.py --name pytorch
```

## 课程体系

| 体系 | 文件 | 状态 |
|------|------|------|
| **《突破朗道位垒》** — 数学研究基础 (10 门课) | `app/curricula/math_qe.py` | ✅ 活跃 |
| **大模型方向** — LLM 研究资源 | `app/curricula/llm_research.py` | ⚠️ 后续部分 |

### 置信度定义

| 等级 | 含义 |
|------|------|
| **A** | 完全配对的中文版教材 |
| **B** | 完全配对的英文版教材 |
| **C** | 其他版本（不同版次/同主题） |

## 数据集

已有文件位于 `dataset/textbooks/`：

| 课程 | 教材 | 置信度 |
|------|------|--------|
| 01 数学分析 | Rudin 中译本 + 吉米多维奇习题集 | A |
| 02 线性代数 | Axler 中译本 + 苏联习题集 | A |
| 03 点集拓扑 | Munkres *Topology* | B (熊金城待补) |
| 04 实分析 | 周民强《实变函数论》+ 解题指南 | A (Stein 待补) |
| 05 复分析 | Ahlfors 中译本 | A (Stein 待补) |
| 06 泛函分析 | Stein *Functional Analysis* | B (张恭庆待补) |
| 07 ODE | Tenenbaum + 习题解 | B, A |
| 08 PDE | — | ❌ |
| 09 抽象代数 | Dummit & Foote | B (冯克勤待补) |
| 10 QE 冲刺 | 伯克利问题集中英 | A, B |

## 项目结构

```
QED-Tracker/
├── app/
│   ├── core/             配置 + 数据库连接
│   ├── db/               多库抽象层 (MySQL/PostgreSQL)
│   ├── models/           ORM 模型
│   ├── repository/       仓储层
│   ├── curricula/        课程体系定义
│   ├── collectors/       采集器
│   ├── tools/            工具集合
│   └── main.py           FastAPI 入口
├── scripts/              CLI 入口 (5 个)
├── docs/                 设计文档
├── dataset/              资源存储 (.gitignore)
└── setting.example.ini   配置模板 (复制为 setting.ini 后修改)
```

## 运行环境

- **Conda 环境**: `QED_env`
- **Python**: 3.12
- **数据库**: MySQL 8.0+ (本机) / PostgreSQL 16+ (可选)
- **依赖**: `pip install -r requirements.txt`
- **代理配置**: `setting.ini` 的 `[Proxy]` 段落

## 文档

详见 `docs/` 目录：

| 文档 | 说明 |
|------|------|
| `architecture.md` | 系统架构 + Mermaid 全景图 |
| `database.md` | 多库设计 + 表结构 |
| `design/scholar_tracker_v1.md` | 采集器 + 置信度矩阵 |
| `design/book_hunter_sources.md` | LibGen 下载链路详述 |
| `design/llm_research_plan.md` | ⚠️ 大模型方向设计预留 |
| `trackers/todos.md` | 当前任务清单 |
| `knowledge_base/inventory.md` | 书目状态完整清单 |
