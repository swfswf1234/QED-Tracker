# PyTorch 官方文档本地镜像指南

> 将 PyTorch 官方文档 (https://pytorch.org/docs/stable/) 下载到本地，
> 通过本地 HTTP 服务查看，排版、交互、图片均与官网一致，无需网络。

## 前置条件

- WSL 已安装（`wsl.exe --version` 确认）
- WSL 中已安装 wget（`wsl wget --version` 确认）
- QED-Tracker 环境已配置

## 下载 PyTorch 文档

### 方式一：通过脚本下载（推荐）

```bash
python scripts/hunt_docs.py --name pytorch
```

下载完成后自动记录到数据库。

### 方式二：手动 wget 下载

```bash
wsl wget --mirror --convert-links --adjust-extension \
  --page-requisites --no-parent --no-host-directories \
  --wait=2 --random-wait --limit-rate=1M \
  --user-agent="Mozilla/5.0 (compatible; QED-Tracker/0.2)" \
  -P /mnt/e/qed/QED-Tracker/dataset/official_docs/pytorch \
  https://pytorch.org/docs/stable/
```

### 方式三：在代码中调用

```python
from app.collectors.doc_scraper import DocScraper

scraper = DocScraper()
result = scraper.scrape("pytorch", "https://pytorch.org/docs/stable/")
print(f"下载完成: {result['file_count']} 个文件")
```

## 本地查看

下载完成后，启动 DocServer：

```bash
python -m app.tools.serve_docs
```

浏览器打开 `http://127.0.0.1:8080`，点击 **pytorch** 卡片进入。

## 文件结构说明

下载后的目录结构：

```
dataset/official_docs/pytorch/
├── index.html              ← 首页（从这里进入）
├── _static/                ← CSS、JS、字体
├── _images/                ← 文档中的图片
├── _sources/               ← Sphinx 源文件
├── tensors.html            ← Tensor 文档
├── autograd.html           ← 自动求导
├── nn.html                 ← 神经网络 API
├── optim.html              ← 优化器
├── data.html               ← 数据加载
├── ...                      ← 其他页面
```

## 常见问题

### 排版与原版不一致

**原因**: 直接用浏览器双击 HTML 文件打开（`file://` 协议）。
**解决**: 必须通过 DocServer 的 HTTP 服务访问。

```
# 正确方式
python -m app.tools.serve_docs  →  http://127.0.0.1:8080

# 错误方式
双击 dataset/official_docs/pytorch/index.html  ← 排版错乱
```

### 图片加载不出来

**原因**: `file://` 协议下相对路径解析异常。
**解决**: 使用 DocServer（HTTP 服务），所有资源自动正确加载。

### 搜索功能无法使用

PyTorch 文档使用 Sphinx 静态生成，搜索依赖客户端 JS。
通过本地 HTTP 服务打开后，搜索功能正常工作。

### 下载速度慢

wget 默认限制 1MB/s 避免被封。可调整 `--limit-rate` 参数：
```bash
# 不限速（慎用）
--limit-rate=0
# 提高到 5MB/s
--limit-rate=5M
```

### 更新文档

重新运行同样的脚本即可增量覆盖：

```bash
python scripts/hunt_docs.py --name pytorch
```

wget 的 `--mirror` 模式会自动比较时间戳，只下载新文件。

## 参考

- DocServer 使用说明: `docs/design/doc_viewer_guide.md`
- 文档爬取脚本: `scripts/hunt_docs.py`
- 镜像工具: `app/tools/wget_mirror.py`
