# DocViewer — 本地文档查看工具使用指南

> 用于解决 wget --mirror 下载的官方文档在 `file://` 协议下
> CSS/JS/图片加载异常、排版错乱的问题。

## 适用场景

已有 xgboost、scikit_learn 等已镜像的官方文档，想本地打开查看。
直接双击 HTML 文件时发现排版与官网不一致、图片显示不全。

## 原理

启动一个本地 HTTP 服务器，将 `dataset/official_docs/` 作为静态文件根目录，
通过 HTTP 协议提供访问。浏览器不再受 `file://` 的安全策略限制，
CSS/JS/图片均可正常加载，排版与官网一致。

## 使用方法

### 启动

```bash
python -m app.tools.serve_docs
```

将自动打开浏览器访问 `http://127.0.0.1:8080`。

### 命令行选项

```bash
# 指定端口
python -m app.tools.serve_docs --port 9090

# 指定监听地址（局域网其他设备访问）
python -m app.tools.serve_docs --host 0.0.0.0 --port 8080

# 不自动打开浏览器
python -m app.tools.serve_docs --no-open

# 查看帮助
python -m app.tools.serve_docs --help
```

### 浏览器访问

服务启动后打开 `http://127.0.0.1:8080` 即可看到入口页面。
页面列出所有已镜像的文档项目，点击卡片进入对应文档。

## 入口页面说明

服务会自动扫描 `dataset/official_docs/` 下的目录：

```
dataset/official_docs/
├── xgboost/          ← 显示为卡片：xgboost
├── scikit_learn/     ← 显示为卡片：scikit_learn
└── pytorch/          ← 后续镜像后自动出现
```

每个目录必须包含 `index.html` 作为入口文件，
DocServer 会自动查找并生成链接。

## 已镜像项目一览

| 项目 | 状态 | 文件数 |
|------|------|--------|
| xgboost | ✅ 完成 | 276 |
| scikit_learn | ✅ 完成 | 203 |
| pytorch | ⬜ 待镜像 | — |
| yolo | ⬜ 待镜像 | — |

## 停止服务

在终端按 `Ctrl+C` 即可停止。

## 注意事项

- 仅用于本地访问，不要暴露到公网
- 服务不消耗网络流量，所有文件已下载到本地
- 如需添加新文档，运行 `python scripts/hunt_docs.py --name <name>` 先下载
