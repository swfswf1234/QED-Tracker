# Book Hunter — 教材检索方案 v0.3

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
| **Z-Library** | 备用 | 仅在可达时尝试，Cloudflare 阻塞则跳过 | `tools/zlib_downloader.py`: singlelogin 页面探测 |

## 一键补缺模式

入口:

```bash
python scripts/hunt_textbooks.py --one-click --missing-only --report dataset/reports/textbooks.md
```

一键模式只处理 `app/curricula/math_qe.py` 中已经给出的教材和习题册，不临时开放搜索新书目。流程:

```mermaid
graph LR
    A[math_qe.py targets] --> B{本地已有?}
    B -->|是| C[SKIP_EXISTS]
    B -->|否| D[LibGen]
    D --> E[Anna]
    E --> F[Z-Library]
    F --> G{严格匹配?}
    G -->|是| H[下载并记录 SUCCESS/FAIL_DOWNLOAD]
    G -->|否| I[PASS_NO_RESULT 或 PASS_NO_EXACT_MATCH]
    H --> J[继续下一项]
    I --> J
```

严格匹配要求:

- 标题相似度达标。
- 目标配置了作者时，候选作者必须包含目标作者 token。
- 语言与目标一致；来源缺语言时允许继续。
- 目标配置了 `edition` 时，候选标题、edition 或年份中必须能匹配版本 token。

状态语义:

| 状态 | 含义 |
| --- | --- |
| `SKIP_EXISTS` | 本地教材目录已有匹配 PDF，不搜索网络。 |
| `SUCCESS` | 已知来源找到严格匹配并下载成功。 |
| `PASS_NO_RESULT` | 已知来源没有搜索结果，跳过并继续。 |
| `PASS_NO_EXACT_MATCH` | 有搜索结果但不满足名称/作者/版本严格匹配，跳过并继续。 |
| `FAIL_DOWNLOAD` | 找到严格匹配但下载失败，记录失败并继续。 |
| `FAIL_SOURCE_UNREACHABLE` | 来源可达性检测失败，记录失败并继续。 |

## 扩展来源探测

`scripts/probe_textbook_sources.py` 用于调研更多下载或手动线索，不参与默认一键下载链路:

```bash
python scripts/probe_textbook_sources.py --target "Evans Partial Differential Equations"
```

当前探测源:

| 源 | 用途 | 自动下载策略 |
| --- | --- | --- |
| Open Library | 官方 Search API 查书目和 Internet Archive 标识 | 只报告 IA 链接，不默认下载 |
| Internet Archive | advancedsearch API 查 texts 条目 | 只报告条目页，后续可按 metadata/files 接入下载 |
| Google Books | Volumes API 查 ebook/PDF 可用性 | 仅报告明确 `pdf.downloadLink` |
| OAPEN/OpenAlex/Crossref | 生成开放获取/元数据手动线索 | 手动线索，不自动下载 |

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
