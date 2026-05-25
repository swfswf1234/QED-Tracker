# Scholar-Tracker v1 → v0.2

> QED-Tracker 设计文档：只做检索、分类、索引，不处理内容。
>
> 架构重构后：工具层下沉 → `app/tools/`，课程体系独立 → `app/curricula/`，多库支持 → `app/db/`

## 检索清单（突破朗道位垒）

| 编号 | 课程 | 目标教材 | 置信度 | 状态 |
|------|------|---------|--------|------|
| 01 | 数学分析 | Rudin《数学分析原理》中译本 | A | ✅ |
| | | Rudin *Principles of Mathematical Analysis* | B | ✅ |
| | | 吉米多维奇习题集 | A | ✅ |
| 02 | 线性代数 | Axler《线性代数应该这样学》中译本 | A | ✅ |
| | | Axler *Linear Algebra Done Right* | B | ✅ |
| | | 苏联习题集 | A | ✅ |
| 03 | 点集拓扑 | 熊金城《点集拓扑学》 | A | ❌ 待检索 |
| | | Munkres *Topology* 2nd ed | B | ✅ |
| 04 | 实分析 | 周民强《实变函数论》第2版+第3版 | A | ✅ |
| | | 周民强《实变函数解题指南》 | A | ✅ |
| | | Stein *Real Analysis* | B | ❌ 待检索 |
| 05 | 复分析 | Ahlfors《复分析》中译本 | A | ✅ |
| | | Stein *Complex Analysis* | B | ❌ 待检索 |
| | | 方企勤《复变函数习题集》 | A | ❌ 待检索 |
| 06 | 泛函分析 | 张恭庆《泛函分析》 | A | ❌ 待检索 |
| | | Stein *Functional Analysis* | B | ✅ |
| | | 泛函分析学习指导 | A | ❌ 待检索 |
| 07 | ODE | 丁同仁《常微分方程》 | A | ❌ 待检索 |
| | | Tenenbaum *ODE* | B | ✅ |
| | | 常微分方程习题解 | A | ✅ |
| 08 | PDE | Evans《偏微分方程》中译本 | A | ❌ 待检索 |
| | | Evans *Partial Differential Equations* | B | ❌ 待检索 |
| 09 | 抽象代数 | 冯克勤《近世代数引论》 | A | ❌ 待检索 |
| | | Dummit & Foote *Abstract Algebra* | B | ✅ |
| 10 | QE 冲刺 | 《伯克利数学问题集》中译本 | A | ✅ |
| | | *Berkeley Problems in Mathematics* 3rd | B | ✅ |

### 置信度定义

| 等级 | 含义 |
|------|------|
| **A** | 完全配对的中文版教材（目标教材的中译本或中文原著） |
| **B** | 完全配对的英文版教材（目标原版教材） |
| **C** | 其他版本（不同版次、不同作者但同主题、同类习题集） |

## 三大采集器（重构后）

### TextbookHunter — 教材 PDF

```
课程体系(math_qe.py) → 搜索(中文→英文→习题集)
  → LibGenDownloader.search() / AnnaDownloader.search()  (tools/)
  → 结果展示(含置信度标记) → 交互/自动选择
  → LibGenDownloader.download()  (Range 分块续传)
  → {dataset_dir}/textbooks/{course}/
  → 入库: textbooks 表
```

### PaperCollector — arXiv 论文

```
arXiv 分类 → arxiv_fetcher.search()  (tools/)
  → 逐篇展示标题+作者+摘要+标签 → [Y/n] 确认
  → httpx 下载 PDF → dataset/papers/{year}/
  → 入库: papers 表 (幂等: arxiv_id UNIQUE)
```

### DocScraper — 官方文档

```
文档名 → wget --mirror --convert-links --page-requisites
  → dataset/official_docs/{name}/
  → 入库: official_docs 表
```

## 数据集布局

```
dataset/
├── textbooks/
│   ├── 01_math_analysis/       # ✅ Rudin + 吉米多维奇
│   ├── 02_linear_algebra/      # ✅ Axler + 苏联习题集
│   ├── 03_topology/            # ✅ Munkres (熊金城待补)
│   ├── 04_real_analysis/       # ✅ 周民强 (Stein待补)
│   ├── 05_complex_analysis/    # ✅ Ahlfors (Stein+习题集待补)
│   ├── 06_functional_analysis/ # ✅ Stein (张恭庆待补)
│   ├── 07_ode/                 # ✅ Tenenbaum + 习题解
│   ├── 08_pde/                 # ❌ 空
│   ├── 09_abstract_algebra/    # ✅ Dummit & Foote (冯克勤待补)
│   └── 10_qe_prep/             # ✅ Berkeley 问题集
├── papers/
│   └── {year}/                 # ❌ 待采集
└── official_docs/
    ├── pytorch/                 # ❌ 待爬取
    ├── scikit_learn/            # ❌ 待爬取
    └── yolo/                    # ❌ 待爬取
```
