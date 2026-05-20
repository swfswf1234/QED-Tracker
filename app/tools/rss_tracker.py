"""RSS/API tracker — fetch articles from Quanta Magazine and Terry Tao blog"""

import xml.etree.ElementTree as ET
from typing import Optional

import httpx
from loguru import logger

from app.tools._http import make_http_client

QUANTA_URL = "https://www.quantamagazine.org/feed/"
TAO_RSS_URL = "https://terrytao.wordpress.com/feed/"


class RssTracker:
    def __init__(self, proxy: str = ""):
        self.proxy = proxy
        self.client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self.client is None:
            self.client = make_http_client(timeout=30.0, proxy=self.proxy)
        return self.client

    def fetch_quanta(self) -> list[dict]:
        client = self._get_client()
        try:
            resp = client.get(QUANTA_URL)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as e:
            logger.error(f"Quanta RSS 请求失败: {e}")
            return []

        articles = []
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            desc = item.findtext("description", "")
            creator = item.findtext("{http://purl.org/dc/elements/1.1/}creator", "Quanta Magazine")
            pub_date = item.findtext("pubDate", "")
            articles.append({
                "title": title,
                "url": link,
                "description": desc[:500] if desc else "",
                "author": creator,
                "platform": "Quanta Magazine",
                "resource_type": "article",
                "published_at": pub_date,
            })
        logger.info(f"Quanta: 获取 {len(articles)} 篇文章")
        return articles

    def fetch_tao_blog(self) -> list[dict]:
        client = self._get_client()
        try:
            resp = client.get(TAO_RSS_URL)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as e:
            logger.error(f"Tao Blog RSS 请求失败: {e}")
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom",
              "dc": "http://purl.org/dc/elements/1.1/"}
        posts = []
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            desc = item.findtext("description", "")
            creator = item.findtext("dc:creator", "Terence Tao", ns)
            pub_date_str = item.findtext("pubDate", "")

            posts.append({
                "title": title,
                "url": link,
                "description": desc[:500] if desc else "",
                "author": creator,
                "platform": "Terence Tao Blog",
                "resource_type": "blog",
                "published_at": pub_date_str,
            })

        logger.info(f"Tao Blog: 获取 {len(posts)} 篇文章")
        return posts

    def fetch_all(self) -> list[dict]:
        seen = set()
        all_items = []
        for item in self.fetch_quanta() + self.fetch_tao_blog():
            if item["url"] and item["url"] not in seen:
                seen.add(item["url"])
                all_items.append(item)
        all_items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        logger.info(f"去重后共 {len(all_items)} 篇新文章")
        return all_items

    def close(self):
        if self.client:
            self.client.close()
            self.client = None


SEED_ARTICLES = [
    {
        "title": "The Random Geometry at the Heart of Physics",
        "url": "https://www.quantamagazine.org/the-random-geometry-at-the-heart-of-physics-20230501/",
        "description": "Random geometry, physics and probability theory core connection",
        "author": "Quanta Magazine",
        "platform": "Quanta Magazine",
        "resource_type": "article",
        "course_tags": ["probability", "geometry"],
    },
    {
        "title": "Mathematicians Prove 2D Version of Quantum Gravity Conjecture",
        "url": "https://www.quantamagazine.org/mathematicians-prove-2d-version-of-quantum-gravity-conjecture-20230501/",
        "description": "PDE, geometric topology, quantum gravity frontier",
        "author": "Quanta Magazine",
        "platform": "Quanta Magazine",
        "resource_type": "article",
        "course_tags": ["pde", "topology"],
    },
    {
        "title": "Simons Lectures: The cosmic distance ladder",
        "url": "https://terrytao.wordpress.com/2023/07/15/simons-lectures-the-cosmic-distance-ladder/",
        "description": "Measure theory and harmonic analysis lecture notes",
        "author": "Terence Tao",
        "platform": "Terence Tao Blog",
        "resource_type": "blog",
        "course_tags": ["real_analysis", "measure"],
    },
    {
        "title": "Discrete random matrices",
        "url": "https://terrytao.wordpress.com/2023/08/20/discrete-random-matrices/",
        "description": "High-dimensional probability and random matrix theory introductory post",
        "author": "Terence Tao",
        "platform": "Terence Tao Blog",
        "resource_type": "blog",
        "course_tags": ["probability", "linear_algebra"],
    },
]
