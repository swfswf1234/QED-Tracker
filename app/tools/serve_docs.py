"""DocServer — 本地文档 HTTP 服务

在本地启动 HTTP 服务器，将 dataset/official_docs/ 下的 wget 镜像文档
通过 HTTP 协议提供访问，解决 file:// 协议下 CSS/JS/图片加载异常的问题。

用法:
    python -m app.tools.serve_docs
    python -m app.tools.serve_docs --port 9090
    python -m app.tools.serve_docs --host 0.0.0.0 --port 8080
"""

import argparse
import webbrowser
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote

from app.core.config import settings


DOCS_DIR = settings.dataset_path / "official_docs"


class DocsHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS_DIR.resolve()), **kwargs)

    def log_message(self, fmt, *args):
        print(f"[DocServer] {args[0]} {args[1]} {args[2]}")

    def do_GET(self):
        path = unquote(self.path)
        if path == "/" or path == "/index.html":
            self._serve_index()
        else:
            super().do_GET()

    def _serve_index(self):
        html = self._build_index_html()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _build_index_html(self) -> str:
        items = []
        if DOCS_DIR.exists():
            for entry in sorted(DOCS_DIR.iterdir()):
                if entry.is_dir():
                    index = self._find_entry_file(entry)
                    if index:
                        items.append((entry.name, index))

        cards = ""
        for name, rel_path in items:
            cards += f"""
            <div class="doc-card" onclick="location.href='{rel_path}'">
                <div class="doc-icon">📖</div>
                <div class="doc-name">{name}</div>
                <div class="doc-path">{rel_path}</div>
            </div>"""

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QED DocViewer — 本地文档入口</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       background: #f5f5f5; color: #333; min-height: 100vh; }}
.header {{ background: linear-gradient(135deg, #1a1a2e, #16213e);
          color: #fff; padding: 40px 20px; text-align: center; }}
.header h1 {{ font-size: 28px; margin-bottom: 8px; }}
.header p {{ opacity: 0.8; font-size: 14px; }}
.container {{ max-width: 1000px; margin: 0 auto; padding: 30px 20px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
         gap: 20px; }}
.doc-card {{ background: #fff; border-radius: 12px; padding: 24px; cursor: pointer;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08); transition: transform 0.15s, box-shadow 0.15s; }}
.doc-card:hover {{ transform: translateY(-3px); box-shadow: 0 6px 20px rgba(0,0,0,0.12); }}
.doc-icon {{ font-size: 36px; margin-bottom: 12px; }}
.doc-name {{ font-size: 18px; font-weight: 600; margin-bottom: 6px; }}
.doc-path {{ font-size: 12px; color: #888; word-break: break-all; }}
.empty {{ text-align: center; padding: 80px 20px; color: #999; }}
.empty h2 {{ font-size: 22px; margin-bottom: 10px; }}
.footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
</style>
</head>
<body>
<div class="header">
    <h1>QED DocViewer</h1>
    <p>本地官方文档镜像 — 点击卡片进入对应文档</p>
</div>
<div class="container">
    {cards if cards else '''
    <div class="empty">
        <h2>暂无文档镜像</h2>
        <p>请先运行 <code>python scripts/hunt_docs.py --all</code> 下载文档</p>
    </div>'''}
</div>
<div class="footer">QED-Tracker · dataset/official_docs/</div>
</body>
</html>"""

    @staticmethod
    def _find_entry_file(directory: Path) -> str | None:
        candidates = ["index.html", "index.htm"]
        for c in candidates:
            p = directory / c
            if p.exists():
                return f"{directory.name}/{c}"
        first_html = next(directory.rglob("*.html"), None)
        if first_html:
            return str(first_html.relative_to(DOCS_DIR).as_posix())
        return None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="QED DocViewer — 本地文档 HTTP 服务")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="监听地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="监听端口 (默认 8080)")
    parser.add_argument("--open", action="store_true", default=True, help="自动打开浏览器 (默认开启)")
    parser.add_argument("--no-open", action="store_false", dest="open", help="不自动打开浏览器")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    if not DOCS_DIR.exists():
        DOCS_DIR.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), DocsHandler)
    url = f"http://{args.host}:{args.port}"

    print(f"{'='*50}")
    print(f"  QED DocViewer 启动")
    print(f"  URL:  {url}")
    print(f"  目录: {DOCS_DIR}")
    print(f"{'='*50}")
    print(f"  已镜像项目:")
    if DOCS_DIR.exists():
        for entry in sorted(DOCS_DIR.iterdir()):
            if entry.is_dir():
                index = DocsHandler._find_entry_file(entry)
                if index:
                    print(f"    ✅ {entry.name} -> {url}/{index}")
                else:
                    print(f"    ⚠️  {entry.name} (未找到入口 HTML)")
    print(f"{'='*50}")

    if args.open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[DocServer] 服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
