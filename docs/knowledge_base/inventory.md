# 书目/教材状态 (v0.5)

> 最后更新: 2026-05-23
> LibGen 状态: ✅ libgen.gl 直连可用（proxy 127.0.0.1:7897 已无效），其余镜像超时
> 下载方式: ads.php→CDN 分块续传（单 client + 10MB 分块，3MB/chunk）
> P0-P2 下载结果: 成功 3 本（冯克勤、学习指导、Stein复分析中译），7 本不在 LibGen，需手动从 Z-Library 获取
> 教材/习题集下载到 `textbook_dir` = `E:\qed\dataset\textbooks\`
> 其余数据（文档镜像、论文等）走 `dataset_dir` = `E:\qed\QED-Tracker\dataset\`

## 已有 PDF（32 个文件）

| 阶段 | 编号 | 课程 | 已有文件 | 置信度 |
|------|------|------|---------|--------|
| 地基 | 01 | 数学分析 | Rudin 中译本 3版 | A |
| | | | 吉米多维奇习题集 ×2 | A |
| 地基 | 02 | 线性代数 | Axler 中译本 | A |
| | | | 苏联习题集 | A |
| 地基 | 03 | 点集拓扑 | Munkres *Topology* 2nd | B |
| 核心 | 04 | 实分析 | 周民强《实变函数论》2版 | A |
| | | | 周民强《实变函数论》3版 | A |
| | | | 周民强《解题指南》×2 | A |
| | | | Stein *Real Analysis* | B |
| 核心 | 05 | 复分析 | Ahlfors 中译本 | A |
| | | | Stein *Complex Analysis* | B |
| | | | Stein《复分析》中译 | A |
| 核心 | 06 | 泛函分析 | Stein *Functional Analysis* | B |
| | | | Lax *Functional Analysis* (7MB) | B |
| | | | 泛函分析学习指导 | A |
| 广度 | 07 | ODE | Tenenbaum *ODE* | B |
| | | | 常微分方程习题解 | A |
| | | | 丁同仁参考答案 | C |
| 广度 | 08 | PDE | Evans *Partial Differential Equations* 2nd 华章影印版 (100MB) | B |
| 广度 | 09 | 抽象代数 | Dummit & Foote *Abstract Algebra* | B |
| | | | 冯克勤《近世代数引论》第4版 | A |
| 冲刺 | 10 | QE 冲刺 | 伯克利数学问题集中译本 | A |
| | | | *Berkeley Problems* 3rd | B |
| 专精 | 11 | 概率论 | Durrett *Probability: Theory and Examples* | B |
| | | | Billingsley *Probability and Measure* | B |
| 专精 | 12 | 随机过程 | Ross *Stochastic Processes* | B |
| | | | 随机过程2（北京大学出版社） | A |
| | | | Karatzas & Shreve *Brownian Motion* (3MB excerpt) | B |
| | | | Asmussen *Applied Probability and Queues* | B |
| 专精 | 13 | 高维概率论 | Vershynin *High-Dimensional Probability* | B |

## 课程状态总表

| 课程 | 中文教材 | 中文习题 | 英文教材 | 评价 |
|:---|:---:|:---:|:---:|:---|
| 01-数学分析 | Y | Y | N | 缺英文原版 |
| 02-线性代数 | Y | Y | N | 缺英文原版+金题精讲 |
| 03-点集拓扑 | N | N | Y | **缺熊金城** |
| 04-实分析 | Y | Y | Y | ✅ 齐全（可补Stein中译） |
| 05-复分析 | Y | N | Y | ✅ 有Ahlfors+Stein中译，缺方企勤习题集 |
| 06-泛函分析 | N | Y | Y | ✅ 有学习指导，**缺张恭庆中教材** |
| 07-常微分方程 | Y（仅参考答案） | Y | Y | ⚠️ 缺丁同仁原书+阿诺德 |
| 08-偏微分方程 | Y（华章英文影印） | — | N（438MB阻塞） | 现有版本可用，英原版需换源 |
| 09-抽象代数 | Y | — | Y | ✅ 有冯克勤，**缺Artin代数学** |
| 10-QE冲刺 | — | Y | Y | ✅ 齐全 |
| 11-概率论 | — | N | Y | 缺Song习题（次要） |
| 12-随机过程 | Y | Y（Asmussen英） | Y | ✅ 齐全 |
| 13-高维概率论 | — | — | Y | ✅ 齐全 |

## 补缺优先级

### P0 — 中文教材（优先补充）

| 编号 | 课程 | 缺失目标 | 当前状态 | 建议渠道 |
|------|------|---------|---------|---------|
| 03 | 点集拓扑 | 熊金城《点集拓扑学》 | ❌ 完全缺失，不在LibGen | Z-Library / 百度网盘 |
| 06 | 泛函分析 | 张恭庆《泛函分析》 | ❌ 完全缺失，不在LibGen | Z-Library / 百度网盘 |
| 09 | 抽象代数 | Artin《代数学》中译 | ❌ 完全缺失，不在LibGen | Z-Library / 百度网盘 |
| 07 | 常微分方程 | 丁同仁《常微分方程》原书 | ⚠️ 仅有参考答案，原书不在LibGen | Z-Library / 百度网盘 |
| 07 | 常微分方程 | 阿诺德《常微分方程》 | ❌ 完全缺失，不在LibGen | Z-Library / 百度网盘 |

### P1 — 中文习题集

| 编号 | 课程 | 缺失目标 | 当前状态 | 建议渠道 |
|------|------|---------|---------|---------|
| 05 | 复分析 | 方企勤《复变函数习题集》 | ❌ 完全缺失，不在LibGen | Z-Library / 百度网盘 |
| 02 | 线性代数 | 《线性代数：金题精讲》 | ❌ 完全缺失，不在LibGen | Z-Library / 百度网盘 |

### P2 — 补充中译本

| 编号 | 课程 | 缺失目标 | 当前状态 | 说明 |
|------|------|---------|---------|------|
| 04 | 实分析 | Stein《实分析》中译 | ❌ 不在LibGen | 已有周民强，非必需 |

### 阻塞 — 需换渠道（CDN超时）

| 编号 | 课程 | 缺失目标 | 大小 | 说明 |
|------|------|---------|------|------|
| 08 | PDE | Evans 英文原版 438MB | 438MB | CDN ~50MB上限，需其他下载方式 |
| 12 | 随机过程 | Karatzas & Shreve *Brownian Motion and Stochastic Calculus* | 78MB | CDN超时，已有3MB excerpt |

### 其他

| 编号 | 课程 | 缺失目标 | 当前状态 | 说明 |
|------|------|---------|---------|------|
| 11 | 概率论 | Song *Solutions Manual for Probability* | ❌ 未获取 | 习题解答，非必需 |

## 统计

| 指标 | 数量 |
|------|------|
| 已有 A 级（中文配对） | 15 |
| 已有 B 级（英文配对） | 15 |
| 已有 C 级（其他版本） | 1 |
| 已有小计（文件数） | **32** |
| P0 缺失（中文教材） | 5 |
| P1 缺失（中文习题） | 2 |
| P2 缺失（补充中译） | 1 |
| 阻塞（CDN超时） | 2 |
| 其他（非必需） | 1 |
| 缺失小计 | **11** |

## 计算机/LLM 资源清单 (v0.1)

> 采集策略与数学教材不同，CS/LLM 资源通过 DocScraper（官方文档）+ GitHub Collector + PaperCollector + LibGen 多渠道获取。

### Stage 1: 数据结构与算法

| 资源 | 类型 | 状态 |
|------|------|------|
| CLRS *Introduction to Algorithms* 4th | 教材 | ❌ 待采集 |
| Sedgewick *Algorithms* 4th | 教材 | ❌ 待采集 |
| LeetCode 分类专题 | 在线 | ✅ 可用 |

### Stage 2: 经典机器学习

| 资源 | 类型 | 状态 |
|------|------|------|
| ISLR (*Introduction to Statistical Learning*) | 教材 | ❌ 待采集 |
| ESL (*Elements of Statistical Learning*) | 教材 | ❌ 待采集 |
| sklearn 官方文档 | 文档 | ✅ 已镜像 (203 files, 17.8MB) |
| xgboost 官方文档 | 文档 | ✅ 已镜像 (276 files, 11MB) |

### Stage 3: 深度学习基础

| 资源 | 类型 | 状态 |
|------|------|------|
| d2l.ai (*Dive into Deep Learning*) | 教材+代码 | ❌ 待采集 |
| PyTorch 官方文档 2.12 | 文档 | ✅ 已镜像 (1549 files, 322MB) |
| YOLO (ultralytics) 文档 | 文档 | ✅ 已镜像 (1751 files, 534MB) |

### Stage 4-5: LLM 算法 + 应用

| 资源 | 类型 | 状态 |
|------|------|------|
| *Attention Is All You Need* | 论文 | ❌ 待采集 |
| GPT-4 Technical Report | 论文 | ❌ 待采集 |
| LLaMA Technical Report | 论文 | ❌ 待采集 |
| vllm-project/vllm | GitHub | ✅ 已跟踪 |
| pytorch/pytorch | GitHub | ✅ 已跟踪 |
| langchain-ai/langchain | GitHub | ⬜ 待添加 |
| run-llama/llama_index | GitHub | ⬜ 待添加 |
| Stanford CS224N / CS229 / CS231n | 视频 | ⬜ 待整理 |
| Jurafsky & Martin *SLP* | 教材 | ❌ 待采集 |

### CS/LLM 统计

| 指标 | 数量 |
|------|------|
| 已有（文档+GitHub） | 6 |
| 待采集（教材） | 5 |
| 待采集（论文） | 3 |
| 待跟踪（GitHub） | 2 |
| 待整理（视频） | 3 |
| **合计** | 6 ✅ / 13 ❌ |
