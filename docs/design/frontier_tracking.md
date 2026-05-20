# 前沿跟踪配置 v0.1

> QED-Tracker 设计文档：定义前沿数学/算法资讯源及精选列表，用于自动采集和跟踪。
> 来源：`docs/discuss/add_book_and_source.md` 文章/图文与 RSS 部分（视频待定）

## RSS 源

| 源 | URL | 类型 | 用途 |
|---|-----|------|------|
| Quanta Magazine - Mathematics | `https://www.quantamagazine.org/feed/` | RSS | 前沿数学突破报道 |
| Terence Tao Blog | `https://terrytao.wordpress.com/feed/` | RSS/Atom | 当代顶尖数学家公开思考 |

## 精选文章清单

### Quanta Magazine 数学专栏

| # | 文章 | 主题 | 推荐理由 |
|---|------|------|---------|
| 1 | *The Random Geometry at the Heart of Physics* | 随机几何、物理与概率论核心 | 与概率论/测度方向强相关 |
| 2 | *Mathematicians Prove 2D Version of Quantum Gravity Conjecture* | PDE、几何拓扑、量子引力前沿 | 前沿应用案例 |

### Terence Tao 博客

| # | 文章 | 主题 | 推荐理由 |
|---|------|------|---------|
| 1 | *Simons Lectures: The cosmic distance ladder* | 测度与调和分析 | 讲座笔记，与测度论直接相关 |
| 2 | *Discrete random matrices* | 高维概率论、随机矩阵 | 与高维概率论/Vershynin 互补 |

## 集成建议

### 采集方案

```
RSS/API 轮询 → 每日新文章检测 → 元数据入库(resources表)
  → 正文缓存(可选) → LLM 摘要生成 → 推送给用户
```

### 采集器实现

已实现 `app/tools/rss_tracker.py`，两者均为 RSS XML 解析：
- **Quanta**: WordPress RSS feed
- **Tao Blog**: WordPress RSS feed（标准 Atom/RSS 并存）

### 当前状态

- RSS 采集器：✅ 已实现 `app/tools/rss_tracker.py`
- 编排/入库：✅ 已实现 `app/collectors/frontier_collector.py`
- CLI 入口：✅ 已实现 `scripts/hunt_frontier.py`
- LLM 摘要：🔲 预留（`--summary`）

## 数字化流程建议

来自 `add_book_and_source.md` 的建议：

> 将 **Rick Durrett *Probability: Theory and Examples* (第5版) 第4章: Martingales** 作为 MinerU 管道的核心测试语料。该章包含 sigma-代数流 $\mathcal{F}_n$、鞅变换等测度论符号，能有效检验 MinerU 对复杂数学 LaTeX 的还原能力。

若 MinerU 流程已就绪，可将其加入测试用例。
