# Book Hunter — 教材检索方案 v0.2

## 检索链路

```mermaid
graph LR
    A[课程体系 math_qe.py] --> B{Search}
    B --> C[LibGenDownloader<br/>7镜像轮询]
    B --> D[AnnaDownloader<br/>备用源]
    C --> E[结果列表]
    D --> E
    E --> F{置信度匹配}
    F --> G[标记 A/B/C]
    G --> H[交互选择 / 自动选择]
    H --> I[下载: Range分块续传]
    I --> J[{dataset_dir}/textbooks/]
    J --> K[入库 PostgreSQL/MySQL]
```

## 来源

| 源 | 优先级 | 策略 | 方法 |
|----|--------|------|------|
| **Library Genesis** | 主源 | 覆盖绝大多数数学教材 | `tools/libgen_downloader.py`: httpx + BeautifulSoup，7 镜像轮询 |
| **Anna's Archive** | 备用 | LibGen 无结果时自动 fallback | `tools/annas_downloader.py`: 搜索详情页→提取 PDF |

## LibGen 下载流程

### 搜索

```
LibGenDownloader.search("Munkres Topology")
  → 7镜像轮询: libgen.li/vg/la/bz/gl/gs/lc
  → GET /index.php?req=Munkres+Topology
  → 解析 <table class="c"> (支持9列/10列两种格式差异)
  → 过滤: ext == "pdf"
  → 返回 list[dict]: title, author, year, lang, size, download_url
```

### 下载 (Range 分块续传)

```
LibGenDownloader.download(url, save_path)
  ├── Step 1: URL 解析
  │   ├── file.php → resolve_get_url() → get.php?md5=...&key=...
  │   └── ads.php → resolve_get_url() → get.php?md5=...&key=...
  │
  ├── Step 2: 完整 GET (先尝试一次完整下载)
  │   ├── 成功(%PDF- 开头 + content-length 匹配) → 保存 ✓
  │   └── 不完整 → 进入 Step 3
  │
  ├── Step 3: Range 分块续传
  │   ├── 获取总大小 (Range: bytes=0-0 → content-range header)
  │   ├── 逐块下载: 每块 3MB (CHUNK=3*1024*1024)
  │   ├── 间隔 3s 避免限速
  │   ├── 最多 3 次僵死重试
  │   └── 全部下载完成 → 保存 ✓
  │
  └── Step 4: 部分保存
      ├── 中断 > 10000 字节且是 PDF → 保存部分文件
      └── 否则 → 返回失败
```

### SSL/代理兼容

```python
# Windows schannel 兼容: 禁用证书验证
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Clash 代理: 从 setting.ini [Proxy] 读取
client = httpx.Client(proxy=proxy_url, verify=ctx)
```

## 置信度匹配

匹配逻辑（在 collector/textbook_hunter.py 编排层实现）：

```python
def match_confidence(result: dict, target: TextbookTarget) -> str | None:
    """返回 'A' / 'B' / 'C' / None"""
    title_sim = fuzzy_match(result["title"], target.title)
    author_sim = fuzzy_match(result["author"], target.author)
    lang = result.get("language", "")

    if title_sim > 0.8 and author_sim > 0.7:
        if target.lang == "zh" and lang == "zh":
            return "A"
        if target.lang == "en" and lang == "en":
            return "B"
    if title_sim > 0.5:
        return "C"
    return None
```

## 待检索课程现状

详见 `docs/knowledge_base/inventory.md` 完整清单。

| # | 课程 | 已有 | 缺失 |
|---|------|------|------|
| 01-02 | 地基 | ✅ 全部 | — |
| 03 | 点集拓扑 | Munkres (B) | 熊金城 (A) |
| 04 | 实分析 | 周民强 (A) | Stein (B) |
| 05 | 复分析 | Ahlfors 中译 (A) | Stein (B), 方企勤 (A) |
| 06 | 泛函分析 | Stein (B) | 张恭庆 (A), 学习指导 (A) |
| 07 | ODE | Tenenbaum (B), 习题解 (A) | 丁同仁 (A) |
| 08 | PDE | ❌ 全缺 | Evans 中/英 |
| 09 | 抽象代数 | Dummit (B) | 冯克勤 (A) |
| 10 | QE | ✅ 全部 | — |
