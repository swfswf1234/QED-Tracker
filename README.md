# QED-Tracker v0.1

> **QED-Engine Part 1** — 面向数学博士资格考试 (QE) 的资源检索与分类引擎。
> 按《突破朗道位垒》课程目录，检索教材 PDF、arXiv 论文、官方文档，分门别类存入本地 dataset，建立 PostgreSQL 索引。

## 核心功能

| 功能 | 说明 |
|------|------|
| **教材检索** | 通过 Library Genesis 搜索目标教材 PDF，交互确认后下载到 `dataset/textbooks/{course}/` |
| **论文检索** | 通过 arXiv API 按数学分类 (math.CA/FA/AP/CV) 搜索，逐篇确认后下载到 `dataset/papers/{year}/` |
| **文档爬取** | 通过 wget --mirror 爬取官方文档 (PyTorch/scikit-learn/YOLO)，保留完整 HTML 结构 |
| **数据库索引** | 所有资源元数据存入 PostgreSQL 4 张表：textbooks / papers / official_docs / resources |

## 快速开始

```bash
# 1. 复制配置模板
cp setting.example.ini setting.ini
# 编辑 setting.ini: 填写 PostgreSQL 密码、代理地址（如需要）

# 2. 安装依赖
pip install -r requirements.txt

# 3. 初始化数据库
python scripts/init_db.py --create-db

# 4. 扫描已有文件入库
python scripts/scan_dataset.py

# 5. 检索教材 (交互式下载 LibGen)
python scripts/hunt_textbooks.py
# 指定单门课程: python scripts/hunt_textbooks.py --course 03
# 跳过数据库:   python scripts/hunt_textbooks.py --no-db

# 6. 检索论文
python scripts/hunt_papers.py --domain math.CA --max 10

# 7. 爬取官方文档
python scripts/hunt_docs.py --name pytorch
```

> **代理配置**：如果无法直连 LibGen，在 `setting.ini` 的 `[Proxy]` 段落配置 HTTP 代理池地址（如 Clash/V2Ray 默认端口 7890）。

## 项目结构

```
QED-Tracker/
├── app/
│   ├── collectors/        # 采集器 (教材/论文/文档)
│   ├── core/              # 配置 + 数据库连接
│   ├── models/            # ORM 模型 (4 表)
│   ├── repository/        # 仓储层 (CRUD)
│   └── services/          # arXiv API 客户端
├── scripts/               # CLI 入口 (5 个)
├── docs/                  # 设计文档
├── dataset/               # 资源存储 (.gitignore)
│   ├── textbooks/         # 教材 PDF (按课程编号)
│   ├── papers/            # 论文 PDF (按年份)
│   └── official_docs/     # 官方文档 (HTML 结构)
├── setting.ini            # 本地配置 (.gitignore)
└── setting.example.ini    # 配置模板
```

## 数据集

已有文件位于 `dataset/textbooks/`：
- `01_math_analysis/` — Rudin 中译本 + 吉米多维奇习题集 (3 PDF)
- `02_linear_algebra/` — Axler 中译本 + 苏联习题集 (2 PDF)

其余课程教材和论文等待检索。
