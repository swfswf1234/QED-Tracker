"""tools 包 — 所有工具通过 __getattr__ 懒导入，避免单依赖缺失拖垮全部"""

import importlib

__all__ = [
    "LibGenDownloader",
    "AnnaDownloader",
    "search_papers",
    "search_by_keywords",
    "GitHubDownloader",
    "VideoTracker",
    "setup_logger",
    "WgetMirror",
    "serve_docs",
]

_MODULE_MAP = {
    "LibGenDownloader": "app.tools.libgen_downloader",
    "AnnaDownloader": "app.tools.annas_downloader",
    "search_papers": "app.tools.arxiv_fetcher",
    "search_by_keywords": "app.tools.arxiv_fetcher",
    "GitHubDownloader": "app.tools.github_downloader",
    "VideoTracker": "app.tools.video_tracker",
    "setup_logger": "app.tools.logger",
    "WgetMirror": "app.tools.wget_mirror",
    "serve_docs": "app.tools.serve_docs",
}


def __getattr__(name):
    if name in _MODULE_MAP:
        mod = importlib.import_module(_MODULE_MAP[name])
        attr = getattr(mod, name)
        globals()[name] = attr
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
