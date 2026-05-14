# Book Hunter — 教材检索方案

## 来源

| 源 | 策略 | 方法 |
|----|------|------|
| **Library Genesis** | 主源，覆盖绝大多数数学教材 | httpx + BeautifulSoup 搜索 libgen.is，解析结果表 |

## 待检索课程

| # | 课程 | 英文教材 | 中文教材 | 习题集 |
|---|------|---------|---------|--------|
| 03 | 点集拓扑 | Munkres *Topology* | 熊金城《点集拓扑》 | 点集拓扑习题集 |
| 04 | 实分析 | Stein *Real Analysis* / Folland | 周民强《实变函数论》 | 周民强《实变函数解题指南》 |
| 05 | 复分析 | Stein *Complex Analysis* / Ahlfors | Ahlfors《复分析》中译本 | 方企勤《复变函数习题集》 |
| 06 | 泛函分析 | Stein *Functional Analysis* / Lax | 张恭庆《泛函分析》 | 泛函分析学习指导 |
| 07 | ODE | Tenenbaum *ODE* | 丁同仁《常微分方程》 | 常微分方程习题解 |
| 08 | PDE | Evans *PDE* | Evans《偏微分方程》中译本 | 书后习题 |
| 09 | 抽象代数 | Dummit & Foote / Aluffi | 冯克勤《近世代数引论》 | 书后习题 |
| 10 | QE 冲刺 | *Berkeley Problems* | 《伯克利数学问题集》影印版 | 同左 |

## 搜索顺序

```
每门课程:
  1. 中文教材 (zh)        → LibGen 搜索 → 交互确认 → 下载
  2. 英文教材 (en)        → LibGen 搜索 → 交互确认 → 下载
  3. 习题集 (zh_exercise) → LibGen 搜索 → 交互确认 → 下载
```

## 搜索逻辑

```
LibGenHunter.search("Munkres Topology")
  → GET https://libgen.is/search.php?req=Munkres+Topology
  → parse <table class="c"> rows
  → extract: title, author, year, language, size, download_url
  → filter: ext == "pdf"
  → sort: language=zh first, year desc
  → return list[dict]
```

## 下载逻辑

```
LibGenHunter.download(url, save_path)
  → GET download_url (follow redirects)
  → if redirected to library.lol or .pdf: download content
  → write to save_path
```
