# ⚠️ 大模型方向研究体系 — 后续部分

> **状态**: 📌 设计预留，工具已就绪但课程体系内容待定义
>
> 本文档记录大模型方向的技术选型与工具接口，具体采集目标留待后续讨论。

---

## 一、范围与边界

### 范围内（本期只做工具）

| 类型 | 工具 | 状态 |
|------|------|------|
| 官方文档下载 | `DocScraper` (PyTorch/scikit-learn/YOLO) | ✅ 代码就绪 |
| GitHub 项目跟踪 | `tools/github_downloader.py` | 🔧 本期新建 |
| arXiv 论文检索 | `PaperCollector` (cs.LG/cs.CL/cs.CV/cs.AI) | ✅ 代码就绪 |

### 待讨论（本期不执行）

- 需要跟踪哪些具体 GitHub 仓库？
- arXiv 论文的具体关键词/领域细分？
- 是否需要教程、课程笔记等资源？
- 是否需要视频（如 Stanford CS224n、Andrej Karpathy 系列）？
- 中文博客/知乎文章是否需要纳入？

## 二、工具接口设计

### GitHub Downloader (`app/tools/github_downloader.py`)

```python
class GitHubDownloader:
    """GitHub 项目文档/Release 跟踪工具"""

    def search_repo(self, repo_name: str) -> dict:
        """搜索仓库基本信息"""

    def download_release_docs(self, repo: str, save_dir: Path) -> list[Path]:
        """下载最新 Release 的文档/资产"""

    def clone_docs(self, repo: str, save_dir: Path) -> Path | None:
        """git clone --depth 1 仅文档目录"""

    def get_readme(self, repo: str) -> str:
        """获取仓库 README 内容"""
```

### arXiv Fetcher (`app/tools/arxiv_fetcher.py`)

从 `app/services/arxiv_client.py` 迁入，保持接口不变，新增 LLM 领域支持。

### DocScraper

保持现有接口，目标 URL 列表可从 `app/curricula/llm_research.py` 读取。

## 三、工具就绪后的采集流程

```
用户决定目标清单 → 填入 curricula/llm_research.py
  → 执行对应 script
  → 下载到 dataset/ 对应目录
  → 元数据入库
```

## 四、待办（后续讨论）

- [ ] 确定核心 GitHub 仓库列表（transformers, vllm, llama.cpp, ...）
- [ ] 确定 arXiv 论文跟踪策略（关键词？引用量阈值？）
- [ ] 确定是否需要中文教程/博客采集
- [ ] 确定是否需要视频字幕/笔记采集
