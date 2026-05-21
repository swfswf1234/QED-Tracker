# 计算机 — LLM 冲刺 v0.1

> Status: Draft
> Scope: AI 开发工程师 / 大模型应用工程师 / RAG 方向
> Curriculum: `app/curricula/cs_llm_sprint.py`

## 动机

QED-Tracker 已有的数学 QE 轨迹（突破朗道位垒）覆盖数学理论根基。计算机轨迹与之并行，以"冲刺"方式系统化掌握 AI 工程落地能力：

- **数学轨迹**：测度论 → 概率论 → 随机过程（理论根基）
- **计算机轨迹**：DS/Algo → 经典 ML → DL → LLM 算法 → LLM 应用（工程落地）

两者互补，构成完整的 AI 研究者/工程师知识体系。

## 五阶段路线

### Stage 1: 数据结构与算法 (快速回顾)

已有 10 年算法工程背景，本阶段以系统化和查漏补缺为主。

| 内容 | 资源 | 交付 |
|------|------|------|
| 基础数据结构（数组/链表/树/图/哈希） | CLRS, Sedgewick | 算法模板库 |
| 算法设计（DP/贪心/图论/网络流） | LeetCode 专题 | 分类刷题笔记 |
| 复杂度分析 | CLRS 第 3-4 章 | 复杂度速查表 |

### Stage 2: 经典机器学习 (sklearn + xgboost)

传统 ML 是 DL/LLM 的基础，也是工程中常用的基线方案。

| 内容 | 资源 | 交付 |
|------|------|------|
| 线性模型 / SVM / 树模型 / 集成学习 | ISLR, ESL | ML pipeline 模板 |
| xgboost 调参与原理 | xgboost 文档 (已镜像) | 调参笔记 |
| 完整 ML 项目流程 | Kaggle | 项目模板 |

### Stage 3: 深度学习基础 (PyTorch + OpenCV + YOLO)

DL 框架工程能力 + CV 基础，为 LLM 铺路。

| 内容 | 资源 | 交付 |
|------|------|------|
| PyTorch 核心 (autograd/DataLoader/训练循环) | PyTorch 文档 (已镜像), d2l.ai | 训练模板 |
| OpenCV 图像处理基础 | OpenCV 文档 | 图像处理管线 |
| YOLO 目标检测 | YOLO 文档 (已镜像) | 检测项目 |

### Stage 4: 大模型算法 (LLM 核心)

理解从 Transformer 到 GPT/LLaMA 的完整链路。

| 内容 | 资源 | 交付 |
|------|------|------|
| Attention / Transformer 架构 | Attention Is All You Need, 3B1B | 论文笔记 |
| GPT 系列 / LLaMA / 微调技术 | arXiv 论文, blog | 源码分析 |
| 推理优化 (量化/剪枝) | vllm, llama.cpp GitHub | 实验记录 |

### Stage 5: 大模型应用 (RAG + Agent)

核心目标：掌握 RAG 系统设计与 Agent 开发。

| 内容 | 资源 | 交付 |
|------|------|------|
| 向量数据库 / Embedding | 官方文档, GitHub | RAG pipeline |
| LangChain / LlamaIndex | 官方文档 | Agent 项目 |
| 检索增强 / 多模态 RAG | 论文, 工程实践 | 完整 RAG 系统 |

## 与现有基础设施的对接

| Stage | 采集工具 | 存储表 |
|-------|---------|--------|
| DS/Algo | LibGen (教材) | `textbooks` |
| ML 经典 | DocScraper (sklearn/xgboost 已镜像) | `official_docs` |
| DL 基础 | DocScraper (PyTorch/YOLO 已镜像) | `official_docs` |
| LLM 算法 | PaperCollector (arXiv cs.CL/cs.LG) | `papers` |
| LLM 应用 | GitHub Collector + RSS | `resources` |

## 当前状态

| Stage | 文档资源 | 代码资源 | 课程体系 |
|-------|---------|---------|---------|
| 1 DS/Algo | ❌ 待采集 | — | ✅ 已定义 (`cs01_ds_algo`) |
| 2 ML 经典 | ✅ sklearn/xgboost 已镜像 | — | ✅ 已定义 (`cs02_ml_classic`) |
| 3 DL 基础 | ✅ PyTorch/YOLO 已镜像 | — | ✅ 已定义 (`cs03_dl_foundation`) |
| 4 LLM 算法 | ❌ 待采集 | ✅ vllm 已跟踪 | ✅ 已定义 (`cs04_llm_algorithm`) |
| 5 LLM 应用 | ❌ 待采集 | ⬜ 待跟踪 | ✅ 已定义 (`cs05_llm_application`) |

## 置信度定义

数学 QE 轨迹使用 A/B/C 置信度体系（中文/英文/其他）。计算机轨迹的资源类型不同，重新定义：

| 等级 | 含义 |
|------|------|
| **Source** | 官方/教材级（官方文档经典教材） |
| **Reference** | 社区高质量参考（GitHub 仓库、博客、视频） |
| **Supplement** | 辅助材料（笔记、习题、讨论） |
