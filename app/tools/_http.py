"""HTTP 客户端工具 — SSL/代理配置复用"""

import ssl as ssl_mod
import httpx


def make_ssl_context():
    ctx = ssl_mod.SSLContext(ssl_mod.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl_mod.CERT_NONE
    return ctx


def make_http_client(timeout: float = 30.0, proxy: str = "") -> httpx.Client:
    kwargs = {"timeout": timeout, "follow_redirects": True, "verify": make_ssl_context()}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)
